"""Odczyt/zapis params.yaml + nadpisania tuningu (zapis w data/processed w Dockerze)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.config import PROJECT_ROOT

PARAMS_PATH = PROJECT_ROOT / "params.yaml"
TUNING_OVERRIDE_PATH = PROJECT_ROOT / "data" / "processed" / "params_tuning_override.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_merged_params() -> dict[str, Any]:
    """params.yaml (bazowy) + opcjonalny override tuningu z portalu."""
    base = _read_yaml(PARAMS_PATH)
    override = _read_yaml(TUNING_OVERRIDE_PATH)
    if not override:
        return base
    merged = copy.deepcopy(base)
    if "tuning" in override:
        merged["tuning"] = override["tuning"]
    return merged


def load_params_file() -> dict[str, Any]:
    """API / formularz — zawsze scalone parametry."""
    return load_merged_params()


def save_tuning_config(
    *,
    enabled: bool,
    param_grid: dict[str, list[Any]],
) -> dict[str, Any]:
    TUNING_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tuning": {"enabled": enabled, "param_grid": param_grid},
        "_saved_from": "portal",
    }
    with open(TUNING_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return load_merged_params()
