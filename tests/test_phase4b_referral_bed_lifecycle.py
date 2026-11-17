"""
Phase 4B Integration Test Suite
Unified PostgreSQL Referral, Reservation & Patient Bed Lifecycle
Target Database: sih_hospital_phase1_run_test
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.database.pg_models import (
    PgBase,
    Hospital,
    User,
    Patient,
    Bed,
    Referral,
    BedReservation,
    AuditLog,
)
from src.database.pg_repository import PgReferralRepository
from src.prediction.bed_reservation import (
    initialize_hospital_beds,
    reserve_bed,
    confirm_reservation,
    mark_bed_occupied,
    release_bed,
    discharge_patient,
    get_reservation,
    expire_reservation,
)
from src.prediction.referral_store import (
    create_referral as create_store_referral,
    update_referral_status,
)
from src.auth.jwt_utils import create_access_token
from src.api.main import app

TEST_DB_URL = "postgresql://localhost:5432/sih_hospital_phase1_run_test"


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("SIH_DATABASE_URL", TEST_DB_URL)
    
    # Reset singleton engine in db_manager so it uses TEST_DB_URL
    import src.database.db_manager as dbm
    dbm._ENGINE = None
    dbm._SESSION_FACTORY = None

    Session = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        dbm._ENGINE = None
        dbm._SESSION_FACTORY = None


@pytest.fixture
def api_client(pg_session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("SIH_DATABASE_URL", TEST_DB_URL)
    from src.database.db_manager import get_db_session

    def _override_get_db_session():
        yield pg_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _seed_test_hospital(session, hospital_id: str, total_beds: int = 10, icu_beds: int = 3):
    now = datetime.now(timezone.utc)
    hosp = session.execute(
        select(Hospital).where(Hospital.hospital_id == hospital_id)
    ).scalar_one_or_none()
    if not hosp:
        hosp = Hospital(
            hospital_id=hospital_id,
            name=f"Hospital {hospital_id}",
            state="Punjab",
            district="Amritsar",
            city="Amritsar",
            latitude=31.63,
            longitude=74.87,
            total_beds=total_beds,
            available_beds=total_beds,
            occupied_beds=0,
            icu_beds=icu_beds,
            available_icu_beds=icu_beds,
            emergency_beds=2,
            available_emergency_beds=2,
            oxygen_support="Yes",
            ventilator="Yes",
            ambulance="Yes",
            blood_bank="Yes",
            emergency_24x7="Yes",
            approval_status="APPROVED",
            is_grandfathered=False,
            approved_at=now,
        )
        session.add(hosp)
        session.flush()

    # Clear existing beds and reservations for clean state
    existing_beds = session.execute(
        select(Bed).where(Bed.hospital_id == hospital_id)
    ).scalars().all()
    if existing_beds:
        b_ids = [b.id for b in existing_beds]
        session.execute(
            text("DELETE FROM bed_reservations WHERE bed_id = ANY(:ids)"),
            {"ids": b_ids},
        )
        session.execute(
            text("DELETE FROM beds WHERE hospital_id = :hid"),
            {"hid": hospital_id},
        )
        session.flush()

    for i in range(1, total_beds + 1):
        b = Bed(
            hospital_id=hospital_id,
            bed_number=f"GENERAL-{i:03d}",
            bed_type="GENERAL",
            status="AVAILABLE",
            created_at=now,
            updated_at=now,
        )
        session.add(b)

    for i in range(1, icu_beds + 1):
        b = Bed(
            hospital_id=hospital_id,
            bed_number=f"ICU-{i:03d}",
            bed_type="ICU",
            status="AVAILABLE",
            created_at=now,
            updated_at=now,
        )
        session.add(b)

    hosp.total_beds = total_beds
    hosp.available_beds = total_beds
    hosp.icu_beds = icu_beds
    hosp.available_icu_beds = icu_beds
    hosp.occupied_beds = 0
    session.commit()
    return hosp


def test_01_successful_direct_reservation_decreases_pg_availability(pg_session):
    """Test 1: Direct bed reservation decreases PostgreSQL availability."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=3)

    repo = PgReferralRepository(pg_session)
    inv_before = repo.get_hospital_inventory(hid)
    assert inv_before["available_icu_beds"] == 3
    assert inv_before["reserved_icu_beds"] == 0

    res = repo.reserve_bed_direct(hid, pid, "ICU")
    assert res["success"] is True
    assert res["status"] == "RESERVED"
    assert res["reservation"]["bed_id"].startswith("ICU-")

    inv_after = repo.get_hospital_inventory(hid)
    assert inv_after["available_icu_beds"] == 2
    assert inv_after["reserved_icu_beds"] == 1


