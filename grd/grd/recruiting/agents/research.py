from __future__ import annotations

from dataclasses import dataclass, field

from grd.llm.base import LLM
from grd.recruiting.schemas import CandidateProfile
from grd.recruiting.sourcing.base import (
    IMPORTANT_FIELDS,
    CandidateSource,
    merge_candidates,
    recompute_completeness,
)


@dataclass
class CandidateResearchResult:
    profile: CandidateProfile
    summary: str
    sources: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)


class CandidateResearchAgent:
    """Step 3a - assemble a factual candidate profile from allowed sources only."""

    def __init__(
        self,
        sources: list[CandidateSource],
        llm: LLM,
        important_fields: list[str] | None = None,
    ) -> None:
        self.sources = sources
        self.llm = llm
        self.important_fields = important_fields or IMPORTANT_FIELDS

    async def run(self, handle: str) -> CandidateResearchResult:
        handle = handle.strip().lstrip("@").rsplit("/", 1)[-1].lower()
        profile = CandidateProfile(handle=handle)
        used: list[str] = []
        sources: list[str] = []

        for source in self.sources:
            part = await source.fetch(handle)
            if part is None:
                continue
            used.append(source.name)
            profile = merge_candidates(profile, part)
            sources.extend(s for s in part.sources if s not in sources)

        profile.sources = sources
        profile = recompute_completeness(profile, self.important_fields)
        summary = await self.llm.summarize_candidate(profile)

        return CandidateResearchResult(
            profile=profile, summary=summary, sources=sources, sources_used=used
        )
