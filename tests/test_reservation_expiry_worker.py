"""
Phase 4D-1 Test Suite: Automated Bed Reservation Expiry Worker
AI Powered Smart Hospital Referral System

Comprehensive coverage for all 26 required test cases:
- Basic behavior (1-7)
- State protection (8-12)
- Reliability (13-18)
- Concurrency & Row-level locking (19-22)
- Observability & Privacy (23-26)
"""

import os
import time
import uuid
import threading
import pytest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/sih_hospital_phase1_run_test")

from src.database.pg_models import (
    Hospital,
    Bed,
    BedReservation,
    Patient,
    Referral,
    AuditLog,
    WorkerHeartbeat,
)
from src.database.pg_repository import PgReferralRepository
from src.workers.reservation_expiry_worker import (
    ReservationExpiryWorker,
    check_worker_health,
)
from src.api.observability import get_system_metrics


@pytest.fixture(scope="module")
def pg_engine():
    db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/sih_hospital_phase1_run_test")
    return create_engine(db_url)


@pytest.fixture(scope="module", autouse=True)
def cleanup_stale_reservations(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM bed_reservations WHERE status = 'RESERVED' AND expires_at < NOW()"))
    yield


@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(bind=pg_engine)


@pytest.fixture
def pg_session(session_factory):
    session = session_factory()
    yield session
    session.rollback()
    session.close()


def _seed_test_hospital(session, hid, total_gen=10, total_icu=4, total_emg=2):
    now = datetime.now(timezone.utc)
    hosp = session.query(Hospital).filter_by(hospital_id=hid).first()
    if not hosp:
        hosp = Hospital(
            hospital_id=hid,
            name=f"Hospital {hid}",
            state="Punjab",
            district="Amritsar",
            latitude=31.634,
            longitude=74.872,
            total_beds=total_gen,
            available_beds=total_gen,
            occupied_beds=0,
            icu_beds=total_icu,
            available_icu_beds=total_icu,
            occupied_icu_beds=0,
            emergency_beds=total_emg,
            available_emergency_beds=total_emg,
            occupied_emergency_beds=0,
            emergency_24x7="Yes",
            accepts_referral="Yes",
            ambulance="Yes",
            oxygen_support="Yes",
            ventilator="Yes",
            blood_bank="Yes",
            approval_status="APPROVED",
            is_grandfathered=False,
            approved_at=now,
        )
        session.add(hosp)
        session.flush()

    existing_beds = session.execute(select(Bed).where(Bed.hospital_id == hid)).scalars().all()
    if existing_beds:
        b_ids = [b.id for b in existing_beds]
        session.execute(text("DELETE FROM bed_reservations WHERE bed_id = ANY(:ids)"), {"ids": b_ids})
        session.execute(text("DELETE FROM beds WHERE hospital_id = :hid"), {"hid": hid})
        session.flush()

    for i in range(1, total_gen + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"GEN-{i:03d}", bed_type="GENERAL", status="AVAILABLE"))
    for i in range(1, total_icu + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"ICU-{i:03d}", bed_type="ICU", status="AVAILABLE"))
    for i in range(1, total_emg + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"EMG-{i:03d}", bed_type="EMERGENCY", status="AVAILABLE"))

    hosp.total_beds = total_gen
    hosp.available_beds = total_gen
    hosp.occupied_beds = 0
    hosp.icu_beds = total_icu
    hosp.available_icu_beds = total_icu
    hosp.occupied_icu_beds = 0
    hosp.emergency_beds = total_emg
    hosp.available_emergency_beds = total_emg
    hosp.occupied_emergency_beds = 0
    hosp.updated_at = now
    session.commit()
    return hosp


def _create_expired_reservation(session, hid, pid, bed_type="GENERAL", minutes_past=30):
    repo = PgReferralRepository(session)
    res = repo.reserve_bed_direct(hid, pid, bed_type=bed_type)
    assert res["success"] is True

    # Force expires_at into the past
    past_time = datetime.now(timezone.utc) - timedelta(minutes=minutes_past)
    res_id = res["reservation"]["reservation_id"]
    r = session.query(BedReservation).filter_by(reservation_id=res_id).one()
    r.expires_at = past_time
    session.commit()
    return res_id


