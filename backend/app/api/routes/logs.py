"""Logs routes — a dedicated view of ingested log events.

The platform turns error logs into incidents and info logs into volume metrics,
but it also records every ingested event (including raw log lines) as a
ConnectorEvent. This endpoint surfaces the ``log`` events as a browsable,
filterable log stream for the dashboard's Logs section.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ConnectorEvent, User
from app.db.session import get_db
from app.schemas.api import LogEntryOut

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=List[LogEntryOut])
def list_logs(
    service: Optional[str] = Query(None, description="Filter by service"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    q: Optional[str] = Query(None, description="Substring search over the message"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(ConnectorEvent).where(ConnectorEvent.event_type == "log")
    if service:
        stmt = stmt.where(ConnectorEvent.service == service)
    if severity:
        stmt = stmt.where(ConnectorEvent.severity == severity)
    if q:
        stmt = stmt.where(ConnectorEvent.summary.ilike(f"%{q}%"))
    stmt = stmt.order_by(ConnectorEvent.timestamp.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/services", response_model=List[str])
def log_services(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    """Distinct services that have log entries — populates the filter dropdown."""
    rows = db.execute(
        select(ConnectorEvent.service)
        .where(ConnectorEvent.event_type == "log")
        .distinct()
        .order_by(ConnectorEvent.service)
    ).scalars().all()
    return [s for s in rows if s]
