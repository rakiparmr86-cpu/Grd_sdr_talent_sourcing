from __future__ import annotations

import asyncio

from grd.pipeline import Pipeline
from grd.spec import AgentSpec


def test_spec_loads_config_and_workflow(spec: AgentSpec):
    assert spec.name == "ai_sdr"
    assert spec.config["agent"] == "ai_sdr"
    assert spec.active_steps() == ["research", "scoring"]


def test_tools_allow_is_parsed_without_comments(spec: AgentSpec):
    caps = spec.tools_allow()
    assert caps == [
        "company_lookup", "contact_lookup", "funding_lookup",
        "tech_lookup", "news_search", "web_fetch",
    ]
    assert all(not c.startswith("#") for c in caps)


def test_prompts_and_icp_resolve(spec: AgentSpec):
    assert "{facts}" in (spec.summary_prompt() or "")
    assert "{signals}" in (spec.signal_prompt() or "")
    assert spec.icp_name() == "grd_staffing"
    assert (spec.icp_dir() / "grd_staffing.yaml").exists()
    assert spec.gate_a_threshold() == 62.0


def test_missing_agent_raises_but_load_or_none_is_safe(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        AgentSpec.load("nope", tmp_path)
    assert AgentSpec.load_or_none("nope", tmp_path) is None


def test_pipeline_uses_the_spec(settings, spec):
    pipe = Pipeline(settings, spec=spec)
    assert pipe.spec is spec
    assert pipe.research.allowlist == spec.tools_allow()
    assert pipe.research.summary_prompt == spec.summary_prompt()

    leads = asyncio.run(pipe.score_batch(["alpha.com", "beta.io"]))
    assert len(leads) == 2
    assert all(0.0 <= x.score.value <= 100.0 for x in leads)
    # scoring agent got the spec's signal prompt
    _, scoring = pipe._scoring_for("grd_staffing")
    assert scoring.signal_prompt == spec.signal_prompt()


def test_pipeline_auto_loads_spec_from_settings(settings):
    pipe = Pipeline(settings)          # no spec passed
    assert pipe.spec is not None
    assert pipe.spec.name == "ai_sdr"
