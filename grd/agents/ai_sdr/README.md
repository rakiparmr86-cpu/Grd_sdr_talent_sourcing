# agents/ai_sdr

The **AI SDR agent as configuration**. The platform (`grd/` package) holds the
logic; this folder holds everything that makes it *this* agent for *this*
campaign. A new agent = a new folder like this one.

```
config.yaml              # llm models, research knobs, scoring icp, gate thresholds, limits
workflow.yaml            # the 6 steps + which are active today
research/
  tools.allow            # capability allow-list (one per line) - the agent's "tools"
  prompts/summarize.md    # grounded research-summary prompt
scoring/
  rubric.yaml             # cross-icp scoring rules
  prompts/interpret_signals.md
  icp/grd_staffing.yaml   # the ICP: industries, sizes, geos, signals, weights, thresholds
copy/                     # step 2.3 (planned): prompt + voice_corpus (RAG) + templates
crm/field_map.yaml        # step 2.4 (planned): typed field -> CRM property
evals/                    # golden scoring cases, research fact-check rules, copy rubric
```

## What runs today

`research` + `scoring` (workflow steps with `status: active`). Loaded by
`grd.spec.AgentSpec.load("ai_sdr")` and passed into `grd.pipeline.Pipeline`,
which uses:

| from this folder | drives |
|---|---|
| `research/tools.allow` | which capabilities `ResearchAgent` may call |
| `config.yaml research.*` | stale cutoff, retries, timeout |
| `research/prompts/summarize.md` | the summary prompt (ollama LLM; mock ignores it) |
| `config.yaml scoring.default_icp` + `scoring/icp/*.yaml` | the scoring rubric |
| `scoring/prompts/interpret_signals.md` | the signal-interpretation prompt |
| `config.yaml gates.gate_a_auto_threshold` | (read now, enforced when Gate A ships) |

Select the agent with `GRD_AGENT=ai_sdr` (default).

## Retarget without touching code

- **New segment:** add `scoring/icp/<name>.yaml`, set `scoring.default_icp` (or pass
  `--icp <name>` / `{"icp": "<name>"}`).
- **Forbid a data source for a campaign:** delete its line from `research/tools.allow`.
- **New agent entirely:** copy this folder to `agents/<name>/`, edit the YAML and
  prompts, point `GRD_AGENT` at it.

## Not built yet

`gate_a`, `copy`, `gate_b`, `crm` steps. Their config files here are placeholders
that define the contract so the code slots in later.
