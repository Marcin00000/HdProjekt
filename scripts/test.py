#!/usr/bin/env python3
"""Uruchamianie testow automatycznych projektu."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUITES: dict[str, list[str]] = {
    "api": ["api/tests/test_api.py"],
    "portal": ["api/tests/test_portal.py", "api/tests/test_operations_api.py"],
    "monitoring": [
        "api/tests/test_drift_simulate.py",
        "api/tests/test_drift_retrain.py",
    ],
    "train": ["api/tests/test_train_fast.py", "api/tests/test_model_artifacts.py"],
    "integration": [
        "api/tests/test_api.py",
        "api/tests/test_portal.py",
        "api/tests/test_drift_simulate.py",
        "api/tests/test_drift_retrain.py",
        "api/tests/test_train_fast.py",
        "api/tests/test_onboarding.py",
    ],
    "all": ["api/tests"],
}

SMOKE_COMMANDS = [
    [sys.executable, str(ROOT / "scripts" / "install.py"), "--help"],
    [sys.executable, str(ROOT / "scripts" / "verify.py"), "--help"],
    [sys.executable, str(ROOT / "scripts" / "run.py"), "--help"],
    [sys.executable, str(ROOT / "scripts" / "test.py"), "--help"],
]


def run_smoke() -> int:
    print("=== Smoke: --help skryptow ===")
    for cmd in SMOKE_COMMANDS:
        print("+", " ".join(cmd))
        code = subprocess.call(cmd, cwd=ROOT)
        if code != 0:
            return code
    print("=== Smoke: subkomendy run.py ===")
    for sub in (
        "prepare",
        "load-dwh",
        "etl",
        "train",
        "dvc",
        "app",
        "mlflow-ui",
        "drift-simulate",
        "drift-retrain",
    ):
        cmd = [sys.executable, str(ROOT / "scripts" / "run.py"), sub, "--help"]
        print("+", " ".join(cmd))
        code = subprocess.call(cmd, cwd=ROOT)
        if code != 0:
            return code
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Testy projektu")
    parser.add_argument(
        "--suite",
        choices=(*SUITES.keys(),),
        default="all",
        help="Zestaw testow (domyslnie: all)",
    )
    parser.add_argument("--smoke", action="store_true", help="Tylko smoke test CLI")
    parser.add_argument("-v", "--verbose", action="store_true", default=True)
    args = parser.parse_args()

    if args.smoke:
        return run_smoke()

    targets = SUITES[args.suite]
    cmd = [sys.executable, "-m", "pytest", *targets, "-v", "--tb=short"]
    print("=== pytest ===")
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
