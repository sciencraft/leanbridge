import env_setup
from pydantic import BaseModel, Field
from agents import function_tool, RunContextWrapper
from typing import List, Optional
import os
import asyncio
import json
import random, string
import logging

from agent.data_model import ChatContext
from config import settings
logger = logging.getLogger('agent_context_tools')
logger.setLevel(level = logging.INFO)

# Max attempts for task execution
MAX_ATTEMPTS = settings.lean.max_attempts or 3

def update_statement_context(context: RunContextWrapper[ChatContext], statement_id: str, user_statement: str, formalize_statement: str, llm_check: dict = None) -> bool:
    try:
        logger.info(f'update_statement: statement_id: {statement_id}, user_statement: {user_statement}, formalize_statement: {formalize_statement}, llm_check: {llm_check}')
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context:
            agent_context['Plan Agent'] = {
                'statement':{
                    statement_id: {
                        'user_statement':user_statement,
                        'formalize_statement':formalize_statement,
                        'llm_check':llm_check
                        }
                    }
                }
        elif 'statement' not in agent_context['Plan Agent']:
            agent_context['Plan Agent']['statement'] = {
                statement_id: {
                    'user_statement':user_statement,
                    'formalize_statement':formalize_statement,
                    'llm_check':llm_check
                    }
                }
        else:
            agent_context['Plan Agent']['statement'][statement_id] = {
                'user_statement':user_statement,
                'formalize_statement':formalize_statement,
                'llm_check':llm_check
                }
    except Exception as e:
        logger.error(f'Error in updating statement: {e}')
        return False
    return True

def update_search_context(context: RunContextWrapper[ChatContext], search_id: str, info_type: str, search_results: str) -> bool:
    try:
        current_agent = context.context.current_agent
        print(f'update_search_context, current_agent: {current_agent}')
        agent_context = context.context.agent_context
        if 'Search Agent' not in agent_context:
            agent_context['Search Agent'] = {
                'search':{
                    search_id: {
                        'info_type':info_type,
                        'search_results':search_results
                        }
                    }
                }
        elif 'search' not in agent_context['Search Agent']:
            agent_context['Search Agent']['search'] = {
                search_id: {
                        'info_type':info_type,
                        'search_results':search_results
                    }
                }
        else:
            agent_context['Search Agent']['search'][search_id] = {
                'info_type':info_type,
                'search_results':search_results
            }
        
        if current_agent == 'Code Agent':
            current_task_id = agent_context['Plan Agent']['current_task']
            current_code_id = agent_context['Plan Agent']['task'][current_task_id]
            if current_code_id:
                agent_context['Plan Agent']['task'][current_task_id]['code'][current_code_id]['search_id'] = search_id
                print(f'Update search result ({search_id}) for code ({current_code_id})')
            else:
                print(f'The code id of task: {current_task_id} is None, search result ({search_id}) for code is not update')
    except Exception as e:
        return False
    return True

def update_code_context(context: RunContextWrapper[ChatContext], code_id: str, code: str, task_id: str) -> bool:
    try:
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context or 'task' not in agent_context['Plan Agent'] or task_id not in agent_context['Plan Agent']['task']:
            return False
        else:
            agent_context['Plan Agent']['task'][task_id]['code'][code_id] = {
                'code': code,
                'has_exec_verify': False,
                'pass_verify': False,
                'verify_message': '',
                'verify_advise': '',
                'search_id': ''
                }
            agent_context['Plan Agent']['task'][task_id]['current_code_id'] = code_id
    except Exception as e:
        return False
    return True

def update_verify_context(context: RunContextWrapper[ChatContext], code_id: str, verify_message: str, verify_result: bool, verify_advise: str) -> bool:
    try:
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context or 'task' not in agent_context['Plan Agent']:
            return False
        task_id = agent_context['Plan Agent']['current_task']
        task = agent_context['Plan Agent']['task'][task_id]
        if code_id != task['current_code_id']:
            return False
        else:
            task['code'][code_id]['has_exec_verify'] = True
            task['code'][code_id]['verify_message'] = verify_message
            task['code'][code_id]['pass_verify'] = verify_result
            task['code'][code_id]['verify_advise'] = verify_advise
            if verify_result:
                task['solved'] = True
    except Exception as e:
        print(f'Error in updating verify context: {e}')
        return False
    return True

def add_attempt(context: RunContextWrapper[ChatContext]) -> bool:
    try:
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context or 'task' not in agent_context['Plan Agent']:
            return False
        else:
            task_id = agent_context['Plan Agent']['current_task']
            agent_context['Plan Agent']['task'][task_id]['attempts'] += 1
            if agent_context['Plan Agent']['task'][task_id]['attempts'] > MAX_ATTEMPTS:
                return False
    except Exception as e:
        return False
    return True

