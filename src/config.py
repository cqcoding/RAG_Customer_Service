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
    # Used both to build and to query Chroma: rebuild chroma_db after changing it.
    embedding_model: str = Field(default='BAAI/bge-base-en-v1.5')
    # Store data (CSV tables) lives in PostgreSQL. Env var: DATABASE_URL.
    # This owner account loads the data and identifies customers; the SQL
    # agent never uses it.
    database_url: str = Field(default='postgresql://rag:rag@localhost:5432/store')
    # Read-only role the SQL agent connects as (same host/port/database as
    # DATABASE_URL). Created by `python -m src.utils.create_sql_db`.
    database_reader_user: str = Field(default='store_reader')
    database_reader_password: str = Field(default='store_reader')
    # Smaller, faster model for routing; the default model writes SQL and answers.
    router_llm_model: str = Field(default='google/gemini-2.5-flash-lite')

def get_settings() -> Settings:
    return Settings()