"""
Budowa schematu gwiazdy z warstwy silver i zaladowanie do Azure SQL Database.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from src.config import AzureSqlConfig


def build_star_schema(
    silver: pd.DataFrame,
    etl_date: date | None = None,
) -> dict[str, pd.DataFrame]:
    """Tworzy dim_time, dim_company, dim_job, fact_salaries z oczyszczonych danych."""
    etl_date = etl_date or date.today()

    dim_time = pd.DataFrame(
        [
            {
                "time_id": 1,
                "etl_date": pd.Timestamp(etl_date),
                "year": etl_date.year,
                "month": etl_date.month,
                "weekday": etl_date.weekday(),
                "is_weekend": int(etl_date.weekday() >= 5),
            }
        ]
    )

    dim_company = (
        silver[["industry", "company_size"]]
        .drop_duplicates()
        .sort_values(["industry", "company_size"])
        .reset_index(drop=True)
    )
    dim_company.insert(0, "company_id", range(1, len(dim_company) + 1))

    dim_job = (
        silver[["job_title", "education_level", "location", "remote_work"]]
        .drop_duplicates()
        .sort_values(["job_title", "location"])
        .reset_index(drop=True)
    )
    dim_job.insert(0, "job_id", range(1, len(dim_job) + 1))

    keys = silver.merge(
        dim_company,
        on=["industry", "company_size"],
        how="left",
        validate="many_to_one",
    ).merge(
        dim_job,
        on=["job_title", "education_level", "location", "remote_work"],
        how="left",
        validate="many_to_one",
    )

    fact_cols = [
        "company_id",
        "job_id",
        "salary",
        "experience_years",
        "skills_count",
        "certifications",
        "salary_k",
        "high_skills",
        "is_remote",
    ]
    fact_salaries = keys[fact_cols].copy()
    fact_salaries.insert(0, "fact_id", range(1, len(fact_salaries) + 1))
    fact_salaries.insert(1, "time_id", 1)
    fact_salaries = fact_salaries.rename(columns={"salary": "salary_amount"})

    return {
        "dim_time": dim_time,
        "dim_company": dim_company,
        "dim_job": dim_job,
        "fact_salaries": fact_salaries,
    }


def get_sql_engine(cfg: AzureSqlConfig | None = None) -> Engine:
    cfg = cfg or AzureSqlConfig()
    engine = create_engine(
        cfg.sqlalchemy_url(),
        pool_pre_ping=True,
        fast_executemany=True,
    )

    @event.listens_for(engine, "before_cursor_execute")
    def _fast_executemany(
        conn, cursor, statement, parameters, context, executemany
    ):
        if executemany:
            cursor.fast_executemany = True

    return engine


def load_to_azure_sql(
    tables: dict[str, pd.DataFrame],
    engine: Engine | None = None,
    chunksize: int = 5_000,
) -> dict[str, int]:
    """Zapisuje tabele do Azure SQL (replace). Zwraca liczbe wierszy na tabele."""
    engine = engine or get_sql_engine()
    row_counts: dict[str, int] = {}

    order = ["dim_time", "dim_company", "dim_job", "fact_salaries"]
    with engine.begin() as conn:
        for name in order:
            df = tables[name].copy()
            if "etl_date" in df.columns:
                df["etl_date"] = pd.to_datetime(df["etl_date"]).dt.date
            chunk = chunksize if name == "fact_salaries" else None
            # method=None + fast_executemany: bezpieczniejsze niz multi (limit parametrow SQL Server)
            df.to_sql(
                name,
                conn,
                if_exists="replace",
                index=False,
                chunksize=chunk,
            )
            row_counts[name] = len(df)
    return row_counts


def run_analytics_queries(engine: Engine | None = None) -> dict[str, Any]:
    """
    Trzy zapytania analityczne (odpowiednik zadania 5.5.1 kursu, domena job salary).
    """
    engine = engine or get_sql_engine()

    queries = {
        "top_location_by_avg_salary": """
            SELECT TOP 1
                j.location,
                COUNT(*) AS job_count,
                AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
            FROM fact_salaries f
            JOIN dim_job j ON f.job_id = j.job_id
            GROUP BY j.location
            ORDER BY avg_salary DESC
        """,
        "avg_salary_by_education": """
            SELECT
                j.education_level,
                COUNT(*) AS job_count,
                AVG(CAST(f.salary_amount AS FLOAT)) AS avg_salary
            FROM fact_salaries f
            JOIN dim_job j ON f.job_id = j.job_id
            GROUP BY j.education_level
            ORDER BY avg_salary DESC
        """,
        "top_industry_by_total_payroll": """
            SELECT TOP 1
                c.industry,
                COUNT(*) AS job_count,
                SUM(CAST(f.salary_amount AS BIGINT)) AS total_salary
            FROM fact_salaries f
            JOIN dim_company c ON f.company_id = c.company_id
            GROUP BY c.industry
            ORDER BY total_salary DESC
        """,
    }

    results: dict[str, Any] = {}
    with engine.connect() as conn:
        for name, sql in queries.items():
            df = pd.read_sql(text(sql), conn)
            results[name] = df
    return results


def verify_load(engine: Engine | None = None) -> dict[str, int]:
    engine = engine or get_sql_engine()
    counts = {}
    with engine.connect() as conn:
        for table in ("dim_time", "dim_company", "dim_job", "fact_salaries"):
            row = conn.execute(text(f"SELECT COUNT(*) AS c FROM {table}")).fetchone()
            counts[table] = int(row[0])
    return counts
