"""Odczyt/zapis params.yaml (tuning z portalu)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import PROJECT_ROOT

PARAMS_PATH = PROJECT_ROOT / "params.yaml"


def load_params_file() -> dict[str, Any]:
    if not PARAMS_PATH.is_file():
        return {}
    with open(PARAMS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_tuning_config(
    *,
    enabled: bool,
    param_grid: dict[str, list[Any]],
    base_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = load_params_file()
    if base_params:
        for key, val in base_params.items():
            if key not in ("tuning", "prepare", "dvc"):
                data[key] = val
    data["tuning"] = {"enabled": enabled, "param_grid": param_grid}
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return data
