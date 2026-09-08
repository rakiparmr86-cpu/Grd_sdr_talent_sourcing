# Compliance — designed in

Controls live in `grd/compliance.py` (deterministic, no LLM — in
`DETERMINISTIC_MODULES`). The pipeline computes a compliance posture for every
lead at scoring time, so a lead is never "found" without also knowing whether it
can be contacted.

## Controls and where each is enforced

| Requirement | Control | Where |
|---|---|---|
| **Geo consent rules** (GDPR / UK PECR / DPDP) | `region_for_country(iso2)` → EU / EEA / UK / US / IN / OTHER / UNKNOWN; `outreach_posture(region)` → `allow` (US, OTHER) or `manual_only` (EU, EEA, UK, IN, UNKNOWN) | `Pipeline.score_domain` sets `ScoredLead.compliance`; `sdr_metrics` → `compliance.regions` + `outreach_manual_only` |
| **Suppression / do-not-contact** | `is_suppressed()` checked in `outreach_gate` before anything else; opt-out and erasure both add to `suppressions` | `grd/classify.py`, `grd/compliance.py` |
| **CAN-SPAM: sender identity + physical address + one-click opt-out** | `campaign_outreach_gaps()` → `outreach_gate` returns `block` if a campaign lacks `sender_identity` / `sender_address` / an unsubscribe target; `email_footer()` builds the required block; `validate_email_body()` flags a draft with no identity or opt-out line | `grd/compliance.py`; `campaigns` columns |
| **LinkedIn ToS** | `outreach_gate(channel="linkedin", mode="automated")` → hard `block`. Licensed provider data / human send only. | `grd/compliance.py`; `web`/`github` sources already touch only the target's own surface |
| **Consent record** | `record_consent(action=opt_in\|opt_out\|preference)` updates the contact and appends a `consent_events` row | `grd/compliance.py` |
| **Data-subject erasure** | `erase_subject(email=/domain=)` deletes company/leads/research/contacts (or anonymizes a contact), suppresses the identifier, writes `deletion_requests` + a `consent_events` `erasure` row | `grd/compliance.py`; `POST /api/compliance/erase` |
| **Retention** | `purge_expired_research(session, retain_days)` deletes `research_runs` past the window | `grd/compliance.py` (run on a schedule) |
| **CRM writes don't clobber humans** | `assert_ai_namespaced(field_map)` — every CRM target property must be `ai_*` or an identity/match field; `ai_property_name()` enforces the prefix | `grd/compliance.py`; validated against `agents/ai_sdr/crm/field_map.yaml` |
| **PII minimization to the model** | `redact_pii(text)` masks emails/phones before any text is sent to an LLM (the LLM boundary already limits this; defense-in-depth) | `grd/compliance.py` |
| **Provenance for every fact** | already enforced by the research agent — every field carries a `source` | `grd/agents/research.py` (see `docs/research-agent.md`) |

## Data model

- `campaigns`: `sender_identity`, `sender_address`, `unsubscribe_url`,
  `unsubscribe_mailto`, `consent_basis`.
- `contacts`: `region`, `consent_status` (`none|opt_in|opt_out`),
  `consent_source`, `consent_at`.
- `suppressions`: global do-not-contact (email or domain), unique per `(value, kind)`.
- `consent_events`: append-only audit — `subject`, `action`, `source`, `note`, ts.
- `deletion_requests`: erasure requests + `deleted_json` counts + `status`.

Migration: `alembic/versions/babdcac57d60_*.py` (on top of the initial schema).

## The pre-send checklist (what step 2.3/2.4 code must call)

```python
d = outreach_gate(session=s, region=contact.region, email=contact.email,
                  domain=company.domain, channel="email", mode="automated",
                  campaign=campaign, consent_status=contact.consent_status)
if not d.allowed:
    route_to_human_or_drop(d)          # d.outcome in {"manual_only", "block"}, d.reasons
else:
    body = draft + "\n\n" + email_footer(campaign)
    assert validate_email_body(body, campaign) == []
    send(body)
```

## API

```
GET  /api/compliance/check?domain=&email=&country=&channel=&mode=   -> {outcome, region, reasons}
POST /api/compliance/suppress   {value, kind, reason}
POST /api/compliance/erase      {email? domain? reason}             -> {status, deleted}
```

## Still policy-only (not code yet)

- Actual sending, unsubscribe-link handling, and the EU/UK **consent capture**
  flow — these arrive with step 2.3/2.4. The gate, the tables and the audit
  trail are already here so that code has to go through them.
- Legal review of `consent_basis` per market before any automated EU send.
