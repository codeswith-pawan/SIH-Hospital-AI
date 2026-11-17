"""
Phase 4D-4: Monitoring, Observability & Telemetry Test Suite
AI Powered Smart Hospital Referral System

Validates:
1. Liveness endpoint (/health/live) independence from database state.
2. Readiness endpoint (/health/ready) dependency validation (PostgreSQL, Redis).
3. Correlation Request ID: generation, passthrough, and malformed header sanitization.
4. Per-route metrics tracking with path normalization and PII exclusion.
5. In-flight request tracking and latency histogram bucketing.
6. Database connection pool monitoring and utilization calculations.
7. Outbox and reservation expiry worker heartbeats, stale detection, and independent identities.
8. Outbox telemetry: oldest pending message age and notification type breakdown.
9. Alert threshold evaluation engine: 5xx rate, latency, pool saturation, stale workers, deduplication.
10. Admin monitoring endpoint (/admin/monitoring): RBAC enforcement and PII exclusion.
"""

import time
import uuid
import re
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.pg_models import PgBase, WorkerHeartbeat, RegistrationEmailOutbox, Notification
from src.services.alerting_service import evaluate_thresholds, get_alert_summary, get_thresholds
from src.auth.jwt_utils import create_access_token


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================
# 1. HEALTH AND READINESS ENDPOINTS
# ============================================================

def test_liveness_probe_independent_of_database(client, monkeypatch):
    """Liveness probe must return UP even when database connectivity fails."""
    # Simulate complete database failure
    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "check_db_health", lambda: {"status": "UNHEALTHY", "error": "Connection refused"})

    res = client.get("/health/live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UP"
    assert "timestamp" in data


def test_readiness_probe_database_down(client, monkeypatch):
    """Readiness probe must report 503 and ready=False when database connectivity fails."""
    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "check_db_health", lambda: {"status": "UNHEALTHY", "error": "Connection refused"})

    res = client.get("/health/ready")
    assert res.status_code == 503
    data = res.json()
    assert data["ready"] is False
    assert data["database"]["status"] == "UNHEALTHY"


def test_readiness_probe_redis_down_when_required(client, monkeypatch):
    """Readiness probe must report 503 and ready=False when Redis is required and unavailable."""
    from src.config import get_settings, reset_settings
    monkeypatch.setenv("REDIS_URL", "redis://nonexistent:6379/0")
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    reset_settings()

    res = client.get("/health/ready")
    assert res.status_code == 503
    data = res.json()
    assert data["ready"] is False
    assert "UNHEALTHY" in data["redis"]["status"]

    reset_settings()


def test_readiness_probe_success(client, monkeypatch):
    """Readiness probe must report ready=True when database is healthy."""
    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "check_db_health", lambda: {"status": "HEALTHY", "dialect": "postgresql"})
    from src.config import reset_settings
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    reset_settings()

    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["database"]["status"] == "HEALTHY"

    reset_settings()


# ============================================================
# 2. CORRELATION REQUEST ID & SANITIZATION
# ============================================================

def test_request_id_generation_when_missing(client):
    """Missing X-Request-ID must be automatically generated with 'req_' prefix."""
    res = client.get("/health")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert req_id.startswith("req_")
    assert len(req_id) >= 16


def test_valid_request_id_preservation(client):
    """Valid X-Request-ID header must be preserved and returned."""
    custom_id = "test-corr-id_98765"
    res = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id


def test_malformed_request_id_sanitization(client):
    """Malformed or oversized X-Request-ID must be sanitized and replaced, never echoed raw."""
    malformed_ids = [
        "<script>alert('xss')</script>",
        "id with spaces and $pecial#chars!",
        "A" * 128,  # Exceeds 64 char limit
        "",  # Empty
    ]
    for bad_id in malformed_ids:
        res = client.get("/health", headers={"X-Request-ID": bad_id})
        assert res.status_code == 200
        clean_id = res.headers.get("X-Request-ID")
        assert clean_id is not None
        assert clean_id != bad_id
        assert clean_id.startswith("req_")
        assert re.match(r'^[a-zA-Z0-9_-]+$', clean_id)


# ============================================================
# 3. PER-ROUTE METRICS & PATH NORMALIZATION
# ============================================================

def test_per_route_metrics_and_path_normalization(client):
    """Route metrics must normalize identifiers to {id} and exclude PII from labels."""
    from src.api.observability import ROUTE_METRICS

    # Call an endpoint with dynamic path
    client.get("/hospitals/HOSP-MOHALI-01/inventory")

    # Verify per-route metrics has normalized entry
    matching = [k for k in ROUTE_METRICS.keys() if "GET" in k and "inventory" in k]
    assert len(matching) >= 1
    key = matching[0]
    # Path parameter must be normalized, not raw ID
    assert "{id}" in key
    assert "HOSP-MOHALI-01" not in key

    entry = ROUTE_METRICS[key]
    assert entry["count"] >= 1
    assert "total_duration_ms" in entry