def set_current_code_id(context: RunContextWrapper[ChatContext], code_id: str) -> bool:
    try:
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context or 'task' not in agent_context['Plan Agent']:
            return False
        else:
            task_id = agent_context['Plan Agent']['current_task']
            agent_context['Plan Agent']['task'][task_id]['current_code_id'] = code_id
    except Exception as e:
        print(f'Error in setting current code id: {e}')
        return False
    return True

def get_history_code_prompt(context: RunContextWrapper[ChatContext], code_id: str) -> str:
    prompt = ''
    try:
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context or 'task' not in agent_context['Plan Agent']:
            return prompt
        else:
            task_id = agent_context['Plan Agent']['current_task']
            code_ids = agent_context['Plan Agent']['task'][task_id]['code'].keys()
            for id in code_ids:
                if id != code_id:
                    code_dict = agent_context['Plan Agent']['task'][task_id]['code'][id]
                    prompt += f'code id: {id}\n{code_dict}\n' 
    except Exception as e:
        print(f'Error in get history code prompt: {e}')
    return prompt
def get_search_context(context: RunContextWrapper[ChatContext], search_id: str) -> Optional[str]:
    extra_info = None
    agent_context = context.context.agent_context
    if search_id and 'Search Agent' in agent_context:
        search_agent_context = agent_context['Search Agent']
        if 'search' in search_agent_context and search_id in search_agent_context['search']:
            extra_info = search_agent_context['search'][search_id]['search_results']
    return extra_info

def get_statement_context(context: RunContextWrapper[ChatContext], statement_id: str) -> Optional[str]:
    agent_context = context.context.agent_context
    if 'Plan Agent' in agent_context and 'statement' in agent_context['Plan Agent']:
        statement = agent_context['Plan Agent']['statement']
        if statement_id in statement:
            return statement[statement_id]
    return None

def get_current_statement(context: RunContextWrapper[ChatContext]) -> Optional[str]:
    agent_context = context.context.agent_context
    if 'Plan Agent' in agent_context and 'task' in agent_context['Plan Agent']:
        statement_id = agent_context['Plan Agent']['current_task']
        return get_statement_context(context, statement_id)
    return None

def get_main_context_inst(context: RunContextWrapper[ChatContext]) -> dict:
    agent_context = context.context.agent_context
    task_context = {}
    if 'Plan Agent' in agent_context and 'current_task' in agent_context['Plan Agent']:
        current_task_id = agent_context['Plan Agent']['current_task']
        if current_task_id:
            task = agent_context['Plan Agent']['task'][current_task_id]
            statement = get_statement_context(context, current_task_id)
            solved = task['solved']
            if 'search_id' in task:
                search_id = task['search_id']
            else:
                search_id = None
            code_ids = list(task['code'].keys())
            current_code_id = task['current_code_id']
            if current_code_id:
                has_exec_verify = task['code'][current_code_id]['has_exec_verify']
                verified = task['code'][current_code_id]['pass_verify']
            else:
                verified = False
                has_exec_verify = False
            if solved and verified:
                solved_code = {current_code_id: task['code'][current_code_id]}
            else:
                solved_code = {}
            task_context = {
                'current_task':current_task_id,
                'statement':statement,
                'task_solved':solved,
                'max_attempts':task['max_attempts'],
                'attempts':task['attempts'],
                'search_id':search_id,
                'code_ids':code_ids,
                'current_code_id':current_code_id,
                'has_exec_verify':has_exec_verify,
                'pass_verify':verified,
                'solved_code':solved_code
            }
    return task_context

def get_search_context_inst(context: RunContextWrapper[ChatContext]) -> dict:
    search_context = {'max_attempts':f'{MAX_ATTEMPTS}  # 对于同一个搜索请求，最多尝试 {MAX_ATTEMPTS} 次工具调用'}
    return search_context
    
def get_code_context_inst(context: RunContextWrapper[ChatContext]) -> dict:
    agent_context = context.context.agent_context
    code_context = {}
    if 'Plan Agent' in agent_context and 'task' in agent_context['Plan Agent']:
        task_id = agent_context['Plan Agent']['current_task']
        if task_id:
            task = agent_context['Plan Agent']['task'][task_id]
            search_id = task['search_id'] if task['search_id'] else ''
            current_code_id = task['current_code_id']
            if current_code_id:
                code = task['code'][current_code_id]['code']
                verified = task['code'][current_code_id]['pass_verify']
                has_exec_verify = task['code'][current_code_id]['has_exec_verify']
                if task['code'][current_code_id]['search_id']:
                    search_id = task['code'][current_code_id]['search_id']
            else:
                code = None
                verified = False
                has_exec_verify = False
            code_context = {
                'task_id':task_id,
                'search_id':search_id,
                'task_solved':task['solved'],
                'max_attempts':task['max_attempts'],
                'attempts':task['attempts'],
                'current_code_id':current_code_id,
                'code':code,
                'has_exec_verify':has_exec_verify,
                'pass_verify':verified
            }
    return code_context

