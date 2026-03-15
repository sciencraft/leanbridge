from agents import (
    Agent,
    AsyncOpenAI, 
    OpenAIChatCompletionsModel,
)
from agent.prompts import custom_instructions, SEARCH_AGENT_AS_TOOL_DESC, VERIFY_AGENT_AS_TOOL_DESC
from agent.tools.web import search_web, fetch_web_content
from agent.tools.plan_tools import formalize_statement, create_proof_plan, check_formalized_statement

from agent.code_agent import code_agent, code_agent_generator
from agent.search_agent import search_agent, search_agent_generator
from agent.verify_agent import verify_agent, verify_agent_generator

from config import settings

plan_model, plan_api_key, plan_base_url = settings.plan_agent_settings
memory_model, memory_api_key, memory_base_url = settings.memory_agent_settings
memory_server_url = settings.memory_server_url


external_client = AsyncOpenAI(
    api_key=plan_api_key,
    base_url=plan_base_url,
)



async def lean_agents_generator(server_dict: dict) -> dict:
    """
    server_dict: { 
            "A_agent":{"server_name":"server_url"},
            "B_agent":{"server_name":"server_url"},
            "C_agent":{"server_name":"server_url"},
            }
    """

    if "search_agent" in server_dict.keys():
        search_agent_server = server_dict["search_agent"]
        if len(search_agent_server) > 0:
            searchAgent = await search_agent_generator(search_agent_server)
        else:
            assert search_agent is not None
            searchAgent = search_agent
    else:
        searchAgent = search_agent
    
    if "code_agent" in server_dict.keys():
        code_agent_server = server_dict["code_agent"]
        if len(code_agent_server) > 0:
            codeAgent = await code_agent_generator(code_agent_server)
        else:
            assert code_agent is not None
            codeAgent = code_agent
    else:
        codeAgent = code_agent

    if "verify_agent" in server_dict.keys():
        verify_agent_server = server_dict["verify_agent"]
        if len(verify_agent_server) > 0:
            verifyAgent = await verify_agent_generator(verify_agent_server)
        else:
            assert verify_agent is not None
            verifyAgent = verify_agent
    else:
        verifyAgent = verify_agent

    planAgent = Agent(
        name="Plan Agent",
        handoff_description="A plan agent that responsible for understanding the user's request, providing insights and creating a proof plan.",
        instructions=custom_instructions,
        handoffs=[
            codeAgent
        ],
        model=OpenAIChatCompletionsModel(
            model=plan_model,
            openai_client=external_client,
            ),
    )

    planAgent.tools.append(formalize_statement)
    planAgent.tools.append(check_formalized_statement)
    planAgent.tools.append(create_proof_plan)
    codeAgent.handoffs.append(planAgent)
    
    searchAgent.tools.append(search_web)
    searchAgent.tools.append(fetch_web_content)
    
    planAgent.tools.append(searchAgent.as_tool(
            tool_name="call_search_agent",
            tool_description=SEARCH_AGENT_AS_TOOL_DESC,
        ))
    codeAgent.tools.append(searchAgent.as_tool(
            tool_name="call_search_agent",
            tool_description=SEARCH_AGENT_AS_TOOL_DESC,
        ))

    lean_agents = {
        planAgent.name: planAgent, 
        searchAgent.name: searchAgent, 
        codeAgent.name: codeAgent,
    }

    print(f"Lean Agents initialized with {len(lean_agents)} agents: {', '.join(lean_agents.keys())}")

    return lean_agents

