"""Dynamic risk scoring for the Agent Behavior Protocol (ADR-010).

Agents invoke :func:`get_risk_context` at the start of CONSULT/AUTO
operations to determine whether live system signals warrant ESCALATING
to a stricter mode (AUTO → CONSULT, CONSULT → STOP). The protocol never
RELAXES based on risk context: STOP is sticky.

Signal sources (by priority):
    1. mcp-prometheus — live Prometheus queries (preferred, ADR-010)
    2. local files ops/incident_state.json, ops/last_drift_report.json
       (fallback when MCP is unavailable)
    3. degraded mode — return an UNAVAILABLE context; caller falls back
       to the static AGENTS.md mapping

Consumers:
    - .windsurf/skills/**/SKILL.md invocations
    - CI jobs that emit the [AGENT MODE: ...] signal
    - Pre-deploy checks in deploy-common.yml (future enhancement)

Engineering Calibration (ADR-001):
    - The module is a 200-line helper, not a distributed policy engine.
    - Dynamic scoring can ONLY escalate; ADR-005 static mapping is the
      conservative floor.
    - Escalation thresholds live in code here so they are version-controlled
      alongside AGENTS.md.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Mode = Literal["AUTO", "CONSULT", "STOP"]

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, "RiskContext"]] = {}


@dataclass(frozen=True)
class RiskContext:
    """Snapshot of live risk signals.

    Attributes:
        incident_active: A P1/P2 alert is firing.
        drift_severe:    Any feature's PSI > 2x its alert threshold.
        error_budget_exhausted: SLO burn rate says the budget is blown.
        off_hours: UTC Mon–Fri 18:00–08:00 OR Sat/Sun (business default).
        recent_rollback: A rollback audit issue was created in the last 6h.
        available: True if the signal source responded; False = fallback.
        source: "prometheus" | "file" | "unavailable".
    """

    incident_active: bool = False
    drift_severe: bool = False
    error_budget_exhausted: bool = False
    off_hours: bool = False
    recent_rollback: bool = False
    available: bool = False
    source: str = "unavailable"
    raw: dict = field(default_factory=dict)

    @property
    def signal_count(self) -> int:
        return sum(
            [
                self.incident_active,
                self.drift_severe,
                self.error_budget_exhausted,
                self.off_hours,
                self.recent_rollback,
            ]
        )

    def escalate(self, base_mode: Mode) -> Mode:
        """Apply the dynamic escalation table from ADR-010.

        Rules:
            AUTO + any 1 signal    → CONSULT
            CONSULT + any 1 signal → STOP
            STOP                   → STOP (always sticky)

        When :attr:`available` is False, returns ``base_mode`` unchanged
        (fallback — graceful degradation per ADR-010).
        """
        if base_mode == "STOP":
            return "STOP"
        if not self.available:
            return base_mode
        if self.signal_count == 0:
            return base_mode
        return "STOP" if base_mode == "CONSULT" else "CONSULT"


# ---------------------------------------------------------------------------
# Signal sources
# ---------------------------------------------------------------------------
def _load_file_signals(ops_dir: Path) -> RiskContext:
    """Fallback signal loader: reads ops/ artifacts written by CronJobs."""
    raw: dict = {}
    incident_active = False
    drift_severe = False
    recent_rollback = False

    incident_file = ops_dir / "incident_state.json"
    if incident_file.exists():
        try:
            data = json.loads(incident_file.read_text())
            raw["incident_state"] = data
            incident_active = bool(data.get("active", False))
        except Exception as exc:
            logger.debug("Could not parse incident_state.json: %s", exc)

    drift_file = ops_dir / "last_drift_report.json"
    if drift_file.exists():
        try:
            data = json.loads(drift_file.read_text())
            raw["drift_report"] = data
            drift_severe = bool(data.get("any_psi_over_2x_threshold", False))
        except Exception as exc:
            logger.debug("Could not parse last_drift_report.json: %s", exc)

    audit_log = ops_dir / "audit.jsonl"
    if audit_log.exists():
        try:
            six_hours_ago = time.time() - 6 * 3600
            for line in audit_log.read_text().splitlines()[-200:]:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("operation", "").startswith("rollback"):
                    ts_str = entry.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                        if ts >= six_hours_ago:
                            recent_rollback = True
                            raw["recent_rollback_entry"] = entry
                            break
                    except ValueError:
                        continue
        except Exception as exc:
            logger.debug("Could not scan audit.jsonl: %s", exc)

    return RiskContext(
        incident_active=incident_active,
        drift_severe=drift_severe,
        recent_rollback=recent_rollback,
        off_hours=_is_off_hours(),
        available=True,
        source="file",
        raw=raw,
    )


def _is_off_hours(now: datetime | None = None) -> bool:
    """Return True on weekends or weekday evenings/nights (UTC).

    Business default: 18:00–08:00 UTC Mon–Fri counts as off-hours.
    Weekends are always off-hours. Override via environment variable
    ``MLOPS_ON_HOURS_UTC`` (format "HH-HH", e.g. "06-20").
    """
    now = now or datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Saturday / Sunday
        return True
    span = os.getenv("MLOPS_ON_HOURS_UTC", "08-18")
    try:
        start_s, end_s = span.split("-")
        start = int(start_s)
        end = int(end_s)
    except ValueError:
        start, end = 8, 18
    return not (start <= now.hour < end)


_PROMETHEUS_TIMEOUT_SECONDS = 5.0
_PROMETHEUS_QUERIES = {
    # incident_active: any P1/P2 alert currently firing
    "incident_active": 'sum(ALERTS{severity=~"P1|P2",alertstate="firing"})',
    # drift_severe: any feature with PSI exceeding 2x its alert threshold
    "drift_severe": "max((feature_psi_score / on(feature) feature_psi_alert_threshold)) > 2",
    # error_budget_exhausted: SLO burn rate over 100% on the 30-day window
    "error_budget_exhausted": "(1 - slo_availability_ratio_rate30d) > slo_error_budget_target",
}


def _query_prometheus_scalar(prom_url: str, query: str, timeout: float) -> bool | None:
    """Run a single PromQL query and return True/False/None.

    Return contract:
        True  — query returned a non-empty `vector` or `scalar` with a value
                that is truthy (interpreted as "the condition is active").
        False — query succeeded but returned an empty vector or value 0.
        None  — HTTP, parsing, or auth failure. Caller treats as UNAVAILABLE.

    Uses stdlib `urllib` only — no new template dependency. Timeout is a
    hard cap; all signal sources combined must fit within
    ``_CACHE_TTL_SECONDS`` (60s) so the agent never blocks on signals.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    base = prom_url.rstrip("/")
    qs = urllib.parse.urlencode({"query": query})
    url = f"{base}/api/v1/query?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — internal URL
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        logger.debug("Prometheus query failed (%s): %s", query, exc)
        return None

    if payload.get("status") != "success":
        logger.debug("Prometheus returned non-success: %s", payload.get("status"))
        return None

    data = payload.get("data") or {}
    result_type = data.get("resultType")
    result = data.get("result") or []

    # `vector` queries return [{ "value": [ts, "1"] }, ...] — empty = condition off.
    if result_type == "vector":
        return len(result) > 0
    # `scalar` queries return [ts, "value"] — value > 0 means condition is active.
    if result_type == "scalar":
        try:
            return float(result[1]) > 0
        except (IndexError, ValueError, TypeError):
            return None
    # Unknown result type — be conservative.
    return None


