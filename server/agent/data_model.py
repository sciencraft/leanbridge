from pydantic import BaseModel


class ChatContext(BaseModel):
    user_name: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    last_agent: str | None = None
    current_agent: str | None = None
    with_cognition: bool = False
    workdir: str | None = None
    sandbox: str | None = None
    mcp_servers: dict = {}
    rag: dict = {}
    user_resource: dict = {}
    agent_context: dict = {}


class ToolResult(BaseModel):
    Execution_Info: str = ''
    Result: str | dict = {}

class CodeGenResult(BaseModel):
    is_success: bool = False
    info: str = ''
    code: str = ''
    code_id: str = ''

class FormalizeResult(BaseModel):
    is_success: bool = False
    info: str = ''
    formalize_statement: str = ''
    statement_id: str = ''

class FormalizeCheckResult(BaseModel):
    check_opinions: dict = {}
    voting_statistics: str = ''

class PlanResult(BaseModel):
    is_success: bool = False
    info: str = ''
    strategy: str = ''

class LeanSearchResult(BaseModel):
    is_success: bool = False
    info: str = ''
    search_results: str = ''
    search_id: str = ''