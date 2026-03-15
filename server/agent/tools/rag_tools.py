import subprocess
from pydantic import BaseModel, Field
from agents import function_tool
from typing import List, Optional
import os
import asyncio
import json
from ragflow_sdk import RAGFlow, DataSet

from agents import RunContextWrapper
from agents.cognition.rag import get_user_database_func, retrieve_database_func
try:
    from ..data_model import ChatContext
except (ImportError, ValueError):
    from agent.data_model import ChatContext

import logging
logger = logging.getLogger(__name__)
logger.setLevel(level = logging.INFO)


@function_tool
async def get_user_database(
    context: RunContextWrapper[ChatContext],
) -> str:
    """Get all document datasets (knowledge bases) that belong to the current user.

    The function connects to an external RAG service through the provided API key and base URL,
enumerates every dataset visible to the user, and for each dataset lists the contained
documents.

    Args: None       

    Returns:
        str:
            {
                "Execution Info": str,
                    - On success: "Success: find <N> document database for user."
                    - On failure: "Fail: do RAG database meet error: <exception details>"
                "Result": str,
                    - On success: JSON str {<dataset_id>: {
                        "dataset_name": str,
                        "dataset_id": str,
                        "dataset_description": str,
                        "document_count": int,
                        "documents": [str, ...]  # list of document names
                    }}
                    - On failure: {} (empty dict str)
            }
    """
    api_key = context.context.rag['api_key']
    base_url = context.context.rag['base_url']
    user_name = context.context.user_name
    logger.info(f'get_user_database for user: {user_name}')
    result = await get_user_database_func(api_key, base_url)
    return result

@function_tool
async def retrieve_database(
    context: RunContextWrapper[ChatContext],
    query:str="", 
    retrieve_count:int=10,
    dataset_ids:list[str]=None, document_ids:list[str]=None, 
    enable_keyword:bool=False
    ) -> str:
    """Query database and retrieve the most
    relevant text chunks using vector and/or keyword search.

    Args: 
        query: str, 
            The user question or search string.
        retrieve_count: int,
            The count of retrieve chunks. Defaults to 10.
        dataset_ids: list[str], optional
            Restrict retrieval to the given dataset IDs. If None, all accessible
            datasets are searched.
        document_ids: list[str], optional
            Restrict retrieval to the given document IDs. If None, all documents
            within the specified (or all) datasets are searched.
        enable_keyword: bool, optional
            Whether to enable keyword search in addition to vector search.
            Defaults to False (vector only).
    
    Returns:
        str:
        {
            "Execution Info": str,   # Success or failure message
            "Result": str            # JSON str, {"[ID:0]": {...}, ...}
        }
        If retrieval fails, "Execution Info"
        contains the error details.
    """
    api_key = context.context.rag['api_key']
    base_url = context.context.rag['base_url']
    result = await retrieve_database_func(api_key, base_url, query, retrieve_count, dataset_ids, document_ids, enable_keyword)
    return result
