import env_setup  # Standardize environment for the monorepo
import os, json, uuid, asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import List, Dict, AsyncIterator, Iterator, Any

import uvicorn, sys
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from cachetools import TTLCache
import config

from openai.types.responses import ResponseTextDeltaEvent
from openai import OpenAI

from ag_ui.core import (
    RunAgentInput,
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    TextMessageChunkEvent,
    ToolCallChunkEvent,
    ToolCallResultEvent,
    Message,
    StateSnapshotEvent
)
from ag_ui.encoder import EventEncoder

from agents import (
    Agent,
    ReasoningItem,
    Runner,
    trace,
)
from agents.exceptions import AgentsException, ModelBehaviorError
from agents.cognition.cognition import CognitionModule
from agents.cognition.data_model import MentalState
from agents.cognition.rag import get_user_database_func

import crud
from database import get_db, engine
from schemas import LoginRequest, TokenResponse, SetUserDocumentsRequest
from auth import get_current_user, create_access_token, verify_access_token, strengthen
from utils import ensure_string, merge_async_generators, build_agent_state
from gateway import router as gateway_router
from agent.plan_agent import lean_agents_generator
from agent.data_model import ChatContext

settings = config.settings

# --- Global State & Caches ---
MAX_SESSIONS = 100
SESSION_TTL = 7200

cognition_bank = TTLCache(maxsize=MAX_SESSIONS, ttl=SESSION_TTL)
messages_bank = TTLCache(maxsize=MAX_SESSIONS, ttl=SESSION_TTL)
current_agent_bank = TTLCache(maxsize=MAX_SESSIONS, ttl=SESSION_TTL)
user_agent_bank = TTLCache(maxsize=MAX_SESSIONS, ttl=SESSION_TTL)

# Store active MCP connections for cleanup
active_mcp_clients: dict[str, list] = {}
empty_mental_state = MentalState().model_dump()

executor = ThreadPoolExecutor(max_workers=4)

