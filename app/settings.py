from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "Network King"
    environment: str = "development"
    secret_key: str = "development-secret-key-change-me"
    database_url: str = "sqlite:///./network_king.db"
    app_base_url: str = "http://localhost:8000"
    session_cookie_secure: bool = False
    storage_backend: str = "local"
    local_media_root: Path = BASE_DIR / "var" / "uploads"
    gcs_bucket_name: str = ""
    seed_admin_login: str = ""
    seed_admin_password: str = ""
    seed_admin_name: str = "Admin"

    @property
    def is_development(self) -> bool:
        return self.environment != "production"


def load_settings() -> Settings:
    return Settings(
        environment=os.getenv("APP_ENV", "development"),
        secret_key=os.getenv("SECRET_KEY", "development-secret-key-change-me"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./network_king.db"),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
        session_cookie_secure=_get_bool("SESSION_COOKIE_SECURE", False),
        storage_backend=os.getenv("STORAGE_BACKEND", "local"),
        local_media_root=Path(os.getenv("LOCAL_MEDIA_ROOT", str(BASE_DIR / "var" / "uploads"))),
        gcs_bucket_name=os.getenv("GCS_BUCKET_NAME", ""),
        seed_admin_login=os.getenv("SEED_ADMIN_LOGIN", ""),
        seed_admin_password=os.getenv("SEED_ADMIN_PASSWORD", ""),
        seed_admin_name=os.getenv("SEED_ADMIN_NAME", "Admin"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

