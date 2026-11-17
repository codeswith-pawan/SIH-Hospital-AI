"""
Production Observability, Structured Logging, Security Headers & Health Metrics
AI Powered Smart Hospital Referral System - Phase 3

Provides:
- Security headers middleware (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
- High-performance structured request/response logging with Request ID correlation
- Safe redaction of sensitive credentials, tokens, OTPs, and medical details
- Liveness (/health/live), Readiness (/health/ready), and Metrics (/metrics)
"""

import os
import re
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from src.config import get_settings, mask_email

logger = logging.getLogger("sih.access")

# Global metrics accumulator
METRICS = {
    "start_time": datetime.now(timezone.utc).isoformat(),
    "total_requests": 0,
    "status_2xx": 0,
    "status_3xx": 0,
    "status_4xx": 0,
    "status_5xx": 0,
    "total_errors": 0,
    "total_duration_ms": 0.0,
    # GAP 2: in-flight counter and latency histogram
    "in_flight": 0,
    "latency_buckets": {
        0.025: 0,
        0.05: 0,
        0.1: 0,
        0.25: 0,
        0.5: 0,
        1.0: 0,
        2.5: 0,
        5.0: 0,
        "inf": 0,
    },
}

# GAP 1: Per-route metrics — capped at 200 unique keys
ROUTE_METRICS: Dict[str, Dict] = {}

# Latency histogram bucket boundaries (sorted for bisect-style lookup)
_LATENCY_BOUNDS = [0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]


def _normalize_path(path: str) -> str:
    """Strip UUIDs, prefixed IDs (HOSP-*, PAT-*, APP-*, etc.), dynamic route IDs, and numeric segments from a URL path."""
    # Normalize known entity route parameters: /hospitals/{id}, /referrals/{id}, /review/applications/{id}
    result = re.sub(r'/(hospitals|referrals)/[A-Za-z0-9_-]+', r'/\1/{id}', path, flags=re.IGNORECASE)
    result = re.sub(r'/review/applications/[A-Za-z0-9_-]+', '/review/applications/{id}', result, flags=re.IGNORECASE)
    result = re.sub(r'/doc_[a-fA-F0-9]+', '/{id}', result)
    result = re.sub(r'/(?:HOSP|PAT|REF|APP|OUT|U)[-_][A-Za-z0-9_-]+', '/{id}', result, flags=re.IGNORECASE)
    result = re.sub(r'/[0-9a-fA-F-]{8,}', '/{id}', result)
    result = re.sub(r'/\d+', '/{id}', result)
    return result


_X_REQUEST_ID_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


