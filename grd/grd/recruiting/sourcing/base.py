from __future__ import annotations

import abc

from grd.recruiting.schemas import CandidateProfile

IMPORTANT_FIELDS = [
    "skills",
    "years_experience",
    "location_country",
    "public_repos",
    "last_active",
]

_SCALAR_FIELDS = [
    "full_name",
    "headline",
    "location_country",
    "years_experience",
    "public_repos",
    "followers",
    "total_stars",
    "portfolio_url",
    "github_url",
    "linkedin_url",
    "last_active",
    "hireable",
]
_LIST_FIELDS = ["skills", "languages", "top_repos", "sources"]


class CandidateSource(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def fetch(self, handle: str) -> CandidateProfile | None:
        """Return a partial CandidateProfile for the handle, or None."""


def merge_candidates(
    base: CandidateProfile, incoming: CandidateProfile | None
) -> CandidateProfile:
    if incoming is None:
        return base
    data = base.model_dump()
    inc = incoming.model_dump()

    for field in _SCALAR_FIELDS:
        if data.get(field) in (None, "") and inc.get(field) not in (None, ""):
            data[field] = inc[field]

    for field in _LIST_FIELDS:
        merged = list(data.get(field) or [])
        for item in inc.get(field) or []:
            if item not in merged:
                merged.append(item)
        data[field] = merged

    return CandidateProfile(**data)


def recompute_completeness(
    profile: CandidateProfile, important: list[str] | None = None
) -> CandidateProfile:
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
