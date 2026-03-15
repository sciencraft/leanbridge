import env_setup
import os
import asyncio
import json, re
import random, string

from pydantic import BaseModel, Field
from agents import function_tool
from typing import List, Optional
from agents import RunContextWrapper

from agent.data_model import ChatContext, ToolResult, FormalizeResult, PlanResult, FormalizeCheckResult
from agent.tools.tool_prompts import FORMALIZE_AGENT_PROMPT, FORMALIZE_TASK, PLAN_AGENT_PROMPT, PLAN_TASK, REFINE_FORMALIZE_PROMPT, STATEMENT_TO_NL_PROMPT, CHECK_NL_PROMPT
from agent.tools.utils import call_llm, call_llm_with_model, get_last_lean_code
from config import settings
from agent.tools.lean_verify_mcp import LeanExecutor
from agent.tools.lean_search import search_lean_packages_func
from agent.tools.agent_context_tools import update_statement_context, get_search_context, get_statement_context, init_task_context

import logging
logger = logging.getLogger('plan_tools')
logger.setLevel(level = logging.INFO)

NL_MODEL = settings.llm.nl_model if settings.llm else ''
CHECK_MODELS = settings.llm.check_models if settings.llm else []

async def formalize_statement_func(user_statement: str,  extra_info: str = None, max_refine_times: int = 3) -> FormalizeResult:
    
    chat_messages=[
                    {"role": "system", "content": FORMALIZE_AGENT_PROMPT},
                    {"role": "user", "content": FORMALIZE_TASK.format(user_statement=user_statement, extra_info=extra_info)}
                ]

    result = FormalizeResult()
    try:
        response = call_llm(
            messages=chat_messages,
            params={'temperature':0.3, 'max_completion_tokens':3000}, 
            model='code'
            )
        if hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content
            chat_messages.append({"role": "assistant", "content": content})
            # 提取并清理 Lean 代码
            lean_code = get_last_lean_code(content)
            if lean_code:
                result = await verify_refine_formalize_func(lean_code, chat_messages)
                if result.is_success:
                    result.info = 'Statement have been formalized'
                    result.statement_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                else:
                    result.info = f'{result.info}\nFormalize statement failed.'
            else:
                result.info = 'Statement is not found in the response'
        else:
            result.info = 'No response from the LLM'
    except Exception as e:
        result.info = f'Error in generating formalize statement: {e}'
    return result

async def verify_refine_formalize_func(lean_code: str, messages: list = []) -> FormalizeResult:
    executor = LeanExecutor()
    max_attempts = executor.max_attempts
    current_code = lean_code
    prompt_template = REFINE_FORMALIZE_PROMPT
    search_pattern = r'\[SEARCH:\s*([^]]+)\]'
    refined_result = FormalizeResult()

    for attempt in range(max_attempts):
        
        # 验证当前代码
        print(f'Lean code to be verified:\n{current_code}')
        verify_result = executor.verify_lean_code(current_code)
        
        if verify_result.is_success:
            refined_result.is_success = True
            refined_result.info = verify_result.info
            refined_result.formalize_statement = current_code
            return refined_result
        else:          
            # 如果不是最后一次尝试，则尝试修正
            if attempt < max_attempts - 1:
                try:
                    # 这里需要添加LLM修正功能，目前先跳过
                    
                    prompt = prompt_template.format(original_proof=current_code, error_message=verify_result.info)
                    print(f'Refined prompt ({attempt+1}/{max_attempts}):\n{prompt}, messages length: {len(messages)}')
                    messages.append({"role": "user", "content": prompt})
                    response = call_llm(messages, 
                                        params={'temperature':0.6, 'max_completion_tokens':5000}, 
                                        model='code'
                                        )
                    refined_content = response.choices[0].message.content.strip()
                    messages.append({"role": "assistant", "content": refined_content})

                    match = re.search(search_pattern, refined_content)
                    if match:
                        search_query = match.group(1)
                        print(f'search_query: {search_query}')
                        if search_query:
                            search_result = await search_lean_packages_func(query=search_query, limit=1)
                            if search_result.is_success:
                                messages.append({"role": "user", "content": f'{search_result.search_results}\n\n请根据搜索结果，继续修复'})
                                response = call_llm(messages, 
                                            params={'temperature':0.6, 'max_completion_tokens':5000}, 
                                            model='code'
                                            )
                                refined_content = response.choices[0].message.content.strip()
                                messages.append({"role": "assistant", "content": refined_content})

                    current_code = get_last_lean_code(refined_content)
                    refined_result.formalize_statement = current_code
                    print(f"修正后的代码: {current_code}\nRefined content:\n{refined_content}")
                except Exception as e:
                    print(f"修正过程中出错: {e})")
                    break
    return refined_result

