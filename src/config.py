from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field
from typing import Optional

load_dotenv()

class Settings(BaseSettings):
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    llm_provider: str = "openrouter"  
    llm_model: Optional[str] = None
    model_config = ConfigDict(extra="allow")
    chroma_db_path: str = Field(default='./chroma_db')
    embedding_model: str = Field(default='BAAI/bge-base-en-v1.5')
    database_url: str = Field(default='postgresql://rag:rag@localhost:5432/store')
    database_reader_user: str = Field(default='store_reader')
    database_reader_password: str = Field(default='store_reader')
    router_llm_model: str = Field(default='google/gemini-2.5-flash-lite')

def get_settings() -> Settings:
    return Settings()