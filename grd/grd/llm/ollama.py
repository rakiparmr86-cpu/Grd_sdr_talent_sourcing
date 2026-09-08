from __future__ import annotations

import json

import httpx

from grd.llm.base import LLM
from grd.schemas import CompanyProfile

_SUMMARY_PROMPT = """You are a B2B research analyst. Using ONLY the JSON facts below, \
write a factual company summary of at most 150 words. Do not invent anything. \
If a fact is missing, say it is unknown.

FACTS:
{facts}
"""

_SIGNAL_PROMPT = """You score how strongly a company shows buying signals for a staffing / \
recruitment service. Using ONLY the JSON facts, respond with strict JSON:
{{"adjustment": <number between {lo} and {hi}>, "rationale": "<one sentence>"}}
Positive adjustment = stronger signal (recent funding, many open roles, headcount growth). \
Negative = weak or no signal.

ICP SIGNALS: {signals}
FACTS: {facts}
"""

_CAND_SUMMARY_PROMPT = """You are a technical recruiter. Using ONLY the JSON facts below, \
write a factual candidate summary of at most 150 words. Do not invent anything. \
If a fact is missing, say it is unknown.

FACTS:
{facts}
"""

_CAND_ASSESS_PROMPT = """You judge how well a candidate fits a job rubric. Using ONLY the \
JSON facts, respond with strict JSON:
{{"adjustment": <number between {lo} and {hi}>, "rationale": "<one sentence>"}}
Positive adjustment = stronger evidence of fit (must-have skills demonstrated, relevant \
open-source work, recent activity, seniority match). Negative = weak or missing evidence.

RUBRIC: {rubric}
FACTS: {facts}
"""


class OllamaLLM(LLM):
    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def _generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    async def summarize_research(
        self, profile: CompanyProfile, *, prompt: str | None = None
    ) -> str:
        facts = profile.model_dump_json(indent=2)
        template = prompt or _SUMMARY_PROMPT
        try:
            text = await self._generate(template.format(facts=facts))
            return text or "Summary unavailable."
        except Exception:  # noqa: BLE001 - degrade gracefully
            return "Summary unavailable (LLM error); see structured profile."

    async def interpret_signals(
        self, profile: CompanyProfile, icp: dict, *, prompt: str | None = None
    ) -> tuple[float, str]:
        cap = float(icp.get("max_llm_adjustment", 10))
        template = prompt or _SIGNAL_PROMPT
        rendered = template.format(
            lo=-cap,
            hi=cap,
            signals=json.dumps(icp.get("signals", {})),
            facts=profile.model_dump_json(),
        )
        try:
            raw = await self._generate(rendered)
            data = _parse_json_object(raw)
            adj = float(data.get("adjustment", 0.0))
            adj = max(-cap, min(cap, adj))
            rationale = str(data.get("rationale", "")).strip() or "no rationale returned"
            return adj, rationale
        except Exception:  # noqa: BLE001
            return 0.0, "LLM unavailable; deterministic score only"

    # --- recruiting -----------------------------------------------------

    async def summarize_candidate(self, profile) -> str:
        try:
            text = await self._generate(
                _CAND_SUMMARY_PROMPT.format(facts=profile.model_dump_json(indent=2))
            )
            return text or "Summary unavailable."
        except Exception:  # noqa: BLE001
            return "Summary unavailable (LLM error); see structured profile."

    async def assess_candidate(self, profile, rubric: dict) -> tuple[float, str]:
        cap = float(rubric.get("max_llm_adjustment", 10))
        prompt = _CAND_ASSESS_PROMPT.format(
            lo=-cap,
            hi=cap,
            rubric=json.dumps(
                {k: rubric.get(k) for k in ("seniority", "skills", "location", "signals")}
            ),
            facts=profile.model_dump_json(),
        )
        try:
            data = _parse_json_object(await self._generate(prompt))
            adj = max(-cap, min(cap, float(data.get("adjustment", 0.0))))
            rationale = str(data.get("rationale", "")).strip() or "no rationale returned"
            return adj, rationale
        except Exception:  # noqa: BLE001
            return 0.0, "LLM unavailable; deterministic score only"


def _parse_json_object(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])
