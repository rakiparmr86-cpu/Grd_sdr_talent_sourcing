from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from grd.recruiting.models import Candidate, CandidateMatch
from grd.recruiting.schemas import CandidateScoreRequest, ScoredCandidate

router = APIRouter()


def _pipeline(request: Request):
    return request.app.state.recruiting_pipeline


@router.post("/candidates/score", response_model=list[ScoredCandidate], tags=["candidates"])
async def score_candidates(payload: CandidateScoreRequest, request: Request) -> list[ScoredCandidate]:
    try:
        return await _pipeline(request).score_batch(payload.handles, rubric=payload.rubric)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates", tags=["candidates"])
async def list_candidates(request: Request, qualified_only: bool = False) -> list[dict]:
    pipe = _pipeline(request)
    with pipe.Session() as s:
        stmt = (
            select(CandidateMatch, Candidate)
            .join(Candidate, Candidate.id == CandidateMatch.candidate_id)
            .order_by(CandidateMatch.score_value.desc())
        )
        if qualified_only:
            stmt = stmt.where(CandidateMatch.qualified.is_(True))
        return [
            {
                "candidate_id": cand.id,
                "handle": cand.handle,
                "full_name": cand.full_name,
                "rubric": match.rubric,
                "score": match.score_value,
                "tier": match.tier,
                "qualified": match.qualified,
                "confidence": match.confidence,
                "pipeline_stage": match.pipeline_stage,
                "rationale": match.rationale,
            }
            for match, cand in s.execute(stmt).all()
        ]


@router.get("/candidates/{candidate_id}", tags=["candidates"])
async def get_candidate(candidate_id: int, request: Request) -> dict:
    pipe = _pipeline(request)
    with pipe.Session() as s:
        row = s.execute(
            select(CandidateMatch, Candidate)
            .join(Candidate, Candidate.id == CandidateMatch.candidate_id)
            .where(Candidate.id == candidate_id)
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="candidate not found")
        match, cand = row
        return {
            "candidate_id": cand.id,
            "handle": cand.handle,
            "rubric": match.rubric,
            "score": match.score_json,
            "candidate_profile": cand.profile_json,
        }
