"""
Czyszczenie i feature engineering — warstwa silver oraz agregaty gold.

Wzorowane na rozdziale Data Cleaning kursu HD (pandas, usuwanie outlierów, walidacja).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

TARGET = "salary"
REQUIRED_COLUMNS = [
    "job_title",
    "experience_years",
    "education_level",
    "skills_count",
    "industry",
    "company_size",
    "location",
    "remote_work",
    "certifications",
    TARGET,
]


@dataclass
class CleaningStats:
    rows_in: int
    rows_out: int
    duplicates_removed: int
    outliers_removed: int
    invalid_removed: int


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.select_dtypes(include=["object", "string"]).columns:
        out[col] = out[col].astype(str).str.strip()
        # astype(str) zamienia NaN na literalny "nan" — przywroc pd.NA
        out[col] = out[col].replace({"nan": pd.NA, "None": pd.NA, "<NA>": pd.NA, "": pd.NA})
    return out


def clean_dataframe(
    df: pd.DataFrame,
    salary_quantile_low: float = 0.01,
    salary_quantile_high: float = 0.99,
    max_experience_years: int = 40,
) -> tuple[pd.DataFrame, CleaningStats]:
    """
    Pipeline czyszczenia:
    - walidacja kolumn
    - usunięcie duplikatów
    - rekordy z niepoprawnymi wartościami
    - outliery wynagrodzenia (kwantyle)
    - proste cechy pochodne pod model i hurtownię
    """
    rows_in = len(df)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Brakujące kolumny: {missing}")

    work = _strip_strings(df)
    dup_mask = work.duplicated()
    duplicates_removed = int(dup_mask.sum())
    work = work.loc[~dup_mask]

    invalid_mask = (
        (work[TARGET] <= 0)
        | (work["experience_years"] < 0)
        | (work["experience_years"] > max_experience_years)
        | (work["skills_count"] < 0)
        | (work["certifications"] < 0)
        | work["job_title"].isna()
        | work["location"].isna()
    )
    invalid_removed = int(invalid_mask.sum())
    work = work.loc[~invalid_mask]

    q_low = work[TARGET].quantile(salary_quantile_low)
    q_high = work[TARGET].quantile(salary_quantile_high)
    outlier_mask = (work[TARGET] < q_low) | (work[TARGET] > q_high)
    outliers_removed = int(outlier_mask.sum())
    work = work.loc[~outlier_mask]

    work = work.reset_index(drop=True)
    work["salary_k"] = (work[TARGET] / 1000).round(2)
    work["high_skills"] = (work["skills_count"] >= work["skills_count"].median()).astype(int)
    work["is_remote"] = work["remote_work"].isin(["Yes", "yes", "Hybrid", "hybrid"]).astype(int)

    stats = CleaningStats(
        rows_in=rows_in,
        rows_out=len(work),
        duplicates_removed=duplicates_removed,
        outliers_removed=outliers_removed,
        invalid_removed=invalid_removed,
    )
    return work, stats


def build_gold_aggregates(silver: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Agregaty analityczne do warstwy gold (dashboard / SQL)."""
    by_location = (
        silver.groupby("location", as_index=False)
        .agg(
            job_count=("salary", "count"),
            avg_salary=("salary", "mean"),
            median_salary=("salary", "median"),
            min_salary=("salary", "min"),
            max_salary=("salary", "max"),
            avg_experience=("experience_years", "mean"),
        )
        .round(2)
        .sort_values("median_salary", ascending=False)
    )

    by_location_industry = (
        silver.groupby(["location", "industry"], as_index=False)
        .agg(
            job_count=("salary", "count"),
            median_salary=("salary", "median"),
        )
        .round(2)
        .sort_values(["location", "median_salary"], ascending=[True, False])
    )

    return {
        "salary_by_location": by_location,
        "salary_by_location_industry": by_location_industry,
    }
