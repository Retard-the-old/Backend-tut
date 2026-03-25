from fastapi import APIRouter
from app.api.routes import auth, users, subscriptions, courses, chat, payouts, admin
from app.api.routes import webhooks

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(subscriptions.router)
api_router.include_router(courses.router)
api_router.include_router(chat.router)
api_router.include_router(payouts.router)
api_router.include_router(admin.router)
api_router.include_router(webhooks.router)
