import os
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.config import config
from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.user import User

from .depends import create_access_token
from .utils import UidStr, check_sms_verify_code, send_sms_verify_code

router = APIRouter(tags=["login"])


class SignInParams(BaseModel):
    country_code: Annotated[
        str,
        StringConstraints(pattern=r"^\d{1,4}$", min_length=1, max_length=4),
    ]
    phone: Annotated[
        str,
        StringConstraints(pattern=r"^\d{7,11}$", min_length=7, max_length=11),
    ]
    verify_code: Annotated[str, StringConstraints(min_length=6, max_length=6)]


@router.post("/signin")
async def login(params: SignInParams, db_session: DBSession):
    await check_sms_verify_code(
        f"{params.country_code}{params.phone}", params.verify_code, "signin"
    )
    user: User | None = await User.find_by(
        db_session,
        [User.country_code == params.country_code, User.phone == params.phone],
    )
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    return {"token": create_access_token(user), "user": user}


class SignInByEmailParams(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=32)]


@router.post("/signin_by_email")
async def signin_by_email(params: SignInByEmailParams, db_session: DBSession):
    user: User | None = await User.find_by(db_session, [User.email == params.email])
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    if not user.verify_password(params.password):
        raise HTTPException(status_code=400, detail="The password is incorrect")

    return {"token": create_access_token(user), "user": user}


class SignUpParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: UidStr
    email: Annotated[
        EmailStr,
        Field(max_length=254),
    ]
    name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=64),
        Field(validation_alias=AliasChoices("name", "displayName")),
    ]
    confirm_password: Annotated[
        str,
        StringConstraints(min_length=8, max_length=32),
        Field(
            validation_alias=AliasChoices(
                "confirm_password",
                "confirmPassword",
                "comfirm_password",
            )
        ),
    ]
    country_code: Annotated[
        str | None,
        StringConstraints(pattern=r"^\d{1,4}$", min_length=1, max_length=4),
    ] = None
    phone: Annotated[
        str | None,
        StringConstraints(pattern=r"^\d{7,11}$", min_length=7, max_length=11),
    ] = None
    verify_code: Annotated[
        str | None, StringConstraints(min_length=6, max_length=6)
    ] = None
    password: Annotated[str, StringConstraints(min_length=8, max_length=32)]

    @model_validator(mode="after")
    def check_passwords_match(self) -> "SignUpParams":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        phone_fields = [self.country_code, self.phone, self.verify_code]
        if any(phone_fields) and not all(phone_fields):
            raise ValueError("country_code, phone and verify_code must be provided together")
        return self

    @property
    def has_phone_verification(self) -> bool:
        return bool(self.country_code and self.phone and self.verify_code)


@router.post("/signup")
async def signup(params: SignUpParams, db_session: DBSession):
    email_exists = await User.exists(db_session, [User.email == params.email])
    if email_exists:
        raise HTTPException(status_code=400, detail="Email already exists")

    username_exists = await User.exists(db_session, [User.username == params.username])
    if username_exists:
        raise HTTPException(status_code=400, detail="Username already exists")
    lab_exists = await Lab.exists(db_session, [Lab.uid == params.username])
    if lab_exists:
        raise HTTPException(status_code=400, detail="Username already exists")

    if params.has_phone_verification:
        phone_exists = await User.exists(
            db_session,
            [
                User.country_code == params.country_code,
                User.phone == params.phone,
            ],
        )
        if phone_exists:
            raise HTTPException(status_code=400, detail="Phone number already exists")

        await check_sms_verify_code(
            f"{params.country_code}{params.phone}", params.verify_code, "signup"
        )
    user = User(
        username=params.username,
        name=params.name,
        email=params.email,
        country_code=params.country_code or "",
        phone=params.phone or "",
        password=params.password,
        api_key_iv=os.urandom(16).hex(),
    )
    db_session.add(user)
    await db_session.flush()
    lab = Lab(
        uid=user.username,
        name=f"{user.username}'s Lab",
        create_user_id=user.id,
    )
    db_session.add(lab)
    await db_session.flush()
    lab_user = LabUser(
        lab_id=lab.id,
        user_id=user.id,
        role=LabRole.OWNER,
        create_user_id=user.id,
    )
    db_session.add(lab_user)
    await db_session.commit()
    return {"token": create_access_token(user), "user": user}


class SendVerifyCodeParams(BaseModel):
    type: Literal["signup", "signin", "reset_password", "change_phone"]
    country_code: Annotated[
        str,
        StringConstraints(pattern=r"^\d{1,4}$", min_length=1, max_length=4),
    ]
    phone: Annotated[
        str, StringConstraints(pattern=r"^\d{7,11}$", min_length=7, max_length=11)
    ]


@router.post("/send_verify_code")
async def send_phone_verify_code(
    db_session: DBSession,
    params: SendVerifyCodeParams,
):
    if params.country_code not in config.sms_country_code_allowlist:
        raise HTTPException(status_code=400, detail="Country code is not supported")

    user: User | None = await User.find_by(
        db_session,
        [User.country_code == params.country_code, User.phone == params.phone],
    )
    if params.type == "signin" or params.type == "reset_password":
        if user is None:
            raise HTTPException(status_code=400, detail="User not found")
    elif params.type == "signup":
        if user is not None:
            raise HTTPException(status_code=400, detail="Phone number already exists")

    await send_sms_verify_code(f"{params.country_code}{params.phone}", params.type)
    return {"success": True}


@router.get(
    "/check_user_uid",
    description="Check if a UID is valid and available for User",
)
async def check_user_uid_exists(uid: UidStr, db_session: DBSession):
    user_exists = await User.exists(db_session, [User.username == uid])
    if user_exists:
        raise HTTPException(status_code=400, detail="User UID already exists")

    lab_exists = await Lab.exists(db_session, [Lab.uid == uid])
    if lab_exists:
        raise HTTPException(status_code=400, detail="User UID already exists")

    return {"result": True, "message": "UID is valid and available"}
