"""Monitoring Agent — anomaly detection, health scoring, alerting.

Inputs : recent metrics + logs for a service/environment.
Output : {"health_status": str, "confidence": float, ...}
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List

from app.agents.base import BaseAgent

# Metric thresholds (value above which a metric is considered hot).
_THRESHOLDS = {
    "cpu": 85.0,
    "cpuutilization": 85.0,
    "percentage cpu": 85.0,
    "memory": 90.0,
    "error_rate": 5.0,
    "latency_p99": 1500.0,
    "disk": 90.0,
}


class MonitoringAgent(BaseAgent):
    name = "monitoring"

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        metrics: List[Dict[str, Any]] = context.get("metrics", [])
        logs: List[Dict[str, Any]] = context.get("logs", [])

        anomalies = self._detect_anomalies(metrics)
        error_logs = [l for l in logs if l.get("severity") in {"high", "critical"}]
        health_score = self._health_score(metrics, anomalies, error_logs)
        status = self._status_from_score(health_score)

        alerts = [
            f"{a['metric_name']} on {a['service']} = {a['value']:.1f} "
            f"(> {a['threshold']:.0f})"
            for a in anomalies
        ]
        if error_logs:
            alerts.append(f"{len(error_logs)} error/critical log signal(s)")

        confidence = round(min(0.99, 0.55 + 0.05 * len(metrics) + 0.1 * len(anomalies)), 2)
        return {
            "health_status": status,
            "health_score": health_score,
            "confidence": confidence,
            "anomalies": anomalies,
            "alerts": alerts,
        }

    def _detect_anomalies(self, metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        # Group by (service, metric_name) for z-score style outlier detection.
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for m in metrics:
            groups.setdefault((m.get("service"), m.get("metric_name")), []).append(m)

        for (service, metric_name), rows in groups.items():
            values = [float(r.get("value", 0.0)) for r in rows]
            latest = values[-1]
            threshold = _THRESHOLDS.get((metric_name or "").lower())
            hot = threshold is not None and latest >= threshold
            # Statistical spike: latest is > 2.5 std above the mean.
            spike = False
            if len(values) >= 4:
                mean = statistics.mean(values[:-1])
                stdev = statistics.pstdev(values[:-1]) or 1e-9
                spike = (latest - mean) / stdev > 2.5
            if hot or spike:
                anomalies.append(
                    {
                        "service": service,
                        "metric_name": metric_name,
                        "value": latest,
                        "threshold": threshold or 0.0,
                        "kind": "threshold" if hot else "statistical_spike",
                    }
                )
        return anomalies

    def _health_score(self, metrics, anomalies, error_logs) -> int:
        score = 100
        score -= 12 * len(anomalies)
        score -= 8 * len(error_logs)
        if not metrics:
            score -= 5  # blind spot penalty
        return max(0, min(100, score))

    @staticmethod
    def _status_from_score(score: int) -> str:
        if score >= 85:
            return "healthy"
        if score >= 60:
            return "degraded"
        if score >= 35:
            return "unhealthy"
        return "critical"
