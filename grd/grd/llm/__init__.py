from __future__ import annotations

from grd.config import Settings
from grd.llm.base import LLM
from grd.llm.mock import MockLLM
from grd.llm.ollama import OllamaLLM


def build_llm(settings: Settings) -> LLM:
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return MockLLM()
    if provider == "ollama":
        return OllamaLLM(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.http_timeout,
        )
    raise ValueError(f"Unknown GRD_LLM_PROVIDER: {settings.llm_provider!r}")


__all__ = ["LLM", "MockLLM", "OllamaLLM", "build_llm"]
