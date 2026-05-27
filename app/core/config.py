from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str = Field(default="", description="Chave da API OpenAI.")

    llm_model: str = Field(default="gpt-4o")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    embeddings_model: str = Field(default="text-embedding-3-small")

    faiss_index_path: str = Field(default="./data/faiss_index")
    confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    pln_timeout_seconds: float = Field(default=10.0, gt=0.0)

    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db")

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
