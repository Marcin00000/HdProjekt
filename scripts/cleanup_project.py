"""
Usuwa zbedne / stare pliki MLflow i artefakty poza data/mlflow/.

Uzycie:
    python scripts/cleanup_project.py
    python scripts/cleanup_project.py --mlflow-reset   # + reset_mlflow.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LEGACY_PATHS = [
    ROOT / "mlflow.db",
    ROOT / "mlflow.db-wal",
    ROOT / "mlflow.db-shm",
    ROOT / "mlruns",
    ROOT / "mlartifacts",
    ROOT / "_mlflow_legacy_registry",
]


def _remove(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except OSError:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mlflow-reset",
        action="store_true",
        help="Po czyszczeniu uruchom scripts/reset_mlflow.py",
    )
    args = parser.parse_args()

    print("=== Czyszczenie projektu ===")
    removed: list[str] = []
    skipped: list[str] = []

    for path in LEGACY_PATHS:
        if _remove(path):
            removed.append(path.relative_to(ROOT).as_posix())
        elif path.exists():
            skipped.append(path.relative_to(ROOT).as_posix())

    for pattern in ("mlruns", "mlartifacts"):
        p = ROOT / pattern
        if p.exists() and not any(p.iterdir()):
            p.rmdir()
            removed.append(f"{pattern}/ (pusty)")

    if removed:
        print("Usunieto:")
        for item in removed:
            print(f"  - {item}")
    else:
        print("Brak starych sciezek MLflow w katalogu glownym.")

    if skipped:
        print("\nZablokowane (zatrzymaj MLflow UI, potem usun recznie lub uruchom ponownie):")
        for item in skipped:
            print(f"  - {item}")

    print("\nAktywny MLflow: data/mlflow/ (nie usuwany)")

    if args.mlflow_reset:
        print("\n=== Reset MLflow (data/mlflow) ===")
        return subprocess.call(
            [sys.executable, str(ROOT / "scripts" / "reset_mlflow.py")],
            cwd=ROOT,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
