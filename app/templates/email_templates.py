from app.templates.base_email import wrap


def welcome_email(full_name: str, referral_code: str) -> tuple[str, str]:
    subject = "Welcome to Tutorii!"
    content = f"""
    <h2>Hey {full_name}, welcome aboard!</h2>
    <p>Your Tutorii account is ready. Subscribe to unlock all courses and your personal AI tutor.</p>
    <div class="hl">
      <strong>Your referral code:</strong>
      <span style="font-size:20px;font-weight:bold;color:#1B4F72">{referral_code}</span><br>
      <span style="font-size:13px;color:#5D6D7E">Earn AED 38 per direct referral + AED 4.75 from their referrals.</span>
    </div>"""
    return subject, wrap(content, f"Welcome to Tutorii, {full_name}!")


def payout_confirmation_email(full_name: str, amount_aed: float, iban_last4: str, commission_count: int) -> tuple[str, str]:
    subject = f"Payout Sent: AED {amount_aed:.2f}"
    content = f"""
    <h2>Your payout is on its way!</h2>
    <p>Hi {full_name},</p>
    <div class="hl">
      <strong>Amount:</strong> AED {amount_aed:.2f}<br>
      <strong>Account ending in:</strong> ...{iban_last4}<br>
      <strong>Commissions included:</strong> {commission_count}
    </div>
    <p>Bank transfers typically arrive within 1&ndash;2 business days.</p>"""
    return subject, wrap(content, f"AED {amount_aed:.2f} payout sent")


def subscription_cancelled_email(full_name: str) -> tuple[str, str]:
    subject = "Tutorii Subscription Cancelled"
    content = f"""
    <h2>Subscription cancelled</h2>
    <p>Hi {full_name}, your subscription has been cancelled. You still have access until the end of your current billing period.</p>
    <p>Changed your mind? Resubscribe any time from your dashboard.</p>"""
    return subject, wrap(content, "Your Tutorii subscription has been cancelled")


def subscription_expired_email(full_name: str) -> tuple[str, str]:
    subject = "Tutorii Subscription Expired"
    content = f"""
    <h2>Your subscription has expired</h2>
    <p>Hi {full_name}, your access to courses and the AI tutor is now paused.</p>
    <p>Resubscribe from your dashboard to pick up where you left off &mdash; your progress is saved.</p>"""
    return subject, wrap(content, "Your Tutorii access has expired")
