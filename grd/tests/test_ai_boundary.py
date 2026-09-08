"""Enforce the AI vs traditional split: only allow-listed modules may touch the LLM.

If you add a new module that legitimately needs the LLM, add it to AI_MODULES
*and* justify it in docs/ai-vs-traditional.md. Everything else must stay
deterministic.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "grd"

# The ONLY modules permitted to import grd.llm / receive an LLM instance.
AI_MODULES = {
    "llm/base.py", "llm/mock.py", "llm/ollama.py", "llm/__init__.py",
    "agents/research.py",            # grounded summary
    "agents/scoring.py",             # bounded (+-N) adjustment only
    "recruiting/agents/research.py",
    "recruiting/agents/scoring.py",
    "pipeline.py", "recruiting/pipeline.py",   # build + inject the LLM
    "main.py",                                  # constructs the pipelines
}

# Modules that must be provably LLM-free (the "traditional automation" half).
DETERMINISTIC_MODULES = {
    "classify.py", "metrics.py", "dashboard.py",
    "db.py", "dbtypes.py", "models.py", "config.py", "spec.py",
    "enrichment/base.py", "enrichment/capabilities.py",
    "enrichment/mock.py", "enrichment/web.py", "enrichment/__init__.py",
    "recruiting/sourcing/base.py", "recruiting/sourcing/mock.py",
    "recruiting/sourcing/github.py",
    "scoring/__init__.py", "recruiting/rubrics/__init__.py",
    "api/routes.py", "recruiting/api.py",
}

_LLM_IMPORT = re.compile(r"^\s*(from\s+grd\.llm|import\s+grd\.llm)", re.M)


def _rel_py_files() -> list[str]:
    return [
        str(p.relative_to(PKG)).replace("\\", "/")
        for p in PKG.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_only_allowlisted_modules_import_the_llm():
    offenders = []
    for rel in _rel_py_files():
        src = (PKG / rel).read_text(encoding="utf-8")
        if _LLM_IMPORT.search(src) and rel not in AI_MODULES:
            offenders.append(rel)
    assert not offenders, f"these modules import grd.llm but are not allow-listed: {offenders}"


def test_deterministic_modules_are_llm_free():
    for rel in DETERMINISTIC_MODULES:
        src = (PKG / rel).read_text(encoding="utf-8")
        assert "grd.llm" not in src, f"{rel} references grd.llm"
        assert not _LLM_IMPORT.search(src), f"{rel} imports grd.llm"


def test_classify_module_has_no_llm_or_network():
    src = (PKG / "classify.py").read_text(encoding="utf-8")
    for banned in ("grd.llm", "httpx", "requests", "openai", "ollama"):
        assert banned not in src, f"classify.py must not use {banned}"


def test_allowlist_entries_all_exist():
    for rel in AI_MODULES | DETERMINISTIC_MODULES:
        assert (PKG / rel).exists(), f"stale entry: {rel}"
