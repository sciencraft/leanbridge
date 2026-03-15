from pydantic import BaseModel
from typing import List, Dict

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    message: str
    token: str
    documents: dict
    agent_names: list

class SetUserDocumentsRequest(BaseModel):
    selected: Dict[str, List[str]]
