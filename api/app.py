"""Aplikacja FastAPI — portal web + REST API (fazy 6–7)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from api.predictor import predictor
from api.routes.jobs_api import router as jobs_api_router
from api.routes.portal import router as portal_router
from api.schemas import HealthResponse, SalaryPredictRequest, SalaryPredictResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("API_SKIP_MODEL_LOAD") != "1":
        try:
            predictor.load()
        except FileNotFoundError:
            pass
    yield


app = FastAPI(
    title="Job Salary Prediction",
    description="Portal: dashboard SQL, prognoza pensji, MLflow, DVC, ETL.",
    version="1.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(portal_router)
app.include_router(jobs_api_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", model_loaded=predictor.is_loaded)


@app.post("/predict", response_model=SalaryPredictResponse)
def predict_api(request: SalaryPredictRequest) -> SalaryPredictResponse:
    if not predictor.is_loaded:
        raise HTTPException(status_code=503, detail="Model niedostepny")
    try:
        salary, warning = predictor.predict(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SalaryPredictResponse(predicted_salary=round(salary, 2), warning=warning)
