"""Disaster Recovery routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dr_agent import DisasterRecoveryAgent, website_dr_from_metrics
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


# Connectors that emit REAL backup/replication/failover telemetry (true RPO/RTO
# signals). When one of these is connected, its DR rows are authoritative.
_DR_SIGNAL_APP_TYPES = ["gcp"]


def _traditional_assessment(db, backups, replication, failovers):
    agent = DisasterRecoveryAgent(db)
    return agent.analyze(
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
                    "auto_failover": (f.meta or {}).get("auto_failover"),
                }
                for f in failovers
            ],
        }
    )


@router.get("/status", response_model=DRStatusResponse)
def dr_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from sqlalchemy import func

    from app.db.models import ConnectedApp

    backups = db.execute(select(Backup)).scalars().all()
    replication = db.execute(select(ReplicationStatus)).scalars().all()
    failovers = db.execute(select(FailoverEvent)).scalars().all()
    have_dr_rows = bool(backups or replication or failovers)

    # Tier 1 — a connected cloud source emitting real backup/replication/failover
    # telemetry (e.g. GCP Cloud SQL) gives a genuine RPO/RTO-based score, which
    # takes precedence over the availability-proxy below.
    has_dr_connector = db.scalar(
        select(func.count(ConnectedApp.id)).where(
            ConnectedApp.app_type.in_(_DR_SIGNAL_APP_TYPES)
        )
    )
    if has_dr_connector and have_dr_rows:
        assessment = _traditional_assessment(db, backups, replication, failovers)
        return DRStatusResponse(
            dr_score=assessment["dr_score"],
            readiness=assessment["readiness"],
            backups=backups,
            replication=replication,
            failovers=failovers,
        )

    # Tier 2 — a live website's REAL measured resilience (TLS, DNS redundancy,
    # uptime). An availability proxy, but real measurements; preferred over any
    # leftover demo/seed DR rows that may still be present in merge mode.
    web = website_dr_from_metrics(db)
    if web is not None:
        return DRStatusResponse(
            dr_score=web["dr_score"],
            readiness=web["readiness"],
            backups=[],
            replication=[],
            failovers=[],
        )

    # Tier 3 — DR rows from a dedicated DR connector / seed (no website, no
    # cloud DR connector).
    if have_dr_rows:
        assessment = _traditional_assessment(db, backups, replication, failovers)
        return DRStatusResponse(
            dr_score=assessment["dr_score"],
            readiness=assessment["readiness"],
            backups=backups,
            replication=replication,
            failovers=failovers,
        )

    # Tier 4 — nothing measurable; report honestly as N/A.
    return DRStatusResponse(
        dr_score=None,
        readiness="not_measured",
        backups=[],
        replication=[],
        failovers=[],
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
