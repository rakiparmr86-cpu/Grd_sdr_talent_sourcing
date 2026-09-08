from __future__ import annotations

from grd.config import Settings
from grd.recruiting.sourcing.base import (
    CandidateSource,
    merge_candidates,
    recompute_completeness,
)
from grd.recruiting.sourcing.github import GitHubCandidateSource
from grd.recruiting.sourcing.mock import MockCandidateSource


def build_candidate_sources(settings: Settings) -> list[CandidateSource]:
    sources: list[CandidateSource] = []
    for name in settings.candidate_source_list:
        if name == "mock":
            sources.append(MockCandidateSource())
        elif name == "github":
            sources.append(
                GitHubCandidateSource(token=settings.github_token, timeout=settings.http_timeout)
            )
        else:
            raise ValueError(f"Unknown candidate source: {name!r}")
    if not sources:
        raise ValueError("GRD_CANDIDATE_SOURCES resolved to an empty list")
    return sources


__all__ = [
    "CandidateSource",
    "GitHubCandidateSource",
    "MockCandidateSource",
    "build_candidate_sources",
    "merge_candidates",
    "recompute_completeness",
]
