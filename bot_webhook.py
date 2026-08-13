"""Cloud Run HTTP entry point for the Telegram bot.

The request remains open until the command handler completes. This is required
for request-based, scale-to-zero compute because background work after returning
HTTP 200 is not reliable when an idle instance is throttled or removed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update

from bot import build_application


def create_api() -> FastAPI:
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required for webhook deployment.")
    telegram_app = build_application()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await telegram_app.initialize()
        await telegram_app.start()
        try:
            yield
        finally:
            await telegram_app.stop()
            await telegram_app.shutdown()

    api = FastAPI(
        title="PastiCuan Telegram Bot",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @api.get("/")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "pasticuan-telegram-webhook"}

    @api.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        supplied = x_telegram_bot_api_secret_token or ""
        if not secrets.compare_digest(supplied, webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret.")
        update = Update.de_json(await request.json(), telegram_app.bot)
        await telegram_app.process_update(update)
        return {"ok": True}

    return api


api = create_api()

