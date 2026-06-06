"""Walidacja artefaktow modelu."""

from __future__ import annotations

from pathlib import Path

from src.portal.model_artifacts import joblib_looks_valid


def test_joblib_looks_valid_rejects_tiny_file(tmp_path: Path):
    bad = tmp_path / "broken.joblib"
    bad.write_bytes(b"x")
    assert joblib_looks_valid(bad) is False
