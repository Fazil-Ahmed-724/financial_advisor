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


def test_production_requires_hardened_transport_and_hosts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET", "unique-production-secret-which-is-long-enough-123456")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.test")
    monkeypatch.setenv("REQUIRE_HTTPS", "false")
    with pytest.raises(RuntimeError, match="REQUIRE_HTTPS"):
        load_settings()
    monkeypatch.setenv("REQUIRE_HTTPS", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://example.test")
    with pytest.raises(RuntimeError, match="HTTPS origins"):
        load_settings()


def test_production_hardened_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET", "unique-production-secret-which-is-long-enough-123456")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.test")
    monkeypatch.setenv("REQUIRE_HTTPS", "true")
    settings=load_settings()
    assert settings.allowed_hosts == ("api.example.test",) and settings.require_https
