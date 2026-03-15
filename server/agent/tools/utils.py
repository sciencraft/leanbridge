import env_setup
import yaml, os
import copy
from typing import Dict, Any
from openai import OpenAI
import logging
from config import settings

# Resolve specific agent settings
plan_model, plan_key, plan_url = settings.plan_agent_settings
code_model, code_key, code_url = settings.code_agent_settings
search_model, search_key, search_url = settings.search_agent_settings

# 1. Clients for specific agent roles
llm_clients = {
    'plan': OpenAI(api_key=plan_key, base_url=plan_url),
    'code': OpenAI(api_key=code_key or plan_key, base_url=code_url or plan_url),
    'verify': OpenAI(api_key=code_key or plan_key, base_url=code_url or plan_url),
    'search': OpenAI(api_key=search_key or plan_key, base_url=search_url or plan_url)
}

models = {
    'plan': plan_model,
    'code': code_model,
    'verify': code_model,
    'search': search_model
}

# 2. Clients for specific model names (lookup from all available models in YAML)
def _init_all_model_clients():
    clients = {}
    if settings.llm and settings.llm.models:
        for m_name, info in settings.llm.models.items():
            clients[m_name] = OpenAI(api_key=info.get('api_key'), base_url=info.get('base_url'))
    return clients

model_clients = _init_all_model_clients()

def call_llm(messages, params={}, model='plan'):
    """
    Call LLM based on either a role (plan, code, verify, search) or a specific model name.
    """
    # 1. Check if model is a recognized role
    if model in llm_clients:
        client = llm_clients[model]
        model_name = models[model]
    # 2. Check if model is a specific model name in model_clients
    elif model in model_clients:
        client = model_clients[model]
        model_name = model
    # 3. Fallback to plan
    else:
        client = llm_clients['plan']
        model_name = models['plan']
        # If it was intended as a specific model name but not found in pre-init clients,
        # we still pass it to the 'plan' client's API call as the model name parameter.
        if model not in llm_clients:
            model_name = model

    params = copy.deepcopy(params)
    params['messages'] = messages
    if 'model' not in params:
        params['model'] = model_name
        
    return client.chat.completions.create(**params)

def call_llm_with_model(messages, model, params={}):
    """Wrapper for call_llm for backward compatibility or explicit model calls."""
    return call_llm(messages, params, model=model)

def get_last_lean_code(code: str) -> str:
    """
    清理生成的Lean代码，移除markdown标记等, 获取最后一个lean代码块
    """
    # 移除markdown代码块标记
    lines = copy.deepcopy(code).strip().split('\n')
    cleaned_lines = []
    code_start = False
    code_end = False
    
    for line in lines:
        if line.strip().startswith('```lean'):
            cleaned_lines = []
            code_start = True
            code_end = False
            continue
        if code_start and not code_end and line.strip().startswith('```'):
            code_end = True
            continue
        if code_start and not code_end:
            if not 'import Mathlib' in line:
                cleaned_lines.append(line)
            else:
                print(f"Skip line: {line}")
    return '\n'.join(['import Mathlib']+cleaned_lines).strip()