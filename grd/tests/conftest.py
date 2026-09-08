from __future__ import annotations

from pathlib import Path

import pytest

from grd.config import Settings

_ROOT = Path(__file__).resolve().parents[1]
ICP_DIR = _ROOT / "agents" / "ai_sdr" / "scoring" / "icp"
RUBRIC_DIR = _ROOT / "grd" / "recruiting" / "rubrics"
AGENTS_DIR = _ROOT / "agents"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",           # in-memory, StaticPool
        enrichment_providers="mock",        # no network in tests
        candidate_sources="mock",
        llm_provider="mock",
        agent="ai_sdr",
        icp="grd_staffing",
        rubric="backend_engineer_india",
    )


@pytest.fixture
def icp() -> dict:
    from grd.scoring import load_icp

    return load_icp("grd_staffing", ICP_DIR)


@pytest.fixture
def rubric() -> dict:
    from grd.recruiting.rubrics import load_rubric

    return load_rubric("backend_engineer_india", RUBRIC_DIR)


@pytest.fixture
def spec():
    from grd.spec import AgentSpec

    return AgentSpec.load("ai_sdr", AGENTS_DIR)
