# GRD AI SDR + Talent Sourcing — Architecture

What this application is, what it does end to end, its data model, and every
technology it uses with the reason it was chosen.

---

## 1. What it is

A **platform for building AI agents** that do lead/candidate research and
scoring, plus two agents built on it:

| Vertical | Input | Output |
|---|---|---|
| **AI SDR** | company domains | for each: a **sourced** company profile + a calibrated **fit score** vs an Ideal Customer Profile (ICP) |
| **Talent sourcing** | candidate handles (GitHub) | for each: a **sourced** candidate profile + a calibrated **fit score** vs a **job rubric** |

The platform is the `grd/` Python package. Each agent is a folder of
configuration under `agents/` (`agents/ai_sdr/`) — YAML + prompts, almost no
code. Adding a new agent/campaign = copy the folder, edit the YAML.

Everything is **local-first**: it runs with zero external services (SQLite +
deterministic stand-ins) for development, and scales to Postgres + pgvector +
a local Ollama model for production. No data leaves the box unless you wire in a
paid enrichment provider.

---

## 2. End-to-end workflow

### 2.1 The full intended pipeline (AI SDR)

```
 domains ─▶ [1 Research] ─▶ [2 Scoring] ─▶ gate A ─▶ [3 Copy] ─▶ gate B ─▶ [4 CRM] ─▶ (send)
               │               │          (auto if      │        (human       │
        capability calls   rubric + LLM   score≥T)   voice RAG   approves)   idempotent
        + provenance       nudge                     draft                    upsert
```

Steps **1–2 are built and running today.** Steps 3–4 and the two human gates
have their config contracts defined (`agents/ai_sdr/copy/`, `.../crm/`, workflow
`status: planned`) and DB tables (`outreach_drafts`, `crm_syncs`,
`suppressions`) but no logic yet.

### 2.2 What happens on one run (built portion), step by step

**Trigger** — `python -m grd.cli score-batch domains.csv` or
`POST /api/leads/score {"domains": [...]}`. `grd/main.py` / `grd/cli.py` build a
`Pipeline` (`grd/pipeline.py`), which loads the agent config folder via
`AgentSpec` (`grd/spec.py`).

**Step 1 — Research** (`grd/agents/research.py`, `ResearchAgent.run(domain)`):

1. Clean the domain (`https://www.Foo.com/x` → `foo.com`).
2. For each **capability** in the allow-list (`agents/ai_sdr/research/tools.allow`
   — `company_lookup`, `contact_lookup`, `funding_lookup`, `tech_lookup`,
   `news_search`, `web_fetch`):
   - find providers that support it (`grd/enrichment/mock.py`, `web.py`);
   - call `provider.call(capability, domain=…)` with a timeout and one retry;
   - collect `Fact`s (each = `value + source + capability + retrieved_at`) and
     `ResearchIssue`s.
3. `assemble_profile()` merges the Facts into one `CompanyProfile`, recording
   **provenance for every field** ("no fact without a source"). First source
   wins for scalars; agreeing sources become `corroborating` provenance.
4. Guardrails: drop any value with no provenance (`unsourced_fact`); flag funding
   / news older than 24 months (`stale_data`, kept); flag `low_confidence` if
   fewer than half the ICP's key fields were sourced; `enrichment_miss` if
   `company_lookup` returned nothing; `site_blocked` from the web provider.
5. The LLM (`grd/llm/`, `mock` or `ollama`) writes a ≤150-word summary from the
   **sourced profile only**, using the prompt in
   `agents/ai_sdr/research/prompts/summarize.md`.
6. Returns `ResearchResult { profile, contact, summary, sources, providers_used,
   capabilities_used, issues }`.

**Step 2 — Scoring** (`grd/agents/scoring.py`, `ScoringAgent.run(profile)`):

1. Six component scores, each 0–1, each with a `basis` string:
   `industry`, `size`, `geography`, `funding_recency`, `open_roles`,
   `headcount_growth` — computed **deterministically** from
   `agents/ai_sdr/scoring/icp/grd_staffing.yaml` (industries, size bands,
   geographies, signal thresholds, weights).
2. `deterministic = Σ(raw × weight) / Σweights × 100` (weights sum to 100).
3. The LLM reads the buying signals and returns a **bounded** adjustment
   (`|adj| ≤ 10`) + one-sentence rationale (prompt:
   `agents/ai_sdr/scoring/prompts/interpret_signals.md`). `mock` LLM uses fixed
   rules; `ollama` calls the model.
