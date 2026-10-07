from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_session

bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Authentication is required"},
        )
    config = request.app.state.settings
    try:
        claims = jwt.decode(
            credentials.credentials,
            config.jwt_secret,
            algorithms=["HS256"],
            issuer=config.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
        if claims.get("token_type") != "access":
            raise jwt.InvalidTokenError("Expected an access token")
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Access token is invalid or expired"},
        ) from None
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Access token is invalid or expired"},
        )
    return user
