from __future__ import annotations

import asyncio
import datetime as dt

from grd.llm.mock import MockLLM
from grd.recruiting.agents.scoring import CandidateScoringAgent
from grd.recruiting.schemas import CandidateProfile, RepoHighlight


def _recent() -> str:
    return (dt.date.today() - dt.timedelta(days=30)).isoformat()


def _strong() -> CandidateProfile:
    return CandidateProfile(
        handle="strong",
        full_name="Strong Dev",
        headline="Senior Backend Engineer",
        location_country="IN",
        years_experience=8,
        skills=["python", "postgresql", "aws", "kubernetes"],
        languages=["Python", "Go"],
        public_repos=40,
        followers=200,
        total_stars=600,
        top_repos=[RepoHighlight(name="proj", stars=180, language="Python")],
        last_active=_recent(),
    )


def _weak() -> CandidateProfile:
    return CandidateProfile(
        handle="weak",
        full_name="Weak Match",
        location_country="BR",
        years_experience=1,
        skills=["php"],
        languages=["PHP"],
        public_repos=1,
        followers=2,
        total_stars=0,
        last_active=(dt.date.today() - dt.timedelta(days=1200)).isoformat(),
    )


def _score(profile: CandidateProfile, rubric: dict):
    return asyncio.run(CandidateScoringAgent(rubric, MockLLM()).run(profile))


def test_strong_candidate_scores_high_and_qualifies(rubric):
    score = _score(_strong(), rubric)
    assert score.value >= 85
    assert score.tier == "A"
    assert score.qualified is True
    assert score.confidence == 1.0
    assert any("python" in m.lower() for m in score.matched_requirements)


def test_weak_candidate_scores_low_and_is_rejected(rubric):
    score = _score(_weak(), rubric)
    assert score.value <= 30
    assert score.tier == "D"
    assert score.qualified is False
    assert any("must-have skill: postgresql" in g.lower() for g in score.gaps)
    assert any("aws" in g.lower() for g in score.gaps)


def test_llm_adjustment_is_bounded(rubric):
    score = _score(_strong(), rubric)
    assert abs(score.llm_adjustment) <= rubric["max_llm_adjustment"]
    assert 0.0 <= score.value <= 100.0


def test_unknown_fields_lower_confidence(rubric):
    bare = CandidateProfile(handle="bare", skills=["python"])
    score = _score(bare, rubric)
    assert score.confidence < 0.5
    assert score.qualified is False


def test_remote_ok_softens_location_penalty(rubric):
    p = _strong()
    p.location_country = "US"  # not in allowed_countries, but rubric is remote_ok
    score = _score(p, rubric)
    loc = next(c for c in score.components if c.name == "location")
    assert loc.raw == 0.5


def test_weights_sum_to_100(rubric):
    assert sum(rubric["weights"].values()) == 100
