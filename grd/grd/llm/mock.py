from __future__ import annotations

from grd.llm.base import LLM
from grd.schemas import CompanyProfile


class MockLLM(LLM):
    """Deterministic stand-in. No network. Keeps the pipeline + tests runnable."""

    async def summarize_research(
        self, profile: CompanyProfile, *, prompt: str | None = None
    ) -> str:
        del prompt  # deterministic stand-in ignores the template
        bits: list[str] = []
        head = profile.name or profile.domain
        if profile.industry:
            head += f", a {profile.industry} company"
        if profile.hq_country:
            head += f" based in {profile.hq_country}"
        bits.append(head + ".")

        if profile.size_band or profile.employee_count:
            size = profile.size_band or f"~{profile.employee_count}"
            bits.append(f"Headcount band {size}.")
        if profile.headcount_growth_pct_6mo is not None:
            bits.append(f"Headcount changed {profile.headcount_growth_pct_6mo:+.0f}% over 6 months.")
        if profile.funding:
            latest = profile.funding[-1]
            amt = f" ${latest.amount_usd:,.0f}" if latest.amount_usd else ""
            when = f" on {latest.announced_on}" if latest.announced_on else ""
            bits.append(f"Last funding: {latest.round or 'round'}{amt}{when}.")
        if profile.open_roles is not None:
            bits.append(f"{profile.open_roles} open roles detected.")
        if profile.tech:
            bits.append("Tech seen: " + ", ".join(profile.tech[:6]) + ".")
        if profile.unknown_fields:
            bits.append("Unknown: " + ", ".join(profile.unknown_fields) + ".")
        return " ".join(bits)

    async def interpret_signals(
        self, profile: CompanyProfile, icp: dict, *, prompt: str | None = None
    ) -> tuple[float, str]:
        del prompt
        cap = float(icp.get("max_llm_adjustment", 10))
        sig = icp.get("signals", {})
        recent_months = float(sig.get("funding_recent_months", 12))
        target_roles = float(sig.get("target_open_roles", 8))

        adj = 0.0
        notes: list[str] = []

        recent_funding = _has_recent_funding(profile, recent_months)
        strong_hiring = (profile.open_roles or 0) >= target_roles
        growing = (profile.headcount_growth_pct_6mo or 0) >= float(
            sig.get("target_headcount_growth_pct_6mo", 12)
        )

        if recent_funding and strong_hiring:
            adj += cap
            notes.append("recent funding paired with active hiring is a strong buying signal")
        elif recent_funding:
            adj += cap * 0.4
            notes.append("recently funded, likely to be scaling teams")
        elif strong_hiring:
            adj += cap * 0.4
            notes.append("high open-role count suggests hiring pressure")

        if growing:
            adj += cap * 0.2
            notes.append("headcount trending up")

        if not profile.funding and not profile.open_roles:
            adj -= cap * 0.3
            notes.append("no funding or hiring signal found")

        adj = max(-cap, min(cap, round(adj, 1)))
        rationale = "; ".join(notes) if notes else "no notable signals either way"
        return adj, rationale

    # --- recruiting -----------------------------------------------------

    async def summarize_candidate(self, profile) -> str:
        bits: list[str] = []
        head = profile.full_name or profile.handle
        if profile.headline:
            head += f" - {profile.headline}"
        if profile.location_country:
            head += f" ({profile.location_country})"
        bits.append(head + ".")

        if profile.years_experience is not None:
            bits.append(f"~{profile.years_experience} years experience.")
        if profile.skills:
            bits.append("Skills: " + ", ".join(profile.skills[:10]) + ".")
        if profile.languages:
            bits.append("Languages: " + ", ".join(profile.languages[:6]) + ".")
        if profile.public_repos is not None:
            bits.append(
                f"{profile.public_repos} public repos, "
                f"{profile.followers or 0} followers, {profile.total_stars or 0} stars."
            )
        if profile.top_repos:
            top = profile.top_repos[0]
            bits.append(f"Top repo: {top.name} ({top.stars} stars).")
        if profile.last_active:
            bits.append(f"Last public activity {profile.last_active}.")
        if profile.unknown_fields:
            bits.append("Unknown: " + ", ".join(profile.unknown_fields) + ".")
        return " ".join(bits)

    async def assess_candidate(self, profile, rubric: dict) -> tuple[float, str]:
        cap = float(rubric.get("max_llm_adjustment", 10))
        must = {s.lower() for s in rubric.get("skills", {}).get("must_have", [])}
        have = {s.lower() for s in profile.skills} | {l.lower() for l in profile.languages}

        adj = 0.0
        notes: list[str] = []

        if must:
            matched = must & have
            if matched == must:
                adj += cap * 0.6
                notes.append("covers all must-have skills")
            elif len(matched) >= len(must) * 0.6:
                adj += cap * 0.2
                notes.append("covers most must-have skills")
            elif not matched:
                adj -= cap * 0.5
                notes.append("no must-have skills evidenced")

        stars = profile.total_stars or 0
        if stars >= 200:
            adj += cap * 0.3
            notes.append("strong open-source traction")

        recent = _is_recent(profile.last_active, rubric.get("signals", {}).get("recent_activity_months", 6))
        if recent is False:
            adj -= cap * 0.2
            notes.append("no recent public activity")

        adj = max(-cap, min(cap, round(adj, 1)))
        rationale = "; ".join(notes) if notes else "no strong evidence either way"
        return adj, rationale


def _is_recent(iso_date: str | None, months: float) -> bool | None:
    import datetime as dt

    if not iso_date:
        return None
    try:
        d = dt.date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    return (dt.date.today() - d).days / 30.44 <= months


def _has_recent_funding(profile: CompanyProfile, months: float) -> bool:
    import datetime as dt

    latest = None
    for f in profile.funding:
        if not f.announced_on:
            continue
        try:
            d = dt.date.fromisoformat(f.announced_on)
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    if latest is None:
        return False
    age_months = (dt.date.today() - latest).days / 30.44
    return age_months <= months
