from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    # ── App ──
    APP_NAME: str = "Tutorii"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me"
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://tutorii:tutorii@localhost:5432/tutorii"
    DATABASE_ECHO: bool = False

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Auth ──
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"

    # ── MamoPay ──
    MAMOPAY_API_KEY: str = ""
    MAMOPAY_BASE_URL: str = "https://business.mamopay.com/manage_api/v1"
    MAMOPAY_WEBHOOK_SECRET: str = ""
    MAMOPAY_SUBSCRIPTION_LINK: str = "https://business.mamopay.com/pay/galcofzellc-4b20ab"

    # ── Anthropic ──
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MAX_TOKENS: int = 4096

    # ── Subscription & Commissions ──
    SUBSCRIPTION_PRICE_AED: float = 95.00
    L1_COMMISSION_RATE: float = 0.40
    L2_COMMISSION_RATE: float = 0.05
    MINIMUM_PAYOUT_AED: float = 50.00

    # ── Celery ──
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Frontend ──
    FRONTEND_URL: str = "https://www.tutorii.com"

    # ── AWS SES ──
    AWS_SES_REGION: str = "me-south-1"
    AWS_SES_ACCESS_KEY_ID: str = ""
    AWS_SES_SECRET_ACCESS_KEY: str = ""
    FROM_EMAIL: str = "hello@tutorii.com"
    FROM_NAME: str = "Tutorii"

    # ── CORS ──
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @property
    def l1_commission_aed(self) -> float:
        return round(self.SUBSCRIPTION_PRICE_AED * self.L1_COMMISSION_RATE, 2)

    @property
    def l2_commission_aed(self) -> float:
        return round(self.SUBSCRIPTION_PRICE_AED * self.L2_COMMISSION_RATE, 2)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
