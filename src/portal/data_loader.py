"""Wspólne wczytywanie raw / silver dla dashboardu i pipeline."""

from __future__ import annotations

import pandas as pd

from src.config import AzureStorageConfig, PROJECT_ROOT, find_local_raw_csv
from src.etl.lake_io import read_raw_csv, read_parquet

SILVER_PATH = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"
GOLD_BY_LOCATION = PROJECT_ROOT / "data" / "processed" / "salary_by_location.parquet"


def load_raw_with_source() -> tuple[pd.DataFrame, str]:
    """CSV lokalny, w razie braku — Azure Data Lake (raw)."""
    local = find_local_raw_csv()
    if local is not None:
        return pd.read_csv(local), "local"
    cfg = AzureStorageConfig()
    return read_raw_csv(cfg), "azure"


def load_raw_dataframe() -> pd.DataFrame:
    df, _ = load_raw_with_source()
    return df


def load_silver_dataframe() -> pd.DataFrame:
    if SILVER_PATH.is_file():
        return pd.read_parquet(SILVER_PATH)
    cfg = AzureStorageConfig()
    return read_parquet(cfg.silver_path, cfg)
