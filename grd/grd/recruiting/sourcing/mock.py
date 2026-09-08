from __future__ import annotations

import datetime as dt
import hashlib
import random

from grd.recruiting.schemas import CandidateProfile, RepoHighlight
from grd.recruiting.sourcing.base import CandidateSource

_SKILLS = [
    "python", "java", "go", "javascript", "typescript", "postgresql", "mysql",
    "aws", "gcp", "kubernetes", "docker", "kafka", "terraform", "react",
    "django", "fastapi", "spring", "rust", "php", "ruby", "graphql", "redis",
]
_LANGS = ["Python", "Go", "JavaScript", "TypeScript", "Java", "Rust", "Ruby", "C++"]
_HEADLINES = [
    "Senior Backend Engineer", "Full-stack Developer", "Platform Engineer",
    "Site Reliability Engineer", "Software Engineer", "Staff Engineer",
]
_COUNTRIES = ["IN", "US", "GB", "SG", "DE", "AU", "BR", "CA"]


class MockCandidateSource(CandidateSource):
    """Deterministic synthetic candidate derived from the handle. No network."""

    name = "mock"

    async def fetch(self, handle: str) -> CandidateProfile | None:
        rng = random.Random(int(hashlib.sha256(handle.encode()).hexdigest(), 16))

        skills = rng.sample(_SKILLS, k=rng.randint(2, 7))
        languages = rng.sample(_LANGS, k=rng.randint(1, 3))
        years = rng.choice([1, 2, 3, 5, 7, 9, 12]) if rng.random() < 0.85 else None
        public_repos = rng.choice([1, 3, 8, 15, 30, 60]) if rng.random() < 0.9 else None
        followers = rng.choice([0, 5, 20, 60, 150, 400]) if rng.random() < 0.9 else None
        total_stars = rng.choice([0, 10, 50, 200, 800]) if rng.random() < 0.8 else None

        last_active = None
        if rng.random() < 0.8:
            months_ago = rng.choice([1, 3, 7, 14, 28])
            last_active = (dt.date.today() - dt.timedelta(days=int(months_ago * 30.44))).isoformat()

        top_repos = [
            RepoHighlight(
                name=f"{handle}-{rng.choice(['api', 'toolkit', 'cli', 'lab'])}",
                url=f"https://github.com/{handle}/repo{i}",
                stars=rng.choice([0, 3, 12, 45, 180]),
                language=rng.choice(_LANGS),
                description="Sample project.",
            )
            for i in range(rng.randint(1, 3))
        ]

        return CandidateProfile(
            handle=handle,
            full_name=handle.replace("-", " ").replace("_", " ").title(),
            headline=rng.choice(_HEADLINES),
            location_country=rng.choice(_COUNTRIES),
            years_experience=years,
            skills=skills,
            languages=languages,
            public_repos=public_repos,
            followers=followers,
            total_stars=total_stars,
            top_repos=top_repos,
            portfolio_url=f"https://{handle}.dev" if rng.random() < 0.4 else None,
            github_url=f"https://github.com/{handle}",
            linkedin_url=f"https://www.linkedin.com/in/{handle}",  # synthetic
            last_active=last_active,
            hireable=rng.choice([True, False, None]),
            sources=[f"mock://github/{handle}"],
        )
