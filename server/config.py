from pydantic_settings import (
    BaseSettings, 
    SettingsConfigDict, 
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource
)
from pydantic import Field, BaseModel, AliasChoices
from pathlib import Path
from typing import Dict, List, Optional, Type, Tuple
import os

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# Config file path priority: CONFIG_FILE env var > 'config.yaml'
config_env = os.getenv("CONFIG_FILE")
if config_env:
    CONFIG_FILE = Path(config_env).resolve()
else:
    CONFIG_FILE = BASE_DIR / "config.yaml"

class LLMModelConfig(BaseModel):
    api_key: str
    base_url: str

class LLMConfig(BaseModel):
    temperature: float = 0.6
    max_tokens: int = 18000
    nl_model: str = 'gpt-5.1'
    check_models: List[str] = ['kimi-k2-0905-preview', 'gemini-3-pro-preview', 'deepseek-chat', 'gpt-5.2']
    
    # Agent model assignments
    plan_agent: Optional[str] = Field("openai/gpt-oss-120b", validation_alias=AliasChoices("PLAN_MODEL", "PLAN_AGENT", "plan_agent"))
    code_agent: Optional[str] = Field("openai/gpt-oss-120b", validation_alias=AliasChoices("CODE_MODEL", "CODE_AGENT", "code_agent"))
    search_agent: Optional[str] = Field("openai/gpt-oss-120b", validation_alias=AliasChoices("SEARCH_MODEL", "SEARCH_AGENT", "search_agent"))
    memory_agent: Optional[str] = Field("openai/gpt-oss-120b", validation_alias=AliasChoices("MEMORY_MODEL", "MEMORY_AGENT", "memory_agent"))

    # Model lookup dictionary   
    models: Dict[str, Dict[str, str]] = {}

class LeanExploreConfig(BaseModel):
    timeout: int = 60
    truncate_output: bool = False
    max_output_length: int = 10000
    support_packages: List[str] = Field(default_factory=list)
    search_limit: int = 3

class LeanConfig(BaseModel):
    timeout: int = 300
    max_attempts: int = 3
    compile_dir: str = "E:\\Lean\\LeanBridge"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, 
        env_nested_delimiter="__", 
        extra="allow",  # Allow extra fields from env which might be picked up by children
        yaml_file=CONFIG_FILE
    )

    lean_explore: LeanExploreConfig = Field(default_factory=LeanExploreConfig)
    lean: LeanConfig = Field(default_factory=LeanConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # API Key/URL Overrides (Keep at root for easy .env override)
    plan_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("PLAN_API_KEY", "plan_api_key"))
    plan_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("PLAN_BASE_URL", "plan_base_url"))
    
    code_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("CODE_API_KEY", "code_api_key"))
    code_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("CODE_BASE_URL", "code_base_url"))
    
    memory_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("MEMORY_API_KEY", "memory_api_key"))
    memory_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("MEMORY_BASE_URL", "memory_base_url"))
    memory_server_url: Optional[str] = Field(None, validation_alias=AliasChoices("MEMORY_SERVER_URL", "memory_server_url"))
    
    search_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("SEARCH_API_KEY", "search_api_key"))
    search_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("SEARCH_BASE_URL", "search_base_url"))

    # Generic overrides for backward compatibility
    openai_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"))
    openai_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("OPENAI_BASE_URL", "openai_base_url"))
    model: Optional[str] = Field(None, validation_alias=AliasChoices("MODEL", "model"))
    
    rag_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("RAG_API_KEY", "rag_api_key"))
    rag_base_url: Optional[str] = Field(None, validation_alias=AliasChoices("RAG_BASE_URL", "rag_base_url"))
    
    leanexplore_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("LEANEXPLORE_API_KEY", "leanexplore_api_key"))
    
    jwt_secret: str = Field("your_secret_key", validation_alias=AliasChoices("JWT_SECRET", "jwt_secret"))
    port: int = Field(8000, validation_alias=AliasChoices("PORT", "port"))
    web_server_url: Optional[str] = Field(None, validation_alias=AliasChoices("WEB_SERVER_URL", "web_server_url"))

    track_name: str = Field("Lean Agents", validation_alias=AliasChoices("TRACK_NAME", "track_name"))
    track_server: Optional[str] = Field(None, validation_alias=AliasChoices("TRACK_SERVER", "track_server"))

    def get_model_info(self, model_name: str) -> Dict[str, str]:
        """Look up model info in llm.models dictionary."""
        if model_name and self.llm and self.llm.models and model_name in self.llm.models:
            return self.llm.models[model_name]
        return {}

    def fetch_model_params(self, agent_role: str, api_key_attr: str, base_url_attr: str) -> Tuple[str, str, str]:
        """
        Resolves model name, api_key, and base_url for a given role.
        Priority: Direct env var override > YAML lookup.
        """
        # Look for the model name in the nested llm config
        current_model_name = getattr(self.llm, f"{agent_role}_agent", "")
        
        env_api_key = getattr(self, api_key_attr, "")
        env_base_url = getattr(self, base_url_attr, "")

        yaml_info = self.get_model_info(current_model_name)
        
        resolved_api_key = env_api_key or yaml_info.get("api_key", "")
        resolved_base_url = env_base_url or yaml_info.get("base_url", "")

        return current_model_name, resolved_api_key, resolved_base_url

    @property
    def plan_agent_settings(self) -> Tuple[str, str, str]:
        """Returns (model, api_key, base_url) for Plan/Main agent."""
        return self.fetch_model_params("plan", "plan_api_key", "plan_base_url")

    @property
    def code_agent_settings(self) -> Tuple[str, str, str]:
        """Returns (model, api_key, base_url) for Code agent."""
        return self.fetch_model_params("code", "code_api_key", "code_base_url")

    @property
    def memory_agent_settings(self) -> Tuple[str, str, str]:
        """Returns (model, api_key, base_url) for Memory agent."""
        return self.fetch_model_params("memory", "memory_api_key", "memory_base_url")

    @property
    def search_agent_settings(self) -> Tuple[str, str, str]:
        """Returns (model, api_key, base_url) for Search agent."""
        return self.fetch_model_params("search", "search_api_key", "search_base_url")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_FILE),
            file_secret_settings,
        )

settings = Settings()

# Compatibility layer
def get_config_dict():
    return settings.model_dump()

if __name__ == "__main__":
    print(f"Loading config from: {CONFIG_FILE} (Exists: {CONFIG_FILE.exists()})")
    print(f"Plan Agent: {settings.plan_agent_settings}")
    print(f"Code Agent: {settings.code_agent_settings}")
    print(f"Memory Agent: {settings.memory_agent_settings}")
    print(f"Search Agent: {settings.search_agent_settings}")
    print(settings.model_dump_json(indent=4))