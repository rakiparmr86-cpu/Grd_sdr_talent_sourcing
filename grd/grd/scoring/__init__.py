from __future__ import annotations

from pathlib import Path

import yaml

_REQUIRED_KEYS = {"industries", "size_bands", "geographies", "signals", "weights", "thresholds"}


def load_icp(name: str, icp_dir: Path) -> dict:
    path = icp_dir / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in icp_dir.glob("*.yaml"))
        raise FileNotFoundError(f"ICP {name!r} not found in {icp_dir}. Available: {available}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"ICP {name!r} missing keys: {sorted(missing)}")
    for tier in ("A", "B", "C", "qualify"):
        if tier not in data["thresholds"]:
            raise ValueError(f"ICP {name!r} thresholds missing {tier!r}")
    return data


__all__ = ["load_icp"]
