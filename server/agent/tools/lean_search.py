import env_setup
import asyncio
import sys
from typing import List, Dict, Any, Optional
import os, json
import yaml
import random, string
import logging

from agent.data_model import ChatContext, ToolResult, LeanSearchResult
from config import settings
from agents import function_tool, RunContextWrapper
from agent.tools.agent_context_tools import update_search_context

from lean_explore.api import ApiClient as LeanExploreAPIClient


class LeanExploreClient:
    """直接的 LeanExplore API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        # 优先级: 传入参数 > Settings (环境变量/YAML)
        self.api_key = api_key or settings.leanexplore_api_key
        
        if not self.api_key:
            raise ValueError("LeanExplore API key 未找到。请在 .env 文件或参数中提供 LEANEXPLORE_API_KEY。")
        
        # 配置选项
        self.truncate_output = settings.lean_explore.truncate_output
        self.max_output_length = settings.lean_explore.max_output_length
        
        # 初始化客户端
        self.client = LeanExploreAPIClient(api_key=self.api_key, timeout=settings.lean_explore.timeout)
    
        
    def _get_lean_file_env(self, file_path: str) -> str:
        """获取Lean文件的环境"""
        compile_dir = settings.lean.compile_dir
        if os.path.exists(compile_dir):
            if "PhysLean" in file_path:
                lean_file = os.path.join(compile_dir, ".lake/packages/PhysLean", file_path)
            elif "Mathlib" in file_path:
                lean_file = os.path.join(compile_dir, ".lake/packages/mathlib", file_path)
            else:
                lean_file = os.path.join(compile_dir, f".lake/packages/{file_path.split('/')[0]}", file_path)
            if os.path.exists(lean_file):
                with open(lean_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    envs = []
                    for line in lines:
                        if 'import' in line and 'Mathlib' in line:
                            if 'import Mathlib' not in envs:
                                envs.append('import Mathlib')
                        if 'import' in line and 'PhysLean' in line:
                            if 'import PhysLean' not in envs:
                                envs.append('import PhysLean')
                        if line.strip().startswith(('open', 'namespace', 'variable')) and line.strip() not in envs:
                            envs.append(line.strip())
                    return '\n'.join(envs)
            return ''
        return ''
    
    async def search(self, query: str, limit: int = 10, packages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        搜索数学知识和定理
        
        Args:
            query: 搜索查询字符串
            limit: 返回结果数量限制
            packages: 包过滤器列表
        
        Returns:
            搜索结果列表
        """
        try:
            response = await self.client.search(
                query=query,
                limit=limit,
                packages=packages
            )
            
            # 转换为我们期望的格式
            results = []
            for i, item in enumerate(response.results):
                if i >= limit:
                    break
                
                # 确保完整输出，不截断长代码
                statement_text = item.source_text or ''
                docstring_text = item.docstring or ''
                description_text = item.informalization or docstring_text or 'No description'
                
                # 如果配置了截断，才进行截断处理
                if self.truncate_output:
                    if len(statement_text) > self.max_output_length:
                        statement_text = statement_text[:self.max_output_length] + "... [输出被截断]"
                    if len(description_text) > self.max_output_length:
                        description_text = description_text[:self.max_output_length] + "... [输出被截断]"
                    if len(docstring_text) > self.max_output_length:
                        docstring_text = docstring_text[:self.max_output_length] + "... [输出被截断]"
                
                result = {
                    'id': item.id,
                    'title': item.name,
                    # 'type': 'theorem',  # 默认类型
                    'description': description_text,
                    'lean_code': statement_text,
                    'module': item.module,
                    'source_link': item.source_link,
                    'docstring': docstring_text,
                    'code_truncated': True if len(statement_text) > self.max_output_length else False,
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            raise RuntimeError(f"搜索失败: {e}")
    
    async def get_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取详细信息
        
        Args:
            item_id: 项目ID
        
        Returns:
            项目详细信息
        """
        try:
            item = await self.client.get_by_id(item_id)
            if not item:
                return None
            
            # 确保完整输出，不截断长代码
            statement_text = item.source_text or ''
            docstring_text = item.docstring or ''
            description_text = item.informalization or docstring_text or 'No description'
            
            # 如果配置了截断，才进行截断处理
            if self.truncate_output:
                if len(statement_text) > self.max_output_length:
                    statement_text = statement_text[:self.max_output_length] + "... [输出被截断]"
                if len(docstring_text) > self.max_output_length:
                    docstring_text = docstring_text[:self.max_output_length] + "... [输出被截断]"
                if len(description_text) > self.max_output_length:
                    description_text = description_text[:self.max_output_length] + "... [输出被截断]"
            
            return {
                'id': item.id,
                'name': item.primary_declaration.lean_name if item.primary_declaration else 'N/A',
                'statement': statement_text,
                'docstring': docstring_text,
                'informal_description': description_text,
                'module': item.module,
                'source_link': item.source_link,
                'full_content': True  # 标记这是完整内容，未被截断
            }
            
        except Exception as e:
            raise RuntimeError(f"获取详情失败: {e}")


async def search_lean_packages_func(query: str, limit: int = 3) -> LeanSearchResult:
        """
        搜索 Lean 包

        Args:
            query: 搜索查询字符串
            limit: 返回结果数量限制

        Returns:
            搜索结果列表
        """
        final_result = LeanSearchResult()
        try:
            client = LeanExploreClient()
            limit = min(limit, settings.lean_explore.search_limit)  
            
            # Use configured support_packages as default filter
            packages = settings.lean_explore.support_packages if settings.lean_explore.support_packages else None
            
            results = await client.search(
                query=query, limit=limit, packages=packages
            )
            if len(results) > limit:
                results = results[:limit]
            # for result in results:
            #     if result['lean_code']:
            #         # lean_file_env = result['module']
            #         lean_file_env = client._get_lean_file_env(result['module'])
            #         result['lean_code'] = f"```lean\n{lean_file_env}\n\n{result['lean_code']}\n```"
            if results:
                final_result.is_success = True
                final_result.search_results = json.dumps(results)
                final_result.info = f'Success: find {len(results)} items'
                final_result.search_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            else:
                final_result.info = 'No results found'
        except Exception as e:
            final_result.info = f'Fail: {e}'
        return final_result


@function_tool
async def search_lean_packages(context: RunContextWrapper[ChatContext], query: str, limit: int = 2, is_proof: bool = False) -> Dict[str, str]:
    """
    Search Lean packages (Lean 4 declarations, lemmas, definitions, etc.).

    Args:
        query : str
            Keywords, either in natural language or Lean syntax fragments.
        limit : int, default 2 (no more than 3)
            Maximum number of results to return.
        is_proof : bool, default False
            Whether the search is intended for proving a proposition.

    Returns:
        str: JSON-serialized ToolResult dict with keys:
            - 'Execution Info': execution status description (success / failure reason).
            - 'Result': JSON string; in general Q&A mode, returns the searched Lean entries
            (giving the main information relevant to the user's question); in proof mode,
            returns only the search_id, with the information stored in agent content for
            later use.
    """
    result = ToolResult()
    search_results = await search_lean_packages_func(query=query, limit=limit)
    result.Execution_Info = search_results.info
    if is_proof:
        if search_results.is_success:
            is_update = update_search_context(context, search_results.search_id, 'lean package', search_results.search_results)
            if is_update:
                result.Execution_Info = search_results.info + ' and update search results to agent context success'
                result.Result = {'search_id': search_results.search_id}
            else:
                result.Execution_Info = 'Fail: update search results to agent context failed'
    else:
        if search_results.is_success:
            result.Result = {'search_results': search_results.search_results}
    return result.model_dump_json()

if __name__ == '__main__':
    results = asyncio.run(search_lean_packages_func(query="wick theorem"))
    print(results)