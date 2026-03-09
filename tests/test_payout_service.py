"""Tests for payout service (weekly payout processing)."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock
from app.models.user import User
from app.models.commission import Commission, Payout
from app.services.payout_service import process_weekly_payouts
from nanoid import generate as nanoid
from sqlalchemy import select

REFERRAL_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _make_user(email: str, iban: str | None = None, payout_name: str | None = None) -> User:
    return User(
        email=email, hashed_password="fakehash", full_name=email.split("@")[0],
        referral_code=nanoid(REFERRAL_ALPHABET, 8).upper(),
        payout_iban=iban, payout_name=payout_name,
    )


@pytest.mark.asyncio
async def test_payout_below_minimum_skipped(db: AsyncSession):
    """Commissions below the minimum threshold are not paid out."""
    earner = _make_user("small@example.com", iban="AE070331234567890123456", payout_name="Small Earner")
    db.add(earner)
    await db.flush()

    # Add a commission worth only 4.75 (below 50 AED minimum)
    comm = Commission(earner_id=earner.id, source_user_id=earner.id, level=2, amount_aed=4.75, status="pending")
    db.add(comm)
    await db.flush()

    results = await process_weekly_payouts(db)
    assert len(results) == 1
    assert results[0]["status"] == "below_minimum"


@pytest.mark.asyncio
async def test_payout_missing_iban_skipped(db: AsyncSession):
    """Users without payout info are skipped."""
    earner = _make_user("noiban@example.com")
    db.add(earner)
    await db.flush()

    comm = Commission(earner_id=earner.id, source_user_id=earner.id, level=1, amount_aed=76.0, status="pending")
    db.add(comm)
    await db.flush()

    results = await process_weekly_payouts(db)
    assert len(results) == 1
    assert results[0]["status"] == "missing_payout_info"


@pytest.mark.asyncio
async def test_payout_success(db: AsyncSession):
    """Successful payout marks commissions as paid."""
    earner = _make_user("rich@example.com", iban="AE070331234567890123456", payout_name="Rich Earner")
    db.add(earner)
    await db.flush()

    comm = Commission(earner_id=earner.id, source_user_id=earner.id, level=1, amount_aed=76.0, status="pending")
    db.add(comm)
    await db.flush()

    with patch("app.services.payout_service.mamopay_client.create_transfer",
               new_callable=AsyncMock, return_value={"id": "transfer_001"}), \
         patch("app.services.payout_service.send_payout_confirmation",
               new_callable=AsyncMock):
        results = await process_weekly_payouts(db)

    assert len(results) == 1
    assert results[0]["status"] == "completed"

    # Commission should be marked as paid
    updated = (await db.execute(select(Commission).where(Commission.id == comm.id))).scalar_one()
    assert updated.status == "paid"
    assert updated.payout_id is not None


@pytest.mark.asyncio
async def test_payout_failure_resets_commissions(db: AsyncSession):
    """Failed payout leaves commissions as pending."""
    earner = _make_user("fail@example.com", iban="AE070331234567890123456", payout_name="Fail Earner")
    db.add(earner)
    await db.flush()

    comm = Commission(earner_id=earner.id, source_user_id=earner.id, level=1, amount_aed=76.0, status="pending")
    db.add(comm)
    await db.flush()

    with patch("app.services.payout_service.mamopay_client.create_transfer",
               new_callable=AsyncMock, side_effect=Exception("Transfer API down")):
        results = await process_weekly_payouts(db)

    assert len(results) == 1
    assert results[0]["status"] == "failed"

    # Commission should still be pending
    updated = (await db.execute(select(Commission).where(Commission.id == comm.id))).scalar_one()
    assert updated.status == "pending"
    assert updated.payout_id is None


@pytest.mark.asyncio
async def test_payout_no_pending_commissions(db: AsyncSession):
    """Nothing to process when there are no pending commissions."""
    results = await process_weekly_payouts(db)
    assert results == []
