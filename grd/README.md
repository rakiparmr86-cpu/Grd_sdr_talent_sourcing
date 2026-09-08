# GRD — AI SDR + Talent Sourcing

Research + Scoring agents for GRD, built in steps. Same shape, two verticals.

> **Full picture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — end-to-end
> workflow, the data model, and every technology with the reason it's used.

### Vertical 1 — SDR (company → lead)

Given company **domains**: **Research** (see [docs/research-agent.md](docs/research-agent.md))
calls a capability allow-list — `company_lookup`, `contact_lookup`,
`funding_lookup`, `tech_lookup`, `news_search`, `web_fetch` — across allowed
providers, records **provenance for every field** ("no fact without a source"),
and reports **issues** (`site_blocked`, `stale_data`, `capability_error`,
`low_confidence`, …) instead of crashing. **Scoring** then produces a calibrated
fit score (0–100) vs an **ICP** — deterministic weighted rubric, then a small
**bounded** LLM nudge on buying signals. Output: score, tier A/B/C/D, qualified
flag, confidence, matched signals, missing criteria, rationale.

### Vertical 2 — Talent sourcing (candidate → match)

Given candidate **handles**: **Research** builds a factual candidate profile from
allowed sources (`mock` synthetic data + real public **`github`** profile/repos);
**Scoring** produces a calibrated fit score (0–100) vs a **job rubric** — same
deterministic-then-bounded-LLM method. Output: score, tier, qualified flag,
confidence, matched requirements, gaps, rationale.

No outreach, no CRM/ATS writes yet — those are later steps (Copy agent →
CRM/ATS agent). See [docs/roadmap.md](docs/roadmap.md).

---

## Layout

**`grd/` = the platform** (generic logic). **`agents/<name>/` = one agent as
config** (YAML + prompts, ~no code). Pick the agent with `GRD_AGENT` (default
`ai_sdr`). See [agents/ai_sdr/README.md](agents/ai_sdr/README.md).

```
agents/ai_sdr/           the SDR agent as configuration
├── config.yaml           llm models, research knobs, scoring icp, gate thresholds
├── workflow.yaml         6 steps (research, scoring active; gate_a/copy/gate_b/crm planned)
├── research/{tools.allow, prompts/summarize.md}
├── scoring/{rubric.yaml, prompts/interpret_signals.md, icp/grd_staffing.yaml}
├── copy/    {prompts/draft.md, voice_corpus/, templates/}   (placeholders, step 2.3)
├── crm/field_map.yaml    (placeholder, step 2.4)
└── evals/   {scoring_golden.jsonl, research_factcheck.jsonl, copy_rubric.yaml}

grd/                      the platform
├── spec.py              AgentSpec — loads agents/<name>/ into a typed object
├── config.py            env settings (GRD_ prefix); agents_dir / icp_dir
├── db.py                engine / session helpers (one shared metadata)
├── llm/{base,mock,ollama}.py   LLM layer; prompts injected from the agent folder
├── main.py · cli.py     FastAPI app · `score-batch` (SDR) + `source-batch` (recruiting)
│
├── schemas.py           CompanyProfile (+provenance), LeadScore, ScoredLead, ResearchIssue
├── models.py            tables: companies, contacts, research_runs, leads
├── pipeline.py          Pipeline: AgentSpec -> Research -> Scoring -> persist
├── agents/{research,scoring}.py
├── enrichment/{base,mock,web,capabilities}.py   capability providers
├── scoring/__init__.py  load_icp()   (ICP files now live under agents/)
├── api/routes.py        POST /api/leads/score, GET /api/leads[/{id}]
│
└── recruiting/          talent-sourcing vertical (own agents/schemas/models/api;
                         still uses grd/recruiting/rubrics/ — not yet an agents/ folder)
```

## Quick start

```bash
cd D:/newdata/Grd-new-rg/grd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### Run the batch scorers (no network needed — mock data)

```bash
# SDR: score company domains
python -m grd.cli score-batch data/sample_domains.csv --out results.csv

# Recruiting: score candidate handles (force mock so it skips GitHub)
GRD_CANDIDATE_SOURCES=mock python -m grd.cli source-batch data/sample_candidates.csv --out cand_results.csv
```

### Run the API

```bash
uvicorn grd.main:app --reload      # http://localhost:8000/docs
```

```bash
curl -s -X POST http://localhost:8000/api/leads/score \
  -H "content-type: application/json" -d "{\"domains\":[\"stripe.com\"]}"

curl -s -X POST http://localhost:8000/api/candidates/score \
  -H "content-type: application/json" -d "{\"handles\":[\"tiangolo\"]}"
