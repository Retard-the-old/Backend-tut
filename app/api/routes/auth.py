from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
from app.db.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.services.auth_service import register_user, login_user
from app.core.security import decode_token, create_access_token, create_refresh_token
from app.models.user import User
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
import secrets
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory reset token store: { token: { "email": str, "expires": datetime } }
_reset_tokens: dict = {}

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
        token = secrets.token_urlsafe(32)
        _reset_tokens[token] = {
            "email": email,
            "expires": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        reset_link = f"https://www.tutorii.com/reset-password?token={token}"
        # Logged to Railway until SES email is configured
        logger.info(f"PASSWORD RESET LINK for {email}: {reset_link}")

    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.get("/validate-reset-token")
async def validate_reset_token(token: str):
    entry = _reset_tokens.get(token)
    if not entry:
        return {"valid": False}
    if datetime.now(timezone.utc) > entry["expires"]:
        del _reset_tokens[token]
        return {"valid": False}
    return {"valid": True, "email": entry["email"]}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    entry = _reset_tokens.get(data.token)
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if datetime.now(timezone.utc) > entry["expires"]:
        del _reset_tokens[data.token]
        raise HTTPException(status_code=400, detail="Reset token has expired")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    result = await db.execute(select(User).where(User.email == entry["email"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = pwd_context.hash(data.new_password)
    del _reset_tokens[data.token]
    await db.commit()

    logger.info(f"Password reset successful for {entry['email']}")
    return {"message": "Password reset successfully. You can now log in."}
