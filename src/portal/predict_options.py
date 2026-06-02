"""Dozwolone wartosci pol formularza prognozy (ze silver/CSV)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT, local_raw_data_path
from src.portal.data_loader import SILVER_PATH
from src.train.features import EDUCATION_ORDER

DEFAULT_OPTIONS: dict[str, list[str]] = {
    "job_title": ["Data Scientist", "Software Engineer", "Product Manager"],
    "education_level": list(EDUCATION_ORDER.keys()),
    "industry": ["Technology", "Finance", "Healthcare"],
    "company_size": ["Small", "Medium", "Large"],
    "location": ["USA", "UK", "Canada"],
    "remote_work": ["Yes", "No", "Hybrid"],
}


def _distinct(df: pd.DataFrame, col: str, limit: int = 200) -> list[str]:
    if col not in df.columns:
        return DEFAULT_OPTIONS.get(col, [])
    vals = df[col].dropna().astype(str).str.strip()
    top = vals.value_counts().head(limit).index.tolist()
    return sorted(top)


def get_predict_field_options() -> dict[str, Any]:
    if SILVER_PATH.is_file():
        df = pd.read_parquet(SILVER_PATH)
        source = "silver"
    else:
        raw_path = local_raw_data_path()
        if not raw_path.is_file():
            return {**DEFAULT_OPTIONS, "source": "defaults"}
        df = pd.read_csv(raw_path, nrows=100_000)
        source = "raw_csv"

    options = {
        "source": source,
        "job_title": _distinct(df, "job_title", 80),
        "education_level": _distinct(df, "education_level") or DEFAULT_OPTIONS["education_level"],
        "industry": _distinct(df, "industry", 40),
        "company_size": _distinct(df, "company_size", 20),
        "location": _distinct(df, "location", 30),
        "remote_work": _distinct(df, "remote_work") or DEFAULT_OPTIONS["remote_work"],
    }
    return options
