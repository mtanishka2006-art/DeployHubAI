"""Disaster Recovery routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dr_agent import compute_dr_status
from app.api.deps import get_current_user, visible_owner
from app.db.models import DisasterRecoveryEvent, User
from app.db.session import get_db
from app.schemas.api import DREventOut, DRStatusResponse

router = APIRouter(prefix="/dr", tags=["disaster-recovery"])


@router.get("/status", response_model=DRStatusResponse)
def dr_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Single source of truth shared with the /overview dashboard.
    dr = compute_dr_status(db, owner=visible_owner(user))
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
    user: User = Depends(get_current_user),
):
    q = (
        select(DisasterRecoveryEvent)
        .order_by(DisasterRecoveryEvent.timestamp.desc())
        .limit(limit)
    )
    owner = visible_owner(user)
    if owner is not None:
        q = q.where(DisasterRecoveryEvent.owner == owner)
    return db.execute(q).scalars().all()
