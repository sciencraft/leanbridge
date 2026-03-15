from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
import env_setup
from agents import Agent, OpenAIChatCompletionsModel, AsyncOpenAI

from config import settings
from agent.prompts import custom_instructions

search_model, search_api_key, search_base_url = settings.search_agent_settings

try:
    from .tools.rag_tools import get_user_database, retrieve_database
    from .tools.lean_search import search_lean_packages
    load_tool_success = True
except Exception as e:
    load_tool_success = False

external_client = AsyncOpenAI(
    api_key=search_api_key,
    base_url=search_base_url,
)

import logging
logger = logging.getLogger('search_agent')
logger.setLevel(level = logging.INFO)

if load_tool_success:
    search_agent = Agent(
        name="Search Agent",
        handoff_description="A helpful agent for searching and retrieving information about lean code/knowledge resources.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=search_model,
            openai_client=external_client,
            ),
        tools=[search_lean_packages],
    )
else:
    search_agent = None

async def search_agent_generator(server_dict: dict):
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
                client_session_timeout_seconds=30*1
            )
        await mcp_server.connect()
        mcp_servers.append(mcp_server)

        skills_info = await discover_skills(mcp_server)
        if skills_info:
            all_skills.append(f"Server {name}:\n{skills_info}")
    
    combined_skills = "\n\n".join(all_skills)

    search_agent = Agent(
        name="Search Agent",
        handoff_description="A helpful agent for searching and retrieving information about lean code/knowledge resources.",
        instructions=custom_instructions,
        model=OpenAIChatCompletionsModel(
            model=search_model,
            openai_client=external_client,
            ),
        mcp_servers=mcp_servers,
    )
    if combined_skills:
        search_agent.skills = combined_skills
    print("search_agent instance created")
    return search_agent
