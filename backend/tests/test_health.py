from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app.database import check_database
from app.main import app

client = TestClient(app)


def test_liveness_does_not_require_database():
    with patch("app.main.check_database") as check:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    check.assert_not_called()


def test_readiness_queries_real_postgresql():
    # Integration check: must run with the Compose PostgreSQL service.
    check_database()
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_readiness_failure_does_not_leak_secrets():
    with patch(
        "app.main.check_database",
        side_effect=psycopg.OperationalError("password=do-not-expose"),
    ):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert "do-not-expose" not in response.text
