from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, function_tool, RunContextWrapper
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
import env_setup

from agent.data_model import ChatContext
from agent.prompts import custom_instructions
from config import settings

code_model, code_api_key, code_base_url = settings.code_agent_settings

try:
    from .tools.code_tools import lean_code_generator
    load_tool_success = True
except Exception as e:
    print(e)
    load_tool_success = False


external_client = AsyncOpenAI(
    api_key=code_api_key,
    base_url=code_base_url,
)

import logging
logger = logging.getLogger('code_agent')
logger.setLevel(level = logging.INFO)


@function_tool
async def update_workdir(
    context: RunContextWrapper[ChatContext], workdir: str) -> str:
    """
    Update the workdir for code environment.

    Args:
        workdir: The confirmation number for the flight.
    """
    context.context.workdir = workdir

    logger.info(f'Updated the workdir to {workdir}')

    return f"Updated the workdir to {workdir} for code environment"

if load_tool_success:
    code_agent = Agent(
        name="Code Agent",
        handoff_description="A helpful agent for lean code generation, code review and code bug fixer.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=code_model,
            openai_client=external_client,
            ),
        tools=[lean_code_generator],
    )
else:
    code_agent = None

async def code_agent_generator(server_dict: dict):
    """
    server_dict: { 
        "server_name1":"server_url",
        "server_name2":"server_url",
        }
    """
    mcp_servers = []
    all_skills = []
    for name in server_dict:
        url = server_dict[name]

        mcp_server = MCPServerSse(
                name=name,
                params={
                    "url": url,
                },
                client_session_timeout_seconds=60*10
            )
        await mcp_server.connect()
        mcp_servers.append(mcp_server)

        skills_info = await discover_skills(mcp_server)
        if skills_info:
            all_skills.append(f"Server {name}:\n{skills_info}")
    
    combined_skills = "\n\n".join(all_skills)
    
    code_agent = Agent(
        name="Code Agent",
        handoff_description="A helpful agent for lean code generation, code review and code bug fixer.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=code_model,
            openai_client=external_client,
            ),
        mcp_servers=mcp_servers,
    )
    if combined_skills:
        code_agent.skills = combined_skills
    print("code_agent instance created")
    return code_agent
