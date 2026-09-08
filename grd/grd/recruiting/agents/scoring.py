from __future__ import annotations

import datetime as dt

from grd.llm.base import LLM
from grd.recruiting.schemas import CandidateProfile, CandidateScore, ScoreComponent

_COMPONENTS = (
    "skills_must_have",
    "skills_nice_to_have",
    "seniority",
    "location",
    "activity",
    "portfolio_strength",
)

_SYNONYMS = {
    "js": "javascript", "ts": "typescript", "golang": "go", "py": "python",
    "postgres": "postgresql", "psql": "postgresql", "k8s": "kubernetes",
    "gcp": "gcp", "node": "nodejs", "node.js": "nodejs",
}


def _norm(skills: set[str]) -> set[str]:
    out = set()
    for s in skills:
        s = s.strip().lower()
        out.add(_SYNONYMS.get(s, s))
    return out


class CandidateScoringAgent:
    """Step 3b - deterministic rubric first, then a small bounded LLM nudge."""

    def __init__(self, rubric: dict, llm: LLM) -> None:
        self.rubric = rubric
        self.llm = llm
        self.weights = {c: float(rubric["weights"].get(c, 0)) for c in _COMPONENTS}
        self._weight_total = sum(self.weights.values()) or 1.0
        self.thresholds = rubric["thresholds"]
        self.important_fields = rubric.get("important_fields") or [
            "skills", "years_experience", "location_country", "public_repos", "last_active",
        ]
        self.max_llm_adjustment = float(rubric.get("max_llm_adjustment", 10))

    async def run(self, profile: CandidateProfile) -> CandidateScore:
        raw_scores = {
            "skills_must_have": self._skills_must(profile),
            "skills_nice_to_have": self._skills_nice(profile),
            "seniority": self._seniority(profile),
            "location": self._location(profile),
            "activity": self._activity(profile),
            "portfolio_strength": self._portfolio(profile),
        }

        components: list[ScoreComponent] = []
        weighted_sum = 0.0
        for name in _COMPONENTS:
            raw, basis = raw_scores[name]
            weight = self.weights[name]
            weighted = raw * weight
            weighted_sum += weighted
            components.append(
                ScoreComponent(name=name, raw=round(raw, 3), weight=weight,
                               weighted=round(weighted, 2), basis=basis)
            )

        deterministic = round(100 * weighted_sum / self._weight_total, 1)
        adjustment, adj_rationale = await self.llm.assess_candidate(profile, self.rubric)
        adjustment = max(-self.max_llm_adjustment,
                         min(self.max_llm_adjustment, float(adjustment)))
        value = round(max(0.0, min(100.0, deterministic + adjustment)), 1)

        confidence = self._confidence(profile)
        tier = self._tier(value)
        qualified = value >= float(self.thresholds["qualify"])

        matched, gaps = self._matched_and_gaps(profile, raw_scores)

        rationale = (
            f"Deterministic fit {deterministic:.0f}/100; LLM evidence adj {adjustment:+.0f} "
            f"({adj_rationale}); final {value:.0f}/100 -> tier {tier}, "
            f"{'qualified' if qualified else 'not qualified'} "
            f"(confidence {confidence:.0%})."
        )

        return CandidateScore(
            value=value,
            deterministic_value=deterministic,
            llm_adjustment=adjustment,
            tier=tier,
            qualified=qualified,
            confidence=round(confidence, 3),
            components=components,
            matched_requirements=matched,
            gaps=gaps,
            rationale=rationale,
        )

    # --- component scorers -------------------------------------------------

    def _have(self, p: CandidateProfile) -> set[str]:
        return _norm({*p.skills, *p.languages})

    def _skills_must(self, p: CandidateProfile) -> tuple[float, str]:
        must = _norm(set(self.rubric["skills"].get("must_have", [])))
        if not must:
            return 1.0, "no must-have skills defined"
        if not p.skills and not p.languages:
            return 0.0, "candidate skills unknown"
        have = self._have(p)
        matched = sorted(must & have)
        missing = sorted(must - have)
        raw = len(matched) / len(must)
        return raw, f"{len(matched)}/{len(must)} must-have (have {matched}, missing {missing})"

    def _skills_nice(self, p: CandidateProfile) -> tuple[float, str]:
        nice = _norm(set(self.rubric["skills"].get("nice_to_have", [])))
        if not nice:
            return 1.0, "no nice-to-have skills defined"
        have = self._have(p)
        matched = sorted(nice & have)
        return len(matched) / len(nice), f"{len(matched)}/{len(nice)} nice-to-have ({matched})"

    def _seniority(self, p: CandidateProfile) -> tuple[float, str]:
        min_years = float(self.rubric["seniority"].get("min_years", 5))
        if p.years_experience is None:
            return 0.0, "years of experience unknown"
        raw = max(0.0, min(p.years_experience / min_years, 1.0))
        return raw, f"{p.years_experience}y vs {min_years:.0f}y target"

    def _location(self, p: CandidateProfile) -> tuple[float, str]:
        allowed = {c.upper() for c in self.rubric["location"].get("allowed_countries", [])}
        remote_ok = bool(self.rubric["location"].get("remote_ok", False))
        if not p.location_country:
            return 0.0, "location unknown"
        c = p.location_country.upper()
        if c in allowed:
            return 1.0, f"{c} in allowed list"
        if remote_ok:
            return 0.5, f"{c} outside list but role is remote-friendly"
        return 0.1, f"{c} not in allowed list"

    def _activity(self, p: CandidateProfile) -> tuple[float, str]:
        months = float(self.rubric["signals"].get("recent_activity_months", 6))
        d = _parse_date(p.last_active)
        if d is None:
            return 0.0, "no recent-activity date"
        age = (dt.date.today() - d).days / 30.44
        if age <= months:
            return 1.0, f"active {age:.0f} months ago"
        if age >= 2 * months:
            return 0.0, f"last active {age:.0f} months ago (stale)"
        return round(1.0 - (age - months) / months, 3), f"active {age:.0f} months ago"

    def _portfolio(self, p: CandidateProfile) -> tuple[float, str]:
        sig = self.rubric["signals"]
        if p.public_repos is None and p.followers is None and p.total_stars is None:
            return 0.0, "no portfolio signal"
        min_repos = max(float(sig.get("min_public_repos", 5)), 1)
        min_followers = max(float(sig.get("min_followers", 20)), 1)
        a = min((p.public_repos or 0) / min_repos, 1.0)
        b = min((p.followers or 0) / min_followers, 1.0)
        c = min((p.total_stars or 0) / (min_followers * 5), 1.0)
        raw = round((a + b + c) / 3, 3)
        return raw, f"{p.public_repos or 0} repos, {p.followers or 0} followers, {p.total_stars or 0} stars"

    # --- helpers ---------------------------------------------------------

    def _confidence(self, p: CandidateProfile) -> float:
        known = sum(
            1 for f in self.important_fields
            if getattr(p, f, None) not in (None, "", [], 0)
        )
        return known / len(self.important_fields)

    def _tier(self, value: float) -> str:
        for tier in ("A", "B", "C"):
            if value >= float(self.thresholds[tier]):
                return tier
        return "D"

    def _matched_and_gaps(
        self, p: CandidateProfile, raw: dict[str, tuple[float, str]]
    ) -> tuple[list[str], list[str]]:
        must = _norm(set(self.rubric["skills"].get("must_have", [])))
        have = self._have(p)
        matched = [f"Skill: {s}" for s in sorted(must & have)]
        gaps = [f"Missing must-have skill: {s}" for s in sorted(must - have)]

        if raw["seniority"][0] >= 0.8:
            matched.append(f"Seniority: {raw['seniority'][1]}")
        elif raw["seniority"][0] < 0.6:
            gaps.append(f"Seniority: {raw['seniority'][1]}")

        if raw["location"][0] >= 0.9:
            matched.append(f"Location: {raw['location'][1]}")
        elif raw["location"][0] < 0.5:
            gaps.append(f"Location: {raw['location'][1]}")

        if raw["activity"][0] >= 0.5:
            matched.append(f"Activity: {raw['activity'][1]}")
        else:
            gaps.append(f"Activity: {raw['activity'][1]}")

        if raw["portfolio_strength"][0] >= 0.5:
            matched.append(f"Portfolio: {raw['portfolio_strength'][1]}")
        return matched, gaps


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None
