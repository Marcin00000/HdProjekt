#!/usr/bin/env python3
"""CLI — symulacja driftu + opcjonalny raport Evidently."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.monitoring.drift_simulate import SCENARIOS, simulate_drift
from src.monitoring.evidently_report import compute_drift_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Symulacja zmiany rynku (silver_current_simulated.parquet)"
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS),
        default="location_shift",
        help="Scenariusz przesuniecia rozkladu",
    )
    parser.add_argument("--count", type=int, default=5000, help="Probka wierszy z cleaned.parquet")
    parser.add_argument("--no-report", action="store_true", help="Pomin generowanie raportu Evidently")
    args = parser.parse_args()

    sim = simulate_drift(args.scenario, args.count)
    print(f"Symulacja: {sim['rows_written']} wierszy -> {sim['log_path']}")

    if not args.no_report:
        report = compute_drift_report()
        print(report.get("message", report.get("status", "")))
        if report.get("report_html"):
            print(f"Raport: {report['report_html']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
