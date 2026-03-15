import asyncio
from typing import Any, AsyncIterator

def ensure_string(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "input_text":
                text += item.get("text", "")
            elif isinstance(item, str):
                text += item
            else:
                text += str(item)
        return text
    return str(content)

async def merge_async_generators(*gens):
    queue: asyncio.Queue = asyncio.Queue()

    async def _feed(gen: AsyncIterator):
        try:
            async for item in gen:
                await queue.put(item)
        except Exception as e:
            await queue.put(e)
        finally:
            await queue.put(None)

    tasks = [asyncio.create_task(_feed(g)) for g in gens]
    finished = 0
    while finished < len(tasks):
        item = await queue.get()
        if item is None:
            finished += 1
            continue
        yield item

    for t in tasks:
        t.cancel()

def build_agent_state(cognition, agent_name, agent_settings, empty_mental_state, agent_context):
    if cognition:
        snapshot={
                    "mental_state": cognition.mental_state.model_dump(),
                    "agent_name":agent_name,
                    "settings": agent_settings,
                    "agent_context": agent_context
                }
    else:
        snapshot={
                    "mental_state": empty_mental_state,
                    "agent_name": agent_name,
                    "settings": agent_settings,
                    "agent_context": agent_context
                }
    return snapshot

async def discover_skills(mcp_server: Any) -> str:
    """Check for list_skills tool and retrieve available skills."""
    from agents.logger import logger
    try:
        tools = await mcp_server.list_tools()
        if any(t.name == "list_skills" for t in tools):
            result = await mcp_server.call_tool("list_skills", {})
            # Format skills list from result
            if hasattr(result, 'content'):
                return "\n".join([item.text for item in result.content if item.type == 'text'])
            return str(result)
    except Exception as e:
        logger.warning(f"Failed to discover skills for {mcp_server.name}: {e}")
    return ""
