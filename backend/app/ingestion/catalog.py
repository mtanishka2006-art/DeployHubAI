"""Catalog of supported integrations for the App Connector Hub.

Drives the `/api/connectors/available` endpoint and the frontend connect forms:
each entry declares the connector source it maps to and the credential fields
the user must provide.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _field(name: str, label: str, secret: bool = False, placeholder: str = "",
           required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "password" if secret else "text",
        "placeholder": placeholder,
        "required": required,
    }


CONNECTOR_CATALOG: List[Dict[str, Any]] = [
    {
        "app_type": "github_actions",
        "label": "GitHub Actions",
        "description": "Pull workflow runs as deployment/pipeline events. "
        "Public repos need no token.",
        "icon": "github",
        "source": "github_actions",
        "live_supported": True,
        "fields": [
            _field("owner", "Repository owner / org", placeholder="my-org"),
            _field("repo", "Repository name", placeholder="my-service"),
            _field("token", "Personal access token (private repos only)",
                   secret=True, placeholder="ghp_...", required=False),
        ],
    },
    {
        "app_type": "aws",
        "label": "AWS CloudWatch",
        "description": "Ingest CloudWatch alarms as incidents and metrics.",
        "icon": "aws",
        "source": "aws",
        "live_supported": True,  # requires boto3 installed
        "fields": [
            _field("access_key_id", "Access key ID", secret=True),
            _field("secret_access_key", "Secret access key", secret=True),
            _field("region", "Region", placeholder="us-east-1"),
        ],
    },
    {
        "app_type": "gcp",
        "label": "GCP Cloud Monitoring",
        "description": "Ingest Google Cloud Monitoring metrics (and alert "
        "policies) for a GCP project.",
        "icon": "gcp",
        "source": "gcp",
        "live_supported": True,  # requires google-cloud-monitoring installed
        "fields": [
            _field("project_id", "Project ID", placeholder="my-gcp-project"),
            _field("credentials_json", "Service account key (JSON)", secret=True,
                   placeholder='{"type":"service_account",...}', required=False),
            _field("metric_type", "Metric type", required=False,
                   placeholder="compute.googleapis.com/instance/cpu/utilization"),
        ],
    },
    {
        "app_type": "datadog",
        "label": "Datadog",
        "description": "Ingest Datadog events and monitor alerts.",
        "icon": "datadog",
        "source": "datadog",
        "live_supported": True,
        "fields": [
            _field("api_key", "API key", secret=True),
            _field("app_key", "Application key", secret=True),
            _field("site", "Site", placeholder="datadoghq.com", required=False),
        ],
    },
    {
        "app_type": "website",
        "label": "Live Website (URL)",
        "description": "Monitor a live website by URL — real uptime, response "
        "time and HTTP status, re-probed on a schedule.",
        "icon": "website",
        "source": "website",
        "live_supported": True,
        "fields": [
            _field("url", "Website URL", placeholder="https://example.com"),
        ],
    },
    {
        "app_type": "git_repo",
        "label": "Git Repository (URL)",
        "description": "Connect any git repo URL — derives services, deployments "
        "and incidents from its commit history.",
        "icon": "git",
        "source": "",
        "live_supported": True,
        "fields": [
            _field("repo_url", "Repository URL",
                   placeholder="https://github.com/owner/repo.git"),
            _field("token", "Access token (private repos only)", secret=True,
                   required=False),
        ],
    },
    {
        "app_type": "project_import",
        "label": "Import Project (.zip)",
        "description": "Upload an app zip — derive services, deployments and "
        "incidents from its git history.",
        "icon": "upload",
        "source": "",
        "live_supported": True,
        "upload": True,  # frontend renders a file picker instead of a cred form
        "fields": [],
    },
]

_BY_TYPE = {c["app_type"]: c for c in CONNECTOR_CATALOG}


def get_catalog_entry(app_type: str) -> Dict[str, Any]:
    if app_type not in _BY_TYPE:
        raise KeyError(f"unknown app_type: {app_type!r}")
    return _BY_TYPE[app_type]


def is_supported(app_type: str) -> bool:
    return app_type in _BY_TYPE