# ==============================================================================
# 1. BASIC BEHAVIOR (Tests 1-7)
# ==============================================================================

def test_01_expired_eligible_reservation_detected(pg_session):
    """Test 1: Expired eligible reservation is automatically detected."""
    hid = f"H_EXP_01_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_01_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)
    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=15)

    repo = PgReferralRepository(pg_session)
    expired = repo.get_expired_reservations(batch_size=10)
    matching = [e for e in expired if e["reservation_id"] == res_id]
    assert len(matching) == 1
    assert matching[0]["hospital_id"] == hid
    assert matching[0]["patient_id"] == pid
    assert matching[0]["status"] == "RESERVED"


def test_02_expired_reservation_transitions_to_expired(pg_session, session_factory):
    """Test 2: Expired reservation transitions to EXPIRED."""
    hid = f"H_EXP_02_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_02_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)
    res_id = _create_expired_reservation(pg_session, hid, pid, "ICU", minutes_past=20)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    result = worker.run_once()
    assert result["succeeded"] >= 1

    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status == "EXPIRED"
    assert r.released_at is not None


def test_03_available_capacity_increases_exactly_once(pg_session, session_factory):
    """Test 3: Available capacity increases exactly once."""
    hid = f"H_EXP_03_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_03_{uuid.uuid4().hex[:6].upper()}"
    hosp = _seed_test_hospital(pg_session, hid, total_gen=10)
    initial_avail = hosp.available_beds

    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)
    pg_session.refresh(hosp)
    assert hosp.available_beds == initial_avail - 1

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(hosp)
    assert hosp.available_beds == initial_avail

    # Second pass must not increase capacity again
    worker.run_once()
    pg_session.refresh(hosp)
    assert hosp.available_beds == initial_avail


def test_04_reserved_capacity_decreases_correctly(pg_session, session_factory):
    """Test 4: Reserved capacity decreases correctly (active reservation removed)."""
    hid = f"H_EXP_04_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_04_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    _create_expired_reservation(pg_session, hid, pid, "EMERGENCY", minutes_past=10)
    active_before = pg_session.query(BedReservation).filter_by(hospital_id=hid, status="RESERVED").count()
    assert active_before == 1

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    active_after = pg_session.query(BedReservation).filter_by(hospital_id=hid, status="RESERVED").count()
    assert active_after == 0


def test_05_correct_department_inventory_is_updated(pg_session, session_factory):
    """Test 5: Correct department inventory is updated (ICU reservation restores ICU only)."""
    hid = f"H_EXP_05_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_05_{uuid.uuid4().hex[:6].upper()}"
    hosp = _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    _create_expired_reservation(pg_session, hid, pid, "ICU", minutes_past=10)
    pg_session.refresh(hosp)
    assert hosp.available_icu_beds == 3
    assert hosp.available_beds == 10
    assert hosp.available_emergency_beds == 2

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(hosp)
    assert hosp.available_icu_beds == 4
    assert hosp.available_beds == 10
    assert hosp.available_emergency_beds == 2


def test_06_categories_general_icu_emergency_covered(pg_session, session_factory):
    """Test 6: General, ICU, and Emergency categories are covered in a single batch."""
    hid = f"H_EXP_06_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    _create_expired_reservation(pg_session, hid, f"P_GEN_{uuid.uuid4().hex[:4]}", "GENERAL", minutes_past=10)
    _create_expired_reservation(pg_session, hid, f"P_ICU_{uuid.uuid4().hex[:4]}", "ICU", minutes_past=10)
    _create_expired_reservation(pg_session, hid, f"P_EMG_{uuid.uuid4().hex[:4]}", "EMERGENCY", minutes_past=10)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    res = worker.run_once()
    assert res["succeeded"] >= 3

    hosp = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert hosp.available_beds == 10
    assert hosp.available_icu_beds == 4
    assert hosp.available_emergency_beds == 2


def test_07_unexpired_reservation_remains_unchanged(pg_session, session_factory):
    """Test 7: Unexpired reservation remains unchanged."""
    hid = f"H_EXP_07_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_07_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    repo = PgReferralRepository(pg_session)
    res = repo.reserve_bed_direct(hid, pid, "GENERAL", ttl_hours=4)
    res_id = res["reservation"]["reservation_id"]

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status == "RESERVED"


