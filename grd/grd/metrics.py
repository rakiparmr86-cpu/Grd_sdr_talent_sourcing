"""SDR dashboard metrics, computed from what the DB actually holds.

Funnel / quality / reliability / economics. Downstream funnel stages (drafted,
sent, replied, meetings) read 0 until the Copy and CRM steps land - the shape is
stable so the dashboard doesn't change when they do.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from grd.models import CrmSync, Lead, OutreachDraft, PipelineRun, ResearchRun


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _ratio_f(n: float, d: int) -> float | None:
    return round(n / d, 6) if d else None


def _pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def sdr_metrics(session: Session, *, icp: str | None = None) -> dict:
    lead_q = select(Lead)
    if icp:
        lead_q = lead_q.where(Lead.icp == icp)
    leads = list(session.scalars(lead_q))
    research_runs = list(session.scalars(select(ResearchRun)))
    runs = list(session.scalars(select(PipelineRun).where(PipelineRun.vertical == "sdr")))
    drafts = list(session.scalars(select(OutreachDraft)))
    syncs = list(session.scalars(select(CrmSync)))

    # ---- funnel --------------------------------------------------------
    researched = len(research_runs)
    enrichment_hits = sum(1 for r in research_runs if (r.providers or "").strip())
    scored = len(leads)
    qualified = sum(1 for x in leads if x.qualified)
    tiers = Counter(x.tier for x in leads)
    drafted = len(drafts)
    approved = sum(1 for d in drafts if d.status in ("approved", "edited", "sent"))
    sent = sum(1 for d in drafts if d.status == "sent")
    synced_ok = sum(1 for c in syncs if c.result == "ok")

    funnel = {
        "researched": researched,
        "enrichment_hit_rate": _ratio(enrichment_hits, researched),
        "scored": scored,
        "qualified": qualified,
        "qualify_rate": _ratio(qualified, scored),
        "tier_counts": {t: tiers.get(t, 0) for t in ("A", "B", "C", "D")},
        "drafted": drafted,
        "draft_approval_rate": _ratio(approved, drafted),
        "sent": sent,
        "crm_synced": synced_ok,
        # populated once reply tracking (step D) exists
        "replied": 0,
        "positive_replies": 0,
        "meetings_booked": 0,
    }

    # ---- quality ------------------------------------------------------
    confidences = [x.confidence for x in leads]
    issue_kinds: Counter[str] = Counter()
    runs_with_issue = 0
    for r in research_runs:
        kinds = {i.get("kind") for i in (r.issues_json or []) if i.get("kind")}
        if kinds:
            runs_with_issue += 1
        issue_kinds.update(kinds)

    edit_dists = [
        len(d.edit_diff or "") for d in drafts if d.status == "edited" and d.edit_diff
    ]

    quality = {
        "confidence_mean": _mean(confidences),
        "confidence_p50": _pctl(confidences, 0.5),
        "research_issue_rate": _ratio(runs_with_issue, researched),
        "issue_breakdown": dict(issue_kinds),
        "draft_edit_distance_p50": _pctl(edit_dists, 0.5),  # personalization proxy
    }

    # ---- reliability -----------------------------------------------
    step_ms: dict[str, list[float]] = defaultdict(list)
    step_ok: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in runs:
        for st in r.steps_json or []:
            name = st.get("step", "?")
            step_ms[name].append(float(st.get("ms", 0)))
            step_ok[name][1] += 1
            if st.get("status") == "ok":
                step_ok[name][0] += 1

    reliability = {
        "pipeline_runs": len(runs),
        "pipeline_success_rate": _ratio(sum(1 for r in runs if r.status == "ok"), len(runs)),
        "step_success_rate": {k: _ratio(v[0], v[1]) for k, v in step_ok.items()},
        "step_latency_ms_p50": {k: _pctl(v, 0.5) for k, v in step_ms.items()},
        "step_latency_ms_p95": {k: _pctl(v, 0.95) for k, v in step_ms.items()},
        "enrichment_error_rate": _ratio(issue_kinds.get("capability_error", 0), researched),
        "site_blocked_rate": _ratio(issue_kinds.get("site_blocked", 0), researched),
        "crm_write_failure_rate": _ratio(
            sum(1 for c in syncs if not c.result.startswith("ok")), len(syncs)
        ),
    }

    # ---- economics ------------------------------------------------
    total_cost = round(sum(r.cost_usd for r in runs), 4)
    total_tokens = sum(r.tokens for r in runs)
    economics = {
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "cost_per_researched_lead": _ratio_f(total_cost, researched),
        "cost_per_qualified_lead": _ratio_f(total_cost, qualified),
        "cost_per_positive_reply": None,  # once replies exist
    }

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "icp": icp or "all",
        "funnel": funnel,
        "quality": quality,
        "reliability": reliability,
        "economics": economics,
        "notes": [
            "drafted/sent/replied/meetings and their rates stay 0 until the Copy "
            "(2.3) and CRM (2.4) steps write to outreach_drafts / crm_syncs",
            "cost/tokens are 0 with the mock and ollama (local) LLMs; a hosted "
            "model or paid enrichment provider would populate them",
        ],
    }