def _load_prometheus_signals(prom_url: str) -> RiskContext:
    """Query Prometheus for the three signals that have a metric source.

    Returns a :class:`RiskContext` with source=``"prometheus"`` when ALL
    three queries succeed (regardless of outcome); ``available=False`` and
    source=``"unavailable"`` when ANY query fails so the caller can chain
    to :func:`_load_file_signals` (ADR-010 graceful degradation).

    Two signals are NOT in Prometheus and are populated separately:
        * ``off_hours``    — computed locally via :func:`_is_off_hours`
        * ``recent_rollback`` — read from the file-backed audit log when
          available (best-effort; ``False`` if log missing).
    """
    raw_results: dict[str, bool | None] = {
        name: _query_prometheus_scalar(prom_url, query, _PROMETHEUS_TIMEOUT_SECONDS)
        for name, query in _PROMETHEUS_QUERIES.items()
    }

    # If ANY signal query failed, the source is degraded → fall back.
    if any(v is None for v in raw_results.values()):
        return RiskContext(available=False, source="unavailable")

    return RiskContext(
        incident_active=bool(raw_results["incident_active"]),
        drift_severe=bool(raw_results["drift_severe"]),
        error_budget_exhausted=bool(raw_results["error_budget_exhausted"]),
        off_hours=_is_off_hours(),
        recent_rollback=False,  # populated by file path when invoked through get_risk_context
        available=True,
        source="prometheus",
        raw={"prometheus_queries": _PROMETHEUS_QUERIES, "results": raw_results},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_risk_context(
    *,
    ops_dir: Path | str = "ops",
    prometheus_url: str | None = None,
    cache_key: str = "default",
) -> RiskContext:
    """Return a :class:`RiskContext` honoring ADR-010 source priority.

    Results are cached for 60 seconds per cache_key so repeated
    invocations within a single agentic workflow do not amplify load.
    """
    now = time.time()
    if cache_key in _cache:
        ts, ctx = _cache[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return ctx

    prom_url = prometheus_url or os.getenv("PROMETHEUS_URL")
    ctx: RiskContext
    if prom_url:
        ctx = _load_prometheus_signals(prom_url)
        if not ctx.available:
            ctx = _load_file_signals(Path(ops_dir))
        else:
            # Prometheus has no `recent_rollback` metric — that signal is
            # backed by the local audit log. Fold it in so the dynamic
            # protocol does not silently lose it when Prometheus is up.
            file_ctx = _load_file_signals(Path(ops_dir))
            if file_ctx.recent_rollback and not ctx.recent_rollback:
                from dataclasses import replace

                ctx = replace(ctx, recent_rollback=True)
    else:
        ctx = _load_file_signals(Path(ops_dir))

    _cache[cache_key] = (now, ctx)
    return ctx


def render_audit_line(base_mode: Mode, final_mode: Mode, ctx: RiskContext) -> str:
    """Return a one-line human-readable summary for audit logs."""
    signals = []
    if ctx.incident_active:
        signals.append("incident_active")
    if ctx.drift_severe:
        signals.append("drift_severe")
    if ctx.error_budget_exhausted:
        signals.append("error_budget_exhausted")
    if ctx.off_hours:
        signals.append("off_hours")
    if ctx.recent_rollback:
        signals.append("recent_rollback")
    sig_str = ",".join(signals) if signals else "none"
    return f"mode={base_mode}→{final_mode} source={ctx.source} signals=[{sig_str}]"
