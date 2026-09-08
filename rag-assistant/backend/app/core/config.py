from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG Assistant"
    app_version: str = "0.1.0"
    debug: bool = False
    api_key: str | None = None

    database_url: str = "sqlite:///./rag_assistant.db"
    upload_dir: Path = Path("../data/uploads")
    chroma_persist_dir: Path = Path("../data/chroma_db")

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
