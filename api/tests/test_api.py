"""Testy API /health i /predict."""

from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True


def test_predict_returns_salary(client, sample_payload):
    r = client.post("/predict", json=sample_payload)
    assert r.status_code == 200
    body = r.json()
    assert "predicted_salary" in body
    assert body["currency"] == "USD"
    assert 50_000 < body["predicted_salary"] < 300_000


def test_predict_validation_error(client):
    r = client.post("/predict", json={"job_title": "X"})
    assert r.status_code == 422


def test_openapi_docs(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/predict" in r.json()["paths"]
