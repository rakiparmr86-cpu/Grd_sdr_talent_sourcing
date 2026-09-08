"""Deterministic helpers - the "traditional automation" half of the pipeline.

Nothing in here may call an LLM. These are the string/rule/DB operations that
must be exact, cheap and auditable: normalization, dedup keys, payload hashing,
suppression checks, gate routing, and first-pass reply parsing. An LLM only
gets involved for what these provably cannot decide (see docs/ai-vs-traditional.md).
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from grd.models import Suppression

# --- normalization ---------------------------------------------------------

_STRIP_PREFIXES = ("https://", "http://", "www.")


def normalize_domain(raw: str) -> str:
    raw = (raw or "").strip().lower()
    for p in _STRIP_PREFIXES:
        if raw.startswith(p):
            raw = raw[len(p):]
    return raw.split("/")[0].split("?")[0].strip()


def normalize_email(raw: str) -> str:
    raw = (raw or "").strip().lower()
    m = re.search(r"<([^>]+)>", raw)          # "Foo Bar <a@b.com>" -> a@b.com
    if m:
        raw = m.group(1).strip()
    return raw


def email_domain(raw: str) -> str:
    e = normalize_email(raw)
    return e.rsplit("@", 1)[-1] if "@" in e else ""


# --- dedup / idempotency -------------------------------------------------

def company_key(domain: str) -> str:
    return normalize_domain(domain)


def contact_key(email: str) -> str:
    return normalize_email(email)


def payload_hash(payload: object) -> str:
    """Stable hash of a CRM payload - lets a sync skip a no-op write."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --- suppression / do-not-contact -------------------------------------

def is_suppressed(
    session: Session, *, email: str | None = None, domain: str | None = None
) -> bool:
    pairs: list[tuple[str, str]] = []
    if email:
        e = normalize_email(email)
        if e:
            pairs.append(("email", e))
        d = email_domain(e)
        if d:
            pairs.append(("domain", d))
    if domain:
        d = normalize_domain(domain)
        if d:
            pairs.append(("domain", d))
    if not pairs:
        return False
    conds = [
        (Suppression.kind == k) & (Suppression.value == v) for k, v in pairs
    ]
    return session.scalar(select(Suppression.id).where(or_(*conds)).limit(1)) is not None


# --- gate routing -----------------------------------------------------

def gate_a_route(score_value: float, threshold: float | None) -> str:
    """Score >= threshold auto-advances to Copy; below goes to a human. No LLM."""
    if threshold is None:
        return "human"
    return "auto" if float(score_value) >= float(threshold) else "human"


# --- reply parsing (first pass) -------------------------------------
# Handles the mechanical cases. `human_reply` / `unknown` are exactly what a
# later AI triage step would read for intent (interested / not now / question).

REPLY_CLASSES = (
    "bounce", "auto_reply", "out_of_office", "unsubscribe", "human_reply", "unknown",
)

_BOUNCE = re.compile(
    r"(mail delivery (failed|subsystem)|delivery status notification|undeliverable|"
    r"address not found|user unknown|mailbox (full|unavailable)|"
    r"550[ -]?5\.|recipient (address )?rejected|quota exceeded)",
    re.I,
)
_OOO = re.compile(
    r"(out of (the )?office|on (vacation|leave|holiday|annual leave|parental leave)|"
    r"away from my desk|back (in the office )?on |currently (away|unavailable))",
    re.I,
)
_AUTO = re.compile(
    r"(auto[- ]?reply|automatic reply|do not reply to this|this is an automated|"
    r"thank you for (contacting|your email)[.,! ].*we will)",
    re.I,
)
_UNSUB = re.compile(
    r"(unsubscribe|remove me from|take me off|stop (emailing|contacting) me|"
    r"opt[- ]?out|do not (contact|email) me|no longer wish to receive)",
    re.I,
)


def classify_reply(text: str, *, subject: str = "", headers: dict | None = None) -> str:
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    blob = f"{subject}\n{text or ''}"

    auto_submitted = headers.get("auto-submitted", "").lower()
    if auto_submitted and auto_submitted != "no":
        return "auto_reply"
    if "x-autoreply" in headers or "x-autorespond" in headers:
        return "auto_reply"
    ctype = headers.get("content-type", "").lower()
    if ctype.startswith("multipart/report") or "delivery-status" in ctype:
        return "bounce"

    if _BOUNCE.search(blob):
        return "bounce"
    if _UNSUB.search(blob):
        return "unsubscribe"
    if _OOO.search(blob):
        return "out_of_office"
    if _AUTO.search(blob):
        return "auto_reply"
    return "human_reply" if (text or "").strip() else "unknown"
