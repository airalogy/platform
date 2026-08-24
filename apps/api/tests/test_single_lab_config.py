from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
        "AI_ENABLED": None,
        "DASHSCOPE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ENABLE_GPT_MODEL": False,
        "MASTERBRAIN_CALL_MODE": "package",
        "CHAT_API_ENDPOINT": "",
        "SMS_LOGIN_ENABLED": None,
        "SMS_SIGNUP_REQUIRED": None,
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "",
        "ALIBABA_CLOUD_SMS_SIGN_NAME": "",
        "ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE": "",
        "ALIBABA_CLOUD_SMS_SENDER_ID": "",
        "SMS_COUNTRY_CODE_ALLOWLIST": "",
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


def test_community_defaults_to_same_origin_documentation():
    value = settings(DEPLOYMENT_MODE="community")

    assert value.effective_documentation_profile == "community"
    assert value.effective_documentation_url == "/docs/"


def test_single_lab_defaults_to_customer_managed_documentation():
    value = settings(DEPLOYMENT_MODE="single_lab")

    assert value.effective_documentation_profile == "customer_managed"
    assert value.effective_documentation_url == "/docs/"


def test_explicit_vendor_managed_documentation_overrides_deployment_default():
    value = settings(
        DEPLOYMENT_MODE="single_lab",
        DOCUMENTATION_PROFILE="vendor_managed",
        DOCUMENTATION_URL="https://docs.example.org/platform/",
        SUPPORT_URL="https://support.example.org/",
    )

    assert value.effective_documentation_profile == "vendor_managed"
    assert value.effective_documentation_url == "https://docs.example.org/platform/"
    assert value.SUPPORT_URL == "https://support.example.org/"


def test_gpt_model_is_disabled_by_default():
    assert settings().ENABLE_GPT_MODEL is False


def test_ai_capability_is_auto_detected_and_can_be_disabled():
    assert settings().effective_ai_enabled is False
    assert settings(DASHSCOPE_API_KEY="test-key").effective_ai_enabled is True
    assert (
        settings(AI_ENABLED=False, DASHSCOPE_API_KEY="test-key").effective_ai_enabled
        is False
    )


def test_explicit_ai_enable_requires_a_provider():
    with pytest.raises(ValidationError, match="AI_ENABLED"):
        settings(AI_ENABLED=True)


def test_sms_login_auto_detection_is_disabled_without_provider_config():
    value = settings()

    assert value.sms_provider_configured is False
    assert value.effective_sms_login_enabled is False


def test_sms_login_auto_detection_accepts_complete_china_config():
    value = settings(
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Airalogy",
        ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE="SMS_123456",
        SMS_COUNTRY_CODE_ALLOWLIST="86",
    )

    assert value.sms_provider_configured is True
    assert value.effective_sms_login_enabled is True


def test_sms_login_auto_detection_accepts_complete_international_config():
    value = settings(
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SENDER_ID="Airalogy",
        SMS_COUNTRY_CODE_ALLOWLIST="1,44",
    )

    assert value.sms_provider_configured is True
    assert value.effective_sms_login_enabled is True


def test_explicit_sms_login_disable_overrides_complete_provider_config():
    value = settings(
        SMS_LOGIN_ENABLED=False,
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Airalogy",
        ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE="SMS_123456",
        SMS_COUNTRY_CODE_ALLOWLIST="86",
    )

    assert value.sms_provider_configured is True
    assert value.effective_sms_login_enabled is False