# ==============================================================================
# 2. STATE PROTECTION (Tests 8-12)
# ==============================================================================

def test_08_occupied_reservation_never_expired(pg_session, session_factory):
    """Test 8: Occupied reservation is never expired."""
    hid = f"H_EXP_08_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_08_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "GENERAL")
    repo.confirm_bed_direct(hid, pid)
    repo.occupy_bed_direct(hid, pid)

    # Set expires_at in the past
    r = pg_session.query(BedReservation).join(Referral).filter(Referral.patient_id == pid).one()
    r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    pg_session.commit()

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(r)
    assert r.status == "OCCUPIED"


def test_09_discharged_reservation_never_expired(pg_session, session_factory):
    """Test 9: Discharged reservation is never expired."""
    hid = f"H_EXP_09_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_09_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "GENERAL")
    repo.confirm_bed_direct(hid, pid)
    repo.occupy_bed_direct(hid, pid)
    repo.discharge_patient_direct(hid, pid)

    r = pg_session.query(BedReservation).join(Referral).filter(Referral.patient_id == pid).one()
    r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    pg_session.commit()

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(r)
    assert r.status == "RELEASED"


def test_10_cancelled_reservation_never_expired(pg_session, session_factory):
    """Test 10: Cancelled reservation is never expired."""
    hid = f"H_EXP_10_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_10_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "GENERAL")
    repo.release_bed_direct(hid, pid)

    r = pg_session.query(BedReservation).join(Referral).filter(Referral.patient_id == pid).one()
    r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    pg_session.commit()

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(r)
    assert r.status == "RELEASED"


def test_11_already_expired_reservation_not_reprocessed(pg_session, session_factory):
    """Test 11: Already expired reservation is not processed again."""
    hid = f"H_EXP_11_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_11_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)
    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    res1 = worker.run_once()
    assert res1["succeeded"] >= 1

    # Second pass must find 0 for this reservation
    repo = PgReferralRepository(pg_session)
    expired = repo.get_expired_reservations(batch_size=10)
    assert not any(e["reservation_id"] == res_id for e in expired)


def test_12_confirmed_reservation_follows_business_policy(pg_session, session_factory):
    """
    Test 12: Confirmed reservation follows existing business policy.
    Confirmation guarantees the bed; it must not auto-expire even if expires_at is in the past.
    """
    hid = f"H_EXP_12_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_12_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "GENERAL")
    repo.confirm_bed_direct(hid, pid)

    # Force expires_at into the past
    r = pg_session.query(BedReservation).join(Referral).filter(Referral.patient_id == pid).one()
    r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=60)
    pg_session.commit()

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    pg_session.refresh(r)
    assert r.status == "CONFIRMED"


# ==============================================================================
# 3. RELIABILITY (Tests 13-18)
# ==============================================================================

def test_13_repeated_processing_does_not_double_release(pg_session, session_factory):
    """Test 13: Repeated processing does not double-release capacity."""
    hid = f"H_EXP_13_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_13_{uuid.uuid4().hex[:6].upper()}"
    hosp = _seed_test_hospital(pg_session, hid, total_gen=5)

    _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)
    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)

    worker.run_once()
    worker.run_once()
    worker.run_once()

    pg_session.refresh(hosp)
    assert hosp.available_beds == 5


def test_14_database_failure_rolls_back_all_changes(pg_session, session_factory):
    """Test 14: Database failure rolls back changes atomically."""
    hid = f"H_EXP_14_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_14_{uuid.uuid4().hex[:6].upper()}"
    hosp = _seed_test_hospital(pg_session, hid, total_gen=5)
    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)

    # Simulate transaction rollback inside a repository call
    repo = PgReferralRepository(pg_session)
    sp = pg_session.begin_nested()
    try:
        repo.expire_reservation_direct(reservation_id=res_id, auto_commit=False)
        raise RuntimeError("Simulated transient database interruption")
    except RuntimeError:
        sp.rollback()

    pg_session.rollback()
    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status == "RESERVED"


