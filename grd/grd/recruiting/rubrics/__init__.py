from __future__ import annotations

from pathlib import Path

import yaml

_REQUIRED_KEYS = {"seniority", "location", "skills", "signals", "weights", "thresholds"}


def load_rubric(name: str, rubric_dir: Path) -> dict:
    path = rubric_dir / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in rubric_dir.glob("*.yaml"))
        raise FileNotFoundError(
            f"Rubric {name!r} not found in {rubric_dir}. Available: {available}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Rubric {name!r} missing keys: {sorted(missing)}")
    for tier in ("A", "B", "C", "qualify"):
        if tier not in data["thresholds"]:
            raise ValueError(f"Rubric {name!r} thresholds missing {tier!r}")
    return data


__all__ = ["load_rubric"]
