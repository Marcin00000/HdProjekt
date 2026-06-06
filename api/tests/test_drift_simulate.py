"""Monitoring driftu — baseline treningu vs silver (nie log prognoz)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.config import PROJECT_ROOT
from src.monitoring.baseline import (
    BASELINE_META_PATH,
    SIMULATED_CURRENT_PATH,
    SIMULATION_META_PATH,
    TRAINING_BASELINE_PATH,
    clear_drift_simulation,
    save_training_baseline,
)
from src.monitoring.drift_simulate import SCENARIOS, simulate_drift
from src.monitoring.evidently_report import DRIFT_METRICS_PATH, compute_drift_report
from src.train.features import RAW_FEATURE_COLUMNS, TARGET

pytest.importorskip("evidently")

SILVER = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"


def _minimal_silver(n: int = 2000) -> pd.DataFrame:
    rng = __import__("numpy").random.default_rng(0)
    return pd.DataFrame(
        {
            "job_title": rng.choice(["Dev", "Analyst"], n),
            "experience_years": rng.integers(1, 15, n),
            "education_level": rng.choice(["Bachelor", "Master"], n),
            "skills_count": rng.integers(3, 20, n),
            "industry": rng.choice(["Technology", "Finance"], n),
            "company_size": rng.choice(["Small", "Medium"], n),
            "location": rng.choice(["USA", "UK"], n),
            "remote_work": rng.choice(["Yes", "No"], n),
            "certifications": rng.integers(0, 5, n),
            "salary": rng.integers(80_000, 200_000, n),
        }
    )


@pytest.fixture
def market_data_fixture():
    proc = PROJECT_ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, bytes | None] = {}
    for path in (
        SILVER,
        TRAINING_BASELINE_PATH,
        BASELINE_META_PATH,
        SIMULATED_CURRENT_PATH,
        SIMULATION_META_PATH,
        DRIFT_METRICS_PATH,
    ):
        backups[path] = path.read_bytes() if path.is_file() else None

    silver = _minimal_silver(2000)
    silver.to_parquet(SILVER, index=False)
    X = silver[[c for c in RAW_FEATURE_COLUMNS if c in silver.columns]]
    save_training_baseline(X, silver[TARGET])

    clear_drift_simulation()
    yield

    for path, data in backups.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)


def test_simulate_writes_silver_not_prediction_log(market_data_fixture):
    result = simulate_drift("salary_market_up", count=1500)
    assert result["rows_written"] >= 500
    assert SIMULATED_CURRENT_PATH.is_file()
    assert not str(result.get("simulated_path", "")).endswith("prediction_log.jsonl")
    sim = pd.read_parquet(SIMULATED_CURRENT_PATH)
    base = pd.read_parquet(TRAINING_BASELINE_PATH)
    assert sim[TARGET].mean() > base[TARGET].mean() * 1.05


def test_drift_report_baseline_vs_simulated_silver(market_data_fixture):
    simulate_drift("salary_features_combo", count=1500)
    report = compute_drift_report()
    assert report["comparison"] == "training_baseline vs current_silver"
    assert report["reference_rows"] >= 500
    assert report["current_rows"] >= 500
    assert DRIFT_METRICS_PATH.is_file()
    assert report.get("report_url", "").startswith("/reports/")
    assert report.get("drift_alert") is True


def test_report_without_baseline_fails_gracefully(market_data_fixture):
    TRAINING_BASELINE_PATH.unlink(missing_ok=True)
    clear_drift_simulation()
    report = compute_drift_report()
    assert report["status"] == "insufficient_data"
    assert "baseline" in report["message"].lower()


def test_scenarios_include_salary_market_up():
    assert "salary_market_up" in SCENARIOS
