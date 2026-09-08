from __future__ import annotations

from collections import Counter

import httpx

from grd.recruiting.schemas import CandidateProfile, RepoHighlight
from grd.recruiting.sourcing.base import CandidateSource

_API = "https://api.github.com"
_UA = "GRD-AI-SDR/0.1 (+research bot)"

# best-effort free-text location -> ISO country
_LOCATION_HINTS = {
    "IN": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai"],
    "US": ["united states", "usa", "u.s.", "san francisco", "new york", "seattle", "austin", "boston"],
    "GB": ["united kingdom", "u.k.", "england", "london", "manchester", "scotland"],
    "SG": ["singapore"],
    "DE": ["germany", "berlin", "munich", "hamburg"],
    "AE": ["uae", "united arab emirates", "dubai", "abu dhabi"],
    "AU": ["australia", "sydney", "melbourne"],
    "CA": ["canada", "toronto", "vancouver", "montreal"],
}


class GitHubCandidateSource(CandidateSource):
    """Reads a candidate's PUBLIC GitHub profile + repos. Real HTTP, best effort.

    Only touches api.github.com. Anything LinkedIn/portfolio beyond the user's own
    `blog` URL must come from a licensed provider added alongside this one.
    """

    name = "github"

    def __init__(self, token: str | None = None, timeout: float = 10.0) -> None:
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": _UA, "Accept": "application/vnd.github+json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def fetch(self, handle: str) -> CandidateProfile | None:
        handle = handle.strip().lstrip("@").rsplit("/", 1)[-1]
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, headers=self._headers(), follow_redirects=True
            ) as client:
                user_resp = await client.get(f"{_API}/users/{handle}")
                if user_resp.status_code != 200:
                    return None
                user = user_resp.json()

                repos_resp = await client.get(
                    f"{_API}/users/{handle}/repos",
                    params={"per_page": 100, "sort": "pushed", "type": "owner"},
                )
                repos = repos_resp.json() if repos_resp.status_code == 200 else []
                if not isinstance(repos, list):
                    repos = []

            return _build_profile(handle, user, repos)
        except Exception:  # noqa: BLE001 - best effort
            return None


def _build_profile(handle: str, user: dict, repos: list[dict]) -> CandidateProfile:
    langs = Counter()
    topics: set[str] = set()
    total_stars = 0
    last_pushed: str | None = None
    highlights: list[RepoHighlight] = []

    for r in repos:
        if r.get("fork"):
            continue
        if r.get("language"):
            langs[r["language"]] += 1
        for t in r.get("topics", []) or []:
            topics.add(t.lower())
        total_stars += int(r.get("stargazers_count", 0) or 0)
        pushed = r.get("pushed_at")
        if pushed and (last_pushed is None or pushed > last_pushed):
            last_pushed = pushed

    for r in sorted(repos, key=lambda x: x.get("stargazers_count", 0) or 0, reverse=True)[:5]:
        highlights.append(
            RepoHighlight(
                name=r.get("name", "?"),
                url=r.get("html_url"),
                stars=int(r.get("stargazers_count", 0) or 0),
                language=r.get("language"),
                description=(r.get("description") or "")[:200] or None,
            )
        )

    languages = [lang for lang, _ in langs.most_common()]
    skills = sorted({*(t for t in topics), *(l.lower() for l in languages)})

    return CandidateProfile(
        handle=handle,
        full_name=user.get("name"),
        headline=user.get("bio") or user.get("company"),
        location_country=_guess_country(user.get("location")),
        years_experience=None,  # not derivable from GitHub; a resume/LinkedIn source fills this
        skills=skills,
        languages=languages,
        public_repos=user.get("public_repos"),
        followers=user.get("followers"),
        total_stars=total_stars or None,
        top_repos=highlights,
        portfolio_url=(user.get("blog") or None),
        github_url=user.get("html_url") or f"https://github.com/{handle}",
        linkedin_url=None,
        last_active=(last_pushed or user.get("updated_at") or "")[:10] or None,
        hireable=user.get("hireable"),
        sources=[f"{_API}/users/{handle}"],
    )


def _guess_country(location: str | None) -> str | None:
    if not location:
        return None
    low = location.lower()
    for code, hints in _LOCATION_HINTS.items():
        if any(h in low for h in hints):
            return code
    return None
