"""ETL synchroniczny (bez serwera Prefect) — stabilny w Dockerze."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.cleaning.preprocess import clean_dataframe
from src.config import AzureStorageConfig, PROJECT_ROOT
from src.etl.lake_io import write_parquet
from src.etl.load_dwh import build_star_schema, get_sql_engine, load_to_azure_sql, verify_load
from src.portal.data_loader import load_raw_with_source, load_silver_dataframe
from src.portal.job_context import log, progress

PROCESSED = PROJECT_ROOT / "data" / "processed"


def _can_use_sql() -> bool:
    try:
        from src.config import AzureSqlConfig

        AzureSqlConfig().sqlalchemy_url()
        from src.etl.load_dwh import get_sql_engine

        get_sql_engine()
        return True
    except Exception:
        return False


def run_etl_sync(*, skip_sql: bool = False, upload_lake: bool = True) -> dict[str, Any]:
    """
    raw → silver → gold → (opcjonalnie) Azure SQL.
    Ten sam efekt co Prefect etl_main, bez ephemeral server.
    """
    started = datetime.now(timezone.utc).isoformat()
    log("=== Start pipeline ETL (tryb synchroniczny) ===")
    progress(5, "ETL — wczytywanie warstwy raw")

    from src.config import local_raw_data_path
    from src.portal.paths_status import azure_storage_configured

    local_path = local_raw_data_path()
    if local_path.is_file():
        log(f"Zrodlo raw: plik lokalny ({local_path.name})")
    elif azure_storage_configured():
        log("Zrodlo raw: brak pliku lokalnego — pobieranie z Azure Data Lake")
    else:
        log("UWAGA: brak CSV lokalnie i brak konfiguracji Azure w .env")

    raw, raw_source = load_raw_with_source()
    if len(raw) < 1000:
        raise ValueError(f"Za malo wierszy w raw: {len(raw)}")

    raw_info = {
        "rows": len(raw),
        "columns": list(raw.columns),
        "source": raw_source,
    }
    src_label = "lokalny" if raw_source == "local" else "Azure Data Lake"
    log(f"Wczytano raw ({src_label}): {raw_info['rows']:,} wierszy, kolumn: {len(raw_info['columns'])}")
    log(f"  Kolumny: {', '.join(str(c) for c in raw.columns[:12])}{'...' if len(raw.columns) > 12 else ''}")

    progress(25, "ETL — oczyszczenie i zapis silver")
    silver, stats = clean_dataframe(raw)
    if silver.isnull().sum().sum() != 0:
        raise ValueError("Silver zawiera braki po czyszczeniu")

    log(
        f"Czyszczenie: usunieto {stats.rows_in - stats.rows_out:,} wierszy "
        f"({stats.rows_in:,} -> {stats.rows_out:,})"
    )

    PROCESSED.mkdir(parents=True, exist_ok=True)
    silver_path = PROCESSED / "cleaned.parquet"
    silver.to_parquet(silver_path, index=False)
    log(f"Zapis silver: {silver_path} ({stats.rows_out:,} wierszy)")

    cfg = AzureStorageConfig()
    if upload_lake:
        log(f"Eksport silver do Azure: {cfg.silver_path}")
        write_parquet(silver, cfg.silver_path, cfg)
    log(
        f"Warstwa silver: {stats.rows_in:,} wierszy wejsciowych → "
        f"{stats.rows_out:,} po czyszczeniu (usunieto {stats.rows_in - stats.rows_out:,})"
    )

    progress(50, "ETL — agregaty warstwy gold")
    from src.cleaning.preprocess import build_gold_aggregates

    gold_tables = build_gold_aggregates(silver)
    paths: dict[str, str] = {}
    for name, table in gold_tables.items():
        table.to_parquet(PROCESSED / f"{name}.parquet", index=False)
        if upload_lake:
            lake_path = cfg.gold_path if name == "salary_by_location" else f"gold/{name}.parquet"
            write_parquet(table, lake_path, cfg)
            paths[name] = lake_path
        log(f"  Tabela gold '{name}': {len(table):,} wierszy")

    dwh_info: dict[str, Any] = {}
    if not skip_sql:
        if not _can_use_sql():
            log("UWAGA: SQL niedostepny (brak ODBC lub .env) — pomijam hurtownie.")
        else:
            progress(75, "ETL — ladowanie hurtowni Azure SQL")
            log("Budowa schematu gwiazdy i ladowanie do Azure SQL...")
            try:
                silver_sql = load_silver_dataframe()
                tables = build_star_schema(silver_sql)
                engine = get_sql_engine()
                loaded = load_to_azure_sql(tables, engine)
                from src.etl.load_dwh import verify_load

                verified = verify_load(engine)
                dwh_info = {"loaded": loaded, "verified": verified}
                log(f"Hurtownia SQL: zaladowano {loaded} tabel, weryfikacja: {verified}")
            except Exception as exc:
                err = str(exc)
                if "odbc" in err.lower() or "libodbc" in err.lower():
                    raise RuntimeError(
                        "Brak sterownika ODBC w kontenerze. Uzyj przycisku "
                        "'ETL bez SQL' lub zainstaluj unixODBC w obrazie Docker."
                    ) from exc
                raise
    else:
        log("Pominieto ladowanie SQL (tryb etl_skip_sql / Docker bez ODBC).")

    progress(100, "ETL — zakonczono pomyslnie")
    log("=== Koniec pipeline ETL ===")
    summary = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "engine": "sync",
        "raw": raw_info,
        "cleaning": asdict(stats),
        "gold": {"tables": list(gold_tables.keys()), "paths": paths},
        "dwh": dwh_info,
    }
    metrics_path = PROCESSED / "phase3_metrics.json"
    metrics_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary
