from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from grd.config import get_settings
from grd.pipeline import Pipeline
from grd.recruiting.pipeline import RecruitingPipeline
from grd.recruiting.schemas import ScoredCandidate
from grd.schemas import ScoredLead

_OUT_COLUMNS = [
    "domain", "name", "industry", "size_band", "hq_country",
    "open_roles", "score", "deterministic", "llm_adj", "tier",
    "qualified", "confidence", "capabilities", "issues", "matched_signals", "rationale",
]


def _row(lead: ScoredLead) -> dict:
    c, s = lead.company, lead.score
    return {
        "domain": lead.domain,
        "name": c.name or "",
        "industry": c.industry or "",
        "size_band": c.size_band or "",
        "hq_country": c.hq_country or "",
        "open_roles": "" if c.open_roles is None else c.open_roles,
        "score": s.value,
        "deterministic": s.deterministic_value,
        "llm_adj": s.llm_adjustment,
        "tier": s.tier,
        "qualified": s.qualified,
        "confidence": f"{s.confidence:.2f}",
        "capabilities": " ".join(lead.capabilities_used),
        "issues": " | ".join(f"{i.kind}:{i.detail}" for i in lead.issues),
        "matched_signals": " | ".join(s.matched_signals),
        "rationale": s.rationale,
    }


def _read_domains(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames and "domain" in reader.fieldnames:
            return [r["domain"].strip() for r in reader if r.get("domain", "").strip()]
    # fall back: one domain per line
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


_CAND_OUT_COLUMNS = [
    "handle", "full_name", "location_country", "years_experience",
    "score", "deterministic", "llm_adj", "tier", "qualified", "confidence",
    "matched_requirements", "gaps", "rationale",
]


def _cand_row(c: ScoredCandidate) -> dict:
    p, s = c.profile, c.score
    return {
        "handle": c.handle,
        "full_name": p.full_name or "",
        "location_country": p.location_country or "",
        "years_experience": "" if p.years_experience is None else p.years_experience,
        "score": s.value,
        "deterministic": s.deterministic_value,
        "llm_adj": s.llm_adjustment,
        "tier": s.tier,
        "qualified": s.qualified,
        "confidence": f"{s.confidence:.2f}",
        "matched_requirements": " | ".join(s.matched_requirements),
        "gaps": " | ".join(s.gaps),
        "rationale": s.rationale,
    }


def _read_column(path: Path, *names: str) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames:
            for name in names:
                if name in reader.fieldnames:
                    return [r[name].strip() for r in reader if r.get(name, "").strip()]
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    pipe = Pipeline(settings)
    domains = _read_domains(Path(args.csv))
    if not domains:
        print("no domains found", file=sys.stderr)
        return 1

    leads = await pipe.score_batch(domains, icp=args.icp)
    leads.sort(key=lambda x: x.score.value, reverse=True)

    print(f"{'DOMAIN':<28} {'TIER':<5} {'SCORE':>6} {'CONF':>6} {'ISSUES':>7}  QUALIFIED")
    print("-" * 70)
    for lead in leads:
        print(
            f"{lead.domain:<28} {lead.score.tier:<5} {lead.score.value:>6.1f} "
            f"{lead.score.confidence:>6.2f} {len(lead.issues):>7}  {lead.score.qualified}"
        )

    if args.out:
        out = Path(args.out)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_OUT_COLUMNS)
            writer.writeheader()
            for lead in leads:
                writer.writerow(_row(lead))
        print(f"\nwrote {len(leads)} rows -> {out}")

    q = sum(1 for x in leads if x.score.qualified)
    print(f"\n{q}/{len(leads)} qualified (>= threshold) with ICP '{args.icp or settings.icp}'")
    return 0


