"""Drift przekracza prog — ponowny trening modelu i audyt."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT
from src.monitoring.baseline import baseline_exists, clear_drift_simulation, simulation_is_active
from src.monitoring.evidently_report import compute_drift_report, load_drift_metrics
from src.monitoring.params import load_monitoring_config
from src.portal.job_context import log, progress

DRIFT_RETRAIN_LAST_PATH = PROJECT_ROOT / "data" / "processed" / "drift_retrain_last.json"


def _write_audit(payload: dict[str, Any]) -> None:
    DRIFT_RETRAIN_LAST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_RETRAIN_LAST_PATH.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def load_retrain_audit() -> dict[str, Any]:
    if not DRIFT_RETRAIN_LAST_PATH.is_file():
        return {}
    return json.loads(DRIFT_RETRAIN_LAST_PATH.read_text(encoding="utf-8"))


def should_retrain(
    metrics: dict[str, Any],
    cfg: dict[str, Any] | None = None,
    *,
    manual: bool = False,
    force: bool = False,
) -> bool:
    """Czy uruchomic retrening po raporcie driftu."""
    cfg = cfg or load_monitoring_config()
    if force:
        return metrics.get("status") not in ("insufficient_data", None) and bool(
            metrics.get("current_rows")
        )
    if metrics.get("status") == "insufficient_data":
        return False
    if not metrics.get("drift_alert"):
        return False
    if not manual and not bool(cfg.get("auto_retrain_enabled", False)):
        return False
    return True


def check_drift_and_retrain(
    *,
    manual: bool = False,
    force: bool = False,
    skip_drift_report: bool = False,
) -> dict[str, Any]:
    """
    1) Raport driftu (baseline vs silver),
    2) Decyzja o retreningu,
    3) Opcjonalnie train_fast / train + nowy baseline.
    """
    cfg = load_monitoring_config()
    started_at = datetime.now(timezone.utc).isoformat()

    if not baseline_exists():
        msg = "Brak training_baseline — najpierw wytrenuj model."
        audit = {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "retrained": False,
            "skipped_reason": "no_baseline",
            "message": msg,
        }
        _write_audit(audit)
        return audit

    progress(5, "Analiza driftu rynku (Evidently)")
    if skip_drift_report:
        metrics = load_drift_metrics()
        if not metrics:
            metrics = compute_drift_report()
    else:
        metrics = compute_drift_report()

    log(metrics.get("message", ""))

    audit: dict[str, Any] = {
        "started_at": started_at,
        "drift_metrics": {
            "drift_alert": metrics.get("drift_alert"),
            "share_drifted_columns": metrics.get("share_drifted_columns"),
            "status": metrics.get("status"),
            "salary_drift_detected": metrics.get("salary_drift_detected"),
            "report_url": metrics.get("report_url"),
        },
        "simulation_was_active": simulation_is_active(),
        "retrained": False,
    }

    if not should_retrain(metrics, cfg, manual=manual, force=force):
        reason = "no_drift"
        if metrics.get("status") == "insufficient_data":
            reason = "insufficient_data"
        elif not metrics.get("drift_alert"):
            reason = "no_drift"
        elif not manual and not cfg.get("auto_retrain_enabled"):
            reason = "auto_retrain_disabled"
        audit["skipped_reason"] = reason
        audit["finished_at"] = datetime.now(timezone.utc).isoformat()
        audit["message"] = (
            "Retrening pominiety — brak alertu driftu lub wylaczona automatyzacja."
            if reason != "insufficient_data"
            else metrics.get("message", "Za malo danych do oceny driftu.")
        )
        _write_audit(audit)
        return audit

    mode = str(cfg.get("retrain_mode", "fast")).lower()
    fast = mode != "full"
    progress(30, f"Retrening ({'szybki' if fast else 'pelny z tuningiem'})")
    log(f"Uruchamiam retrening: retrain_mode={mode}")

    from src.portal.operations import run_train

    train_result = run_train(fast=fast)

    if simulation_is_active():
        clear_drift_simulation()
        log("Symulacja driftu wylaczona po retreningu.")

    progress(95, "Aktualizacja raportu driftu po retreningu")
    post_metrics = compute_drift_report()

    audit.update(
        {
            "retrained": True,
            "retrain_mode": mode,
            "train_result": {
                "best_run_id": train_result.get("best_run_id"),
                "metrics": train_result.get("metrics"),
                "combinations_tested": train_result.get("combinations_tested"),
            },
            "post_retrain_drift_alert": post_metrics.get("drift_alert"),
            "message": (
                f"Retrening zakonczony (run_id={train_result.get('best_run_id')}). "
                "Baseline zaktualizowany. Model gotowy do przeładowania w API."
            ),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_audit(audit)
    progress(100, "Retrening po drift zakonczony")
    return audit
