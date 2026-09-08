from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from grd.agents.research import ResearchAgent, _clean_domain
from grd.enrichment.base import EnrichmentProvider, assemble_profile
from grd.enrichment.capabilities import (
    COMPANY_LOOKUP,
    FUNDING_LOOKUP,
    WEB_FETCH,
    CapabilityResult,
    Fact,
)
from grd.enrichment.mock import MockEnrichmentProvider
from grd.llm.mock import MockLLM
from grd.schemas import ResearchIssue


def _run(agent: ResearchAgent, domain: str):
    return asyncio.run(agent.run(domain))


def test_clean_domain_strips_scheme_and_path():
    assert _clean_domain("https://www.Example.com/careers") == "example.com"
    assert _clean_domain("  HTTP://foo.io  ") == "foo.io"


def test_every_non_empty_field_has_provenance():
    agent = ResearchAgent([MockEnrichmentProvider()], MockLLM())
    res = _run(agent, "acme.io")

    sourced = {p.field for p in res.profile.provenance if not p.note}
    for field in ("industry", "size_band", "hq_country", "name"):
        if getattr(res.profile, field, None):
            assert field in sourced, f"{field} has a value but no provenance"
    # provenance carries a real source string
    assert all(p.source for p in res.profile.provenance)
    assert res.profile.sources == sorted(set(res.profile.sources))


def test_capabilities_and_providers_are_reported():
    agent = ResearchAgent([MockEnrichmentProvider()], MockLLM())
    res = _run(agent, "acme.io")
    assert "mock" in res.providers_used
    assert COMPANY_LOOKUP in res.capabilities_used
    # mock does not support web_fetch -> it is simply not attempted, no issue
    assert not any(i.capability == WEB_FETCH for i in res.issues)


def test_allowlist_limits_which_capabilities_run():
    agent = ResearchAgent(
        [MockEnrichmentProvider()], MockLLM(), allowlist=[COMPANY_LOOKUP]
    )
    res = _run(agent, "acme.io")
    assert res.capabilities_used == [COMPANY_LOOKUP]
    assert res.profile.funding == []          # funding_lookup was not allowed
    assert res.profile.tech == []


def test_research_is_deterministic_per_domain_ignoring_timestamps():
    agent = ResearchAgent([MockEnrichmentProvider()], MockLLM())
    a = _run(agent, "same.com")
    b = _run(agent, "same.com")
    assert a.profile.model_dump(exclude={"provenance"}) == b.profile.model_dump(exclude={"provenance"})
    assert [(p.field, p.source) for p in a.profile.provenance] == \
           [(p.field, p.source) for p in b.profile.provenance]


class _BoomProvider(EnrichmentProvider):
    name = "boom"
    capabilities = {COMPANY_LOOKUP}

    async def call(self, capability, *, domain, contact_hint=None):
        raise RuntimeError("kaboom")


def test_provider_error_becomes_issue_not_crash():
    agent = ResearchAgent([_BoomProvider()], MockLLM(), retries=0)
    res = _run(agent, "acme.io")
    assert any(i.kind == "capability_error" and i.source == "boom" for i in res.issues)
    assert res.profile.industry is None


class _StaleFundingProvider(EnrichmentProvider):
    name = "stale"
    capabilities = {COMPANY_LOOKUP, FUNDING_LOOKUP}

    async def call(self, capability, *, domain, contact_hint=None):
        res = CapabilityResult()
        old = (dt.date.today() - dt.timedelta(days=1500)).isoformat()
        if capability == COMPANY_LOOKUP:
            res.facts.append(Fact("industry", "fintech", "stale://co", capability))
        elif capability == FUNDING_LOOKUP:
            res.facts.append(Fact(
                "funding",
                {"round": "Series A", "announced_on": old, "source": "stale://cb"},
                "stale://cb", capability, as_of=old,
            ))
        return res


def test_stale_funding_is_flagged_but_kept():
    agent = ResearchAgent([_StaleFundingProvider()], MockLLM(), stale_after_months=24)
    res = _run(agent, "acme.io")
    assert len(res.profile.funding) == 1                      # kept
    assert any(i.kind == "stale_data" for i in res.issues)    # flagged


class _WebBlockedProvider(EnrichmentProvider):
    name = "web"
    capabilities = {WEB_FETCH}

    async def call(self, capability, *, domain, contact_hint=None):
        return CapabilityResult(issues=[ResearchIssue(
            kind="site_blocked", detail="403", capability=WEB_FETCH, source=f"https://{domain}"
        )])


def test_site_blocked_issue_propagates_and_low_confidence_flagged():
    agent = ResearchAgent([_WebBlockedProvider()], MockLLM())
    res = _run(agent, "acme.io")
    assert any(i.kind == "site_blocked" for i in res.issues)
    assert any(i.kind == "low_confidence" for i in res.issues)  # nothing else sourced


def test_assemble_profile_records_corroborating_sources():
    facts = [
        Fact("industry", "fintech", "src-a", COMPANY_LOOKUP),
        Fact("industry", "fintech", "src-b", COMPANY_LOOKUP),
    ]
    profile, _ = assemble_profile("x.com", facts)
    assert profile.industry == "fintech"
    notes = [p.note for p in profile.provenance if p.field == "industry"]
    assert notes.count(None) == 1 and any("corroborating" in (n or "") for n in notes)
