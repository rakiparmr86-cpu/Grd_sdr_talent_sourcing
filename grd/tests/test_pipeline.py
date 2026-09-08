from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from grd.pipeline import Pipeline


def test_pipeline_scores_and_persists(settings):
    pipe = Pipeline(settings)
    leads = asyncio.run(pipe.score_batch(["alpha.com", "beta.io", "gamma.co"]))

    assert len(leads) == 3
    for lead in leads:
        assert lead.lead_id is not None
        assert 0.0 <= lead.score.value <= 100.0
        assert lead.score.tier in {"A", "B", "C", "D"}

    # re-running updates the same lead row, does not duplicate
    again = asyncio.run(pipe.score_batch(["alpha.com"]))
    assert again[0].lead_id == leads[0].lead_id


def test_api_end_to_end(settings, monkeypatch):
    monkeypatch.setenv("GRD_ENRICHMENT_PROVIDERS", "mock")
    monkeypatch.setenv("GRD_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GRD_DATABASE_URL", "sqlite://")

    from grd.config import get_settings

    get_settings.cache_clear()
    from grd.main import create_app

    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["llm"] == "mock"

    resp = client.post("/api/leads/score", json={"domains": ["one.com", "two.com"]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2

    listing = client.get("/api/leads")
    assert listing.status_code == 200
    assert len(listing.json()) == 2

    lead_id = body[0]["lead_id"]
    detail = client.get(f"/api/leads/{lead_id}")
    assert detail.status_code == 200
    assert detail.json()["company_profile"]["domain"] in {"one.com", "two.com"}

    get_settings.cache_clear()
