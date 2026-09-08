from __future__ import annotations

import asyncio
from time import perf_counter

from sqlalchemy import select

from grd.agents.research import ResearchAgent, ResearchResult
from grd.agents.scoring import ScoringAgent
from grd.classify import gate_a_route
from grd.config import Settings, get_settings
from grd.db import init_db, make_engine, make_session_factory
from grd.enrichment import build_providers
from grd.llm import build_llm
from grd.models import Company, Contact, Lead, PipelineRun, ResearchRun
from grd.schemas import ContactProfile, LeadScore, ScoredLead
from grd.scoring import load_icp
from grd.spec import AgentSpec


def _ms(t0: float) -> float:
    return round((perf_counter() - t0) * 1000, 1)


class Pipeline:
    """Research -> Scoring, with persistence.

    Driven by an AgentSpec (the `agents/<name>/` config folder): capability
    allow-list, ICP, prompts and gate thresholds all come from there. Falls back
    to plain settings when no spec folder exists.
    """

    def __init__(
        self, settings: Settings | None = None, spec: AgentSpec | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.spec = spec or AgentSpec.load_or_none(self.settings.agent, self.settings.agents_dir)
        self.engine = make_engine(self.settings.database_url)
        init_db(self.engine)
        self.Session = make_session_factory(self.engine)

        self._llm = build_llm(self.settings)
        self._providers = build_providers(self.settings)

        s = self.spec
        self.research = ResearchAgent(
            self._providers,
            self._llm,
            allowlist=(s.tools_allow() if s else None) or self.settings.research_capability_list,
            timeout=float(s.research_setting("timeout_seconds", self.settings.http_timeout)) if s
            else self.settings.http_timeout,
            retries=int(s.research_setting("retries", self.settings.research_retries)) if s
            else self.settings.research_retries,
            stale_after_months=int(
                s.research_setting("stale_after_months", self.settings.research_stale_after_months)
            ) if s else self.settings.research_stale_after_months,
            summary_prompt=s.summary_prompt() if s else None,
        )

        self._icp_cache: dict[str, dict] = {}
        self._scoring_cache: dict[str, ScoringAgent] = {}

    @property
    def _icp_dir(self):
        return self.spec.icp_dir() if self.spec else self.settings.icp_dir

    def _default_icp(self) -> str:
        return (self.spec.icp_name() if self.spec else None) or self.settings.icp

    def _scoring_for(self, icp_name: str) -> tuple[str, ScoringAgent]:
        icp_name = icp_name or self._default_icp()
        if icp_name not in self._scoring_cache:
            icp = self._icp_cache.setdefault(icp_name, load_icp(icp_name, self._icp_dir))
            self._scoring_cache[icp_name] = ScoringAgent(
                icp, self._llm,
                signal_prompt=self.spec.signal_prompt() if self.spec else None,
            )
        return icp_name, self._scoring_cache[icp_name]

    async def score_domain(
        self,
        domain: str,
        contact_hint: ContactProfile | None = None,
        icp: str | None = None,
    ) -> ScoredLead:
        icp_name, scoring = self._scoring_for(icp or self._default_icp())
        steps: list[dict] = []

        t0 = perf_counter()
        try:
            research = await self.research.run(domain, contact_hint)
        except Exception as exc:  # noqa: BLE001 - record the failed run, then re-raise
            steps.append({"step": "research", "status": "error", "ms": _ms(t0)})
            self._record_run(icp_name, domain, "error", steps, repr(exc))
            raise
        steps.append({
            "step": "research", "status": "ok", "ms": _ms(t0),
            "issues": len(research.issues),
            "capabilities": len(research.capabilities_used),
            "providers": len(research.providers_used),
        })

        t1 = perf_counter()
        score = await scoring.run(research.profile)
        steps.append({"step": "scoring", "status": "ok", "ms": _ms(t1)})

        lead_id = self._persist(icp_name, research, score)
        self._record_run(icp_name, domain, "ok", steps, None)

        threshold = self.spec.gate_a_threshold() if self.spec else None
        return ScoredLead(
            domain=research.profile.domain,
            lead_id=lead_id,
            company=research.profile,
            contact=research.contact,
            research_summary=research.summary,
            providers_used=research.providers_used,
            capabilities_used=research.capabilities_used,
            issues=research.issues,
            gate_a=gate_a_route(score.value, threshold),
            score=score,
        )

    def _record_run(
        self, icp_name: str, target: str, status: str, steps: list[dict], error: str | None
    ) -> None:
        """One pipeline_runs row per execution. Never breaks scoring if it fails."""
        try:
            with self.Session.begin() as s:
                s.add(PipelineRun(
                    vertical="sdr",
                    agent=self.settings.agent,
                    target=target,
                    status=status,
                    steps_json=steps,
                    cost_usd=0.0,   # mock/ollama are free; a hosted model would fill this
                    tokens=0,
                    error=error,
                ))
        except Exception:  # noqa: BLE001
            pass

    async def score_batch(
        self,
        domains: list[str],
        contact_hint: ContactProfile | None = None,
        icp: str | None = None,
        concurrency: int = 4,
    ) -> list[ScoredLead]:
        sem = asyncio.Semaphore(concurrency)

        async def _one(d: str) -> ScoredLead:
            async with sem:
                return await self.score_domain(d, contact_hint, icp)

        return list(await asyncio.gather(*(_one(d) for d in domains)))

    # --- persistence -----------------------------------------------------

    def _persist(self, icp_name: str, research: ResearchResult, score: LeadScore) -> int:
        profile = research.profile
        contact = research.contact
        with self.Session.begin() as s:
            company = s.scalar(select(Company).where(Company.domain == profile.domain))
            if company is None:
                company = Company(domain=profile.domain)
                s.add(company)
            company.name = profile.name or company.name
            company.industry = profile.industry or company.industry
            company.size_band = profile.size_band or company.size_band
            company.employee_count = profile.employee_count or company.employee_count
            company.hq_country = profile.hq_country or company.hq_country
            company.profile_json = profile.model_dump(mode="json")
            s.flush()

            s.add(ResearchRun(
                company_id=company.id,
                summary=research.summary,
                profile_json=profile.model_dump(mode="json"),
                sources_json=profile.sources,
                providers=",".join(research.providers_used),
                capabilities=",".join(research.capabilities_used),
                issues_json=[i.model_dump() for i in research.issues],
            ))

            contact_id = None
            if contact is not None and (contact.name or contact.email):
                row = Contact(
                    company_id=company.id, name=contact.name, title=contact.title,
                    email=contact.email, linkedin_url=contact.linkedin_url,
                    source=contact.source,
                )
                s.add(row)
                s.flush()
                contact_id = row.id

            lead = s.scalar(
                select(Lead).where(Lead.company_id == company.id, Lead.icp == icp_name)
            )
            if lead is None:
                lead = Lead(company_id=company.id, icp=icp_name)
                s.add(lead)
            lead.contact_id = contact_id or lead.contact_id
            lead.score_value = score.value
            lead.tier = score.tier
            lead.qualified = score.qualified
            lead.confidence = score.confidence
            lead.rationale = score.rationale
            lead.score_json = score.model_dump(mode="json")
            s.flush()
            return lead.id
