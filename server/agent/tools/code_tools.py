import env_setup
import subprocess
from pydantic import BaseModel, Field
from agents import function_tool
from typing import List, Optional
import os
import asyncio
import json
import random, string

from agents import RunContextWrapper
from agent.data_model import ChatContext, ToolResult, CodeGenResult
from agent.tools.tool_prompts import GEN_FIRST_CODE, REFINE_CODE, CODE_POLICY, LEAN_CODE_AGENT_PROMPT
from agent.tools.utils import call_llm, get_last_lean_code
from agent.tools.agent_context_tools import get_search_context, get_statement_context, update_code_context, set_current_code_id, add_attempt, get_history_code_prompt
from agent.tools.lean_verify_mcp import verify_lean_code

import logging
logger = logging.getLogger('codeagent.tools')
logger.setLevel(level = logging.INFO)


def lean_code_generator_func(task: str,  base_code: str = None, is_refine: bool = False, extra_info: str = None, strategy: str = None, error_message: str = None, verify_advise: str = None, history: str = None) -> CodeGenResult:
    if is_refine:
        # prompt = REFINE_CODE.format(task=task, lean_code=base_code, error_message=error_message, extra_info=extra_info, strategy=strategy, verify_advise=verify_advise)
        prompt = REFINE_CODE.format(task=task, lean_code=base_code, error_message=error_message, verify_advise=verify_advise, history=history)
    else:
        prompt = GEN_FIRST_CODE.format(task=task, extra_info=extra_info, strategy=strategy)
    chat_messages=[
                    {"role": "system", "content": LEAN_CODE_AGENT_PROMPT + CODE_POLICY},
                    {"role": "user", "content": prompt}
                ]
    result = CodeGenResult()
    try:
        response = call_llm(
            messages=chat_messages,
            params={'temperature':0.6, 'max_completion_tokens':4000}, 
            model='code'
            )
        if hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content
            chat_messages.append({"role": "assistant", "content": content})
            # 提取并清理 Lean 代码
            lean_code = get_last_lean_code(content)
            if lean_code:
                result.is_success = True
                result.code = lean_code
                result.info = 'Lean code have been refined, please call call_verify_agent to check the code' if is_refine else 'Lean code have been generated (first version), please call call_verify_agent to check the code'
                result.code_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            else:
                result.info = 'Lean code is not found in the response'
        else:
            result.info = 'No response from the LLM'
    except Exception as e:
        result.info = f'Error in generating code: {e}'
    return result

