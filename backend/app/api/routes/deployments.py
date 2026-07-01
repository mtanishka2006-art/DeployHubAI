"""Deployment routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, visible_owner
from app.db.models import Deployment, User
from app.db.session import get_db
from app.schemas.api import DeploymentOut

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get("", response_model=List[DeploymentOut])
def list_deployments(
    service: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Deployment)
    owner = visible_owner(user)
    if owner is not None:
        q = q.where(Deployment.owner == owner)
    if service:
        q = q.where(Deployment.service == service)
    if status:
        q = q.where(Deployment.status == status)
    q = q.order_by(Deployment.timestamp.desc()).limit(limit)
    return db.execute(q).scalars().all()
