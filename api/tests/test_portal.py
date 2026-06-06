"""Testy tras HTML portalu."""

from __future__ import annotations


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Job Salary" in r.text
    assert "/dashboard" in r.text


def test_dashboard_page(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "chartLocation" in r.text


def test_predict_page(client):
    r = client.get("/predict")
    assert r.status_code == 200
    assert "predict/form" in r.text


def test_docs_pages(client):
    for path in ("/docs/training", "/docs/dvc", "/docs/etl"):
        r = client.get(path)
        assert r.status_code == 200


def test_mlflow_redirect(client):
    r = client.get("/mlflow", follow_redirects=False)
    assert r.status_code == 302
    assert "5000" in r.headers.get("location", "")
