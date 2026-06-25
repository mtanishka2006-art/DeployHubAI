"""App Connector Hub routes — connect/manage third-party integrations.

RBAC: SRE+ (and Admin) may connect/sync/disconnect apps; any authenticated user
may view the catalog, the connected apps, and their event feeds.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.crypto import encrypt_dict
from app.core.security import Role
from app.db.models import ConnectedApp, ConnectorEvent, User
from app.db.session import get_db
from app.ingestion.catalog import CONNECTOR_CATALOG, get_catalog_entry, is_supported
from app.ingestion.project_import import import_project_zip
from app.ingestion.registry import get_connector
from app.ingestion.sync import sync_connected_app
from app.schemas.api import (
    AvailableConnector,
    ConnectConnectorRequest,
    ConnectedAppOut,
    ConnectorEventOut,
    ImportResult,
    SyncResult,
)

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/available", response_model=List[AvailableConnector])
def available(_: User = Depends(get_current_user)):
    return CONNECTOR_CATALOG


@router.get("", response_model=List[ConnectedAppOut])
def list_connected(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    rows = db.execute(
        select(ConnectedApp).order_by(ConnectedApp.created_at.desc())
    ).scalars().all()
    return rows


@router.post("/connect", response_model=SyncResult)
def connect(
    payload: ConnectConnectorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.SRE)),
):
    if not is_supported(payload.app_type):
        raise HTTPException(status_code=400, detail=f"Unknown app_type '{payload.app_type}'")
    entry = get_catalog_entry(payload.app_type)

    # Git repository: clone + analyze commit history (handled specially).
    if payload.app_type == "git_repo":
        repo_url = payload.credentials.get("repo_url", "")
        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required")
        from app.ingestion.project_import import import_git_url

        try:
            result = import_git_url(
                db, repo_url, payload.credentials.get("token", ""),
                user.username, replace=payload.replace,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return SyncResult(
            ok=True, message=result["message"],
            events_ingested=result["events_ingested"],
            app=ConnectedAppOut.model_validate(result["app"]),
        )

    # Validate required credential fields are present.
    missing = [
        f["name"]
        for f in entry["fields"]
        if f.get("required") and not payload.credentials.get(f["name"])
    ]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing required fields: {', '.join(missing)}"
        )

    # Test the connection before saving (if live is supported).
    if entry["live_supported"]:
        connector = get_connector(entry["source"], dict(payload.credentials))
        ok, message = connector.test_connection()
        if not ok:
            raise HTTPException(status_code=400, detail=f"Connection failed: {message}")
    else:
        message = "saved (live sync not supported for this integration yet)"

    # Replace mode: wipe prior data/sources so the dashboards reflect ONLY this
    # source (any connector — keeps different sources from overlapping). Logs
    # are preserved (reset_platform_data no longer clears connector events).
    if payload.replace:
        from app.seed.seed_data import reset_platform_data

        reset_platform_data(db)

    app = ConnectedApp(
        name=payload.name or entry["label"],
        app_type=payload.app_type,
        credentials_encrypted=encrypt_dict(payload.credentials),
        status="connected",
        polling_interval_seconds=payload.polling_interval_seconds or 60,
        created_by=user.username,
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    # Kick off an immediate first sync so data shows up right away.
    count = 0
    if entry["live_supported"]:
        count, _ok, message = sync_connected_app(db, app)
        db.refresh(app)

    return SyncResult(
        ok=True,
        message=message,
        events_ingested=count,
        app=ConnectedAppOut.model_validate(app),
    )


@router.post("/import", response_model=ImportResult)
async def import_project(
    file: UploadFile = File(...),
    replace: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.SRE)),
):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 200 MB)")
    try:
        result = import_project_zip(db, data, user.username, replace=replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ImportResult(
        ok=result["ok"],
        message=result["message"],
        app_name=result["app_name"],
        services=result["services"],
        commits=result["commits"],
        deployments=result["deployments"],
        incidents=result["incidents"],
        pipelines=result.get("pipelines", 0),
        events_ingested=result["events_ingested"],
        app=ConnectedAppOut.model_validate(result["app"]),
    )


@router.post("/{app_id}/sync", response_model=SyncResult)
def sync_now(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.SRE)),
):
    app = db.get(ConnectedApp, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Connector not found")
    app_type = app.app_type
    count, ok, message = sync_connected_app(db, app)
    # A git_repo full-refresh replaces the app row; fetch a fresh handle.
    fresh = db.get(ConnectedApp, app_id)
    if fresh is None and app_type == "git_repo":
        fresh = db.execute(
            select(ConnectedApp)
            .where(ConnectedApp.app_type == "git_repo")
            .order_by(ConnectedApp.created_at.desc())
        ).scalars().first()
    return SyncResult(
        ok=ok, message=message, events_ingested=count,
        app=ConnectedAppOut.model_validate(fresh) if fresh else None,
    )


@router.get("/{app_id}/events", response_model=List[ConnectorEventOut])
def connector_events(
    app_id: int,
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.get(ConnectedApp, app_id):
        raise HTTPException(status_code=404, detail="Connector not found")
    rows = db.execute(
        select(ConnectorEvent)
        .where(ConnectorEvent.connected_app_id == app_id)
        .order_by(ConnectorEvent.timestamp.desc())
        .limit(limit)
    ).scalars().all()
    return rows


@router.delete("/{app_id}", status_code=204)
def disconnect(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.SRE)),
):
    app = db.get(ConnectedApp, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Connector not found")
    # Deleting the app cascades its ConnectorEvents + Pipelines.
    db.delete(app)
    db.commit()

    # Imported projects (zip / git) are ingested in 'replace' mode, so all the
    # operational data (metrics, deployments, incidents, DR) belongs solely to
    # that app — but it isn't FK-linked back to it. Once no connected apps
    # remain, clear that now-orphaned data and restore the zero-config demo
    # seed, so the dashboard stops showing the disconnected app's telemetry.
    remaining = db.scalar(select(func.count(ConnectedApp.id)))
    if not remaining:
        from app.seed.seed_data import reset_platform_data, run_all

        reset_platform_data(db)
        run_all(db)
    return None
