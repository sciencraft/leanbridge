import env_setup
import asyncio
import uuid
import sys
import os
import mlflow
from openai import OpenAI
from openai.types.responses import ResponseTextDeltaEvent
from dotenv import load_dotenv

# Standard agents SDK imports
from agents import (
    Agent,
    Runner,
    trace,
)
from agents.exceptions import AgentsException
from agents.cognition.cognition import CognitionModule

# Local imports
from agent.data_model import ChatContext
from agent.plan_agent import lean_agents_generator
from config import settings

load_dotenv(override=True)

# Centralized settings
plan_model, plan_api_key, plan_base_url = settings.plan_agent_settings
memory_server_url = settings.memory_server_url
track_name = settings.track_name

# MLFlow setup
mlflow.openai.autolog()
mlflow.set_experiment(track_name)

async def main(server_dict):
    """Main interactive CLI loop for LeanBridge."""
    # Initialize agents
    lean_agents = await lean_agents_generator(server_dict)
    
    current_agent: Agent[ChatContext] = lean_agents["Plan Agent"]
    input_items = []
    context = ChatContext()
    
    thread_id = 'test_cli'
    # Match user's think_mode logic
    think_mode = '/no_think' if 'qwen3' in plan_model.lower() else ''
    with_cognition = False
    user = os.getenv("USER", "test_user")
    stream_mode = True

    context.user_name = user
    context.user_id = '1'
    context.thread_id = thread_id
    context.current_agent = current_agent.name

    if with_cognition:
        cognition_client = OpenAI(base_url=plan_base_url, api_key=plan_api_key)
        cognition = CognitionModule(
            cognition_client, 
            thread_id, 
            model=plan_model, 
            memory_url=memory_server_url
        )
    else:
        cognition = None

    print(f"Starting LeanBridge CLI 🚀\nUser: {user} | Conversation: {thread_id} | Model: {plan_model}\n with cognition: {with_cognition}, stream mode: {stream_mode}")

    agent_err = ''
    user_input = ''
    while True:
        try:
            if not agent_err:
                user_input = input(f"\n\033[90mUser ({user})\033[0m: ")
            
            if not user_input.strip():
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                break

            if think_mode:
                user_input += think_mode

            with trace(track_name, group_id=thread_id):
                if agent_err:
                    input_items[-1]['content'] = user_input
                    agent_err = ''
                else:
                    input_items.append({
                        "content": user_input, 
                        "role": "user", 
                        'name': user, 
                        'type': 'message', 
                        'uuid': str(uuid.uuid4().hex[:16])
                    })

                if stream_mode:
                    result = Runner.run_streamed(current_agent, input_items, context=context, cognition=cognition)
                    is_start = True
                    async for event in result.stream_events():
                        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                            if is_start:
                                print(f"\033[94mAgent ({current_agent.name})\033[0m: {event.data.delta}", end="", flush=True)
                                is_start = False
                            else:
                                print(event.data.delta, end="", flush=True)
                        elif event.type == "agent_updated_stream_event":
                            if current_agent.name != event.new_agent.name:
                                print(f"\n🔄 Handed off from {current_agent.name} to {event.new_agent.name}")
                                print(event)
                                current_agent = event.new_agent
                                is_start = True
                        elif event.type == "run_item_stream_event":
                            is_start = True
                            if event.item.type == "tool_call_item":
                                print(f"\n\033[94mAgent ({current_agent.name})\033[0m: Tool was called\n {event.item.raw_item}")
                            elif event.item.type == "tool_call_output_item":
                                print(f"\n\033[94mAgent ({current_agent.name})\033[0m: Tool call output: {event.item.raw_item}")
                else:
                    result = await Runner.run(current_agent, input_items, context=context, cognition=cognition)
            
        except AgentsException as e:
            agent_err = f'Agent meet error: {e}, try to solve.'
            print(f"\033[91m{agent_err}\033[0m")
            if input_items:
                user_input = input_items[-1]['content'].replace(think_mode, '')
            else:
                user_input = "Retry"
            user_input = f"{user_input} ({agent_err})"
            continue
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\033[91mUnexpected Error: {e}\033[0m")
            break # Exit on serious unexpected errors
            
        finally:
            # Result processing logic from requested snippet
            if 'result' in locals():
                if not stream_mode:
                    from agents import MessageOutputItem, HandoffOutputItem, ToolCallItem, ToolCallOutputItem, ItemHelpers
                    for new_item in result.new_items:
                        agent_name = new_item.agent.name
                        if isinstance(new_item, MessageOutputItem):
                            content = ItemHelpers.text_message_output(new_item)
                            content = ('</think>'.join(content.split('</think>')[1:])).strip()
                            print(f"\033[94mAgent ({agent_name})\033[0m: {content}")
                        elif isinstance(new_item, HandoffOutputItem):
                            print(f"Handed off from {new_item.source_agent.name} to {new_item.target_agent.name}")
                        elif isinstance(new_item, ToolCallItem):
                            print(f"\033[94mAgent ({agent_name})\033[0m: Calling a tool: {new_item.raw_item.name}")
                        elif isinstance(new_item, ToolCallOutputItem):
                            print(f"\033[94mAgent ({agent_name})\033[0m: Tool call output: {new_item.output}")
                    current_agent = result.last_agent
                
                input_items = result.to_input_list()
                for item in input_items:
                    if isinstance(item, dict):
                        if 'uuid' not in item:
                            item['uuid'] = str(uuid.uuid4().hex[:16])
                        if think_mode and item.get('type') == 'message':
                            if item.get('role') == 'user':
                                item['content'] = item['content'].replace(think_mode, '')
                            elif isinstance(item.get('content'), list) and len(item['content']) > 0 and 'text' in item['content'][0]:
                                content = item['content'][0]['text']
                                if '</think>' in content:
                                    item['content'][0]['text'] = ('</think>'.join(content.split('</think>')[1:])).strip()

                context.current_agent = current_agent.name

if __name__ == "__main__":
    server_dict = {}
    try:
        asyncio.run(main(server_dict))
    except KeyboardInterrupt:
        pass