def test_02_hospital_dashboard_reflects_reservation_immediately(api_client, pg_session):
    """Test 2: Hospital dashboard GET /hospitals/{hid}/inventory immediately reflects reservation."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=10, icu_beds=2)

    token = create_access_token({
        "user_id": f"U_{hid}",
        "username": f"admin_{hid.lower()}",
        "role": "HOSPITAL",
        "hospital_id": hid,
        "district": "Amritsar",
        "state": "Punjab",
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Direct reservation via API
    resp_reserve = api_client.post(
        f"/reservation/{hid}/{pid}/reserve?bed_type=ICU",
        headers=headers,
    )
    assert resp_reserve.status_code == 200
    res_data = resp_reserve.json()
    assert res_data["success"] is True
    assert res_data["status"] == "RESERVED"

    # Query Dashboard inventory
    resp_inv = api_client.get(f"/hospitals/{hid}/inventory", headers=headers)
    assert resp_inv.status_code == 200
    inv = resp_inv.json()
    assert inv["available_icu_beds"] == 1
    assert inv["reserved_icu_beds"] == 1


def test_03_cancellation_restores_reserved_availability(pg_session):
    """Test 3: Cancellation/release restores reserved availability."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    res = repo.reserve_bed_direct(hid, pid, "ICU")
    assert res["success"] is True

    inv_mid = repo.get_hospital_inventory(hid)
    assert inv_mid["available_icu_beds"] == 1
    assert inv_mid["reserved_icu_beds"] == 1

    rel = repo.release_bed_direct(hid, pid)
    assert rel["success"] is True
    assert rel["status"] == "RELEASED"

    inv_after = repo.get_hospital_inventory(hid)
    assert inv_after["available_icu_beds"] == 2
    assert inv_after["reserved_icu_beds"] == 0


def test_04_occupancy_moves_reserved_to_occupied(pg_session):
    """Test 4: Occupancy moves reserved beds into occupied."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "ICU")

    occ = repo.occupy_bed_direct(hid, pid)
    assert occ["success"] is True
    assert occ["status"] == "OCCUPIED"

    inv = repo.get_hospital_inventory(hid)
    assert inv["available_icu_beds"] == 1
    assert inv["reserved_icu_beds"] == 0
    assert inv["occupied_icu_beds"] == 1
    assert inv["total_occupied_beds"] == 1


def test_05_discharge_releases_occupied_bed_to_available(pg_session):
    """Test 5: Discharge releases occupied beds back to available."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "ICU")
    repo.occupy_bed_direct(hid, pid)

    disc = repo.discharge_patient_direct(hid, pid)
    assert disc["success"] is True
    assert disc["status"] == "RELEASED"

    inv = repo.get_hospital_inventory(hid)
    assert inv["available_icu_beds"] == 2
    assert inv["reserved_icu_beds"] == 0
    assert inv["occupied_icu_beds"] == 0


def test_06_duplicate_reservation_rejected(pg_session):
    """Test 6: Duplicate reservation is rejected."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    res1 = repo.reserve_bed_direct(hid, pid, "ICU")
    assert res1["success"] is True

    res2 = repo.reserve_bed_direct(hid, pid, "ICU")
    assert res2["success"] is False
    assert res2["status"] == "ALREADY_RESERVED"


def test_07_duplicate_cancellation_is_safe_and_idempotent(pg_session):
    """Test 7: Duplicate cancellation is safe."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "ICU")
    rel1 = repo.release_bed_direct(hid, pid)
    assert rel1["success"] is True

    rel2 = repo.release_bed_direct(hid, pid)
    assert rel2["success"] is False
    assert rel2["status"] == "ALREADY_RELEASED"

    # Verify inventory was not incremented twice
    inv = repo.get_hospital_inventory(hid)
    assert inv["available_icu_beds"] == 2


