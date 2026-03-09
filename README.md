# Tutorii Backend API

AI-powered tutoring platform with subscription billing, multi-level referral commissions, and automated weekly payouts.

## Stack
- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL + SQLAlchemy (async)
- **Cache/Broker:** Redis
- **Task Queue:** Celery + Celery Beat
- **Payments:** MamoPay API
- **AI Chat:** Anthropic Claude API

## Business Rules
| Parameter | Value |
|---|---|
| Subscription | AED 95/month |
| L1 Referral Commission | 40% (AED 38) |
| L2 Referral Commission | 5% (AED 4.75) |
| Payout Schedule | Weekly, every Tuesday |
| Minimum Payout | AED 50 |
| Payment Provider | MamoPay |

## Project Structure
```
tutorii/
├── app/
│   ├── api/routes/       # FastAPI route modules
│   ├── clients/          # External API clients (MamoPay, Claude)
│   ├── core/             # Config, security, dependencies
│   ├── db/               # Database engine & session
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic layer
│   └── tasks/            # Celery async tasks
├── alembic/              # DB migrations
├── main.py               # App entrypoint
├── celery_app.py         # Celery entrypoint
├── requirements.txt
└── .env.example
```

## Quick Start
```bash
cp .env.example .env       # fill in values
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
celery -A celery_app worker --beat -l info
```