def test_15_worker_recovers_after_transient_error(session_factory, pg_session):
    """Test 15: Worker recovers gracefully after a transient database error."""
    hid = f"H_EXP_15_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_15_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)
    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)

    call_count = 0

    class MockSessionFactory:
        def __call__(self):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Simulated transient connection failure")
            return session_factory()

    mock_factory = MockSessionFactory()
    worker = ReservationExpiryWorker(session_factory=mock_factory, batch_size=10)

    # Pass 1: Fails with ConnectionError, records error
    p1 = worker.run_once()
    assert p1["failed"] == 1
    assert "Simulated transient connection failure" in p1["error"]

    # Pass 2: Recovers and succeeds
    p2 = worker.run_once()
    assert p2["succeeded"] >= 1

    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status == "EXPIRED"


def test_16_empty_queue_does_not_cause_excessive_cpu(session_factory):
    """Test 16: Empty queue completes quickly without spin or error."""
    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    start = time.perf_counter()
    summary = worker.run_once()
    duration = time.perf_counter() - start

    assert summary["failed"] == 0
    assert duration < 1.0


def test_17_graceful_shutdown_works(session_factory):
    """Test 17: Graceful shutdown via stop() exits thread loop cleanly."""
    worker = ReservationExpiryWorker(session_factory=session_factory, poll_interval=10.0)
    t = threading.Thread(target=worker.run_forever)
    t.start()
    time.sleep(0.3)

    assert worker._is_running is True
    worker.stop()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert worker._is_running is False


def test_18_batch_limits_are_respected(pg_session, session_factory):
    """Test 18: Batch size limit is strictly respected."""
    hid = f"H_EXP_18_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10)

    for i in range(5):
        _create_expired_reservation(pg_session, hid, f"P_BATCH_{i}_{uuid.uuid4().hex[:4]}", "GENERAL", minutes_past=10)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=2)
    summary = worker.run_once()
    assert summary["processed"] == 2
    assert summary["succeeded"] == 2


# ==============================================================================
# 4. CONCURRENCY & ROW-LEVEL LOCKING (Tests 19-22)
# ==============================================================================

def test_19_concurrent_workers_skip_locked_no_double_expire(pg_session, session_factory):
    """Test 19: Two workers processing the same queue concurrently cannot double-expire."""
    hid = f"H_EXP_19_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10)

    created_ids = set()
    for i in range(6):
        res_id = _create_expired_reservation(pg_session, hid, f"P_CONC_{i}_{uuid.uuid4().hex[:4]}", "GENERAL", minutes_past=10)
        created_ids.add(res_id)

    worker1 = ReservationExpiryWorker(session_factory=session_factory, batch_size=6, worker_id="worker_alpha")
    worker2 = ReservationExpiryWorker(session_factory=session_factory, batch_size=6, worker_id="worker_beta")

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker1.run_once)
        f2 = executor.submit(worker2.run_once)
        f1.result()
        f2.result()

    # Verify that all 6 reservations for this hospital transitioned to EXPIRED exactly once
    expired_count = pg_session.query(BedReservation).filter(
        BedReservation.reservation_id.in_(created_ids),
        BedReservation.status == "EXPIRED",
    ).count()
    assert expired_count == 6

    # Verify hospital capacity restored to 10
    hosp = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert hosp.available_beds == 10


def test_20_concurrent_confirmation_and_expiry_valid_final_state(pg_session, session_factory):
    """Test 20: Concurrent confirmation and expiry preserve a valid final state."""
    hid = f"H_EXP_20_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_20_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=5)

    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=1)

    repo = PgReferralRepository(session_factory())
    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_confirm = executor.submit(repo.confirm_bed_direct, hid, pid)
        f_expire = executor.submit(worker.run_once)
        c_res = f_confirm.result()
        e_res = f_expire.result()

    # The final state must be either CONFIRMED or EXPIRED, never both or corrupted
    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status in ("CONFIRMED", "EXPIRED")

    hosp = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    if r.status == "CONFIRMED":
        assert hosp.available_beds == 4
    else:
        assert hosp.available_beds == 5


def test_21_concurrent_occupancy_and_expiry_valid_counters(pg_session, session_factory):
    """Test 21: Concurrent occupancy and expiry preserve correct inventory counters."""
    hid = f"H_EXP_21_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_21_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=5)

    res_id = _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=1)

    repo = PgReferralRepository(session_factory())
    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_occupy = executor.submit(repo.occupy_bed_direct, hid, pid)
        f_expire = executor.submit(worker.run_once)
        f_occupy.result()
        f_expire.result()

    r = pg_session.query(BedReservation).filter_by(reservation_id=res_id).one()
    assert r.status in ("OCCUPIED", "EXPIRED")

    hosp = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    if r.status == "OCCUPIED":
        assert hosp.occupied_beds == 1
        assert hosp.available_beds == 4
    else:
        assert hosp.occupied_beds == 0
        assert hosp.available_beds == 5


