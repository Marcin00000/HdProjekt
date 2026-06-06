"""
Calkowity reset lokalnego MLflow + modeli.

Uzycie:
    python scripts/reset_mlflow.py
    python scripts/reset_mlflow.py --train   # potem od razu trening (--no-tune)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.mlflow_config import (  # noqa: E402
    EXPERIMENT_NAME,
    REGISTERED_MODEL_NAME,
    configure_mlflow,
    ensure_experiment,
    reset_mlflow_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset MLflow i opcjonalnie ponowny trening")
    parser.add_argument(
        "--train",
        action="store_true",
        help="Po resecie uruchom scripts/run.py train --no-tune",
    )
    args = parser.parse_args()

    print("=== Reset MLflow ===")
    removed = reset_mlflow_data()
    if removed:
        for item in removed:
            print(f"  usunieto: {item}")
    else:
        print("  (brak plikow do usuniecia)")

    configure_mlflow()
    exp_id = ensure_experiment()
    print(f"\nNowy eksperyment: {EXPERIMENT_NAME} (id={exp_id})")
    print(f"Tracking URI: {configure_mlflow()}")
    print("\nNastepnie:")
    print("  python scripts/run.py train")
    print("  python scripts/run.py train --no-tune")
    print("  python scripts/run.py mlflow-ui")

    if not args.train:
        return 0

    print("\n=== Trening (--no-tune) ===")
    return subprocess.call(
        [sys.executable, str(ROOT / "scripts" / "run.py"), "train", "--no-tune"],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
