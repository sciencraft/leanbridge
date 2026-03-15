import os, math, json, asyncio
import re, glob
import subprocess
import tempfile
import shlex
from pydantic import BaseModel
from datetime import datetime

from typing import Dict, List, Optional, Tuple
import anyio
from fastmcp import FastMCP, Context
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import logging
from agents import RunContextWrapper

import env_setup
from agent.data_model import ChatContext, ToolResult
from config import settings
from agent.tools.agent_context_tools import get_current_statement
from agent.tools.utils import call_llm
from agent.tools.tool_prompts import REVIEW_AGENT_PROMPT, REVIEW_TASK

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelno)s | %(message)s")

custom_middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    ),
]

mcp = FastMCP(
        name="LeanVerifyTools",
        log_level="INFO",        
    )
# mcp.add_middleware(
#     custom_middleware
# )

http_app = mcp.http_app(middleware=custom_middleware, transport="sse")



class VerifyResult(BaseModel):
    is_success: bool = False
    info: str = ''
    advise: str = ''


class LeanExecutor:
    def __init__(self, config: dict = None):
        if config:
            self.timeout = config.get('lean', {}).get('timeout', settings.lean.timeout)
            self.max_attempts = config.get('lean', {}).get('max_attempts', settings.lean.max_attempts)
            self.compile_dir = config.get('lean', {}).get('compile_dir', settings.lean.compile_dir)
        else:
            self.timeout = settings.lean.timeout
            self.max_attempts = settings.lean.max_attempts
            self.compile_dir = settings.lean.compile_dir
        
    def check_lean_installation(self) -> bool:
        """
        检查Lean4是否正确安装
        """
        try:
            result = subprocess.run(['lean', '--version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def verify_advise(self, statement: str,  lean_code: str,  error_messages: str ) -> str:
    
        chat_messages=[
                        {"role": "system", "content": REVIEW_AGENT_PROMPT},
                        {"role": "user", "content": REVIEW_TASK.format(statement=statement, lean_code=lean_code, error_message=error_messages)},
                    ]

        advise = ''
        try:
            response = call_llm(
                messages=chat_messages,
                params={'temperature':0.6, 'max_completion_tokens':1000}, 
                model='code'
                )
            if hasattr(response, 'choices') and len(response.choices) > 0:
                advise = response.choices[0].message.content
        except Exception as e:
            print(f'Error in generating verify advise: {e}')
        return advise

    def verify_lean_code(self, lean_code: str, statement:str = None, ctx: Context = None) -> VerifyResult:
        """
        验证Lean4证明代码
        返回: (是否成功, 输出信息或错误信息)
        """
        # if not self.check_lean_installation():
        #     return False, "错误: Lean4未安装或无法访问。请先安装Lean4。"
        
        if not os.path.exists(self.compile_dir):
            return False, f"错误: 编译目录 {self.compile_dir} 不存在。请检查配置。"
        
        original_cwd = os.getcwd()
        
        # 确保编译目录存在
        lean_bridge_dir = os.path.join(self.compile_dir, 'LeanBridge')
        os.makedirs(lean_bridge_dir, exist_ok=True)

        verify_result = VerifyResult()
        
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.lean', 
                delete=False, 
                encoding='utf-8',
                dir=lean_bridge_dir
            ) as f:
                f.write(lean_code)
                temp_file = f.name
                temp_filename = os.path.basename(temp_file)
            
            # 切换到编译目录
            os.chdir(self.compile_dir)
            
            # 运行lean检查
            print(f'Running lean check for {temp_filename}')
            result = subprocess.run(
                ['lake', 'env', 'lean', f'LeanBridge/{temp_filename}'],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8'
            )
            print(lean_bridge_dir, result)
            
            if result.returncode == 0:
                verify_result.is_success = True
                verify_result.info = f"验证成功！stdout: {result.stdout}"
            else:
                error_msg = result.stderr or result.stdout
                # verify_result.info = f"证明验证失败:\n{error_msg}"
                verify_result.info = f"验证失败:\n{error_msg}"
                if statement:
                    verify_result.advise = self.verify_advise(statement, lean_code, error_msg)
        except subprocess.TimeoutExpired:
            verify_result.info = f"验证超时（超过{self.timeout}秒）"
        except Exception as e:
            verify_result.info = f"验证过程中发生错误: {str(e)}"
        finally:
            # 切换回原始目录
            try:
                os.chdir(original_cwd)
            except:
                pass
            
            # 清理临时文件
            try:
                if 'temp_file' in locals():
                    os.unlink(temp_file)
            except:
                pass

        return verify_result
    
    def create_lean_project(self, project_name: str) -> bool:
        """
        创建新的Lean4项目
        """
        try:
            result = subprocess.run(
                ['lake', 'new', project_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def build_lean_project(self, project_path: str) -> Tuple[bool, str]:
        """
        构建Lean4项目
        """
        try:
            result = subprocess.run(
                ['lake', 'build'],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                return True, "项目构建成功"
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "项目构建超时"
        except Exception as e:
            return False, f"构建过程中发生错误: {str(e)}"
    

@mcp.tool()
async def verify_lean_code_mcp(
    code_id: str,
    ctx: Context,
    agent_context: dict = {}
) -> Dict[str, str]:
    """
    验证一段 Lean4 证明代码是否可通过编译。
    该工具会调用 Lean4 的编译器进行验证，并返回验证结果。

    Args:
        code_id (str): 需验证的Lean4 代码的唯一标识符。
        agent_context (dict): MCP 框架自动注入的agent上下文(内含需验证的lean code)，无需填写。

    Returns:
        dict: 固定两个字段：
            - 'Execution Info': 编译信息。
            - 'Result': 是否通过编译。
    """
    task_id = None
    if 'agent_context' in agent_context.keys():
        agent_context = agent_context['agent_context']
    if 'Plan Agent' in agent_context.keys() and 'task' in agent_context['Plan Agent'].keys():
        task_id = agent_context['Plan Agent']['current_task']
    else:
        return {
            "Execution Info": f"当前任务不存在，请检查。",
            "Result": "False"
        }
    if code_id in agent_context['Plan Agent']['task'][task_id]['code'].keys():
        lean_code = agent_context['Plan Agent']['task'][task_id]['code'][code_id]
    else:
        return {
            "Execution Info": f"code: {code_id} 不存在，请检查。",
            "Result": "False"
        }
    # 实例化执行器（复用全局配置）
    executor = LeanExecutor()

    # 真正调用核心逻辑
    statement = None
    verify_result: VerifyResult = executor.verify_lean_code(lean_code, statement, ctx=ctx)

    # 统一包装成 MCP 需要的格式
    return {
        "Execution Info": verify_result.info,
        "Result": str(verify_result.is_success)
    }


# @function_tool
async def verify_lean_code(context: RunContextWrapper[ChatContext], code_id: str) -> str:
    """
    验证一段 Lean4 证明代码是否可通过编译。
    该工具会调用 Lean4 的编译器进行验证，并返回验证结果。

    Args:
        code_id (str): 需验证的Lean4 代码的唯一标识符。

    Returns:
        dict: 固定两个字段：
            - 'Execution Info': 编译信息。
            - 'Result': 是否通过编译。
    """
    agent_context = context.context.agent_context
    lean_code = None
    task_id = None
    result = ToolResult()
    print(f'verify_lean_code: {code_id}')
    if 'Plan Agent' in agent_context.keys() and 'task' in agent_context['Plan Agent'].keys() and agent_context['Plan Agent']['current_task']:
        task_id = agent_context['Plan Agent']['current_task']
    else:
        result.Execution_Info = f"当前任务不存在，请检查。"
        return result.model_dump_json()

    if code_id in agent_context['Plan Agent']['task'][task_id]['code'].keys():
        lean_code = agent_context['Plan Agent']['task'][task_id]['code'][code_id]['code']
    else:
        result.Execution_Info = f"code: {code_id} 不存在，请检查。"
        return result.model_dump_json()
    if lean_code is None:
        result.Execution_Info = f"code: {code_id} 为空代码，请检查。"
        return result.model_dump_json()

    # 实例化执行器（复用全局配置）
    executor = LeanExecutor()

    # 真正调用核心逻辑
    statement = get_current_statement(context)
    verify_result: VerifyResult = executor.verify_lean_code(lean_code, statement)
    print(verify_result)
    is_update = update_verify_context(context, code_id, verify_result.info, verify_result.is_success, verify_result.advise)
    if is_update:
        result.Execution_Info = verify_result.info
        result.Result = str(verify_result.is_success)
    else:
        result.Execution_Info = "验证结果未更新，请检查。"
    return result.model_dump_json()


async def test():
    lean_code = """
-- Test.lean
theorem add_comm_two_two : 2 + 2 = 4 := by
  rfl

theorem id_works (x : Nat) : id x = x := by
  simp [id]
    """
    
    executor = LeanExecutor()
    # 真正调用核心逻辑
    verify_result: VerifyResult = executor.verify_lean_code(lean_code)
    print(verify_result)

if __name__ == '__main__':
    asyncio.run(test())
    # uvicorn.run(http_app, host="0.0.0.0", port=3333)

    
