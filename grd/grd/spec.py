"""AgentSpec - loads an `agents/<name>/` config folder into a typed object.

The platform stays generic; a spec is the per-agent, mostly-YAML configuration
that makes it a concrete agent (which capabilities, which ICP, which prompts,
which gate thresholds).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AgentSpec:
    name: str
    root: Path
    config: dict
    workflow: dict

    # --- loading ------------------------------------------------------

    @classmethod
    def load(cls, name: str, agents_dir: Path) -> "AgentSpec":
        root = agents_dir / name
        cfg_path = root / "config.yaml"
        if not cfg_path.exists():
            available = sorted(p.name for p in agents_dir.glob("*") if p.is_dir())
            raise FileNotFoundError(
                f"agent {name!r} not found in {agents_dir} (have: {available})"
            )
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        wf_path = root / "workflow.yaml"
        workflow = (
            yaml.safe_load(wf_path.read_text(encoding="utf-8")) if wf_path.exists() else {}
        ) or {}
        return cls(name=name, root=root, config=config, workflow=workflow)

    @classmethod
    def load_or_none(cls, name: str, agents_dir: Path) -> "AgentSpec | None":
        try:
            return cls.load(name, agents_dir)
        except FileNotFoundError:
            return None

    # --- research ---------------------------------------------------

    def tools_allow(self) -> list[str]:
        rel = self.config.get("research", {}).get("tools_allow", "research/tools.allow")
        path = self.root / rel
        if not path.exists():
            return []
        out: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
        return out

    def summary_prompt(self) -> str | None:
        return self._read_prompt(self.config.get("research", {}).get("prompt"))

    def research_setting(self, key: str, default):
        return self.config.get("research", {}).get(key, default)

    # --- scoring ---------------------------------------------------

    def icp_name(self) -> str:
        return self.config.get("scoring", {}).get("default_icp", "grd_staffing")

    def icp_dir(self) -> Path:
        return self.root / "scoring" / "icp"

    def signal_prompt(self) -> str | None:
        return self._read_prompt(self.config.get("scoring", {}).get("prompt"))

    # --- gates / limits ------------------------------------------

    def gate_a_threshold(self) -> float | None:
        v = self.config.get("gates", {}).get("gate_a_auto_threshold")
        return float(v) if v is not None else None

    # --- workflow --------------------------------------------------

    def active_steps(self) -> list[str]:
        return [s["id"] for s in self.workflow.get("steps", []) if s.get("status") == "active"]

    # --- helpers -------------------------------------------------

    def _read_prompt(self, rel: str | None) -> str | None:
        if not rel:
            return None
        path = self.root / rel
        return path.read_text(encoding="utf-8") if path.exists() else None
