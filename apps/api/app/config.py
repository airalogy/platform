import os
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str
    SECRET_KEY: str
    AES_KEY: str
    AIRALOGY_ENDPOINT: str
    API_ROOT_PATH: str = ""
    PROTOCOL_DIR: str = f"{os.getcwd()}/protocols"
    REDIS_URL: str
    PROTOCOL_RUN_ENV: str = "local"
    # Record delete safety buffer (days). Non-admins cannot delete records older than this.
    RECORD_DELETE_GRACE_DAYS: int = 7
    # Lab creation limit per user. Set to 0 or a negative value to disable the limit.
    MAX_LABS_PER_USER: int = 3

    # Deployment profile. `single_lab` keeps the shared domain model while
    # changing instance bootstrap, account admission, and navigation defaults.
    DEPLOYMENT_MODE: Literal["community", "single_lab"] = "community"
    SIGNUP_MODE: Literal["open", "invite_only", "disabled"] | None = None
    SITE_URL: str = "http://localhost"
    SINGLE_LAB_UID: str = "main"
    SINGLE_LAB_NAME: str = "Airalogy Lab"
    SINGLE_LAB_DESCRIPTION: str = ""
    SINGLE_LAB_DEFAULT_PROJECT_UID: str = "lab_protocols"
    SINGLE_LAB_DEFAULT_PROJECT_NAME: str = "Lab Protocols"
    INITIAL_ADMIN_TOKEN: str = ""
    INVITATION_TTL_HOURS: int = 168
    PASSWORD_RESET_TTL_MINUTES: int = 60

    # Request bodies can contain passwords and unpublished research records.
    # Keep body logging disabled even in development unless debugging locally.
    LOG_REQUEST_BODIES: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    SQL_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        "WARNING"
    )
    LOG_FILE: str = "log/app.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # Chat config
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    # Masterbrain runs in-process through the installed `masterbrain` package by
    # default. The old external service path is deprecated and should only be
    # enabled as a compatibility escape hatch.
    MASTERBRAIN_CALL_MODE: str = "package"
    CHAT_API_ENDPOINT: str = ""
    CHAT_MODEL_FAST: str = "qwen3.5-flash"
    CHAT_MODEL_ACCURATE: str = "qwen3.5-plus"
    CHAT_MODEL_DEEP: str = "qwen-max"

    AIRALOGY_ENGINE_IMAGE: str = "numbcoder/airalogy-engine:latest"
    AIRALOGY_ENGINE_DEBUG: bool = False
    AIRALOGY_ENGINE_BOXLITE_HOME: str | None = None

    # Storage config
    STORAGE_BACKEND: Literal["minio", "oss"] = "minio"

    # Minio config
    MINIO_ENDPOINT: str = ""
    MINIO_BUCKET: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_PROXY_PATH: str = ""

    # Aliyun OSS config
    OSS_REGION: str = "cn-hangzhou"
    OSS_ENDPOINT: str = ""
    OSS_BUCKET: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""

    # Alibaba Cloud SMS config
    ALIBABA_CLOUD_ACCESS_KEY_ID: str = ""
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = ""
    ALIBABA_CLOUD_SMS_SIGN_NAME: str = ""
    ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE: str = ""
    ALIBABA_CLOUD_SMS_SENDER_ID: str = ""
    SMS_COUNTRY_CODE_ALLOWLIST: str = ""

    @property
    def sms_country_code_allowlist(self) -> set[str]:
        return {
            country_code.strip().removeprefix("+")
            for country_code in self.SMS_COUNTRY_CODE_ALLOWLIST.split(",")
            if country_code.strip()
        }

    # inner api key
    INNER_API_KEY: str = ""

    @property
    def is_single_lab(self) -> bool:
        return self.DEPLOYMENT_MODE == "single_lab"

    @property
    def effective_signup_mode(self) -> Literal["open", "invite_only", "disabled"]:
        if self.SIGNUP_MODE is not None:
            return self.SIGNUP_MODE
        return "invite_only" if self.is_single_lab else "open"

    @model_validator(mode="after")
    def validate_deployment_settings(self) -> "Settings":
        uid_pattern = re.compile(r"^[a-z][a-z0-9_]{2,31}$")
        if self.is_single_lab and not uid_pattern.fullmatch(self.SINGLE_LAB_UID):
            raise ValueError(
                "SINGLE_LAB_UID must start with a letter and contain 3-32 "
                "lowercase letters, numbers, or underscores"
            )
        if self.is_single_lab and not uid_pattern.fullmatch(
            self.SINGLE_LAB_DEFAULT_PROJECT_UID
        ):
            raise ValueError(
                "SINGLE_LAB_DEFAULT_PROJECT_UID must start with a letter and "
                "contain 3-32 lowercase letters, numbers, or underscores"
            )
        if self.is_single_lab and not self.SINGLE_LAB_NAME.strip():
            raise ValueError("SINGLE_LAB_NAME must not be empty")

        if self.INVITATION_TTL_HOURS <= 0:
            raise ValueError("INVITATION_TTL_HOURS must be positive")
        if self.PASSWORD_RESET_TTL_MINUTES <= 0:
            raise ValueError("PASSWORD_RESET_TTL_MINUTES must be positive")
        if self.LOG_MAX_BYTES <= 0:
            raise ValueError("LOG_MAX_BYTES must be positive")
        if self.LOG_BACKUP_COUNT <= 0:
            raise ValueError("LOG_BACKUP_COUNT must be positive")

        parsed_site_url = urlparse(self.SITE_URL)
        if parsed_site_url.scheme not in {"http", "https"} or not parsed_site_url.netloc:
            raise ValueError("SITE_URL must be an absolute HTTP(S) origin")

        if self.APP_ENV == "production":
            insecure_values = {
                "change-me-community-secret-key",
                "change-me-inner-api-key",
                "airalogy",
                "airalogy-minio-password",
            }
            if len(self.SECRET_KEY) < 32 or self.SECRET_KEY in insecure_values:
                raise ValueError(
                    "SECRET_KEY must be a non-default value with at least 32 characters"
                )
            if not re.fullmatch(r"[0-9a-fA-F]{64}", self.AES_KEY):
                raise ValueError("AES_KEY must be a 64-character hexadecimal AES-256 key")
            if set(self.AES_KEY) == {"0"}:
                raise ValueError("AES_KEY must not use the example all-zero value")
            if len(self.INNER_API_KEY) < 32 or self.INNER_API_KEY in insecure_values:
                raise ValueError(
                    "INNER_API_KEY must be a non-default value with at least 32 characters"
                )
            if "airalogy:airalogy@" in self.DATABASE_URL:
                raise ValueError("DATABASE_URL must not use the example database password")
            if self.STORAGE_BACKEND == "minio":
                if not self.MINIO_ENDPOINT or not self.MINIO_BUCKET:
                    raise ValueError("MinIO endpoint and bucket are required")
                if len(self.MINIO_ACCESS_KEY) < 8:
                    raise ValueError("MINIO_ACCESS_KEY must contain at least 8 characters")
                if (
                    len(self.MINIO_SECRET_KEY) < 16
                    or self.MINIO_SECRET_KEY in insecure_values
                ):
                    raise ValueError(
                        "MINIO_SECRET_KEY must be a non-default value with at least 16 characters"
                    )
            elif self.STORAGE_BACKEND == "oss":
                if not all(
                    [
                        self.OSS_ENDPOINT,
                        self.OSS_BUCKET,
                        self.OSS_ACCESS_KEY_ID,
                        self.OSS_ACCESS_KEY_SECRET,
                    ]
                ):
                    raise ValueError("OSS storage settings are incomplete")
            if self.is_single_lab and (
                len(self.INITIAL_ADMIN_TOKEN) < 32
                or self.INITIAL_ADMIN_TOKEN in insecure_values
            ):
                raise ValueError(
                    "INITIAL_ADMIN_TOKEN must be a non-default value with at least "
                    "32 characters in production single-Lab deployments"
                )
            if (
                parsed_site_url.scheme != "https"
                and parsed_site_url.hostname not in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("SITE_URL must use HTTPS for non-local production hosts")
        return self


class ProdSettings(Settings):
    APP_ENV: str = "production"


config = (
    ProdSettings()
    if os.getenv("APP_ENV", "development") == "production"
    else Settings()
)
