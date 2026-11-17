"""
Dedicated Test Suite: Inventory Accounting Consistency & Category-Specific Occupancy
AI Powered Smart Hospital Referral System
"""

import os
import uuid
import pytest
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/sih_hospital_phase1_run_test")

from src.database.pg_models import Hospital, Bed, BedReservation, Patient, Referral
from src.database.pg_repository import PgReferralRepository, PgAdminRepository


@pytest.fixture(scope="module")
def pg_engine():
    db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/sih_hospital_phase1_run_test")
    return create_engine(db_url)


@pytest.fixture
def pg_session(pg_engine):
    Session = sessionmaker(bind=pg_engine)
    session = Session()
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

    # Clear beds & reservations for clean run
    existing_beds = session.execute(select(Bed).where(Bed.hospital_id == hid)).scalars().all()
    if existing_beds:
        b_ids = [b.id for b in existing_beds]
        session.execute(text("DELETE FROM bed_reservations WHERE bed_id = ANY(:ids)"), {"ids": b_ids})
        session.execute(text("DELETE FROM beds WHERE hospital_id = :hid"), {"hid": hid})
        session.flush()

    for i in range(1, total_gen + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"GENERAL-{i:03d}", bed_type="GENERAL", status="AVAILABLE"))
    for i in range(1, total_icu + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"ICU-{i:03d}", bed_type="ICU", status="AVAILABLE"))
    for i in range(1, total_emg + 1):
        session.add(Bed(hospital_id=hid, bed_number=f"EMERGENCY-{i:03d}", bed_type="EMERGENCY", status="AVAILABLE"))

    hosp.total_beds = total_gen
    hosp.available_beds = total_gen
    hosp.occupied_beds = 0
    hosp.icu_beds = total_icu
    hosp.available_icu_beds = total_icu
    hosp.occupied_icu_beds = 0
    hosp.emergency_beds = total_emg
    hosp.available_emergency_beds = total_emg
    hosp.occupied_emergency_beds = 0
    session.commit()
    return hosp


def test_01_general_reservation_and_occupancy(pg_session):
    """Test 1: General reservation and occupancy isolates counters to General ward."""
    hid = f"H_TEST_GEN_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_GEN_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    res = repo.reserve_bed_direct(hid, pid, "GENERAL")
    assert res["success"] is True

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_beds == 9
    assert h.occupied_beds == 0
    assert h.available_icu_beds == 4
    assert h.occupied_icu_beds == 0
    assert h.available_emergency_beds == 2
    assert h.occupied_emergency_beds == 0

    occ = repo.occupy_bed_direct(hid, pid)
    assert occ["success"] is True

    pg_session.refresh(h)
    assert h.available_beds == 9
    assert h.occupied_beds == 1
    assert h.occupied_icu_beds == 0
    assert h.occupied_emergency_beds == 0


def test_02_icu_reservation_and_occupancy(pg_session):
    """Test 2: ICU reservation and occupancy updates ONLY ICU counters, leaving General untouched."""
    hid = f"H_TEST_ICU_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_ICU_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    res = repo.reserve_bed_direct(hid, pid, "ICU")
    assert res["success"] is True

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_icu_beds == 3
    assert h.occupied_icu_beds == 0
    assert h.available_beds == 10
    assert h.occupied_beds == 0

    occ = repo.occupy_bed_direct(hid, pid)
    assert occ["success"] is True

    pg_session.refresh(h)
    assert h.available_icu_beds == 3
    assert h.occupied_icu_beds == 1
    # Critical invariant: General occupancy MUST remain 0
    assert h.occupied_beds == 0
    assert h.available_beds == 10


def test_03_emergency_reservation_and_occupancy(pg_session):
    """Test 3: Emergency reservation and occupancy updates ONLY Emergency counters."""
    hid = f"H_TEST_EMG_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_EMG_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    res = repo.reserve_bed_direct(hid, pid, "EMERGENCY")
    assert res["success"] is True

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_emergency_beds == 1
    assert h.occupied_emergency_beds == 0
    assert h.available_beds == 10
    assert h.occupied_beds == 0
    assert h.available_icu_beds == 4
    assert h.occupied_icu_beds == 0

    occ = repo.occupy_bed_direct(hid, pid)
    assert occ["success"] is True

    pg_session.refresh(h)
    assert h.available_emergency_beds == 1
    assert h.occupied_emergency_beds == 1
    assert h.occupied_beds == 0
    assert h.occupied_icu_beds == 0


