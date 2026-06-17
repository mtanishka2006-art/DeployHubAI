"""Disaster Recovery routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dr_agent import DisasterRecoveryAgent
from app.api.deps import get_current_user
from app.db.models import (
    Backup,
    DisasterRecoveryEvent,
    FailoverEvent,
    ReplicationStatus,
    User,
)
from app.db.session import get_db
from app.schemas.api import DREventOut, DRStatusResponse

router = APIRouter(prefix="/dr", tags=["disaster-recovery"])


@router.get("/status", response_model=DRStatusResponse)
def dr_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    backups = db.execute(select(Backup)).scalars().all()
    replication = db.execute(select(ReplicationStatus)).scalars().all()
    failovers = db.execute(select(FailoverEvent)).scalars().all()

    # Reuse the DR agent to compute the readiness score from live telemetry.
    agent = DisasterRecoveryAgent(db)
    assessment = agent.analyze(
        {
            "backups": [
                {
                    "system": b.system,
                    "status": b.status,
                    "last_backup": b.last_backup.isoformat(),
                    "rpo_minutes": b.rpo_minutes,
                }
                for b in backups
            ],
            "replication": [
                {
                    "source": r.source,
                    "target": r.target,
                    "status": r.status,
                    "lag_seconds": r.lag_seconds,
                }
                for r in replication
            ],
            "failovers": [
                {
                    "service": f.service,
                    "status": f.status,
                    "last_tested": f.last_tested.isoformat() if f.last_tested else None,
                }
                for f in failovers
            ],
        }
    )
    return DRStatusResponse(
        dr_score=assessment["dr_score"],
        readiness=assessment["readiness"],
        backups=backups,
        replication=replication,
        failovers=failovers,
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
