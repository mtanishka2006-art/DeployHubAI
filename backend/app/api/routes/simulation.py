"""Disaster Simulation routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_role
from app.core.security import Role
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import SimulationRequest, SimulationResponse
from app.simulation.engine import SimulationEngine, valid_targets
from app.simulation.scenarios import SCENARIOS
from app.simulation.topology import default_topology
from sqlalchemy.orm import Session
from fastapi import Depends as _Depends

router = APIRouter(prefix="/simulation", tags=["simulation"])

# The topology is static config, so build it once for listing valid targets.
_TOPOLOGY = default_topology()


@router.get("/scenarios")
def list_scenarios(_: User = Depends(require_role(Role.VIEWER))):
    out = []
    for s in SCENARIOS.values():
        param, targets = valid_targets(s.key, _TOPOLOGY)
        out.append(
            {
                "key": s.key,
                "label": s.label,
                "description": s.description,
                "severity": s.severity,
                "target_param": param,  # "region" or "target"
                "targets": targets,     # the only values the user may pick
            }
        )
    return out


@router.post("/run", response_model=SimulationResponse)
def run_simulation(
    payload: SimulationRequest,
    db: Session = _Depends(get_db),
    _: User = Depends(require_role(Role.DEVOPS)),
):
    if payload.scenario_type not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario_type. Valid: {', '.join(SCENARIOS)}",
        )
    engine = SimulationEngine(db)
    try:
        report = engine.run(
            scenario_type=payload.scenario_type,
            target=payload.target,
            region=payload.region,
            params=payload.params,
        )
    except ValueError as exc:
        # Unknown/invalid target -> clear 400 with valid options.
        raise HTTPException(status_code=400, detail=str(exc))
    return SimulationResponse(**report)