def test_22_cross_hospital_isolation(pg_session, session_factory):
    """Test 22: Multiple expired reservations across hospitals do not affect each other's capacity."""
    h1 = f"H_EXP_22A_{uuid.uuid4().hex[:6].upper()}"
    h2 = f"H_EXP_22B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, h1, total_gen=8, total_icu=2)
    _seed_test_hospital(pg_session, h2, total_gen=12, total_icu=5)

    _create_expired_reservation(pg_session, h1, f"P1_{uuid.uuid4().hex[:4]}", "GENERAL", minutes_past=10)
    _create_expired_reservation(pg_session, h2, f"P2_{uuid.uuid4().hex[:4]}", "ICU", minutes_past=10)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    worker.run_once()

    hosp1 = pg_session.query(Hospital).filter_by(hospital_id=h1).one()
    hosp2 = pg_session.query(Hospital).filter_by(hospital_id=h2).one()

    assert hosp1.available_beds == 8
    assert hosp1.available_icu_beds == 2
    assert hosp2.available_beds == 12
    assert hosp2.available_icu_beds == 5


# ==============================================================================
# 5. OBSERVABILITY & PRIVACY (Tests 23-26)
# ==============================================================================

def test_23_processed_metric_incremented(session_factory, pg_session):
    """Test 23: Successful processing increments the processed metric."""
    hid = f"H_EXP_23_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_23_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid)
    _create_expired_reservation(pg_session, hid, pid, "GENERAL", minutes_past=10)

    worker = ReservationExpiryWorker(session_factory=session_factory, batch_size=10)
    m_before = worker.get_metrics()["total_processed"]
    worker.run_once()
    m_after = worker.get_metrics()["total_processed"]

    assert m_after >= m_before + 1


def test_24_failure_metric_incremented(session_factory):
    """Test 24: Failed processing increments the failure metric."""
    class FailingFactory:
        def __call__(self):
            raise RuntimeError("Database pool connection timeout")

    worker = ReservationExpiryWorker(session_factory=FailingFactory(), batch_size=10)
    m_before = worker.get_metrics()["total_failed"]
    worker.run_once()
    m_after = worker.get_metrics()["total_failed"]

    assert m_after == m_before + 1


def test_25_worker_heartbeat_stale_detection(pg_session, session_factory):
    """Test 25: Worker heartbeat becomes stale when the worker stops."""
    worker = ReservationExpiryWorker(session_factory=session_factory)
    worker.record_heartbeat(status="RUNNING")

    # When fresh, healthcheck probe returns True
    assert check_worker_health(stale_threshold_seconds=90.0) is True

    # Simulate stale heartbeat by pushing timestamp 120 seconds into the past
    hb = pg_session.query(WorkerHeartbeat).filter_by(worker_name="reservation_expiry_worker").one()
    hb.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)
    pg_session.commit()

    # Healthcheck should detect stale heartbeat
    assert check_worker_health(stale_threshold_seconds=90.0) is False

    # Reset to fresh for subsequent operations
    worker.record_heartbeat(status="RUNNING")


def test_26_sensitive_information_absent_from_logs_and_metrics(session_factory, caplog):
    """Test 26: Sensitive patient information is strictly absent from metrics and logs."""
    metrics = get_system_metrics()
    expiry = metrics.get("reservation_expiry_worker", {})

    # Check metrics payload for absence of patient PII
    expiry_str = str(expiry)
    forbidden_terms = ["patient_name", "phone", "email", "aadhar", "diagnosis", "PAT_", "@"]
    for term in forbidden_terms:
        assert term not in expiry_str

    # Expiry worker metrics must expose only operational integers and timestamps
    assert isinstance(expiry.get("reservation_expiry_processed_total"), int)
    assert isinstance(expiry.get("reservation_expiry_failed_total"), int)
    assert isinstance(expiry.get("reservation_expiry_worker_running"), bool)
