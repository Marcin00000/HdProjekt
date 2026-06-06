"""Odczyt i zapis danych w Azure Data Lake (parquet / CSV)."""

from __future__ import annotations

import pandas as pd

from src.config import AzureStorageConfig, find_local_raw_csv


def read_raw_csv(cfg: AzureStorageConfig | None = None, prefer_lake: bool = True) -> pd.DataFrame:
    """Wczytuje surowy CSV z lake (domyślnie) lub lokalnie jako fallback."""
    cfg = cfg or AzureStorageConfig()
    opts = cfg.storage_options

    if prefer_lake:
        try:
            path = cfg.abfs_path(cfg.raw_path)
            return pd.read_csv(path, storage_options=opts)
        except Exception as exc:
            local = find_local_raw_csv()
            if local is not None:
                print(f"Ostrzeżenie: odczyt z lake nie powiódł się ({exc}), używam pliku lokalnego.")
                return pd.read_csv(local)
            raise

    local = find_local_raw_csv()
    if local is not None:
        return pd.read_csv(local)
    path = cfg.abfs_path(cfg.raw_path)
    return pd.read_csv(path, storage_options=opts)


def write_parquet(df: pd.DataFrame, lake_path: str, cfg: AzureStorageConfig | None = None) -> str:
    """Zapisuje DataFrame do ścieżki w lake (parquet). Zwraca pełną ścieżkę abfs."""
    cfg = cfg or AzureStorageConfig()
    abfs = cfg.abfs_path(lake_path)
    df.to_parquet(abfs, index=False, storage_options=cfg.storage_options)
    return abfs


def read_parquet(lake_path: str, cfg: AzureStorageConfig | None = None) -> pd.DataFrame:
    cfg = cfg or AzureStorageConfig()
    return pd.read_parquet(cfg.abfs_path(lake_path), storage_options=cfg.storage_options)
