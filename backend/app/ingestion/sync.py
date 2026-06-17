"""Run a single ConnectedApp's connector and ingest its events.

Shared by the manual-sync API endpoint and the background poller.
"""
from __future__ import annotations

from typing import Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.crypto import decrypt_dict
from app.db.models import ConnectedApp
from app.ingestion.catalog import get_catalog_entry
from app.ingestion.pipeline import ingest_events
from app.ingestion.registry import get_connector

logger = get_logger("ingestion.sync")


def sync_connected_app(db: Session, app: ConnectedApp) -> Tuple[int, bool, str]:
    """Fetch + ingest for one connected app. Updates its status/error/counters.
    Returns (events_ingested, ok, message). Never raises."""
    if app.app_type == "project_import":
        # Imported projects are a one-shot snapshot; re-upload to refresh.
        return 0, True, "import-only connector — re-upload the .zip to refresh"
    if app.app_type == "git_repo":
        # Re-clone the repo for a fresh snapshot (full replace).
        from app.core.crypto import decrypt_dict
        from app.ingestion.project_import import import_git_url

        creds = decrypt_dict(app.credentials_encrypted)
        try:
            res = import_git_url(
                db, creds.get("repo_url", ""), creds.get("token", ""),
                app.created_by, replace=True,
            )
            return res["events_ingested"], True, res["message"]
        except Exception as exc:  # noqa: BLE001
            return 0, False, str(exc)
    try:
        entry = get_catalog_entry(app.app_type)
        creds = decrypt_dict(app.credentials_encrypted)
        connector = get_connector(entry["source"], creds)
        events = connector.collect()
        count = ingest_events(db, events, connected_app=app)
        app.status = "connected"
        app.last_error = ""
        db.commit()
        logger.info("synced %s (#%s): %d events", app.app_type, app.id, count)
        return count, True, f"ingested {count} events"
    except Exception as exc:  # noqa: BLE001 - poller/route must never crash
        logger.exception("sync failed for app #%s", app.id)
        db.rollback()
        app.status = "error"
        app.last_error = str(exc)[:500]
        db.commit()
        return 0, False, str(exc)