4. `final = clamp(deterministic + adj, 0, 100)`; `tier` A/B/C/D from thresholds;
   `qualified = final ≥ thresholds.qualify`; `confidence` = share of key fields
   sourced.
5. Returns `LeadScore { value, deterministic_value, llm_adjustment, tier,
   qualified, confidence, components[], matched_signals[], missing_criteria[],
   rationale }`.

**Persist** (`Pipeline._persist`): upsert `companies`, insert a `research_runs`
row (summary, provenance, capabilities, issues, cost/tokens), upsert `contacts`,
upsert the `leads` row (score, tier, stage). Re-running a domain updates the
same lead — no duplicates.

**Response** — `ScoredLead { domain, company (+provenance), contact,
research_summary, providers_used, capabilities_used, issues, score }`. The CLI
prints a table + optional CSV; the API returns JSON; `GET /api/leads/{id}`
returns the full profile + the research block (summary, capabilities, issues,
provenance).

### 2.3 Talent-sourcing run (parallel structure)

`grd/recruiting/` mirrors the SDR side: `CandidateResearchAgent` pulls a public
GitHub profile + repos (`grd/recruiting/sourcing/github.py`) — languages,
topics→skills, stars, followers, last-push — plus a deterministic `mock` source;
`CandidateScoringAgent` grades it against `grd/recruiting/rubrics/
backend_engineer_india.yaml` (must-have / nice-to-have skills, seniority,
location + remote-ok, activity, portfolio strength). Output: `ScoredCandidate`
with `matched_requirements` / `gaps`. Endpoints: `POST /api/candidates/score`,
`GET /api/candidates[/{id}]`. CLI: `source-batch`.

---

## 3. Data model  (SQLite for dev, Postgres + pgvector for production)

One SQLAlchemy metadata (`grd/models.py` + `grd/recruiting/models.py`). Dev
creates tables with `create_all`; production uses Alembic (`alembic/`,
initial migration checked in).

### 3.1 Tables

**SDR core**

| Table | Purpose | Key columns |
|---|---|---|
| `campaigns` | one outreach programme | `name`(uniq), `agent`, `icp`, `status`, `offer`, `sender_identity` |
| `companies` | deduped company, keyed by domain | `domain`(uniq), `name`, `industry`, `size_band`, `employee_count`, `hq_country`, `profile_json` |
| `contacts` | a decision-maker at a company | `company_id`→, `name`, `title`, `email`, `linkedin_url`, `source`, `verified` |
| `research_runs` | one research execution's output + audit | `company_id`→, `summary`, `profile_json` (incl. provenance), `sources_json`, `providers`, `capabilities`, `issues_json`, `cost_usd`, `tokens` |
| `leads` | a scored (company, icp) pair, moves through stages | `company_id`→, `contact_id`→, `campaign_id`→, `icp`, `stage` (`sourced→researched→scored→drafting→review→crm→done`), `score_value`, `tier`, `qualified`, `confidence`, `rationale`, `score_json` |

**Downstream (schema now, logic later — steps 2.3 / 2.4)**

| Table | Purpose | Key columns |
|---|---|---|
| `outreach_drafts` | a generated message + its review trail | `lead_id`→, `channel`, `subject`, `body`, `personalization_json`, `version`, `status` (`draft→approved\|edited\|rejected→sent`), `approver`, `edit_diff` |
| `crm_syncs` | one write to an external CRM, idempotent | `lead_id`→, `crm`, `crm_object_id`, `action`, `payload_hash` (skip no-op writes), `result`, `synced_at` |
| `suppressions` | global do-not-contact list | `value` + `kind` (`email`\|`domain`) **unique**, `reason`, `added_at` |

**Observability**

| Table | Purpose | Key columns |
|---|---|---|
| `pipeline_runs` | one row per pipeline execution, either vertical | `vertical`, `agent`, `campaign_id`→, `target`, `status`, `steps_json` (`[{step, ms, status}]`), `cost_usd`, `tokens`, `error` |

**RAG (voice corpus for the Copy agent)**

