"""
Weryfikacja połączenia z Azure Data Lake i Azure SQL.

Użycie (z katalogu głównego projektu):
    pip install -r requirements.txt
    python scripts/setup_azure_check.py
    python scripts/setup_azure_check.py --upload-raw
    python scripts/setup_azure_check.py --skip-sql
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    PROJECT_ROOT,
    AzureSqlConfig,
    AzureStorageConfig,
    local_raw_data_path,
)


def check_storage(upload_raw: bool) -> bool:
    print("\n=== Azure Data Lake (Storage Account) ===")
    try:
        cfg = AzureStorageConfig()
    except ValueError as exc:
        print(f"  BŁĄD konfiguracji: {exc}")
        return False

    try:
        from adlfs import AzureBlobFileSystem
    except ImportError:
        print("  BŁĄD: pip install -r requirements.txt")
        return False

    fs = AzureBlobFileSystem(
        account_name=cfg.account_name,
        account_key=cfg.account_key,
    )
    container_prefix = cfg.container
    raw_blob = f"{cfg.container}/{cfg.raw_path}"

    try:
        entries = fs.ls(container_prefix)
        print(
            f"  OK — kontener '{cfg.container}' dostępny "
            f"({len(entries)} elementów na najwyższym poziomie)"
        )
        for name in sorted(entries)[:10]:
            print(f"       - {name}")
        if len(entries) > 10:
            print(f"       ... i {len(entries) - 10} więcej")
    except Exception as exc:
        print(f"  BŁĄD listowania kontenera: {exc}")
        return False

    if fs.exists(raw_blob):
        print(f"  OK — plik raw istnieje: {cfg.raw_path}")
        _try_read_sample(cfg, fs, raw_blob)
    else:
        print(f"  INFO — brak pliku w lake: {cfg.raw_path}")
        local = local_raw_data_path()
        if upload_raw and local.is_file():
            print(f"  Upload: {local} → {raw_blob}")
            fs.put(str(local), raw_blob)
            print("  OK — upload zakończony")
            _try_read_sample(cfg, fs, raw_blob)
        elif local.is_file():
            print(f"  Wskazówka: uruchom z --upload-raw aby wgrać {local.name}")
        else:
            print(f"  Brak lokalnego pliku: {local}")

    return True


def _try_read_sample(cfg: AzureStorageConfig, fs, raw_blob: str) -> None:
    if not fs.exists(raw_blob):
        return
    try:
        import pandas as pd

        abfs = cfg.abfs_path(cfg.raw_path)
        opts = cfg.storage_options
        if cfg.raw_path.endswith(".parquet"):
            df = pd.read_parquet(abfs, storage_options=opts)
        else:
            df = pd.read_csv(abfs, storage_options=opts, nrows=5)
        print(f"  OK — próbka odczytu: {df.shape[1]} kolumn, typ: {cfg.raw_path.split('.')[-1]}")
    except Exception as exc:
        print(f"  OSTRZEŻENIE — odczyt próbki nie powiódł się: {exc}")


def check_sql() -> bool:
    print("\n=== Azure SQL Database ===")
    try:
        cfg = AzureSqlConfig()
        url = cfg.sqlalchemy_url()
    except ValueError as exc:
        print(f"  BŁĄD konfiguracji: {exc}")
        return False

    try:
        import pyodbc
        from sqlalchemy import create_engine, text

        drivers = pyodbc.drivers()
        if not any("ODBC Driver" in d and "SQL Server" in d for d in drivers):
            print("  OSTRZEŻENIE: brak ODBC Driver 18 for SQL Server")
            print(f"  Sterowniki: {drivers or '(brak)'}")
    except ImportError:
        print("  BŁĄD: pip install sqlalchemy pyodbc")
        return False

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1 AS ok")).fetchone()
        print(f"  OK — polaczenie SQL (SELECT 1 -> {row[0]})")
        return True
    except Exception as exc:
        print(f"  BŁĄD połączenia: {exc}")
        print("  Sprawdź firewall (Add client IP), login i hasło.")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Test połączenia Azure")
    parser.add_argument(
        "--upload-raw",
        action="store_true",
        help="Wgraj LOCAL_RAW_DATA_PATH do Azure Lake (raw/)",
    )
    parser.add_argument(
        "--skip-sql",
        action="store_true",
        help="Pomiń test Azure SQL",
    )
    args = parser.parse_args()

    print(f"Projekt: {PROJECT_ROOT}")
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        print("BŁĄD: brak pliku .env — skopiuj z .env.example")
        return 1

    ok_storage = check_storage(upload_raw=args.upload_raw)
    ok_sql = check_sql() if not args.skip_sql else True
    if args.skip_sql:
        print("\n=== Azure SQL — pominięto (--skip-sql) ===")

    print("\n=== Podsumowanie ===")
    if ok_storage and ok_sql:
        print("Wszystkie testy zakończone powodzeniem.")
        return 0
    if ok_storage and args.skip_sql:
        print("Data Lake OK. SQL nie testowano.")
        return 0
    print("Część testów nie powiodła się.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
