"""Wczytywanie konfiguracji z pliku .env (katalog główny projektu)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Brak wymaganej zmiennej środowiskowej: {name}")
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


class AzureStorageConfig:
    def __init__(self) -> None:
        self.account_name = _require("AZURE_STORAGE_ACCOUNT_NAME")
        self.account_key = _require("AZURE_STORAGE_ACCOUNT_KEY")
        self.container = _optional("AZURE_STORAGE_CONTAINER", "job-data")
        self.raw_path = _optional(
            "AZURE_LAKE_RAW_PATH", "raw/job_salary_prediction_dataset.csv"
        )
        self.silver_path = _optional("AZURE_LAKE_SILVER_PATH", "silver/cleaned.parquet")
        self.gold_path = _optional(
            "AZURE_LAKE_GOLD_PATH", "gold/salary_by_location.parquet"
        )
        self.dvc_container = _optional("AZURE_DVC_CONTAINER", "dvc-artifacts")

    @property
    def abfs_base(self) -> str:
        return f"abfs://{self.container}@{self.account_name}.dfs.core.windows.net"

    def abfs_path(self, blob_path: str) -> str:
        return f"{self.abfs_base}/{blob_path.lstrip('/')}"

    @property
    def storage_options(self) -> dict[str, str]:
        return {
            "account_name": self.account_name,
            "account_key": self.account_key,
        }


class AzureSqlConfig:
    def __init__(self) -> None:
        self.connection_string = _optional("AZURE_SQL_CONNECTION_STRING") or None
        self.server = _optional("AZURE_SQL_SERVER")
        self.database = _optional("AZURE_SQL_DATABASE")
        self.user = _optional("AZURE_SQL_USER")
        self.password = _optional("AZURE_SQL_PASSWORD")

    def sqlalchemy_url(self) -> str:
        if self.connection_string:
            return self.connection_string
        if not all([self.server, self.database, self.user, self.password]):
            raise ValueError(
                "Uzupełnij AZURE_SQL_SERVER, AZURE_SQL_DATABASE, "
                "AZURE_SQL_USER, AZURE_SQL_PASSWORD lub AZURE_SQL_CONNECTION_STRING"
            )
        from urllib.parse import quote_plus

        params = quote_plus(
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server=tcp:{self.server},1433;"
            f"Database={self.database};"
            f"Uid={self.user};"
            f"Pwd={self.password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=60;"
        )
        return f"mssql+pyodbc:///?odbc_connect={params}"


def local_raw_data_path() -> Path:
    rel = _optional("LOCAL_RAW_DATA_PATH", "job_salary_prediction_dataset.csv")
    return PROJECT_ROOT / rel


def find_local_raw_csv() -> Path | None:
    """Plik CSV: sciezka z .env, katalog glowny lub input/ (Docker)."""
    primary = local_raw_data_path()
    if primary.is_file():
        return primary
    fallback = PROJECT_ROOT / "input" / "job_salary_prediction_dataset.csv"
    if fallback.is_file():
        return fallback
    return None