async def _run_sourcing(args: argparse.Namespace) -> int:
    settings = get_settings()
    pipe = RecruitingPipeline(settings)
    handles = _read_column(Path(args.csv), "handle", "github", "username", "profile")
    if not handles:
        print("no handles found", file=sys.stderr)
        return 1

    cands = await pipe.score_batch(handles, rubric=args.rubric)
    cands.sort(key=lambda x: x.score.value, reverse=True)

    print(f"{'HANDLE':<24} {'TIER':<5} {'SCORE':>6} {'CONF':>6}  QUALIFIED")
    print("-" * 58)
    for c in cands:
        print(
            f"{c.handle:<24} {c.score.tier:<5} {c.score.value:>6.1f} "
            f"{c.score.confidence:>6.2f}  {c.score.qualified}"
        )

    if args.out:
        out = Path(args.out)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CAND_OUT_COLUMNS)
            writer.writeheader()
            for c in cands:
                writer.writerow(_cand_row(c))
        print(f"\nwrote {len(cands)} rows -> {out}")

    q = sum(1 for x in cands if x.score.qualified)
    print(f"\n{q}/{len(cands)} qualified with rubric '{args.rubric or settings.rubric}'")
    return 0


async def _run_metrics(args: argparse.Namespace) -> int:
    import json

    from grd.metrics import sdr_metrics

    pipe = Pipeline(get_settings())
    threshold = pipe.spec.gate_a_threshold() if pipe.spec else None
    with pipe.Session() as s:
        m = sdr_metrics(s, icp=args.icp, gate_a_threshold=threshold)

    if args.json:
        print(json.dumps(m, indent=2))
        return 0

    f, q, rel, ec = m["funnel"], m["quality"], m["reliability"], m["economics"]
    print(f"SDR metrics  ({m['icp']})  as of {m['generated_at']}")
    print("-" * 56)
    print("FUNNEL")
    for k in ("researched", "scored", "qualified", "drafted", "sent", "crm_synced",
              "replied", "positive_replies", "meetings_booked"):
        print(f"  {k:<18} {f[k]}")
    print(f"  enrichment_hit_rate {f['enrichment_hit_rate']}")
    print(f"  qualify_rate        {f['qualify_rate']}   tiers {f['tier_counts']}")
    print(f"  gate A  auto/human  {f['gate_a_auto']} / {f['gate_a_human']}")
    print("QUALITY")
    print(f"  confidence mean/p50 {q['confidence_mean']} / {q['confidence_p50']}")
    print(f"  research_issue_rate {q['research_issue_rate']}   {q['issue_breakdown']}")
    print("RELIABILITY")
    print(f"  pipeline_runs       {rel['pipeline_runs']}   success {rel['pipeline_success_rate']}")
    print(f"  step latency p50    {rel['step_latency_ms_p50']}")
    print(f"  enrichment_error    {rel['enrichment_error_rate']}   site_blocked {rel['site_blocked_rate']}")
    print("ECONOMICS")
    print(f"  cost usd / tokens   {ec['total_cost_usd']} / {ec['total_tokens']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grd", description="GRD AI SDR - research + scoring")
    sub = parser.add_subparsers(dest="cmd", required=True)

    score = sub.add_parser("score-batch", help="[SDR] research + score a CSV of company domains")
    score.add_argument("csv", help="CSV with a 'domain' column (or one domain per line)")
    score.add_argument("--icp", default=None, help="ICP name (default: GRD_ICP env)")
    score.add_argument("--out", default=None, help="optional path to write results CSV")
    score.set_defaults(func=_run)

    source = sub.add_parser("source-batch", help="[recruiting] research + score a CSV of candidate handles")
    source.add_argument("csv", help="CSV with a 'handle' column (or one handle per line)")
    source.add_argument("--rubric", default=None, help="rubric name (default: GRD_RUBRIC env)")
    source.add_argument("--out", default=None, help="optional path to write results CSV")
    source.set_defaults(func=_run_sourcing)

    mx = sub.add_parser("metrics", help="[SDR] print the dashboard metrics from the DB")
    mx.add_argument("--icp", default=None, help="filter leads by ICP name")
    mx.add_argument("--json", action="store_true", help="emit raw JSON")
    mx.set_defaults(func=_run_metrics)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
