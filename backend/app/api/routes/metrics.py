"""Metrics routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, visible_owner
from app.db.models import InfrastructureMetric, User
from app.db.session import get_db
from app.schemas.api import MetricOut

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=List[MetricOut])
def list_metrics(
    service: Optional[str] = None,
    metric_name: Optional[str] = None,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(InfrastructureMetric)
    owner = visible_owner(user)
    if owner is not None:
        q = q.where(InfrastructureMetric.owner == owner)
    if service:
        q = q.where(InfrastructureMetric.service == service)
    if metric_name:
        q = q.where(InfrastructureMetric.metric_name == metric_name)
    q = q.order_by(InfrastructureMetric.timestamp.desc()).limit(limit)
    return db.execute(q).scalars().all()