def test_04_category_specific_discharge(pg_session):
    """Test 4: Category-specific discharge decrements matching occupied counter and restores availability."""
    hid = f"H_TEST_DIS_{uuid.uuid4().hex[:6].upper()}"
    pid_icu = f"PAT_ICU_{uuid.uuid4().hex[:6].upper()}"
    pid_emg = f"PAT_EMG_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid_icu, "ICU")
    repo.occupy_bed_direct(hid, pid_icu)

    repo.reserve_bed_direct(hid, pid_emg, "EMERGENCY")
    repo.occupy_bed_direct(hid, pid_emg)

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.occupied_icu_beds == 1
    assert h.occupied_emergency_beds == 1
    assert h.occupied_beds == 0

    # Discharge ICU
    d_icu = repo.discharge_patient_direct(hid, pid_icu)
    assert d_icu["success"] is True

    pg_session.refresh(h)
    assert h.available_icu_beds == 4
    assert h.occupied_icu_beds == 0
    assert h.occupied_emergency_beds == 1
    assert h.occupied_beds == 0

    # Discharge Emergency
    d_emg = repo.discharge_patient_direct(hid, pid_emg)
    assert d_emg["success"] is True

    pg_session.refresh(h)
    assert h.available_emergency_beds == 2
    assert h.occupied_emergency_beds == 0
    assert h.occupied_beds == 0


def test_05_category_specific_release(pg_session):
    """Test 5: Category-specific release restores availability without altering occupancy."""
    hid = f"H_TEST_REL_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_REL_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "ICU")

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_icu_beds == 3

    rel = repo.release_bed_direct(hid, pid)
    assert rel["success"] is True

    pg_session.refresh(h)
    assert h.available_icu_beds == 4
    assert h.occupied_icu_beds == 0


def test_06_reservation_expiry(pg_session):
    """Test 6: Expire reservation restores availability correctly."""
    hid = f"H_TEST_EXP_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_EXP_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)
    repo.reserve_bed_direct(hid, pid, "EMERGENCY")

    h = pg_session.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_emergency_beds == 1

    exp = repo.expire_reservation_direct(hid, pid)
    assert exp["success"] is True

    pg_session.refresh(h)
    assert h.available_emergency_beds == 2
    assert h.occupied_emergency_beds == 0


def test_07_duplicate_operations(pg_session):
    """Test 7: Duplicate operations are rejected idempotently."""
    hid = f"H_TEST_DUP_{uuid.uuid4().hex[:6].upper()}"
    pid = f"PAT_DUP_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=5, total_icu=2, total_emg=2)

    repo = PgReferralRepository(pg_session)
    res1 = repo.reserve_bed_direct(hid, pid, "GENERAL")
    assert res1["success"] is True

    # Duplicate reservation for same patient
    res2 = repo.reserve_bed_direct(hid, pid, "GENERAL")
    assert res2["success"] is False
    assert res2["status"] == "ALREADY_RESERVED"

    # Release
    rel1 = repo.release_bed_direct(hid, pid)
    assert rel1["success"] is True

    # Duplicate release
    rel2 = repo.release_bed_direct(hid, pid)
    assert rel2["success"] is False
    assert rel2["status"] == "ALREADY_RELEASED"


def test_08_concurrent_reservations_cannot_oversell(pg_engine):
    """Test 8: Concurrent reservations for final available bed cannot oversell capacity."""
    Session = sessionmaker(bind=pg_engine)
    session = Session()

    hid = f"H_TEST_CONCUR_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(session, hid, total_gen=1, total_icu=1, total_emg=1)
    session.close()

    def try_reserve(i):
        s = Session()
        try:
            repo = PgReferralRepository(s)
            p_id = f"PAT_CONCUR_{i}_{uuid.uuid4().hex[:4]}"
            return repo.reserve_bed_direct(hid, p_id, "GENERAL")
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(try_reserve, range(5)))

    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 4

    verify_s = Session()
    h = verify_s.query(Hospital).filter_by(hospital_id=hid).one()
    assert h.available_beds == 0
    verify_s.close()


def test_09_emergency_initialization_without_duplicate_beds(pg_session):
    """Test 9: initialize_or_reset_inventory seeds Emergency beds consistently and respects reset=False."""
    hid = f"H_TEST_INIT_{uuid.uuid4().hex[:6].upper()}"
    repo = PgReferralRepository(pg_session)

    # 1. Initialize with General=5, ICU=2, Emergency=3
    inv = repo.initialize_or_reset_inventory(hid, available_beds=5, available_icu_beds=2, available_emergency_beds=3, reset=True)
    assert inv["total_general_beds"] == 5
    assert inv["total_icu_beds"] == 2
    assert inv["total_emergency_beds"] == 3
    assert inv["total_capacity"] == 10

    # Verify physical beds in database
    beds = pg_session.query(Bed).filter_by(hospital_id=hid).all()
    assert len(beds) == 10
    gen_beds = [b for b in beds if b.bed_type == "GENERAL"]
    icu_beds = [b for b in beds if b.bed_type == "ICU"]
    emg_beds = [b for b in beds if b.bed_type == "EMERGENCY"]
    assert len(gen_beds) == 5
    assert len(icu_beds) == 2
    assert len(emg_beds) == 3

    # 2. Repeated call with reset=False must return existing inventory without creating duplicates
    inv2 = repo.initialize_or_reset_inventory(hid, available_beds=5, available_icu_beds=2, reset=False)
    assert inv2["total_capacity"] == 10
    beds_after = pg_session.query(Bed).filter_by(hospital_id=hid).all()
    assert len(beds_after) == 10


