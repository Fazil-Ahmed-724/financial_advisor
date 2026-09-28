import uuid
from datetime import timedelta

import jwt
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import load_settings
from app.main import app

client = TestClient(app)
PASSWORD = "correct horse battery staple"


def register(email: str = "person@example.com"):
    return client.post("/auth/register", json={"email": email, "password": PASSWORD})


def test_registration_and_authenticated_access():
    response = register()
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "person@example.com"
    assert "password" not in str(body).lower()
    assert body["token"]["token_type"] == "bearer"
    assert body["token"]["expires_in"] == 900

    protected = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['token']['access_token']}"},
    )
    assert protected.status_code == 200
    assert protected.json()["id"] == body["user"]["id"]


def test_duplicate_email_is_rejected_case_insensitively():
    assert register("duplicate@example.com").status_code == 201
    response = register("DUPLICATE@example.com")
    assert response.status_code == 409


def test_login_success_and_invalid_password():
    registration = register("login@example.com")
    assert registration.status_code == 201

    success = client.post(
        "/auth/login", json={"email": "LOGIN@example.com", "password": PASSWORD}
    )
    assert success.status_code == 200
    assert success.json()["token_type"] == "bearer"

    failure = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "incorrect-password"},
    )
    assert failure.status_code == 401
    assert failure.json()["detail"] == "Invalid email or password"


def test_unauthenticated_access_is_rejected():
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_expired_token_is_rejected():
    registration = register("expired@example.com").json()
    expired = create_access_token(
        uuid.UUID(registration["user"]["id"]), expires_delta=timedelta(seconds=-1)
    )
    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


def test_invalid_signature_is_rejected():
    registration = register("signature@example.com").json()
    token = jwt.encode(
        {
            "sub": registration["user"]["id"],
            "type": "access",
            "iat": 1,
            "exp": 4_102_444_800,
        },
        "a_different_secret_that_is_long_enough_1234567890",
        algorithm="HS256",
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_for_missing_user_is_rejected():
    token = create_access_token(uuid.uuid4())
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_access_token_contains_short_lived_expiry():
    registration = register("claims@example.com").json()
    token = registration["token"]["access_token"]
    payload = jwt.decode(token, load_settings().auth_secret, algorithms=["HS256"])
    assert payload["type"] == "access"
    assert 0 < payload["exp"] - payload["iat"] <= 15 * 60
