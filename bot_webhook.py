"""Cloud Run HTTP entry point for the Telegram bot.

The request remains open until the command handler completes. This is required
for request-based, scale-to-zero compute because background work after returning
HTTP 200 is not reliable when an idle instance is throttled or removed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections import OrderedDict
import asyncio
import os
import secrets

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update

from bot import build_application
from analysis.snapshots import get_research_snapshot
from analysis.scan_snapshots import get_scan_snapshot


def create_api() -> FastAPI:
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required for webhook deployment.")
    telegram_app = build_application()
    processed_updates: OrderedDict[int, None] = OrderedDict()
    update_lock = asyncio.Lock()

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

    @api.get("/ready")
    async def readiness() -> dict[str, str]:
        snapshot = get_research_snapshot()
        scan = (await asyncio.to_thread(get_scan_snapshot)).to_bundle()
        return {
            "status": "degraded" if (
                snapshot.snapshot_id == "bundled-empty-shadow" or scan.mode != "PRIMARY"
            ) else "ok",
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_effective_at": snapshot.effective_at,
            "model_status": snapshot.model_status,
            "scan_mode": scan.mode,
            "scan_snapshot_id": scan.snapshot_id or "unavailable",
            "scan_session_date": scan.session_date or "unavailable",
        }

    @api.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        supplied = x_telegram_bot_api_secret_token or ""
        if not secrets.compare_digest(supplied, webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret.")
        update = Update.de_json(await request.json(), telegram_app.bot)
        if update.update_id is not None:
            async with update_lock:
                if update.update_id in processed_updates:
                    return {"ok": True}
                processed_updates[update.update_id] = None
                processed_updates.move_to_end(update.update_id)
                while len(processed_updates) > 500:
                    processed_updates.popitem(last=False)
        try:
            await telegram_app.process_update(update)
        except Exception:
            if update.update_id is not None:
                async with update_lock:
                    processed_updates.pop(update.update_id, None)
            raise
        return {"ok": True}

    return api


api = create_api()
