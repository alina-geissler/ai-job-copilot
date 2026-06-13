"""E2E tests for the health-check endpoint."""

from __future__ import annotations


def test_health_check_returns_200(client):
    """GET /health must return HTTP 200 with status=ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
