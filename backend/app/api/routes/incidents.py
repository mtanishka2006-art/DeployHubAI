"""Incident routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.security import Role
from app.db.models import Incident, User
from app.db.session import get_db
from app.memory.infrastructure_memory import get_memory
from app.schemas.api import IncidentCreate, IncidentDetail, IncidentOut

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=List[IncidentOut])
def list_incidents(
    status: Optional[str] = None,
    service: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(Incident)
    if status:
        q = q.where(Incident.status == status)
    if service:
        q = q.where(Incident.service == service)
    q = q.order_by(Incident.detected_at.desc()).limit(limit)
    return db.execute(q).scalars().all()


@router.post("", response_model=IncidentOut, status_code=201)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.DEVOPS)),
):
    incident = Incident(
        title=payload.title,
        description=payload.description,
        service=payload.service,
        environment=payload.environment,
        severity=payload.severity,
        source=payload.source,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    similar = get_memory().search_similar_incidents(
        incident.root_cause or incident.title, k=5
    )
    detail = IncidentDetail.model_validate(incident)
    detail.recommended_actions = incident.recovery_actions  # type: ignore[assignment]
    detail.similar_incidents = similar
    return detail
