from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from grd.dbtypes import Embedding


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# SDR core: campaign -> company -> contact -> lead, with research + outreach
# ---------------------------------------------------------------------------

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    agent: Mapped[str] = mapped_column(String(64), default="ai_sdr")
    icp: Mapped[str] = mapped_column(String(64), default="grd_staffing")
    status: Mapped[str] = mapped_column(String(16), default="active")   # active|paused|done
    offer: Mapped[str | None] = mapped_column(Text)
    sender_identity: Mapped[str | None] = mapped_column(String(255))    # outreach compliance
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(128))
    size_band: Mapped[str | None] = mapped_column(String(32))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    hq_country: Mapped[str | None] = mapped_column(String(8))
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(512))
    source: Mapped[str | None] = mapped_column(String(128))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    summary: Mapped[str] = mapped_column(Text, default="")
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sources_json: Mapped[list] = mapped_column(JSON, default=list)
    providers: Mapped[str] = mapped_column(String(128), default="")
    capabilities: Mapped[str] = mapped_column(String(256), default="")
    issues_json: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    icp: Mapped[str] = mapped_column(String(64), default="grd_staffing")
    stage: Mapped[str] = mapped_column(String(24), default="scored")
    # sourced -> researched -> scored -> drafting -> review -> crm -> done
    score_value: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[str] = mapped_column(String(4), default="D")
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    score_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Downstream steps (2.3 Copy, 2.4 CRM) - schema defined now, wired later
# ---------------------------------------------------------------------------

class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    channel: Mapped[str] = mapped_column(String(16), default="email")      # email|linkedin
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    personalization_json: Mapped[dict] = mapped_column(JSON, default=dict)  # facts referenced
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # draft -> approved | edited | rejected -> sent
    approver: Mapped[str | None] = mapped_column(String(128))
    edit_diff: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class CrmSync(Base):
    __tablename__ = "crm_syncs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    crm: Mapped[str] = mapped_column(String(24), default="hubspot")
    crm_object_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(48), default="upsert")
    payload_hash: Mapped[str] = mapped_column(String(64), default="")     # skip no-op writes
    result: Mapped[str] = mapped_column(String(255), default="")          # ok | error:<msg>
    synced_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class Suppression(Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("value", "kind", name="uq_suppression_value_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(255), index=True)           # email or domain
    kind: Mapped[str] = mapped_column(String(16), default="email")        # email|domain
    reason: Mapped[str] = mapped_column(String(255), default="")
    added_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


# ---------------------------------------------------------------------------
# Observability - one row per pipeline execution (both verticals)
# ---------------------------------------------------------------------------

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vertical: Mapped[str] = mapped_column(String(16), default="sdr")      # sdr|recruiting
    agent: Mapped[str] = mapped_column(String(64), default="ai_sdr")
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    target: Mapped[str] = mapped_column(String(255), default="")         # domain or handle
    status: Mapped[str] = mapped_column(String(16), default="ok")        # ok|error
    steps_json: Mapped[list] = mapped_column(JSON, default=list)         # [{step, ms, status}]
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


# ---------------------------------------------------------------------------
# RAG - voice corpus / knowledge chunks for the Copy agent (step 2.3)
# `embedding` is vector(384) on Postgres+pgvector, JSON list on SQLite
# ---------------------------------------------------------------------------

class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent: Mapped[str] = mapped_column(String(64), default="ai_sdr", index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="voice_corpus")
    source_ref: Mapped[str] = mapped_column(String(512), default="")
    ord: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list | None] = mapped_column(Embedding(), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
