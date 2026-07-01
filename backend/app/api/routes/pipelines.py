"""Pipelines route — list CI/CD pipelines detected from connected sources."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, visible_owner
from app.db.models import ConnectedApp, Pipeline, User
from app.db.session import get_db
from app.schemas.api import PipelineOut

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=List[PipelineOut])
def list_pipelines(
    provider: Optional[str] = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = (
        select(Pipeline, ConnectedApp.name)
        .join(ConnectedApp, ConnectedApp.id == Pipeline.connected_app_id)
        .order_by(Pipeline.provider, Pipeline.name)
        .limit(limit)
    )
    owner = visible_owner(user)
    if owner is not None:
        q = q.where(Pipeline.owner == owner)
    if provider:
        q = q.where(Pipeline.provider == provider)
    rows = db.execute(q).all()
    return [
        PipelineOut(
            id=p.id,
            provider=p.provider,
            name=p.name,
            file_path=p.file_path,
            triggers=p.triggers or [],
            stages=p.stages or [],
            status=p.status,
            app_name=app_name,
        )
        for (p, app_name) in rows
    ]
