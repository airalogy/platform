import pytest
from pydantic import ValidationError

from app.config import Settings


def settings(**overrides):
    values = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
        "SECRET_KEY": "development-secret",
        "AES_KEY": "1" * 64,
        "AIRALOGY_ENDPOINT": "http://localhost:4000",
        "REDIS_URL": "redis://localhost:6379/0",
        "INNER_API_KEY": "development-inner-key",
        "MINIO_ENDPOINT": "localhost:9200",
        "MINIO_BUCKET": "airalogy",
        "MINIO_ACCESS_KEY": "airalogy-test",
        "MINIO_SECRET_KEY": "m" * 32,
    }
    values.update(overrides)
    return Settings(**values)


def test_single_lab_defaults_to_invite_only_signup():
    value = settings(DEPLOYMENT_MODE="single_lab")

    assert value.is_single_lab is True
    assert value.effective_signup_mode == "invite_only"


def test_community_defaults_to_open_signup():
    value = settings(DEPLOYMENT_MODE="community")

    assert value.is_single_lab is False
    assert value.effective_signup_mode == "open"


def test_structure_mode_defaults_follow_deployment_profile():
    assert settings(DEPLOYMENT_MODE="community").effective_lab_structure_mode == "flat"
    assert (
        settings(DEPLOYMENT_MODE="single_lab").effective_lab_structure_mode
        == "structured"
    )
    assert (
        settings(
            DEPLOYMENT_MODE="single_lab", LAB_STRUCTURE_MODE="flat"
        ).effective_lab_structure_mode
        == "flat"
    )


def test_explicit_signup_mode_overrides_profile_default():
    value = settings(DEPLOYMENT_MODE="single_lab", SIGNUP_MODE="disabled")

    assert value.effective_signup_mode == "disabled"


def test_gpt_model_is_disabled_by_default():
    assert settings().ENABLE_GPT_MODEL is False


def test_gpt_model_requires_an_openai_or_external_provider():
    with pytest.raises(ValidationError, match="ENABLE_GPT_MODEL"):
        settings(ENABLE_GPT_MODEL=True)

    assert settings(
        ENABLE_GPT_MODEL=True,
        OPENAI_API_KEY="test-openai-key",
    ).ENABLE_GPT_MODEL is True
    assert settings(
        ENABLE_GPT_MODEL=True,
        MASTERBRAIN_CALL_MODE="external",
        CHAT_API_ENDPOINT="https://chat.example.org",
    ).ENABLE_GPT_MODEL is True


def test_single_lab_uid_must_be_stable_route_identifier():
    with pytest.raises(ValidationError, match="SINGLE_LAB_UID"):
        settings(DEPLOYMENT_MODE="single_lab", SINGLE_LAB_UID="Invalid Lab")


def test_single_lab_default_project_uid_must_be_stable_route_identifier():
    with pytest.raises(ValidationError, match="SINGLE_LAB_DEFAULT_PROJECT_UID"):
        settings(
            DEPLOYMENT_MODE="single_lab",
            SINGLE_LAB_DEFAULT_PROJECT_UID="Invalid Project",
        )


@pytest.mark.parametrize("field", ["LOG_MAX_BYTES", "LOG_BACKUP_COUNT"])
def test_log_rotation_limits_must_be_positive(field):
    with pytest.raises(ValidationError, match=field):
        settings(**{field: 0})


def test_production_rejects_example_secrets():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        settings(
            APP_ENV="production",
            SECRET_KEY="change-me-community-secret-key",
            INNER_API_KEY="x" * 32,
        )


def test_production_single_lab_requires_initial_admin_token():
    with pytest.raises(ValidationError, match="INITIAL_ADMIN_TOKEN"):
        settings(
            APP_ENV="production",
            DEPLOYMENT_MODE="single_lab",
            SECRET_KEY="s" * 32,
            INNER_API_KEY="i" * 32,
        )


def test_production_single_lab_accepts_generated_secrets():
    value = settings(
        APP_ENV="production",
        DEPLOYMENT_MODE="single_lab",
        SECRET_KEY="s" * 32,
        INNER_API_KEY="i" * 32,
        INITIAL_ADMIN_TOKEN="b" * 32,
    )

    assert value.is_single_lab is True


def test_production_rejects_example_minio_secret():
    with pytest.raises(ValidationError, match="MINIO_SECRET_KEY"):
        settings(
            APP_ENV="production",
            SECRET_KEY="s" * 32,
            INNER_API_KEY="i" * 32,
            MINIO_SECRET_KEY="airalogy-minio-password",
        )
