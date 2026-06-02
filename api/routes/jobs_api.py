"""REST API — dashboard, zadania pipeline, status systemu, params."""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.dashboard_data import get_dashboard_data
from api.predictor import MODEL_PATH, PREPROCESSOR_PATH, predictor
from api.services.job_runner import job_runner
from src.config import PROJECT_ROOT, local_raw_data_path
from src.portal.data_loader import GOLD_BY_LOCATION, SILVER_PATH
from src.portal.operations import JOB_HANDLERS
from src.portal.params_io import load_params_file, save_tuning_config
from src.portal.predict_options import get_predict_field_options
from src.train.train_model import load_params

router = APIRouter(prefix="/api", tags=["operations"])

PREFECT_UI_URL = os.getenv("PREFECT_UI_URL", "http://127.0.0.1:4200")


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., description="prepare | etl | train | dvc_repro | ...")
    upload_lake: bool = False
    skip_sql: bool = False
    fast: bool = False
    tuning_enabled: bool | None = None
    param_grid: dict[str, list[Any]] | None = None


class TuningParamsUpdate(BaseModel):
    enabled: bool = True
    param_grid: dict[str, list[Any]] = Field(default_factory=dict)
    n_estimators: list[int] | None = None
    max_depth: list[int] | None = None
    learning_rate: list[float] | None = None


@router.get("/dashboard")
def api_dashboard():
    return get_dashboard_data()


@router.get("/predict/options")
def predict_options():
    return get_predict_field_options()


@router.get("/params")
def get_params():
    return load_params_file()


@router.put("/params/tuning")
def update_tuning(body: TuningParamsUpdate):
    grid = dict(body.param_grid)
    if body.n_estimators is not None:
        grid["n_estimators"] = body.n_estimators
    if body.max_depth is not None:
        grid["max_depth"] = body.max_depth
    if body.learning_rate is not None:
        grid["learning_rate"] = body.learning_rate
    if not grid:
        current = load_params()
        grid = (current.get("tuning") or {}).get("param_grid") or {}
    data = save_tuning_config(enabled=body.enabled, param_grid=grid)
    return {"ok": True, "tuning": data.get("tuning")}


@router.get("/system/status")
def system_status():
    raw = local_raw_data_path()
    return {
        "model_loaded": predictor.is_loaded,
        "job_busy": job_runner.is_busy(),
        "prefect_ui_url": PREFECT_UI_URL,
        "mlflow_url": os.getenv("MLFLOW_PUBLIC_URL", "http://127.0.0.1:5000"),
        "paths": {
            "raw_csv": raw.is_file(),
            "silver": SILVER_PATH.is_file(),
            "gold": GOLD_BY_LOCATION.is_file(),
            "preprocessor": PREPROCESSOR_PATH.is_file(),
            "model": MODEL_PATH.is_file(),
            "mlflow_db": (PROJECT_ROOT / "data" / "mlflow" / "mlflow.db").is_file(),
        },
        "available_jobs": list(JOB_HANDLERS.keys()),
    }


@router.get("/jobs")
def list_jobs():
    return {"jobs": job_runner.list_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    record = job_runner.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania")
    return asdict(record)


@router.post("/jobs")
def create_job(body: JobCreateRequest):
    kwargs: dict[str, Any] = {}
    if body.job_type in ("prepare", "prepare_lake"):
        kwargs["upload_lake"] = body.upload_lake or body.job_type == "prepare_lake"
    if body.job_type.startswith("etl"):
        kwargs["skip_sql"] = body.skip_sql or body.job_type == "etl_skip_sql"
    if "fast" in body.job_type or body.fast:
        kwargs["fast"] = True

    if body.job_type.startswith("train"):
        params = load_params()
        if body.tuning_enabled is not None:
            tuning = params.get("tuning") or {}
            tuning["enabled"] = body.tuning_enabled
            params["tuning"] = tuning
        if body.param_grid:
            tuning = params.get("tuning") or {}
            tuning["param_grid"] = body.param_grid
            params["tuning"] = tuning
        kwargs["params_override"] = params

    try:
        record = job_runner.submit(body.job_type, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(record)


@router.post("/model/reload")
def reload_model():
    try:
        predictor.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"model_loaded": predictor.is_loaded}
