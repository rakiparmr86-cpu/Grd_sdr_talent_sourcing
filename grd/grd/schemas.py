from __future__ import annotations

from pydantic import BaseModel, Field


class Funding(BaseModel):
    round: str | None = None
    amount_usd: float | None = None
    announced_on: str | None = None  # ISO date string
    source: str | None = None


class HiringSignal(BaseModel):
    kind: str
    detail: str
    source: str | None = None


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_on: str | None = None
    source: str | None = None


class FactProvenance(BaseModel):
    """Where one field's value came from. Every non-empty field gets >= 1 of these."""

    field: str
    source: str
    capability: str
    retrieved_at: str
    as_of: str | None = None
    note: str | None = None


class ResearchIssue(BaseModel):
    # enrichment_miss | site_blocked | stale_data | capability_error
    #   | low_confidence | unsourced_fact
    kind: str
    detail: str
    capability: str | None = None
    source: str | None = None


class CompanyProfile(BaseModel):
    domain: str
    name: str | None = None
    description: str | None = None
    industry: str | None = None
    size_band: str | None = None
    employee_count: int | None = None
    hq_country: str | None = None
    tech: list[str] = Field(default_factory=list)
    funding: list[Funding] = Field(default_factory=list)
    open_roles: int | None = None
    headcount_growth_pct_6mo: float | None = None
    hiring_signals: list[HiringSignal] = Field(default_factory=list)
    recent_news: list[NewsItem] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    provenance: list[FactProvenance] = Field(default_factory=list)
    known_fields: list[str] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)


class ContactProfile(BaseModel):
    name: str | None = None
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    source: str | None = None


class ScoreComponent(BaseModel):
    name: str
    raw: float          # 0..1
    weight: float       # points out of 100
    weighted: float     # raw * weight
    basis: str


class LeadScore(BaseModel):
    value: float                 # 0..100 final
    deterministic_value: float   # 0..100 before LLM adjustment
    llm_adjustment: float        # bounded +/-
    tier: str                    # A | B | C | D
    qualified: bool
    confidence: float            # 0..1, share of important fields known
    components: list[ScoreComponent] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)
    missing_criteria: list[str] = Field(default_factory=list)
    rationale: str = ""


class ScoredLead(BaseModel):
    domain: str
    lead_id: int | None = None
    company: CompanyProfile
    contact: ContactProfile | None = None
    research_summary: str = ""
    providers_used: list[str] = Field(default_factory=list)
    capabilities_used: list[str] = Field(default_factory=list)
    issues: list[ResearchIssue] = Field(default_factory=list)
    gate_a: str = "human"          # deterministic route: "auto" | "human"
    score: LeadScore


class ScoreRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1)
    icp: str | None = None
    contact_hint: ContactProfile | None = None
