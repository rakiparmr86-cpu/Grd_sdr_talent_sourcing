from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field

from grd.enrichment.base import (
    IMPORTANT_FIELDS,
    EnrichmentProvider,
    assemble_profile,
    recompute_completeness,
)
from grd.classify import normalize_domain as _clean_domain
from grd.enrichment.capabilities import ALL_CAPABILITIES, COMPANY_LOOKUP, Fact
from grd.llm.base import LLM
from grd.schemas import CompanyProfile, ContactProfile, ResearchIssue

_SOURCEABLE_FIELDS = [
    "name", "description", "industry", "size_band", "employee_count",
    "hq_country", "open_roles", "headcount_growth_pct_6mo",
]


@dataclass
class ResearchResult:
    profile: CompanyProfile
    contact: ContactProfile | None
    summary: str
    sources: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    capabilities_used: list[str] = field(default_factory=list)
    issues: list[ResearchIssue] = field(default_factory=list)


class ResearchAgent:
    """Build a factual lead profile from an allow-list of capabilities.

    Rules:
      * every non-empty field carries provenance ("no fact without a source");
        anything that slips through is nulled and flagged `unsourced_fact`
      * expected failures become `ResearchIssue`s, never exceptions
      * stale funding/news is kept but flagged `stale_data`
      * a thin profile is flagged `low_confidence`
    """

    def __init__(
        self,
        providers: list[EnrichmentProvider],
        llm: LLM,
        *,
        allowlist: list[str] | None = None,
        important_fields: list[str] | None = None,
        timeout: float = 10.0,
        retries: int = 1,
        stale_after_months: int = 24,
        summary_prompt: str | None = None,
    ) -> None:
        self.providers = providers
        self.llm = llm
        self.allowlist = [c for c in (allowlist or list(ALL_CAPABILITIES)) if c in ALL_CAPABILITIES]
        self.important_fields = important_fields or IMPORTANT_FIELDS
        self.timeout = timeout
        self.retries = max(0, retries)
        self.stale_after_months = stale_after_months
        self.summary_prompt = summary_prompt

    async def run(
        self, domain: str, contact_hint: ContactProfile | None = None
    ) -> ResearchResult:
        domain = _clean_domain(domain)

        facts: list[Fact] = []
        issues: list[ResearchIssue] = []
        providers_used: set[str] = set()
        caps_used: list[str] = []

        for capability in self.allowlist:
            cap_facts, cap_issues, used = await self._run_capability(
                capability, domain, contact_hint
            )
            facts.extend(cap_facts)
            issues.extend(cap_issues)
            providers_used.update(used)
            if cap_facts:
                caps_used.append(capability)

        profile, contact = assemble_profile(domain, facts, contact_hint)
        profile = recompute_completeness(profile, self.important_fields)

        self._enforce_sourcing(profile, issues)
        self._flag_stale(profile, issues)
        self._flag_low_confidence(profile, issues)

        summary = await self.llm.summarize_research(profile, prompt=self.summary_prompt)

        return ResearchResult(
            profile=profile,
            contact=contact,
            summary=summary,
            sources=profile.sources,
            providers_used=sorted(providers_used),
            capabilities_used=caps_used,
            issues=_dedupe(issues),
        )

    # --- capability orchestration ---------------------------------------

    async def _run_capability(
        self, capability: str, domain: str, contact_hint: ContactProfile | None
    ) -> tuple[list[Fact], list[ResearchIssue], list[str]]:
        providers = [p for p in self.providers if capability in p.capabilities]
        if not providers:
            return [], [], []  # not attempted - silent, it wasn't in scope

        facts: list[Fact] = []
        issues: list[ResearchIssue] = []
        used: list[str] = []
        produced = False

        for provider in providers:
            result = await self._call_with_retry(provider, capability, domain, contact_hint)
            if result is None:
                issues.append(ResearchIssue(
                    kind="capability_error",
                    detail=f"{provider.name} failed after {self.retries + 1} attempt(s)",
                    capability=capability, source=provider.name,
                ))
                continue
            used.append(provider.name)
            facts.extend(result.facts)
            issues.extend(result.issues)
            produced = produced or bool(result.facts)

        # An empty result is only notable for the capability that must yield
        # firmographics; "no funding" / "no news" is a valid finding, not a miss.
        if not produced and not issues and capability == COMPANY_LOOKUP:
            issues.append(ResearchIssue(
                kind="enrichment_miss",
                detail="no firmographic data returned (company_lookup)",
                capability=capability,
            ))
        return facts, issues, used

    async def _call_with_retry(self, provider, capability, domain, contact_hint):
        for _ in range(self.retries + 1):
            try:
                return await asyncio.wait_for(
                    provider.call(capability, domain=domain, contact_hint=contact_hint),
                    timeout=self.timeout,
                )
            except Exception:  # noqa: BLE001 - any failure is retried then flagged
                continue
        return None

    # --- guardrails / diagnostics -------------------------------------

    def _enforce_sourcing(self, profile: CompanyProfile, issues: list[ResearchIssue]) -> None:
        sourced = {p.field for p in profile.provenance if not p.note}
        for f in _SOURCEABLE_FIELDS:
            value = getattr(profile, f, None)
            if value not in (None, "", [], 0) and f not in sourced:
                setattr(profile, f, None)
                issues.append(ResearchIssue(
                    kind="unsourced_fact",
                    detail=f"dropped '{f}': value present with no provenance",
                ))
        profile.known_fields = [k for k in profile.known_fields if getattr(profile, k, None) not in (None, "", [], 0)]

    def _flag_stale(self, profile: CompanyProfile, issues: list[ResearchIssue]) -> None:
        cutoff = dt.date.today() - dt.timedelta(days=int(self.stale_after_months * 30.44))
        for fund in profile.funding:
            d = _parse_date(fund.announced_on)
            if d and d < cutoff:
                issues.append(ResearchIssue(
                    kind="stale_data",
                    detail=f"latest funding is {(dt.date.today() - d).days // 30} months old ({fund.announced_on})",
                    capability="funding_lookup", source=fund.source,
                ))
        for item in profile.recent_news:
            d = _parse_date(item.published_on)
            if d and d < cutoff:
                issues.append(ResearchIssue(
                    kind="stale_data",
                    detail=f"news item dated {item.published_on} is beyond the {self.stale_after_months}-month window",
                    capability="news_search", source=item.source,
                ))

    def _flag_low_confidence(self, profile: CompanyProfile, issues: list[ResearchIssue]) -> None:
        total = len(profile.known_fields) + len(profile.unknown_fields)
        if total and len(profile.known_fields) / total < 0.5:
            issues.append(ResearchIssue(
                kind="low_confidence",
                detail=(
                    f"only {len(profile.known_fields)}/{total} key fields sourced "
                    f"(missing: {', '.join(profile.unknown_fields)})"
                ),
            ))


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _dedupe(issues: list[ResearchIssue]) -> list[ResearchIssue]:
    seen: set[tuple] = set()
    out: list[ResearchIssue] = []
    for i in issues:
        key = (i.kind, i.detail, i.capability, i.source)
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out
