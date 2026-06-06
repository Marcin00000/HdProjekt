"""Fixtures pytest — API z zaladowanym modelem lub mockiem."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.predictor import predictor
from src.portal.model_artifacts import models_ready


@pytest.fixture(scope="session")
def sample_payload() -> dict:
    return {
        "job_title": "Data Scientist",
        "experience_years": 5,
        "education_level": "Master",
        "skills_count": 10,
        "industry": "Technology",
        "company_size": "Medium",
        "location": "USA",
        "remote_work": "Yes",
        "certifications": 2,
    }


@pytest.fixture(scope="session")
def client():
    models_ok = models_ready()
    if not models_ok:
        os.environ["API_SKIP_MODEL_LOAD"] = "1"
        predictor._preprocessor = MagicMock()
        predictor._model = MagicMock()
        predictor._model.predict.return_value = [145000.0]
        predictor.predict = lambda req: (145000.0, None)
        predictor._preprocessor.transform.return_value = [[0.0]]
        from api.app import app
    else:
        os.environ.pop("API_SKIP_MODEL_LOAD", None)
        from api.app import app

    with TestClient(app) as c:
        yield c

    if not models_ok:
        predictor._preprocessor = None
        predictor._model = None
