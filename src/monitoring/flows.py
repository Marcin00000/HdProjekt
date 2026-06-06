"""Prefect — monitoring driftu i retrening."""

from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger


@flow(name="monitor_and_retrain", log_prints=True)
def monitor_and_retrain(force: bool = False) -> dict[str, Any]:
    """
    Harmonogram: po ETL sprawdz drift (baseline vs silver) i opcjonalnie retrenuj.
    Retrening tylko gdy ``monitoring.auto_retrain_enabled: true`` w params.yaml.
    """
    logger = get_run_logger()
    from src.monitoring.drift_retrain import check_drift_and_retrain

    logger.info("monitor_and_retrain start (force=%s)", force)
    result = check_drift_and_retrain(manual=False, force=force)
    logger.info(
        "retrained=%s reason=%s",
        result.get("retrained"),
        result.get("skipped_reason", "ok"),
    )
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Prefect: monitor drift + retrain")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Deployment z cronem (niedziela 04:30, po ETL)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wymus retrening gdy drift wykryty (ignoruj auto_retrain przy jednorazowym run)",
    )
    args = parser.parse_args()

    if args.serve:
        monitor_and_retrain.serve(
            name="weekly-monitor-retrain",
            cron="30 4 * * 0",
            tags=["hd-projekt", "monitoring", "retrain"],
            parameters={"force": False},
        )
    else:
        monitor_and_retrain(force=args.force)


if __name__ == "__main__":
    main()
