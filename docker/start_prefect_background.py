"""Uruchamia serwer Prefect UI w tle (Docker entrypoint)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

host = os.environ.get("PREFECT_HOST", "0.0.0.0")
port = os.environ.get("PREFECT_PORT", "4200")
api_url = os.environ.get("PREFECT_API_URL", f"http://127.0.0.1:{port}/api")
prefect_home = os.environ.get("PREFECT_HOME", "/app/data/prefect")

os.environ["PREFECT_API_URL"] = api_url
os.environ["PREFECT_HOME"] = prefect_home
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")

Path(prefect_home).mkdir(parents=True, exist_ok=True)

subprocess.Popen(
    [
        sys.executable,
        "-m",
        "prefect",
        "server",
        "start",
        "--host",
        host,
        "--port",
        port,
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
