from __future__ import annotations

import datetime as dt

from grd.llm.base import LLM
from grd.schemas import CompanyProfile, LeadScore, ScoreComponent

_COMPONENTS = ("industry", "size", "geography", "funding_recency", "open_roles", "headcount_growth")


class ScoringAgent:
    """Step 1b - deterministic rubric first, then a small bounded LLM nudge."""

    def __init__(self, icp: dict, llm: LLM, *, signal_prompt: str | None = None) -> None:
        self.icp = icp
        self.llm = llm
        self.signal_prompt = signal_prompt
        self.weights = {c: float(icp["weights"].get(c, 0)) for c in _COMPONENTS}
        self._weight_total = sum(self.weights.values()) or 1.0
        self.thresholds = icp["thresholds"]
        self.important_fields = icp.get("important_fields") or [
            "industry", "size_band", "hq_country", "funding", "open_roles",
            "headcount_growth_pct_6mo",
        ]
        self.max_llm_adjustment = float(icp.get("max_llm_adjustment", 10))

    async def run(self, profile: CompanyProfile) -> LeadScore:
        raw_scores = {
            "industry": self._industry(profile),
            "size": self._size(profile),
            "geography": self._geography(profile),
            "funding_recency": self._funding(profile),
            "open_roles": self._open_roles(profile),
            "headcount_growth": self._growth(profile),
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

        adjustment, adj_rationale = await self.llm.interpret_signals(
            profile, self.icp, prompt=self.signal_prompt
        )
        adjustment = max(-self.max_llm_adjustment, min(self.max_llm_adjustment, float(adjustment)))
        value = round(max(0.0, min(100.0, deterministic + adjustment)), 1)

        confidence = self._confidence(profile)
        tier = self._tier(value)
        qualified = value >= float(self.thresholds["qualify"])

        matched = _matched_signals(profile, raw_scores)
        missing = [f"{c.name}: {c.basis}" for c in components if c.raw < 0.3]

        rationale = (
            f"Deterministic fit {deterministic:.0f}/100; LLM signal adj {adjustment:+.0f} "
            f"({adj_rationale}); final {value:.0f}/100 -> tier {tier}, "
            f"{'qualified' if qualified else 'not qualified'} "
            f"(confidence {confidence:.0%})."
        )

        return LeadScore(
            value=value,
            deterministic_value=deterministic,
            llm_adjustment=adjustment,
            tier=tier,
            qualified=qualified,
            confidence=round(confidence, 3),
            components=components,
            matched_signals=matched,
            missing_criteria=missing,
            rationale=rationale,
        )

    # --- component scorers: return (raw 0..1, basis text) ---------------------

    def _industry(self, p: CompanyProfile) -> tuple[float, str]:
        if not p.industry:
            return 0.0, "industry unknown"
        val = p.industry.strip().lower()
        inc = {i.lower() for i in self.icp["industries"].get("include", [])}
        exc = {i.lower() for i in self.icp["industries"].get("exclude", [])}
        if val in exc:
            return 0.0, f"'{p.industry}' is on the exclude list"
        if val in inc:
            return 1.0, f"'{p.industry}' is a target industry"
        return 0.35, f"'{p.industry}' is adjacent / not a listed target"

    def _size(self, p: CompanyProfile) -> tuple[float, str]:
        if not p.size_band:
            return 0.0, "size unknown"
        ideal = set(self.icp["size_bands"].get("ideal", []))
        ok = set(self.icp["size_bands"].get("acceptable", []))
        if p.size_band in ideal:
            return 1.0, f"size {p.size_band} is ideal"
        if p.size_band in ok:
            return 0.6, f"size {p.size_band} is acceptable"
        return 0.15, f"size {p.size_band} is out of range"

    def _geography(self, p: CompanyProfile) -> tuple[float, str]:
        if not p.hq_country:
            return 0.0, "HQ country unknown"
        inc = {c.upper() for c in self.icp["geographies"].get("include", [])}
        if p.hq_country.upper() in inc:
            return 1.0, f"HQ {p.hq_country} in target region"
        return 0.25, f"HQ {p.hq_country} outside target region"

    def _funding(self, p: CompanyProfile) -> tuple[float, str]:
        recent_months = float(self.icp["signals"].get("funding_recent_months", 12))
        latest = _latest_funding_date(p)
        if latest is None:
            return 0.0, "no funding on record"
        age = (dt.date.today() - latest).days / 30.44
        if age <= recent_months:
            return 1.0, f"funded {age:.0f} months ago"
        if age >= 2 * recent_months:
            return 0.0, f"last funding {age:.0f} months ago (stale)"
        raw = 1.0 - (age - recent_months) / recent_months
        return round(raw, 3), f"funded {age:.0f} months ago"

    def _open_roles(self, p: CompanyProfile) -> tuple[float, str]:
        if p.open_roles is None:
            return 0.0, "open roles unknown"
        target = float(self.icp["signals"].get("target_open_roles", 8))
        raw = min(p.open_roles / (2 * target), 1.0)
        return round(raw, 3), f"{p.open_roles} open roles (target {target:.0f})"

    def _growth(self, p: CompanyProfile) -> tuple[float, str]:
        if p.headcount_growth_pct_6mo is None:
            return 0.0, "headcount trend unknown"
        target = float(self.icp["signals"].get("target_headcount_growth_pct_6mo", 12))
        raw = max(0.0, min(p.headcount_growth_pct_6mo / (2 * target), 1.0))
        return round(raw, 3), f"headcount {p.headcount_growth_pct_6mo:+.0f}% / 6mo"

    # --- helpers ------------------------------------------------------------

    def _confidence(self, p: CompanyProfile) -> float:
        known = 0
        for field in self.important_fields:
            value = getattr(p, field, None)
            if value not in (None, "", [], 0):
                known += 1
        return known / len(self.important_fields)

    def _tier(self, value: float) -> str:
        for tier in ("A", "B", "C"):
            if value >= float(self.thresholds[tier]):
                return tier
        return "D"


def _latest_funding_date(p: CompanyProfile) -> dt.date | None:
    latest = None
    for f in p.funding:
        if not f.announced_on:
            continue
        try:
            d = dt.date.fromisoformat(f.announced_on)
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    return latest


def _matched_signals(p: CompanyProfile, raw: dict[str, tuple[float, str]]) -> list[str]:
    out: list[str] = []
    if raw["industry"][0] >= 0.9:
        out.append(f"Industry match: {p.industry}")
    if raw["size"][0] >= 0.6:
        out.append(f"Size in range: {p.size_band}")
    if raw["geography"][0] >= 0.9:
        out.append(f"HQ in target region: {p.hq_country}")
    if raw["funding_recency"][0] >= 0.5 and p.funding:
        f = p.funding[-1]
        out.append(f"Recent funding: {f.round or 'round'} ({f.announced_on})")
    if raw["open_roles"][0] >= 0.5:
        out.append(f"{p.open_roles} open roles")
    if raw["headcount_growth"][0] >= 0.5:
        out.append(f"Headcount {p.headcount_growth_pct_6mo:+.0f}% in 6mo")
    return out
