"""Background polling engine for the App Connector Hub.

An AsyncIO task wakes every ``CONNECTOR_POLL_TICK_SECONDS``, finds connected
apps whose ``polling_interval_seconds`` has elapsed, and syncs them. Blocking
connector I/O (httpx/boto3) runs in worker threads so the event loop stays free.
"""
from __future__ import annotations

import asyncio
from datetime import timezone
from typing import List, Optional

from app.config import settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import ConnectedApp
from app.db.session import SessionLocal
from app.ingestion.sync import sync_connected_app

logger = get_logger("ingestion.poller")

_task: Optional[asyncio.Task] = None


def _due_app_ids() -> List[int]:
    db = SessionLocal()
    try:
        apps = (
            db.query(ConnectedApp)
            .filter(ConnectedApp.status.in_(["connected", "pending"]))
            .all()
        )
        now = utcnow()
        due: List[int] = []
        for a in apps:
            # interval <= 0 or import-only connectors are never auto-polled.
            if a.app_type == "project_import" or (a.polling_interval_seconds or 0) <= 0:
                continue
            interval = a.polling_interval_seconds or settings.CONNECTOR_DEFAULT_INTERVAL_SECONDS
            last = a.last_synced_at
            if last is None:
                due.append(a.id)
                continue
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() >= interval:
                due.append(a.id)
        return due
    finally:
        db.close()


def _sync_one(app_id: int) -> None:
    db = SessionLocal()
    try:
        app = db.get(ConnectedApp, app_id)
        if app is not None:
            sync_connected_app(db, app)
    finally:
        db.close()


async def _tick() -> None:
    due = await asyncio.to_thread(_due_app_ids)
    for app_id in due:
        await asyncio.to_thread(_sync_one, app_id)


async def _loop() -> None:
    logger.info(
        "connector poller started (tick=%ss)", settings.CONNECTOR_POLL_TICK_SECONDS
    )
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("poller tick failed")
        await asyncio.sleep(settings.CONNECTOR_POLL_TICK_SECONDS)


async def start_poller() -> None:
    global _task
    if not settings.CONNECTOR_POLLING_ENABLED:
        logger.info("connector polling disabled by config")
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_poller() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _task = None
