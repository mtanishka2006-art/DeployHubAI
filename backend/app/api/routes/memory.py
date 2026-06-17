"""Infrastructure Memory (RAG) routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.db.models import User
from app.memory.infrastructure_memory import get_memory
from app.schemas.api import MemoryResult, MemorySearchRequest, MemorySearchResponse

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/search", response_model=MemorySearchResponse)
def search_memory(
    payload: MemorySearchRequest, _: User = Depends(get_current_user)
):
    results = get_memory().search_similar_incidents(
        payload.query, k=payload.k, collection=payload.collection
    )
    return MemorySearchResponse(
        results=[MemoryResult(**r) for r in results]
    )


@router.get("/stats")
def memory_stats(_: User = Depends(get_current_user)):
    return get_memory().stats()
