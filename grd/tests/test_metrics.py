from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from grd.metrics import sdr_metrics
from grd.models import PipelineRun
from grd.pipeline import Pipeline


def test_pipeline_writes_a_run_row_per_domain(settings):
    pipe = Pipeline(settings)
    asyncio.run(pipe.score_batch(["alpha.com", "beta.io", "gamma.co"]))

    with pipe.Session() as s:
        runs = list(s.scalars(select(PipelineRun)))
    assert len(runs) == 3
    for r in runs:
        assert r.vertical == "sdr"
        assert r.status == "ok"
        names = [st["step"] for st in r.steps_json]
        assert names == ["research", "scoring"]
        assert all("ms" in st for st in r.steps_json)


def test_sdr_metrics_shape_and_values(settings):
    pipe = Pipeline(settings)
    asyncio.run(pipe.score_batch(["alpha.com", "beta.io", "gamma.co", "delta.dev"]))

    with pipe.Session() as s:
        m = sdr_metrics(s)

    assert set(m) >= {"funnel", "quality", "reliability", "economics", "notes"}
    assert m["funnel"]["researched"] == 4
    assert m["funnel"]["scored"] == 4
    assert m["funnel"]["enrichment_hit_rate"] == 1.0        # mock always yields a provider
    assert 0.0 <= (m["funnel"]["qualify_rate"] or 0) <= 1.0
    assert sum(m["funnel"]["tier_counts"].values()) == 4
    assert m["reliability"]["pipeline_runs"] == 4
    assert m["reliability"]["pipeline_success_rate"] == 1.0
    assert set(m["reliability"]["step_success_rate"]) == {"research", "scoring"}
    assert m["reliability"]["step_latency_ms_p50"]["research"] is not None
    # downstream funnel not wired yet
    assert m["funnel"]["drafted"] == 0
    assert m["economics"]["total_cost_usd"] == 0.0


def test_metrics_api_and_dashboard(monkeypatch):
    monkeypatch.setenv("GRD_ENRICHMENT_PROVIDERS", "mock")
    monkeypatch.setenv("GRD_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GRD_DATABASE_URL", "sqlite://")

    from grd.config import get_settings

    get_settings.cache_clear()
    from grd.main import create_app

    client = TestClient(create_app())
    client.post("/api/leads/score", json={"domains": ["one.com", "two.com"]})

    m = client.get("/api/metrics")
    assert m.status_code == 200
    assert m.json()["funnel"]["scored"] == 2

    d = client.get("/dashboard")
    assert d.status_code == 200
    assert "text/html" in d.headers["content-type"]
    assert "GRD AI SDR" in d.text

    get_settings.cache_clear()
