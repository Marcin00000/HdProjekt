#!/usr/bin/env python3
"""Weryfikacja srodowiska, Azure, DVC, MLflow i plikow projektu."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REMOTE_NAME = "azure_remote"

REQUIRED_PATHS = [
    "api/app.py",
    "input/.gitkeep",
    "docker-compose.yml",
    "readme.md",
    "docs/configuration.md",
    "docs/user-web.md",
    "docs/user-cli.md",
    "docs/tools.md",
    "docs/presentation.md",
    "src/monitoring/evidently_report.py",
    "src/monitoring/drift_retrain.py",
    "src/monitoring/flows.py",
    "params.yaml",
    "dvc.yaml",
    "requirements.txt",
]


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True)


def check_env_file() -> bool:
    print("\n=== Plik .env ===")
    env_file = ROOT / ".env"
    if not env_file.is_file():
        print("  BRAK: skopiuj .env.example do .env")
        return False
    print(f"  OK: {env_file}")
    return True


def check_project_files() -> bool:
    print("\n=== Pliki projektu ===")
    missing = [rel for rel in REQUIRED_PATHS if not (ROOT / rel).is_file()]
    if missing:
        for m in missing:
            print(f"  BRAK: {m}")
        return False
    print(f"  OK: {len(REQUIRED_PATHS)} plikow")
    return True


def check_storage(upload_raw: bool) -> bool:
    from src.config import AzureStorageConfig, local_raw_data_path

    print("\n=== Azure Data Lake ===")
    try:
        cfg = AzureStorageConfig()
    except ValueError as exc:
        print(f"  BLAD konfiguracji: {exc}")
        return False

    try:
        from adlfs import AzureBlobFileSystem
    except ImportError:
        print("  BLAD: brak pakietu adlfs — uruchom scripts/install.py")
        return False

    fs = AzureBlobFileSystem(
        account_name=cfg.account_name,
        account_key=cfg.account_key,
    )
    container_prefix = cfg.container
    raw_blob = f"{cfg.container}/{cfg.raw_path}"

    try:
        entries = fs.ls(container_prefix)
        print(f"  OK — kontener '{cfg.container}' ({len(entries)} elementow)")
    except Exception as exc:
        print(f"  BLAD listowania kontenera: {exc}")
        return False

    if fs.exists(raw_blob):
        print(f"  OK — plik raw: {cfg.raw_path}")
    else:
        print(f"  INFO — brak pliku w lake: {cfg.raw_path}")
        local = local_raw_data_path()
        if upload_raw and local.is_file():
            print(f"  Upload: {local} -> {raw_blob}")
            fs.put(str(local), raw_blob)
            print("  OK — upload zakonczony")
        elif local.is_file():
            print(f"  Wskazowka: --upload-raw aby wgrac {local.name}")
        else:
            print(f"  Brak lokalnego pliku: {local}")

    return True


def check_sql() -> bool:
    print("\n=== Azure SQL ===")
    try:
        from src.config import AzureSqlConfig

        cfg = AzureSqlConfig()
        url = cfg.sqlalchemy_url()
    except ValueError as exc:
        print(f"  BLAD konfiguracji: {exc}")
        return False

    try:
        import pyodbc
        from sqlalchemy import create_engine, text

        drivers = pyodbc.drivers()
        if not any("ODBC Driver" in d and "SQL Server" in d for d in drivers):
            print("  OSTRZEZENIE: brak ODBC Driver 18 for SQL Server")
    except ImportError:
        print("  BLAD: brak sqlalchemy/pyodbc")
        return False

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1 AS ok")).fetchone()
        print(f"  OK — polaczenie SQL (SELECT 1 -> {row[0]})")
        return True
    except Exception as exc:
        print(f"  BLAD polaczenia: {exc}")
        return False


def setup_dvc_remote() -> bool:
    from src.config import AzureStorageConfig, PROJECT_ROOT

    print("\n=== DVC remote (Azure) ===")
    dvc_dir = PROJECT_ROOT / ".dvc"
    if not dvc_dir.is_dir():
        try:
            _run([sys.executable, "-m", "dvc", "init"])
        except subprocess.CalledProcessError:
            return False
    else:
        print("  DVC juz zainicjalizowane")

    try:
        cfg = AzureStorageConfig()
    except ValueError as exc:
        print(f"  BLAD: {exc}")
        return False

    remote_url = f"azure://{cfg.container}/{cfg.dvc_container}"
    config_file = PROJECT_ROOT / ".dvc" / "config"
    config_text = config_file.read_text(encoding="utf-8") if config_file.is_file() else ""
    if REMOTE_NAME not in config_text:
        try:
            _run(
                [sys.executable, "-m", "dvc", "remote", "add", "-d", REMOTE_NAME, remote_url]
            )
        except subprocess.CalledProcessError:
            return False

    for key, value in (("account_name", cfg.account_name), ("account_key", cfg.account_key)):
        try:
            _run(
                [
                    sys.executable,
                    "-m",
                    "dvc",
                    "remote",
                    "modify",
                    REMOTE_NAME,
                    key,
                    value,
                    "--local",
                ]
            )
        except subprocess.CalledProcessError:
            return False

    _run([sys.executable, "-m", "dvc", "remote", "list", "-v"], check=False)
    print("  OK — remote skonfigurowany")
    return True


def check_mlflow_client(*, strict: bool = False) -> bool:
    from src.mlflow_config import EXPERIMENT_NAME, REGISTERED_MODEL_NAME, configure_mlflow

    print("\n=== MLflow (klient) ===")
    try:
        configure_mlflow()
        from mlflow.tracking import MlflowClient

        client = MlflowClient()
    except Exception as exc:
        print(f"  BLAD klienta MLflow: {exc}")
        return False

    exp = client.get_experiment_by_name(EXPERIMENT_NAME)
    if not exp:
        print(
            f"  INFO — brak eksperymentu {EXPERIMENT_NAME!r} (swiezy projekt). "
            "Po treningu: python scripts/run.py train"
        )
        return not strict

    runs = client.search_runs(experiment_ids=[exp.experiment_id])
    versions = client.search_model_versions(f"name='{REGISTERED_MODEL_NAME}'")
    if not runs:
        print(
            f"  INFO — eksperyment istnieje, brak runow ({len(versions)} wersji rejestru). "
            "Uruchom trening, aby zapelnic MLflow."
        )
        return not strict

    print(f"  OK — eksperyment: {len(runs)} runow, rejestr: {len(versions)} wersji")
    return True


def check_data_sources() -> bool:
    """Informacja o CSV/silver — nie blokuje swiezego klonu."""
    from src.config import PROJECT_ROOT, find_local_raw_csv
    from src.portal.model_artifacts import models_ready

    print("\n=== Dane i modele ===")
    local = find_local_raw_csv()
    silver = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"
    if local is not None:
        print(f"  OK — CSV lokalnie: {local.relative_to(PROJECT_ROOT)}")
    elif silver.is_file():
        print("  OK — warstwa silver: data/processed/cleaned.parquet")
    else:
        print(
            "  INFO — brak CSV/silver lokalnie. Skopiuj CSV do katalogu glownego lub "
            "input/job_salary_prediction_dataset.csv (Docker), albo uzyj danych w Azure lake."
        )
    if models_ready():
        print("  OK — modele produkcyjne: models/*.joblib")
    else:
        print(
            "  INFO — brak modelu (oczekiwane po clone). Portal dziala; "
            "prognoza po treningu lub dvc pull."
        )
    return True


def check_mlflow_server(port: int = 5003) -> bool:
    from src.mlflow_config import EXPERIMENT_NAME, mlflow_ui_command

    print(f"\n=== MLflow (serwer :{port}) ===")
    proc = subprocess.Popen(mlflow_ui_command(port=port), cwd=ROOT)
    time.sleep(12)
    base = f"http://127.0.0.1:{port}"
    ok = True
    try:
        with urllib.request.urlopen(
            f"{base}/ajax-api/3.0/mlflow/server-info", timeout=10
        ) as r:
            info = json.loads(r.read().decode())
        if info.get("store_type") != "SqlStore":
            ok = False
        data = json.dumps({"max_results": 20}).encode()
        req = urllib.request.Request(
            f"{base}/ajax-api/2.0/mlflow/experiments/search",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            exps = json.loads(r.read().decode())
        names = [e["name"] for e in exps.get("experiments", [])]
        if EXPERIMENT_NAME not in names:
            ok = False
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code}")
        ok = False
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    print("  OK" if ok else "  BLAD")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Weryfikacja projektu")
    parser.add_argument("--env", action="store_true", help="Sprawdz plik .env")
    parser.add_argument("--azure", action="store_true", help="Test Azure Data Lake")
    parser.add_argument("--sql", action="store_true", help="Test Azure SQL")
    parser.add_argument("--upload-raw", action="store_true", help="Wgraj CSV do lake")
    parser.add_argument("--dvc", action="store_true", help="Konfiguracja DVC remote")
    parser.add_argument("--mlflow", action="store_true", help="Sprawdz eksperyment MLflow")
    parser.add_argument(
        "--mlflow-strict",
        action="store_true",
        help="MLflow musi miec run (nie tylko pusty eksperyment)",
    )
    parser.add_argument("--mlflow-server", action="store_true", help="Test serwera MLflow UI")
    parser.add_argument("--project", action="store_true", help="Sprawdz pliki projektu")
    parser.add_argument("--data", action="store_true", help="Status CSV/silver/modeli (informacyjnie)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="env + project + data + azure + sql + dvc + mlflow (lagodny dla swiezego projektu)",
    )
    args = parser.parse_args()

    if not any(
        (
            args.env,
            args.azure,
            args.sql,
            args.dvc,
            args.mlflow,
            args.mlflow_strict,
            args.mlflow_server,
            args.project,
            args.data,
            args.all,
        )
    ):
        args.project = True
        args.env = True

    if args.all:
        args.env = args.project = args.data = args.azure = args.sql = args.dvc = args.mlflow = True

    print(f"Projekt: {ROOT}")
    results: list[bool] = []

    if args.env:
        results.append(check_env_file())
    if args.project:
        results.append(check_project_files())
    if args.data:
        results.append(check_data_sources())
    if args.azure:
        results.append(check_storage(upload_raw=args.upload_raw))
    if args.sql:
        results.append(check_sql())
    if args.dvc:
        results.append(setup_dvc_remote())
    if args.mlflow:
        results.append(check_mlflow_client(strict=args.mlflow_strict))
    if args.mlflow_server:
        results.append(check_mlflow_server())

    print("\n=== Podsumowanie ===")
    if results and all(results):
        print("Weryfikacja zakonczona powodzeniem.")
        return 0
    if not results:
        return 0
    print("Czesc testow nie powiodla sie.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