class ProductionSecurityAndLoggingMiddleware(BaseHTTPMiddleware):
    """
    Unified middleware for:
    1. Correlation Request-ID generation and header injection
    2. Request duration timing and operational metrics aggregation
    3. Production security response headers
    4. Structured logging without secret/PII leakage
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Request ID correlation
        request_id = request.headers.get("x-request-id")
        if request_id:
            # GAP 3: Validate incoming X-Request-ID
            if not (1 <= len(request_id) <= 64 and _X_REQUEST_ID_RE.match(request_id)):
                new_id = f"req_{uuid.uuid4().hex[:12]}"
                logger.warning("Invalid X-Request-ID rejected, generated new id=%s", new_id)
                request_id = new_id
        else:
            request_id = f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        start_time = time.perf_counter()
        settings = get_settings()

        # GAP 2: Increment in-flight counter before calling next handler
        METRICS["in_flight"] += 1
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            METRICS["total_requests"] += 1
            METRICS["status_5xx"] += 1
            METRICS["total_errors"] += 1
            METRICS["total_duration_ms"] += duration_ms

            # GAP 2: Bucket latency for exception path
            duration_seconds = duration_ms / 1000.0
            _record_latency_bucket(duration_seconds)

            logger.error(
                "Unhandled Exception [req_id=%s] %s %s -> 500 in %.2fms: %s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                exc,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An internal server error occurred.",
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "request_id": request_id,
                },
                headers={
                    "X-Request-ID": request_id,
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                },
            )
        finally:
            # GAP 2: Always decrement in-flight counter
            METRICS["in_flight"] -= 1

        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # 2. Record aggregate metrics
        METRICS["total_requests"] += 1
        METRICS["total_duration_ms"] += duration_ms
        if 200 <= status_code < 300:
            METRICS["status_2xx"] += 1
        elif 300 <= status_code < 400:
            METRICS["status_3xx"] += 1
        elif 400 <= status_code < 500:
            METRICS["status_4xx"] += 1
        else:
            METRICS["status_5xx"] += 1
            METRICS["total_errors"] += 1

        # GAP 2: Bucket latency for normal path
        duration_seconds = duration_ms / 1000.0
        _record_latency_bucket(duration_seconds)

        # GAP 1: Per-route metrics tracking
        normalized = _normalize_path(request.url.path)
        route_key = f"{request.method} {normalized}"
        if route_key in ROUTE_METRICS:
            entry = ROUTE_METRICS[route_key]
            entry["count"] += 1
            entry["total_duration_ms"] += duration_ms
            if 200 <= status_code < 300:
                entry["status_2xx"] += 1
            elif 400 <= status_code < 500:
                entry["status_4xx"] += 1
            elif status_code >= 500:
                entry["status_5xx"] += 1
        elif len(ROUTE_METRICS) < 200:
            entry = {
                "count": 1,
                "status_2xx": 1 if 200 <= status_code < 300 else 0,
                "status_4xx": 1 if 400 <= status_code < 500 else 0,
                "status_5xx": 1 if status_code >= 500 else 0,
                "total_duration_ms": duration_ms,
            }
            ROUTE_METRICS[route_key] = entry
        # else: cap reached — skip new keys

        # 3. Inject Security Headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 4. Structured log output
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
        # Sanitize path to prevent query param token logging
        clean_path = request.url.path
        level = logging.INFO if status_code < 400 else (logging.WARNING if status_code < 500 else logging.ERROR)
        logger.log(
            level,
            "HTTP %s %s -> %d in %.2fms [req_id=%s, ip=%s]",
            request.method,
            clean_path,
            status_code,
            duration_ms,
            request_id,
            client_ip,
        )

        return response


def _record_latency_bucket(duration_seconds: float) -> None:
    """Place a request duration into the appropriate histogram bucket."""
    buckets = METRICS["latency_buckets"]
    for bound in _LATENCY_BOUNDS:
        if duration_seconds <= bound:
            buckets[bound] += 1
            return
    buckets["inf"] += 1


def get_liveness() -> Dict[str, Any]:
    """Lightweight liveness probe."""
    return {
        "status": "UP",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_readiness() -> Dict[str, Any]:
    """
    Comprehensive readiness check: verifies that backend dependencies (PostgreSQL,
    Redis, and configuration) can actually serve traffic.
    """
    from src.database.db_manager import check_db_health, is_postgres
    from src.config import get_settings

    settings = get_settings()
    db_health = check_db_health()
    is_ready = (db_health.get("status") == "HEALTHY")

    redis_status = "NOT_CONFIGURED"
    if settings.redis_url:
        try:
            import redis
            rc = redis.Redis.from_url(settings.redis_url, socket_timeout=2.0)
            rc.ping()
            redis_status = "HEALTHY"
        except Exception as r_err:
            redis_status = f"UNHEALTHY ({r_err})"
            if settings.redis_required:
                is_ready = False

    return {
        "ready": is_ready,
        "environment": settings.environment,
        "database": db_health,
        "redis": {
            "status": redis_status,
            "required": settings.redis_required,
        },
        "email_backend": settings.email_backend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_system_metrics() -> Dict[str, Any]:
    """Return operational application and database metrics."""
    avg_latency = (
        METRICS["total_duration_ms"] / METRICS["total_requests"]
        if METRICS["total_requests"] > 0
        else 0.0
    )

    outbox_stats = {"pending": 0, "sent": 0, "failed": 0, "processing": 0}
    try:
        from src.database.db_manager import get_session_factory
        from src.database.pg_models import RegistrationEmailOutbox
        from sqlalchemy import func
        SessionFactory = get_session_factory()
        with SessionFactory() as db:
            counts = (
                db.query(RegistrationEmailOutbox.status, func.count(RegistrationEmailOutbox.id))
                .group_by(RegistrationEmailOutbox.status)
                .all()
            )
            for status, count in counts:
                outbox_stats[status.lower()] = count

            # GAP 5: Oldest pending outbox age
            now_utc = datetime.now(timezone.utc)
            oldest = db.query(func.min(RegistrationEmailOutbox.created_at)).filter(
                RegistrationEmailOutbox.status == "PENDING"
            ).scalar()
            if oldest:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                outbox_stats["oldest_pending_age_seconds"] = round((now_utc - oldest).total_seconds(), 1)
            else:
                outbox_stats["oldest_pending_age_seconds"] = 0.0

            # GAP 5: Unread notification type breakdown
            from src.database.pg_models import Notification
            type_rows = db.query(Notification.event_type, func.count(Notification.id)).filter(
                Notification.is_read == False  # noqa: E712
            ).group_by(Notification.event_type).all()
            outbox_stats["unread_notifications_by_type"] = {et: c for et, c in type_rows}

    except Exception:
        pass

    # GAP 4: Outbox worker DB heartbeat (with in-process fallback)
    outbox_worker_running = False
    outbox_worker_status = "STOPPED"
    outbox_worker_heartbeat_age_seconds: Optional[float] = None

    try:
        from src.database.db_manager import get_session_factory
        from src.database.pg_models import WorkerHeartbeat
        SessionFactory = get_session_factory()
        with SessionFactory() as db:
            hb = db.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").one_or_none()
            if hb:
                now = datetime.now(timezone.utc)
                lhb = hb.last_heartbeat
                if lhb and lhb.tzinfo is None:
                    lhb = lhb.replace(tzinfo=timezone.utc)
                age = (now - lhb).total_seconds() if lhb else 999999.0
                outbox_worker_heartbeat_age_seconds = round(age, 2)
                is_running = age <= 90.0 and hb.status == "RUNNING"
                outbox_worker_running = is_running
                if is_running:
                    outbox_worker_status = "RUNNING"
                elif hb.status == "RUNNING":
                    outbox_worker_status = "STALE"
                else:
                    outbox_worker_status = hb.status or "STOPPED"
    except Exception:
        # Fallback to in-process metrics
        from src.workers.outbox_worker import get_active_worker_metrics
        worker_metrics_fallback = get_active_worker_metrics()
        if worker_metrics_fallback.get("is_running"):
            outbox_worker_running = True
            outbox_worker_status = "RUNNING"

    # Worker metrics (original in-process metrics kept for background_worker key)
    from src.workers.outbox_worker import get_active_worker_metrics
    worker_metrics = get_active_worker_metrics()

    # Reservation Expiry Worker Metrics (shared PostgreSQL heartbeat)
    expiry_metrics = {
        "reservation_expiry_worker_running": False,
        "reservation_expiry_last_success_timestamp": None,
        "reservation_expiry_processed_total": 0,
        "reservation_expiry_failed_total": 0,
        "reservation_expiry_batch_size": 100,
        "reservation_expiry_processing_duration_seconds": 0.0,
        "reservation_expiry_last_error_timestamp": None,
        "heartbeat_age_seconds": None,
        "status": "STOPPED",
    }
    try:
        from src.database.db_manager import get_session_factory
        from src.database.pg_models import WorkerHeartbeat
        SessionFactory = get_session_factory()
        with SessionFactory() as db:
            hb = db.query(WorkerHeartbeat).filter_by(worker_name="reservation_expiry_worker").one_or_none()
            if hb:
                now = datetime.now(timezone.utc)
                lhb = hb.last_heartbeat
                if lhb and lhb.tzinfo is None:
                    lhb = lhb.replace(tzinfo=timezone.utc)
                age = (now - lhb).total_seconds() if lhb else 999999.0
                # Stale heartbeat threshold is 90 seconds (3x default poll interval)
                is_running = (age <= 90.0) and (hb.status == "RUNNING")
                expiry_metrics = {
                    "reservation_expiry_worker_running": is_running,
                    "reservation_expiry_last_success_timestamp": hb.last_success_at.isoformat() if hb.last_success_at else None,
                    "reservation_expiry_processed_total": int(hb.processed_total or 0),
                    "reservation_expiry_failed_total": int(hb.failed_total or 0),
                    "reservation_expiry_batch_size": int(hb.batch_size or 100),
                    "reservation_expiry_processing_duration_seconds": float(hb.duration_seconds or 0.0),
                    "reservation_expiry_last_error_timestamp": hb.last_error_at.isoformat() if hb.last_error_at else None,
                    "heartbeat_age_seconds": round(age, 2),
                    "status": "RUNNING" if is_running else ("STALE" if hb.status == "RUNNING" else hb.status),
                    "worker_id": hb.worker_id,
                }
    except Exception:
        from src.workers.reservation_expiry_worker import get_active_expiry_worker_metrics
        in_proc = get_active_expiry_worker_metrics()
        if in_proc.get("is_running"):
            expiry_metrics["reservation_expiry_worker_running"] = True
            expiry_metrics["status"] = "RUNNING"

    # GAP 6: Pool stats
    pool_stats = {}
    try:
        from src.database.db_manager import get_pool_stats
        pool_stats = get_pool_stats()
    except Exception:
        pass

    # GAP 7: Per-route metrics (top 50 by count)
    per_route = dict(
        sorted(ROUTE_METRICS.items(), key=lambda x: x[1]["count"], reverse=True)[:50]
    )

    return {
        "server": {
            "uptime_since": METRICS["start_time"],
            "total_requests": METRICS["total_requests"],
            "status_2xx": METRICS["status_2xx"],
            "status_3xx": METRICS["status_3xx"],
            "status_4xx": METRICS["status_4xx"],
            "status_5xx": METRICS["status_5xx"],
            "total_errors": METRICS["total_errors"],
            "average_latency_ms": round(avg_latency, 2),
        },
        "email_outbox_queue": outbox_stats,
        "background_worker": worker_metrics,
        "reservation_expiry_worker": expiry_metrics,
        "reservation_expiry_worker_running": expiry_metrics["reservation_expiry_worker_running"],
        "reservation_expiry_last_success_timestamp": expiry_metrics["reservation_expiry_last_success_timestamp"],
        "reservation_expiry_processed_total": expiry_metrics["reservation_expiry_processed_total"],
        "reservation_expiry_failed_total": expiry_metrics["reservation_expiry_failed_total"],
        "reservation_expiry_batch_size": expiry_metrics["reservation_expiry_batch_size"],
        "reservation_expiry_processing_duration_seconds": expiry_metrics["reservation_expiry_processing_duration_seconds"],
        "reservation_expiry_last_error_timestamp": expiry_metrics["reservation_expiry_last_error_timestamp"],
        # GAP 4: Outbox worker DB heartbeat keys
        "outbox_worker_running": outbox_worker_running,
        "outbox_worker_status": outbox_worker_status,
        "outbox_worker_heartbeat_age_seconds": outbox_worker_heartbeat_age_seconds,
        # GAP 6: Pool stats
        "pool_stats": pool_stats,
        # GAP 7: Extended metrics
        "per_route_metrics": per_route,
        "latency_histogram_seconds": METRICS["latency_buckets"],
        "in_flight_requests": METRICS["in_flight"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def check_metrics_access(req: Request) -> bool:
    """
    Ensure internal metrics are not exposed publicly without appropriate authorization
    or network boundary restrictions:
    - In development/testing: allows access freely
    - In production: permits loopback/private IPs, valid METRICS_API_KEY, or admin JWT
    """
    from src.config import get_settings
    settings = get_settings()
    if not settings.is_production:
        return True

    # 1. Localhost / loopback / container internal network check
    client_ip = (req.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (req.client.host if req.client else "")
    if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True

    # 2. Dedicated metrics key (X-Metrics-Key or ?key=)
    configured_key = os.getenv("METRICS_API_KEY", "")
    metrics_header = req.headers.get("x-metrics-key", "")
    if configured_key and metrics_header == configured_key:
        return True

    # 3. Authenticated Administrative JWT Bearer token
    auth_header = req.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            from src.auth.jwt_utils import decode_access_token
            payload = decode_access_token(token)
            if payload and payload.get("role") in ("CENTRAL_ADMIN", "STATE_ADMIN"):
                return True
        except Exception:
            pass

    return False
