from __future__ import annotations

import asyncio
import datetime as dt

from grd.agents.scoring import ScoringAgent
from grd.llm.mock import MockLLM
from grd.schemas import CompanyProfile, Funding


def _ideal() -> CompanyProfile:
    recent = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    return CompanyProfile(
        domain="ideal.com",
        name="Ideal",
        industry="fintech",
        size_band="201-500",
        hq_country="IN",
        funding=[Funding(round="Series B", amount_usd=3e7, announced_on=recent)],
        open_roles=20,
        headcount_growth_pct_6mo=25.0,
    )


def _poor() -> CompanyProfile:
    return CompanyProfile(
        domain="poor.com",
        name="Poor",
        industry="staffing and recruiting",
        size_band="5001+",
        hq_country="BR",
        funding=[],
        open_roles=0,
        headcount_growth_pct_6mo=-5.0,
    )


def _score(profile: CompanyProfile, icp: dict):
    return asyncio.run(ScoringAgent(icp, MockLLM()).run(profile))


def test_ideal_profile_scores_high_and_qualifies(icp):
    score = _score(_ideal(), icp)
    assert score.value >= 85
    assert score.tier == "A"
    assert score.qualified is True
    assert score.confidence == 1.0
    assert any("funding" in s.lower() for s in score.matched_signals)


def test_poor_profile_scores_low_and_is_rejected(icp):
    score = _score(_poor(), icp)
    assert score.value <= 25
    assert score.tier == "D"
    assert score.qualified is False
    assert any("exclude list" in c for c in score.missing_criteria)


def test_llm_adjustment_is_bounded(icp):
    score = _score(_ideal(), icp)
    assert abs(score.llm_adjustment) <= icp["max_llm_adjustment"]
    assert 0.0 <= score.value <= 100.0


def test_unknown_fields_lower_confidence(icp):
    score = _score(CompanyProfile(domain="bare.com", industry="saas"), icp)
    assert score.confidence < 0.5
    assert score.value < 40


def test_component_weights_sum_to_100(icp):
    assert sum(icp["weights"].values()) == 100
