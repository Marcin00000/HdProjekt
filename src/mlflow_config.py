"""Konfiguracja MLflow — SQLite (metadane) + mlartifacts/ (pliki)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from src.config import PROJECT_ROOT

MLFLOW_DIR = PROJECT_ROOT / "data" / "mlflow"
MLFLOW_DB = MLFLOW_DIR / "mlflow.db"
MLARTIFACTS_DIR = MLFLOW_DIR / "artifacts"
# MLflow 3.x czasem tworzy podfolder przy logowaniu modeli
MLRUNS_DIR = PROJECT_ROOT / "mlruns"

EXPERIMENT_NAME = "job_salary_prediction"
REGISTERED_MODEL_NAME = "JobSalaryPredictor"


def canonical_sqlite_uri() -> str:
    return f"sqlite:///{MLFLOW_DB.resolve().as_posix()}"


DEFAULT_URI = canonical_sqlite_uri()


def experiment_artifact_uri() -> str:
    path = (MLARTIFACTS_DIR / EXPERIMENT_NAME).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path.as_uri()


def get_artifact_root_uri() -> str:
    MLARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return MLARTIFACTS_DIR.resolve().as_uri()


def normalize_tracking_uri(uri: str | None = None) -> str:
    raw = (uri or os.getenv("MLFLOW_TRACKING_URI") or "").strip()
    if not raw:
        return DEFAULT_URI
    lower = raw.lower()
    if lower.startswith("file:") or lower in ("./mlruns", "mlruns"):
        return DEFAULT_URI
    if lower.startswith("sqlite:"):
        return DEFAULT_URI
    return raw


def get_tracking_uri() -> str:
    return normalize_tracking_uri()


def ensure_experiment(name: str = EXPERIMENT_NAME) -> str:
    """Tworzy eksperyment z artefaktami w mlartifacts/ (nie w mlruns/)."""
    import mlflow
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    exp = client.get_experiment_by_name(name)
    if exp is None:
        exp_id = client.create_experiment(name, artifact_location=experiment_artifact_uri())
        return exp_id
    return exp.experiment_id


def configure_mlflow() -> str:
    uri = get_tracking_uri()
    artifact_root = get_artifact_root_uri()
    os.environ["MLFLOW_TRACKING_URI"] = uri
    os.environ["MLFLOW_REGISTRY_URI"] = uri
    os.environ["MLFLOW_DEFAULT_ARTIFACT_ROOT"] = artifact_root
    import mlflow

    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    return uri


def reset_mlflow_data() -> list[str]:
    """Usuwa lokalne dane MLflow i modele treningowe. Zwraca liste usunietych elementow."""
    removed: list[str] = []
    failed: list[str] = []
    targets = [
        MLFLOW_DIR,
        PROJECT_ROOT / "mlflow.db",
        PROJECT_ROOT / "mlflow.db-wal",
        PROJECT_ROOT / "mlflow.db-shm",
        PROJECT_ROOT / "mlartifacts",
        MLRUNS_DIR,
        PROJECT_ROOT / "_mlflow_legacy_registry",
        PROJECT_ROOT / "models",
        PROJECT_ROOT / "data" / "processed" / "phase4_metrics.json",
    ]
    for path in targets:
        if not path.exists():
            continue
        label = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(label)
        except OSError as exc:
            failed.append(f"{label} ({exc})")
    if failed:
        print("Nie usunieto (zatrzymaj MLflow UI: Ctrl+C):")
        for item in failed:
            print(f"  - {item}")
    return removed


def mlflow_ui_command(port: int = 5000) -> list[str]:
    import sys

    configure_mlflow()
    uri = get_tracking_uri()
    return [
        sys.executable,
        "-m",
        "mlflow",
        "ui",
        "--port",
        str(port),
        "--backend-store-uri",
        uri,
        "--registry-store-uri",
        uri,
        "--default-artifact-root",
        get_artifact_root_uri(),
        "--serve-artifacts",
    ]
