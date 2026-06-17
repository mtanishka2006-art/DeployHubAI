"""RCA Agent — root cause detection via temporal + causal correlation.

Inputs : logs, metrics, recent deployment history, plus retrieved memory.
Output : {"root_cause": str, "confidence": float, ...}
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.agents.base import BaseAgent


class RCAAgent(BaseAgent):
    name = "rca"

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        logs: List[Dict[str, Any]] = context.get("logs", [])
        metrics: List[Dict[str, Any]] = context.get("metrics", [])
        deployments: List[Dict[str, Any]] = context.get("deployments", [])
        anomalies: List[Dict[str, Any]] = context.get("anomalies", [])
        service = context.get("service", "unknown")

        hypotheses: List[Dict[str, Any]] = []

        # 1. Deployment correlation — a recent failed/changed deploy is the
        #    most common root cause.
        recent_deploys = sorted(
            deployments, key=lambda d: d.get("timestamp", ""), reverse=True
        )
        for dep in recent_deploys[:3]:
            if dep.get("status") in {"failed", "rolled_back"}:
                hypotheses.append(
                    {
                        "cause": f"Recent {dep['status']} deployment of "
                        f"{dep.get('service', service)} "
                        f"(v{dep.get('version', '?')})",
                        "confidence": 0.82,
                        "signal": "deployment_correlation",
                    }
                )
            elif dep.get("status") == "success":
                hypotheses.append(
                    {
                        "cause": f"Regression introduced by deployment "
                        f"v{dep.get('version', '?')} of {dep.get('service', service)}",
                        "confidence": 0.6,
                        "signal": "deployment_temporal",
                    }
                )

        # 2. Resource saturation from anomalies.
        for a in anomalies:
            hypotheses.append(
                {
                    "cause": f"Resource saturation: {a['metric_name']} at "
                    f"{a['value']:.0f} on {a['service']}",
                    "confidence": 0.7,
                    "signal": "metric_anomaly",
                }
            )

        # 3. Error-signature clustering from logs.
        signatures = self._top_signatures(logs)
        for sig, count in signatures[:2]:
            hypotheses.append(
                {
                    "cause": f"Recurring error signature '{sig}' ({count}x)",
                    "confidence": min(0.75, 0.4 + 0.05 * count),
                    "signal": "log_clustering",
                }
            )

        # 4. Memory: have we seen this before?
        memory_hits = self.memory.search_similar_incidents(
            context.get("query", service), k=3
        )
        for hit in memory_hits:
            if hit.get("root_cause") and hit.get("score", 0) > 0.5:
                hypotheses.append(
                    {
                        "cause": f"Matches historical incident: {hit['root_cause']}",
                        "confidence": round(0.5 + 0.4 * hit["score"], 2),
                        "signal": "historical_match",
                    }
                )

        if not hypotheses:
            return {
                "root_cause": "Insufficient signal to determine root cause; "
                "manual investigation required.",
                "confidence": 0.25,
                "hypotheses": [],
                "correlations": [],
            }

        hypotheses.sort(key=lambda h: h["confidence"], reverse=True)
        best = hypotheses[0]
        return {
            "root_cause": best["cause"],
            "confidence": best["confidence"],
            "hypotheses": hypotheses,
            "correlations": [h["signal"] for h in hypotheses],
        }

    @staticmethod
    def _top_signatures(logs: List[Dict[str, Any]]):
        counts: Dict[str, int] = {}
        for l in logs:
            sig = l.get("error_signature") or l.get("message", "")[:40]
            if sig:
                counts[sig] = counts.get(sig, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
