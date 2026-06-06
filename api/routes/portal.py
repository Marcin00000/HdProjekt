"""Trasy HTML portalu (faza 7) — pelna obsluga operacyjna."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.predictor import predictor
from api.schemas import SalaryPredictRequest
from src.config import PROJECT_ROOT
from src.portal.paths_status import get_paths_status

router = APIRouter(tags=["portal"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

MLFLOW_PUBLIC_URL = os.getenv("MLFLOW_PUBLIC_URL", "http://127.0.0.1:5000")
PREFECT_PUBLIC_URL = os.getenv(
    "PREFECT_PUBLIC_URL",
    os.getenv("PREFECT_UI_URL", "http://127.0.0.1:4200"),
)
PROCESSED = PROJECT_ROOT / "data" / "processed"


def _paths() -> dict[str, bool]:
    paths = get_paths_status()
    paths["mlflow_db"] = (PROJECT_ROOT / "data" / "mlflow" / "mlflow.db").is_file()
    return paths


def _ctx(request: Request, **extra):
    base = {
        "request": request,
        "mlflow_url": MLFLOW_PUBLIC_URL,
        "prefect_ui_url": PREFECT_PUBLIC_URL,
        "model_loaded": predictor.is_loaded,
        "paths": _paths(),
    }
    base.update(extra)
    return base


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", _ctx(request))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request))


def _predict_ctx(request: Request, **extra):
    from src.portal.predict_options import get_predict_field_options

    return _ctx(
        request,
        options=get_predict_field_options(),
        **extra,
    )


@router.get("/predict", response_class=HTMLResponse)
def predict_page(
    request: Request,
    result: float | None = None,
    error: str | None = None,
    warning: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "predict.html",
        _predict_ctx(request, result=result, error=error, warning=warning),
    )


def _form_inputs(
    *,
    job_title: str,
    experience_years: int,
    education_level: str,
    skills_count: int,
    industry: str,
    company_size: str,
    location: str,
    remote_work: str,
    certifications: int,
) -> dict[str, str | int]:
    return {
        "job_title": job_title,
        "experience_years": experience_years,
        "education_level": education_level,
        "skills_count": skills_count,
        "industry": industry,
        "company_size": company_size,
        "location": location,
        "remote_work": remote_work,
        "certifications": certifications,
    }


@router.post("/predict/form", response_class=HTMLResponse)
def predict_form(
    request: Request,
    job_title: str = Form(...),
    experience_years: int = Form(...),
    education_level: str = Form(...),
    skills_count: int = Form(...),
    industry: str = Form(...),
    company_size: str = Form(...),
    location: str = Form(...),
    remote_work: str = Form(...),
    certifications: int = Form(...),
):
    inputs = _form_inputs(
        job_title=job_title,
        experience_years=experience_years,
        education_level=education_level,
        skills_count=skills_count,
        industry=industry,
        company_size=company_size,
        location=location,
        remote_work=remote_work,
        certifications=certifications,
    )
    try:
        payload = SalaryPredictRequest(**inputs)
        salary, warning = predictor.predict(payload)
        return templates.TemplateResponse(
            request,
            "predict.html",
            _predict_ctx(
                request,
                result=round(salary, 2),
                error=None,
                warning=warning,
                inputs=inputs,
            ),
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "predict.html",
            _predict_ctx(request, result=None, error=str(exc), inputs=inputs),
        )


@router.get("/mlflow")
def mlflow_redirect():
    return RedirectResponse(url=MLFLOW_PUBLIC_URL, status_code=302)


@router.get("/prefect")
def prefect_redirect():
    return RedirectResponse(url=PREFECT_PUBLIC_URL, status_code=302)


@router.get("/docs/training", response_class=HTMLResponse)
def docs_training(request: Request):
    raw_metrics = _read_json(PROCESSED / "phase4_metrics.json")
    metrics = raw_metrics.get("metrics", raw_metrics) if raw_metrics else {}
    from src.portal.params_io import load_params_file

    params = load_params_file()
    params_text = yaml.dump(params, allow_unicode=True, default_flow_style=False) if params else ""
    tuning = params.get("tuning") or {}
    grid = tuning.get("param_grid") or {}
    return templates.TemplateResponse(
        request,
        "docs_training.html",
        _ctx(
            request,
            metrics=metrics,
            params_text=params_text,
            tuning_enabled=tuning.get("enabled", True),
            grid_n=",".join(str(x) for x in grid.get("n_estimators", [500, 800])),
            grid_d=",".join(str(x) for x in grid.get("max_depth", [6, 7, 8])),
            grid_lr=",".join(str(x) for x in grid.get("learning_rate", [0.03, 0.05])),
        ),
    )


@router.get("/docs/dvc", response_class=HTMLResponse)
def docs_dvc(request: Request):
    dvc_metrics = _read_json(PROCESSED / "metrics.json")
    return templates.TemplateResponse(
        request,
        "docs_dvc.html",
        _ctx(request, dvc_metrics=dvc_metrics),
    )


@router.get("/docs/etl", response_class=HTMLResponse)
def docs_etl(request: Request):
    return templates.TemplateResponse(request, "docs_etl.html", _ctx(request))


@router.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request):
    from src.monitoring.baseline import baseline_exists, load_simulation_meta, simulation_is_active
    from src.monitoring.drift_retrain import load_retrain_audit
    from src.monitoring.drift_simulate import SCENARIOS
    from src.monitoring.evidently_report import load_drift_metrics, list_report_files
    from src.monitoring.params import load_monitoring_config

    metrics = load_drift_metrics()
    cfg = load_monitoring_config()

    return templates.TemplateResponse(
        request,
        "monitoring.html",
        _ctx(
            request,
            drift_metrics=metrics,
            monitoring_cfg=cfg,
            scenarios=SCENARIOS,
            baseline_ok=baseline_exists(),
            simulation_active=simulation_is_active(),
            simulation_meta=load_simulation_meta(),
            reports=list_report_files(),
            last_retrain=load_retrain_audit(),
        ),
    )
