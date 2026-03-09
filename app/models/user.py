from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    referral_code: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    referred_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    mamopay_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payout_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    payout_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    referrer: Mapped[User | None] = relationship("User", remote_side="User.id", foreign_keys=[referred_by_id])
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="user", uselist=False)
    commissions_earned: Mapped[list["Commission"]] = relationship("Commission", back_populates="earner", foreign_keys="Commission.earner_id")
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="user")