def test_10_no_false_reserved_counts_for_uncommissioned_facilities(pg_session):
    """Test 10: Uncommissioned facilities (like GH00509) return 0 reserved beds in get_hospital_inventory."""
    repo = PgReferralRepository(pg_session)
    inv = repo.get_hospital_inventory("GH00509")
    if inv:
        assert inv["reserved_beds"] == 0, f"Expected 0 reserved beds, got {inv['reserved_beds']}"
        assert inv["total_reserved_beds"] == 0


def test_11_category_specific_dashboard_metrics(pg_session):
    """Test 11: PgAdminRepository dashboard metrics report actual occupied_icu_beds without inflating from active holds."""
    repo = PgAdminRepository(pg_session)
    metrics = repo.get_central_metrics()

    # Invariants
    assert "total_beds" in metrics
    assert "available_beds" in metrics
    assert "occupied_beds" in metrics
    assert "total_icu_beds" in metrics
    assert "available_icu_beds" in metrics
    assert "occupied_icu_beds" in metrics
    assert "icu_occupancy_rate" in metrics

    # icu_occupancy_rate must be calculated against occupied_icu_beds, not (total - available)
    if metrics["total_icu_beds"] > 0:
        expected_rate = round((metrics["occupied_icu_beds"] / metrics["total_icu_beds"] * 100), 1)
        assert metrics["icu_occupancy_rate"] == expected_rate


def test_12_capacity_invariants_per_department(pg_session):
    """Test 12: Total capacity = Available + Reserved + Occupied independently per department."""
    hid = f"H_TEST_INV_{uuid.uuid4().hex[:6].upper()}"
    _seed_test_hospital(pg_session, hid, total_gen=10, total_icu=4, total_emg=2)

    repo = PgReferralRepository(pg_session)

    # Perform mixed lifecycle operations
    pat_g1 = f"PAT_G1_{uuid.uuid4().hex[:4]}"
    pat_g2 = f"PAT_G2_{uuid.uuid4().hex[:4]}"
    pat_i1 = f"PAT_I1_{uuid.uuid4().hex[:4]}"
    pat_e1 = f"PAT_E1_{uuid.uuid4().hex[:4]}"

    repo.reserve_bed_direct(hid, pat_g1, "GENERAL")
    repo.reserve_bed_direct(hid, pat_g2, "GENERAL")
    repo.occupy_bed_direct(hid, pat_g1)  # G1 occupied, G2 reserved

    repo.reserve_bed_direct(hid, pat_i1, "ICU")
    repo.occupy_bed_direct(hid, pat_i1)   # I1 occupied

    repo.reserve_bed_direct(hid, pat_e1, "EMERGENCY") # E1 reserved

    inv = repo.get_hospital_inventory(hid)

    # General Invariant
    assert inv["total_general_beds"] == (inv["available_beds"] + inv["reserved_beds"] + inv["occupied_beds"])
    assert inv["total_general_beds"] == 10
    assert inv["occupied_beds"] == 1
    assert inv["reserved_beds"] == 1
    assert inv["available_beds"] == 8

    # ICU Invariant
    assert inv["total_icu_beds"] == (inv["available_icu_beds"] + inv["reserved_icu_beds"] + inv["occupied_icu_beds"])
    assert inv["total_icu_beds"] == 4
    assert inv["occupied_icu_beds"] == 1
    assert inv["reserved_icu_beds"] == 0
    assert inv["available_icu_beds"] == 3

    # Emergency Invariant
    assert inv["total_emergency_beds"] == (inv["available_emergency_beds"] + inv["reserved_emergency_beds"] + inv["occupied_emergency_beds"])
    assert inv["total_emergency_beds"] == 2
    assert inv["occupied_emergency_beds"] == 0
    assert inv["reserved_emergency_beds"] == 1
    assert inv["available_emergency_beds"] == 1

    # Total Invariant
    assert inv["total_capacity"] == (inv["total_available_beds"] + inv["total_reserved_beds"] + inv["total_occupied_beds"])
    assert inv["total_capacity"] == 16
    assert inv["total_available_beds"] == 12
    assert inv["total_reserved_beds"] == 2
    assert inv["total_occupied_beds"] == 2
