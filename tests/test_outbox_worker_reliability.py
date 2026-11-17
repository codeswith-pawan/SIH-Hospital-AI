"""
Phase 3 Worker Reliability Test Suite
AI Powered Smart Hospital Referral System

Validates:
1. Pending event processing
2. Successful delivery & status update to SENT
3. Failed delivery & exponential backoff calculation
4. Retry behavior & max_retries permanent failure
5. Expired worker lease recovery (crash resilience)
6. Worker graceful shutdown on stop event
7. Concurrent worker isolation (no double dispatch)
8. Duplicate event handling & at-least-once delivery guarantees
"""

import time
import json
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.pg_models import PgBase, RegistrationEmailOutbox
from src.services.email_service import SimulatedEmailProvider
from src.services.email_outbox_service import EmailOutboxService
from src.workers.outbox_worker import OutboxWorker


@pytest.fixture
def memory_db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return Session


def test_worker_pending_events_success(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()
    outbox_svc = EmailOutboxService(session, sim_email)

    evt = outbox_svc.enqueue_email(
        event_type="GENERIC_NOTIFICATION",
        recipient_email="success@domain.gov.in",
        subject="Welcome",
        payload={"body_text": "Hello world."},
    )
    session.commit()
    outbox_id = evt.outbox_id
    session.close()

    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="test_worker_1")
    summary = worker.run_once()

    assert summary["processed"] == 1
    assert summary["succeeded"] == 1
    assert summary["failed"] == 0

    verify_session = memory_db_factory()
    reloaded = verify_session.query(RegistrationEmailOutbox).filter_by(outbox_id=outbox_id).first()
    assert reloaded.status == "SENT"
    assert reloaded.sent_at is not None
    assert len(sim_email.sent_emails) == 1
    verify_session.close()


def test_worker_failed_delivery_exponential_backoff(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()
    sim_email.fail_next = True  # Force delivery exception

    outbox_svc = EmailOutboxService(session, sim_email)
    evt = outbox_svc.enqueue_email(
        event_type="GENERIC_NOTIFICATION",
        recipient_email="fail@domain.gov.in",
        subject="Alert",
        payload={"body_text": "Failing message."},
        max_retries=3,
    )
    session.commit()
    outbox_id = evt.outbox_id
    session.close()

    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="test_worker_2")
    summary = worker.run_once()

    assert summary["processed"] == 1
    assert summary["failed"] == 1
    assert summary["succeeded"] == 0

    verify_session = memory_db_factory()
    reloaded = verify_session.query(RegistrationEmailOutbox).filter_by(outbox_id=outbox_id).first()
    assert reloaded.status == "FAILED"
    assert reloaded.retry_count == 1
    assert reloaded.next_retry_at is not None
    next_retry = reloaded.next_retry_at.replace(tzinfo=timezone.utc) if reloaded.next_retry_at.tzinfo is None else reloaded.next_retry_at
    assert next_retry > datetime.now(timezone.utc) - timedelta(seconds=5)
    verify_session.close()


def test_worker_max_retries_permanent_failure(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()
    sim_email.fail_next = True

    outbox_svc = EmailOutboxService(session, sim_email)
    evt = outbox_svc.enqueue_email(
        event_type="GENERIC_NOTIFICATION",
        recipient_email="max_retries@domain.gov.in",
        subject="Alert",
        payload={"body_text": "Failing message."},
        max_retries=1,  # Only 1 retry allowed
    )
    session.commit()
    outbox_id = evt.outbox_id
    session.close()

    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="test_worker_3")
    worker.run_once()

    verify_session = memory_db_factory()
    reloaded = verify_session.query(RegistrationEmailOutbox).filter_by(outbox_id=outbox_id).first()
    assert reloaded.status == "FAILED"
    assert reloaded.retry_count == 1
    verify_session.close()

    # Second pass: retry_count is 1 which equals max_retries, so it must not be picked up again
    sim_email.fail_next = False
    pass2 = worker.run_once()
    assert pass2["processed"] == 0


def test_worker_expired_lease_recovery(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()

    # Simulate an abandoned event stuck in PROCESSING from a crashed worker 10 minutes ago
    ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    abandoned_evt = RegistrationEmailOutbox(
        outbox_id="OUT_CRASHED_WORKER_01",
        event_type="GENERIC_NOTIFICATION",
        recipient_email="crashed@domain.gov.in",
        subject="Recover Me",
        payload=json.dumps({"body_text": "Recover after crash."}),
        status="PROCESSING",
        retry_count=0,
        max_retries=3,
        processed_at=ten_min_ago,
        created_at=ten_min_ago,
    )
    session.add(abandoned_evt)
    session.commit()
    session.close()

    worker = OutboxWorker(
        session_factory=memory_db_factory,
        email_provider=sim_email,
        worker_id="recovering_worker",
        lease_timeout_seconds=300,  # 5 minutes
    )
    summary = worker.run_once()

    assert summary["reclaimed"] == 1
    assert summary["succeeded"] == 1

    verify_session = memory_db_factory()
    reloaded = verify_session.query(RegistrationEmailOutbox).filter_by(outbox_id="OUT_CRASHED_WORKER_01").first()
    assert reloaded.status == "SENT"
    assert reloaded.sent_at is not None
    verify_session.close()


def test_worker_shutdown_and_stop_event(memory_db_factory):
    sim_email = SimulatedEmailProvider()
    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="shutdown_test_worker")

    assert not worker._stop_event.is_set()
    worker.stop()
    assert worker._stop_event.is_set()

    metrics = worker.get_metrics()
    assert metrics["is_running"] is False
    assert metrics["worker_id"] == "shutdown_test_worker"


