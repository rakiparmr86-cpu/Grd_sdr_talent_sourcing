from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from grd.db import init_db, make_engine, make_session_factory
from grd.models import Campaign, DocChunk, Lead, Suppression


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    init_db(engine)
    return engine, make_session_factory(engine)


def test_all_tables_created(session_factory):
    engine, _ = session_factory
    tables = set(inspect(engine).get_table_names())
    assert {
        "campaigns", "companies", "contacts", "research_runs", "leads",
        "outreach_drafts", "crm_syncs", "suppressions", "pipeline_runs", "doc_chunks",
        "candidates", "candidate_matches", "candidate_research_runs",
    } <= tables


def test_embedding_column_roundtrips_as_json_on_sqlite(session_factory):
    _, Session = session_factory
    vec = [0.1, 0.2, 0.3, 0.4]
    with Session.begin() as s:
        s.add(DocChunk(agent="ai_sdr", source_kind="voice_corpus",
                       source_ref="emails/best_1.md", ord=0, text="hi", embedding=vec))
    with Session() as s:
        row = s.query(DocChunk).one()
        assert row.embedding == vec
        assert row.text == "hi"


def test_suppression_is_unique_per_value_and_kind(session_factory):
    _, Session = session_factory
    with Session.begin() as s:
        s.add(Suppression(value="x@example.com", kind="email", reason="unsub"))
    with pytest.raises(IntegrityError):
        with Session.begin() as s:
            s.add(Suppression(value="x@example.com", kind="email", reason="dup"))


def test_lead_has_campaign_and_stage(session_factory):
    _, Session = session_factory
    with Session.begin() as s:
        c = Campaign(name="grd-q4-in", agent="ai_sdr", icp="grd_staffing")
        s.add(c)
        s.flush()
        s.add(Lead(company_id=1, campaign_id=c.id, icp="grd_staffing", stage="review"))
    with Session() as s:
        lead = s.query(Lead).one()
        assert lead.stage == "review"
        assert lead.campaign_id is not None
