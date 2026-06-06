"""Symulacja zmiany rynku — przesuniety silver (jak po aktualizacji ETL), nie log prognoz."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.monitoring.baseline import (
    SIMULATED_CURRENT_PATH,
    clear_drift_simulation,
    write_simulation_meta,
)
from src.monitoring.params import load_monitoring_config
from src.portal.data_loader import SILVER_PATH
from src.train.features import RAW_FEATURE_COLUMNS, TARGET

SCENARIOS = (
    "location_shift",
    "experience_high",
    "industry_tech",
    "salary_market_up",
    "salary_features_combo",
)


def _apply_feature_scenario(df: pd.DataFrame, scenario: str, rng: np.random.Generator) -> pd.DataFrame:
    out = df.copy()
    n = len(out)

    if scenario == "location_shift":
        out["location"] = rng.choice(
            ["Germany", "France", "Poland", "India", "Brazil"], size=n
        )
    elif scenario == "experience_high":
        base = out["experience_years"].astype(float)
        out["experience_years"] = np.clip(base + rng.integers(8, 16, size=n), 0, 40)
    elif scenario == "industry_tech":
        mask = rng.random(n) < 0.9
        out.loc[mask, "industry"] = "Technology"
    elif scenario == "salary_market_up":
        pass
    elif scenario == "salary_features_combo":
        out["location"] = rng.choice(["UK", "Germany", "Remote"], size=n)
        base = out["experience_years"].astype(float)
        out["experience_years"] = np.clip(base + rng.integers(5, 12, size=n), 0, 40)
        mask = rng.random(n) < 0.85
        out.loc[mask, "industry"] = "Technology"
        mask = rng.random(n) < 0.7
        out.loc[mask, "remote_work"] = "Yes"
    else:
        raise ValueError(f"Nieznany scenariusz: {scenario}. Dostepne: {', '.join(SCENARIOS)}")

    return out


def _apply_salary_scenario(df: pd.DataFrame, scenario: str, rng: np.random.Generator) -> pd.DataFrame:
    """Symulacja wzrostu pensji na rynku (target drift — model moze byc nieaktualny)."""
    if TARGET not in df.columns:
        return df
    out = df.copy()
    salaries = out[TARGET].astype(float)

    if scenario == "salary_market_up":
        factor = rng.uniform(1.12, 1.28, size=len(out))
        out[TARGET] = (salaries * factor).astype(int)
    elif scenario == "industry_tech":
        tech = out["industry"].astype(str) == "Technology"
        out.loc[tech, TARGET] = (salaries[tech] * rng.uniform(1.18, 1.32)).astype(int)
    elif scenario == "salary_features_combo":
        out[TARGET] = (salaries * rng.uniform(1.15, 1.30, size=len(out))).astype(int)
    elif scenario == "experience_high":
        out[TARGET] = (salaries * rng.uniform(1.08, 1.18, size=len(out))).astype(int)

    return out


def simulate_drift(
    scenario: str,
    count: int | None = None,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Buduje ``silver_current_simulated.parquet`` — jak nowy zrzut rynku po ETL
  z przesunietymi cechami i pensjami (demo retrainingu).
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Nieznany scenariusz: {scenario}")

    if not SILVER_PATH.is_file():
        raise FileNotFoundError(
            f"Brak {SILVER_PATH.relative_to(PROJECT_ROOT)} — uruchom ETL lub przygotowanie danych."
        )

    cfg = load_monitoring_config()
    rng = np.random.default_rng(seed)
    current = pd.read_parquet(SILVER_PATH)
    sample_n = int(count or cfg.get("default_simulate_count", 5000))
    sample_n = min(max(sample_n, 500), len(current))
    sample = current.sample(n=sample_n, random_state=seed).reset_index(drop=True)

    shifted = _apply_feature_scenario(sample, scenario, rng)
    shifted = _apply_salary_scenario(shifted, scenario, rng)

    cols = [c for c in [*RAW_FEATURE_COLUMNS, TARGET] if c in shifted.columns]
    SIMULATED_CURRENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shifted[cols].to_parquet(SIMULATED_CURRENT_PATH, index=False)
    write_simulation_meta(scenario, len(shifted))

    return {
        "scenario": scenario,
        "rows_written": len(shifted),
        "simulated_path": str(SIMULATED_CURRENT_PATH.relative_to(PROJECT_ROOT)),
        "note": (
            "Symulacja zapisana jako aktualny silver. Raport driftu porowna "
            "training_baseline (model) vs ten zrzut."
        ),
    }


def clear_simulation() -> dict[str, Any]:
    clear_drift_simulation()
    return {"cleared": True}
