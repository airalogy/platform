import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from jose import jwt

from app.config import config
from app.database import DBSession
from app.models.user import User

ALGORITHM = "HS256"

logger = logging.getLogger("app")


def create_access_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(days=30)

    data = {"exp": expire, "user": {"id": str(user.id)}}
    encoded_jwt = jwt.encode(data, config.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    db_session: DBSession,
    request: Request,
    auth_token: Annotated[str | None, Header()] = "",
) -> User:
    try:
        payload = jwt.decode(auth_token, config.SECRET_KEY, algorithms=ALGORITHM)
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    user = await User.find_by(db_session, [User.id == payload["user"]["id"]])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    logger.info(f"--- current_user: {user.username}, {user.id} ---")

    request.state.current_user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_current_user(
    db_session: DBSession,
    request: Request,
    auth_token: Annotated[str | None, Header()] = "",
) -> User | None:
    if not auth_token:
        request.state.current_user = None
        return None

    try:
        payload = jwt.decode(auth_token, config.SECRET_KEY, algorithms=ALGORITHM)
    except jwt.JWTError:
        request.state.current_user = None
        return None

    user = await User.find_by(db_session, [User.id == payload["user"]["id"]])
    if user is None:
        request.state.current_user = None
        return None

    logger.info(f"--- current_user: {user.username}, {user.id} ---")
    request.state.current_user = user
    return user


OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client


HTTPClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
