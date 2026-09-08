"""Tiny self-contained SDR metrics dashboard. No external assets - it fetches
/api/metrics and renders tiles + a funnel. Served at GET /dashboard.
"""

from __future__ import annotations

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GRD AI SDR - metrics</title>
<style>
  :root { color-scheme: light dark; --bg:#f7f7f8; --card:#fff; --ink:#1a1a1a;
          --muted:#6b7280; --line:#e5e7eb; --accent:#2563eb; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0f1115; --card:#171a21; --ink:#e8e8ea; --muted:#9aa1ac; --line:#2a2f3a; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:20px 24px; border-bottom:1px solid var(--line);
           display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
  h1 { font-size:16px; margin:0; }
  .muted { color:var(--muted); }
  main { padding:24px; max-width:1100px; margin:0 auto; }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:.06em;
       color:var(--muted); margin:28px 0 10px; }
  .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); }
  .tile { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }
  .tile .k { color:var(--muted); font-size:12px; }
  .tile .v { font-size:22px; font-weight:600; margin-top:4px; font-variant-numeric:tabular-nums; }
  .funnel { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .frow { display:flex; align-items:center; gap:12px; padding:10px 14px; border-top:1px solid var(--line); }
  .frow:first-child { border-top:0; }
  .frow .lbl { width:150px; color:var(--muted); }
  .bar { height:14px; background:var(--accent); border-radius:3px; min-width:2px; }
  .frow .n { margin-left:auto; font-variant-numeric:tabular-nums; }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  td, th { padding:8px 14px; text-align:left; border-top:1px solid var(--line); }
  th { color:var(--muted); font-weight:500; }
  tr:first-child td, tr:first-child th { border-top:0; }
  button { background:var(--accent); color:#fff; border:0; border-radius:8px;
           padding:8px 14px; cursor:pointer; font:inherit; }
  code { background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }
  .note { color:var(--muted); font-size:12px; margin-top:8px; }
</style>
</head>
<body>
<header>
  <h1>GRD AI SDR</h1><span class="muted">metrics dashboard</span>
  <span class="muted" id="ts" style="margin-left:auto"></span>
  <button onclick="load()">Refresh</button>
</header>
<main id="root"><p class="muted">loading&hellip;</p></main>
<script>
const pct = v => v == null ? "&ndash;" : (v*100).toFixed(1) + "%";
const num = v => v == null ? "&ndash;" : v;
function tile(k, v) { return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div></div>`; }

function funnel(f) {
  const rows = [
    ["Researched", f.researched], ["Scored", f.scored], ["Qualified", f.qualified],
    ["Drafted", f.drafted], ["Sent", f.sent], ["CRM synced", f.crm_synced],
    ["Replied", f.replied], ["Positive replies", f.positive_replies],
    ["Meetings booked", f.meetings_booked],
  ];
  const max = Math.max(1, ...rows.map(r => r[1] || 0));
  return `<div class="funnel">` + rows.map(([l, n]) =>
    `<div class="frow"><span class="lbl">${l}</span>
     <span class="bar" style="width:${(100*(n||0)/max).toFixed(1)}%"></span>
     <span class="n">${n||0}</span></div>`).join("") + `</div>`;
}

function kvTable(obj) {
  const e = Object.entries(obj || {});
  if (!e.length) return `<p class="muted">none</p>`;
  return `<table>${e.map(([k, v]) =>
    `<tr><th>${k}</th><td>${typeof v === "number" && v < 1 && v > 0 ? v : num(v)}</td></tr>`).join("")}</table>`;
}

async function load() {
  const r = await fetch("/api/metrics");
  const m = await r.json();
  document.getElementById("ts").textContent = "as of " + m.generated_at + "  (icp: " + m.icp + ")";
  const f = m.funnel, q = m.quality, rel = m.reliability, ec = m.economics;
  document.getElementById("root").innerHTML = `
    <h2>Funnel</h2>
    <div class="grid">
      ${tile("Enrichment hit rate", pct(f.enrichment_hit_rate))}
      ${tile("Qualify rate", pct(f.qualify_rate))}
      ${tile("Draft approval rate", pct(f.draft_approval_rate))}
      ${tile("Tier A / B", (f.tier_counts.A||0) + " / " + (f.tier_counts.B||0))}
    </div>
    ${funnel(f)}
    <h2>Quality</h2>
    <div class="grid">
      ${tile("Confidence (mean)", pct(q.confidence_mean))}
      ${tile("Confidence (p50)", pct(q.confidence_p50))}
      ${tile("Research issue rate", pct(q.research_issue_rate))}
      ${tile("Draft edit dist (p50)", num(q.draft_edit_distance_p50))}
    </div>
    <h2>Issue breakdown</h2>
    ${kvTable(q.issue_breakdown)}
    <h2>Reliability</h2>
    <div class="grid">
      ${tile("Pipeline runs", num(rel.pipeline_runs))}
      ${tile("Pipeline success", pct(rel.pipeline_success_rate))}
      ${tile("Enrichment error rate", pct(rel.enrichment_error_rate))}
      ${tile("Site blocked rate", pct(rel.site_blocked_rate))}
    </div>
    <h2>Step latency (ms)</h2>
    ${kvTable(rel.step_latency_ms_p50)} <div class="note">p50 &middot; p95: ${JSON.stringify(rel.step_latency_ms_p95)}</div>
    <h2>Economics</h2>
    <div class="grid">
      ${tile("Total cost (USD)", num(ec.total_cost_usd))}
      ${tile("Total tokens", num(ec.total_tokens))}
      ${tile("Cost / researched", num(ec.cost_per_researched_lead))}
      ${tile("Cost / qualified", num(ec.cost_per_qualified_lead))}
    </div>
    ${(m.notes||[]).map(n => `<p class="note">${n}</p>`).join("")}
  `;
}
load();
</script>
</body>
</html>
"""