@function_tool
async def lean_code_generator(context: RunContextWrapper[ChatContext], task_id: str, code_id: str = None,  is_refine: bool = False) -> str:
    """ Call an LLM to generate or refine Lean 4 code for a proof task and code will be executed in local lean environment.
    Examples:
        # first generation
        lean_code_generator(task_id)
        # refine based on error messages
        lean_code_generator(task_id='sed34dw2', code_id='a1B2c3D4', is_refine=True)

    Args:
        task_id: str, identifies the task to be solved.
        code_id : str, optional
            Required when is_refine=True. Identifies the code version to be improved
            (usually the latest one). Ignored when is_refine=False (code has not been generated yet).
        is_refine : bool, default False
            - False → generate the first version from task / extra_info / strategy.
            - True  → refine an existing version using its base_code, error_message and hits.

    Returns:
        str: JSON-serialized ToolResult dict with keys:
            - 'Execution_Info': human-readable outcome or error description.
            - 'Result': {"code_id": <8-char random id>, "passed_verification": <bool>, "verification_info": <str info about lean code verification in local lean executor>}  # id of the new created/refined code, present only on success, and the verification status of this code.
    """
    # logger.info(f'lean_code_generator: task_id: {task_id}, code_id: {code_id}, is_refine: {is_refine}')
    result = ToolResult()
    task_context = {}
    task = None
    extra_info = None
    strategy = None
    verify_advise = None
    agent_context = context.context.agent_context

    if 'Plan Agent' in agent_context and 'task' in agent_context['Plan Agent']:
        if agent_context['Plan Agent']['current_task'] != task_id:
            result.Execution_Info = f'Current task_id: {agent_context['Plan Agent']['current_task']} is not equal to the task_id passed in: {task_id}, please handoff to Plan Agent and create a new task!'
            return result.model_dump_json()
        task_context = agent_context['Plan Agent']['task'][task_id]
    else:
        result.Execution_Info = 'Code Agent task context is empty, please handoff to Plan Agent and create a new task!'
        return result.model_dump_json()
    
    if task_context['attempts'] >= task_context['max_attempts']:
        result.Execution_Info = f'Code Agent has reached the maximum attempts: {task_context["max_attempts"]}, please handoff to Plan Agent and create a new task!'
        return result.model_dump_json()
    search_id = task_context['search_id'] if task_context['search_id'] else ''
    if is_refine and ('code' in task_context and code_id == task_context['current_code_id']):
        search_id = task_context['code'][code_id]['search_id']
    if search_id:
        extra_info = get_search_context(context, search_id)
    statement_dict = get_statement_context(context, task_id)

    if statement_dict:
        user_statement = statement_dict['user_statement']
        formalize_statement = statement_dict['formalize_statement']
        task = f'User statement: {user_statement}\nLean 4 formalized statement: {formalize_statement}'
    else:
        result.Execution_Info = f'No statement found for task_id: {task_id}, please handoff to Plan Agent and create a new task!'
        return result.model_dump_json()
    
    if 'strategy' in task_context:
        strategy = task_context['strategy']
    if not is_refine:
        code_result = lean_code_generator_func(task=task, extra_info=extra_info, strategy=strategy)
    else:
        if 'code' in task_context and code_id == task_context['current_code_id']:
            if task_context['code'][code_id]['pass_verify']:
                result.Execution_Info = f'Code_id: {code_id} has been verified, please handoff to Plan Agent and give a proof summary!'
                return result.model_dump_json()
            history = get_history_code_prompt(context, code_id)
            base_code = task_context['code'][code_id]['code']
            error_message = task_context['code'][code_id]['verify_message']  
            verify_advise = task_context['code'][code_id]['verify_advise']
            code_result = lean_code_generator_func(
                task=task, 
                base_code=base_code, 
                is_refine=is_refine, 
                error_message=error_message, 
                extra_info=extra_info, 
                strategy=strategy,
                verify_advise=verify_advise,
                history=history
                )
        else:
            result.Execution_Info = f'No code have generated for code_id: {code_id}, please set is_refine to False'
            return result.model_dump_json()
        
    if code_result.is_success:
        code_id = code_result.code_id
        is_update = update_code_context(context, code=code_result.code, code_id=code_id, task_id=task_id)
        print(code_result.code)
        res_dict = {'code_id': code_id}
        if not is_update:
            result.Execution_Info = f'Failed to update code context for code_id: {code_id}'
            return result.model_dump_json()
        else:
            raw_verify_result = await verify_lean_code(context, code_id)
            verify_result = ToolResult(**json.loads(raw_verify_result))
            if verify_result.Result.lower() == 'true':
                code_result.info = 'Lean code have been refined and verified' if is_refine else 'Lean code have been generated (first version), and verified'
                res_dict['passed_verification'] = True
            else:
                code_result.info = 'Lean code have been refined, but it does not pass the verification' if is_refine else 'Lean code have been generated (first version), but it does not pass the verification'
                res_dict['passed_verification'] = False
            res_dict['verification_info'] = verify_result.Execution_Info

        result.Execution_Info = code_result.info
        result.Result = res_dict
    else:
        result.Execution_Info = code_result.info
    
    add_attempt(context)
    return result.model_dump_json()

@function_tool
def set_current_code_id(code_id: str) -> str:
    """
    Designate a specific code version as the current working copy for downstream work.

    Args:
        code_id : str
            The 8-character identifier of the code version that should become active.
            Typically obtained from a previous call to lean_code_generator.

    Returns:
        str : JSON-serialized ToolResult with:
            - 'Execution_Info': success or failure message.
            - 'Result': {'code_id': '<the-id-that-was-set>'} on success, {} on failure.
    """
    result = ToolResult()
    is_set = set_current_code_id(code_id)
    if is_set:
        result.Execution_Info = f'Successfully set current code id: {code_id}'
        result.Result = {'code_id': code_id}
    else:
        result.Execution_Info = f'Failed to set current code id: {code_id}'
    return result.model_dump_json()


    
