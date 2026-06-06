"""Etap DVC: train — uruchamiany przez `dvc repro train`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dvc.pipeline_stages import run_train  # noqa: E402
from src.train.train_model import load_params  # noqa: E402


def main() -> int:
    bundle = run_train(load_params())
    print(json.dumps(bundle["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