def test_explicit_sms_login_enable_requires_complete_provider_config():
    with pytest.raises(
        ValidationError,
        match=r"SMS_LOGIN_ENABLED=true.*ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    ):
        settings(
            SMS_LOGIN_ENABLED=True,
            ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
            SMS_COUNTRY_CODE_ALLOWLIST="86",
        )


def test_sms_signup_requirement_auto_detects_provider_for_community():
    assert settings(DEPLOYMENT_MODE="community").effective_sms_signup_required is False

    value = settings(
        DEPLOYMENT_MODE="community",
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Airalogy",
        ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE="SMS_123456",
        SMS_COUNTRY_CODE_ALLOWLIST="86",
    )

    assert value.effective_sms_signup_required is True


def test_single_lab_does_not_require_sms_signup_by_default():
    value = settings(
        DEPLOYMENT_MODE="single_lab",
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Airalogy",
        ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE="SMS_123456",
        SMS_COUNTRY_CODE_ALLOWLIST="86",
    )

    assert value.sms_provider_configured is True
    assert value.effective_sms_signup_required is False


def test_explicit_sms_signup_requirement_overrides_profile_default():
    provider = {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-access-key",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-secret",
        "ALIBABA_CLOUD_SMS_SIGN_NAME": "Airalogy",
        "ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE": "SMS_123456",
        "SMS_COUNTRY_CODE_ALLOWLIST": "86",
    }

    assert settings(
        DEPLOYMENT_MODE="single_lab",
        SMS_SIGNUP_REQUIRED=True,
        **provider,
    ).effective_sms_signup_required is True
    assert settings(
        DEPLOYMENT_MODE="community",
        SMS_SIGNUP_REQUIRED=False,
        **provider,
    ).effective_sms_signup_required is False


def test_explicit_sms_signup_requirement_needs_complete_provider_config():
    with pytest.raises(
        ValidationError,
        match=r"SMS_SIGNUP_REQUIRED=true.*ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    ):
        settings(
            SMS_SIGNUP_REQUIRED=True,
            ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
            SMS_COUNTRY_CODE_ALLOWLIST="86",
        )


def test_mixed_sms_regions_require_china_and_international_fields():
    with pytest.raises(ValidationError) as error:
        settings(
            SMS_LOGIN_ENABLED=True,
            ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
            ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
            SMS_COUNTRY_CODE_ALLOWLIST="86,1",
        )

    message = str(error.value)
    assert "ALIBABA_CLOUD_SMS_SIGN_NAME" in message
    assert "ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE" in message
    assert "ALIBABA_CLOUD_SMS_SENDER_ID" in message

    value = settings(
        SMS_LOGIN_ENABLED=True,
        ALIBABA_CLOUD_ACCESS_KEY_ID="test-access-key",
        ALIBABA_CLOUD_ACCESS_KEY_SECRET="test-secret",
        ALIBABA_CLOUD_SMS_SIGN_NAME="Airalogy",
        ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE="SMS_123456",
        ALIBABA_CLOUD_SMS_SENDER_ID="Airalogy",
        SMS_COUNTRY_CODE_ALLOWLIST="86,1",
    )
    assert value.effective_sms_login_enabled is True


def test_single_lab_generated_config_disables_sms_login_by_default():
    env_example = (
        REPOSITORY_ROOT / "deploy/single-lab/.env.example"
    ).read_text(encoding="utf-8")
    generator = (
        REPOSITORY_ROOT / "deploy/single-lab/scripts/generate-env.sh"
    ).read_text(encoding="utf-8")

    assert "\nSMS_LOGIN_ENABLED=false\n" in env_example
    assert "\nSMS_LOGIN_ENABLED=false\n" in generator
    assert "\nSMS_SIGNUP_REQUIRED=false\n" in env_example
    assert "\nSMS_SIGNUP_REQUIRED=false\n" in generator


def test_engine_image_uses_official_multiarch_immutable_release():
    assert Settings.model_fields["AIRALOGY_ENGINE_IMAGE"].default == (
        "ghcr.io/airalogy/airalogy-engine:0.16.0@"
        "sha256:5d26af0a28fc42f042cf079ac6e00b1a4435ff2d1fd02631c5d356bfdd0e08b7"
    )


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


def test_deployment_id_is_opaque_and_contains_no_customer_label():
    value = settings(AIRALOGY_DEPLOYMENT_ID="dep_0123456789abcdef0123456789abcdef")
    assert value.AIRALOGY_DEPLOYMENT_ID.startswith("dep_")

    with pytest.raises(ValidationError, match="AIRALOGY_DEPLOYMENT_ID"):
        settings(AIRALOGY_DEPLOYMENT_ID="customer-lab-production")


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
