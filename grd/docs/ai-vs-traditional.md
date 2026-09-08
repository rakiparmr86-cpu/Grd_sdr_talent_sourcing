# AI vs traditional automation — the split

**Rule:** use plain code (rules / regex / SQL / hashing) whenever the input is
structured *or* the output must be exact, deterministic and auditable. An LLM is
only allowed where the input is unstructured language **and** a wrong answer is
cheap and reviewable.

Default one notch more conservative than feels necessary: ship the deterministic
path first, measure, add AI only for the residue it can't handle.

## The split in this codebase

| Deterministic — **no LLM** | Where it lives | AI — LLM allowed | Where it lives |
|---|---|---|---|
| Domain / email normalization | `grd/classify.py::normalize_domain` / `normalize_email` | Turn sourced facts into a buying-intent read | `grd/agents/scoring.py` → `LLM.interpret_signals` (bounded ±`max_llm_adjustment`) |
| Dedup keys, payload hashing (CRM no-op skip) | `grd/classify.py::company_key` / `contact_key` / `payload_hash` | Research summary (grounded, ≤150 words) | `grd/agents/research.py` → `LLM.summarize_research` |
| Suppression / do-not-contact check | `grd/classify.py::is_suppressed` (reads `suppressions`) | Candidate fit narrative | `grd/recruiting/agents/scoring.py` → `LLM.assess_candidate` |
| Gate A routing (score ≥ threshold → auto) | `grd/classify.py::gate_a_route`, wired in `grd/pipeline.py` | — | — |
| Enrichment calls, retries, timeouts, provenance merge | `grd/enrichment/**` | Personalized outreach draft *(step 2.3)* | `agents/ai_sdr/copy/` (planned) |
| Deterministic rubric maths, weights, tiers, confidence | `grd/agents/scoring.py` (the non-LLM 90%) | Reply **intent** on a `human_reply` *(step D)* | planned `LLM` method |
| Bounce / auto-reply / OOO / unsubscribe parsing | `grd/classify.py::classify_reply` (regex + headers) | Edge-case reply triage regex can't place | planned |
| CRM upsert, field mapping *(step 2.4)* | `agents/ai_sdr/crm/field_map.yaml` + planned code | | |
| Metrics aggregation | `grd/metrics.py` | | |
| Scheduling / send-time rules *(step D)* | planned | | |

`classify_reply` returns `bounce | auto_reply | out_of_office | unsubscribe |
human_reply | unknown`. The last two are exactly the hand-off point: a later AI
step reads *those* for intent — it never re-does the mechanical classification.

## How it's enforced

`tests/test_ai_boundary.py` (runs in CI):

- **`AI_MODULES`** — the only files allowed to `import grd.llm` or receive an
  `LLM`: the `grd/llm/` package, the four agent modules, the two pipelines, and
  `main.py`. Any other file importing `grd.llm` fails the test.
- **`DETERMINISTIC_MODULES`** — `classify`, `metrics`, `dashboard`, `db`,
  `models`, `config`, `spec`, all of `enrichment/`, all of
  `recruiting/sourcing/`, the API routers — asserted to contain **no** reference
  to `grd.llm`.
- `grd/classify.py` is additionally checked to import no network client
  (`httpx`, `requests`, `openai`, `ollama`) — it is pure functions over strings
  and one DB read.

Adding a module that needs the LLM means adding it to `AI_MODULES` **and**
adding a row to the table above with the justification.

## Why

- **Explainability / audit** — a prospect asks "why did you email me?": the
  answer is a rubric score + provenance, not a model's mood.
- **Cost & latency** — normalization, dedup and suppression run millions of
  times; they must be free and instant.
- **Determinism** — money (invoicing), compliance (suppression, opt-out) and
  idempotency (CRM writes) cannot vary run to run.
- **Testability** — the deterministic half is covered by exact-value unit tests;
  the AI half is bounded (`±N` adjustment) and mockable, so tests stay stable.
