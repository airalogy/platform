import os
import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, StringConstraints, model_validator
from sqlalchemy import func, select, text

from app.config import config
from app.database import DBSession
from app.models.account_token import AccountTokenType
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import ProjectRole
from app.models.user import User
from app.services.account_security import bump_auth_version
from app.services.single_lab import (
    add_user_to_single_lab,
    create_account_token,
    ensure_default_project,
    find_valid_account_token,
    get_single_lab,
    invitation_url,
    normalize_email,
    password_reset_url,
    user_single_lab_role,
    utcnow,
)

from .depends import CurrentUser, create_access_token
from .utils import UidStr

router = APIRouter(prefix="/instance", tags=["instance"])


def ensure_single_lab_mode() -> None:
    if not config.is_single_lab:
        raise HTTPException(status_code=404, detail="Not found")


class InstanceLabInfo(BaseModel):
    id: UUID
    uid: str
    name: str


class InstanceStatus(BaseModel):
    deployment_mode: str
    single_lab: bool
    initialized: bool
    signup_mode: str
    bootstrap_token_required: bool
    site_url: str
    lab: InstanceLabInfo | None = None


@router.get("", response_model=InstanceStatus)
async def get_instance_status(db_session: DBSession):
    lab = await get_single_lab(db_session)
    return InstanceStatus(
        deployment_mode=config.DEPLOYMENT_MODE,
        single_lab=config.is_single_lab,
        initialized=not config.is_single_lab or lab is not None,
        signup_mode=config.effective_signup_mode,
        bootstrap_token_required=bool(config.INITIAL_ADMIN_TOKEN),
        site_url=config.SITE_URL,
        lab=(
            InstanceLabInfo(id=lab.id, uid=lab.uid, name=lab.name)
            if lab is not None
            else None
        ),
    )


class BootstrapParams(BaseModel):
    setup_token: str = ""
    username: UidStr
    email: EmailStr
    name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=8, max_length=32)]
    confirm_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]

    @model_validator(mode="after")
    def validate_passwords(self) -> "BootstrapParams":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


@router.post("/bootstrap")
async def bootstrap_single_lab(params: BootstrapParams, db_session: DBSession):
    ensure_single_lab_mode()
    if config.INITIAL_ADMIN_TOKEN and not secrets.compare_digest(
        params.setup_token,
        config.INITIAL_ADMIN_TOKEN,
    ):
        raise HTTPException(status_code=403, detail="Invalid initial setup code")

    # Serialize the one-time setup path on PostgreSQL so two first requests cannot
    # both become instance owners.
    await db_session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('airalogy-single-lab-bootstrap'))")
    )
    users_count = await db_session.scalar(select(func.count()).select_from(User))
    labs_count = await db_session.scalar(select(func.count()).select_from(Lab))
    if users_count or labs_count:
        raise HTTPException(status_code=409, detail="Instance is already initialized")
    if params.username == config.SINGLE_LAB_UID:
        raise HTTPException(
            status_code=400,
            detail="Administrator username must differ from the single Lab UID",
        )

    user = User(
        username=params.username,
        name=params.name,
        email=normalize_email(str(params.email)),
        country_code="",
        phone="",
        password=params.password,
        api_key_iv=os.urandom(16).hex(),
    )
    db_session.add(user)
    await db_session.flush()

    lab = Lab(
        uid=config.SINGLE_LAB_UID,
        name=config.SINGLE_LAB_NAME,
        description=config.SINGLE_LAB_DESCRIPTION,
        create_user_id=user.id,
        users_count=1,
    )
    db_session.add(lab)
    await db_session.flush()
    db_session.add(
        LabUser(
            lab_id=lab.id,
            user_id=user.id,
            role=LabRole.OWNER,
            create_user_id=user.id,
        )
    )
    await ensure_default_project(db_session, lab, user)
    await db_session.commit()

    return {
        "token": create_access_token(user),
        "user": user,
        "lab": InstanceLabInfo(id=lab.id, uid=lab.uid, name=lab.name),
    }


class CreateInvitationParams(BaseModel):
    email: EmailStr
    lab_role: LabRole = LabRole.MEMBER
    project_role: ProjectRole = ProjectRole.RECORDER


async def require_single_lab_manager(
    db_session: DBSession,
    current_user: User,
) -> tuple[Lab, LabRole]:
    lab = await get_single_lab(db_session)
    if lab is None:
        raise HTTPException(status_code=409, detail="Single Lab is not initialized")
    role = await user_single_lab_role(db_session, current_user.id, lab.id)
    if role not in {LabRole.OWNER, LabRole.MANAGER}:
        raise HTTPException(status_code=403, detail="Permission denied")
    return lab, role


@router.post("/invitations")
async def create_invitation(
    params: CreateInvitationParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_single_lab_mode()
    lab, current_role = await require_single_lab_manager(db_session, current_user)
    if params.lab_role == LabRole.OWNER:
        raise HTTPException(status_code=400, detail="Owner invitations are not allowed")
    if params.project_role == ProjectRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Default Project owner invitations are not allowed",
        )
    if current_role == LabRole.MANAGER and params.lab_role != LabRole.MEMBER:
        raise HTTPException(
            status_code=403,
            detail="Managers can only invite Lab members",
        )

    email = normalize_email(str(params.email))
    existing_user = await User.find_by(db_session, [User.email == email])
    if existing_user is not None:
        existing_membership = await LabUser.find_by(
            db_session,
            [LabUser.lab_id == lab.id, LabUser.user_id == existing_user.id],
        )
        if existing_membership is not None:
            raise HTTPException(status_code=409, detail="User is already in the Lab")

    token, raw_token = await create_account_token(
        db_session,
        token_type=AccountTokenType.INVITATION,
        created_by_user_id=current_user.id,
        expires_in=timedelta(hours=config.INVITATION_TTL_HOURS),
        email=email,
        lab_id=lab.id,
        user_id=existing_user.id if existing_user is not None else None,
        lab_role=params.lab_role,
        project_role=params.project_role,
    )
    await db_session.commit()
    return {
        "id": token.id,
        "email": email,
        "expires_at": token.expires_at,
        "existing_account": existing_user is not None,
        "url": invitation_url(raw_token),
    }


