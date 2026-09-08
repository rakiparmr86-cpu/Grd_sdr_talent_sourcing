from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GRD AI SDR"
    debug: bool = False

    database_url: str = "sqlite:///./grd.db"

    # comma separated: mock, web
    enrichment_providers: str = "mock,web"

    # mock | ollama
    llm_provider: str = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # which agents/<name>/ config folder to load
    agent: str = "ai_sdr"

    icp: str = "grd_staffing"
    http_timeout: float = 10.0

    # research agent: which capabilities it is allowed to call, and staleness cutoff
    research_capabilities: str = (
        "company_lookup,contact_lookup,funding_lookup,tech_lookup,news_search,web_fetch"
    )
    research_stale_after_months: int = 24
    research_retries: int = 1

    # --- recruiting / talent sourcing vertical ---
    # comma separated: mock, github
    candidate_sources: str = "mock,github"
    github_token: str | None = None
    rubric: str = "backend_engineer_india"

    @property
    def provider_list(self) -> list[str]:
        return [p.strip().lower() for p in self.enrichment_providers.split(",") if p.strip()]

    @property
    def research_capability_list(self) -> list[str]:
        return [c.strip().lower() for c in self.research_capabilities.split(",") if c.strip()]

    @property
    def candidate_source_list(self) -> list[str]:
        return [p.strip().lower() for p in self.candidate_sources.split(",") if p.strip()]

    @property
    def agents_dir(self) -> Path:
        return REPO_ROOT / "agents"

    @property
    def icp_dir(self) -> Path:
        # ICP library now lives inside the agent config folder
        return self.agents_dir / self.agent / "scoring" / "icp"

    @property
    def rubric_dir(self) -> Path:
        return PACKAGE_DIR / "recruiting" / "rubrics"


@lru_cache
def get_settings() -> Settings:
    return Settings()
