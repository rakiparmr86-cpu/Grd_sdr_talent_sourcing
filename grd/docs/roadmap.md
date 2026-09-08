# Roadmap

Same deterministic workflow shape in two verticals. Each step ships and is used on
its own before the next is added.

| Step | SDR (company → lead) | Recruiting (candidate → match) | Status |
|---|---|---|---|
| **A. Research + Scoring** | domain → profile + fit score vs **ICP** | handle → profile + fit score vs **job rubric** | **done, in this repo** |
| B. Copy + review inbox | outreach draft per qualified lead, grounded in research + voice corpus (RAG); human edits every draft (Gate B) | personalized candidate outreach message, grounded in the profile; human edits every draft | not started |
| C. CRM / ATS connector | idempotent upsert into a CRM (HubSpot first); suppression list; Gate A auto-routing by score | idempotent upsert into an ATS (Greenhouse / Lever / Ashby); tag pipeline stage; dedupe by email/handle | not started |
| D. Assisted send + feedback loop | send on approval, reply/bounce webhooks, intent classifier, funnel dashboard, monthly recalibration | sequence send, response tracking, stage automation, monthly rubric recalibration | not started |

## Step A — definition of done

Shared:
- [x] `LLM` interface + `mock` + `ollama` (4 methods: 2 per vertical); prompts injected from the agent folder
- [x] Deterministic rubric scorer with per-component `basis` + bounded LLM adjustment
- [x] `weights` sum to 100; `thresholds` = A/B/C/qualify; `confidence` from `important_fields`
- [x] Shared SQLAlchemy metadata, one `create_all`
- [x] CLI + FastAPI endpoints + unit tests
- [x] **Platform / agent-config split** — `agents/ai_sdr/` holds config.yaml,
      workflow.yaml, `research/tools.allow`, prompts, `scoring/icp/*.yaml`, evals,
      README. `grd.spec.AgentSpec` loads it; `Pipeline` is driven by it. New SDR
      agent = copy the folder, set `GRD_AGENT`. `gate_a`/`copy`/`crm` config files
      are placeholders that fix the contract. See `agents/ai_sdr/README.md`.
- [ ] Rename `grd/` → `platform/`, `grd/enrichment/` → `platform/integrations/`
      (cosmetic; deferred to avoid churn)
- [ ] Give recruiting its own `agents/recruiter_*/` folder(s)
- [x] **Data model** — `campaigns`, `outreach_drafts`, `crm_syncs`,
      `suppressions`, `pipeline_runs`, `doc_chunks` (RAG); `leads.campaign_id` +
      `leads.stage`; portable `Embedding` type (`vector(384)` on Postgres /
      pgvector, JSON on SQLite); `deploy/docker-compose.yml` (Postgres+pgvector +
      Ollama + API); Alembic scaffold + committed initial migration. Full
      write-up: `docs/ARCHITECTURE.md`.
- [x] Write to `pipeline_runs` from `Pipeline` (per-step timing + status; cost/tokens
      plumbed, 0 with local LLMs)
- [x] **Metrics dashboard** — `grd/metrics.py::sdr_metrics` (funnel / quality /
      reliability / economics from `pipeline_runs` + `research_runs` + `leads` +
      `outreach_drafts` + `crm_syncs`), `GET /api/metrics`, `GET /dashboard`
      (self-contained HTML), `grd.cli metrics [--json] [--icp]`. See `docs/metrics.md`.
- [ ] Thread real LLM/provider usage into `pipeline_runs.cost_usd` / `.tokens`
- [ ] Scoring rank-correlation vs labelled outcomes (needs real `scoring_golden.jsonl`)
- [x] **AI vs traditional split** — `grd/classify.py` (deterministic:
      normalize_domain/email, dedup keys, `payload_hash`, `is_suppressed`,
      `gate_a_route`, `classify_reply`); `ScoredLead.gate_a` + `funnel.gate_a_*`
      metrics; `tests/test_ai_boundary.py` enforces that only allow-listed
      modules import `grd.llm`. Policy: `docs/ai-vs-traditional.md`.
- [x] **Compliance, designed in** — `grd/compliance.py`: `region_for_country`,
      `outreach_posture` / `outreach_gate` (suppression + geo + CAN-SPAM campaign
      completeness + LinkedIn ToS), `email_footer` / `validate_email_body`,
      `redact_pii`, `assert_ai_namespaced`, `purge_expired_research`,
      `record_consent`, `erase_subject`. New model: `campaigns` +compliance cols,
      `contacts` +consent cols, `consent_events`, `deletion_requests`.
      `ScoredLead.compliance` + `metrics.compliance`; `/api/compliance/{check,
      suppress,erase}`; migration `babdcac57d60`. See `docs/compliance.md`.
- [ ] Consent-capture flow + real send path (arrive with step 2.3/2.4, must go
      through `outreach_gate`)

SDR:
- [x] `EnrichmentProvider` + `mock` + `web`; ICP format; companies/contacts/research_runs/leads
- [x] **Research agent** = capability allow-list (`company_lookup`, `contact_lookup`,
      `funding_lookup`, `tech_lookup`, `news_search`, `web_fetch`), per-field
      provenance ("no fact without a source"), `ResearchIssue` diagnostics
      (`site_blocked` / `stale_data` / `capability_error` / `low_confidence` /
      `unsourced_fact`), retry+timeout per call. See `docs/research-agent.md`.
- [ ] **Calibration:** 50–100 historical accounts labelled won/lost → set `thresholds.qualify`
- [ ] First real enrichment provider (Apollo / PDL / Crunchbase / news API)
- [ ] Cross-source conflict flagging (today: first-wins + corroboration only)
- [ ] Port the recruiting `CandidateResearchAgent` to the same capability model

Recruiting:
- [x] `CandidateSource` + `mock` + real `github`; rubric format; candidates/candidate_research_runs/candidate_matches
- [x] `CandidateMatch.pipeline_stage` column (sourced → ... ) ready for Step C
- [ ] **Skill vocabulary filter** — the `github` source currently keeps every repo
      topic as a "skill"; filter against a known-skills list per role family
- [ ] **Years-of-experience source** — GitHub can't give it; wire a résumé parser
      or licensed profile provider so `seniority` isn't always low-confidence
- [ ] **Calibration:** score past hires / strong-reject candidates → set `thresholds.qualify`
- [ ] First licensed profile provider (for LinkedIn-type data — never scraped)

## Compliance notes (carry into every later step)

- Enrichment touches only the target's **own** surface: the company's own domain,
  or a candidate's **public** GitHub. No LinkedIn scraping — licensed provider
  data or human-in-the-loop only.
- Every stored fact keeps a `source`. Support deletion of a company / lead /
  candidate on request.
- Candidate data is personal data: minimise what's stored, set retention on
  `candidate_research_runs`, and keep it to legitimate recruiting use.
- Outreach (Step B+) needs: sender identity, opt-out, a global suppression list
  checked before every send, and geo-segmentation (EU/UK → manual pending
  lawful-basis review).
