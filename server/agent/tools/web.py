import asyncio, os
from agents import function_tool
from agents.cognition.web import search_web_func, fetch_web_content_func

try:
    from ...config import settings
except (ImportError, ValueError):
    from config import settings

web_server_url = settings.web_server_url

import logging
logger = logging.getLogger(__name__)

@function_tool
async def search_web(query: str, max_results: int = 10,) -> dict:
    """
    Perform a web search through MCP service.

    This function sends a search query to the MCP server and returns the search results which ranked by relative, and give a summary of web content.

    Args:
        query: The search term or phrase to look up.
        max_results: Maximum number of results to return (default: 10).

    Returns:
        dict: A dictionary containing two keys:
            - 'Execution Info': A string indicating the success or failure of the operation.
            - 'Result': The search results dict, including: Index, Title, URL, Summary.

    Examples:
        >>> results = web_search("Python programming", 5)
    """
    logger.info(f"web search: {query}, {max_results}")
    # results = asyncio.run(search(query, max_results, WEB_SERVER_URL))
    results = await search_web_func(query, max_results, web_server_url)
    logger.info(f"finished search: {results}")
    return results

@function_tool
async def fetch_web_content(url: str,) -> dict:
    """
    Fetch the content of a web page through MCP service.

    This function retrieves the content of a specified URL.

    Args:
        url: The web page URL to fetch content from.

    Returns:
        dict: A dictionary containing two keys:
            - 'Execution Info': A string indicating the success or failure of the operation.
            - 'Result': The web fetch results dict, including: URL, Content.

    Examples:
        >>> content = web_fetch_content("https://example.com")
    """
    # results = asyncio.run(fetch_content(url, WEB_SERVER_URL))
    results = await fetch_web_content_func(url, web_server_url)
    return results

if __name__ == "__main__":
    # 示例调用
    search_results = asyncio.run(search_web_func("Python programming", max_results=3))
    print("搜索结果: ", search_results)

    content = asyncio.run(fetch_web_content_func("https://arxiv.org/"))
    print("网页内容: ", content)
