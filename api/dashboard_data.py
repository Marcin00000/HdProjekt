"""Dane do dashboardu — Azure SQL z fallback na pliki lokalne / CSV."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.config import PROJECT_ROOT, local_raw_data_path
from src.etl.load_dwh import get_sql_engine
from src.portal.data_loader import GOLD_BY_LOCATION, SILVER_PATH

GOLD_LOCATION = GOLD_BY_LOCATION  # alias


def _sanitize_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        return _sanitize_value(v.item())
    if isinstance(v, (pd.Timestamp,)):
        return str(v)
    return v


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = df.to_dict(orient="records")
    return [{k: _sanitize_value(v) for k, v in row.items()} for row in rows]


def _aggregates_from_silver(silver: pd.DataFrame) -> dict[str, Any]:
    by_location = (
        silver.groupby("location", as_index=False)
        .agg(job_count=("salary", "count"), avg_salary=("salary", "mean"))
        .sort_values("avg_salary", ascending=False)
        .head(10)
    )
    by_education = (
        silver.groupby("education_level", as_index=False)
        .agg(job_count=("salary", "count"), avg_salary=("salary", "mean"))
        .sort_values("avg_salary", ascending=False)
    )
    by_remote = (
        silver.groupby("remote_work", as_index=False)
        .agg(job_count=("salary", "count"), avg_salary=("salary", "mean"))
        .sort_values("avg_salary", ascending=False)
    )
    return {
        "by_location": _records(by_location),
        "by_education": _records(by_education),
        "by_remote": _records(by_remote),
        "table_counts": {"fact_rows": int(len(silver))},
    }


def _sql_available() -> bool:
    try:
        from src.config import AzureSqlConfig

        cfg = AzureSqlConfig()
        cfg.sqlalchemy_url()
        return True
    except ValueError:
        return False


def _query_df(engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def fetch_from_sql() -> dict[str, Any]:
    engine = get_sql_engine()
    by_location = _query_df(
        engine,
        """
        SELECT TOP 10
            j.location,
            COUNT(*) AS job_count,
            AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.location
        ORDER BY avg_salary DESC
        """,
    )
    by_education = _query_df(
        engine,
        """
        SELECT
            j.education_level,
            COUNT(*) AS job_count,
            AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.education_level
        ORDER BY avg_salary DESC
        """,
    )
    by_remote = _query_df(
        engine,
        """
        SELECT
            j.remote_work,
            COUNT(*) AS job_count,
            AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.remote_work
        ORDER BY avg_salary DESC
        """,
    )
    counts = _query_df(
        engine,
        """
        SELECT
            (SELECT COUNT(*) FROM fact_salaries) AS fact_rows,
            (SELECT COUNT(*) FROM dim_job) AS dim_job,
            (SELECT COUNT(*) FROM dim_company) AS dim_company
        """,
    )
    return {
        "source": "azure_sql",
        "by_location": _records(by_location),
        "by_education": _records(by_education),
        "by_remote": _records(by_remote),
        "table_counts": _records(counts)[0] if len(counts) else {},
    }


def fetch_from_local_fallback() -> dict[str, Any]:
    if SILVER_PATH.is_file():
        silver = pd.read_parquet(SILVER_PATH)
        data = _aggregates_from_silver(silver)
        data["source"] = "silver_parquet"
        return data

    if GOLD_LOCATION.is_file():
        gold = pd.read_parquet(GOLD_LOCATION)
        by_location = gold.copy()
        if "median_salary" in by_location.columns and "avg_salary" not in by_location.columns:
            by_location["avg_salary"] = by_location["median_salary"]
        return {
            "source": "gold_parquet",
            "by_location": _records(by_location.head(10)),
            "by_education": [],
            "by_remote": [],
            "table_counts": {},
        }

    raw_path = local_raw_data_path()
    if raw_path.is_file():
        try:
            raw = pd.read_csv(raw_path)
            if "salary" in raw.columns:
                data = _aggregates_from_silver(raw)
                data["source"] = "raw_csv"
                data["hint"] = "Uruchom Przygotowanie danych (ETL) aby zapisac silver."
                return data
        except Exception as exc:
            return {
                "source": "none",
                "error": f"Nie udalo sie wczytac CSV: {exc}",
                "by_location": [],
                "by_education": [],
                "by_remote": [],
                "table_counts": {},
            }

    return {
        "source": "none",
        "error": (
            "Brak danych: Azure SQL, silver/gold parquet lub "
            f"{raw_path.name}. Uruchom Przygotowanie danych w zakladce ETL."
        ),
        "by_location": [],
        "by_education": [],
        "by_remote": [],
        "table_counts": {},
    }


def get_dashboard_data() -> dict[str, Any]:
    if _sql_available():
        try:
            return fetch_from_sql()
        except Exception as exc:
            data = fetch_from_local_fallback()
            data["sql_error"] = str(exc)
            return data
    return fetch_from_local_fallback()
