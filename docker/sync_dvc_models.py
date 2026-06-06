"""Przy starcie kontenera: pobierz brakujace lub uszkodzone modele z remote DVC."""

from __future__ import annotations

import sys
from pathlib import Path

# Import po ustawieniu PYTHONPATH w entrypoint (/app w Dockerze)
if "/app" not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROJECT_ROOT
from src.portal.model_artifacts import MODEL_ARTIFACTS, invalid_model_paths, joblib_looks_valid


def _remove_invalid(paths: list[Path]) -> None:
    for path in paths:
        if path.is_file() and not joblib_looks_valid(path):
            print(f"Uszkodzony artefakt — usuwam: {path.relative_to(PROJECT_ROOT)}")
            path.unlink(missing_ok=True)


def main() -> int:
    bad = invalid_model_paths()
    if not bad:
        print("Modele DVC: preprocessor i xgboost poprawne na dysku.")
        return 0

    _remove_invalid([p for p in MODEL_ARTIFACTS if p.is_file()])

    dvc_config = PROJECT_ROOT / ".dvc" / "config"
    if not dvc_config.is_file():
        print(
            "Brak poprawnych modeli i .dvc/config — pomijam dvc pull "
            "(uruchom trening lub zamontuj models/)."
        )
        return 0

    still_bad = invalid_model_paths()
    if not still_bad:
        return 0

    print(f"Brak lub uszkodzone modele ({len(still_bad)}) — probuje dvc pull z remote...")
    try:
        from src.portal.dvc_runtime import ensure_dvc_runtime

        ensure_dvc_runtime()
    except Exception as exc:
        print(f"Konfiguracja DVC: {exc}")
        return 0

    import subprocess

    targets = ["models/preprocessor.joblib", "models/xgboost_model.joblib"]
    proc = subprocess.run(
        [sys.executable, "-m", "dvc", "pull", "-f", *targets],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        print(out.strip()[-2000:])

    if invalid_model_paths():
        print(
            "Uwaga: nadal brak poprawnych modeli — uruchom trening (train_fast) "
            "lub sprawdz remote DVC / .env Azure."
        )
        return 0

    print("Modele pobrane z DVC remote i zweryfikowane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