# --- Background Tasks ---
async def cleanup_expired_sessions():
    """Background task to cleanup disconnected/expired agents and their MCP connections."""
    while True:
        try:
            await asyncio.sleep(600)
            # Evict expired keys manually to trigger cleanup
            _ = list(user_agent_bank.keys())
            
            evicted_threads = []
            for thread_id, mcp_servers_list in active_mcp_clients.items():
                if thread_id not in user_agent_bank:
                    evicted_threads.append(thread_id)
                    for mcp in mcp_servers_list:
                        try:
                            await mcp.cleanup()
                            print(f"Disconnected MCP Server for evicted session {thread_id}")
                        except Exception as e:
                            print(f"Failed to disconnect MCP Server for {thread_id}: {e}")
                            
            for thread_id in evicted_threads:
                del active_mcp_clients[thread_id]
                
        except Exception as e:
            print(f"Cleanup error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    yield
    cleanup_task.cancel()

# --- App Instantiation ---
app = FastAPI(title="Lean Bridge Agents AG-UI Endpoint", lifespan=lifespan)
app.include_router(gateway_router, prefix="/gateway", tags=["gateway"])


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions ---
async def get_user_documents(username: str, rag_key: str, db: Session) -> dict:
    if not rag_key:
        return {}
    user_config = crud.get_user_config(db, username)
    rag_base_url = user_config.rag_base_url if user_config and user_config.rag_base_url else settings.rag_base_url
    
    rag_documents_str = await get_user_database_func(rag_key, rag_base_url)
    rag_documents_dict = json.loads(rag_documents_str)
    if rag_documents_dict.get("Result"):
        return rag_documents_dict["Result"]
    return {}

async def get_user_agent_names(username: str) -> list:
    return ["Plan Agent", "Search Agent", "Code Agent", "Verify Agent"]

# --- Routes ---
@app.post("/api/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, req.username)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
    password_strengthened = strengthen(req.password, req.username)
    if password_strengthened == db_user.password_hash:
        token = create_access_token(req.username)
        user_config = crud.get_user_config(db, req.username)
        rag_api_key = user_config.rag_api_key if user_config else None
        
        documents = await get_user_documents(req.username, rag_api_key, db)
        agent_names = await get_user_agent_names(req.username)
        return {
            "message": "Login successful", 
            "token": token, 
            "documents": documents, 
            "agent_names": agent_names
        }
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

@app.get("/api/verify")
async def verify(current_user: str = Depends(get_current_user)):
    return {"message": f"Welcome, {current_user}!"}

@app.post("/api/set_user_documents")
async def set_user_documents(req: SetUserDocumentsRequest, username: str = Depends(get_current_user)):
    print("收到 selected:", req.selected, username)
    return {"message": "ok"}

@app.post("/")
async def agentic_chat_endpoint(input_data: RunAgentInput, request: Request, db: Session = Depends(get_db)):
    """Agentic chat endpoint"""
    accept_header = request.headers.get("accept")
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.replace("Bearer ", "")
    username = verify_access_token(token)
    print(f'----user: {username}----')

    encoder = EventEncoder(accept=accept_header)
    if not input_data.thread_id:
        input_data.thread_id='test'
    if not input_data.run_id:
        input_data.run_id=str(uuid.uuid4().hex[:16])

    user_config = crud.get_user_config(db, username)
    server_dict = user_config.mcp_servers if user_config else {}

    print(f'----Agent state----\n{input_data.state}')
    agent_settings = input_data.state["settings"]
    agent_context = input_data.state["agent_context"]

    # Use settings for plan agent model
    plan_model, plan_key, plan_url = settings.plan_agent_settings
    memory_model, mem_key, mem_url = settings.memory_agent_settings

    think = agent_settings["think"]
    add_think_tokens = '/no_think' if not think and 'qwen3' in plan_model.lower() else ''

    if input_data.thread_id not in user_agent_bank:
        agents_dict = await lean_agents_generator(server_dict)
        user_agent_bank[input_data.thread_id] = agents_dict
        
        collected_mcps = []
        for ag in agents_dict.values():
            if hasattr(ag, "mcp_servers") and ag.mcp_servers:
                collected_mcps.extend(ag.mcp_servers)
        active_mcp_clients[input_data.thread_id] = collected_mcps
        
    if input_data.thread_id not in current_agent_bank:
        current_agent_bank[input_data.thread_id] = user_agent_bank[input_data.thread_id]["Plan Agent"]
    current_agent: Agent[ChatContext] = current_agent_bank[input_data.thread_id]

    if not input_data.context:
        print('----init context----')
        context = ChatContext()
        context.user_name = username
        context.user_id = '1'
        context.rag={"api_key": settings.rag_api_key,
                     "base_url": settings.rag_base_url}
        context.thread_id = input_data.thread_id
        context.current_agent = current_agent.name
        context.with_cognition = agent_settings["cognition"]
        context.agent_context = agent_context
        input_data.context = [context]

    has_user_input = update_user_input(input_data.context[0], input_data.messages, add_think_tokens)

    if has_user_input:
        if input_data.context[0].with_cognition:
            cognition_client = OpenAI(api_key=plan_key, base_url=plan_url)
            if input_data.thread_id in cognition_bank:
                cognition_bank[input_data.thread_id].assistant_settings = agent_settings
                cognition_bank[input_data.thread_id].assistant_context = agent_context
                cognition = cognition_bank[input_data.thread_id]
            else:
                cognition = CognitionModule(
                    cognition_client, 
                    input_data.thread_id, 
                    model=plan_model, 
                    memory_url=settings.memory_server_url,
                    rag_api=input_data.context[0].rag
                    )
                await cognition.init_assistant_tools(user_agent_bank[input_data.thread_id], input_data.context[0])
                await cognition.init_user_database()
                cognition.assistant_settings = agent_settings
                cognition.assistant_context = agent_context
                cognition_bank[input_data.thread_id] = cognition
        else:
            cognition = None

        async def event_generator():
            nonlocal current_agent
            nonlocal cognition, agent_settings, agent_context
            user_input = ''
            need_run = True
            max_try = 3
            max_autopilot = 20
            yield ":ok\n\n"
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=input_data.thread_id,
                    run_id=input_data.run_id
                ),
            )
            while max_try and max_autopilot and need_run:
                result = None
                input_items = messages_bank[input_data.thread_id]
                print(f'----input_items---try: {4-max_try}----\n{input_items}')                
                try:
                    if cognition:
                        cognition._state_closed = False

                    async def main_events():
                        nonlocal current_agent, cognition, agent_settings, agent_context
                        nonlocal result, need_run, input_items 

                        snapshot = build_agent_state(cognition, current_agent.name, agent_settings, empty_mental_state, agent_context)
                        yield encoder.encode(
                                StateSnapshotEvent(
                                    type=EventType.STATE_SNAPSHOT,
                                    snapshot=snapshot
                                )
                            )

                        result = Runner.run_streamed(current_agent, input_items, context=input_data.context[0], cognition=cognition)
                       
                        is_start = True
                        message_id = None
                        need_run = False

                        try:
                            async for event in result.stream_events():
                                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                                    if is_start:
                                        message_id = str(uuid.uuid4())
                                        is_start = False
                                    
                                    yield encoder.encode(
                                        TextMessageChunkEvent(
                                            type=EventType.TEXT_MESSAGE_CHUNK,
                                            message_id=message_id,
                                            delta=event.data.delta
                                        )
                                    )
                                elif event.type == "reasoning_item_event":
                                    # Support for reasoning content in latest SDK
                                    reasoning_item: ReasoningItem = event.item
                                    yield encoder.encode(
                                        TextMessageChunkEvent(
                                            type=EventType.TEXT_MESSAGE_CHUNK,
                                            message_id=message_id,
                                            delta=reasoning_item.summary[0].text if reasoning_item.summary else ""
                                        )
                                    )
                                elif event.type == "agent_updated_stream_event":
                                    if current_agent.name != event.new_agent.name:
                                        current_agent = event.new_agent
                                        input_data.context[0].current_agent = current_agent.name
                                        current_agent_bank[input_data.thread_id] = current_agent
                                        is_start = True
                                        snapshot = build_agent_state(cognition, current_agent.name, agent_settings, empty_mental_state, agent_context)
                                        yield encoder.encode(
                                                StateSnapshotEvent(
                                                    type=EventType.STATE_SNAPSHOT,
                                                    snapshot=snapshot
                                                )
                                            )
                                elif event.type == "run_item_stream_event":
                                    is_start = True
                                    if event.item.type == "tool_call_item":
                                        tool_call_item = event.item.raw_item
                                        yield encoder.encode(
                                            ToolCallChunkEvent(
                                                type=EventType.TOOL_CALL_CHUNK,
                                                tool_call_id=tool_call_item.call_id,
                                                tool_call_name=tool_call_item.name if tool_call_item.name else None,
                                                parent_message_id=message_id,
                                                delta=tool_call_item.arguments if tool_call_item.arguments else None,
                                            )
                                        )
                                    elif event.item.type == "tool_call_output_item":
                                        tool_call_item = event.item.raw_item
                                        tool_message_id = str(uuid.uuid4().hex[:16])
                                        yield encoder.encode(
                                            ToolCallResultEvent(
                                                type=EventType.TOOL_CALL_RESULT,
                                                tool_call_id=tool_call_item["call_id"],
                                                message_id=tool_message_id,
                                                content=ensure_string(tool_call_item["output"]),
                                                role='tool'
                                            )
                                        )
                        except ModelBehaviorError as e:
                            if cognition:
                                cognition.close_state_stream()
                            raise

                        if cognition:
                            cognition.close_state_stream()
                    
                    async def state_events():
                        if cognition is None:
                            return
                        async for snapshot in cognition.state_changes():
                            yield encoder.encode(
                                StateSnapshotEvent(
                                    type=EventType.STATE_SNAPSHOT,
                                    snapshot=snapshot
                                )
                            )

                    async for chunk in merge_async_generators(main_events(), state_events()):
                        if isinstance(chunk, Exception):
                            raise chunk
                        yield chunk

                except AgentsException as e:
                    agent_err = f'Agent meet error: {e}, try to solve.'
                    user_input = input_items[-1]['content'].replace(add_think_tokens, '')
                    if cognition:
                        user_input = cognition.COGNITION_TAG_PATTERN.sub('', user_input)
                    user_input = f'{user_input} ({agent_err})'
                    max_try -= 1
                    need_run = True
                    continue
                except Exception as error:
                    yield encoder.encode(
                        RunErrorEvent(type=EventType.RUN_ERROR, message=str(error))
                    )
                finally:
                    if result:
                        input_items = result.to_input_list()
                        last_user_index = -1
                        for i, item in enumerate(input_items):
                            if 'uuid' not in item:
                                item['uuid'] = str(uuid.uuid4().hex[:16])
                            if item['type']=='message':
                                if add_think_tokens and item['role']=='user':
                                    last_user_index = i
                                    item['content'] = item['content'].replace(add_think_tokens, '')
                                if item['role']=='assistant':
                                    content = item['content'][0]['text'].strip()
                                    if content.startswith('<think>'):
                                        content = ('</think>'.join(content.split('</think>')[1:])).strip()
                                    item['content'][0]['text'] = content

                        if need_run and user_input:
                            input_items[last_user_index]['content'] = user_input
                        elif agent_settings['autopilot'] and cognition:
                            if cognition.eval_end == 'no':
                                auto_input = {"role": 'user', "name": "Eval Agent", "type":"message", "content": cognition.guide_sentence, "uuid":str(uuid.uuid4().hex[:16])}
                                input_items.append(auto_input)
                                need_run = True
                                max_try = 3
                                max_autopilot -= 1

                        messages_bank[input_data.thread_id] = input_items
                        input_data.context[0].current_agent = current_agent.name
            
            yield encoder.encode(
                RunFinishedEvent(
                    type=EventType.RUN_FINISHED,
                    thread_id=input_data.thread_id,
                    run_id=input_data.run_id
                ),
            )
        
        return StreamingResponse(
            event_generator(),
            media_type=encoder.get_content_type()
        )
    else:
        async def error_generator():
            yield encoder.encode(
                RunErrorEvent(type=EventType.RUN_ERROR, message="No valid user input!")
            )
        return StreamingResponse(
            error_generator(),
            media_type=encoder.get_content_type()
        )

def update_user_input(context: ChatContext, messages: List[Message], add_think_tokens: str):
    if len(messages) > 0:
        if messages[-1].role == 'user' and messages[-1].content:
            content = messages[-1].content + add_think_tokens if add_think_tokens else messages[-1].content
            uid = messages[-1].id if messages[-1].id else str(uuid.uuid4().hex[:16])
            user_input = {"role": 'user', "name": context.user_name, "type":"message", "content": content, "uuid":uid}
            if context.thread_id in messages_bank:
                messages_bank[context.thread_id].append(user_input)
            else:
                messages_bank[context.thread_id] = [user_input]
            return True
    return False

def main():
    """Run the uvicorn server."""
    port = settings.port
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )

if __name__ == "__main__":
    main()
