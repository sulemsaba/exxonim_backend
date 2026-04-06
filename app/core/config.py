from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

load_dotenv(ENV_FILE)

LOCAL_ENVIRONMENTS = {"local", "development", "dev"}
PRODUCTION_LIKE_ENVIRONMENTS = {"staging", "production"}
DEFAULT_LOCAL_MEDIA_ROOT = ROOT_DIR / "uploads"
DEFAULT_LOCAL_DOCUMENTS_ROOT = ROOT_DIR / "protected-documents"
LOCALHOST_MARKERS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    APP_ENV: str = "local"
    DATABASE_URL: str = (
        "postgresql+asyncpg://app_user:strongpassword@127.0.0.1:5433/"
        "Exxonim"
    )
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_DOMAIN: str = ""
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    ACCESS_COOKIE_NAME: str = "exxonim_access_token"
    REFRESH_COOKIE_NAME: str = "exxonim_refresh_token"
    CSRF_COOKIE_NAME: str = "exxonim_csrf_token"
    CONSENT_COOKIE_NAME: str = "exxonim_consent"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3039,http://127.0.0.1:3039"
    PUBLIC_SITE_URL: str = "http://127.0.0.1:5173"
    ADMIN_SITE_URL: str = "http://127.0.0.1:3039"
    MEDIA_ROOT: str = ""
    DOCUMENTS_ROOT: str = ""
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    MAX_UPLOAD_IMAGE_DIMENSION: int = 6000
    MAX_DOCUMENT_SIZE_BYTES: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = LOCAL_ENVIRONMENTS | PRODUCTION_LIKE_ENVIRONMENTS
        if normalized not in allowed:
            raise ValueError(
                f"APP_ENV must be one of: {', '.join(sorted(allowed))}."
            )
        return normalized

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none.")
        return normalized

    @property
    def is_local(self) -> bool:
        return self.APP_ENV in LOCAL_ENVIRONMENTS

    @property
    def is_production_like(self) -> bool:
        return self.APP_ENV in PRODUCTION_LIKE_ENVIRONMENTS

    @property
    def cors_origins(self) -> list[str]:
        return [
            item.strip()
            for item in self.CORS_ORIGINS.split(",")
            if item.strip()
        ]

    @property
    def cors_allow_methods(self) -> list[str]:
        return ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    @property
    def cors_allow_headers(self) -> list[str]:
        return ["Content-Type", "X-CSRF-Token", "Authorization"]

    @property
    def media_root_path(self) -> Path:
        if self.MEDIA_ROOT.strip():
            return Path(self.MEDIA_ROOT).expanduser().resolve()
        return DEFAULT_LOCAL_MEDIA_ROOT.resolve()

    @property
    def documents_root_path(self) -> Path:
        if self.DOCUMENTS_ROOT.strip():
            return Path(self.DOCUMENTS_ROOT).expanduser().resolve()
        if self.MEDIA_ROOT.strip():
            return self.media_root_path.parent / "protected-documents"
        return DEFAULT_LOCAL_DOCUMENTS_ROOT.resolve()

    def model_post_init(self, __context: object) -> None:
        self._validate_runtime_safety()

    def _validate_runtime_safety(self) -> None:
        if not self.DATABASE_URL.strip():
            raise ValueError("DATABASE_URL must be configured.")

        if self.is_local:
            return

        if self.JWT_SECRET.strip() == "change-this-secret" or len(self.JWT_SECRET.strip()) < 32:
            raise ValueError(
                "JWT_SECRET must be set to a strong value with at least 32 characters "
                "outside local development."
            )

        if not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true outside local development.")

        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")

        if not self.MEDIA_ROOT.strip():
            raise ValueError("MEDIA_ROOT must be configured outside local development.")

        if not self.DOCUMENTS_ROOT.strip():
            raise ValueError("DOCUMENTS_ROOT must be configured outside local development.")

        if not self.PUBLIC_SITE_URL.strip():
            raise ValueError("PUBLIC_SITE_URL must be configured outside local development.")

        if not self.ADMIN_SITE_URL.strip():
            raise ValueError("ADMIN_SITE_URL must be configured outside local development.")

        origins = self.cors_origins
        if not origins:
            raise ValueError("CORS_ORIGINS must define at least one explicit origin.")

        if any(origin == "*" for origin in origins):
            raise ValueError("Wildcard CORS origins are not allowed outside local development.")

        for origin in origins:
            if any(marker in origin for marker in LOCALHOST_MARKERS):
                raise ValueError(
                    "Localhost CORS origins are not allowed outside local development."
                )


settings = Settings()
