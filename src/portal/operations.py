"""Wykonanie faz projektu — wywolania z portalu."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.cleaning.preprocess import build_gold_aggregates, clean_dataframe
from src.config import PROJECT_ROOT, local_raw_data_path
from src.etl.lake_io import write_parquet
from src.etl.load_dwh import build_star_schema, get_sql_engine, load_to_azure_sql, verify_load
from src.mlflow_config import configure_mlflow
from src.portal.data_loader import load_raw_dataframe, load_silver_dataframe
from src.portal.dvc_runtime import run_dvc_push
from src.portal.etl_sync import run_etl_sync
from src.portal.job_context import capture_stdout_to_log, log, progress
from src.portal.params_io import load_params_file
from src.train.train_model import load_params, train_xgboost

PROCESSED = PROJECT_ROOT / "data" / "processed"
SILVER = PROCESSED / "cleaned.parquet"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def run_prepare(*, upload_lake: bool = False) -> dict[str, Any]:
    from src.portal.data_loader import load_raw_with_source

    progress(10, "Przygotowanie — wczytywanie raw")
    raw, raw_source = load_raw_with_source()
    log(
        f"Zrodlo raw: {'plik lokalny' if raw_source == 'local' else 'Azure Data Lake'} "
        f"({len(raw):,} wierszy)"
    )
    progress(30, "Przygotowanie — czyszczenie i silver")
    silver, stats = clean_dataframe(raw)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(SILVER, index=False)

    gold_tables = build_gold_aggregates(silver)
    for name, table in gold_tables.items():
        table.to_parquet(PROCESSED / f"{name}.parquet", index=False)

    if upload_lake:
        from src.config import AzureStorageConfig

        cfg = AzureStorageConfig()
        write_parquet(silver, cfg.silver_path, cfg)
        for name, table in gold_tables.items():
            lake_path = (
                cfg.gold_path if name == "salary_by_location" else f"gold/{name}.parquet"
            )
            write_parquet(table, lake_path, cfg)

    progress(100, "Przygotowanie zakonczone.")
    summary = {
        "finished_at": _now(),
        "rows_in": stats.rows_in,
        "rows_out": stats.rows_out,
        "gold_tables": list(gold_tables.keys()),
        "upload_lake": upload_lake,
    }
    _write_json(PROCESSED / "phase1_metrics.json", summary)
    log(f"Gold: {len(gold_tables)} tabel zapisanych lokalnie")
    return summary


def run_load_dwh() -> dict[str, Any]:
    silver = load_silver_dataframe()
    tables = build_star_schema(silver)
    engine = get_sql_engine()
    loaded = load_to_azure_sql(tables, engine)
    from src.etl.load_dwh import verify_load

    verified = verify_load(engine)
    summary = {
        "finished_at": _now(),
        "loaded": loaded,
        "verified": verified,
    }
    _write_json(PROCESSED / "phase2_metrics.json", summary)
    return summary


def run_prefect_etl(*, skip_sql: bool = False) -> dict[str, Any]:
    """Pipeline ETL — Prefect Server (gdy dostepny) lub tryb synchroniczny."""
    api_url = os.getenv("PREFECT_API_URL", "").strip()
    if api_url:
        os.environ["PREFECT_API_URL"] = api_url
        log(f"Orkiestracja Prefect (API: {api_url})")
        try:
            from src.etl.flows import etl_main

            with capture_stdout_to_log():
                return etl_main(skip_sql=skip_sql)
        except Exception as exc:
            log(f"Flow Prefect nieudany ({exc}) — przejscie na ETL synchroniczny.")
    log("ETL synchroniczny (bez rejestracji w Prefect Server)")
    with capture_stdout_to_log():
        return run_etl_sync(skip_sql=skip_sql, upload_lake=True)


def run_train(
    *,
    fast: bool = False,
    params_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    configure_mlflow()
    silver = load_silver_dataframe()
    params = params_override or load_params()
    with capture_stdout_to_log():
        result = train_xgboost(silver, params=params, force_tuning=not fast)
    metrics = result["metrics"]
    _write_json(
        PROCESSED / "phase4_metrics.json",
        {
            "finished_at": _now(),
            "metrics": metrics,
            "best_run_id": result.get("best_run_id"),
            "fast": fast,
        },
    )
    return {
        "finished_at": _now(),
        "metrics": metrics,
        "best_run_id": result.get("best_run_id"),
        "combinations_tested": result.get("combinations_tested"),
    }


def _dvc_repo_ready() -> bool:
    return (PROJECT_ROOT / ".dvc" / "config").is_file()


def _run_dvc_stages_direct(*, fast: bool) -> None:
    """Uruchomienie etapow pipeline DVC przez modul Python (bez CLI)."""
    from src.dvc.pipeline_stages import run_prepare as dvc_prepare
    from src.dvc.pipeline_stages import run_train as dvc_train

    params = load_params()
    if local_raw_data_path().is_file() or not SILVER.is_file():
        progress(15, "DVC — etap przygotowania danych (prepare)")
        log("Etap prepare: oczyszczenie i zapis warstwy silver")
        dvc_prepare(params)
    os.environ["DVC_FAST_TRAIN"] = "1" if fast else "0"
    progress(55, "DVC — etap treningu modelu (train)")
    log("Etap train: trenowanie modelu i zapis metryk")
    dvc_train(params)
    progress(90, "DVC — finalizacja artefaktow")


def run_dvc_repro(*, fast: bool = False, push: bool = False) -> dict[str, Any]:
    if not local_raw_data_path().is_file() and not SILVER.is_file():
        raise FileNotFoundError(
            "Brak CSV i silver. Uruchom najpierw przygotowanie danych (ETL) "
            "lub dodaj plik job_salary_prediction_dataset.csv."
        )

    use_cli = _dvc_repo_ready() and os.getenv("IN_DOCKER") != "1"
    if use_cli:
        env = {**os.environ, "DVC_FAST_TRAIN": "1" if fast else "0"}
        stages = ["train"] if SILVER.is_file() and not local_raw_data_path().is_file() else []
        cmd = [sys.executable, "-m", "dvc", "repro", *stages, "-f"]
        log(f"Uruchamiam pipeline DVC (CLI): {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log(out[-4000:])
        if proc.returncode != 0:
            log("Polecenie DVC nie powiodlo sie — uruchamiam etapy w Pythonie.")
            with capture_stdout_to_log():
                _run_dvc_stages_direct(fast=fast)
    else:
        log("Uruchamiam pipeline DVC (modul Python, tryb kontenera/lokalny).")
        with capture_stdout_to_log():
            _run_dvc_stages_direct(fast=fast)

    if push:
        if not _dvc_repo_ready():
            log("Pominieto wysylke na remote DVC — brak konfiguracji .dvc w kontenerze.")
        else:
            out = run_dvc_push()
            log(out[-2000:])

    metrics: dict[str, Any] = {}
    mpath = PROCESSED / "metrics.json"
    if mpath.is_file():
        metrics = json.loads(mpath.read_text(encoding="utf-8"))

    summary = {
        "finished_at": _now(),
        "fast": fast,
        "pushed": push,
        "dvc_metrics": metrics,
    }
    _write_json(PROCESSED / "phase5_pipeline_run.json", summary)
    return summary


def run_dvc_push_only() -> dict[str, Any]:
    if not _dvc_repo_ready():
        raise RuntimeError(
            "Repozytorium DVC nie jest skonfigurowane w kontenerze. "
            "Uruchom scripts/setup_dvc_remote.py lokalnie lub zamontuj katalog .dvc."
        )
    out = run_dvc_push()
    log(out[-3000:])
    _write_json(
        PROCESSED / "dvc_push_last.json",
        {"finished_at": _now(), "note": "Tylko push — bez aktualizacji podsumowania reprodukcji."},
    )
    return {"finished_at": _now(), "pushed": True}


JOB_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "prepare": lambda **kw: run_prepare(upload_lake=kw.get("upload_lake", False)),
    "prepare_lake": lambda **kw: run_prepare(upload_lake=True),
    "load_dwh": lambda **kw: run_load_dwh(),
    "etl": lambda **kw: run_prefect_etl(skip_sql=kw.get("skip_sql", False)),
    "etl_skip_sql": lambda **kw: run_prefect_etl(skip_sql=True),
    "train": lambda **kw: run_train(
        fast=kw.get("fast", False),
        params_override=kw.get("params_override"),
    ),
    "train_fast": lambda **kw: run_train(fast=True, params_override=kw.get("params_override")),
    "dvc_repro": lambda **kw: run_dvc_repro(fast=kw.get("fast", False), push=False),
    "dvc_repro_fast": lambda **kw: run_dvc_repro(fast=True, push=False),
    "dvc_repro_push": lambda **kw: run_dvc_repro(fast=kw.get("fast", False), push=True),
    "dvc_push": lambda **kw: run_dvc_push_only(),
}
