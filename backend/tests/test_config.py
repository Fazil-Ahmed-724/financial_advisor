import pytest

from app.config import load_settings


def test_production_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="at least 32"):
        load_settings()


def test_production_rejects_known_local_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "AUTH_SECRET",
        "local_dev_auth_secret_change_me_64_chars_minimum_1234567890abcdef",
    )
    with pytest.raises(RuntimeError, match="unique and secure"):
        load_settings()