def check_formalized_statement_func(lean_statement: str, nl_statement: str, nl_model: str, check_models: list):
    """statement check"""
    check_result = FormalizeCheckResult()
    try:
        prompt = STATEMENT_TO_NL_PROMPT.format(statement = lean_statement)
        chat_messages=[
                {"role": "system", "content": "You are Lean and math expert."},
                {"role": "user", "content": prompt}
            ]
        print(f'Translate statement to natural language with model: {nl_model} ...')
        response = call_llm_with_model(chat_messages, 
                                       model=nl_model, 
                                       params={'temperature':0.6, 'max_completion_tokens':3000}
                                       )

        if hasattr(response, 'choices') and len(response.choices) > 0:
            raw_statement_nl = response.choices[0].message.content
            if raw_statement_nl and 'NL_STATEMENT:' in raw_statement_nl:
                lean_statement_nl = raw_statement_nl.split('NL_STATEMENT:')[-1].strip()
            else:
                lean_statement_nl = ''
            print(f'Raw answer len: {len(raw_statement_nl)}, Lean statement in natural language:\n{lean_statement_nl}')
            if lean_statement_nl:
                check_prompt = CHECK_NL_PROMPT.format(statement1 = nl_statement, statement2 = lean_statement_nl)
                chat_messages=[
                    {"role": "system", "content": "You are Lean and math expert."},
                    {"role": "user", "content": check_prompt}
                ]
                for model in check_models:
                    print(f'Check model: {model} ...')
                    response = call_llm_with_model(chat_messages, 
                                       model=model, 
                                       params={'temperature':0.6, 'max_completion_tokens':3000}
                                       )

                    if hasattr(response, 'choices') and len(response.choices) > 0:
                        check_res = response.choices[0].message.content
                        print(f'Check result: {check_res}')
                        if check_res and 'SAME_STATEMENT:' in check_res:
                            is_same = check_res.split('SAME_STATEMENT:')[-1].strip()
                            if is_same.lower().startswith('yes'):
                                check_result.check_opinions[model] = {'check_result': True, 'reason': None}
                            else:
                                reason = check_res.split('REASON:')[-1].strip()
                                check_result.check_opinions[model] = {'check_result': False, 'reason': reason}

                total = len(check_result.check_opinions)
                if total > 0:
                    pass_count = [v['check_result'] for v in check_result.check_opinions.values()].count(True)
                    check_result.voting_statistics = f'共{total}个模型检查，{pass_count}个模型认为formalized statement与用户原始statement一致' 
            else:
                print(f'未检测到有效的翻译结果:\n{response}')
                check_result.voting_statistics = '检查失败'
        else:
            check_result.voting_statistics = '没有response.choices， 检查失败'
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_msg = traceback.format_exc()
        info = f"Error in check statement: {error_msg}"
        print(info)
        print(f"Full traceback: {traceback_msg}")
        check_result.voting_statistics = info

    return check_result

def create_proof_plan_func(statement: str, extra_info: str = None) -> PlanResult:
    chat_messages=[
                    {"role": "system", "content": PLAN_AGENT_PROMPT},
                    {"role": "user", "content": PLAN_TASK.format(statement=statement, extra_info=extra_info)}
                ]
    result = PlanResult()
    try:
        response = call_llm(
            messages=chat_messages,
            params={'temperature':0.6, 'max_completion_tokens':2500},
            model='plan'
            )
        if hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content
            if content:
                result.is_success = True
                result.strategy = content
                result.info = 'Plan/Strategy have been generated'
            else:
                result.info = 'No plan/strategy found in the response'
        else:
            result.info = 'No response from the LLM'
    except Exception as e:
        result.info = f'Error in generating plan/strategy: {e}'
    return result


@function_tool
async def formalize_statement(context: RunContextWrapper[ChatContext], user_statement: str, search_id: str = None) -> str:
    """ Call an LLM to generate to formalize user's statement to Lean 4 code.

    Args:
        user_statement : str
            The human-readable sentence or phrase describing the theorem/lemma
            to be formalized (e.g. "there are infinitely many prime numbers").
        search_id : str, optional
            If the search agent have been called to do relative searching previously, 
            supply its returned search_id here. The corresponding definitions, 
            examples or lemmas will be appended to the prompt to improve 
            formalization quality.

    Returns:
        str: JSON-serialized ToolResult dict with keys:
            - 'Execution_Info': human-readable outcome or error description.
            - 'Result': {
                  'formalize_statement': '<Lean 4 theorem/lemma code>',
                  'statement_id': <8-char random id>  # unique identifier for later reuse
              }
            On failure only 'Execution_Info' is present, 'Result' is {}
    """
    logger.info(f'formalize_statement: user_statement: {user_statement}, search_id: {search_id}')
    result = ToolResult()
    extra_info = get_search_context(context, search_id)
    formalize_result = await formalize_statement_func(user_statement=user_statement, extra_info=extra_info)
    if formalize_result.is_success:
        result.Execution_Info = formalize_result.info 
        if not extra_info and search_id:
            result.Execution_Info += f'\nNo search results found for search_id: {search_id}'
        result.Result = {'formalize_statement': formalize_result.formalize_statement, 'statement_id': formalize_result.statement_id}
        update_statement_context(context, formalize_result.statement_id, user_statement, formalize_result.formalize_statement)
    else:
        result.Execution_Info = formalize_result.info
    return result.model_dump_json()

