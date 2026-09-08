from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grd.recruiting.schemas import CandidateProfile
    from grd.schemas import CompanyProfile


class LLM(abc.ABC):
    """Narrow interface shared by every agent. Two jobs per vertical."""

    # --- SDR / company sourcing ------------------------------------------
    @abc.abstractmethod
    async def summarize_research(
        self, profile: CompanyProfile, *, prompt: str | None = None
    ) -> str:
        """<= ~150 word factual summary grounded in the company profile.

        `prompt` is an optional template (from the agent config folder); when
        absent the implementation's built-in default is used.
        """

    @abc.abstractmethod
    async def interpret_signals(
        self, profile: CompanyProfile, icp: dict, *, prompt: str | None = None
    ) -> tuple[float, str]:
        """Read buying signals -> (adjustment, rationale), adjustment bounded by caller."""

    # --- recruiting / talent sourcing ----------------------------------
    @abc.abstractmethod
    async def summarize_candidate(self, profile: CandidateProfile) -> str:
        """<= ~150 word factual summary grounded in the candidate profile."""

    @abc.abstractmethod
    async def assess_candidate(
        self, profile: CandidateProfile, rubric: dict
    ) -> tuple[float, str]:
        """Read fit evidence -> (adjustment, rationale), adjustment bounded by caller."""