| Table | Purpose | Key columns |
|---|---|---|
| `doc_chunks` | chunked + embedded reference text | `agent`, `source_kind` (`voice_corpus`\|`case_study`\|…), `source_ref`, `ord`, `text`, **`embedding`**, `meta_json` |

**Talent sourcing** — `candidates` (`handle` uniq), `candidate_research_runs`,
`candidate_matches` (`candidate_id` + `rubric`, `pipeline_stage`). Same shape as
the SDR trio.

### 3.2 Why Postgres + pgvector

- **SQLite for dev / CI / tests** — zero setup, one file, the whole suite runs
  in ~1.5 s with no services. Perfect while iterating.
- **Postgres for production** because the workload needs concurrent writers
  (batch workers scoring many domains at once), real transactions across the
  `companies / research_runs / leads / outreach_drafts / crm_syncs` chain,
  JSON columns *and* relational integrity in one store, and operational
  maturity (backups, PITR, replicas).
- **pgvector** adds a `vector(N)` column type + ANN indexes to that same
  Postgres. The Copy agent (step 2.3) retrieves the closest few
  `doc_chunks` to ground each draft in GRD's real voice. Keeping embeddings in
  Postgres — rather than a separate vector DB (Qdrant, Pinecone, Chroma) — means
  **one database to run, back up and join**: a similarity search can filter by
  `agent` / `source_kind` in the same query. A dedicated vector DB only earns
  its keep at much larger corpora than a curated voice corpus.
- **Portability is built in**: `grd/dbtypes.py::Embedding` is a
  `TypeDecorator` that renders as `vector(384)` on Postgres (when `pgvector` is
  installed) and as a JSON array everywhere else, so the identical models run on
  both. On SQLite an embedding is just stored/returned as a list — fine for
  tests and tiny corpora; real ANN search needs Postgres.
- **`create_all` vs Alembic**: dev uses `create_all` (`grd/db.py::init_db`,
  which also runs `CREATE EXTENSION IF NOT EXISTS vector` on Postgres);
  production applies versioned migrations (`alembic upgrade head`). The initial
  autogenerated migration is committed at `alembic/versions/`.

---

## 4. Technology stack — what and why

| Technology | Used for | Why this one |
|---|---|---|
| **Python 3.11+** | everything | batteries-included for HTTP, async, data; the ecosystem for LLM/embeddings/DB work; `from __future__ import annotations` keeps type hints cheap |
| **FastAPI** | the HTTP API (`grd/main.py`, `grd/api/`, `grd/recruiting/api.py`) | async-native (research fans out many I/O-bound provider calls concurrently), Pydantic request/response validation for free, auto OpenAPI docs at `/docs`, tiny footprint |
| **Uvicorn** | ASGI server | the standard way to run FastAPI; `[standard]` extras add fast HTTP/websocket parsing |
| **Pydantic v2 + pydantic-settings** | typed I/O models (`grd/schemas.py`, `grd/recruiting/schemas.py`) and env config (`grd/config.py`, `GRD_` prefix) | every agent boundary is a typed contract — invalid data fails loudly at the edge, not deep in scoring; settings come from env/`.env` with types and defaults in one place |
| **SQLAlchemy 2.0** | ORM + Core (`grd/models.py`, `grd/db.py`) | one model layer that runs on SQLite and Postgres; typed `Mapped[...]` columns; explicit sessions/transactions; `TypeDecorator` gives us the portable `Embedding` type |
| **SQLite** | dev / test database | no service to run; the full test suite is hermetic and fast; in-memory (`sqlite://`) per test via `StaticPool` |
| **PostgreSQL 16** | production database | concurrency, transactions across the lead lifecycle, JSON + relational in one engine, operational tooling |
| **pgvector** | `doc_chunks.embedding` similarity search | vector search *inside* Postgres — one datastore, filterable joins, no separate vector DB to operate |
| **Alembic** | schema migrations | production schema changes must be reviewable and reversible; autogenerate from the same metadata `create_all` uses |
| **psycopg 3** | Postgres driver (`postgresql+psycopg://`) | current-generation driver, good async + binary support; only installed for Postgres deploys (`requirements-postgres.txt`) |
| **Ollama** | local LLM runtime (`grd/llm/ollama.py`) | runs `llama3.1` / `qwen2.5` **on-box** — CV data, client contracts and prospect research never leave the network; swappable model; no per-token cost. The `LLM` interface (`grd/llm/base.py`) means a hosted model is a one-file addition when quality demands it |
| **`mock` LLM + `mock` providers** | deterministic stand-ins | the whole pipeline runs and every test is reproducible with **no network and no model** — you develop scoring logic without waiting on an LLM, and CI never flakes |
| **sentence-transformers** (planned — added when the Copy agent lands) | embeddings for the voice corpus | small, fast, local (`all-MiniLM-L6-v2`, 384-dim → `EMBED_DIM`); good enough for a curated corpus; upgradeable to `bge-*` |
| **httpx** | all outbound HTTP (`web` enrichment, GitHub source, Ollama client) | async client so provider calls run concurrently; timeouts and retries are first-class |
| **BeautifulSoup4** | parse the company's own homepage / careers page | tolerant HTML parsing to pull `<title>`, meta description and count job links |
| **PyYAML** | load agent config (`config.yaml`, `workflow.yaml`, ICP / rubric YAML) | agent behaviour lives in readable YAML that non-engineers can edit; `safe_load` only |
| **pytest** | the test suite (`tests/`, 35 tests) | fixtures for settings/spec/ICP/DB; every agent invariant (bounded LLM nudge, provenance, weights sum to 100, dedupe on re-run) is pinned |
| **Docker Compose** | `deploy/docker-compose.yml` | one command brings up Postgres+pgvector, Ollama and the API wired together |
| **argparse** | the CLI (`grd/cli.py`) | stdlib; `score-batch` (SDR) and `source-batch` (recruiting) with CSV in / CSV out |

