import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import config
from app.routers import instance as instance_router
from app.routers import login as login_router


def disable_sms_login(monkeypatch):
    monkeypatch.setattr(config, "SMS_LOGIN_ENABLED", False)


def enable_sms_login_provider(monkeypatch):
    monkeypatch.setattr(config, "SMS_LOGIN_ENABLED", None)
    monkeypatch.setattr(config, "ALIBABA_CLOUD_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setattr(config, "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setattr(config, "ALIBABA_CLOUD_SMS_SIGN_NAME", "Airalogy")
    monkeypatch.setattr(
        config,
        "ALIBABA_CLOUD_SMS_VERIFY_CODE_TEMPLATE_CODE",
        "SMS_123456",
    )
    monkeypatch.setattr(config, "ALIBABA_CLOUD_SMS_SENDER_ID", "")
    monkeypatch.setattr(config, "SMS_COUNTRY_CODE_ALLOWLIST", "86")


def enable_sms_signup_provider(monkeypatch):
    enable_sms_login_provider(monkeypatch)
    monkeypatch.setattr(config, "SMS_SIGNUP_REQUIRED", True)


def test_instance_status_reports_effective_sms_login_capability(monkeypatch):
    enable_sms_login_provider(monkeypatch)
    monkeypatch.setattr(instance_router, "get_single_lab", AsyncMock(return_value=None))

    status = asyncio.run(instance_router.get_instance_status(AsyncMock()))

    assert status.sms_login_enabled is True
    assert status.sms_signup_required is True


def test_disabled_sms_signin_returns_503_before_code_verification(monkeypatch):
    disable_sms_login(monkeypatch)
    verify_code = AsyncMock()
    monkeypatch.setattr(login_router, "check_sms_verify_code", verify_code)
    params = login_router.SignInParams(
        country_code="86",
        phone="13800138000",
        verify_code="123456",
    )

    with pytest.raises(HTTPException, match="SMS login is disabled") as error:
        asyncio.run(login_router.login(params, AsyncMock()))

    assert error.value.status_code == 503
    verify_code.assert_not_awaited()


def test_disabled_signin_code_request_returns_503_before_user_lookup(monkeypatch):
    disable_sms_login(monkeypatch)
    find_user = AsyncMock()
    monkeypatch.setattr(login_router.User, "find_by", find_user)
    params = login_router.SendVerifyCodeParams(
        type="signin",
        country_code="86",
        phone="13800138000",
    )

    with pytest.raises(HTTPException, match="SMS login is disabled") as error:
        asyncio.run(login_router.send_phone_verify_code(AsyncMock(), params))

    assert error.value.status_code == 503
    find_user.assert_not_awaited()


def test_disabled_sms_login_does_not_affect_email_password_login(monkeypatch):
    disable_sms_login(monkeypatch)
    user = SimpleNamespace(id="user-id", verify_password=lambda password: True)
    monkeypatch.setattr(login_router.User, "find_by", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login_router,
        "get_auth_version",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(login_router, "create_access_token", lambda *_args: "token")
    params = login_router.SignInByEmailParams(
        email="user@example.org",
        password="password123",
    )

    result = asyncio.run(login_router.signin_by_email(params, AsyncMock()))

    assert result == {"token": "token", "user": user}


@pytest.mark.parametrize(
    ("code_type", "existing_user"),
    [
        ("signup", None),
        ("reset_password", SimpleNamespace(id="user-id")),
        ("change_phone", None),
    ],
)
def test_disabled_sms_login_does_not_block_other_code_types(
    monkeypatch,
    code_type,
    existing_user,
):
    disable_sms_login(monkeypatch)
    if code_type == "signup":
        enable_sms_signup_provider(monkeypatch)
        disable_sms_login(monkeypatch)
    else:
        monkeypatch.setattr(config, "SMS_COUNTRY_CODE_ALLOWLIST", "86")
    monkeypatch.setattr(
        login_router.User,
        "find_by",
        AsyncMock(return_value=existing_user),
    )
    send_code = AsyncMock()
    monkeypatch.setattr(login_router, "send_sms_verify_code", send_code)
    params = login_router.SendVerifyCodeParams(
        type=code_type,
        country_code="86",
        phone="13800138000",
    )

    result = asyncio.run(login_router.send_phone_verify_code(AsyncMock(), params))

    assert result == {"success": True}
    send_code.assert_awaited_once_with("8613800138000", code_type)
