import argparse
import asyncio
from datetime import timedelta

from app.config import config
from app.database import sessionmanager
from app.models.account_token import AccountTokenType
from app.models.user import User
from app.services.single_lab import (
    create_account_token,
    get_single_lab,
    normalize_email,
    password_reset_url,
    user_single_lab_role,
)


async def create_operator_reset_link(email: str) -> str:
    if not config.is_single_lab:
        raise RuntimeError("operator password recovery requires single-Lab mode")

    normalized_email = normalize_email(email)
    async with sessionmanager.session() as db_session:
        lab = await get_single_lab(db_session)
        if lab is None:
            raise RuntimeError("single Lab is not initialized")

        user = await User.find_by(db_session, [User.email == normalized_email])
        if user is None:
            raise RuntimeError("Lab member not found")
        if await user_single_lab_role(db_session, user.id, lab.id) is None:
            raise RuntimeError("Lab member not found")

        _, raw_token = await create_account_token(
            db_session,
            token_type=AccountTokenType.PASSWORD_RESET,
            created_by_user_id=None,
            expires_in=timedelta(minutes=config.PASSWORD_RESET_TTL_MINUTES),
            email=user.email,
            lab_id=lab.id,
            user_id=user.id,
        )
        await db_session.commit()
    return password_reset_url(raw_token)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an operator-only password reset link for a Lab member."
    )
    parser.add_argument("email")
    args = parser.parse_args()
    try:
        url = asyncio.run(create_operator_reset_link(args.email))
    except RuntimeError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(url)


if __name__ == "__main__":
    main()
