from __future__ import annotations

import pytest

from grd.classify import (
    classify_reply,
    company_key,
    email_domain,
    gate_a_route,
    is_suppressed,
    normalize_domain,
    normalize_email,
    payload_hash,
)
from grd.db import init_db, make_engine, make_session_factory
from grd.models import Suppression


@pytest.mark.parametrize("raw,expected", [
    ("https://www.Example.com/careers", "example.com"),
    ("  HTTP://Foo.IO  ", "foo.io"),
    ("bar.co.uk?utm=x", "bar.co.uk"),
    ("already.clean", "already.clean"),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Foo Bar <A@B.com>", "a@b.com"),
    ("  USER@Example.COM ", "user@example.com"),
])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected
    assert email_domain(raw) == expected.split("@")[1]


def test_dedup_keys_are_normalized():
    assert company_key("HTTPS://WWW.X.com/") == "x.com"


def test_payload_hash_is_order_independent_and_stable():
    a = payload_hash({"b": 2, "a": 1})
    b = payload_hash({"a": 1, "b": 2})
    assert a == b == payload_hash({"a": 1, "b": 2})
    assert a != payload_hash({"a": 1, "b": 3})


def test_gate_a_route_is_pure_threshold():
    assert gate_a_route(80, 62) == "auto"
    assert gate_a_route(62, 62) == "auto"
    assert gate_a_route(61.9, 62) == "human"
    assert gate_a_route(99, None) == "human"   # no threshold -> always human


@pytest.mark.parametrize("text,subject,headers,expected", [
    ("Your message could not be delivered: 550 5.1.1 user unknown", "", {}, "bounce"),
    ("", "Undeliverable: Intro", {}, "bounce"),
    ("", "x", {"Content-Type": "multipart/report; report-type=delivery-status"}, "bounce"),
    ("I am out of the office until Monday and will reply then.", "", {}, "out_of_office"),
    ("Automatic reply: I have received your email.", "", {}, "auto_reply"),
    ("hi", "", {"Auto-Submitted": "auto-replied"}, "auto_reply"),
    ("Please unsubscribe me from this list.", "", {}, "unsubscribe"),
    ("Do not email me again.", "", {}, "unsubscribe"),
    ("Thanks, this looks interesting - can we talk Thursday?", "", {}, "human_reply"),
    ("", "", {}, "unknown"),
])
def test_classify_reply(text, subject, headers, expected):
    assert classify_reply(text, subject=subject, headers=headers) == expected


def test_is_suppressed_checks_email_and_its_domain():
    engine = make_engine("sqlite://")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session.begin() as s:
        s.add(Suppression(value="blocked.com", kind="domain", reason="client request"))
        s.add(Suppression(value="ceo@vip.com", kind="email", reason="asked to stop"))

    with Session() as s:
        assert is_suppressed(s, email="anyone@blocked.com") is True     # domain match
        assert is_suppressed(s, domain="www.Blocked.com") is True       # normalized
        assert is_suppressed(s, email="CEO@vip.com") is True            # exact email
        assert is_suppressed(s, email="someone@fine.com") is False
        assert is_suppressed(s) is False
