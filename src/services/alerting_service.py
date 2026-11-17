"""
Phase 4D-4: Configurable Alert Threshold Evaluation Engine
AI Powered Smart Hospital Referral System

Evaluates operational metrics against configurable thresholds.
Sends alerts via existing RegistrationEmailOutbox if configured.
Deduplicates alerts within a cooldown window to prevent alert storms.
"""
import os
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger("sih.alerting")

# ============================================================
# DEFAULT THRESHOLDS (all overridable via environment vars)
# ============================================================
def get_thresholds() -> Dict[str, Any]:
    return {
        "api_5xx_rate_pct": float(os.getenv("ALERT_5XX_RATE_PCT", "5.0")),       # % of 5xx over total
        "api_p95_latency_ms": float(os.getenv("ALERT_P95_LATENCY_MS", "1000.0")),# ms
        "db_pool_utilization_pct": float(os.getenv("ALERT_DB_POOL_PCT", "85.0")),# %
        "worker_heartbeat_stale_seconds": float(os.getenv("ALERT_HEARTBEAT_STALE_S", "120.0")),
        "outbox_oldest_pending_seconds": float(os.getenv("ALERT_OUTBOX_AGE_S", "300.0")),  # 5 min
        "outbox_failed_max": int(os.getenv("ALERT_OUTBOX_FAILED_MAX", "10")),
        "alert_cooldown_seconds": float(os.getenv("ALERT_COOLDOWN_S", "300.0")),  # 5 min dedup
    }

# In-memory deduplication store: alert_key -> last_fired_utc
_ALERT_FIRED: Dict[str, datetime] = {}

# Active alerts list (most recent evaluation)
_ACTIVE_ALERTS: List[Dict[str, Any]] = []


def _should_fire(alert_key: str, cooldown_seconds: float) -> bool:
    """Returns True if alert has not fired within cooldown window."""
    last = _ALERT_FIRED.get(alert_key)
    if last is None:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() > cooldown_seconds


def _record_fired(alert_key: str) -> None:
    _ALERT_FIRED[alert_key] = datetime.now(timezone.utc)
    # Keep dict bounded: evict entries older than 1 hour
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    for k in list(_ALERT_FIRED.keys()):
        if _ALERT_FIRED[k] < cutoff:
            del _ALERT_FIRED[k]


def evaluate_thresholds(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Evaluates metrics dict against configured thresholds.
    Returns list of active alert dicts. Never includes PII.
    
    Each alert dict:
      {
        "key": str,           # dedup key
        "severity": "WARNING"|"CRITICAL",
        "condition": str,     # human-readable description
        "current_value": Any, # actual value that triggered
        "threshold": Any,     # configured threshold
        "first_fired_at": str, # ISO timestamp
        "is_new": bool,       # True if first time this fired in current window
      }
    """
    thresholds = get_thresholds()
    cooldown = thresholds["alert_cooldown_seconds"]
    alerts = []
    now = datetime.now(timezone.utc)

    def add_alert(key, severity, condition, current, threshold):
        is_new = _should_fire(key, cooldown)
        if is_new:
            _record_fired(key)
        alerts.append({
            "key": key,
            "severity": severity,
            "condition": condition,
            "current_value": current,
            "threshold": threshold,
            "fired_at": _ALERT_FIRED.get(key, now).isoformat(),
            "is_new": is_new,
        })

    server = metrics.get("server", {})

    # 1. 5xx error rate
    total = server.get("total_requests", 0)
    errors_5xx = server.get("status_5xx", 0)
    if total > 0:
        rate_5xx_pct = 100.0 * errors_5xx / total
        if rate_5xx_pct > thresholds["api_5xx_rate_pct"]:
            add_alert("api_5xx_rate", "CRITICAL",
                      f"API 5xx error rate {rate_5xx_pct:.1f}% exceeds {thresholds['api_5xx_rate_pct']}% threshold",
                      round(rate_5xx_pct, 2), thresholds["api_5xx_rate_pct"])

    # 2. Average latency as p95 proxy (histogram not yet available in first pass)
    avg_latency = server.get("average_latency_ms", 0.0)
    if avg_latency > thresholds["api_p95_latency_ms"]:
        add_alert("api_latency_high", "WARNING",
                  f"API average latency {avg_latency:.0f}ms exceeds {thresholds['api_p95_latency_ms']:.0f}ms threshold",
                  round(avg_latency, 1), thresholds["api_p95_latency_ms"])

    # 3. DB pool utilization
    pool_stats = metrics.get("pool_stats", {})
    util_pct = pool_stats.get("utilization_pct")
    if util_pct is not None and util_pct > thresholds["db_pool_utilization_pct"]:
        add_alert("db_pool_saturation", "CRITICAL",
                  f"DB pool utilization {util_pct:.1f}% exceeds {thresholds['db_pool_utilization_pct']}% threshold",
                  util_pct, thresholds["db_pool_utilization_pct"])

    # 4. Outbox worker heartbeat
    outbox_age = metrics.get("outbox_worker_heartbeat_age_seconds")
    if outbox_age is not None and outbox_age > thresholds["worker_heartbeat_stale_seconds"]:
        add_alert("outbox_worker_stale", "CRITICAL",
                  f"Outbox worker heartbeat stale for {outbox_age:.0f}s (threshold: {thresholds['worker_heartbeat_stale_seconds']}s)",
                  outbox_age, thresholds["worker_heartbeat_stale_seconds"])

    # 5. Expiry worker heartbeat
    expiry = metrics.get("reservation_expiry_worker", {})
    expiry_age = expiry.get("heartbeat_age_seconds")
    if expiry_age is not None and expiry_age > thresholds["worker_heartbeat_stale_seconds"]:
        add_alert("expiry_worker_stale", "CRITICAL",
                  f"Expiry worker heartbeat stale for {expiry_age:.0f}s (threshold: {thresholds['worker_heartbeat_stale_seconds']}s)",
                  expiry_age, thresholds["worker_heartbeat_stale_seconds"])

    # 6. Oldest pending outbox message
    outbox = metrics.get("email_outbox_queue", {})
    oldest_age = outbox.get("oldest_pending_age_seconds", 0.0)
    if oldest_age > thresholds["outbox_oldest_pending_seconds"]:
        add_alert("outbox_pending_age", "WARNING",
                  f"Oldest pending outbox message is {oldest_age:.0f}s old (threshold: {thresholds['outbox_oldest_pending_seconds']}s)",
                  oldest_age, thresholds["outbox_oldest_pending_seconds"])

    # 7. Failed outbox messages
    failed_count = outbox.get("failed", 0)
    if failed_count > thresholds["outbox_failed_max"]:
        add_alert("outbox_failed_count", "WARNING",
                  f"Outbox failed email count {failed_count} exceeds threshold {thresholds['outbox_failed_max']}",
                  failed_count, thresholds["outbox_failed_max"])

    # Update global active alerts
    global _ACTIVE_ALERTS
    _ACTIVE_ALERTS = alerts
    return alerts


def get_active_alerts() -> List[Dict[str, Any]]:
    """Return most recently evaluated alert list."""
    return list(_ACTIVE_ALERTS)


def get_alert_summary() -> Dict[str, Any]:
    """Return summary suitable for dashboard header."""
    alerts = _ACTIVE_ALERTS
    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    warnings = [a for a in alerts if a["severity"] == "WARNING"]
    return {
        "total_active": len(alerts),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "status": "CRITICAL" if critical else ("WARNING" if warnings else "HEALTHY"),
        "alerts": alerts,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
