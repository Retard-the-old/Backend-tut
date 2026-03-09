"""Reusable input validators for Tutorii.

Import and use in Pydantic schemas via field_validator or in services directly.
"""
from __future__ import annotations
import re
from fastapi import HTTPException, status


# ── Password ──

MIN_PASSWORD_LENGTH = 8

def validate_password(password: str) -> str:
    """Enforce password strength rules. Returns the password if valid, raises otherwise."""
    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one digit")
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"password": errors},
        )
    return password


# ── IBAN ──

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")

def validate_iban(iban: str) -> str:
    """Basic IBAN format validation. Returns cleaned IBAN or raises."""
    cleaned = iban.upper().replace(" ", "").replace("-", "")
    if not IBAN_PATTERN.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"payout_iban": ["Invalid IBAN format. Expected: 2 letters, 2 digits, then 11-30 alphanumeric characters."]},
        )
    # UAE IBANs are always 23 chars: AE + 2 check + 3 bank + 16 account
    if cleaned.startswith("AE") and len(cleaned) != 23:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"payout_iban": ["UAE IBANs must be exactly 23 characters (e.g. AE070331234567890123456)."]},
        )
    return cleaned


# ── Full Name ──

def validate_full_name(name: str) -> str:
    """Ensure name is reasonable."""
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"full_name": ["Name must be at least 2 characters"]},
        )
    if len(name) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"full_name": ["Name must be under 200 characters"]},
        )
    return name


# ── Referral Code ──

REFERRAL_PATTERN = re.compile(r"^[A-Z0-9]{6,12}$")

def validate_referral_code(code: str | None) -> str | None:
    """Validate referral code format if provided."""
    if code is None or code.strip() == "":
        return None
    cleaned = code.upper().strip()
    if not REFERRAL_PATTERN.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"referral_code": ["Referral code must be 6-12 alphanumeric characters."]},
        )
    return cleaned


# ── Slug ──

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def validate_slug(slug: str) -> str:
    """Validate URL-safe slug."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"slug": ["Slug must be lowercase alphanumeric with hyphens only (e.g. my-course-title)."]},
        )
    return slug
