"""Walidacja plikow modelu (joblib) — wykrywanie pustych/uszkodzonych artefaktow."""

from __future__ import annotations

from pathlib import Path

import joblib

from src.config import PROJECT_ROOT

PREPROCESSOR_PATH = PROJECT_ROOT / "models" / "preprocessor.joblib"
MODEL_PATH = PROJECT_ROOT / "models" / "xgboost_model.joblib"

MODEL_ARTIFACTS = (PREPROCESSOR_PATH, MODEL_PATH)

# Pusty lub obciety zapis joblib jest zwykle bardzo maly.
_MIN_BYTES = 128


def joblib_looks_valid(path: Path) -> bool:
    """True gdy plik istnieje, ma sensowny rozmiar i da sie odczytac przez joblib."""
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < _MIN_BYTES:
            return False
        joblib.load(path)
        return True
    except Exception:
        return False


def invalid_model_paths() -> list[Path]:
    """Pliki modelu obecne na dysku, ale niepoprawne (lub brakujace)."""
    bad: list[Path] = []
    for path in MODEL_ARTIFACTS:
        if not path.is_file() or not joblib_looks_valid(path):
            bad.append(path)
    return bad


def models_ready() -> bool:
    return not invalid_model_paths()
