"""Mission Control routes — run the orchestrated agent workflow."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.security import Role
from app.db.models import MissionControlReport, User
from app.db.session import get_db
from app.mission_control.orchestrator import MissionControl
from app.schemas.api import MissionControlReportOut, MissionControlRequest

router = APIRouter(prefix="/mission-control", tags=["mission-control"])


@router.post("/run", response_model=MissionControlReportOut)
def run_mission_control(
    payload: MissionControlRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.SRE)),
):
    mc = MissionControl(db)
    report = mc.run(payload.model_dump())
    return MissionControlReportOut(**report)


@router.get("/reports", response_model=List[MissionControlReportOut])
def list_reports(
    limit: int = Query(20, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.VIEWER)),
):
    rows = db.execute(
        select(MissionControlReport)
        .order_by(MissionControlReport.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        MissionControlReportOut(
            incident_id=r.incident_id,
            severity=(r.raw_outputs or {}).get("severity", "medium"),
            system_health=r.system_health,
            root_cause=r.root_cause,
            dr_readiness=r.dr_readiness,
            similar_incidents=r.similar_incidents or [],
            recommended_actions=r.recommended_actions or [],
            executive_summary=r.executive_summary,
            monitoring=(r.raw_outputs or {}).get("monitoring", {}),
            rca=(r.raw_outputs or {}).get("rca", {}),
            dr=(r.raw_outputs or {}).get("dr", {}),
            recovery=(r.raw_outputs or {}).get("recovery", {}),
            created_at=r.created_at,
        )
        for r in rows
    ]