def get_verify_context_inst(context: RunContextWrapper[ChatContext]) -> dict:
    # task_context = get_main_context_inst(context)
    # if task_context:
    #     statement = task_context['statement']
    # else:
    #     statement = None
    code_context = get_code_context_inst(context)
    if code_context:
        current_code_id = code_context['current_code_id']
        # code = code_context['code']
        verified = code_context['pass_verify']
        has_exec_verify = code_context['has_exec_verify']
    else:
        current_code_id = None
        # code = None
        verified = False
        has_exec_verify = False

    verify_context = {
                    #   'statement':statement,
                      'current_code_id':current_code_id,
                    #   'code': code,
                      'has_exec_verify':has_exec_verify,
                      'pass_verify':verified,
                      'max_attempts':f'1  # 对于同一个版本的code验证，只执行一次工具调用验证',
                      'notes': '请调用verify_lean_code工具进行真实的运行环境验证，绝对不能未经工具验证对代码做出任何判断'}
    return verify_context



def init_task_context(context: RunContextWrapper[ChatContext], statement_id: str, strategy: str, search_id: str = None) -> bool:
    try:
        logger.info(f'init_task: statement_id: {statement_id}, strategy: {strategy}, search_id: {search_id}')
        agent_context = context.context.agent_context
        if 'Plan Agent' not in agent_context:
            agent_context['Plan Agent'] = {
                'task':{
                    statement_id: {
                        'strategy':strategy,
                        'search_id':search_id,
                        'solved':False,
                        'max_attempts':MAX_ATTEMPTS,
                        'attempts':0,
                        'code':{},
                        'current_code_id':None
                        }
                    },
                'current_task':statement_id
                }
        elif 'task' not in agent_context['Plan Agent']:
            agent_context['Plan Agent']['task'] = {
                statement_id: {
                    'strategy':strategy,
                    'search_id':search_id,
                    'solved':False,
                    'max_attempts':MAX_ATTEMPTS,
                    'attempts':0,
                    'code':{},
                    'current_code_id':None
                    }
                }
            agent_context['Plan Agent']['current_task'] = statement_id
        else:
            agent_context['Plan Agent']['task'][statement_id] = {
                'strategy':strategy,
                'search_id':search_id,
                'solved':False,
                'max_attempts':MAX_ATTEMPTS,
                'attempts':0,
                'code':{},
                'current_code_id':None
            }
            agent_context['Plan Agent']['current_task'] = statement_id
        # is_code_ready = init_code_task_context(context, statement_id, search_id)
        # assert is_code_ready, 'Error in initializing code task context'
    except Exception as e:
        logger.error(f'Error in initializing task: {e}')
        return False
    return True

# def init_code_task_context(context: RunContextWrapper[ChatContext], statement_id: str, search_id: str = None) -> bool:
#     try:
#         logger.info(f'init_code_task_context: statement_id: {statement_id}, search_id: {search_id}')
#         agent_context = context.context.agent_context
#         if 'Code Agent' not in agent_context:
#             agent_context['Code Agent'] = {
#                 'task_id':statement_id,
#                 'search_id':search_id,
#                 'solved':False,
#                 'max_attempts':MAX_ATTEMPTS,
#                 'attempts':0,
#                 'verified':False,
#                 'verified_message':'',
#                 'verify_advise': '',
#                 'current_code_id':'', 
#                 'code':{}
#                 }
#         else:
#             agent_context['Code Agent']['task_id'] = statement_id
#             agent_context['Code Agent']['search_id'] = search_id
#             agent_context['Code Agent']['solved'] = False
#             agent_context['Code Agent']['verified'] = False
#             agent_context['Code Agent']['verified_message'] = ''
#             agent_context['Code Agent']['verify_advise'] = ''
#             agent_context['Code Agent']['current_code_id'] = ''
#             agent_context['Code Agent']['max_attempts'] = MAX_ATTEMPTS
#             agent_context['Code Agent']['attempts'] = 0
#     except Exception as e:
#         logger.error(f'Error in initializing code task: {e}')
#         return False
#     return True