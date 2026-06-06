"""Przygotowanie DVC w Dockerze (bez Git) i wysylka na remote Azure."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from src.config import PROJECT_ROOT, local_raw_data_path

DVC_DIR = PROJECT_ROOT / ".dvc"
DVC_CONFIG = DVC_DIR / "config"
REMOTE_NAME = "azure_remote"
SILVER_PATH = PROJECT_ROOT / "data" / "processed" / "cleaned.parquet"

PIPELINE_OUTS = (
    "data/processed/cleaned.parquet",
    "data/processed/predictions.csv",
    "data/processed/training_summary.json",
    "data/processed/metrics.json",
    "models/preprocessor.joblib",
    "models/xgboost_model.joblib",
)


def _run_dvc(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dvc", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def _config_text() -> str:
    if not DVC_CONFIG.is_file():
        return ""
    return DVC_CONFIG.read_text(encoding="utf-8")


def ensure_no_scm() -> None:
    if not DVC_CONFIG.is_file():
        raise RuntimeError("Brak pliku .dvc/config w projekcie.")

    text = _config_text()
    if re.search(r"^\s*no_scm\s*=", text, re.MULTILINE):
        return

    if "[core]" in text:
        text = re.sub(
            r"(\[core\][^\[]*)",
            r"\1    no_scm = true\n",
            text,
            count=1,
        )
    else:
        text = "[core]\n    no_scm = true\n" + text

    DVC_CONFIG.write_text(text, encoding="utf-8")
    _run_dvc(["config", "core.no_scm", "true"], check=False)


def sync_azure_remote_credentials() -> None:
    try:
        from src.config import AzureStorageConfig

        cfg = AzureStorageConfig()
    except ValueError:
        return

    for key, value in (
        ("account_name", cfg.account_name),
        ("account_key", cfg.account_key),
    ):
        _run_dvc(
            ["remote", "modify", REMOTE_NAME, key, value, "--local"],
            check=False,
        )


def ensure_dvc_runtime() -> None:
    ensure_no_scm()
    sync_azure_remote_credentials()
    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")


def _existing_outs() -> list[str]:
    return [p for p in PIPELINE_OUTS if (PROJECT_ROOT / p).is_file()]


def _has_train_outputs() -> bool:
    return (PROJECT_ROOT / "models/xgboost_model.joblib").is_file()


def _log_dvc(proc: subprocess.CompletedProcess[str], log) -> None:
    combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if combined:
        log(combined[-1500:])


def sync_pipeline_to_dvc_cache() -> None:
    """
    Zaktualizuj cache DVC przed push.
    W Dockerze czesto brak CSV — pomijamy commit prepare, commitujemy tylko train.
    """
    from src.portal.job_context import log

    outs = _existing_outs()
    if not outs:
        return

    if local_raw_data_path().is_file():
        proc = _run_dvc(["commit", "prepare", "-f"], check=False)
        _log_dvc(proc, log)
        if proc.returncode != 0:
            log("Uwaga: commit etapu prepare nieudany (kontynuuje z train).")
    elif SILVER_PATH.is_file():
        log("Brak CSV raw w kontenerze — pomijam commit etapu prepare.")

    if SILVER_PATH.is_file() and _has_train_outputs():
        proc = _run_dvc(["commit", "train", "-f"], check=False)
        _log_dvc(proc, log)
    elif SILVER_PATH.is_file():
        log("Silver dostepny, brak modelu — push tylko warstwy silver.")


def _push_targets() -> list[str]:
    """Cele push: etap pipeline lub konkretne pliki wyjsciowe."""
    if _has_train_outputs():
        return ["train"]
    if SILVER_PATH.is_file():
        return ["data/processed/cleaned.parquet"]
    return _existing_outs()


def run_dvc_push(*, sync_cache: bool = True) -> str:
    ensure_dvc_runtime()

    if not _existing_outs():
        raise RuntimeError(
            "Brak artefaktow do wyslania. Uruchom najpierw reprodukcje pipeline DVC "
            "(lub trening), aby powstaly pliki w data/processed/ i models/."
        )

    if sync_cache:
        sync_pipeline_to_dvc_cache()

    targets = _push_targets()
    from src.portal.job_context import log

    log(f"Wysylka DVC na remote '{REMOTE_NAME}': {', '.join(targets)}")

    proc = _run_dvc(["push", "-r", REMOTE_NAME, *targets], check=False)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(out[-2000:].strip() or "Wysylka DVC (push) nie powiodla sie")
    return out
