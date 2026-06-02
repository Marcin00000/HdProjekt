"""Uruchamia MLflow UI w tle (Docker entrypoint)."""

from __future__ import annotations

import os
import subprocess

from src.mlflow_config import configure_mlflow, mlflow_ui_command

configure_mlflow()
port = int(os.environ.get("MLFLOW_PORT", "5000"))
host = os.environ.get("MLFLOW_HOST", "0.0.0.0")
subprocess.Popen(mlflow_ui_command(port=port, host=host))
