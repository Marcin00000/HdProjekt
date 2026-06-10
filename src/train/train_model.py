"""Trenowanie XGBoost z logowaniem do MLflow i tuningiem hiperparametrow."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from src.config import PROJECT_ROOT
from src.mlflow_config import (
    EXPERIMENT_NAME,
    REGISTERED_MODEL_NAME,
    configure_mlflow,
    ensure_experiment,
)
from src.portal.job_context import log, progress
from src.train.features import build_preprocessor, prepare_train_test

MODELS_DIR = PROJECT_ROOT / "models"

XGB_PARAM_KEYS = (
    "n_estimators",
    "max_depth",
    "learning_rate",
    "subsample",
    "colsample_bytree",
    "reg_alpha",
    "reg_lambda",
    "min_child_weight",
)


def load_params(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    from src.portal.params_io import load_merged_params

    return load_merged_params()


def evaluate_model(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100)
    mean_salary = float(np.mean(y_true))
    return {
        "rmse": rmse,
        "mae": mae,
        "mape_pct": mape,
        "rmse_pct_of_mean": float(rmse / mean_salary * 100) if mean_salary else 0.0,
        "median_ae": float(np.median(np.abs(y_true - y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def _xgb_params(hyperparams: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = {**defaults, **hyperparams}
    out: dict[str, Any] = {
        "random_state": int(merged.get("random_state", 42)),
        "n_jobs": -1,
        "objective": "reg:squarederror",
    }
    for key in XGB_PARAM_KEYS:
        if key in merged:
            val = merged[key]
            out[key] = int(val) if key in ("n_estimators", "max_depth", "min_child_weight") else float(val)
    return out


def _iter_param_grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(param_grid.keys())
    values = [param_grid[k] if isinstance(param_grid[k], list) else [param_grid[k]] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _fit_and_log_run(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
    y_train: pd.Series,
    y_val: pd.Series,
    hyperparams: dict[str, Any],
    defaults: dict[str, Any],
    preprocessor,
) -> tuple[XGBRegressor, dict[str, float], str, str]:
    """Trenuje model i loguje do MLflow. Walidacja na zbiorze walidacyjnym (nie testowym)."""
    X_train_t = preprocessor.fit_transform(X_train)
    X_val_t = preprocessor.transform(X_val)

    xgb_kw = _xgb_params(hyperparams, defaults)
    early_stop = int(defaults.get("early_stopping_rounds", 0))
    fit_kw: dict[str, Any] = {}
    if early_stop > 0:
        xgb_kw["early_stopping_rounds"] = early_stop
        fit_kw["eval_set"] = [(X_val_t, y_val)]
        fit_kw["verbose"] = False

    model = XGBRegressor(**xgb_kw)

    run_name = (
        f"xgb_n{xgb_kw['n_estimators']}_d{xgb_kw['max_depth']}"
        f"_lr{xgb_kw['learning_rate']}"
    )

    with mlflow.start_run(run_name=run_name):
        model.fit(X_train_t, y_train, **fit_kw)
        pred = model.predict(X_val_t)
        metrics = evaluate_model(y_val, pred)

        for key, value in hyperparams.items():
            mlflow.log_param(key, value)
        for key, value in metrics.items():
            mlflow.log_metric(key, value)

        model_info = mlflow.xgboost.log_model(model, name="model")
        run_id = mlflow.active_run().info.run_id
        model_uri = model_info.model_uri

    return model, metrics, run_id, model_uri


def train_xgboost(
    silver: pd.DataFrame,
    params: dict[str, Any] | None = None,
    register_model: bool = True,
    force_tuning: bool | None = None,
) -> dict[str, Any]:
    """Trenuje model; opcjonalnie przeszukuje siatke hiperparametrow z params.yaml.

    Podział danych: train (64%) / validation (16%) / test (20%).
    - Validation: uzywany do early stopping i wyboru najlepszych hiperparametrow.
    - Test: uzywany WYLACZNIE do koncowej ewaluacji najlepszego modelu.
    """
    params = params or load_params()
    progress(2, "Przygotowanie danych treningowych...")
    configure_mlflow()
    ensure_experiment()
    mlflow.set_experiment(EXPERIMENT_NAME)

    random_state = int(params.get("random_state", 42))
    defaults = {**params, "random_state": random_state}

    # Podział 3-stronny: train / val / test
    # Najpierw wydzielamy test (20%), potem z reszty wydzielamy val (20% z 80% = 16% calości)
    X_trainval, X_test, y_trainval, y_test = prepare_train_test(
        silver,
        test_size=float(params.get("test_size", 0.2)),
        random_state=random_state,
    )
    from sklearn.model_selection import train_test_split as _split

    X_train, X_val, y_train, y_val = _split(
        X_trainval, y_trainval, test_size=0.2, random_state=random_state,
    )

    from src.monitoring.baseline import save_training_baseline

    save_training_baseline(X_train, y_train)
    log(
        f"Baseline monitoringu zapisany ({len(X_train):,} wierszy treningowych). "
        f"Walidacja: {len(X_val):,}, Test: {len(X_test):,}."
    )

    preprocessor = build_preprocessor()

    tuning_cfg = params.get("tuning") or {}
    use_tuning = force_tuning if force_tuning is not None else bool(tuning_cfg.get("enabled", False))

    best: dict[str, Any] = {"rmse": float("inf")}
    runs_summary: list[dict[str, Any]] = []

    if use_tuning:
        grid = tuning_cfg.get("param_grid") or {}
        combinations = _iter_param_grid(grid)
        total = len(combinations)
        log(f"Strojenie hiperparametrow: {total} kombinacji w siatce")
        for idx, hyperparams in enumerate(combinations, start=1):
            pct = int(10 + (idx - 1) / max(total, 1) * 80)
            progress(pct, f"Strojenie — kombinacja {idx} z {total}")
            preproc = build_preprocessor()
            model, metrics, run_id, model_uri = _fit_and_log_run(
                X_train, X_val, y_train, y_val, hyperparams, defaults, preproc
            )
            entry = {"run_id": run_id, "model_uri": model_uri, **hyperparams, **metrics}
            runs_summary.append(entry)
            log(
                f"  n={hyperparams.get('n_estimators')} depth={hyperparams.get('max_depth')} "
                f"lr={hyperparams.get('learning_rate')} -> "
                f"RMSE={metrics['rmse']:,.0f} ({metrics['rmse_pct_of_mean']:.1f}% sredniej) "
                f"MAPE={metrics['mape_pct']:.2f}% R2={metrics['r2']:.4f}"
            )
            if metrics["rmse"] < best.get("rmse", float("inf")):
                best = {
                    "run_id": run_id,
                    "model_uri": model_uri,
                    "hyperparams": hyperparams,
                    "model": model,
                    "preprocessor": preproc,
                    "metrics": metrics,
                    "rmse": metrics["rmse"],
                }
    else:
        hyperparams = {k: params[k] for k in XGB_PARAM_KEYS if k in params}
        log(
            "Trening szybki (bez strojenia): "
            f"n_estimators={hyperparams.get('n_estimators')}, "
            f"max_depth={hyperparams.get('max_depth')}, "
            f"learning_rate={hyperparams.get('learning_rate')}"
        )
        progress(20, "Trening szybki — przygotowanie modelu")
        preproc = build_preprocessor()
        progress(50, "Trening szybki — trenowanie XGBoost")
        model, metrics, run_id, model_uri = _fit_and_log_run(
            X_train, X_val, y_train, y_val, hyperparams, defaults, preproc
        )
        progress(85, "Trening szybki — zapis wynikow")
        entry = {"run_id": run_id, "model_uri": model_uri, **hyperparams, **metrics}
        runs_summary.append(entry)
        log(
            f"  RMSE={metrics['rmse']:,.0f} ({metrics['rmse_pct_of_mean']:.1f}% sredniej) "
            f"MAPE={metrics['mape_pct']:.2f}% R2={metrics['r2']:.4f}"
        )
        best = {
            "run_id": run_id,
            "model_uri": model_uri,
            "hyperparams": hyperparams,
            "model": model,
            "preprocessor": preproc,
            "metrics": metrics,
            "rmse": metrics["rmse"],
        }

    # Końcowa ewaluacja najlepszego modelu na ZBIORZE TESTOWYM (nigdy nie widziany)
    progress(90, "Ewaluacja koncowa na zbiorze testowym...")
    X_test_t = best["preprocessor"].transform(X_test)
    test_pred = best["model"].predict(X_test_t)
    test_metrics = evaluate_model(y_test, test_pred)
    best["metrics"] = test_metrics
    log(
        f"  Metryki TESTOWE (uczciwe): "
        f"RMSE={test_metrics['rmse']:,.0f} ({test_metrics['rmse_pct_of_mean']:.1f}%) "
        f"MAPE={test_metrics['mape_pct']:.2f}% R2={test_metrics['r2']:.4f}"
    )

    progress(92, "Zapis modelu na dysk...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best["preprocessor"], MODELS_DIR / "preprocessor.joblib")
    joblib.dump(best["model"], MODELS_DIR / "xgboost_model.joblib")

    bundle = {
        "best_run_id": best["run_id"],
        "best_hyperparams": best["hyperparams"],
        "metrics": best["metrics"],
        "all_runs": runs_summary,
        "tuning_enabled": use_tuning,
        "combinations_tested": len(runs_summary),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
    }

    from src.processed_artifacts import TRAINING_SUMMARY

    metrics_path = TRAINING_SUMMARY
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    if register_model:
        try:
            mlflow.register_model(best["model_uri"], REGISTERED_MODEL_NAME)
        except Exception as exc:
            log(f"  UWAGA: rejestracja modelu w MLflow nie powiodla sie: {exc}")

    progress(100, "Trening zakonczony.")
    return bundle
