from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from grd.metrics import sdr_metrics
from grd.models import Company, Lead, ResearchRun
from grd.schemas import ScoredLead, ScoreRequest

router = APIRouter()


def _pipeline(request: Request):
    return request.app.state.pipeline


@router.get("/metrics", tags=["metrics"])
async def metrics(request: Request, icp: str | None = None) -> dict:
    pipe = _pipeline(request)
    threshold = pipe.spec.gate_a_threshold() if pipe.spec else None
    with pipe.Session() as s:
        return sdr_metrics(s, icp=icp, gate_a_threshold=threshold)


@router.post("/leads/score", response_model=list[ScoredLead], tags=["leads"])
async def score_leads(payload: ScoreRequest, request: Request) -> list[ScoredLead]:
    pipe = _pipeline(request)
    try:
        return await pipe.score_batch(
            payload.domains, contact_hint=payload.contact_hint, icp=payload.icp
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/leads", tags=["leads"])
async def list_leads(request: Request, qualified_only: bool = False) -> list[dict]:
    pipe = _pipeline(request)
    with pipe.Session() as s:
        stmt = (
            select(Lead, Company)
            .join(Company, Company.id == Lead.company_id)
            .order_by(Lead.score_value.desc())
        )
        if qualified_only:
            stmt = stmt.where(Lead.qualified.is_(True))
        rows = s.execute(stmt).all()
        return [
            {
                "lead_id": lead.id,
                "domain": company.domain,
                "name": company.name,
                "icp": lead.icp,
                "score": lead.score_value,
                "tier": lead.tier,
                "qualified": lead.qualified,
                "confidence": lead.confidence,
                "rationale": lead.rationale,
            }
            for lead, company in rows
        ]


@router.get("/leads/{lead_id}", tags=["leads"])
async def get_lead(lead_id: int, request: Request) -> dict:
    pipe = _pipeline(request)
    with pipe.Session() as s:
        row = s.execute(
            select(Lead, Company)
            .join(Company, Company.id == Lead.company_id)
            .where(Lead.id == lead_id)
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="lead not found")
        lead, company = row

        run = s.scalar(
            select(ResearchRun)
            .where(ResearchRun.company_id == company.id)
            .order_by(ResearchRun.created_at.desc())
        )
        return {
            "lead_id": lead.id,
            "domain": company.domain,
            "icp": lead.icp,
            "score": lead.score_json,
            "company_profile": company.profile_json,
            "research": {
                "summary": run.summary if run else "",
                "providers": run.providers if run else "",
                "capabilities": run.capabilities if run else "",
                "issues": run.issues_json if run else [],
                "provenance": (company.profile_json or {}).get("provenance", []),
            },
        }
