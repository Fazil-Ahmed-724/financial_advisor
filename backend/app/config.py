import os
from dataclasses import dataclass


INSECURE_PRODUCTION_SECRETS = {
    "local_dev_auth_secret_change_me_64_chars_minimum_1234567890abcdef",
    "test_auth_secret_which_is_long_enough_1234567890abcdef",
}


@dataclass(frozen=True)
class Settings:
    app_env: str
    auth_secret: str
    access_token_minutes: int
    debug: bool
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    require_https: bool


def _bool(name: str, default: str = "false") -> bool:
    value = os.environ.get(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return value == "true"


def _csv(name: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())


def load_settings() -> Settings:
    app_env = os.environ.get("APP_ENV", "production").strip().lower()
    auth_secret = os.environ.get("AUTH_SECRET", "")
    if len(auth_secret) < 32:
        raise RuntimeError("AUTH_SECRET must contain at least 32 characters")
    if app_env == "production" and auth_secret in INSECURE_PRODUCTION_SECRETS:
        raise RuntimeError("AUTH_SECRET must be unique and secure in production")

    try:
        access_token_minutes = int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))
    except ValueError as error:
        raise RuntimeError("ACCESS_TOKEN_MINUTES must be an integer") from error
    if not 1 <= access_token_minutes <= 60:
        raise RuntimeError("ACCESS_TOKEN_MINUTES must be between 1 and 60")

    debug = _bool("APP_DEBUG")
    allowed_hosts = _csv("ALLOWED_HOSTS")
    allowed_origins = _csv("ALLOWED_ORIGINS")
    require_https = _bool("REQUIRE_HTTPS")
    if app_env == "production":
        if debug:
            raise RuntimeError("APP_DEBUG must be false in production")
        if not allowed_hosts or "*" in allowed_hosts:
            raise RuntimeError("ALLOWED_HOSTS must be explicit in production")
        if "*" in allowed_origins or any(not x.startswith("https://") for x in allowed_origins):
            raise RuntimeError("ALLOWED_ORIGINS must contain only HTTPS origins in production")
        if not require_https:
            raise RuntimeError("REQUIRE_HTTPS must be true in production")

    return Settings(
        app_env=app_env,
        auth_secret=auth_secret,
        access_token_minutes=access_token_minutes,
        debug=debug,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
        require_https=require_https,
    )
