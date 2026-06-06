"""Trening szybki — regresja na bledzie combinations / bundle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("mlflow")

from src.train.train_model import train_xgboost


def _silver_frame(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "job_title": rng.choice(["Dev", "Analyst"], n),
            "experience_years": rng.integers(1, 15, n),
            "education_level": rng.choice(["Bachelor", "Master"], n),
            "skills_count": rng.integers(3, 20, n),
            "industry": rng.choice(["Tech", "Finance"], n),
            "company_size": rng.choice(["Small", "Medium"], n),
            "location": rng.choice(["USA", "UK"], n),
            "remote_work": rng.choice(["Yes", "No"], n),
            "certifications": rng.integers(0, 5, n),
            "salary": rng.integers(80_000, 200_000, n),
        }
    )


@patch("src.train.train_model.joblib.dump")
@patch("src.train.train_model.mlflow.register_model")
@patch("src.train.train_model._fit_and_log_run")
@patch("src.train.train_model.ensure_experiment")
@patch("src.train.train_model.configure_mlflow")
def test_train_fast_sets_combinations_tested(
    _cfg, _exp, mock_fit, _reg, _dump,
):
    mock_fit.return_value = (
        MagicMock(),
        {"rmse": 1.0, "mae": 1.0, "mape_pct": 1.0, "rmse_pct_of_mean": 1.0, "median_ae": 1.0, "r2": 0.9},
        "run-1",
        "runs:/x/model",
    )
    bundle = train_xgboost(
        _silver_frame(),
        params={"random_state": 42, "test_size": 0.2, "n_estimators": 10, "max_depth": 3, "learning_rate": 0.1},
        register_model=False,
        force_tuning=False,
    )
    assert bundle["combinations_tested"] == 1
    assert bundle["tuning_enabled"] is False
