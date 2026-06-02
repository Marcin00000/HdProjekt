"""Ładowanie modelu i predykcja pensji."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from api.schemas import SalaryPredictRequest
from src.config import PROJECT_ROOT
from src.portal.predict_options import get_predict_field_options
from src.train.features import RAW_FEATURE_COLUMNS

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
PREPROCESSOR_PATH = MODELS_DIR / "preprocessor.joblib"
MODEL_PATH = MODELS_DIR / "xgboost_model.joblib"
PREDICTION_LOG = PROJECT_ROOT / "data" / "processed" / "prediction_log.jsonl"


class PredictorService:
    def __init__(self) -> None:
        self._preprocessor = None
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._preprocessor is not None and self._model is not None

    def load(self) -> None:
        if not PREPROCESSOR_PATH.is_file():
            raise FileNotFoundError(f"Brak preprocessora: {PREPROCESSOR_PATH}")
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"Brak modelu: {MODEL_PATH}")
        self._preprocessor = joblib.load(PREPROCESSOR_PATH)
        self._model = joblib.load(MODEL_PATH)

    def predict(self, request: SalaryPredictRequest) -> tuple[float, str | None]:
        if not self.is_loaded:
            raise RuntimeError("Model nie zostal zaladowany")

        row = request.model_dump()
        warning = self._unknown_category_warning(row)
        X = pd.DataFrame([row], columns=RAW_FEATURE_COLUMNS)
        X_t = self._preprocessor.transform(X)
        pred = self._model.predict(X_t)
        salary = float(pred[0])
        self._append_log(row, salary)
        return salary, warning

    def _unknown_category_warning(self, row: dict) -> str | None:
        try:
            opts = get_predict_field_options()
        except Exception:
            return None
        unknown: list[str] = []
        for field in ("job_title", "industry", "company_size", "location", "remote_work"):
            allowed = set(opts.get(field, []))
            val = str(row.get(field, ""))
            if allowed and val not in allowed:
                unknown.append(f"{field}={val!r}")
        if not unknown:
            return None
        return (
            "Wartosci spoza zbioru treningowego (prognoza moze byc mniej dokladna): "
            + ", ".join(unknown)
        )

    def _append_log(self, features: dict, salary: float) -> None:
        """Prosty audit trail pod monitoring (faza 8)."""
        try:
            PREDICTION_LOG.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "features": features,
                "predicted_salary": salary,
            }
            with PREDICTION_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass


predictor = PredictorService()