@function_tool
async def check_formalized_statement(context: RunContextWrapper[ChatContext], statement_id: str) -> str:
    """ Call multi-LLMs to check if the formalized statement meet with user's natural-language statement.

    Args:
        statement_id : str
            The 8-character identifier returned by `formalize_statement`.

    Returns:
        str: JSON-serialized ToolResult dict with keys:
            - 'Execution_Info': human-readable outcome or error description.
            - 'Result': {
                'check_opinions': dict # key: LLM name, value: LLM's check opinion
              }
            On failure only 'Execution_Info' is present, 'Result' is {}
    """
    logger.info(f'check_formalized_statement: statement_id: {statement_id}')
    result = ToolResult()
    statement_dict = get_statement_context(context, statement_id)
    if statement_dict:
        user_statement = statement_dict['user_statement']
        formalize_statement = statement_dict['formalize_statement']
        if 'llm_check' in statement_dict and statement_dict['llm_check']:
            llm_check = statement_dict['llm_check']
            result.Execution_Info = f"Formalized statement has been checked by LLM: {llm_check['voting_statistics']}"
            result.Result = {'check_opinions': llm_check['check_opinions']}
        else:
            llm_check = check_formalized_statement_func(
                lean_statement=formalize_statement,
                nl_statement=user_statement, 
                nl_model=NL_MODEL,
                check_models=CHECK_MODELS)
            if llm_check.check_opinions:
                result.Execution_Info = f"Formalized statement has been checked by LLM: {llm_check.voting_statistics}"
                result.Result = {'check_opinions': llm_check.check_opinions}
                update_statement_context(context, statement_id, user_statement, formalize_statement, llm_check.model_dump())
            else:
                result.Execution_Info = f'No LLM check result found for statement_id: {statement_id}, {llm_check.voting_statistics}'
    else:
        result.Execution_Info = f'No formalized statement found for statement_id: {statement_id}'

    return result.model_dump_json()

@function_tool
async def create_proof_plan(context: RunContextWrapper[ChatContext], statement_id: str, search_id: str = None) -> str:
    """ Call an LLM to draft a high-level proof strategy for a previously formalized Lean 4 statement and initialize proof task.
    Expected flow:
        1. Call formalize_statement(...) to obtain statement_id.
        2. Call create_proof_plan(statement_id, <optional-search_id>) to generate strategy.
        3. Handoff to Code Agent with task_id for actual proof construction.

    Args:
        statement_id : str
            The 8-char identifier returned by formalize_statement.  Must correspond to
            an existing formalized theorem/lemma in the current session.
        search_id : str, optional
            If earlier search results (packages, lemmas, examples) are relevant,
            supply the search_id returned by the search agent.  These snippets
            are injected into the prompt to produce a more informed plan.

    Returns:
        str: JSON-serialized ToolResult dict with keys:
            - 'Execution_Info': human-readable summary or error message.
            - 'Result': {
                  'strategy': '<step-by-step proof outline>',
                  'task_id': '<statement_id>'  # re-used as task identifier
              }
            If the statement_id is unknown, only 'Execution_Info' is returned.
    """
    logger.info(f'create_proof_plan: statement_id: {statement_id}, search_id: {search_id}')
    result = ToolResult()
    extra_info = get_search_context(context, search_id)
    statement_dict = get_statement_context(context, statement_id)
    if statement_dict:
        user_statement = statement_dict['user_statement']
        formalize_statement = statement_dict['formalize_statement']
        statement = f'User statement: {user_statement}\nLean 4 formalized statement: {formalize_statement}'
        plan_result = create_proof_plan_func( statement=statement, extra_info=extra_info)
        if plan_result.is_success:
            is_create = init_task_context(context, statement_id, plan_result.strategy, search_id)
            if is_create:
                result.Execution_Info = plan_result.info + '\nTask initialized successfully, please handoff to Code Agent to execute the proof plan.'
            else:
                result.Execution_Info = plan_result.info + '\nTask initialize failed, please check the state of task context.'
            result.Result = {'strategy': plan_result.strategy, 'task_id': statement_id}
        else:
            result.Execution_Info = plan_result.info
    else:
        result.Execution_Info = f'No statement found for statement_id: {statement_id}, please call formalize_statement first'
    return result.model_dump_json()