def test_latency_histogram_and_in_flight(client):
    """Metrics must expose latency histogram buckets and in-flight counter."""
    from src.api.observability import get_system_metrics

    client.get("/health")
    metrics = get_system_metrics()

    assert "latency_histogram_seconds" in metrics
    buckets = metrics["latency_histogram_seconds"]
    assert 0.025 in buckets
    assert 1.0 in buckets
    assert "inf" in buckets

    # Sum of bucket counts must be >= total requests
    total_bucketed = sum(buckets.values())
    assert total_bucketed >= 1

    assert "in_flight_requests" in metrics
    assert isinstance(metrics["in_flight_requests"], int)


# ============================================================
# 4. DATABASE POOL MONITORING
# ============================================================

def test_postgresql_pool_stats_function():
    """get_pool_stats must return pool attributes safely without throwing."""
    from src.database.db_manager import get_pool_stats
    stats = get_pool_stats()
    assert isinstance(stats, dict)
    assert "pool_type" in stats
    assert "available" in stats


# ============================================================
# 5. WORKER HEARTBEATS & STALE DETECTION
# ============================================================

def test_worker_stale_heartbeat_detection(monkeypatch):
    """Heartbeat older than 90 seconds must be classified as STALE."""
    from src.api.observability import get_system_metrics

    # Create in-memory DB with WorkerHeartbeat table
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as s:
        # Outbox worker with stale heartbeat (200 seconds ago)
        s.add(WorkerHeartbeat(
            worker_name="outbox_worker",
            worker_id="outbox_01",
            status="RUNNING",
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=200),
            processed_total=50,
            failed_total=2,
        ))
        # Expiry worker with fresh heartbeat (10 seconds ago)
        s.add(WorkerHeartbeat(
            worker_name="reservation_expiry_worker",
            worker_id="expiry_01",
            status="RUNNING",
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=10),
            processed_total=10,
            failed_total=0,
        ))
        s.commit()

    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "get_session_factory", lambda: Session)

    metrics = get_system_metrics()

    # Outbox worker must be detected as STALE
    assert metrics["outbox_worker_status"] == "STALE"
    assert metrics["outbox_worker_running"] is False
    assert metrics["outbox_worker_heartbeat_age_seconds"] >= 190.0

    # Expiry worker must be detected as RUNNING
    assert metrics["reservation_expiry_worker"]["status"] == "RUNNING"
    assert metrics["reservation_expiry_worker_running"] is True


def test_independent_worker_identities(monkeypatch):
    """Outbox and Expiry workers must maintain independent identities and statuses."""
    from src.api.observability import get_system_metrics

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as s:
        s.add(WorkerHeartbeat(
            worker_name="outbox_worker",
            worker_id="outbox_worker_node_A",
            status="RUNNING",
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=15),
        ))
        s.add(WorkerHeartbeat(
            worker_name="reservation_expiry_worker",
            worker_id="expiry_worker_node_B",
            status="STOPPED",
            last_heartbeat=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        s.commit()

    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "get_session_factory", lambda: Session)

    metrics = get_system_metrics()

    assert metrics["outbox_worker_status"] == "RUNNING"
    assert metrics["outbox_worker_running"] is True

    assert metrics["reservation_expiry_worker"]["status"] == "STOPPED"
    assert metrics["reservation_expiry_worker_running"] is False


# ============================================================
# 6. NOTIFICATION & OUTBOX QUEUE TELEMETRY
# ============================================================

def test_outbox_oldest_pending_age_and_notification_types(monkeypatch):
    """Oldest pending outbox message age and unread notification types must be accurately reported."""
    from src.api.observability import get_system_metrics

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as s:
        # Add outbox items with known ages
        s.add(RegistrationEmailOutbox(
            outbox_id="OUT_OLD_01",
            event_type="APPLICATION_SUBMITTED",
            recipient_email="test@hospital.gov.in",
            subject="Application Submitted",
            payload="{}",
            status="PENDING",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        ))
        s.add(RegistrationEmailOutbox(
            outbox_id="OUT_NEW_02",
            event_type="NEW_REFERRAL",
            recipient_email="referral@hospital.gov.in",
            subject="New Referral",
            payload="{}",
            status="PENDING",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        ))
        # Add unread notifications
        s.add(Notification(
            event_type="NEW_REFERRAL",
            title="Referral Alert",
            message="Test message",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        ))
        s.add(Notification(
            event_type="LOW_BED_AVAILABILITY",
            title="Low Bed Alert",
            message="Critical capacity",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        ))
        s.commit()

    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "get_session_factory", lambda: Session)

    metrics = get_system_metrics()
    outbox = metrics["email_outbox_queue"]

    # Oldest pending age should be ~120s
    assert outbox["oldest_pending_age_seconds"] >= 115.0
    assert outbox["pending"] == 2

    # Unread notifications breakdown
    assert "unread_notifications_by_type" in outbox
    types = outbox["unread_notifications_by_type"]
    assert types.get("NEW_REFERRAL") == 1
    assert types.get("LOW_BED_AVAILABILITY") == 1


