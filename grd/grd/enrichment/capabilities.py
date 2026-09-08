from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from grd.schemas import ResearchIssue

# The research agent's tool allow-list. Providers declare which of these they
# support; the agent calls capabilities, never providers directly.
COMPANY_LOOKUP = "company_lookup"    # firmographics: name, industry, size, hq, description
CONTACT_LOOKUP = "contact_lookup"    # a decision-maker contact
FUNDING_LOOKUP = "funding_lookup"    # funding rounds
TECH_LOOKUP = "tech_lookup"          # tech stack
NEWS_SEARCH = "news_search"          # recent news items
WEB_FETCH = "web_fetch"              # the company's OWN website (homepage + careers)

ALL_CAPABILITIES: tuple[str, ...] = (
    COMPANY_LOOKUP,
    CONTACT_LOOKUP,
    FUNDING_LOOKUP,
    TECH_LOOKUP,
    NEWS_SEARCH,
    WEB_FETCH,
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Fact:
    """One piece of information plus where it came from. No fact without a source."""

    field: str          # target field on CompanyProfile, or "contact"
    value: Any          # scalar, str (for tech), or dict (funding / news / contact)
    source: str         # URL or "mock://..." - provenance
    capability: str     # which capability produced it
    retrieved_at: str = field(default_factory=now_iso)
    as_of: str | None = None   # the data's own date, when known (funding/news date)


@dataclass
class CapabilityResult:
    facts: list[Fact] = field(default_factory=list)
    issues: list[ResearchIssue] = field(default_factory=list)
