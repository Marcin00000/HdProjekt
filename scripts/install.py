#!/usr/bin/env python3
"""Instalacja zaleznosci projektu."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 11)


def main() -> int:
    parser = argparse.ArgumentParser(description="Instalacja zaleznosci Python")
    parser.add_argument(
        "--dvc-init",
        action="store_true",
        help="Inicjalizuj repozytorium DVC (.dvc/), jesli brak",
    )
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        print(
            f"Wymagany Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+, "
            f"obecny: {sys.version_info.major}.{sys.version_info.minor}"
        )
        return 1

    req = ROOT / "requirements.txt"
    if not req.is_file():
        print(f"Brak pliku: {req}")
        return 1

    print("=== Instalacja pakietow ===")
    code = subprocess.call(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        cwd=ROOT,
    )
    if code != 0:
        return code

    if args.dvc_init and not (ROOT / ".dvc").is_dir():
        print("\n=== Inicjalizacja DVC ===")
        code = subprocess.call([sys.executable, "-m", "dvc", "init"], cwd=ROOT)
        if code != 0:
            return code

    env_example = ROOT / ".env.example"
    env_file = ROOT / ".env"
    if env_example.is_file() and not env_file.is_file():
        print("\nUwaga: skopiuj .env.example do .env i uzupelnij zmienne Azure.")

    print("\nInstalacja zakonczona.")
    print("Nastepnie: python scripts/verify.py --all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
