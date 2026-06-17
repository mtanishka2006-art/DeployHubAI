"""CI/CD pipeline detection from a checked-out repository.

Scans a repo for pipeline definition files (GitHub Actions, GitLab CI, Jenkins,
Azure Pipelines, CircleCI, Bitbucket, Travis) and extracts light metadata:
name, triggers and stages/jobs. Uses PyYAML when available, otherwise a regex
fallback so it works with zero extra dependencies.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("ingestion.pipelines")

_MAX = 60  # cap stages/triggers lists


def _load_yaml(text: str) -> Optional[dict]:
    try:
        import yaml  # optional

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - no yaml or parse error
        return None


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# Heuristic (no-YAML) helpers
# --------------------------------------------------------------------------- #
def _regex_name(text: str, fallback: str) -> str:
    m = re.search(r"^name:\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def _regex_block_keys(text: str, parent: str) -> List[str]:
    """Top-level keys nested under `parent:` (2-space indent block)."""
    keys: List[str] = []
    in_block = False
    for line in text.splitlines():
        if re.match(rf"^{parent}:\s*$", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^\S", line):  # dedent to column 0 => block ended
                break
            m = re.match(r"^  ([A-Za-z0-9_.-]+):", line)
            if m:
                keys.append(m.group(1))
    return keys[:_MAX]


def _github_triggers(data: Optional[dict], text: str) -> List[str]:
    if data is not None:
        # PyYAML parses the `on:` key as boolean True (YAML 1.1).
        on = data.get("on", data.get(True))
        if isinstance(on, str):
            return [on]
        if isinstance(on, list):
            return [str(x) for x in on][:_MAX]
        if isinstance(on, dict):
            return list(on.keys())[:_MAX]
    # regex fallback
    m = re.search(r"^on:\s*\[([^\]]+)\]", text, re.MULTILINE)
    if m:
        return [t.strip() for t in m.group(1).split(",")][:_MAX]
    m = re.search(r"^on:\s*([A-Za-z_]+)\s*$", text, re.MULTILINE)
    if m:
        return [m.group(1)]
    return _regex_block_keys(text, "on")


# --------------------------------------------------------------------------- #
# Per-provider parsers
# --------------------------------------------------------------------------- #
def _parse_github(path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    data = _load_yaml(text)
    name = (data.get("name") if data else None) or _regex_name(
        text, os.path.basename(path)
    )
    jobs = list(data.get("jobs", {}).keys())[:_MAX] if data and isinstance(
        data.get("jobs"), dict
    ) else _regex_block_keys(text, "jobs")
    return {
        "provider": "github_actions",
        "name": name,
        "file_path": rel,
        "triggers": _github_triggers(data, text),
        "stages": jobs,
    }


def _parse_gitlab(path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    data = _load_yaml(text)
    stages = []
    if data and isinstance(data.get("stages"), list):
        stages = [str(s) for s in data["stages"]][:_MAX]
    elif data:
        stages = [k for k in data.keys()
                  if k not in ("stages", "variables", "default", "include")][:_MAX]
    return {"provider": "gitlab_ci", "name": "GitLab CI", "file_path": rel,
            "triggers": ["push", "merge_request"], "stages": stages}


def _parse_jenkins(path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    stages = re.findall(r"stage\s*\(\s*[\"']([^\"']+)[\"']", text)[:_MAX]
    triggers = []
    if "cron(" in text:
        triggers.append("schedule")
    if "pollSCM" in text:
        triggers.append("scm")
    return {"provider": "jenkins", "name": "Jenkins Pipeline", "file_path": rel,
            "triggers": triggers or ["manual"], "stages": stages}


def _parse_azure(path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    data = _load_yaml(text)
    stages = []
    if data:
        if isinstance(data.get("stages"), list):
            stages = [s.get("stage", "stage") if isinstance(s, dict) else str(s)
                      for s in data["stages"]][:_MAX]
        elif isinstance(data.get("jobs"), list):
            stages = [j.get("job", "job") if isinstance(j, dict) else str(j)
                      for j in data["jobs"]][:_MAX]
    return {"provider": "azure_pipelines", "name": "Azure Pipelines",
            "file_path": rel, "triggers": ["push", "pr"], "stages": stages}


def _parse_circleci(path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    data = _load_yaml(text)
    jobs = list(data.get("jobs", {}).keys())[:_MAX] if data and isinstance(
        data.get("jobs"), dict
    ) else _regex_block_keys(text, "jobs")
    return {"provider": "circleci", "name": "CircleCI", "file_path": rel,
            "triggers": ["push"], "stages": jobs}


def _parse_generic_yaml(provider: str, label: str, path: str, rel: str) -> Dict[str, Any]:
    text = _read(path)
    data = _load_yaml(text)
    stages = _regex_block_keys(text, "pipelines") or (
        list(data.keys())[:_MAX] if data else []
    )
    return {"provider": provider, "name": label, "file_path": rel,
            "triggers": ["push"], "stages": stages}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def detect_pipelines(root: str) -> List[Dict[str, Any]]:
    pipelines: List[Dict[str, Any]] = []

    # GitHub Actions — every yml/yaml under .github/workflows
    wf_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf_dir):
        for fname in sorted(os.listdir(wf_dir)):
            if fname.endswith((".yml", ".yaml")):
                pipelines.append(
                    _parse_github(os.path.join(wf_dir, fname),
                                  f".github/workflows/{fname}")
                )

    single_files = [
        (".gitlab-ci.yml", _parse_gitlab),
        ("azure-pipelines.yml", _parse_azure),
        (".circleci/config.yml", _parse_circleci),
    ]
    for rel, parser in single_files:
        full = os.path.join(root, *rel.split("/"))
        if os.path.isfile(full):
            pipelines.append(parser(full, rel))

    # Jenkinsfile (root or common locations)
    for rel in ("Jenkinsfile", "jenkins/Jenkinsfile", "ci/Jenkinsfile"):
        full = os.path.join(root, *rel.split("/"))
        if os.path.isfile(full):
            pipelines.append(_parse_jenkins(full, rel))

    for rel, label, provider in (
        ("bitbucket-pipelines.yml", "Bitbucket Pipelines", "bitbucket"),
        (".travis.yml", "Travis CI", "travis"),
    ):
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            pipelines.append(_parse_generic_yaml(provider, label, full, rel))

    logger.info("detected %d pipeline(s)", len(pipelines))
    return pipelines
