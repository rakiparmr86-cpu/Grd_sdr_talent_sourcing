from __future__ import annotations

import abc

from grd.enrichment.capabilities import CapabilityResult, Fact
from grd.schemas import (
    CompanyProfile,
    ContactProfile,
    FactProvenance,
    Funding,
    HiringSignal,
    NewsItem,
)

# Fields the scoring model cares about; also drives the confidence metric.
IMPORTANT_FIELDS = [
    "industry",
    "size_band",
    "hq_country",
    "funding",
    "open_roles",
    "headcount_growth_pct_6mo",
]

_SCALAR_FIELDS = {
    "name",
    "description",
    "industry",
    "size_band",
    "employee_count",
    "hq_country",
    "open_roles",
    "headcount_growth_pct_6mo",
}


class EnrichmentProvider(abc.ABC):
    name: str = "base"
    capabilities: set[str] = set()

    @abc.abstractmethod
    async def call(
        self,
        capability: str,
        *,
        domain: str,
        contact_hint: ContactProfile | None = None,
    ) -> CapabilityResult:
        """Run one capability for a domain. Never raises for expected failures -
        it returns issues instead. The agent only calls capabilities the provider
        lists in `capabilities`.
        """


def assemble_profile(
    domain: str,
    facts: list[Fact],
    contact_hint: ContactProfile | None = None,
) -> tuple[CompanyProfile, ContactProfile | None]:
    """Build a CompanyProfile from Facts, recording provenance for every value.

    First non-empty value wins for scalars; later ones are recorded as
    corroborating. List fields accumulate.
    """
    profile = CompanyProfile(domain=domain)
    contact = contact_hint
    prov: list[FactProvenance] = []
    scalar_set: set[str] = set()

    for f in facts:
        p = FactProvenance(
            field=f.field, source=f.source, capability=f.capability,
            retrieved_at=f.retrieved_at, as_of=f.as_of,
        )

        if f.field == "contact":
            if contact is None and isinstance(f.value, dict):
                contact = ContactProfile(**{**f.value, "source": f.value.get("source", f.source)})
            prov.append(p)
        elif f.field == "tech":
            v = str(f.value)
            if v.lower() not in {t.lower() for t in profile.tech}:
                profile.tech.append(v)
            prov.append(p)
        elif f.field == "funding":
            profile.funding.append(Funding(**f.value))
            prov.append(p)
        elif f.field == "recent_news":
            profile.recent_news.append(NewsItem(**f.value))
            prov.append(p)
        elif f.field == "hiring_signals":
            profile.hiring_signals.append(HiringSignal(**f.value))
            prov.append(p)
        elif f.field in _SCALAR_FIELDS:
            if f.field in scalar_set:
                p.note = "corroborating (not applied)"
            else:
                setattr(profile, f.field, f.value)
                scalar_set.add(f.field)
            prov.append(p)
        else:
            p.note = "unmapped field, ignored"
            prov.append(p)

    profile.provenance = prov
    profile.sources = sorted({p.source for p in prov})
    return profile, contact


def recompute_completeness(
    profile: CompanyProfile, important: list[str] | None = None
) -> CompanyProfile:
    important = important or IMPORTANT_FIELDS
    known, unknown = [], []
    for field in important:
        value = getattr(profile, field, None)
        if value in (None, "", [], 0):
            unknown.append(field)
        else:
            known.append(field)
    profile.known_fields = known
    profile.unknown_fields = unknown
    return profile