# ============================================================
# 7. ALERT THRESHOLDS ENGINE & DEDUPLICATION
# ============================================================

def test_alert_threshold_evaluation_and_deduplication():
    """Alert engine must trigger alerts on exceeded thresholds and deduplicate within cooldown."""
    # Mock metrics crossing thresholds
    metrics = {
        "server": {
            "total_requests": 100,
            "status_5xx": 10,  # 10% > 5% threshold
            "average_latency_ms": 1500.0,  # 1500ms > 1000ms threshold
        },
        "pool_stats": {
            "utilization_pct": 92.0,  # 92% > 85% threshold
        },
        "outbox_worker_heartbeat_age_seconds": 180.0,  # 180s > 120s threshold
        "reservation_expiry_worker": {
            "heartbeat_age_seconds": 250.0,  # 250s > 120s threshold
        },
        "email_outbox_queue": {
            "oldest_pending_age_seconds": 450.0,  # 450s > 300s threshold
            "failed": 15,  # 15 > 10 threshold
        },
    }

    # First evaluation -> alerts should trigger as is_new=True
    alerts = evaluate_thresholds(metrics)
    assert len(alerts) >= 5

    alert_keys = [a["key"] for a in alerts]
    assert "api_5xx_rate" in alert_keys
    assert "api_latency_high" in alert_keys
    assert "db_pool_saturation" in alert_keys
    assert "outbox_worker_stale" in alert_keys
    assert "expiry_worker_stale" in alert_keys
    assert "outbox_pending_age" in alert_keys
    assert "outbox_failed_count" in alert_keys

    # Check alert summary
    summary = get_alert_summary()
    assert summary["status"] == "CRITICAL"
    assert summary["critical_count"] >= 3

    # Second immediate evaluation -> alerts must be deduplicated (is_new=False)
    alerts_second = evaluate_thresholds(metrics)
    assert len(alerts_second) == len(alerts)
    for a in alerts_second:
        assert a["is_new"] is False


def test_alert_recovery_when_below_threshold():
    """Alerts must clear when metrics return below thresholds."""
    healthy_metrics = {
        "server": {
            "total_requests": 100,
            "status_5xx": 1,  # 1% < 5% threshold
            "average_latency_ms": 120.0,  # 120ms < 1000ms threshold
        },
        "pool_stats": {
            "utilization_pct": 30.0,  # 30% < 85% threshold
        },
        "outbox_worker_heartbeat_age_seconds": 10.0,  # Fresh
        "reservation_expiry_worker": {
            "heartbeat_age_seconds": 15.0,  # Fresh
        },
        "email_outbox_queue": {
            "oldest_pending_age_seconds": 20.0,  # Normal
            "failed": 0,
        },
    }

    alerts = evaluate_thresholds(healthy_metrics)
    assert len(alerts) == 0

    summary = get_alert_summary()
    assert summary["status"] == "HEALTHY"
    assert summary["total_active"] == 0


# ============================================================
# 8. ADMIN MONITORING DASHBOARD API & RBAC
# ============================================================

def test_admin_monitoring_endpoint_rbac(client):
    """GET /admin/monitoring must require CENTRAL_ADMIN role."""
    # 1. Unauthenticated -> 401
    res_unauth = client.get("/admin/monitoring")
    assert res_unauth.status_code == 401

    # 2. Hospital role -> 403 Forbidden
    token_hosp = create_access_token({"user_id": "U_HOSP", "role": "HOSPITAL", "hospital_id": "HOSP-01"})
    res_hosp = client.get("/admin/monitoring", headers={"Authorization": f"Bearer {token_hosp}"})
    assert res_hosp.status_code == 403

    # 3. District Admin -> 403 Forbidden
    token_dist = create_access_token({"user_id": "U_DIST", "role": "DISTRICT_ADMIN", "district": "Mohali"})
    res_dist = client.get("/admin/monitoring", headers={"Authorization": f"Bearer {token_dist}"})
    assert res_dist.status_code == 403

    # 4. Central Admin -> 200 OK
    token_central = create_access_token({"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"})
    res_central = client.get("/admin/monitoring", headers={"Authorization": f"Bearer {token_central}"})
    assert res_central.status_code == 200

    data = res_central.json()
    assert "system_metrics" in data
    assert "alerts" in data
    assert data["dashboard_version"] == "4D-4"
    assert "generated_at" in data

    # Verify no credentials or secret keys are exposed
    payload_str = str(data)
    assert "password_hash" not in payload_str.lower()
    assert "smtp_password" not in payload_str.lower()
    assert "jwt_secret" not in payload_str.lower()
    assert "patient_id" not in payload_str.lower()
    assert "patient_name" not in payload_str.lower()
