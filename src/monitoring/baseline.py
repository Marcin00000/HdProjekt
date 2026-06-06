"""Baseline treningowy — referencja do porownania z aktualnym rynkiem (silver po ETL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT
from src.train.features import RAW_FEATURE_COLUMNS, TARGET

TRAINING_BASELINE_PATH = PROJECT_ROOT / "data" / "processed" / "training_baseline.parquet"
BASELINE_META_PATH = PROJECT_ROOT / "data" / "processed" / "training_baseline_meta.json"
SIMULATED_CURRENT_PATH = PROJECT_ROOT / "data" / "processed" / "silver_current_simulated.parquet"
SIMULATION_META_PATH = PROJECT_ROOT / "data" / "processed" / "drift_simulation_meta.json"

DRIFT_COLUMNS = [*RAW_FEATURE_COLUMNS, TARGET]


def save_training_baseline(X_train: pd.DataFrame, y_train: pd.Series) -> None:
    """Zapisz rozklad danych, na ktorych wytrenowano model (referencja monitoringu)."""
    df = X_train.copy()
    df[TARGET] = y_train.values
    cols = [c for c in DRIFT_COLUMNS if c in df.columns]
    TRAINING_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df[cols].to_parquet(TRAINING_BASELINE_PATH, index=False)
    meta = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(df),
        "columns": cols,
    }
    BASELINE_META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def baseline_exists() -> bool:
    return TRAINING_BASELINE_PATH.is_file()


def load_training_baseline(*, max_rows: int | None = None) -> pd.DataFrame:
    if not TRAINING_BASELINE_PATH.is_file():
        raise FileNotFoundError(
            "Brak training_baseline.parquet — uruchom trening modelu, aby zapisac referencje."
        )
    df = pd.read_parquet(TRAINING_BASELINE_PATH)
    cols = [c for c in DRIFT_COLUMNS if c in df.columns]
    df = df[cols]
    if max_rows and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=42)
    return df.reset_index(drop=True)


def simulation_is_active() -> bool:
    if not SIMULATION_META_PATH.is_file() or not SIMULATED_CURRENT_PATH.is_file():
        return False
    try:
        meta = json.loads(SIMULATION_META_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(meta.get("active"))


def load_current_market_data(*, max_rows: int | None = None) -> tuple[pd.DataFrame, str]:
    """Aktualny rynek: symulowany silver (demo) lub cleaned.parquet po ETL."""
    if simulation_is_active():
        path = SIMULATED_CURRENT_PATH
        source = "silver_current_simulated (demo)"
    else:
        from src.portal.data_loader import SILVER_PATH

        path = SILVER_PATH
        source = "cleaned.parquet (silver po ETL)"

    if not path.is_file():
        raise FileNotFoundError(
            f"Brak aktualnych danych rynku ({path.name}). Uruchom ETL lub symulacje driftu."
        )

    df = pd.read_parquet(path)
    cols = [c for c in DRIFT_COLUMNS if c in df.columns]
    df = df[cols]
    if max_rows and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=42)
    return df.reset_index(drop=True), source


def clear_drift_simulation() -> None:
    for path in (SIMULATED_CURRENT_PATH, SIMULATION_META_PATH):
        if path.is_file():
            path.unlink()


def write_simulation_meta(scenario: str, rows: int) -> None:
    SIMULATION_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIMULATION_META_PATH.write_text(
        json.dumps(
            {
                "active": True,
                "scenario": scenario,
                "rows": rows,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_simulation_meta() -> dict[str, Any]:
    if not SIMULATION_META_PATH.is_file():
        return {}
    return json.loads(SIMULATION_META_PATH.read_text(encoding="utf-8"))
