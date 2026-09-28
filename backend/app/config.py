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

    return Settings(
        app_env=app_env,
        auth_secret=auth_secret,
        access_token_minutes=access_token_minutes,
    )
