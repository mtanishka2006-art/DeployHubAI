"""Disaster Recovery routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dr_agent import compute_dr_status
from app.api.deps import get_current_user
from app.db.models import DisasterRecoveryEvent, User
from app.db.session import get_db
from app.schemas.api import DREventOut, DRStatusResponse

router = APIRouter(prefix="/dr", tags=["disaster-recovery"])


@router.get("/status", response_model=DRStatusResponse)
def dr_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    # Single source of truth shared with the /overview dashboard.
    dr = compute_dr_status(db)
    return DRStatusResponse(
        dr_score=dr["dr_score"],
        readiness=dr["readiness"],
        backups=dr["backups"],
        replication=dr["replication"],
        failovers=dr["failovers"],
    )


@router.get("/events", response_model=List[DREventOut])
def dr_events(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = (
        select(DisasterRecoveryEvent)
        .order_by(DisasterRecoveryEvent.timestamp.desc())
        .limit(limit)
    )
    return db.execute(q).scalars().all()
