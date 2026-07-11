import pytest
from pydantic import ValidationError

from app.routers.login import SignUpParams


def _signup_params(**overrides):
    data = {
        "username": "community_user",
        "name": "Community User",
        "email": "user@example.org",
        "password": "password123",
        "confirm_password": "password123",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def test_signup_params_allow_email_password_without_phone():
    params = SignUpParams(**_signup_params())

    assert params.has_phone_verification is False
    assert params.country_code is None
    assert params.phone is None
    assert params.verify_code is None
    assert params.confirm_password == "password123"


def test_signup_params_accept_legacy_confirm_password_typo():
    params = SignUpParams(
        **_signup_params(
            confirm_password=None,
            comfirm_password="password123",
        )
    )

    assert params.confirm_password == "password123"


def test_signup_params_accept_frontend_camel_case_fields():
    params = SignUpParams(
        **_signup_params(
            name=None,
            displayName="Community User",
            confirm_password=None,
            confirmPassword="password123",
        )
    )

    assert params.name == "Community User"
    assert params.confirm_password == "password123"


def test_signup_params_accept_common_email_characters():
    params = SignUpParams(**_signup_params(email="user-name+dev@example.org"))

    assert str(params.email) == "user-name+dev@example.org"


def test_signup_params_accept_complete_phone_verification():
    params = SignUpParams(
        **_signup_params(
            country_code="86",
            phone="13800138000",
            verify_code="123456",
        )
    )

    assert params.has_phone_verification is True


def test_signup_params_accept_frontend_invite_token_alias():
    params = SignUpParams(**_signup_params(inviteToken="invite-token"))

    assert params.invite_token == "invite-token"


def test_signup_params_reject_partial_phone_verification():
    with pytest.raises(ValidationError):
        SignUpParams(**_signup_params(country_code="86", phone="13800138000"))
