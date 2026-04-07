from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from nanoid import generate as nanoid
from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
from app.services.email_service import send_welcome_email
from app.core.validators import validate_password, validate_full_name, validate_referral_code

REFERRAL_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

async def register_user(req: RegisterRequest, db: AsyncSession) -> TokenResponse:
    validate_password(req.password)
    req.full_name = validate_full_name(req.full_name)
    if req.referral_code:
        req.referral_code = validate_referral_code(req.referral_code)

    existing = await db.execute(select(User).where(User.email == req.email.lower().strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    referred_by_id = None
    if req.referral_code:
        ref = await db.execute(select(User).where(User.referral_code == req.referral_code.upper()))
        referrer = ref.scalar_one_or_none()
        if referrer is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid referral code")
        referred_by_id = referrer.id

    # Generate a unique referral code — retry up to 5 times on collision
    referral_code = None
    for _ in range(5):
        candidate = nanoid(REFERRAL_ALPHABET, 8).upper()
        clash = await db.execute(select(User).where(User.referral_code == candidate))
        if not clash.scalar_one_or_none():
            referral_code = candidate
            break
    if not referral_code:
        raise HTTPException(status_code=500, detail="Could not generate unique referral code. Please try again.")

    user = User(
        email=req.email.lower().strip(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        phone=req.phone.strip() if req.phone else None,
        referral_code=referral_code,
        referred_by_id=referred_by_id,
    )
    db.add(user)
    await db.flush()
    await send_welcome_email(user.email, user.full_name, user.referral_code)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )

async def login_user(req: LoginRequest, db: AsyncSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == req.email.lower().strip()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
