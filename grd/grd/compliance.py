"""Compliance controls - enforced in code, not left to a checklist. No LLM.

Covers: region classification, the pre-send outreach gate (suppression + geo +
campaign completeness + LinkedIn ToS), the required email footer / body checks,
PII redaction, CRM AI-namespace guard, retention purge, and data-subject erasure
with an audit trail.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from grd.classify import email_domain, is_suppressed, normalize_domain, normalize_email
from grd.models import (
    Company,
    ConsentEvent,
    Contact,
    DeletionRequest,
    Lead,
    ResearchRun,
    Suppression,
)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- region classification ----------------------------------------------

_EU27 = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}
_EEA_EXTRA = {"IS", "LI", "NO"}
_UK = {"GB", "UK"}

# regions where automated cold email needs prior consent -> route to a human
MANUAL_ONLY_REGIONS = {"EU", "EEA", "UK", "IN", "UNKNOWN"}


def region_for_country(iso2: str | None) -> str:
    c = (iso2 or "").strip().upper()
    if not c:
        return "UNKNOWN"
    if c in _UK:
        return "UK"
    if c in _EU27:
        return "EU"
    if c in _EEA_EXTRA:
        return "EEA"
    if c == "US":
        return "US"
    if c == "IN":
        return "IN"
    return "OTHER"


# --- outreach gate ------------------------------------------------------

@dataclass
class ComplianceDecision:
    outcome: str                       # "allow" | "manual_only" | "block"
    region: str
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"


_CAMPAIGN_REQUIRED = ("sender_identity", "sender_address")


def campaign_outreach_gaps(campaign: object) -> list[str]:
    missing = [f for f in _CAMPAIGN_REQUIRED if not getattr(campaign, f, None)]
    if not (getattr(campaign, "unsubscribe_url", None) or getattr(campaign, "unsubscribe_mailto", None)):
        missing.append("unsubscribe_url|unsubscribe_mailto")
    return missing


def outreach_posture(region: str, consent_status: str = "none") -> tuple[str, list[str]]:
    """Region-only view: would automated outreach be permitted in principle?

    Cheap, no DB. The full check is `outreach_gate`.
    """
    if consent_status == "opt_out":
        return "block", ["contact opted out"]
    if consent_status == "opt_in":
        return "allow", ["explicit opt-in on file"]
    if region in MANUAL_ONLY_REGIONS:
        law = {
            "EU": "GDPR + national ePrivacy", "EEA": "GDPR + ePrivacy",
            "UK": "UK GDPR + PECR", "IN": "DPDP Act", "UNKNOWN": "region unverifiable",
        }[region]
        return "manual_only", [f"{region}: {law} - cold automated email needs prior consent; route to a human"]
    return "allow", [f"{region}: automated cold B2B email permitted with opt-out + sender identity"]


def outreach_gate(
    *,
    session: Session | None,
    region: str,
    email: str | None = None,
    domain: str | None = None,
    channel: str = "email",
    mode: str = "automated",
    campaign: object | None = None,
    consent_status: str = "none",
) -> ComplianceDecision:
    # hard blocks first
    if session is not None and is_suppressed(session, email=email, domain=domain):
        return ComplianceDecision("block", region, ["on the suppression / do-not-contact list"])
    if channel == "linkedin" and mode == "automated":
        return ComplianceDecision(
            "block", region,
            ["automated LinkedIn messaging violates their ToS - human-in-the-loop only"],
        )
    if campaign is not None:
        gaps = campaign_outreach_gaps(campaign)
        if gaps:
            return ComplianceDecision("block", region, [f"campaign missing: {', '.join(gaps)}"])

    outcome, reasons = outreach_posture(region, consent_status)
    return ComplianceDecision(outcome, region, reasons)


# --- email content requirements -------------------------------------

MAX_OUTREACH_WORDS = 200


def email_footer(campaign: object) -> str:
    unsub = getattr(campaign, "unsubscribe_url", None) or (
        f"mailto:{campaign.unsubscribe_mailto}" if getattr(campaign, "unsubscribe_mailto", None) else ""
    )
    lines = [
        getattr(campaign, "sender_identity", "") or "",
        getattr(campaign, "sender_address", "") or "",
        f"Unsubscribe: {unsub}" if unsub else "",
    ]
    return "\n".join(x for x in lines if x)


def validate_email_body(body: str, campaign: object) -> list[str]:
    issues: list[str] = []
    b = (body or "").lower()
    ident = (getattr(campaign, "sender_identity", "") or "").strip()
    if ident and ident.lower() not in b and ident.split()[0].lower() not in b:
        issues.append("missing sender identity")
    if not any(k in b for k in ("unsubscribe", "opt out", "opt-out")):
        issues.append("missing opt-out line")
    if len((body or "").split()) > MAX_OUTREACH_WORDS:
        issues.append(f"over {MAX_OUTREACH_WORDS} words")
    return issues


# --- PII redaction (defense-in-depth before any text hits an LLM) ---

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")


def redact_pii(text: str) -> str:
    text = _EMAIL_RE.sub("[email]", text or "")
    return _PHONE_RE.sub("[phone]", text)


# --- CRM AI-namespace guard --------------------------------------

AI_PROP_PREFIX = "ai_"
_MATCH_PROPS = {"domain", "name", "email", "full_name", "title", "body", "subject"}


def ai_property_name(field: str) -> str:
    return field if field.startswith(AI_PROP_PREFIX) else AI_PROP_PREFIX + field


def assert_ai_namespaced(field_map: dict) -> list[str]:
    """CRM target properties that would clobber a human-maintained field."""
    bad: list[str] = []
    for section in ("company", "contact", "note"):
        for target in (field_map.get(section) or {}):
            if target not in _MATCH_PROPS and not target.startswith(AI_PROP_PREFIX):
                bad.append(f"{section}.{target}")
    return bad


# --- retention + data-subject rights -----------------------------

def purge_expired_research(session: Session, retain_days: int) -> int:
    cutoff = _utcnow() - dt.timedelta(days=retain_days)
    rows = list(session.scalars(select(ResearchRun).where(ResearchRun.created_at < cutoff)))
    for r in rows:
        session.delete(r)
    return len(rows)


def erase_subject(
    session: Session, *, email: str | None = None, domain: str | None = None,
    reason: str = "data subject erasure request",
) -> dict:
    """Delete/anonymize everything tied to a domain or email, suppress it so it
    can't be re-ingested, and log the request + a consent event.
    """
    deleted: dict[str, int] = {}
    req = DeletionRequest(
        subject=(email or domain or ""),
        kind=("email" if email else "domain"),
        reason=reason,
        status="received",
        requested_at=_utcnow(),
    )
    session.add(req)

    if domain:
        d = normalize_domain(domain)
        company = session.scalar(select(Company).where(Company.domain == d))
        if company:
            leads = list(session.scalars(select(Lead).where(Lead.company_id == company.id)))
            for lead in leads:
                session.delete(lead)
            for rr in session.scalars(select(ResearchRun).where(ResearchRun.company_id == company.id)):
                session.delete(rr)
            for ct in session.scalars(select(Contact).where(Contact.company_id == company.id)):
                session.delete(ct)
            session.delete(company)
            deleted = {"leads": len(leads), "company": 1}
        _suppress(session, d, "domain", reason)

    if email:
        e = normalize_email(email)
        contacts = list(session.scalars(select(Contact).where(Contact.email == e)))
        for ct in contacts:
            ct.name = None
            ct.email = None
            ct.linkedin_url = None
            ct.title = None
        deleted["contacts_anonymized"] = len(contacts)
        _suppress(session, e, "email", reason)
        dd = email_domain(e)
        if dd:
            _suppress(session, dd, "domain", reason)

    session.add(ConsentEvent(
        subject=(email or domain or ""), kind=("email" if email else "domain"),
        action="erasure", source="erase_subject", note=reason, created_at=_utcnow(),
    ))
    req.status = "completed"
    req.deleted_json = deleted
    req.completed_at = _utcnow()
    return {"status": "completed", "deleted": deleted}


def record_consent(
    session: Session, *, email: str, action: str, source: str, note: str = ""
) -> None:
    """action: opt_in | opt_out | preference. Updates the contact + logs the event."""
    e = normalize_email(email)
    for ct in session.scalars(select(Contact).where(Contact.email == e)):
        ct.consent_status = {"opt_in": "opt_in", "opt_out": "opt_out"}.get(action, ct.consent_status)
        ct.consent_source = source
        ct.consent_at = _utcnow()
    if action == "opt_out":
        _suppress(session, e, "email", note or "opt-out")
    session.add(ConsentEvent(
        subject=e, kind="email", action=action, source=source, note=note, created_at=_utcnow(),
    ))


def _suppress(session: Session, value: str, kind: str, reason: str) -> None:
    exists = session.scalar(
        select(Suppression.id).where(Suppression.value == value, Suppression.kind == kind)
    )
    if not exists:
        session.add(Suppression(value=value, kind=kind, reason=reason, added_at=_utcnow()))
