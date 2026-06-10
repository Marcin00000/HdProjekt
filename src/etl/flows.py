"""
Prefect — orkiestracja pipeline ETL (fazy 1 + 2).

Uruchomienie:
    python -m src.etl.flows
    python -m src.etl.flows --serve   # harmonogram (cron)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from prefect import flow, get_run_logger, task

from src.cleaning.preprocess import CleaningStats, build_gold_aggregates, clean_dataframe
from src.config import AzureStorageConfig, PROJECT_ROOT
from src.etl.lake_io import write_parquet
from src.etl.load_dwh import build_star_schema, get_sql_engine, load_to_azure_sql, verify_load


@task(retries=3, retry_delay_seconds=[5, 15, 30])
def verify_raw() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Wczytuje i weryfikuje plik raw (lokalny lub Azure Data Lake)."""
    logger = get_run_logger()

    # Uzywa tej samej logiki co run_prepare / etl_sync — priorytet: lokalny, potem lake
    from src.portal.data_loader import load_raw_with_source

    raw, source = load_raw_with_source()
    if len(raw) < 1000:
        raise ValueError(f"Za malo wierszy w raw: {len(raw)}")

    info = {
        "source": source,
        "rows": len(raw),
        "columns": list(raw.columns),
    }
    logger.info("verify_raw OK: %s", info)
    return raw, info


@task(retries=2, retry_delay_seconds=10)
def clean_to_silver(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Czyszczenie i zapis warstwy silver (lake + lokalnie)."""
    logger = get_run_logger()

    # Parametry czyszczenia z params.yaml — spojna z run_prepare i etl_sync
    from src.portal.params_io import load_params_file

    prep = load_params_file().get("prepare", {})
    silver, stats = clean_dataframe(
        raw,
        salary_quantile_low=float(prep.get("salary_quantile_low", 0.01)),
        salary_quantile_high=float(prep.get("salary_quantile_high", 0.99)),
        max_experience_years=int(prep.get("max_experience_years", 40)),
    )

    if silver.isnull().sum().sum() != 0:
        raise ValueError("Silver zawiera braki po czyszczeniu")

    cfg = AzureStorageConfig()
    write_parquet(silver, cfg.silver_path, cfg)

    local_dir = PROJECT_ROOT / "data" / "processed"
    local_dir.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(local_dir / "cleaned.parquet", index=False)

    stats_dict = asdict(stats)
    logger.info("clean_to_silver: %s -> %s wierszy", stats.rows_in, stats.rows_out)
    return silver, stats_dict


@task
def build_gold(silver: pd.DataFrame) -> dict[str, Any]:
    """Agregaty gold i zapis do lake."""
    logger = get_run_logger()
    cfg = AzureStorageConfig()
    gold_tables = build_gold_aggregates(silver)
    paths: dict[str, str] = {}

    for name, table in gold_tables.items():
        lake_path = cfg.gold_path if name == "salary_by_location" else f"gold/{name}.parquet"
        write_parquet(table, lake_path, cfg)
        paths[name] = lake_path
        logger.info("gold %s: %s wierszy -> %s", name, len(table), lake_path)

    local_dir = PROJECT_ROOT / "data" / "processed"
    for name, table in gold_tables.items():
        table.to_parquet(local_dir / f"{name}.parquet", index=False)

    return {"tables": list(gold_tables.keys()), "paths": paths}


@task(retries=2, retry_delay_seconds=20)
def load_star_schema_sql(silver: pd.DataFrame) -> dict[str, Any]:
    """Budowa schematu gwiazdy i zaladowanie do Azure SQL."""
    logger = get_run_logger()
    tables = build_star_schema(silver)

    out_dir = PROJECT_ROOT / "data" / "dwh"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)

    engine = get_sql_engine()
    loaded = load_to_azure_sql(tables, engine)
    verified = verify_load(engine)

    for table, expected in loaded.items():
        actual = verified.get(table, 0)
        if actual != expected:
            logger.warning("UWAGA: %s — zaladowano %d, w SQL: %d", table, expected, actual)

    result = {"loaded": loaded, "verified": verified}
    logger.info("load_star_schema_sql: %s", result)
    return result


@flow(name="etl_main", log_prints=True)
def etl_main(skip_sql: bool = False) -> dict[str, Any]:
    """
    Pelny pipeline ETL:
    raw (lokalny lub lake) -> silver -> gold -> Azure SQL (hurtownia).
    """
    logger = get_run_logger()
    started = datetime.now(timezone.utc).isoformat()

    # verify_raw zwraca (DataFrame, info) — brak podwojnego wczytywania raw
    raw, raw_info = verify_raw()

    silver, cleaning_stats = clean_to_silver(raw)
    gold_info = build_gold(silver)

    dwh_info: dict[str, Any] = {}
    if not skip_sql:
        dwh_info = load_star_schema_sql(silver)
    else:
        logger.info("Pominieto load_star_schema_sql (skip_sql=True)")

    summary = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "raw": raw_info,
        "cleaning": cleaning_stats,
        "gold": gold_info,
        "dwh": dwh_info,
    }

    from src.processed_artifacts import ETL_SUMMARY

    metrics_path = ETL_SUMMARY
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Pipeline zakonczony. Metryki: %s", metrics_path)
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Prefect ETL flow")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Uruchom deployment z harmonogramem cron (niedziela 03:00)",
    )
    parser.add_argument(
        "--skip-sql",
        action="store_true",
        help="Pomin zaladowanie hurtowni SQL",
    )
    args = parser.parse_args()

    if args.serve:
        etl_main.serve(
            name="weekly-etl-job-salary",
            cron="0 3 * * 0",
            tags=["hd-projekt", "etl"],
            parameters={"skip_sql": args.skip_sql},
        )
    else:
        etl_main(skip_sql=args.skip_sql)


if __name__ == "__main__":
    main()
