from pydantic import BaseModel
import os
import functools  

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, function_tool, RunContextWrapper
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
import env_setup
from agents import Agent, OpenAIChatCompletionsModel, AsyncOpenAI

from agent.prompts import custom_instructions
from config import settings

verify_model, verify_api_key, verify_base_url = settings.code_agent_settings

try:
    from .tools.lean_verify_mcp import verify_lean_code
    load_tool_success = True
except Exception as e:
    print(e)
    load_tool_success = False

external_client = AsyncOpenAI(
    api_key=verify_api_key,
    base_url=verify_base_url,
)

import logging
logger = logging.getLogger('verify_agent')
logger.setLevel(level = logging.INFO)


if load_tool_success:
    verify_agent = Agent(
        name="Verify Agent",
        handoff_description="A helpful agent for verify lean code and give modify advices.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=verify_model,
            openai_client=external_client,
            ),
        tools=[verify_lean_code],
    )
else:
    verify_agent = None

async def verify_agent_generator(server_dict: dict):
    """
    server_dict: {
        "servers":{ 
        "server_name1":"server_url",
        "server_name2":"server_url",
        },
        "thread_id":"thread_id"
    """
    mcp_servers = []
    all_skills = []
    run_id = server_dict["thread_id"]
    for name in server_dict["servers"]:
        url = server_dict["servers"][name]

        mcp_server = MCPServerSse(
                name=name,
                params={
                    "url": url,
                    "timeout": 2*60*60,
                    # "sse_read_timeout":60*20
                },
                client_session_timeout_seconds=2*60*60,
                run_id=run_id,
            )
        await mcp_server.connect()
        mcp_servers.append(mcp_server)

        skills_info = await discover_skills(mcp_server)
        if skills_info:
            all_skills.append(f"Server {name}:\n{skills_info}")
    
    combined_skills = "\n\n".join(all_skills)

    verify_agent = Agent(
        name="Verify Agent",
        handoff_description="A helpful agent for verify lean code and give modify advices.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=verify_model,
            openai_client=external_client,
            ),
        mcp_servers=mcp_servers,
    )
    if combined_skills:
        verify_agent.skills = combined_skills
    print("verify_agent instance created")
    return verify_agent
