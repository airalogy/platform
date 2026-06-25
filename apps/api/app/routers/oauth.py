import secrets
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, StringConstraints, field_validator

from app.database import DBSession
from app.models.oauth import OAuthAccessToken, OAuthAuthorizationCode, OAuthClient
from app.models.user import User

from .depends import CurrentUser

router = APIRouter(prefix="/oauth", tags=["oauth"])

bearer_scheme = HTTPBearer(auto_error=False)

AUTH_CODE_EXPIRE_SECONDS = 10 * 60
ACCESS_TOKEN_EXPIRE_SECONDS = 30 * 24 * 60 * 60


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(params)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _validate_redirect_uri(redirect_uri: str):
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri scheme")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri host")


class OAuthClientCreateParams(BaseModel):
    name: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, strip_whitespace=True),
    ]
    redirect_uris: list[
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=2048, strip_whitespace=True),
        ]
    ]

    @field_validator("redirect_uris")
    @classmethod
    def validate_redirect_uris(cls, redirect_uris: list[str]) -> list[str]:
        if not redirect_uris:
            raise ValueError("redirect_uris cannot be empty")
        if len(redirect_uris) > 20:
            raise ValueError("redirect_uris cannot contain more than 20 items")

        normalized: list[str] = []
        for redirect_uri in redirect_uris:
            _validate_redirect_uri(redirect_uri)
            normalized.append(redirect_uri)
        return sorted(set(normalized))


@router.post("/clients")
async def create_oauth_client(
    params: OAuthClientCreateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    # tmp disable this api
    raise HTTPException(status_code=400, detail="Not implemented")

    client_id = ""
    for _ in range(5):
        candidate = f"oc_{secrets.token_urlsafe(24)}"
        if not await OAuthClient.exists(
            db_session, [OAuthClient.client_id == candidate]
        ):
            client_id = candidate
            break
    if not client_id:
        raise HTTPException(status_code=500, detail="Failed to create client_id")

    client_secret = f"os_{secrets.token_urlsafe(32)}"
    oauth_client = OAuthClient(
        name=params.name,
        client_id=client_id,
        redirect_uris=params.redirect_uris,
        create_user_id=current_user.id,
    )
    oauth_client.client_secret = client_secret
    db_session.add(oauth_client)
    await db_session.commit()
    return {
        "name": oauth_client.name,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": oauth_client.redirect_uris,
    }


@router.get("/authorize")
async def oauth_authorize(
    db_session: DBSession,
    current_user: CurrentUser,
    response_type: Literal["code"] = Query(...),
    client_id: str = Query(..., min_length=10, max_length=128),
    redirect_uri: str = Query(..., min_length=1, max_length=2048),
    state: str | None = Query(None, max_length=2048),
    scope: str = Query("basic", max_length=256),
    auto_redirect: bool = Query(False),
):
    _validate_redirect_uri(redirect_uri)
    oauth_client: OAuthClient | None = await OAuthClient.find_by(
        db_session,
        [
            OAuthClient.client_id == client_id,
            OAuthClient.is_active.is_(True),
        ],
    )
    if oauth_client is None:
        raise HTTPException(status_code=400, detail="Invalid client_id")

    if redirect_uri not in oauth_client.redirect_uris:
        raise HTTPException(status_code=400, detail="redirect_uri is not allowed")

    code = f"oa_{secrets.token_urlsafe(32)}"
    expires_at = datetime.now() + timedelta(seconds=AUTH_CODE_EXPIRE_SECONDS)
    authorization_code = OAuthAuthorizationCode(
        client_id=oauth_client.id,
        user_id=current_user.id,
        code=code,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state or "",
        expires_at=expires_at,
    )
    db_session.add(authorization_code)
    await db_session.commit()

    redirect_target = _append_query_params(
        redirect_uri,
        {"code": code, **({"state": state} if state else {})},
    )
    if auto_redirect:
        return RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)

    return {
        "code": code,
        "state": state,
        "scope": scope,
        "expires_in": AUTH_CODE_EXPIRE_SECONDS,
        "redirect_to": redirect_target,
    }


@router.post("/token")
async def oauth_token(
    db_session: DBSession,
    grant_type: Annotated[str, Form(...)],
    code: Annotated[str, Form(min_length=1, max_length=128)],
    redirect_uri: Annotated[str, Form(min_length=1, max_length=2048)],
    client_id: Annotated[str, Form(min_length=1, max_length=128)],
    client_secret: Annotated[str, Form(min_length=1, max_length=256)],
):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")
    _validate_redirect_uri(redirect_uri)

    oauth_client: OAuthClient | None = await OAuthClient.find_by(
        db_session,
        [
            OAuthClient.client_id == client_id,
            OAuthClient.is_active.is_(True),
        ],
    )
    if oauth_client is None:
        raise HTTPException(status_code=400, detail="Invalid client")
    if not oauth_client.verify_client_secret(client_secret):
        raise HTTPException(status_code=400, detail="Invalid client")

    auth_code: OAuthAuthorizationCode | None = await OAuthAuthorizationCode.find_by(
        db_session,
        [
            OAuthAuthorizationCode.code == code,
            OAuthAuthorizationCode.client_id == oauth_client.id,
            OAuthAuthorizationCode.used_at.is_(None),
        ],
    )
    if auth_code is None:
        raise HTTPException(status_code=400, detail="Invalid authorization code")
    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    if auth_code.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="Authorization code expired")

    now = datetime.now()
    access_token = f"at_{secrets.token_urlsafe(48)}"
    token = OAuthAccessToken(
        client_id=oauth_client.id,
        user_id=auth_code.user_id,
        access_token=access_token,
        scope=auth_code.scope,
        expires_at=now + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS),
    )
    auth_code.used_at = now
    db_session.add(token)
    await db_session.commit()
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
        "scope": auth_code.scope,
    }


async def get_current_oauth_user(
    db_session: DBSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid token")

    token: OAuthAccessToken | None = await OAuthAccessToken.find_by(
        db_session,
        [
            OAuthAccessToken.access_token == credentials.credentials,
            OAuthAccessToken.revoked_at.is_(None),
            OAuthAccessToken.expires_at >= datetime.now(),
        ],
    )
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await User.find_by(
        db_session,
        [
            User.id == token.user_id,
        ],
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


OAuthUser = Annotated[User, Depends(get_current_oauth_user)]


@router.get("/userinfo")
async def oauth_user_info(current_user: OAuthUser):
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "username": current_user.username,
        "email": current_user.email,
        "country_code": current_user.country_code,
        "phone": current_user.phone,
        "avatar_url": current_user.avatar_url,
    }
