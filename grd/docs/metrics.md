# SDR metrics dashboard

Computed on demand from the DB by `grd/metrics.py::sdr_metrics(session)`.
Nothing is pre-aggregated - every call is a fresh read.

## Where it comes from

| Source table | Feeds |
|---|---|
| `pipeline_runs` (written per `score_domain` call) | pipeline count / success rate, per-step latency (p50/p95), per-step success rate, cost, tokens |
| `research_runs` | researched count, enrichment hit rate, issue rate + breakdown |
| `leads` | scored count, qualified count, qualify rate, tier counts, confidence mean/p50 |
| `outreach_drafts` | drafted / approval rate / sent, edit-distance p50 (personalization proxy) — **0 until step 2.3** |
| `crm_syncs` | crm_synced, CRM write failure rate — **0 until step 2.4** |

`replied`, `positive_replies`, `meetings_booked`, `cost_per_positive_reply` stay
0/None until reply tracking (step D) exists. The JSON shape does not change when
they light up.

## Sections

- **Funnel** — researched → scored → qualified → drafted → sent → crm_synced →
  replied → positive_replies → meetings_booked, plus enrichment hit rate,
  qualify rate, draft approval rate, tier counts.
- **Quality** — confidence mean & p50, research issue rate, issue breakdown by
  kind (`stale_data`, `site_blocked`, `low_confidence`, `capability_error`, …),
  draft edit-distance p50.
- **Reliability** — pipeline run count & success rate, per-step success rate,
  per-step latency p50/p95, enrichment error rate, site-blocked rate, CRM write
  failure rate.
- **Economics** — total cost USD, total tokens, cost per researched lead, cost
  per qualified lead, cost per positive reply. All 0 with the `mock` / `ollama`
  (local) LLMs; a hosted model or paid enrichment provider populates them via
  `pipeline_runs.cost_usd` / `.tokens`.

## How to read it

```bash
python -m grd.cli metrics                 # table
python -m grd.cli metrics --json          # raw
python -m grd.cli metrics --icp grd_staffing
```

```
GET /api/metrics            -> the JSON above
GET /api/metrics?icp=<name> -> leads filtered by ICP
GET /dashboard              -> a self-contained HTML page that polls /api/metrics
```

The dashboard page (`grd/dashboard.py`) has no external assets - tiles + a
funnel bar list, light/dark aware, one "Refresh" button.

## Not wired yet

- `pipeline_runs.cost_usd` / `.tokens` are written as 0. When a hosted LLM or a
  paid enrichment provider is added, have its client return usage and thread it
  into `Pipeline._record_run`.
- Scoring rank-correlation vs historical outcomes (needs the labelled
  `agents/ai_sdr/evals/scoring_golden.jsonl` filled with real data).
- Recruiting has no dashboard yet; `PipelineRun` rows are SDR-only for now.
