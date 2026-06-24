"""Website Monitor connector — synthetic uptime/performance checks for a live URL.

Unlike the git-import path (which infers telemetry from commit history), this is
genuinely live: the background poller re-probes the URL on a schedule and emits
real runtime telemetry — availability, response time, HTTP status, error rate —
plus an incident-grade log when the site is down, errors, or is slow. So Health,
Incidents, Metrics and Mission Control reflect the real running website.
"""
from __future__ import annotations

import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import httpx

from app.ingestion.base import BaseConnector
from app.schemas.events import EventType, UnifiedEvent


# A browser-ish UA — some hosts (httpstat.us, CDNs, WAFs) drop requests from
# the default python-httpx client and "disconnect without a response".
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DeployHub-Monitor/1.0)",
    "Accept": "*/*",
}


def _service_name(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host or "website"


def _resilience_signals(url: str) -> Dict[str, float]:
    """Measure REAL, externally-observable disaster-recovery signals for a URL:

      * endpoint_redundancy : how many distinct IPs the host resolves to
                              (>1 => real failover/redundancy; 1 => single point of failure)
      * tls_valid           : 1.0 if the certificate chain verifies, else 0.0
      * cert_days_to_expiry : days until the TLS certificate expires (-1 if unknown)

    Nothing here is fabricated — these come straight from DNS resolution and the
    live TLS handshake.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    out = {"endpoint_redundancy": 0.0, "tls_valid": 0.0, "cert_days_to_expiry": -1.0}
    if not host:
        return out

    # DNS redundancy — distinct resolved IPs.
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        out["endpoint_redundancy"] = float(len({i[4][0] for i in infos}))
    except Exception:  # noqa: BLE001
        pass

    if parsed.scheme != "https":
        return out

    # TLS chain validity (verified handshake).
    try:
        with socket.create_connection((host, port), timeout=10) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=host):
                out["tls_valid"] = 1.0
    except ssl.SSLError:
        out["tls_valid"] = 0.0
    except Exception:  # noqa: BLE001
        pass

    # Certificate expiry — read the cert even if the chain is invalid.
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=10) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                der = ss.getpeercert(binary_form=True)
        if der:
            from cryptography import x509

            cert = x509.load_der_x509_certificate(der)
            try:
                expiry = cert.not_valid_after_utc
            except AttributeError:  # older cryptography
                expiry = cert.not_valid_after.replace(tzinfo=timezone.utc)
            out["cert_days_to_expiry"] = float(
                (expiry - datetime.now(timezone.utc)).days
            )
    except Exception:  # noqa: BLE001
        pass
    return out


class WebsiteConnector(BaseConnector):
    source = "website"

    def _url(self) -> str:
        url = (self.config.get("url") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def _request(self, url: str, timeout: float):
        """GET with TLS verification; if the certificate can't be verified, retry
        WITHOUT verification so internal / self-signed / incomplete-chain sites
        can still be monitored. Returns (response_or_None, error_str, ssl_ok).
        """
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True,
                          headers=_HEADERS)
            return r, "", True
        except httpx.HTTPError as exc:
            msg = str(exc)
            if "CERTIFICATE_VERIFY" in msg or "SSL" in msg.upper() or "certificate" in msg.lower():
                try:
                    r = httpx.get(url, timeout=timeout, follow_redirects=True,
                                  verify=False, headers=_HEADERS)
                    return r, "", False  # reachable, but cert is invalid
                except httpx.HTTPError as exc2:
                    return None, str(exc2), False
            return None, msg, True

    def test_connection(self) -> Tuple[bool, str]:
        url = self._url()
        if not url:
            return False, "url is required"
        if not urlparse(url).netloc:
            return False, "enter a valid URL, e.g. https://example.com"
        # A down / error-returning site is a VALID monitor target — that's the
        # whole point — so reachability never blocks the connect.
        r, error, ssl_ok = self._request(url, timeout=25)
        if r is None:
            return True, f"added — site currently unreachable ({error}); will be monitored"
        note = "" if ssl_ok else " (reachable, but TLS certificate is invalid — will be flagged as an incident)"
        return True, f"reachable — HTTP {r.status_code}{note}"

    def fetch_raw(self) -> Iterable[Dict[str, Any]]:
        url = self._url()
        if not url:
            return []
        svc = _service_name(url)
        now = datetime.now(timezone.utc).isoformat()

        start = time.perf_counter()
        r, error, ssl_ok = self._request(url, timeout=30)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        status_code = r.status_code if r is not None else 0

        down = (r is None) or status_code >= 500 or status_code == 0
        client_err = 400 <= status_code < 500
        up = not down

        # error_rate feeds the monitoring agent's threshold (>=5 => anomaly), so
        # downtime/errors actually lower the health score.
        error_rate = 100.0 if down else (50.0 if client_err else 0.0)

        records: List[Dict[str, Any]] = [
            {"kind": "metric", "service": svc, "metric_name": "availability",
             "value": 100.0 if up else 0.0, "unit": "Percent", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "latency_p99",
             "value": round(elapsed_ms, 1), "unit": "Milliseconds", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "status_code",
             "value": float(status_code), "unit": "Count", "ts": now},
            {"kind": "metric", "service": svc, "metric_name": "error_rate",
             "value": error_rate, "unit": "Percent", "ts": now},
        ]

        # Real DR/resilience signals (DNS redundancy + TLS validity/expiry).
        sig = _resilience_signals(url)
        for name, unit in (("endpoint_redundancy", "Count"),
                           ("tls_valid", "Count"),
                           ("cert_days_to_expiry", "Days")):
            records.append({"kind": "metric", "service": svc,
                            "metric_name": name, "value": sig[name],
                            "unit": unit, "ts": now})

        # Incident-grade log when the site is unhealthy. Each carries a STABLE
        # signature ("sig") so recurring issues de-duplicate into one open
        # incident instead of a new one every poll (the varying ms etc. stays in
        # the message/description).
        if down:
            detail = error or f"HTTP {status_code}"
            records.append({
                "kind": "log", "service": svc, "severity": "critical",
                "sig": f"{svc} is down",
                "message": f"{svc} is DOWN: {detail}", "ts": now,
            })
        elif client_err:
            records.append({
                "kind": "log", "service": svc, "severity": "high",
                "sig": f"{svc} HTTP {status_code}",
                "message": f"{svc} returned HTTP {status_code}", "ts": now,
            })
        elif elapsed_ms > 1500:
            records.append({
                "kind": "log", "service": svc, "severity": "high",
                "sig": f"{svc} slow response",
                "message": f"{svc} slow response: {elapsed_ms:.0f}ms", "ts": now,
            })

        # An invalid/unverifiable TLS certificate is itself an incident, even if
        # the site responds — surface it independently of up/down status.
        if r is not None and not ssl_ok:
            records.append({
                "kind": "log", "service": svc, "severity": "high",
                "sig": f"{svc} TLS certificate invalid",
                "message": f"{svc} TLS certificate verification failed "
                           f"(invalid or incomplete certificate chain)", "ts": now,
            })
        return records

    def normalize(self, raw: Dict[str, Any]) -> UnifiedEvent:
        if raw.get("kind") == "log":
            msg = raw.get("message", "")
            return UnifiedEvent(
                source=self.source, event_type=EventType.LOG.value,
                timestamp=raw.get("ts"), severity=raw.get("severity", "high"),
                service=raw["service"], environment="prod",
                metadata={"message": msg,
                          "error_signature": raw.get("sig") or msg[:60]},
            )
        return UnifiedEvent(
            source=self.source, event_type=EventType.METRIC.value,
            timestamp=raw.get("ts"), severity="info",
            service=raw["service"], environment="prod",
            metadata={"metric_name": raw["metric_name"], "value": raw["value"],
                      "unit": raw.get("unit", "")},
        )
