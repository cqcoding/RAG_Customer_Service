from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field
from typing import Optional

load_dotenv()

class Settings(BaseSettings):
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    llm_provider: str = "openrouter"  # or "openai"
    llm_model: Optional[str] = None
    model_config = ConfigDict(extra="allow")
    chroma_db_path: str = Field(default='./chroma_db')

def get_settings() -> Settings:
    return Settings()