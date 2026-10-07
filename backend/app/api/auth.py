from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.config import Settings
from app.core.security import (
    hash_password,
    hash_token,
    issue_access_token,
    issue_refresh_token,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.db.session import get_session
from app.schemas.auth import (
    AuthOutput,
    LoginInput,
    ProfileUpdateInput,
    RefreshInput,
    RegisterInput,
    TokensOutput,
    UserOutput,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def build_tokens(user_id: UUID, config: Settings) -> tuple[TokensOutput, RefreshToken]:
    access = issue_access_token(user_id, config)
    refresh, token_hash, expires_at = issue_refresh_token(user_id, config)
    now = datetime.now(UTC)
    return (
        TokensOutput(
            access_token=access,
            refresh_token=refresh,
            expires_in=config.access_token_minutes * 60,
        ),
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
        ),
    )


@router.post("/register", status_code=201, response_model=AuthOutput)
async def register(
    payload: RegisterInput,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthOutput:
    now = datetime.now(UTC)
    user = User(
        name=payload.name,
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        created_at=now,
    )
    try:
        async with session.begin():
            existing = await session.scalar(select(User).where(User.email == user.email))
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "email_already_registered",
                        "message": "An account with this email already exists",
                    },
                )
            session.add(user)
            await session.flush()
            tokens, refresh_row = build_tokens(user.id, request.app.state.settings)
            session.add(refresh_row)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "email_already_registered",
                "message": "An account with this email already exists",
            },
        ) from None
    return AuthOutput(user=UserOutput.model_validate(user), tokens=tokens)


@router.post("/login", response_model=AuthOutput)
async def login(
    payload: LoginInput,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthOutput:
    async with session.begin():
        user = await session.scalar(select(User).where(User.email == str(payload.email)))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=401,
                detail={"code": "invalid_credentials", "message": "Email or password is incorrect"},
            )
        tokens, refresh_row = build_tokens(user.id, request.app.state.settings)
        session.add(refresh_row)
        await session.flush()
    return AuthOutput(user=UserOutput.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=TokensOutput)
async def refresh_tokens(
    payload: RefreshInput,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokensOutput:
    config = request.app.state.settings
    try:
        claims = jwt.decode(
            payload.refresh_token,
            config.jwt_secret,
            algorithms=["HS256"],
            issuer=config.jwt_issuer,
            options={"require": ["sub", "jti", "exp", "iat", "iss"]},
        )
        if claims.get("token_type") != "refresh":
            raise jwt.InvalidTokenError("Expected a refresh token")
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_refresh_token",
                "message": "Refresh token is invalid or expired",
            },
        ) from None

    async with session.begin():
        old_token = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(payload.refresh_token),
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        user = await session.get(User, user_id)
        if (
            old_token is None
            or user is None
            or old_token.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
        ):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "invalid_refresh_token",
                    "message": "Refresh token is invalid or expired",
                },
            )
        old_token.revoked_at = datetime.now(UTC)
        tokens, refresh_row = build_tokens(user.id, config)
        session.add(refresh_row)
        await session.flush()
    return tokens


@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshInput,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    token = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.token_hash == hash_token(payload.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    if token is not None:
        token.revoked_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOutput)
async def get_me(user: User = Depends(current_user)) -> UserOutput:
    return UserOutput.model_validate(user)


@router.patch("/me", response_model=UserOutput)
async def update_me(
    payload: ProfileUpdateInput,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOutput:
    if payload.name is not None:
        user.name = payload.name
    await session.commit()
    await session.refresh(user)
    return UserOutput.model_validate(user)
