import random
import string
import time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import (
    AfterValidator,
    StringConstraints,
)

from app.libs.redis import clear_cache, get_cache, set_cache
from app.libs.sms_service import send_verify_code


def no_double_underscore(v: str) -> str:
    if "__" in v:
        raise HTTPException(status_code=400, detail="Double underscore is not allowed")
    return v


# type alias
UUIDStr = (
    Annotated[
        str,
        StringConstraints(
            strict=True,
            min_length=36,
            max_length=36,
            pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        ),
    ]
    | UUID
)

"""
uid is a string that is used to identify a resource
- Lowercase letters a-z, _, numbers 0-9
- only start with lowercase letters
- Continuous underlining is not allowed
- max length is 64
"""
UidStr = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
    AfterValidator(no_double_underscore),
]


async def send_sms_verify_code(
    phone: str,
    type: Literal["signup", "signin", "reset_password", "change_phone"],
):
    verify_code_data = await get_cache(f"verify_code_{phone}")
    if (
        verify_code_data
        and verify_code_data["sent_at"] + 60 > time.time()
        and verify_code_data["type"] == type
    ):
        raise HTTPException(status_code=400, detail="Verify code already sent")

    code = "".join(random.choices(string.digits, k=6))
    await send_verify_code(phone, code)
    await set_cache(
        f"verify_code_{phone}",
        {"code": code, "sent_at": time.time(), "type": type},
        60 * 5,
    )
    return True


async def check_sms_verify_code(
    phone: str,
    code: str,
    type: Literal["signup", "signin", "reset_password", "change_phone"],
):
    cache_key = f"verify_code_{phone}"
    code_in_cache = await get_cache(cache_key)
    if (
        code_in_cache is None
        or code_in_cache["code"] != code
        or code_in_cache["type"] != type
    ):
        raise HTTPException(status_code=400, detail="Verify code is invalid")
    await clear_cache(cache_key)
    return True
