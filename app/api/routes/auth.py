from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from jose import JWTError
from app.db.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.services.auth_service import register_user, login_user
from app.core.security import decode_token, create_access_token, create_refresh_token
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.core.config import settings
from app.services.email_service import send_password_reset_email
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
import secrets
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await register_user(req, db)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await login_user(req, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        uid = payload["sub"]
        return TokenResponse(access_token=create_access_token(uid), refresh_token=create_refresh_token(uid))
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    email = data.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if user:
        # Clean up any expired tokens for this email
        await db.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.email == email,
                PasswordResetToken.expires_at < datetime.now(timezone.utc)
            )
        )

        token = secrets.token_urlsafe(32)
        reset_entry = PasswordResetToken(
            token=token,
            email=email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(reset_entry)
        await db.flush()

        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        # Try to send via email service; fall back to logging only the email (not the token)
        try:
            await send_password_reset_email(email, user.full_name, reset_link)
            logger.info(f"Password reset email sent to {email}")
        except Exception:
            # SES not yet configured — log that a reset was requested, NOT the token
            logger.warning(f"Password reset requested for {email} — email delivery failed (SES not configured). Reset link NOT logged for security.")

    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.get("/validate-reset-token")
async def validate_reset_token(token: str, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.used == False,  # noqa: E712
            PasswordResetToken.expires_at > now
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return {"valid": False}
    return {"valid": True, "email": entry.email}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == data.token,
            PasswordResetToken.used == False,  # noqa: E712
            PasswordResetToken.expires_at > now
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user_result = await db.execute(select(User).where(User.email == entry.email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = pwd_context.hash(data.new_password)
    entry.used = True  # Mark token as consumed — prevents reuse
    await db.flush()

    logger.info(f"Password reset successful for {entry.email}")
    return {"message": "Password reset successfully. You can now log in."}
