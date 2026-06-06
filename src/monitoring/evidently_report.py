"""Raport driftu: dane treningowe modelu (baseline) vs aktualny rynek (silver po ETL)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PROJECT_ROOT
from src.monitoring.baseline import (
    DRIFT_COLUMNS,
    baseline_exists,
    load_current_market_data,
    load_simulation_meta,
    load_training_baseline,
    simulation_is_active,
)
from src.monitoring.params import load_monitoring_config

DRIFT_METRICS_PATH = PROJECT_ROOT / "data" / "processed" / "drift_metrics.json"
REPORTS_DIR = PROJECT_ROOT / "reports"


def _prepare_for_evidently(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object" or str(out[col].dtype) == "category":
            out[col] = out[col].astype(str)
    return out


def _parse_evidently_snapshot(snapshot: Any) -> dict[str, Any]:
    data = snapshot.dict()
    share_drifted = 0.0
    drifted_count = 0
    column_drifts: list[dict[str, Any]] = []

    for metric in data.get("metrics", []):
        name = str(metric.get("metric_name") or "")
        value = metric.get("value")
        if "DriftedColumnsCount" in name and isinstance(value, dict):
            share_drifted = float(value.get("share", 0) or 0)
            drifted_count = int(value.get("count", 0) or 0)
        if "ValueDrift" in name:
            col_match = re.search(r"column=([^,]+)", name)
            col = col_match.group(1) if col_match else name
            drifted = False
            if isinstance(value, (int, float)):
                drifted = float(value) == 0.0
            column_drifts.append(
                {
                    "column": col,
                    "drift_detected": drifted,
                    "detail": name,
                }
            )

    return {
        "share_drifted_columns": share_drifted,
        "drifted_columns_count": drifted_count,
        "column_drifts": column_drifts,
    }


def compute_drift_report(
    *,
    report_name: str | None = None,
) -> dict[str, Any]:
    """
    Porownanie:
    - referencja = ``training_baseline.parquet`` (dane z treningu modelu),
    - biezace = ``cleaned.parquet`` po ETL lub symulowany silver (demo).
    """
    cfg = load_monitoring_config()
    ref_n = int(cfg.get("reference_sample_size", 5000))
    cur_n = int(cfg.get("current_sample_size", cfg.get("production_sample_size", 5000)))
    threshold = float(cfg.get("drift_threshold", 0.5))
    min_rows = int(cfg.get("min_current_rows", cfg.get("min_predictions", 1000)))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    html_name = report_name or f"drift_report_{stamp}.html"
    html_path = REPORTS_DIR / html_name

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison": "training_baseline vs current_silver",
        "drift_threshold": threshold,
        "report_html": str(html_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "report_url": f"/reports/{html_name}",
        "simulation_active": simulation_is_active(),
        "simulation_meta": load_simulation_meta(),
    }

    if not baseline_exists():
        result.update(
            {
                "status": "insufficient_data",
                "drift_alert": False,
                "message": (
                    "Brak baseline treningowego (training_baseline.parquet). "
                    "Uruchom trening modelu — zapisze referencje do monitoringu."
                ),
            }
        )
        DRIFT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRIFT_METRICS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    try:
        reference = load_training_baseline(max_rows=ref_n)
        current, current_source = load_current_market_data(max_rows=cur_n)
    except FileNotFoundError as exc:
        result.update(
            {
                "status": "insufficient_data",
                "drift_alert": False,
                "message": str(exc),
            }
        )
        DRIFT_METRICS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    result["reference_rows"] = len(reference)
    result["current_rows"] = len(current)
    result["current_source"] = current_source
    result["reference_label"] = "training_baseline (dane treningowe modelu)"
    result["min_current_rows_required"] = min_rows

    if len(current) < min_rows:
        result.update(
            {
                "status": "insufficient_data",
                "drift_alert": False,
                "message": (
                    f"Za malo wierszy w aktualnym silver ({len(current)} < {min_rows}). "
                    "Uruchom ETL lub zwieksz probe w symulacji."
                ),
            }
        )
        DRIFT_METRICS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result

    cols = [c for c in DRIFT_COLUMNS if c in reference.columns and c in current.columns]
    reference = _prepare_for_evidently(reference[cols])
    current = _prepare_for_evidently(current[cols])

    from evidently import Report
    from evidently.presets import DataDriftPreset

    snapshot = Report([DataDriftPreset()]).run(reference_data=reference, current_data=current)
    snapshot.save_html(str(html_path))

    parsed = _parse_evidently_snapshot(snapshot)
    share = parsed["share_drifted_columns"]
    drift_alert = share >= threshold

    salary_drift = any(
        c.get("column") == "salary" and c.get("drift_detected") for c in parsed["column_drifts"]
    )

    result.update(parsed)
    result["status"] = "alert" if drift_alert else "ok"
    result["drift_alert"] = drift_alert
    result["salary_drift_detected"] = salary_drift
    result["message"] = (
        f"Rynek odbiega od danych treningowych: {share:.0%} kolumn z driftem "
        f"(prog {threshold:.0%}). "
        + ("Wykryto zmiane rozkladu pensji (salary) — rozwaz retrening." if salary_drift else "")
        if drift_alert
        else f"Model na razie zgodny z rynkiem ({share:.0%} kolumn z driftem)."
    )

    DRIFT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_METRICS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def load_drift_metrics() -> dict[str, Any]:
    if not DRIFT_METRICS_PATH.is_file():
        return {}
    return json.loads(DRIFT_METRICS_PATH.read_text(encoding="utf-8"))


def list_report_files() -> list[dict[str, str]]:
    if not REPORTS_DIR.is_dir():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(REPORTS_DIR.glob("drift_report_*.html"), reverse=True):
        items.append(
            {
                "name": path.name,
                "url": f"/reports/{path.name}",
                "modified": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return items
