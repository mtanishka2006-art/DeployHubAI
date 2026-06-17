"""Typed state passed between Mission Control workflow nodes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class MissionState(TypedDict, total=False):
    # Inputs
    incident_id: Optional[int]
    service: str
    environment: str
    severity: str
    query: str
    context: Dict[str, Any]

    # Agent outputs
    monitoring: Dict[str, Any]
    rca: Dict[str, Any]
    dr: Dict[str, Any]
    similar_incidents: List[Dict[str, Any]]
    recovery: Dict[str, Any]

    # Final
    report: Dict[str, Any]
