"""Dane do dashboardu — silver (wykresy) + opcjonalnie Azure SQL (liczniki)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.config import local_raw_data_path
from src.etl.load_dwh import get_sql_engine
from src.portal.data_loader import GOLD_BY_LOCATION, SILVER_PATH

GOLD_LOCATION = GOLD_BY_LOCATION


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


def _group_avg(silver: pd.DataFrame, col: str, top: int | None = None) -> pd.DataFrame:
    out = (
        silver.groupby(col, as_index=False, observed=True)
        .agg(job_count=("salary", "count"), avg_salary=("salary", "mean"))
        .sort_values("avg_salary", ascending=False)
    )
    if top:
        out = out.head(top)
    return out


def _aggregates_from_silver(silver: pd.DataFrame) -> dict[str, Any]:
    work = silver.copy()
    by_location = _group_avg(work, "location", top=10)
    by_education = _group_avg(work, "education_level")
    by_remote = _group_avg(work, "remote_work")
    by_industry = _group_avg(work, "industry", top=12)
    by_company_size = _group_avg(work, "company_size")

    by_experience = pd.DataFrame()
    if "experience_years" in work.columns:
        work["exp_bucket"] = pd.cut(
            work["experience_years"].clip(0, 40),
            bins=[-1, 2, 5, 10, 15, 40],
            labels=["0-2", "3-5", "6-10", "11-15", "16+"],
        )
        by_experience = _group_avg(work, "exp_bucket")

    by_job_title = _group_avg(work, "job_title", top=10)

    salary_bins: list[dict[str, Any]] = []
    if "salary" in work.columns and len(work) > 0:
        series = work["salary"].dropna()
        if len(series) > 0:
            counts, _edges = pd.cut(series, bins=12, retbins=True)
            hist = counts.value_counts().sort_index()
            for interval, cnt in hist.items():
                salary_bins.append(
                    {
                        "bin": f"{int(interval.left):,}-{int(interval.right):,}",
                        "count": int(cnt),
                    }
                )

    overall: dict[str, Any] = {}
    if "salary" in silver.columns and len(silver) > 0:
        overall["avg_salary"] = _sanitize_value(silver["salary"].mean())
        overall["median_salary"] = _sanitize_value(silver["salary"].median())
        overall["total_records"] = int(len(silver))

    return {
        "by_location": _records(by_location),
        "by_education": _records(by_education),
        "by_remote": _records(by_remote),
        "by_industry": _records(by_industry),
        "by_company_size": _records(by_company_size),
        "by_experience": _records(by_experience),
        "by_job_title": _records(by_job_title),
        "salary_distribution": salary_bins,
        "table_counts": {"fact_rows": int(len(silver))},
        "overall": overall,
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


def _fetch_sql_table_counts() -> dict[str, Any]:
    engine = get_sql_engine()
    counts = _query_df(
        engine,
        """
        SELECT
            (SELECT COUNT(*) FROM fact_salaries) AS fact_rows,
            (SELECT COUNT(*) FROM dim_job) AS dim_job,
            (SELECT COUNT(*) FROM dim_company) AS dim_company
        """,
    )
    return _records(counts)[0] if len(counts) else {}


def fetch_from_sql_only() -> dict[str, Any]:
    """Pelny dashboard tylko z SQL (gdy brak silver lokalnie)."""
    engine = get_sql_engine()

    by_location = _query_df(
        engine,
        """
        SELECT TOP 10 j.location, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.location ORDER BY avg_salary DESC
        """,
    )

    by_education = _query_df(
        engine,
        """
        SELECT j.education_level, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.education_level ORDER BY avg_salary DESC
        """,
    )

    by_remote = _query_df(
        engine,
        """
        SELECT j.remote_work, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.remote_work ORDER BY avg_salary DESC
        """,
    )

    by_industry = _query_df(
        engine,
        """
        SELECT TOP 12 c.industry, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_company c ON f.company_id = c.company_id
        GROUP BY c.industry ORDER BY avg_salary DESC
        """,
    )

    by_company_size = _query_df(
        engine,
        """
        SELECT c.company_size, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_company c ON f.company_id = c.company_id
        GROUP BY c.company_size ORDER BY avg_salary DESC
        """,
    )

    by_experience = _query_df(
        engine,
        """
        SELECT
            CASE
                WHEN f.experience_years <= 2 THEN '0-2'
                WHEN f.experience_years <= 5 THEN '3-5'
                WHEN f.experience_years <= 10 THEN '6-10'
                WHEN f.experience_years <= 15 THEN '11-15'
                ELSE '16+'
            END AS exp_bucket,
            COUNT(*) AS job_count,
            AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        GROUP BY
            CASE
                WHEN f.experience_years <= 2 THEN '0-2'
                WHEN f.experience_years <= 5 THEN '3-5'
                WHEN f.experience_years <= 10 THEN '6-10'
                WHEN f.experience_years <= 15 THEN '11-15'
                ELSE '16+'
            END
        ORDER BY MIN(f.experience_years)
        """,
    )

    by_job_title = _query_df(
        engine,
        """
        SELECT TOP 10 j.job_title, COUNT(*) AS job_count,
               AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
        FROM fact_salaries f
        JOIN dim_job j ON f.job_id = j.job_id
        GROUP BY j.job_title ORDER BY avg_salary DESC
        """,
    )

    table_counts = _fetch_sql_table_counts()
    salary_distribution: list[dict[str, Any]] = []

    if SILVER_PATH.is_file():
        salary_distribution = _aggregates_from_silver(pd.read_parquet(SILVER_PATH))[
            "salary_distribution"
        ]

    return {
        "source": "azure_sql",
        "by_location": _records(by_location),
        "by_education": _records(by_education),
        "by_remote": _records(by_remote),
        "by_industry": _records(by_industry),
        "by_company_size": _records(by_company_size),
        "by_experience": _records(by_experience),
        "by_job_title": _records(by_job_title),
        "salary_distribution": salary_distribution,
        "table_counts": table_counts,
        "overall": {},
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
            "by_industry": [],
            "by_company_size": [],
            "by_experience": [],
            "by_job_title": [],
            "salary_distribution": [],
            "table_counts": {},
            "overall": {},
        }

    raw_path = local_raw_data_path()
    if raw_path.is_file():
        try:
            raw = pd.read_csv(raw_path)
            if "salary" in raw.columns:
                data = _aggregates_from_silver(raw)
                data["source"] = "raw_csv"
                data["hint"] = "Uruchom pipeline ETL (Prefect) aby zapisac silver."
                return data
        except Exception as exc:
            return _empty_data(f"Nie udalo sie wczytac CSV: {exc}")

    return _empty_data(
        "Brak danych: Azure SQL, silver/gold parquet lub plik CSV. "
        "Uruchom ETL w zakladce ETL / Prefect UI."
    )


def _empty_data(error: str) -> dict[str, Any]:
    return {
        "source": "none",
        "error": error,
        "by_location": [],
        "by_education": [],
        "by_remote": [],
        "by_industry": [],
        "by_company_size": [],
        "by_experience": [],
        "by_job_title": [],
        "salary_distribution": [],
        "table_counts": {},
        "overall": {},
    }


def get_dashboard_data() -> dict[str, Any]:
    """
    Wykresy z warstwy silver (pelny zestaw wymiarow).
    Liczniki SQL opcjonalnie, gdy Azure SQL jest dostepny.
    """
    if SILVER_PATH.is_file():
        silver = pd.read_parquet(SILVER_PATH)
        data = _aggregates_from_silver(silver)
        data["source"] = "silver_parquet"
        if _sql_available():
            try:
                sql_counts = _fetch_sql_table_counts()
                if sql_counts:
                    data["table_counts"] = {
                        **(data.get("table_counts") or {}),
                        **sql_counts,
                    }
                    data["source"] = "silver_parquet+azure_sql"
            except Exception as exc:
                data["sql_error"] = str(exc)
        return data

    if _sql_available():
        try:
            return fetch_from_sql_only()
        except Exception as exc:
            data = fetch_from_local_fallback()
            data["sql_error"] = str(exc)
            return data

    return fetch_from_local_fallback()
