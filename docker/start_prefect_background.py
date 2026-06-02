"""Uruchamia serwer Prefect UI w tle (Docker entrypoint)."""

from __future__ import annotations

import os
import subprocess
import sys

host = os.environ.get("PREFECT_HOST", "0.0.0.0")
port = os.environ.get("PREFECT_PORT", "4200")
api_url = os.environ.get("PREFECT_API_URL", f"http://127.0.0.1:{port}/api")

os.environ["PREFECT_API_URL"] = api_url
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED", "false")

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
