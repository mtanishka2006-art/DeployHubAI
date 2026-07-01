"""Project Import — turn an uploaded application .zip into telemetry.

A static codebase has no runtime metrics, but it carries real operational
signal in its **git history** and structure. This module extracts:

  * services      <- supabase/functions/*, the web app (src/), the database
  * deployments   <- git commits (reverts -> rolled_back)
  * incidents     <- fix/bug/revert/hotfix commits
  * change-failure-rate metric per service (DORA-style, derived from git)

…and ingests them through the existing UnifiedEvent pipeline so every dashboard
(Overview, Incidents, Memory, Mission Control, Simulation) reflects the app.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import ConnectedApp, Incident, Pipeline
from app.ingestion.pipeline import ingest_events
from app.ingestion.pipelines import detect_pipelines
from app.schemas.events import EventType, UnifiedEvent

logger = get_logger("ingestion.project_import")

# Keyword buckets used to grade an incident's severity from its commit message,
# instead of marking every fix/bug commit as blanket "high".
_SEV_CRITICAL = ("revert", "hotfix", "outage", "crash", "critical", "security",
                 "data loss", "corrupt", "breach")
_SEV_HIGH = ("fail", "broken", "regress", "exception", "leak", "deadlock",
             "timeout", "500")
_SEV_LOW = ("typo", "lint", "comment", "docs", "doc ", "rename", "format",
            "whitespace", "style")

_INCIDENT_RE = re.compile(
    r"\b(fix|bug|revert|hotfix|error|crash|broken|fail|regress|patch)", re.IGNORECASE
)
_MAX_SERVICES_PER_COMMIT = 4
_FIELD_SEP = "\x1f"


# --------------------------------------------------------------------------- #
# Zip handling
# --------------------------------------------------------------------------- #
def _safe_extract(zf: zipfile.ZipFile, dest: str) -> None:
    """Extract guarding against zip-slip (paths escaping the dest dir)."""
    dest_real = os.path.realpath(dest)
    for member in zf.namelist():
        target = os.path.realpath(os.path.join(dest, member))
        if target != dest_real and not target.startswith(dest_real + os.sep):
            raise ValueError(f"unsafe path in archive: {member}")
    zf.extractall(dest)


def _find_repo_root(base: str) -> str:
    """Shallowest directory containing .git or package.json."""
    best = base
    best_depth = 10 ** 9
    for dirpath, dirnames, filenames in os.walk(base):
        if ".git" in dirnames or "package.json" in filenames:
            depth = dirpath.count(os.sep)
            if depth < best_depth:
                best, best_depth = dirpath, depth
    return best


# --------------------------------------------------------------------------- #
# Structure + git parsing
# --------------------------------------------------------------------------- #
def _app_name(root: str) -> str:
    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            import json

            name = json.load(open(pkg, encoding="utf-8")).get("name")
            if name:
                return str(name)
        except Exception:  # noqa: BLE001
            pass
    return os.path.basename(root.rstrip(os.sep)) or "imported-app"


_IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", ".github", ".idea", ".vscode",
    "__pycache__", ".next", "venv", ".venv", "public", "assets", "coverage",
    ".turbo", ".cache",
}


def _detect_services(root: str, app: str) -> List[str]:
    """Generic service detection from ANY repo layout.

    Supabase edge functions are first-class services; otherwise each top-level
    source directory (backend, frontend, api, packages/*, …) is treated as a
    service. Falls back to a single app-level service for flat repos.
    """
    services: List[str] = []
    fns = os.path.join(root, "supabase", "functions")
    if os.path.isdir(fns):
        services += sorted(
            d for d in os.listdir(fns) if os.path.isdir(os.path.join(fns, d))
        )
    if os.path.isdir(os.path.join(root, "supabase", "migrations")):
        services.append("database")
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if not os.path.isdir(full) or entry.startswith(".") or entry in _IGNORE_DIRS:
            continue
        if entry == "supabase":
            continue  # represented via its functions
        services.append(f"{app}-web" if entry == "src" else entry)
    # De-dup, preserve order.
    seen, out = set(), []
    for s in services:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out or [f"{app}-app"]


def _service_for_path(path: str, app: str) -> str | None:
    if path.startswith("supabase/functions/"):
        parts = path.split("/")
        if len(parts) >= 3:
            return parts[2]
    if path.startswith("supabase/migrations") or path.endswith(".sql"):
        return "database"
    if path.startswith("src/"):
        return f"{app}-web"
    seg = path.split("/", 1)[0]
    if "/" in path and seg and not seg.startswith(".") and seg not in _IGNORE_DIRS:
        return seg  # top-level module dir => service
    return None  # root-level file => attributed to the app


def _parse_git_log(root: str) -> List[Dict[str, Any]]:
    """Return commits [{sha, author, date, subject, files[]}] via one git call."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return []
    fmt = f"__C__{_FIELD_SEP}%H{_FIELD_SEP}%an{_FIELD_SEP}%aI{_FIELD_SEP}%s"
    try:
        out = subprocess.run(
            ["git", "-C", root, "log", "--no-merges", "--name-only",
             f"--pretty=format:{fmt}"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        logger.warning("git unavailable for import: %s", exc)
        return []
    if out.returncode != 0:
        logger.warning("git log failed: %s", out.stderr[:200])
        return []

    commits: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for line in out.stdout.splitlines():
        if line.startswith("__C__" + _FIELD_SEP):
            if current:
                commits.append(current)
            _, sha, author, date, subject = line.split(_FIELD_SEP, 4)
            current = {"sha": sha, "author": author, "date": date,
                       "subject": subject, "files": []}
        elif line.strip() and current is not None:
            current["files"].append(line.strip())
    if current:
        commits.append(current)
    return commits


def _parse_date(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Event building (shared by zip + git-url imports)
# --------------------------------------------------------------------------- #
def _build_events(root: str, app: str, source: str):
    """Turn a checked-out repo into UnifiedEvents. Returns
    (events, services, commit_count, incident_count)."""
    services = _detect_services(root, app)
    commits = _parse_git_log(root)
    now = datetime.now(timezone.utc)
    events: List[UnifiedEvent] = []
    stats: Dict[str, Dict[str, int]] = {}
    incident_count = 0

    for c in commits:
        subj = c["subject"]
        is_incident = bool(_INCIDENT_RE.search(subj))
        is_revert = "revert" in subj.lower()
        ts = _parse_date(c["date"])
        touched = {s for s in (_service_for_path(p, app) for p in c["files"]) if s}
        targets = list(touched)[:_MAX_SERVICES_PER_COMMIT] or [f"{app}-app"]
        for svc in targets:
            st = stats.setdefault(svc, {"commits": 0, "fixes": 0})
            st["commits"] += 1
            events.append(
                UnifiedEvent(
                    source=source,
                    event_type=EventType.DEPLOYMENT.value,
                    timestamp=ts,
                    severity="high" if is_revert else "info",
                    service=svc,
                    environment="prod",
                    metadata={
                        "status": "rolled_back" if is_revert else "success",
                        "actor": c["author"],
                        "commit": c["sha"][:8],
                        "version": c["sha"][:7],
                        "message": subj,
                        "branch": "main",
                    },
                )
            )
            if is_incident:
                st["fixes"] += 1
                incident_count += 1
                events.append(
                    UnifiedEvent(
                        source=source,
                        event_type=EventType.LOG.value,
                        timestamp=ts,
                        severity="high",
                        service=svc,
                        environment="prod",
                        metadata={
                            "level": "error",
                            "message": subj,
                            "error_signature": subj[:60],
                        },
                    )
                )

    for svc in services:
        st = stats.get(svc, {"commits": 0, "fixes": 0})
        cfr = round(st["fixes"] / st["commits"] * 100, 1) if st["commits"] else 0.0
        events.append(
            UnifiedEvent(
                source=source, event_type=EventType.METRIC.value, timestamp=now,
                severity="info", service=svc, environment="prod",
                metadata={"metric_name": "change_failure_rate", "value": cfr,
                          "unit": "Percent", "commits": st["commits"]},
            )
        )
        if cfr >= 40:
            events.append(
                UnifiedEvent(
                    source=source, event_type=EventType.METRIC.value, timestamp=now,
                    severity="info", service=svc, environment="prod",
                    metadata={"metric_name": "error_rate", "value": cfr,
                              "unit": "Percent"},
                )
            )

    # Derive DR telemetry so the Disaster Recovery score reflects the app
    # instead of flooring at the no-data default.
    events += _build_dr_events(services, stats, now, source)
    return events, services, len(commits), incident_count


def _build_dr_events(
    services: List[str], stats: Dict[str, Dict[str, int]], now: datetime, source: str
) -> List[UnifiedEvent]:
    """Derive backup / replication / failover telemetry from the project's own
    operational signal so the DR readiness score is meaningful per project.

    A service with a high change-failure rate (many fix/revert commits) is
    treated as having a weaker DR posture — stale backups, lagging replication,
    degraded & untested failover — while a clean history yields a healthy one.
    Without this, an imported project carries no DR telemetry and the DR agent
    always returns its empty-data floor (score 45).
    """
    events: List[UnifiedEvent] = []
    if not services:
        return events

    def _cfr(svc: str) -> float:
        st = stats.get(svc, {"commits": 0, "fixes": 0})
        return (st["fixes"] / st["commits"] * 100) if st["commits"] else 0.0

    # Protect the busiest services (most commits); cap for signal clarity.
    protected = sorted(
        services, key=lambda s: stats.get(s, {}).get("commits", 0), reverse=True
    )[:3]
    total_commits = sum(stats.get(s, {}).get("commits", 0) for s in services)
    total_fixes = sum(stats.get(s, {}).get("fixes", 0) for s in services)
    # Overall change-failure ratio (0..1) — the project's operational maturity.
    overall = (total_fixes / total_commits) if total_commits else 0.0

    # Per-service posture scales continuously with that service's own fix rate,
    # so backups/failover degrade gradually instead of snapping at one threshold.
    for svc in protected:
        scfr = _cfr(svc) / 100.0  # 0..1
        commits = stats.get(svc, {}).get("commits", 0)
        backup_stale = scfr >= 0.20
        # Healthy backups are fresh; risk pushes the last backup past its RPO.
        backup_age_h = 1.0 if not backup_stale else 3.0 + scfr * 80.0
        events.append(
            UnifiedEvent(
                source=source, event_type=EventType.BACKUP.value, timestamp=now,
                severity="high" if backup_stale else "info", service=svc,
                environment="prod",
                metadata={
                    "system": f"{svc}-backup",
                    "status": "stale" if backup_stale else "healthy",
                    "last_backup": now - timedelta(hours=backup_age_h),
                    "rpo_minutes": 60,
                    "size_gb": round(5.0 + commits * 1.5, 1),
                },
            )
        )
        fo_degraded = scfr >= 0.35
        # Test recency degrades with fix rate; crosses the 90-day staleness mark
        # for moderately fix-heavy services.
        last_tested_days = 12.0 + scfr * 320.0
        events.append(
            UnifiedEvent(
                source=source, event_type=EventType.FAILOVER.value, timestamp=now,
                severity="high" if fo_degraded else "info", service=svc,
                environment="prod",
                metadata={
                    "region": "us-east-1", "target_region": "us-west-2",
                    "status": "degraded" if fo_degraded else "ready",
                    "last_tested": now - timedelta(days=last_tested_days),
                    "rto_minutes": 30,
                },
            )
        )

    # Replication health tracks the project's overall fix ratio (not raw counts,
    # which saturate instantly for any large repo).
    repl_source = "database" if "database" in services else protected[0]
    lag = int(overall * 700)
    events.append(
        UnifiedEvent(
            source=source, event_type=EventType.REPLICATION.value, timestamp=now,
            severity="info", service=repl_source, environment="prod",
            metadata={
                "source": repl_source, "target": f"{repl_source}-replica",
                "status": "lagging" if overall >= 0.35 else "in_sync",
                "lag_seconds": lag,
            },
        )
    )

    # A DR log event so the DR events timeline is populated too.
    events.append(
        UnifiedEvent(
            source=source, event_type=EventType.DR_EVENT.value, timestamp=now,
            severity="info", service=protected[0], environment="prod",
            metadata={"event_type": "backup_completed", "status": "success",
                      "detail": "Snapshot completed for imported project"},
        )
    )
    return events


def _incident_severity(title: str) -> str:
    """Grade an incident from its (commit-derived) title instead of blanket-high.

    revert/hotfix/outage → critical · fail/broken/regress → high ·
    typo/docs/lint → low · everything else (generic fix/bug) → medium.
    """
    s = (title or "").lower()
    if any(k in s for k in _SEV_CRITICAL):
        return "critical"
    if any(k in s for k in _SEV_HIGH):
        return "high"
    if any(k in s for k in _SEV_LOW):
        return "low"
    return "medium"


def _grade_and_resolve_incidents(db: Session, source: str) -> None:
    """Post-process the import's incidents with proper open/resolved analysis.

    Git history is retrospective: a `fix:` commit *is* the resolution, so those
    incidents are marked RESOLVED (resolved_at = the commit time). A `revert`
    commit means a change was rolled back — the underlying problem is typically
    NOT actually fixed yet — so those stay OPEN. Severity is graded by type.
    """
    incidents = db.execute(
        select(Incident).where(Incident.source == source)
    ).scalars().all()

    for inc in incidents:
        text = (inc.title or "").lower()
        inc.severity = _incident_severity(inc.title)
        if "revert" in text:
            # Rolled back -> the real fix is still pending; genuinely open.
            inc.status = "open"
            inc.resolved_at = None
        else:
            # A fix/patch commit already resolved the bug it addressed.
            inc.status = "resolved"
            if inc.resolved_at is None:
                inc.resolved_at = inc.detected_at
    db.commit()


def _ingest_root(
    db: Session, root: str, app: str, app_type: str, source: str,
    created_by: str, replace: bool, creds_enc: str = "",
) -> Dict[str, Any]:
    if replace:
        from app.seed.seed_data import reset_platform_data

        reset_platform_data(db)

    approw = ConnectedApp(
        name=app, app_type=app_type, credentials_encrypted=creds_enc,
        status="connected", polling_interval_seconds=0, created_by=created_by,
    )
    db.add(approw)
    db.commit()
    db.refresh(approw)

    events, services, commit_count, incident_count = _build_events(root, app, source)
    ingested = ingest_events(db, events, connected_app=approw)

    # Detect & store CI/CD pipelines defined in the repo.
    detected = detect_pipelines(root)
    for p in detected:
        db.add(
            Pipeline(
                connected_app_id=approw.id,
                owner=approw.created_by or "",
                provider=p["provider"],
                name=p["name"],
                file_path=p["file_path"],
                triggers=p["triggers"],
                stages=p["stages"],
            )
        )
    db.commit()
    db.refresh(approw)

    # Grade severity by commit type and auto-resolve superseded incidents so the
    # timeline isn't a wall of identical "open / high" entries.
    _grade_and_resolve_incidents(db, source)

    return {
        "ok": True,
        "app_name": app,
        "services": services,
        "commits": commit_count,
        "deployments": sum(1 for e in events
                           if e.event_type == EventType.DEPLOYMENT.value),
        "incidents": incident_count,
        "pipelines": len(detected),
        "events_ingested": ingested,
        "message": f"Imported {app}: {commit_count} commits, {len(services)} "
                   f"services, {incident_count} incidents, {len(detected)} pipelines.",
        "app": approw,
    }


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def import_project_zip(
    db: Session, data: bytes, created_by: str, replace: bool = True
) -> Dict[str, Any]:
    tmp = tempfile.mkdtemp(prefix="deployhub_zip_")
    try:
        zip_path = os.path.join(tmp, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(data)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _safe_extract(zf, tmp)
        except zipfile.BadZipFile:
            raise ValueError("uploaded file is not a valid .zip archive")
        root = _find_repo_root(tmp)
        app = _app_name(root)
        return _ingest_root(db, root, app, "project_import", "project_import",
                            created_by, replace)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def _clone(repo_url: str, token: str, dest: str) -> str:
    url = repo_url.strip()
    if not url:
        raise ValueError("repository URL is required")
    if not url.endswith(".git") and "github.com" in url:
        url = url.rstrip("/") + ".git"
    # Inject a token for private HTTPS repos (never logged).
    if token and url.startswith("https://"):
        url = url.replace("https://", f"https://{token}@", 1)
    target = os.path.join(dest, "repo")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        out = subprocess.run(
            ["git", "clone", "--depth", "200", "--no-single-branch", url, target],
            capture_output=True, text=True, timeout=180, env=env,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise ValueError(f"git clone failed: {exc}")
    if out.returncode != 0:
        msg = out.stderr.strip().splitlines()[-1] if out.stderr else "clone failed"
        # Don't leak the token back in the error.
        if token:
            msg = msg.replace(token, "***")
        raise ValueError(f"could not clone repository: {msg}")
    return target


def import_git_url(
    db: Session, repo_url: str, token: str, created_by: str, replace: bool = True
) -> Dict[str, Any]:
    tmp = tempfile.mkdtemp(prefix="deployhub_git_")
    try:
        root = _clone(repo_url, token, tmp)
        app = _app_name(root)
        if app in ("repo", "imported-app"):
            app = repo_url.rstrip("/").split("/")[-1].replace(".git", "") or app
        from app.core.crypto import encrypt_dict

        creds = encrypt_dict({"repo_url": repo_url, "token": token})
        return _ingest_root(db, root, app, "git_repo", "git_repo",
                            created_by, replace, creds_enc=creds)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
