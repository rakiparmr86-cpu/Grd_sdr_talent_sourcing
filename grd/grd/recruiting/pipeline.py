from __future__ import annotations

import asyncio

from sqlalchemy import select

from grd.config import Settings, get_settings
from grd.db import init_db, make_engine, make_session_factory
from grd.llm import build_llm
from grd.recruiting.agents.research import CandidateResearchAgent
from grd.recruiting.agents.scoring import CandidateScoringAgent
from grd.recruiting.models import Candidate, CandidateMatch, CandidateResearchRun
from grd.recruiting.rubrics import load_rubric
from grd.recruiting.schemas import CandidateProfile, CandidateScore, ScoredCandidate
from grd.recruiting.sourcing import build_candidate_sources


class RecruitingPipeline:
    """Candidate research -> fit scoring, with persistence. Talent-sourcing step."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = make_engine(self.settings.database_url)
        init_db(self.engine)
        self.Session = make_session_factory(self.engine)

        self._llm = build_llm(self.settings)
        self._sources = build_candidate_sources(self.settings)
        self.research = CandidateResearchAgent(self._sources, self._llm)

        self._rubric_cache: dict[str, dict] = {}
        self._scoring_cache: dict[str, CandidateScoringAgent] = {}

    def _scoring_for(self, rubric_name: str) -> tuple[str, CandidateScoringAgent]:
        rubric_name = rubric_name or self.settings.rubric
        if rubric_name not in self._scoring_cache:
            rubric = self._rubric_cache.setdefault(
                rubric_name, load_rubric(rubric_name, self.settings.rubric_dir)
            )
            self._scoring_cache[rubric_name] = CandidateScoringAgent(rubric, self._llm)
        return rubric_name, self._scoring_cache[rubric_name]

    async def score_handle(self, handle: str, rubric: str | None = None) -> ScoredCandidate:
        rubric_name, scoring = self._scoring_for(rubric or self.settings.rubric)
        research = await self.research.run(handle)
        score = await scoring.run(research.profile)
        candidate_id = self._persist(
            rubric_name, research.profile, score, research.summary,
            research.sources, research.sources_used,
        )
        return ScoredCandidate(
            handle=research.profile.handle,
            candidate_id=candidate_id,
            rubric=rubric_name,
            profile=research.profile,
            research_summary=research.summary,
            sources_used=research.sources_used,
            score=score,
        )

    async def score_batch(
        self, handles: list[str], rubric: str | None = None, concurrency: int = 4
    ) -> list[ScoredCandidate]:
        sem = asyncio.Semaphore(concurrency)

        async def _one(h: str) -> ScoredCandidate:
            async with sem:
                return await self.score_handle(h, rubric)

        return list(await asyncio.gather(*(_one(h) for h in handles)))

    # --- persistence ---------------------------------------------------

    def _persist(
        self,
        rubric_name: str,
        profile: CandidateProfile,
        score: CandidateScore,
        summary: str,
        sources: list[str],
        sources_used: list[str],
    ) -> int:
        with self.Session.begin() as s:
            row = s.scalar(select(Candidate).where(Candidate.handle == profile.handle))
            if row is None:
                row = Candidate(handle=profile.handle)
                s.add(row)
            row.full_name = profile.full_name or row.full_name
            row.headline = profile.headline or row.headline
            row.location_country = profile.location_country or row.location_country
            row.github_url = profile.github_url or row.github_url
            row.linkedin_url = profile.linkedin_url or row.linkedin_url
            row.profile_json = profile.model_dump(mode="json")
            s.flush()

            s.add(CandidateResearchRun(
                candidate_id=row.id,
                summary=summary,
                profile_json=profile.model_dump(mode="json"),
                sources_json=sources,
                sources_used=",".join(sources_used),
            ))

            match = s.scalar(
                select(CandidateMatch).where(
                    CandidateMatch.candidate_id == row.id,
                    CandidateMatch.rubric == rubric_name,
                )
            )
            if match is None:
                match = CandidateMatch(candidate_id=row.id, rubric=rubric_name)
                s.add(match)
            match.score_value = score.value
            match.tier = score.tier
            match.qualified = score.qualified
            match.confidence = score.confidence
            match.rationale = score.rationale
            match.score_json = score.model_dump(mode="json")
            s.flush()
            return row.id
