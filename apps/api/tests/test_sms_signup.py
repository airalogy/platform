import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.config import config
from app.routers import login as login_router
from app.services import signup_verification


def enable_sms_signup(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
    monkeypatch.setattr(config, "SMS_SIGNUP_REQUIRED", True)
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


def test_signup_verification_token_is_opaque_hashed_and_single_use(monkeypatch):
    stored = {}

    async def fake_set_cache(key, value, ttl):
        stored[key] = value
        assert ttl == signup_verification.SIGNUP_VERIFICATION_TTL_SECONDS

    async def fake_get_cache(key):
        return stored.get(key)

    async def fake_pop_cache(key):
        return stored.pop(key, None)

    monkeypatch.setattr(signup_verification, "set_cache", fake_set_cache)
    monkeypatch.setattr(signup_verification, "get_cache", fake_get_cache)
    monkeypatch.setattr(signup_verification, "pop_cache", fake_pop_cache)

    token = asyncio.run(signup_verification.issue_signup_verification("86", "13800138000"))
    cache_key = next(iter(stored))

    assert token not in cache_key
    assert cache_key.startswith(signup_verification.SIGNUP_VERIFICATION_CACHE_PREFIX)
    assert asyncio.run(signup_verification.get_signup_verification(token)) == {
        "country_code": "86",
        "phone": "13800138000",
    }
    assert asyncio.run(signup_verification.consume_signup_verification(token)) == {
        "country_code": "86",
        "phone": "13800138000",
    }
    assert asyncio.run(signup_verification.consume_signup_verification(token)) is None


def test_disabled_sms_signup_rejects_code_request_before_sending(monkeypatch):
    monkeypatch.setattr(config, "SMS_SIGNUP_REQUIRED", False)
    send_code = AsyncMock()
    monkeypatch.setattr(login_router, "send_sms_verify_code", send_code)
    params = login_router.SendVerifyCodeParams(
        type="signup",
        country_code="86",
        phone="13800138000",
    )

    with pytest.raises(HTTPException, match="SMS signup verification is disabled") as error:
        asyncio.run(login_router.send_phone_verify_code(AsyncMock(), params))

    assert error.value.status_code == 503
    send_code.assert_not_awaited()


def test_disabled_sms_signup_rejects_phone_verification(monkeypatch):
    monkeypatch.setattr(config, "SMS_SIGNUP_REQUIRED", False)
    verify_code = AsyncMock()
    monkeypatch.setattr(login_router, "check_sms_verify_code", verify_code)
    params = login_router.VerifySignupPhoneParams(
        country_code="86",
        phone="13800138000",
        verify_code="123456",
    )

    with pytest.raises(HTTPException, match="SMS signup verification is disabled"):
        asyncio.run(login_router.verify_signup_phone(params, AsyncMock()))

    verify_code.assert_not_awaited()


def test_signup_code_request_does_not_reveal_existing_phone(monkeypatch):
    enable_sms_signup(monkeypatch)
    find_user = AsyncMock()
    send_code = AsyncMock()
    monkeypatch.setattr(login_router.User, "find_by", find_user)
    monkeypatch.setattr(login_router, "send_sms_verify_code", send_code)
    params = login_router.SendVerifyCodeParams(
        type="signup",
        country_code="86",
        phone="13800138000",
    )

    result = asyncio.run(login_router.send_phone_verify_code(AsyncMock(), params))

    assert result == {"success": True}
    find_user.assert_not_awaited()
    send_code.assert_awaited_once_with("8613800138000", "signup")


def test_phone_must_be_verified_before_signup_token_is_issued(monkeypatch):
    enable_sms_signup(monkeypatch)
    verify_code = AsyncMock()
    issue_token = AsyncMock(return_value="s" * 43)
    monkeypatch.setattr(login_router, "check_sms_verify_code", verify_code)
    monkeypatch.setattr(login_router.User, "exists", AsyncMock(return_value=False))
    monkeypatch.setattr(login_router, "issue_signup_verification", issue_token)
    params = login_router.VerifySignupPhoneParams(
        country_code="86",
        phone="13800138000",
        verify_code="123456",
    )

    result = asyncio.run(login_router.verify_signup_phone(params, AsyncMock()))

    verify_code.assert_awaited_once_with("8613800138000", "123456", "signup")
    issue_token.assert_awaited_once_with("86", "13800138000")
    assert result == {
        "signup_verification_token": "s" * 43,
        "expires_in": signup_verification.SIGNUP_VERIFICATION_TTL_SECONDS,
    }


def test_existing_phone_is_reported_only_after_valid_code(monkeypatch):
    enable_sms_signup(monkeypatch)
    verification_finished = False

    async def verify_code(*_args):
        nonlocal verification_finished
        verification_finished = True

    async def phone_exists(*_args):
        assert verification_finished is True
        return True

    monkeypatch.setattr(login_router, "check_sms_verify_code", verify_code)
    monkeypatch.setattr(login_router.User, "exists", phone_exists)
    monkeypatch.setattr(login_router, "issue_signup_verification", AsyncMock())
    params = login_router.VerifySignupPhoneParams(
        country_code="86",
        phone="13800138000",
        verify_code="123456",
    )

    with pytest.raises(HTTPException, match="Phone number already exists"):
        asyncio.run(login_router.verify_signup_phone(params, AsyncMock()))


def test_required_phone_signup_rejects_missing_or_expired_token(monkeypatch):
    enable_sms_signup(monkeypatch)
    params = login_router.SignUpParams(
        username="community_user",
        name="Community User",
        email="user@example.org",
        password="password123",
        confirm_password="password123",
    )
    db_session = SimpleNamespace()

    with pytest.raises(HTTPException, match="Phone verification is required") as missing:
        asyncio.run(login_router.signup(params, db_session))
    assert missing.value.status_code == 403

    params.signup_verification_token = "s" * 43
    monkeypatch.setattr(
        login_router,
        "get_signup_verification",
        AsyncMock(return_value=None),
    )
    with pytest.raises(HTTPException, match="invalid or expired") as expired:
        asyncio.run(login_router.signup(params, db_session))
    assert expired.value.status_code == 400


def test_required_phone_signup_consumes_token_and_uses_bound_phone(monkeypatch):
    enable_sms_signup(monkeypatch)
    verified_phone = {"country_code": "86", "phone": "13800138000"}
    get_verification = AsyncMock(return_value=verified_phone)
    consume_verification = AsyncMock(return_value=verified_phone)
    monkeypatch.setattr(login_router, "get_signup_verification", get_verification)
    monkeypatch.setattr(login_router, "consume_signup_verification", consume_verification)
    monkeypatch.setattr(
        login_router.User,
        "exists",
        AsyncMock(side_effect=[False, False, False]),
    )
    monkeypatch.setattr(login_router.Lab, "exists", AsyncMock(return_value=False))
    monkeypatch.setattr(login_router, "create_access_token", lambda _user: "access-token")
    check_code = AsyncMock()
    monkeypatch.setattr(login_router, "check_sms_verify_code", check_code)
    db_session = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    params = login_router.SignUpParams(
        username="community_user",
        name="Community User",
        email="user@example.org",
        password="password123",
        confirm_password="password123",
        signup_verification_token="s" * 43,
    )

    result = asyncio.run(login_router.signup(params, db_session))

    get_verification.assert_awaited_once_with("s" * 43)
    consume_verification.assert_awaited_once_with("s" * 43)
    check_code.assert_not_awaited()
    created_user = result["user"]
    assert created_user.country_code == "86"
    assert created_user.phone == "13800138000"
    assert result["token"] == "access-token"
    db_session.commit.assert_awaited_once()


def test_disabled_sms_signup_keeps_email_registration(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
    monkeypatch.setattr(config, "SMS_SIGNUP_REQUIRED", False)
    monkeypatch.setattr(
        login_router.User,
        "exists",
        AsyncMock(side_effect=[False, False]),
    )
    monkeypatch.setattr(login_router.Lab, "exists", AsyncMock(return_value=False))
    monkeypatch.setattr(login_router, "create_access_token", lambda _user: "access-token")
    get_verification = AsyncMock()
    consume_verification = AsyncMock()
    monkeypatch.setattr(login_router, "get_signup_verification", get_verification)
    monkeypatch.setattr(login_router, "consume_signup_verification", consume_verification)
    db_session = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    params = login_router.SignUpParams(
        username="community_user",
        name="Community User",
        email="user@example.org",
        password="password123",
        confirm_password="password123",
    )

    result = asyncio.run(login_router.signup(params, db_session))

    get_verification.assert_not_awaited()
    consume_verification.assert_not_awaited()
    assert result["user"].country_code == ""
    assert result["user"].phone == ""
    assert result["token"] == "access-token"
