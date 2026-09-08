from __future__ import annotations

import datetime as dt
import hashlib
import random

from grd.enrichment.base import EnrichmentProvider
from grd.enrichment.capabilities import (
    COMPANY_LOOKUP,
    CONTACT_LOOKUP,
    FUNDING_LOOKUP,
    NEWS_SEARCH,
    TECH_LOOKUP,
    CapabilityResult,
    Fact,
)
from grd.schemas import ContactProfile

_INDUSTRIES = [
    "software", "fintech", "saas", "e-commerce", "healthtech", "edtech",
    "logistics technology", "cybersecurity", "artificial intelligence",
    "manufacturing", "retail", "hospitality", "staffing and recruiting",
]
_SIZE_BANDS = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001+"]
_EMPLOYEES = {
    "1-10": 6, "11-50": 30, "51-200": 120, "201-500": 350,
    "501-1000": 750, "1001-5000": 2500, "5001+": 8000,
}
_COUNTRIES = ["IN", "US", "AE", "GB", "SG", "DE", "AU", "CA", "FR", "BR"]
_TECH = ["React", "Python", "AWS", "Kubernetes", "PostgreSQL", "Kafka", "Go", "Snowflake"]
_ROUNDS = ["Pre-seed", "Seed", "Series A", "Series B", "Series C"]


class MockEnrichmentProvider(EnrichmentProvider):
    """Deterministic synthetic data derived from the domain. No network.

    Supports every capability except web_fetch (that is the `web` provider's job).
    """

    name = "mock"
    capabilities = {
        COMPANY_LOOKUP, CONTACT_LOOKUP, FUNDING_LOOKUP, TECH_LOOKUP, NEWS_SEARCH,
    }

    async def call(
        self, capability: str, *, domain: str, contact_hint: ContactProfile | None = None
    ) -> CapabilityResult:
        rng = random.Random(int(hashlib.sha256(f"{domain}:{capability}".encode()).hexdigest(), 16))
        src = f"mock://{capability}/{domain}"
        res = CapabilityResult()

        if capability == COMPANY_LOOKUP:
            name = domain.split(".")[0].replace("-", " ").title()
            industry = rng.choice(_INDUSTRIES)
            size_band = rng.choice(_SIZE_BANDS)
            hq = rng.choice(_COUNTRIES)
            growth = rng.choice([-5, 0, 4, 9, 15, 25, 40]) if rng.random() < 0.7 else None
            res.facts += [
                Fact("name", name, src, capability),
                Fact("description", f"{name} operates in {industry}.", src, capability),
                Fact("industry", industry, src, capability),
                Fact("size_band", size_band, src, capability),
                Fact("employee_count", _EMPLOYEES[size_band], src, capability),
                Fact("hq_country", hq, src, capability),
            ]
            if growth is not None:
                res.facts.append(Fact("headcount_growth_pct_6mo", float(growth), src, capability))

        elif capability == CONTACT_LOOKUP:
            first = rng.choice(["Alex", "Priya", "Sam", "Jordan", "Neha"])
            last = rng.choice(["Sharma", "Khan", "Lee", "Patel", "Roy"])
            res.facts.append(Fact(
                "contact",
                {
                    "name": f"{first} {last}",
                    "title": rng.choice(["Head of Talent", "VP Engineering", "CEO", "HR Director"]),
                    "email": None,
                    "linkedin_url": None,
                    "source": src,
                },
                src, capability,
            ))

        elif capability == FUNDING_LOOKUP:
            if rng.random() < 0.6:
                months_ago = rng.choice([2, 5, 8, 11, 14, 20, 30])
                announced = (dt.date.today() - dt.timedelta(days=int(months_ago * 30.44))).isoformat()
                res.facts.append(Fact(
                    "funding",
                    {
                        "round": rng.choice(_ROUNDS),
                        "amount_usd": float(rng.choice([1.5e6, 5e6, 12e6, 30e6, 75e6])),
                        "announced_on": announced,
                        "source": src,
                    },
                    src, capability, as_of=announced,
                ))

        elif capability == TECH_LOOKUP:
            for t in rng.sample(_TECH, k=rng.randint(2, 5)):
                res.facts.append(Fact("tech", t, src, capability))

        elif capability == NEWS_SEARCH:
            if rng.random() < 0.5:
                published = (dt.date.today() - dt.timedelta(days=rng.choice([20, 90, 300, 800]))).isoformat()
                name = domain.split(".")[0].title()
                res.facts.append(Fact(
                    "recent_news",
                    {"title": f"{name} expands operations", "published_on": published, "source": src},
                    src, capability, as_of=published,
                ))

        return res
