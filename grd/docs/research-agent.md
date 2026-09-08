# Research agent (SDR)

Sub-agent 2.1 of the AI SDR. Builds a **factual, sourced** company profile that
the Scoring agent then grades.

## Contract

```
input:   domain (+ optional contact hint)
output:  ResearchResult {
           profile: CompanyProfile          # + per-field provenance
           contact: ContactProfile | None
           summary: str                     # grounded only in sourced facts
           sources / providers_used / capabilities_used: list[str]
           issues: list[ResearchIssue]
         }
```

## Capability allow-list (the "tools")

The agent calls **capabilities**, not providers. A provider declares which it
supports; the agent runs each allowed capability against every provider that
offers it. Configure with `GRD_RESEARCH_CAPABILITIES` (comma list).

| capability | yields | mock | web |
|---|---|:--:|:--:|
| `company_lookup` | name, industry, size band, employee count, HQ, description | ✓ | — |
| `contact_lookup` | one decision-maker contact | ✓ | — |
| `funding_lookup` | funding rounds (with dates) | ✓ | — |
| `tech_lookup` | tech stack | ✓ | — |
| `news_search` | recent news items (with dates) | ✓ | — |
| `web_fetch` | the company's **own** homepage + careers page → name, description, open-role count | — | ✓ |

Add a real provider (Apollo / People Data Labs / Crunchbase / BuiltWith / a news
API) by implementing `EnrichmentProvider.call` and listing its capabilities. **No
LinkedIn scraping** — licensed provider data only.

## Guarantees

- **No fact without a source.** Every value on the profile comes from a `Fact`
  that carries `source`, `capability`, `retrieved_at` (and `as_of` for dated
  data). These land in `profile.provenance`. A value with no provenance is
  dropped and flagged `unsourced_fact`.
- **First source wins** for scalars; later agreeing sources are kept as
  `corroborating` provenance entries. List fields (tech, funding, news)
  accumulate.
- **Failures degrade, never crash.** Each capability call gets `retries`
  attempts with a timeout; a persistent failure becomes a `capability_error`
  issue. A provider can also return its own issues (e.g. `web` → `site_blocked`).
- **Summary is grounded.** The LLM only sees the sourced profile; the prompt
  forbids new facts.

## Issue kinds

| kind | meaning |
|---|---|
| `enrichment_miss` | `company_lookup` returned nothing (firmographics missing) |
| `site_blocked` | the company website could not be fetched |
| `capability_error` | a provider errored/timed out after all retries |
| `stale_data` | funding/news older than `GRD_RESEARCH_STALE_AFTER_MONTHS` (kept, flagged) |
| `low_confidence` | fewer than half the ICP's `important_fields` were sourced |
| `unsourced_fact` | a value had no provenance and was dropped |

## Config

| var | default |
|---|---|
| `GRD_RESEARCH_CAPABILITIES` | `company_lookup,contact_lookup,funding_lookup,tech_lookup,news_search,web_fetch` |
| `GRD_RESEARCH_STALE_AFTER_MONTHS` | `24` |
| `GRD_RESEARCH_RETRIES` | `1` |
| `GRD_HTTP_TIMEOUT` | `10` (per capability call) |

## Where it surfaces

- `ScoredLead.issues` / `.capabilities_used` (API `POST /api/leads/score`)
- `GET /api/leads/{id}` → `research.{summary,providers,capabilities,issues,provenance}`
- persisted on `research_runs` (`capabilities`, `issues_json`)
- CLI `score-batch`: `ISSUES` count column + `capabilities` / `issues` CSV columns

## Not done yet

- Real providers (all data is `mock` synthetic except `web_fetch`).
- Cross-source conflict detection (currently first-wins + corroboration only; a
  disagreeing source is recorded but not flagged).
- The recruiting `CandidateResearchAgent` still uses the older single-call
  provider shape — port it to this capability model next.
