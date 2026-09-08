from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from grd.compliance import (
    assert_ai_namespaced,
    email_footer,
    erase_subject,
    outreach_gate,
    outreach_posture,
    purge_expired_research,
    record_consent,
    redact_pii,
    region_for_country,
    validate_email_body,
)
from grd.db import init_db, make_engine, make_session_factory
from grd.models import (
    Company,
    ConsentEvent,
    Contact,
    DeletionRequest,
    Lead,
    ResearchRun,
    Suppression,
)


@pytest.fixture
def Session():
    engine = make_engine("sqlite://")
    init_db(engine)
    return make_session_factory(engine)


@pytest.mark.parametrize("iso,region", [
    ("DE", "EU"), ("fr", "EU"), ("GB", "UK"), ("uk", "UK"), ("NO", "EEA"),
    ("US", "US"), ("IN", "IN"), ("BR", "OTHER"), ("", "UNKNOWN"), (None, "UNKNOWN"),
])
def test_region_for_country(iso, region):
    assert region_for_country(iso) == region


@pytest.mark.parametrize("region,expected", [
    ("US", "allow"), ("OTHER", "allow"),
    ("EU", "manual_only"), ("UK", "manual_only"), ("EEA", "manual_only"),
    ("IN", "manual_only"), ("UNKNOWN", "manual_only"),
])
def test_outreach_posture_by_region(region, expected):
    assert outreach_posture(region)[0] == expected


def test_opt_in_overrides_region_and_opt_out_blocks():
    assert outreach_posture("EU", consent_status="opt_in")[0] == "allow"
    assert outreach_posture("US", consent_status="opt_out")[0] == "block"


def _campaign(**kw):
    base = dict(sender_identity="GRD Talent, Pvt Ltd", sender_address="1 MG Rd, Bengaluru 560001",
                unsubscribe_url="https://grd.example/u/abc", unsubscribe_mailto=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_outreach_gate_full(Session):
    with Session.begin() as s:
        s.add(Suppression(value="blocked.com", kind="domain", reason="x"))

    with Session() as s:
        # clean US lead, complete campaign -> allow
        d = outreach_gate(session=s, region="US", domain="good.com", campaign=_campaign())
        assert d.outcome == "allow"
        # EU -> manual_only even with a complete campaign
        assert outreach_gate(session=s, region="EU", domain="good.com",
                             campaign=_campaign()).outcome == "manual_only"
        # suppressed -> block
        assert outreach_gate(session=s, region="US", domain="blocked.com",
                             campaign=_campaign()).outcome == "block"
        # campaign missing physical address -> block
        assert outreach_gate(session=s, region="US", domain="good.com",
                             campaign=_campaign(sender_address=None)).outcome == "block"
        # automated LinkedIn -> block
        assert outreach_gate(session=s, region="US", domain="good.com", channel="linkedin",
                             mode="automated", campaign=_campaign()).outcome == "block"


def test_email_footer_and_body_validation():
    c = _campaign()
    footer = email_footer(c)
    assert "GRD Talent" in footer and "MG Rd" in footer and "Unsubscribe:" in footer

    ok = "Hi, GRD Talent here. ... To stop hearing from us, unsubscribe."
    assert validate_email_body(ok, c) == []
    bad = validate_email_body("Hey there, quick question about hiring.", c)
    assert "missing sender identity" in bad and "missing opt-out line" in bad


def test_redact_pii():
    out = redact_pii("reach me at jane.doe@acme.co or +1 (415) 555-2671 today")
    assert "jane.doe@acme.co" not in out and "555-2671" not in out
    assert "[email]" in out and "[phone]" in out


def test_assert_ai_namespaced():
    good = {"company": {"domain": "domain", "ai_fit_score": "score.value"},
            "contact": {"email": "contact.email"}}
    assert assert_ai_namespaced(good) == []
    bad = {"company": {"industry": "industry", "ai_x": "y"}}
    assert assert_ai_namespaced(bad) == ["company.industry"]


def test_erase_subject_by_domain_removes_rows_and_suppresses(Session):
    with Session.begin() as s:
        c = Company(domain="wipe.com", name="Wipe Inc")
        s.add(c)
        s.flush()
        s.add(ResearchRun(company_id=c.id, summary="x"))
        s.add(Contact(company_id=c.id, email="a@wipe.com", name="A"))
        s.add(Lead(company_id=c.id, icp="grd_staffing"))

    with Session.begin() as s:
        res = erase_subject(s, domain="wipe.com")
    assert res["status"] == "completed"

    with Session() as s:
        assert s.scalar(select(Company).where(Company.domain == "wipe.com")) is None
        assert list(s.scalars(select(Lead))) == []
        assert list(s.scalars(select(ResearchRun))) == []
        assert s.scalar(select(Suppression).where(Suppression.value == "wipe.com")) is not None
        assert s.scalar(select(DeletionRequest)).status == "completed"
        assert s.scalar(select(ConsentEvent)).action == "erasure"


def test_record_consent_opt_out_suppresses(Session):
    with Session.begin() as s:
        c = Company(domain="co.com")
        s.add(c)
        s.flush()
        s.add(Contact(company_id=c.id, email="p@co.com", name="P"))

    with Session.begin() as s:
        record_consent(s, email="p@co.com", action="opt_out", source="reply", note="asked to stop")

    with Session() as s:
        ct = s.scalar(select(Contact).where(Contact.email == "p@co.com"))
        assert ct.consent_status == "opt_out"
        assert s.scalar(select(Suppression).where(Suppression.value == "p@co.com")) is not None


def test_purge_expired_research(Session):
    with Session.begin() as s:
        c = Company(domain="r.com")
        s.add(c)
        s.flush()
        old = ResearchRun(company_id=c.id, summary="old")
        old.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)
        s.add(old)
        s.add(ResearchRun(company_id=c.id, summary="fresh"))

    with Session.begin() as s:
        n = purge_expired_research(s, retain_days=365)
    assert n == 1
    with Session() as s:
        assert [r.summary for r in s.scalars(select(ResearchRun))] == ["fresh"]