### Design choices worth calling out

- **Deterministic core, bounded LLM.** Scores come from an explicit weighted
  rubric; the LLM only nudges within `±max_llm_adjustment`. This keeps results
  explainable and auditable, and lets the LLM be `mock` in tests without
  changing outcomes materially.
- **Capabilities, not providers.** The research agent calls abstract
  capabilities; providers advertise which they support. Adding Apollo / PDL /
  Crunchbase / a news API is implementing one method — no agent changes. A
  campaign can forbid a data source by deleting a line from `tools.allow`.
- **Provenance is mandatory.** Every field on a profile records its source; the
  agent drops anything unsourced and the summary prompt forbids new facts. This
  is what makes the output defensible for outreach and for compliance.
- **Agent = configuration.** All business specifics (which industries, which
  skills, which prompts, which gates) live under `agents/<name>/`. The platform
  package has no campaign knowledge.
- **Compliance by construction.** Enrichment touches only the target's own
  surface (its domain, or public GitHub) — never LinkedIn scraping. The
  `suppressions` table and the human gates exist in the schema before any
  sending code does.

---

## 5. Running it

| Mode | Command | Stores |
|---|---|---|
| Dev / tests | `pip install -r requirements.txt` → `pytest -q` / `uvicorn grd.main:app` | SQLite file, `mock` LLM |
| Local with a real model | run Ollama, `GRD_LLM_PROVIDER=ollama` | SQLite, Ollama |
| Production | `pip install -r requirements.txt -r requirements-postgres.txt`; `alembic upgrade head`; `docker compose -f deploy/docker-compose.yml up` | Postgres + pgvector, Ollama |

Config is all `GRD_`-prefixed env vars (see `.env.example`): `GRD_AGENT`,
`GRD_DATABASE_URL`, `GRD_LLM_PROVIDER`, `GRD_ENRICHMENT_PROVIDERS`,
`GRD_CANDIDATE_SOURCES`, `GRD_ICP`, `GRD_RUBRIC`, `GRD_RESEARCH_*`.

---

## 6. Status

| Piece | State |
|---|---|
| Research agent (SDR) — capabilities, provenance, issues | **done** |
| Scoring agent (SDR) — rubric + bounded LLM | **done** |
| Candidate research + scoring (recruiting) | **done** |
| Agent-as-config (`agents/ai_sdr/`, `AgentSpec`) | **done** |
| Data model incl. Postgres/pgvector types + Alembic | **done (this step)** |
| Copy agent (2.3) + voice-corpus RAG + Gate B | schema + config only |
| CRM/ATS agent (2.4) + suppression checks + Gate A | schema + config only |
| Real enrichment providers; score calibration; observability writes | not started |
| Rename `grd/` → `platform/`; recruiting as its own `agents/` folder | deferred |
