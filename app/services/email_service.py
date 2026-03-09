from __future__ import annotations
import logging
from app.clients.ses import ses_client
from app.templates.email_templates import (
    welcome_email, payout_confirmation_email,
    subscription_cancelled_email, subscription_expired_email,
)

logger = logging.getLogger(__name__)


async def send_welcome_email(email: str, full_name: str, referral_code: str) -> None:
    try:
        subject, html = welcome_email(full_name, referral_code)
        await ses_client.send_email(to_email=email, subject=subject, html_body=html)
    except Exception as e:
        logger.error("Failed to send welcome email to %s: %s", email, e)


async def send_payout_confirmation(email: str, full_name: str, amount_aed: float, iban: str, commission_count: int) -> None:
    try:
        subject, html = payout_confirmation_email(full_name, amount_aed, iban[-4:] if iban else "****", commission_count)
        await ses_client.send_email(to_email=email, subject=subject, html_body=html)
    except Exception as e:
        logger.error("Failed to send payout email to %s: %s", email, e)


async def send_subscription_cancelled(email: str, full_name: str) -> None:
    try:
        subject, html = subscription_cancelled_email(full_name)
        await ses_client.send_email(to_email=email, subject=subject, html_body=html)
    except Exception as e:
        logger.error("Failed to send cancellation email to %s: %s", email, e)


async def send_subscription_expired(email: str, full_name: str) -> None:
    try:
        subject, html = subscription_expired_email(full_name)
        await ses_client.send_email(to_email=email, subject=subject, html_body=html)
    except Exception as e:
        logger.error("Failed to send expiry email to %s: %s", email, e)