def test_concurrent_worker_isolation(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()
    outbox_svc = EmailOutboxService(session, sim_email)

    # Enqueue 3 events
    for i in range(3):
        outbox_svc.enqueue_email(
            event_type="GENERIC_NOTIFICATION",
            recipient_email=f"recipient_{i}@domain.gov.in",
            subject=f"Subject {i}",
            payload={"body_text": f"Body {i}"},
        )
    session.commit()
    session.close()

    worker_a = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="worker_A", batch_size=2)
    worker_b = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="worker_B", batch_size=2)

    res_a = worker_a.run_once()
    res_b = worker_b.run_once()

    total_processed = res_a["processed"] + res_b["processed"]
    assert total_processed == 3
    assert len(sim_email.sent_emails) == 3


def test_duplicate_event_handling_already_sent(memory_db_factory):
    session = memory_db_factory()
    sim_email = SimulatedEmailProvider()
    outbox_svc = EmailOutboxService(session, sim_email)

    evt = outbox_svc.enqueue_email(
        event_type="GENERIC_NOTIFICATION",
        recipient_email="already_sent@domain.gov.in",
        subject="Single Delivery",
        payload={"body_text": "One-time only."},
    )
    session.commit()
    outbox_id = evt.outbox_id

    # Process first time
    res1 = outbox_svc.process_event(outbox_id)
    assert res1["status"] == "SENT"
    assert len(sim_email.sent_emails) == 1

    # Attempt to process same event again
    res2 = outbox_svc.process_event(outbox_id)
    assert res2["status"] == "ALREADY_SENT"
    assert len(sim_email.sent_emails) == 1  # No duplicate dispatch
    session.close()


def test_outbox_worker_heartbeat_and_healthcheck(memory_db_factory):
    """Verify that OutboxWorker records heartbeats and reports healthy via check_worker_health."""
    from src.database.pg_models import WorkerHeartbeat
    from src.workers.outbox_worker import check_worker_health

    sim_email = SimulatedEmailProvider()
    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="hb_test_worker")

    # Before running, healthcheck must return False (no heartbeat row)
    assert check_worker_health(session_factory=memory_db_factory) is False

    # Execute one pass
    summary = worker.run_once()
    assert summary["worker_id"] == "hb_test_worker"

    # Verify heartbeat record exists in database
    session = memory_db_factory()
    hb = session.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").first()
    assert hb is not None
    assert hb.status == "RUNNING"
    assert hb.worker_id == "hb_test_worker"
    assert hb.last_heartbeat is not None
    session.close()

    # Healthcheck must now report True
    assert check_worker_health(session_factory=memory_db_factory) is True


def test_outbox_worker_healthcheck_stale_and_stopped_detection(memory_db_factory):
    """Verify that stale heartbeats and STOPPED status fail the healthcheck probe."""
    from src.database.pg_models import WorkerHeartbeat
    from src.workers.outbox_worker import check_worker_health

    sim_email = SimulatedEmailProvider()
    worker = OutboxWorker(session_factory=memory_db_factory, email_provider=sim_email, worker_id="stale_test_worker")
    worker.run_once()

    # Stale detection: threshold is 10s, but heartbeat is set to 20s ago
    session = memory_db_factory()
    hb = session.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").one()
    twenty_sec_ago = datetime.now(timezone.utc) - timedelta(seconds=20)
    hb.last_heartbeat = twenty_sec_ago
    session.commit()
    session.close()

    assert check_worker_health(session_factory=memory_db_factory, stale_threshold_seconds=10.0) is False

    # Worker stop detection: when worker stops, healthcheck must fail
    worker.stop()
    session = memory_db_factory()
    hb = session.query(WorkerHeartbeat).filter_by(worker_name="outbox_worker").one()
    assert hb.status == "STOPPED"
    session.close()

    assert check_worker_health(session_factory=memory_db_factory) is False


def test_independent_worker_heartbeats(memory_db_factory):
    """Verify that outbox_worker and reservation_expiry_worker heartbeats coexist independently."""
    from src.database.pg_models import WorkerHeartbeat
    from src.workers.outbox_worker import check_worker_health as check_outbox_health

    session = memory_db_factory()
    now = datetime.now(timezone.utc)
    # Seed both worker heartbeats in the shared table
    hb_outbox = WorkerHeartbeat(
        worker_name="outbox_worker",
        worker_id="outbox_worker_01",
        status="RUNNING",
        last_heartbeat=now,
    )
    hb_expiry = WorkerHeartbeat(
        worker_name="reservation_expiry_worker",
        worker_id="expiry_worker_01",
        status="STOPPED",  # Expiry worker is stopped
        last_heartbeat=now,
    )
    session.add_all([hb_outbox, hb_expiry])
    session.commit()
    session.close()

    # Outbox worker healthcheck must be unaffected by the stopped expiry worker
    assert check_outbox_health(session_factory=memory_db_factory) is True

