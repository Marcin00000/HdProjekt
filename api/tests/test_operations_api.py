"""Testy API operacji i dashboardu."""

from __future__ import annotations


def test_dashboard_api(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "source" in body
    assert "by_location" in body


def test_system_status(client):
    r = client.get("/api/system/status")
    assert r.status_code == 200
    assert "paths" in r.json()
    assert "available_jobs" in r.json()


def test_create_job_unknown(client):
    r = client.post("/api/jobs", json={"job_type": "invalid_xyz"})
    assert r.status_code == 400
