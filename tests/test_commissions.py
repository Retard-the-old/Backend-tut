"""Tests for commission service (L1 / L2 creation logic)."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.subscription import Subscription, Payment
from app.models.commission import Commission
from app.services.commission_service import create_commissions_for_payment
from app.core.config import settings
from sqlalchemy import select
from nanoid import generate as nanoid


REFERRAL_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _make_user(email: str, referred_by_id: str | None = None) -> User:
    return User(
        email=email, hashed_password="fakehash", full_name=email.split("@")[0],
        referral_code=nanoid(REFERRAL_ALPHABET, 8).upper(), referred_by_id=referred_by_id,
    )


@pytest.mark.asyncio
async def test_no_commissions_without_referral(db: AsyncSession):
    """A user who wasn't referred generates no commissions."""
    user = _make_user("solo@example.com")
    db.add(user)
    await db.flush()

    sub = Subscription(user_id=user.id, plan_price_aed=95.0, status="active")
    db.add(sub)
    await db.flush()

    payment = Payment(subscription_id=sub.id, user_id=user.id, amount_aed=95.0, status="succeeded")
    db.add(payment)
    await db.flush()

    comms = await create_commissions_for_payment(payment, db)
    assert comms == []


@pytest.mark.asyncio
async def test_l1_commission_created(db: AsyncSession):
    """L1 referrer gets a commission when their referral pays."""
    referrer = _make_user("referrer@example.com")
    db.add(referrer)
    await db.flush()

    payer = _make_user("payer@example.com", referred_by_id=referrer.id)
    db.add(payer)
    await db.flush()

    sub = Subscription(user_id=payer.id, plan_price_aed=95.0, status="active")
    db.add(sub)
    await db.flush()

    payment = Payment(subscription_id=sub.id, user_id=payer.id, amount_aed=95.0, status="succeeded")
    db.add(payment)
    await db.flush()

    comms = await create_commissions_for_payment(payment, db)
    assert len(comms) == 1
    assert comms[0].earner_id == referrer.id
    assert comms[0].level == 1
    assert comms[0].amount_aed == settings.l1_commission_aed


@pytest.mark.asyncio
async def test_l1_and_l2_commissions_created(db: AsyncSession):
    """Both L1 and L2 commissions are created in a two-tier chain."""
    grandparent = _make_user("grandparent@example.com")
    db.add(grandparent)
    await db.flush()

    parent = _make_user("parent@example.com", referred_by_id=grandparent.id)
    db.add(parent)
    await db.flush()

    payer = _make_user("child@example.com", referred_by_id=parent.id)
    db.add(payer)
    await db.flush()

    sub = Subscription(user_id=payer.id, plan_price_aed=95.0, status="active")
    db.add(sub)
    await db.flush()

    payment = Payment(subscription_id=sub.id, user_id=payer.id, amount_aed=95.0, status="succeeded")
    db.add(payment)
    await db.flush()

    comms = await create_commissions_for_payment(payment, db)
    assert len(comms) == 2

    l1 = next(c for c in comms if c.level == 1)
    l2 = next(c for c in comms if c.level == 2)

    assert l1.earner_id == parent.id
    assert l1.amount_aed == settings.l1_commission_aed
    assert l2.earner_id == grandparent.id
    assert l2.amount_aed == settings.l2_commission_aed


@pytest.mark.asyncio
async def test_commission_has_correct_payment_id(db: AsyncSession):
    """Commission payment_id links back to the triggering payment."""
    referrer = _make_user("ref2@example.com")
    db.add(referrer)
    await db.flush()

    payer = _make_user("pay2@example.com", referred_by_id=referrer.id)
    db.add(payer)
    await db.flush()

    sub = Subscription(user_id=payer.id, plan_price_aed=95.0, status="active")
    db.add(sub)
    await db.flush()

    payment = Payment(subscription_id=sub.id, user_id=payer.id, amount_aed=95.0, status="succeeded")
    db.add(payment)
    await db.flush()

    comms = await create_commissions_for_payment(payment, db)
    assert comms[0].payment_id == payment.id
