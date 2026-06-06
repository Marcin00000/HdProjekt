"""Testy sciezki onboarding — swiezy projekt bez modelu."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


def _load_verify():
    path = ROOT / "scripts" / "verify.py"
    spec = importlib.util.spec_from_file_location("verify_script", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_script"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


verify_script = _load_verify()


def test_check_mlflow_client_fresh_project_not_strict():
    mock_client = MagicMock()
    mock_client.get_experiment_by_name.return_value = None
    with patch("mlflow.tracking.MlflowClient", return_value=mock_client), patch(
        "src.mlflow_config.configure_mlflow", return_value="sqlite:///x"
    ):
        assert verify_script.check_mlflow_client(strict=False) is True


def test_check_mlflow_client_fresh_project_strict():
    mock_client = MagicMock()
    mock_client.get_experiment_by_name.return_value = None
    with patch("mlflow.tracking.MlflowClient", return_value=mock_client), patch(
        "src.mlflow_config.configure_mlflow", return_value="sqlite:///x"
    ):
        assert verify_script.check_mlflow_client(strict=True) is False


def test_check_data_sources_without_models():
    with patch("src.config.find_local_raw_csv", return_value=None), patch(
        "src.portal.model_artifacts.models_ready", return_value=False
    ):
        assert verify_script.check_data_sources() is True


def test_find_local_raw_csv_fallback_input(tmp_path, monkeypatch):
    from src.config import find_local_raw_csv

    monkeypatch.setenv("LOCAL_RAW_DATA_PATH", "job_salary_prediction_dataset.csv")
    with patch("src.config.PROJECT_ROOT", tmp_path):
        csv = tmp_path / "input" / "job_salary_prediction_dataset.csv"
        csv.parent.mkdir(parents=True)
        csv.write_text("a\n1", encoding="utf-8")
        found = find_local_raw_csv()
        assert found == csv


def test_app_starts_without_models_message(capsys):
    run_path = ROOT / "scripts" / "run.py"
    spec = importlib.util.spec_from_file_location("run_script", run_path)
    run_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(run_mod)

    args = type("Args", (), {"docker": False, "host": "127.0.0.1", "port": 8765, "reload": False})()
    missing = Path("/nonexistent/xgboost_model.joblib")
    with patch.object(run_mod, "MODELS", [missing]), patch.object(
        run_mod.subprocess, "call", return_value=0
    ) as mock_call:
        code = run_mod.cmd_app(args)
    assert code == 0
    mock_call.assert_called_once()
    assert "brak modeli" in capsys.readouterr().out.lower()
