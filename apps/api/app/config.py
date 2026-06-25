import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    STORAGE_BACKEND: str = "minio"  # options: "minio" or "oss"

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


class ProdSettings(Settings):
    APP_ENV: str = "production"


config = (
    ProdSettings()
    if os.getenv("APP_ENV", "development") == "production"
    else Settings()
)
