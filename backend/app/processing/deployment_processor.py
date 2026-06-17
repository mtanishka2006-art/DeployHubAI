"""DeploymentProcessor — persists deployment events; records failures to memory."""
from __future__ import annotations

from typing import Any, Dict

from app.db.models import Deployment, DeploymentStatus
from app.memory.infrastructure_memory import get_memory
from app.processing.base import BaseProcessor, json_safe
from app.schemas.events import UnifiedEvent


class DeploymentProcessor(BaseProcessor):
    name = "deployment"

    def extract_features(self, event: UnifiedEvent) -> Dict[str, Any]:
        md = dict(event.metadata)
        md["status"] = md.get("status", DeploymentStatus.SUCCESS.value)
        md["failed"] = md["status"] in {
            DeploymentStatus.FAILED.value,
            DeploymentStatus.ROLLED_BACK.value,
        }
        return md

    def persist(self, event: UnifiedEvent, features: Dict[str, Any]):
        dep = Deployment(
            source=event.source,
            service=event.service,
            environment=event.environment,
            version=str(features.get("version", "")),
            commit=str(features.get("commit", "")),
            actor=str(features.get("actor", "")),
            status=features["status"],
            duration_seconds=int(features.get("duration_seconds", 0) or 0),
            timestamp=event.timestamp,
            meta=json_safe(
                {
                    k: v
                    for k, v in features.items()
                    if k
                    not in {"version", "commit", "actor", "status", "duration_seconds"}
                }
            ),
        )
        self.db.add(dep)
        self.db.flush()
        return dep

    def embed(self, event: UnifiedEvent, persisted: Deployment) -> None:
        if event.metadata.get("failed"):
            get_memory().store_deployment_failure(
                deployment_id=str(persisted.id),
                service=persisted.service,
                summary=f"{persisted.status} deploy v{persisted.version}",
                root_cause=event.metadata.get("message", ""),
            )
