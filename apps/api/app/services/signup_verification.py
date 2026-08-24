import hashlib
import secrets
from typing import TypedDict

from app.libs.redis import get_cache, pop_cache, set_cache


SIGNUP_VERIFICATION_TTL_SECONDS = 30 * 60
SIGNUP_VERIFICATION_CACHE_PREFIX = "signup_verification:"


class SignupVerificationData(TypedDict):
    country_code: str
    phone: str


def signup_verification_cache_key(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{SIGNUP_VERIFICATION_CACHE_PREFIX}{token_hash}"


async def issue_signup_verification(country_code: str, phone: str) -> str:
    token = secrets.token_urlsafe(32)
    await set_cache(
        signup_verification_cache_key(token),
        {"country_code": country_code, "phone": phone},
        SIGNUP_VERIFICATION_TTL_SECONDS,
    )
    return token


async def get_signup_verification(token: str) -> SignupVerificationData | None:
    value = await get_cache(signup_verification_cache_key(token))
    if not isinstance(value, dict):
        return None
    country_code = value.get("country_code")
    phone = value.get("phone")
    if not isinstance(country_code, str) or not isinstance(phone, str):
        return None
    return {"country_code": country_code, "phone": phone}


async def consume_signup_verification(token: str) -> SignupVerificationData | None:
    value = await pop_cache(signup_verification_cache_key(token))
    if not isinstance(value, dict):
        return None
    country_code = value.get("country_code")
    phone = value.get("phone")
    if not isinstance(country_code, str) or not isinstance(phone, str):
        return None
    return {"country_code": country_code, "phone": phone}
