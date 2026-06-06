"""Etapy pipeline DVC (prepare, train)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.cleaning.preprocess import clean_dataframe
from src.config import PROJECT_ROOT
from src.etl.lake_io import read_raw_csv
from src.train.train_model import load_params, train_xgboost

RAW_CSV = PROJECT_ROOT / "job_salary_prediction_dataset.csv"
SILVER_PARQUET = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"
METRICS_JSON = PROJECT_ROOT / "data" / "processed" / "metrics.json"
PREDICTIONS_CSV = PROJECT_ROOT / "data" / "processed" / "predictions.csv"
def _prepare_params(params: dict[str, Any]) -> dict[str, Any]:
    return params.get("prepare") or {}


def run_prepare(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Raw CSV -> silver parquet (lokalnie)."""
    params = params or load_params()
    prep = _prepare_params(params)

    if RAW_CSV.is_file():
        raw = pd.read_csv(RAW_CSV)
        source = str(RAW_CSV)
    else:
        from src.config import AzureStorageConfig

        raw = read_raw_csv(AzureStorageConfig())
        source = "azure_raw"

    silver, stats = clean_dataframe(
        raw,
        salary_quantile_low=float(prep.get("salary_quantile_low", 0.01)),
        salary_quantile_high=float(prep.get("salary_quantile_high", 0.99)),
        max_experience_years=int(prep.get("max_experience_years", 40)),
    )

    SILVER_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(SILVER_PARQUET, index=False)

    summary = {
        "source": source,
        "rows_in": stats.rows_in,
        "rows_out": stats.rows_out,
        "duplicates_removed": stats.duplicates_removed,
        "outliers_removed": stats.outliers_removed,
        "invalid_removed": stats.invalid_removed,
    }
    return summary


def _save_predictions(
    silver: pd.DataFrame,
    preprocessor,
    model,
    params: dict[str, Any],
) -> None:
    from src.train.features import prepare_train_test

    random_state = int(params.get("random_state", 42))
    test_size = float(params.get("test_size", 0.2))
    _, X_test, _, y_test = prepare_train_test(silver, test_size, random_state)
    X_test_t = preprocessor.transform(X_test)
    pred = model.predict(X_test_t)

    out = pd.DataFrame(
        {
            "actual_salary": y_test.values,
            "predicted_salary": pred,
            "residual": y_test.values - pred,
        }
    )
    PREDICTIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(PREDICTIONS_CSV, index=False)


def run_train(
    params: dict[str, Any] | None = None,
    *,
    register_model: bool = True,
    force_tuning: bool | None = None,
) -> dict[str, Any]:
    """Silver parquet -> model, metryki, prognozy testowe."""
    params = params or load_params()
    if not SILVER_PARQUET.is_file():
        raise FileNotFoundError(f"Brak silver: {SILVER_PARQUET} — uruchom etap prepare")

    silver = pd.read_parquet(SILVER_PARQUET)
    import os

    tuning_cfg = params.get("tuning") or {}
    if force_tuning is None:
        fast = os.getenv("DVC_FAST_TRAIN") == "1"
        dvc_cfg = params.get("dvc") or {}
        if fast or dvc_cfg.get("fast_train", False):
            force_tuning = False
        else:
            force_tuning = bool(tuning_cfg.get("enabled", False))

    bundle = train_xgboost(
        silver,
        params=params,
        register_model=register_model,
        force_tuning=force_tuning,
    )

    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.write_text(
        json.dumps(bundle["metrics"], indent=2),
        encoding="utf-8",
    )

    import joblib

    preprocessor = joblib.load(PROJECT_ROOT / "models" / "preprocessor.joblib")
    model = joblib.load(PROJECT_ROOT / "models" / "xgboost_model.joblib")
    _save_predictions(silver, preprocessor, model, params)

    return bundle


def write_params_snapshot(path: Path | None = None) -> None:
    """Kopia params.yaml do artefaktow (opcjonalnie)."""
    path = path or PROJECT_ROOT / "data" / "processed" / "params_snapshot.yaml"
    src = PROJECT_ROOT / "params.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
