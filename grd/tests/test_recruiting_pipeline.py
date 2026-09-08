from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from grd.recruiting.agents.research import CandidateResearchAgent
from grd.recruiting.pipeline import RecruitingPipeline
from grd.recruiting.sourcing.mock import MockCandidateSource
from grd.llm.mock import MockLLM


def test_candidate_research_is_deterministic_and_complete():
    agent = CandidateResearchAgent([MockCandidateSource()], MockLLM())
    a = asyncio.run(agent.run("octocat"))
    b = asyncio.run(agent.run("OCTOCAT"))  # normalised to same handle

    assert a.profile.handle == "octocat"
    assert a.summary
    assert "mock" in a.sources_used
    assert a.profile.model_dump() == b.profile.model_dump()
    assert set(a.profile.known_fields) | set(a.profile.unknown_fields)


def test_pipeline_scores_and_persists(settings):
    pipe = RecruitingPipeline(settings)
    cands = asyncio.run(pipe.score_batch(["alice", "bob", "carol"]))

    assert len(cands) == 3
    for c in cands:
        assert c.candidate_id is not None
        assert c.rubric == "backend_engineer_india"
        assert 0.0 <= c.score.value <= 100.0
        assert c.score.tier in {"A", "B", "C", "D"}

    again = asyncio.run(pipe.score_batch(["alice"]))
    assert again[0].candidate_id == cands[0].candidate_id


def test_api_end_to_end(monkeypatch):
    monkeypatch.setenv("GRD_ENRICHMENT_PROVIDERS", "mock")
    monkeypatch.setenv("GRD_CANDIDATE_SOURCES", "mock")
    monkeypatch.setenv("GRD_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GRD_DATABASE_URL", "sqlite://")

    from grd.config import get_settings

    get_settings.cache_clear()
    from grd.main import create_app

    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["recruiting"]["rubric"] == "backend_engineer_india"

    resp = client.post("/api/candidates/score", json={"handles": ["dev-one", "dev-two"]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2

    listing = client.get("/api/candidates")
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    cid = body[0]["candidate_id"]
    detail = client.get(f"/api/candidates/{cid}")
    assert detail.status_code == 200
    assert detail.json()["candidate_profile"]["handle"] in {"dev-one", "dev-two"}

    get_settings.cache_clear()
