#!/usr/bin/env python3
"""Uruchamianie operacji pipeline, aplikacji i narzedzi pomocniczych."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODELS = [
    ROOT / "models" / "preprocessor.joblib",
    ROOT / "models" / "xgboost_model.joblib",
]


def _run_cmd(cmd: list[str], check: bool = True, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check, env=env).returncode


def cmd_prepare(args: argparse.Namespace) -> int:
    from src.cleaning.preprocess import build_gold_aggregates, clean_dataframe
    from src.config import AzureStorageConfig, PROJECT_ROOT
    from src.eda.summarize import run_eda
    from src.etl.lake_io import read_raw_csv, write_parquet
    from src.processed_artifacts import PREPARE_SUMMARY, PROCESSED

    print("=== Przygotowanie danych: wczytanie raw ===")
    cfg = AzureStorageConfig()
    raw = read_raw_csv(cfg)
    print(f"Wczytano {len(raw):,} wierszy")

    print("\n=== EDA (raw) ===")
    eda_path = run_eda(raw, label="raw")
    print(f"Raport: {eda_path}")

    print("\n=== Czyszczenie -> silver ===")
    silver, stats = clean_dataframe(raw)
    print(
        f"  wejscie: {stats.rows_in:,} | wyjscie: {stats.rows_out:,} | "
        f"duplikaty: {stats.duplicates_removed} | "
        f"niepoprawne: {stats.invalid_removed} | outliery: {stats.outliers_removed}"
    )
    run_eda(silver, label="silver")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    silver_local = PROCESSED / "cleaned.parquet"
    silver.to_parquet(silver_local, index=False)
    print(f"  lokalnie: {silver_local}")

    if not args.local_only:
        print("\n=== Zapis silver do lake ===")
        abfs_silver = write_parquet(silver, cfg.silver_path, cfg)
        print(f"  {abfs_silver}")

    print("\n=== Agregaty gold ===")
    gold_tables = build_gold_aggregates(silver)
    metrics = {
        "cleaning": {
            "rows_in": stats.rows_in,
            "rows_out": stats.rows_out,
            "duplicates_removed": stats.duplicates_removed,
            "invalid_removed": stats.invalid_removed,
            "outliers_removed": stats.outliers_removed,
        },
        "gold_tables": list(gold_tables.keys()),
    }
    PREPARE_SUMMARY.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    for name, table in gold_tables.items():
        local_gold = PROCESSED / f"{name}.parquet"
        table.to_parquet(local_gold, index=False)
        print(f"  {name}: {len(table)} wierszy -> {local_gold.name}")
        if not args.local_only:
            lake_path = (
                cfg.gold_path if name == "salary_by_location" else f"gold/{name}.parquet"
            )
            write_parquet(table, lake_path, cfg)
            print(f"    lake: {lake_path}")

    print("\n=== Przygotowanie zakonczone ===")
    return 0


def cmd_load_dwh(args: argparse.Namespace) -> int:
    import pandas as pd

    from src.config import AzureStorageConfig, PROJECT_ROOT
    from src.etl.lake_io import read_parquet
    from src.etl.load_dwh import (
        build_star_schema,
        get_sql_engine,
        load_to_azure_sql,
        run_analytics_queries,
        verify_load,
    )
    from src.processed_artifacts import DWH_DIR, DWH_SUMMARY, PROCESSED

    local_path = PROCESSED / "cleaned.parquet"

    def _load_silver() -> pd.DataFrame:
        if args.local_silver and local_path.is_file():
            print(f"Silver (lokalnie): {local_path}")
            return pd.read_parquet(local_path)
        cfg = AzureStorageConfig()
        print(f"Silver (lake): {cfg.silver_path}")
        try:
            return read_parquet(cfg.silver_path, cfg)
        except Exception as exc:
            if local_path.is_file():
                print(f"Lake nieudane ({exc}), fallback lokalny.")
                return pd.read_parquet(local_path)
            raise

    print("=== Hurtownia: wczytanie silver ===")
    silver = _load_silver()
    print(f"Wierszy silver: {len(silver):,}")

    print("\n=== Budowa schematu gwiazdy ===")
    tables = build_star_schema(silver)
    for name, df in tables.items():
        print(f"  {name}: {len(df):,} wierszy")

    DWH_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(DWH_DIR / f"{name}.parquet", index=False)
    print(f"  kopie lokalne: {DWH_DIR}")

    metrics: dict = {
        "silver_rows": len(silver),
        "tables_built": {k: len(v) for k, v in tables.items()},
    }

    if args.build_only:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        DWH_SUMMARY.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
        print(f"Metryki: {DWH_SUMMARY}")
        return 0

    print("\n=== Zapis do Azure SQL ===")
    engine = get_sql_engine()
    counts = load_to_azure_sql(tables, engine)
    verified = verify_load(engine)
    metrics["loaded"] = counts
    metrics["verified"] = verified

    if not args.skip_analytics:
        print("\n=== Zapytania analityczne ===")
        results = run_analytics_queries(engine)
        for qname, df in results.items():
            print(f"\n--- {qname} ---")
            print(df.to_string(index=False))
        metrics["analytics_preview"] = {
            k: v.to_dict(orient="records") for k, v in results.items()
        }

    PROCESSED.mkdir(parents=True, exist_ok=True)
    DWH_SUMMARY.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    print(f"\nMetryki: {DWH_SUMMARY}")
    print("\n=== Zaladowanie hurtowni zakonczone ===")
    return 0


def cmd_etl(args: argparse.Namespace) -> int:
    from src.etl.flows import etl_main

    if args.serve:
        etl_main.serve(
            name="weekly-etl-job-salary",
            cron="0 3 * * 0",
            tags=["hd-projekt", "etl"],
            parameters={"skip_sql": args.skip_sql},
        )
        return 0

    result = etl_main(skip_sql=args.skip_sql)
    print("\n=== Podsumowanie etl_main ===")
    print(f"  raw rows: {result['raw']['rows']:,}")
    print(f"  silver out: {result['cleaning']['rows_out']:,}")
    print(f"  gold tables: {result['gold']['tables']}")
    if result.get("dwh"):
        print(f"  fact_salaries: {result['dwh']['verified'].get('fact_salaries', 'n/a')}")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    from src.config import AzureStorageConfig, PROJECT_ROOT
    from src.etl.lake_io import read_parquet
    from src.mlflow_config import configure_mlflow
    from src.train.train_model import train_xgboost

    import pandas as pd

    configure_mlflow()

    local = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"
    if local.is_file():
        print(f"Silver (lokalnie): {local}")
        silver = pd.read_parquet(local)
    else:
        cfg = AzureStorageConfig()
        print(f"Silver (lake): {cfg.silver_path}")
        silver = read_parquet(cfg.silver_path, cfg)

    print(f"Wierszy: {len(silver):,}")
    print("\n=== Trening XGBoost + MLflow ===")
    print(f"  MLflow URI: {configure_mlflow()}")
    result = train_xgboost(silver, force_tuning=not args.no_tune)

    m = result["metrics"]
    print("\n=== Wyniki ===")
    print(f"  RMSE: {m['rmse']:,.0f} | MAE: {m['mae']:,.0f} | R2: {m['r2']:.4f}")
    print(f"  run_id: {result['best_run_id']}")
    print(f"  modele: {PROJECT_ROOT / 'models'}")
    print("  UI: python scripts/run.py mlflow-ui")
    return 0


def cmd_dvc(args: argparse.Namespace) -> int:
    if args.setup_dvc:
        return subprocess.call([sys.executable, str(ROOT / "scripts" / "verify.py"), "--dvc"])

    raw = ROOT / "job_salary_prediction_dataset.csv"
    if not raw.is_file():
        print(f"UWAGA: brak {raw.name} — prepare probuje wczytac raw z Azure")

    dvc_dir = ROOT / ".dvc"
    if not dvc_dir.is_dir():
        print("Inicjalizacja DVC...")
        if _run_cmd([sys.executable, "-m", "dvc", "init"], check=False) != 0:
            return 1

    subprocess.call(
        [sys.executable, str(ROOT / "scripts" / "verify.py"), "--dvc"],
        cwd=ROOT,
    )

    print("\n=== DVC repro ===")
    cmd = [sys.executable, "-m", "dvc", "repro"]
    if args.stage:
        cmd.append(args.stage)
    env = os.environ.copy()
    venv_scripts = ROOT / ".venv" / "Scripts"
    if venv_scripts.is_dir():
        env["PATH"] = str(venv_scripts) + os.pathsep + env.get("PATH", "")
    if args.fast:
        env["DVC_FAST_TRAIN"] = "1"
        print("  (tryb szybki: bez tuningu)")
    code = _run_cmd(cmd, check=False, env=env)
    if code != 0:
        return code

    _run_cmd([sys.executable, "-m", "dvc", "metrics", "show"], check=False)
    if args.push:
        print("\n=== DVC push ===")
        code = _run_cmd([sys.executable, "-m", "dvc", "push"], check=False)
        if code != 0:
            return code

    print("\n=== Pipeline DVC zakonczony ===")
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    if args.docker:
        return subprocess.call(["docker", "compose", "up", "--build"], cwd=ROOT)

    missing = [p for p in MODELS if not p.is_file()]
    if missing and not args.docker:
        print("Brak modeli — uruchom najpierw:")
        print("  python scripts/run.py dvc --fast")
        print("  lub: dvc pull")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.app:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    print(f"Portal: http://{args.host}:{args.port}/")
    print(f"Dashboard: http://{args.host}:{args.port}/dashboard")
    print("Docker: python scripts/run.py app --docker  -> http://localhost:8080")
    return subprocess.call(cmd, cwd=ROOT)


def cmd_mlflow_ui(args: argparse.Namespace) -> int:
    from src.mlflow_config import (
        configure_mlflow,
        ensure_experiment,
        get_artifact_root_uri,
        get_tracking_uri,
        mlflow_ui_command,
    )

    configure_mlflow()
    ensure_experiment()
    print(f"MLflow tracking URI: {get_tracking_uri()}")
    print(f"Artifact root: {get_artifact_root_uri()}")
    print(f"UI: http://127.0.0.1:{args.port}")
    return subprocess.call(mlflow_ui_command(port=args.port), cwd=ROOT)


def cmd_drift_simulate(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "simulate_drift.py"),
        "--scenario",
        args.scenario,
        "--count",
        str(args.count),
    ]
    return subprocess.call(cmd, cwd=ROOT)


def cmd_drift_retrain(_args: argparse.Namespace) -> int:
    from src.monitoring.drift_retrain import check_drift_and_retrain

    result = check_drift_and_retrain(manual=True)
    print(result.get("message", result))
    return 0 if result.get("ok", True) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Operacje projektu HdProjekt")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="EDA, czyszczenie, silver i gold")
    p_prepare.add_argument("--local-only", action="store_true")
    p_prepare.set_defaults(func=cmd_prepare)

    p_dwh = sub.add_parser("load-dwh", help="Schemat gwiazdy i zaladowanie Azure SQL")
    p_dwh.add_argument("--local-silver", action="store_true")
    p_dwh.add_argument("--skip-analytics", action="store_true")
    p_dwh.add_argument("--build-only", action="store_true")
    p_dwh.set_defaults(func=cmd_load_dwh)

    p_etl = sub.add_parser("etl", help="Pipeline Prefect etl_main")
    p_etl.add_argument("--skip-sql", action="store_true")
    p_etl.add_argument("--serve", action="store_true", help="Harmonogram cron w Prefect")
    p_etl.set_defaults(func=cmd_etl)

    p_train = sub.add_parser("train", help="Trening XGBoost + MLflow")
    p_train.add_argument("--no-tune", action="store_true")
    p_train.set_defaults(func=cmd_train)

    p_dvc = sub.add_parser("dvc", help="Pipeline DVC (prepare -> train)")
    p_dvc.add_argument("--fast", action="store_true")
    p_dvc.add_argument("--push", action="store_true")
    p_dvc.add_argument("--setup-dvc", action="store_true")
    p_dvc.add_argument("--stage", choices=("prepare", "train"))
    p_dvc.set_defaults(func=cmd_dvc)

    p_app = sub.add_parser("app", help="Portal FastAPI (uvicorn lub Docker)")
    p_app.add_argument("--docker", action="store_true")
    p_app.add_argument("--host", default="127.0.0.1")
    p_app.add_argument("--port", type=int, default=8000)
    p_app.add_argument("--reload", action="store_true")
    p_app.set_defaults(func=cmd_app)

    p_mlflow = sub.add_parser("mlflow-ui", help="Serwer MLflow UI")
    p_mlflow.add_argument("--port", type=int, default=5000)
    p_mlflow.set_defaults(func=cmd_mlflow_ui)

    p_sim = sub.add_parser("drift-simulate", help="Symulacja zmiany rynku (demo driftu)")
    p_sim.add_argument("--scenario", default="salary_market_up")
    p_sim.add_argument("--count", type=int, default=5000)
    p_sim.set_defaults(func=cmd_drift_simulate)

    p_retrain = sub.add_parser("drift-retrain", help="Sprawdzenie driftu i retrening")
    p_retrain.set_defaults(func=cmd_drift_retrain)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
