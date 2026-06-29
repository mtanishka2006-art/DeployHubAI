"""Connector registry + ingestion service.

Resolves a connector by its source name and provides a single entry point to
run one or all connectors over a batch of config (e.g. for scheduled polling).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from app.core.logging import get_logger
from app.ingestion.aws import AWSConnector
from app.ingestion.azure import AzureConnector
from app.ingestion.base import BaseConnector
from app.ingestion.datadog import DatadogConnector
from app.ingestion.disaster_recovery import DisasterRecoveryConnector
from app.ingestion.gcp import GCPConnector
from app.ingestion.github_actions import GithubActionsConnector
from app.ingestion.jenkins import JenkinsConnector
from app.ingestion.jira import JiraConnector
from app.ingestion.kubernetes import KubernetesConnector
from app.ingestion.logs import LogConnector
from app.ingestion.pagerduty import PagerDutyConnector
from app.ingestion.website import WebsiteConnector

logger = get_logger(__name__)

CONNECTOR_REGISTRY: Dict[str, Type[BaseConnector]] = {
    "jenkins": JenkinsConnector,
    "github_actions": GithubActionsConnector,
    "aws": AWSConnector,
    "gcp": GCPConnector,
    "azure": AzureConnector,
    "kubernetes": KubernetesConnector,
    "logs": LogConnector,
    "disaster_recovery": DisasterRecoveryConnector,
    "jira": JiraConnector,
    "pagerduty": PagerDutyConnector,
    "datadog": DatadogConnector,
    "website": WebsiteConnector,
}


def get_connector(
    source: str, config: Optional[Dict[str, Any]] = None
) -> BaseConnector:
    if source not in CONNECTOR_REGISTRY:
        raise KeyError(f"unknown connector source: {source!r}")
    return CONNECTOR_REGISTRY[source](config=config)


class IngestionService:
    """Runs connectors and reports how many events each published."""

    def run_one(self, source: str, config: Optional[Dict[str, Any]] = None) -> int:
        return get_connector(source, config).run()

    def run_all(self, configs: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
        results: Dict[str, int] = {}
        for source, cfg in configs.items():
            try:
                results[source] = self.run_one(source, cfg)
            except Exception:  # noqa: BLE001
                logger.exception("connector %s failed", source)
                results[source] = -1
        return results

    @staticmethod
    def available_sources() -> List[str]:
        return sorted(CONNECTOR_REGISTRY)
