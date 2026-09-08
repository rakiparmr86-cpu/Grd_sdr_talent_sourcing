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
- [ ] Actually write to `pipeline_runs` from `Pipeline` (cost/tokens/timing)

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