@router.get("/invitations/{raw_token}")
async def get_invitation(raw_token: str, db_session: DBSession):
    ensure_single_lab_mode()
    token = await find_valid_account_token(
        db_session,
        raw_token,
        AccountTokenType.INVITATION,
    )
    if token is None:
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired")
    lab = await Lab.find(db_session, token.lab_id)
    return {
        "email": token.email,
        "expires_at": token.expires_at,
        "lab": InstanceLabInfo(id=lab.id, uid=lab.uid, name=lab.name),
        "existing_account": token.user_id is not None,
    }


@router.post("/invitations/{raw_token}/accept")
async def accept_invitation(
    raw_token: str,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_single_lab_mode()
    token = await find_valid_account_token(
        db_session,
        raw_token,
        AccountTokenType.INVITATION,
        for_update=True,
    )
    if token is None:
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired")
    if normalize_email(current_user.email) != token.email:
        raise HTTPException(
            status_code=403,
            detail="Invitation email does not match the signed-in account",
        )
    lab = await Lab.find(db_session, token.lab_id)
    await add_user_to_single_lab(
        db_session,
        lab=lab,
        user=current_user,
        created_by_user_id=token.created_by_user_id or current_user.id,
        lab_role=LabRole(token.lab_role or LabRole.MEMBER),
        project_role=ProjectRole(token.project_role or ProjectRole.RECORDER),
    )
    token.user_id = current_user.id
    token.consumed_at = utcnow()
    await db_session.commit()
    return {"success": True, "lab": InstanceLabInfo(id=lab.id, uid=lab.uid, name=lab.name)}


class CreatePasswordResetParams(BaseModel):
    user_id: UUID


@router.post("/password-reset-links")
async def create_password_reset_link(
    params: CreatePasswordResetParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_single_lab_mode()
    lab, current_role = await require_single_lab_manager(db_session, current_user)
    target_role = await user_single_lab_role(db_session, params.user_id, lab.id)
    if target_role is None:
        raise HTTPException(status_code=404, detail="Lab member not found")
    if current_role == LabRole.MANAGER and target_role != LabRole.MEMBER:
        raise HTTPException(
            status_code=403,
            detail="Managers can only reset member passwords",
        )

    target_user = await User.find(db_session, params.user_id)
    token, raw_token = await create_account_token(
        db_session,
        token_type=AccountTokenType.PASSWORD_RESET,
        created_by_user_id=current_user.id,
        expires_in=timedelta(minutes=config.PASSWORD_RESET_TTL_MINUTES),
        email=target_user.email,
        lab_id=lab.id,
        user_id=target_user.id,
    )
    await db_session.commit()
    return {
        "id": token.id,
        "email": target_user.email,
        "expires_at": token.expires_at,
        "url": password_reset_url(raw_token),
    }


@router.get("/password-resets/{raw_token}")
async def get_password_reset(raw_token: str, db_session: DBSession):
    ensure_single_lab_mode()
    token = await find_valid_account_token(
        db_session,
        raw_token,
        AccountTokenType.PASSWORD_RESET,
    )
    if token is None:
        raise HTTPException(status_code=404, detail="Password reset is invalid or expired")
    return {"email": token.email, "expires_at": token.expires_at}


class ResetPasswordParams(BaseModel):
    password: Annotated[str, StringConstraints(min_length=8, max_length=32)]
    confirm_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]

    @model_validator(mode="after")
    def validate_passwords(self) -> "ResetPasswordParams":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


@router.post("/password-resets/{raw_token}")
async def reset_password(
    raw_token: str,
    params: ResetPasswordParams,
    db_session: DBSession,
):
    ensure_single_lab_mode()
    token = await find_valid_account_token(
        db_session,
        raw_token,
        AccountTokenType.PASSWORD_RESET,
        for_update=True,
    )
    if token is None or token.user_id is None:
        raise HTTPException(status_code=404, detail="Password reset is invalid or expired")
    user = await User.find(db_session, token.user_id, with_for_update=True)
    user.password = params.password
    await bump_auth_version(db_session, user.id)
    token.consumed_at = utcnow()
    await db_session.commit()
    return {"success": True}


class ChangeOwnPasswordParams(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]
    password: Annotated[str, StringConstraints(min_length=8, max_length=32)]
    confirm_password: Annotated[str, StringConstraints(min_length=8, max_length=32)]

    @model_validator(mode="after")
    def validate_passwords(self) -> "ChangeOwnPasswordParams":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


@router.put("/account/password")
async def change_own_password(
    params: ChangeOwnPasswordParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    ensure_single_lab_mode()
    if not current_user.verify_password(params.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password = params.password
    auth_version = await bump_auth_version(db_session, current_user.id)
    await db_session.commit()
    return {
        "success": True,
        "token": create_access_token(current_user, auth_version),
    }
