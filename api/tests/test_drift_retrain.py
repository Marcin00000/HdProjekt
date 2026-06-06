"""Decyzja o retreningu przy drift i audyt."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src.config import PROJECT_ROOT
from src.monitoring.baseline import (
    TRAINING_BASELINE_PATH,
    save_training_baseline,
)
from src.monitoring.drift_retrain import (
    DRIFT_RETRAIN_LAST_PATH,
    check_drift_and_retrain,
    should_retrain,
)
from src.monitoring.params import load_monitoring_config
from src.train.features import RAW_FEATURE_COLUMNS, TARGET

pytest.importorskip("evidently")

SILVER = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"


def _silver(n: int = 1500) -> pd.DataFrame:
    rng = __import__("numpy").random.default_rng(1)
    return pd.DataFrame(
        {
            "job_title": rng.choice(["Dev"], n),
            "experience_years": rng.integers(1, 10, n),
            "education_level": rng.choice(["Master"], n),
            "skills_count": rng.integers(5, 15, n),
            "industry": rng.choice(["Technology"], n),
            "company_size": rng.choice(["Medium"], n),
            "location": rng.choice(["USA"], n),
            "remote_work": rng.choice(["Yes"], n),
            "certifications": rng.integers(0, 3, n),
            "salary": rng.integers(90_000, 120_000, n),
        }
    )


@pytest.fixture
def market_with_baseline():
    proc = PROJECT_ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    backups = {}
    for p in (SILVER, TRAINING_BASELINE_PATH, DRIFT_RETRAIN_LAST_PATH):
        backups[p] = p.read_bytes() if p.is_file() else None

    df = _silver(1500)
    df.to_parquet(SILVER, index=False)
    X = df[RAW_FEATURE_COLUMNS]
    save_training_baseline(X, df[TARGET])

    yield

    for p, data in backups.items():
        if data is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(data)


def test_should_retrain_requires_alert():
    cfg = load_monitoring_config()
    assert should_retrain({"drift_alert": False, "status": "ok"}, cfg, manual=True) is False
    assert should_retrain({"drift_alert": True, "status": "alert"}, cfg, manual=True) is True


def test_should_retrain_auto_disabled_without_manual():
    cfg = {**load_monitoring_config(), "auto_retrain_enabled": False}
    assert should_retrain({"drift_alert": True, "status": "alert"}, cfg, manual=False) is False


@patch("src.portal.operations.run_train")
@patch("src.monitoring.drift_retrain.compute_drift_report")
def test_check_drift_retrain_when_alert(mock_report, mock_train, market_with_baseline):
    mock_report.side_effect = [
        {
            "drift_alert": True,
            "status": "alert",
            "share_drifted_columns": 0.8,
            "message": "alert",
            "current_rows": 1500,
        },
        {
            "drift_alert": False,
            "status": "ok",
            "share_drifted_columns": 0.1,
            "message": "ok",
            "current_rows": 1500,
        },
    ]
    mock_train.return_value = {
        "best_run_id": "run-test",
        "metrics": {"rmse": 1000},
        "combinations_tested": 1,
    }

    result = check_drift_and_retrain(manual=True)
    assert result["retrained"] is True
    mock_train.assert_called_once()
    assert DRIFT_RETRAIN_LAST_PATH.is_file()


@patch("src.portal.operations.run_train")
@patch("src.monitoring.drift_retrain.compute_drift_report")
def test_skip_when_no_drift(mock_report, mock_train, market_with_baseline):
    mock_report.return_value = {
        "drift_alert": False,
        "status": "ok",
        "share_drifted_columns": 0.0,
        "message": "ok",
        "current_rows": 1500,
    }
    result = check_drift_and_retrain(manual=True)
    assert result["retrained"] is False
    mock_train.assert_not_called()