def test_08_insufficient_capacity_is_rejected(pg_session):
    """Test 8: Insufficient capacity is rejected without overbooking."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=2, icu_beds=1)

    repo = PgReferralRepository(pg_session)
    res1 = repo.reserve_bed_direct(hid, "PAT_1", "ICU")
    assert res1["success"] is True

    res2 = repo.reserve_bed_direct(hid, "PAT_2", "ICU")
    assert res2["success"] is False
    assert res2["status"] == "NO_ICU_AVAILABLE"

    inv = repo.get_hospital_inventory(hid)
    assert inv["available_icu_beds"] == 0
    assert inv["reserved_icu_beds"] == 1


def test_09_concurrent_reservations_cannot_oversell(pg_engine):
    """Test 9: Concurrent reservations cannot oversell beds."""
    hid = f"H_CONCUR_{uuid.uuid4().hex[:6].upper()}"
    
    # Seed hospital with exactly 1 available ICU bed
    Session = sessionmaker(bind=pg_engine)
    with Session() as s:
        _seed_test_hospital(s, hid, total_beds=5, icu_beds=1)

    def _attempt_booking(pat_id):
        with Session() as sess:
            repo = PgReferralRepository(sess)
            return repo.reserve_bed_direct(hid, pat_id, "ICU")

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_attempt_booking, f"PAT_C_{i}") for i in range(5)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r["success"] is True]
    failures = [r for r in results if r["success"] is False]

    # Exactly 1 can succeed
    assert len(successes) == 1
    assert len(failures) == 4

    with Session() as s:
        repo = PgReferralRepository(s)
        inv = repo.get_hospital_inventory(hid)
        assert inv["available_icu_beds"] == 0
        assert inv["reserved_icu_beds"] == 1


def test_10_transaction_rollback_leaves_no_partial_writes(pg_session):
    """Test 10: Failed transactions roll back cleanly."""
    hid = f"H_P4B_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_P4B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    # Attempt booking with invalid bed type
    res = repo.reserve_bed_direct(hid, pid, "INVALID_TYPE")
    assert res["success"] is False
    assert res["status"] == "INVALID_BED_TYPE"

    inv = repo.get_hospital_inventory(hid)
    assert inv["available_icu_beds"] == 2
    assert inv["reserved_icu_beds"] == 0


def test_11_invalid_referral_transitions_rejected(pg_session):
    """Test 11: Invalid referral transitions are rejected."""
    hid_src = f"H_SRC_{uuid.uuid4().hex[:6].upper()}"
    hid_dest = f"H_DEST_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_REF_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid_src, total_beds=5, icu_beds=2)
    _seed_test_hospital(pg_session, hid_dest, total_beds=5, icu_beds=2)

    repo = PgReferralRepository(pg_session)
    ref_res = repo.create_referral(pid, hid_src, hid_dest, reason="Cardiac emergency", bed_type="ICU")
    assert ref_res["success"] is True
    ref_id = ref_res["referral"]["referral_id"]

    # Try invalid jump: PENDING -> TREATMENT_ACTIVE
    t_res = repo.atomic_transition_lifecycle(ref_id, "TREATMENT_ACTIVE")
    assert t_res["success"] is False
    assert t_res["status"] == "INVALID_STATE"


def test_12_cross_hospital_authorization_enforced(api_client, pg_session):
    """Test 12: Cross-hospital authorization returns 403 Forbidden."""
    hid_a = f"H_AUTH_A_{uuid.uuid4().hex[:6].upper()}"
    hid_b = f"H_AUTH_B_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid_a)
    _seed_test_hospital(pg_session, hid_b)

    # Token for Hospital A
    token_a = create_access_token({
        "user_id": f"U_{hid_a}",
        "username": f"admin_{hid_a.lower()}",
        "role": "HOSPITAL",
        "hospital_id": hid_a,
        "district": "Amritsar",
        "state": "Punjab",
    })
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Attempt to reserve bed in Hospital B with Hospital A token
    resp = api_client.post(
        f"/reservation/{hid_b}/PAT_HACK/reserve?bed_type=GENERAL",
        headers=headers_a,
    )
    assert resp.status_code == 403


def test_13_dual_storage_divergence_defect_eliminated(pg_session):
    """
    Test 13 (CRITICAL PHASE 4B PROOF):
    Empirical demonstration that reserve_bed() from bed_reservation.py updates
    PostgreSQL inventory and dashboard reading matches immediately.
    """
    hid = f"H_PROOFA_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_PROOFA_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_beds=5, icu_beds=5)

    repo = PgReferralRepository(pg_session)
    inv_start = repo.get_hospital_inventory(hid)
    assert inv_start["available_icu_beds"] == 5

    # Execute bed reservation via reserve_bed()
    res = reserve_bed(
        hospital_id=hid,
        patient_id=pid,
        bed_type="ICU",
        inventory=inv_start,
    )
    assert res["success"] is True

    # Check PostgreSQL authoritative inventory
    inv_pg = repo.get_hospital_inventory(hid)
    assert inv_pg["available_icu_beds"] == 4
    assert inv_pg["reserved_icu_beds"] == 1

    # Release bed
    rel = release_bed(
        hospital_id=hid,
        patient_id=pid,
        inventory=inv_pg,
    )
    assert rel["success"] is True

    inv_released = repo.get_hospital_inventory(hid)
    assert inv_released["available_icu_beds"] == 5
    assert inv_released["reserved_icu_beds"] == 0
