"""Parametry monitoringu z params.yaml."""

from __future__ import annotations

from typing import Any

from src.train.train_model import load_params

DEFAULT_MONITORING: dict[str, Any] = {
    "drift_threshold": 0.5,
    "min_current_rows": 1000,
    "reference_sample_size": 5000,
    "current_sample_size": 5000,
    "default_simulate_count": 5000,
}


def load_monitoring_config() -> dict[str, Any]:
    params = load_params()
    cfg = dict(DEFAULT_MONITORING)
    cfg.update(params.get("monitoring") or {})
    return cfg
