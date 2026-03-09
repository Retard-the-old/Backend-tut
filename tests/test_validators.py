"""Tests for input validators."""
import pytest
from fastapi import HTTPException
from app.core.validators import validate_password, validate_iban, validate_full_name, validate_referral_code, validate_slug


def test_password_valid():
    assert validate_password("StrongPass1") == "StrongPass1"


def test_password_too_short():
    with pytest.raises(HTTPException) as exc:
        validate_password("Ab1")
    assert exc.value.status_code == 422


def test_password_no_uppercase():
    with pytest.raises(HTTPException):
        validate_password("weakpass1")


def test_password_no_digit():
    with pytest.raises(HTTPException):
        validate_password("NoDigitHere")


def test_iban_valid_uae():
    assert validate_iban("AE07 0331 2345 6789 0123 456") == "AE070331234567890123456"


def test_iban_invalid_format():
    with pytest.raises(HTTPException):
        validate_iban("not-an-iban")


def test_iban_uae_wrong_length():
    with pytest.raises(HTTPException):
        validate_iban("AE0703312345")


def test_full_name_valid():
    assert validate_full_name("  John Doe  ") == "John Doe"


def test_full_name_too_short():
    with pytest.raises(HTTPException):
        validate_full_name("J")


def test_referral_code_valid():
    assert validate_referral_code("ABC12345") == "ABC12345"
    assert validate_referral_code(None) is None
    assert validate_referral_code("") is None


def test_referral_code_invalid():
    with pytest.raises(HTTPException):
        validate_referral_code("bad!code")


def test_slug_valid():
    assert validate_slug("my-course-title") == "my-course-title"


def test_slug_invalid():
    with pytest.raises(HTTPException):
        validate_slug("Bad Slug With Spaces")
