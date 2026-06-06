"""Sciezki plikow podsumowan operacji w data/processed/."""

from __future__ import annotations

from pathlib import Path

from src.config import PROJECT_ROOT

PROCESSED = PROJECT_ROOT / "data" / "processed"
DWH_DIR = PROJECT_ROOT / "data" / "dwh"

PREPARE_SUMMARY = PROCESSED / "prepare_summary.json"
DWH_SUMMARY = PROCESSED / "dwh_summary.json"
ETL_SUMMARY = PROCESSED / "etl_summary.json"
TRAINING_SUMMARY = PROCESSED / "training_summary.json"
DVC_RUN_SUMMARY = PROCESSED / "dvc_run_summary.json"
