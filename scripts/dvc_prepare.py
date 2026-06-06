"""Etap DVC: prepare — uruchamiany przez `dvc repro prepare`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dvc.pipeline_stages import run_prepare  # noqa: E402
from src.train.train_model import load_params  # noqa: E402


def main() -> int:
    summary = run_prepare(load_params())
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