```

### AI vs traditional split

Deterministic code (normalization, dedup, `payload_hash`, suppression checks,
Gate-A routing, reply parsing) lives in `grd/classify.py` and **must not** use an
LLM — `tests/test_ai_boundary.py` enforces that only allow-listed modules import
`grd.llm`. Policy + table: [docs/ai-vs-traditional.md](docs/ai-vs-traditional.md).

### Metrics ([docs/metrics.md](docs/metrics.md))

```bash
python -m grd.cli metrics            # funnel / quality / reliability / economics
```

`GET /api/metrics` (JSON) · `GET /dashboard` (self-contained HTML page).

### Tests

```bash
python -m pytest -q
```

### Deploy on Postgres + pgvector

Dev uses SQLite + `create_all`. For production:

```bash
pip install -r requirements.txt -r requirements-postgres.txt
export GRD_DATABASE_URL=postgresql+psycopg://grd:grd@localhost:5432/grd
alembic upgrade head            # versioned schema (initial migration is committed)
uvicorn grd.main:app
# or the whole stack (Postgres+pgvector, Ollama, API):
docker compose -f deploy/docker-compose.yml up --build
```

The models are backend-portable: `doc_chunks.embedding` is `vector(384)` on
Postgres (via `pgvector`) and a JSON array on SQLite — same code either way.
Regenerate migrations after model changes with
`alembic revision --autogenerate -m "..."`.

## Configuration (`.env`, all `GRD_`-prefixed)

| Var | Default | Notes |
|---|---|---|
| `GRD_DATABASE_URL` | `sqlite:///./grd.db` | any SQLAlchemy URL; `postgresql+psycopg://…` for prod (see below) |
| `GRD_LLM_PROVIDER` | `mock` | `mock` or `ollama` |
| `GRD_OLLAMA_BASE_URL` / `GRD_OLLAMA_MODEL` | `localhost:11434` / `llama3.1` | |
| `GRD_AGENT` | `ai_sdr` | which `agents/<name>/` config folder to load |
| `GRD_ENRICHMENT_PROVIDERS` | `mock,web` | SDR company providers, in order |
| `GRD_ICP` | `grd_staffing` | `agents/<GRD_AGENT>/scoring/icp/<name>.yaml` (else the agent's `config.yaml` default) |
| `GRD_RESEARCH_CAPABILITIES` | all 6 | fallback allow-list when no spec folder; the spec's `tools.allow` wins |
| `GRD_RESEARCH_STALE_AFTER_MONTHS` / `GRD_RESEARCH_RETRIES` | `24` / `1` | fallbacks; the spec's `config.yaml research.*` wins |
| `GRD_CANDIDATE_SOURCES` | `mock,github` | recruiting candidate sources, in order |
| `GRD_GITHUB_TOKEN` | _(none)_ | lifts GitHub API limit 60/hr → 5000/hr |
| `GRD_RUBRIC` | `backend_engineer_india` | file in `grd/recruiting/rubrics/<name>.yaml` |

## Retargeting

- **New ICP / job rubric:** copy the matching YAML in
  `agents/ai_sdr/scoring/icp/` or `grd/recruiting/rubrics/` and edit it.
  `weights` must sum to 100; `thresholds` needs `A`/`B`/`C`/`qualify`.
- **New SDR agent / campaign:** copy `agents/ai_sdr/` to `agents/<name>/`, edit
  the YAML + prompts, run with `GRD_AGENT=<name>`. No code changes.
- **Forbid a data source for a campaign:** delete its line from
  `agents/<name>/research/tools.allow`.
- **Real data providers:** add a class in `grd/enrichment/` (`EnrichmentProvider`)
  or `grd/recruiting/sourcing/` (`CandidateSource`), register it in that package's
  `__init__.py`, and list it in the relevant `GRD_*_SOURCES`. **No LinkedIn
  scraping** — licensed provider data only. The `github` source reads only public
  profile/repo data; it does not infer years of experience (a résumé/LinkedIn
  source fills that).
- **Real LLM:** `GRD_LLM_PROVIDER=ollama` + a running Ollama, or add a client in `grd/llm/`.

## How a score is built (both verticals)

```
deterministic = Σ (component_raw[0..1] × weight) / Σ weights × 100
final         = clamp(deterministic + llm_adjustment, 0, 100)   # |adj| ≤ max_llm_adjustment
tier          = A/B/C/D from thresholds ; qualified = final ≥ thresholds.qualify
confidence    = share of important_fields that were found
```

| Vertical | Components |
|---|---|
| SDR | `industry`, `size`, `geography`, `funding_recency`, `open_roles`, `headcount_growth` |
| Recruiting | `skills_must_have`, `skills_nice_to_have`, `seniority`, `location`, `activity`, `portfolio_strength` |

Each component carries a `basis` string explaining its raw value, surfaced in the
rationale and the API detail response.
