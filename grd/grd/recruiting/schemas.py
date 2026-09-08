from __future__ import annotations

from pydantic import BaseModel, Field


class RepoHighlight(BaseModel):
    name: str
    url: str | None = None
    stars: int = 0
    language: str | None = None
    description: str | None = None


class CandidateProfile(BaseModel):
    handle: str                       # github username / slug used to source
    full_name: str | None = None
    headline: str | None = None       # title or bio line
    location_country: str | None = None
    years_experience: int | None = None
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)   # programming languages seen
    public_repos: int | None = None
    followers: int | None = None
    total_stars: int | None = None
    top_repos: list[RepoHighlight] = Field(default_factory=list)
    portfolio_url: str | None = None
    github_url: str | None = None
    linkedin_url: str | None = None
    last_active: str | None = None     # ISO date string
    hireable: bool | None = None
    sources: list[str] = Field(default_factory=list)
    known_fields: list[str] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)


class ScoreComponent(BaseModel):
    name: str
    raw: float
    weight: float
    weighted: float
    basis: str


class CandidateScore(BaseModel):
    value: float
    deterministic_value: float
    llm_adjustment: float
    tier: str
    qualified: bool
    confidence: float
    components: list[ScoreComponent] = Field(default_factory=list)
    matched_requirements: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    rationale: str = ""


class ScoredCandidate(BaseModel):
    handle: str
    candidate_id: int | None = None
    rubric: str
    profile: CandidateProfile
    research_summary: str = ""
    sources_used: list[str] = Field(default_factory=list)
    score: CandidateScore


class CandidateScoreRequest(BaseModel):
    handles: list[str] = Field(..., min_length=1)
    rubric: str | None = None
