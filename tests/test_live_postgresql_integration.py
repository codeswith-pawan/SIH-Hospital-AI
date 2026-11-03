"""
Live PostgreSQL Integration, Failure Recovery & Production Hardening Test Suite
AI Powered Smart Hospital Referral System - Phase 16
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from src.database.pg_models import (
    PgBase,
    Role,
    Hospital,
    User,
    Patient,
    HospitalVisit,
    Bed,
    Referral,
    BedReservation,
    AuditLog,
)
from src.database.pg_repository import PgReferralRepository
from src.database.db_manager import (
    get_database_url,
    is_postgres,
    is_production,
    check_db_health,
    sanitize_database_url,
    sanitize_db_error,
    validate_production_database_config,
    reset_engine,
)

DEV_DB_URL = "postgresql://localhost:5432/sih_hospital_dev"
TEST_DB_URL = "postgresql://localhost:5432/sih_hospital_test"


@pytest.fixture(scope="module")
def pg_engine():
    """Shared PostgreSQL test database engine."""
    engine = create_engine(TEST_DB_URL)
    PgBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """Isolated session for each test with automatic rollback."""
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_postgresql_live_connection_and_version(pg_engine):
    """Verify live connectivity and validate PostgreSQL engine version."""
    with pg_engine.connect() as conn:
        version_str = conn.execute(text("SELECT version();")).scalar()
        assert "PostgreSQL 17" in version_str, f"Expected PostgreSQL 17, got: {version_str}"


def test_live_migration_record_counts():
    """Verify exact migration counts in sih_hospital_dev match extracted source data."""
    engine = create_engine(DEV_DB_URL)
    with engine.connect() as conn:
        hosp_cnt = conn.execute(text("SELECT COUNT(*) FROM hospitals;")).scalar()
        pat_cnt = conn.execute(text("SELECT COUNT(*) FROM patients;")).scalar()
        user_cnt = conn.execute(text("SELECT COUNT(*) FROM users;")).scalar()
        bed_cnt = conn.execute(text("SELECT COUNT(*) FROM beds;")).scalar()
        ref_cnt = conn.execute(text("SELECT COUNT(*) FROM referrals;")).scalar()
        res_cnt = conn.execute(text("SELECT COUNT(*) FROM bed_reservations;")).scalar()
        visit_cnt = conn.execute(text("SELECT COUNT(*) FROM hospital_visits;")).scalar()
        audit_cnt = conn.execute(text("SELECT COUNT(*) FROM audit_logs;")).scalar()

    assert hosp_cnt == 500, f"Expected 500 hospitals, got {hosp_cnt}"
    assert pat_cnt >= 50000, f"Expected at least 50000 patients, got {pat_cnt}"
    assert user_cnt == 8, f"Expected 8 users, got {user_cnt}"
    assert bed_cnt >= 76000, f"Expected >= 76000 beds, got {bed_cnt}"
    assert ref_cnt >= 8, f"Expected >= 8 referrals, got {ref_cnt}"
    assert res_cnt >= 7, f"Expected >= 7 reservations, got {res_cnt}"
    assert visit_cnt == 4, f"Expected 4 visits, got {visit_cnt}"
    assert audit_cnt >= 1, f"Expected audit log entry, got {audit_cnt}"
    engine.dispose()


def test_foreign_key_integrity_in_live_database():
    """Verify 0 broken foreign keys exist in sih_hospital_dev across all relations."""
    engine = create_engine(DEV_DB_URL)
    with engine.connect() as conn:
        broken_refs = conn.execute(text(
            "SELECT COUNT(*) FROM referrals r LEFT JOIN patients p ON r.patient_id = p.patient_id WHERE p.patient_id IS NULL;"
        )).scalar()
        broken_beds = conn.execute(text(
            "SELECT COUNT(*) FROM beds b LEFT JOIN hospitals h ON b.hospital_id = h.hospital_id WHERE h.hospital_id IS NULL;"
        )).scalar()
        broken_res_refs = conn.execute(text(
            "SELECT COUNT(*) FROM bed_reservations br LEFT JOIN referrals r ON br.referral_id = r.referral_id WHERE r.referral_id IS NULL;"
        )).scalar()
        broken_res_beds = conn.execute(text(
            "SELECT COUNT(*) FROM bed_reservations br LEFT JOIN beds b ON br.bed_id = b.id WHERE b.id IS NULL;"
        )).scalar()

    assert broken_refs == 0
    assert broken_beds == 0
    assert broken_res_refs == 0
    assert broken_res_beds == 0
    engine.dispose()


def test_partial_unique_index_prevents_duplicate_active_reservation(pg_session):
    """
    Simulate race condition attempting to create two active reservations on the same bed.
    Verifies that PostgreSQL engine-level partial unique index raises UniqueViolation.
    """
    session = pg_session
    now = datetime.now(timezone.utc)
    hosp_id = "GH_TEST_PARTIAL_UQ"

    # Setup hospital, bed, patient, and 2 referrals
    hosp = Hospital(
        hospital_id=hosp_id,
        name="Partial Unique Test Hosp",
        state="Punjab",
        district="Amritsar",
        latitude=31.6,
        longitude=74.8,
        total_beds=10,
        available_beds=5,
        icu_beds=1,
        available_icu_beds=1,
    )
    session.add(hosp)
    session.flush()

    bed = Bed(hospital_id=hosp_id, bed_number="ICU-UQ-01", bed_type="ICU", status="AVAILABLE")
    session.add(bed)
    session.flush()

    p1 = Patient(patient_id="PAT_UQ1", name="Patient UQ 1", priority="Critical")
    p2 = Patient(patient_id="PAT_UQ2", name="Patient UQ 2", priority="Critical")
    session.add_all([p1, p2])
    session.flush()

    r1 = Referral(referral_id="REF_UQ1", patient_id="PAT_UQ1", from_hospital_id=hosp_id, to_hospital_id=hosp_id, status="ACCEPTED", priority="Critical", bed_type="ICU")
    r2 = Referral(referral_id="REF_UQ2", patient_id="PAT_UQ2", from_hospital_id=hosp_id, to_hospital_id=hosp_id, status="ACCEPTED", priority="Critical", bed_type="ICU")
    session.add_all([r1, r2])
    session.flush()

    # First active reservation succeeds
    res1 = BedReservation(
        reservation_id="RES_UQ_1",
        referral_id="REF_UQ1",
        hospital_id=hosp_id,
        bed_id=bed.id,
        status="RESERVED",
        reserved_at=now,
        expires_at=now + timedelta(hours=2),
    )
    session.add(res1)
    session.flush()

    # Second active reservation on SAME bed must fail via partial unique index
    res2 = BedReservation(
        reservation_id="RES_UQ_2",
        referral_id="REF_UQ2",
        hospital_id=hosp_id,
        bed_id=bed.id,
        status="RESERVED",
        reserved_at=now,
        expires_at=now + timedelta(hours=2),
    )
    session.add(res2)

    with pytest.raises(IntegrityError) as exc_info:
        session.flush()

    assert "uq_active_bed_reservation" in str(exc_info.value).lower() or "unique" in str(exc_info.value).lower()


def test_failure_invalid_foreign_key_rejected_by_postgresql(pg_session):
    """Verify that PostgreSQL rejects referrals referencing non-existent patients."""
    session = pg_session
    ref = Referral(
        referral_id="REF_INVALID_FK",
        patient_id="NON_EXISTENT_PATIENT_XYZ",
        from_hospital_id="GH00001",
        to_hospital_id="GH00001",
        status="PENDING",
        priority="Critical",
        bed_type="ICU",
    )
    session.add(ref)
    with pytest.raises(IntegrityError) as exc_info:
        session.flush()

    assert "foreign key" in str(exc_info.value).lower() or "referrals_patient_id_fkey" in str(exc_info.value).lower()


def test_end_to_end_referral_lifecycle_and_audit_trail(pg_session):
    """
    Test full lifecycle via PgReferralRepository on live PostgreSQL:
    PENDING -> ACCEPTED -> IN_TRANSIT -> ARRIVED -> TREATMENT_ACTIVE -> COMPLETED.
    Verifies that audit_logs records every transition.
    """
    session = pg_session
    repo = PgReferralRepository(session)
    now = datetime.now(timezone.utc)
    import uuid
    hosp_id = f"GH_LC_{uuid.uuid4().hex[:6].upper()}"
    pat_id = f"PAT_LC_{uuid.uuid4().hex[:6].upper()}"
    ref_id = f"REF_LC_{uuid.uuid4().hex[:6].upper()}"

    hosp = Hospital(
        hospital_id=hosp_id,
        name="Lifecycle Live Hospital",
        state="Punjab",
        district="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=10,
        available_beds=5,
        icu_beds=1,
        available_icu_beds=1,
    )
    session.add(hosp)
    session.flush()

    bed = Bed(hospital_id=hosp_id, bed_number="ICU-LC-01", bed_type="ICU", status="AVAILABLE")
    session.add(bed)
    session.flush()

    pat = Patient(patient_id=pat_id, name="Lifecycle Patient", priority="Critical")
    session.add(pat)

    ref = Referral(
        referral_id=ref_id,
        patient_id=pat_id,
        from_hospital_id=hosp_id,
        to_hospital_id=hosp_id,
        status="PENDING",
        priority="Critical",
        bed_type="ICU",
    )
    session.add(ref)
    session.commit()

    # 1. Accept and Reserve
    res_acc = repo.atomic_accept_and_reserve(ref_id, user_id="STAFF_DOC_A")
    assert res_acc["success"] is True
    assert res_acc["status"] == "ACCEPTED"

    # Check bed is RESERVED and counter decremented
    b1 = session.execute(select(Bed).where(Bed.bed_number == "ICU-LC-01", Bed.hospital_id == hosp_id)).scalar_one()
    assert b1.status == "RESERVED"
    h1 = session.execute(select(Hospital).where(Hospital.hospital_id == hosp_id)).scalar_one()
    assert h1.available_icu_beds == 0

    # 2. In Transit
    t1 = repo.atomic_transition_lifecycle(ref_id, "IN_TRANSIT", user_id="STAFF_AMB")
    assert t1["success"] is True

    # 3. Arrived
    t2 = repo.atomic_transition_lifecycle(ref_id, "ARRIVED", user_id="STAFF_TRIAGE")
    assert t2["success"] is True

    # 4. Treatment Active (Bed becomes OCCUPIED)
    t3 = repo.atomic_transition_lifecycle(ref_id, "TREATMENT_ACTIVE", user_id="STAFF_ICU")
    assert t3["success"] is True
    b2 = session.execute(select(Bed).where(Bed.bed_number == "ICU-LC-01", Bed.hospital_id == hosp_id)).scalar_one()
    assert b2.status == "OCCUPIED"

    # 5. Completed (Bed is released to AVAILABLE, counter restored to 1)
    t4 = repo.atomic_transition_lifecycle(ref_id, "COMPLETED", user_id="STAFF_DISCHARGE", notes="Fully recovered")
    assert t4["success"] is True

    b3 = session.execute(select(Bed).where(Bed.bed_number == "ICU-LC-01", Bed.hospital_id == hosp_id)).scalar_one()
    assert b3.status == "AVAILABLE"
    h2 = session.execute(select(Hospital).where(Hospital.hospital_id == hosp_id)).scalar_one()
    assert h2.available_icu_beds == 1

    # 6. Verify Audit Logs in PostgreSQL
    audits = session.execute(
        select(AuditLog).where(AuditLog.entity_id == ref_id).order_by(AuditLog.id.asc())
    ).scalars().all()
    actions = [a.action for a in audits]
    assert "ACCEPTED_WITH_BED" in actions
    assert "TRANSITION_IN_TRANSIT" in actions
    assert "TRANSITION_ARRIVED" in actions
    assert "TRANSITION_TREATMENT_ACTIVE" in actions
    assert "TRANSITION_COMPLETED" in actions


def test_production_configuration_safeguards_and_fallback_prevention(monkeypatch):
    """
    Verify production invariant:
    1. In production, missing or SQLite DATABASE_URL raises RuntimeError.
    2. Connection error sanitization strips passwords.
    """
    reset_engine()

    # Test 1: Production mode with no DATABASE_URL must raise RuntimeError
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SIH_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        get_database_url()
    assert "Production environment requires PostgreSQL" in str(exc_info.value)
    assert "Silent fallback to SQLite/JSON is forbidden" in str(exc_info.value)

    # Test 2: Production mode with SQLite URL must raise RuntimeError
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    with pytest.raises(RuntimeError) as exc_info2:
        get_database_url()
    assert "must use the PostgreSQL protocol" in str(exc_info2.value)

    # Test 3: Credential sanitization
    secret_url = "postgresql://admin_user:super_secret_password_123@prod-cluster.db.internal:5432/hospital_prod"
    masked = sanitize_database_url(secret_url)
    assert "super_secret_password_123" not in masked
    assert ":******@" in masked

    error_with_creds = Exception(f"Failed to connect to {secret_url}: timeout")
    sanitized_err = sanitize_db_error(error_with_creds)
    assert "super_secret_password_123" not in sanitized_err
    assert ":******@" in sanitized_err

    # Reset
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine()


def test_fastapi_client_lifecycle_routes_live(tmp_path, monkeypatch):
    """Verify end-to-end API routes execution via TestClient with isolated test storage."""
    import shutil
    from pathlib import Path
    from fastapi.testclient import TestClient
    from src.api.main import app

    base_dir = Path(__file__).resolve().parents[1]
    res_path = tmp_path / "test_reservations.json"
    bed_path = tmp_path / "test_bed_inventory.json"
    ref_path = tmp_path / "test_referrals.json"

    shutil.copy(base_dir / "data" / "bed_inventory.json", bed_path)
    shutil.copy(base_dir / "data" / "runtime" / "referrals.json", ref_path)
    shutil.copy(base_dir / "data" / "reservations.json", res_path)

    monkeypatch.setenv("SIH_RESERVATIONS_PATH", str(res_path))
    monkeypatch.setenv("SIH_BED_INVENTORY_PATH", str(bed_path))
    monkeypatch.setenv("SIH_REFERRALS_PATH", str(ref_path))

    client = TestClient(app)

    # 1. Login as hospital user
    login_resp = client.post(
        "/login",
        json={"username": "gh00046", "password": "hospital123"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Lookup patient
    pat_resp = client.get("/patients/PAT000005", headers=headers)
    assert pat_resp.status_code == 200, f"Patient lookup failed: {pat_resp.text}"
    pat_data = pat_resp.json()
    assert pat_data["patient"]["patient_id"] == "PAT000005"

    # 3. Create fresh incoming referral to GH00046 from GH00119
    fresh_patient_id = f"PAT_API_{uuid.uuid4().hex[:6].upper()}"
    ref_resp = client.post(
        "/referrals",
        json={
            "patient_id": fresh_patient_id,
            "from_hospital_id": "GH00119",
            "to_hospital_id": "GH00046",
            "reason": "Intensive critical care requirement",
            "priority": "Critical",
            "bed_type": "ICU",
        },
        headers=headers,
    )
    assert ref_resp.status_code == 200, f"Referral creation failed: {ref_resp.text}"
    assert ref_resp.json()["success"] is True, f"Referral not created: {ref_resp.text}"
    ref_id = ref_resp.json()["referral"]["referral_id"]

    # 4. Destination hospital accepts referral and allocates bed
    acc_resp = client.post(
        f"/referrals/{ref_id}/status/ACCEPTED",
        headers=headers,
    )
    assert acc_resp.status_code == 200, f"Accept failed: {acc_resp.text}"
    assert acc_resp.json()["status"] == "ACCEPTED"
    assert acc_resp.json()["reservation"]["bed_type"] == "ICU"

    # 5. Source hospital (GH00119) logs in and dispatches patient IN_TRANSIT
    login_source = client.post(
        "/login",
        json={"username": "gh00119", "password": "hospital123"},
    )
    assert login_source.status_code == 200
    source_token = login_source.json()["access_token"]
    source_headers = {"Authorization": f"Bearer {source_token}"}

    trans_resp = client.post(
        f"/referrals/{ref_id}/status/IN_TRANSIT",
        headers=source_headers,
    )
    assert trans_resp.status_code == 200, f"Transit failed: {trans_resp.text}"
    assert trans_resp.json()["status"] == "IN_TRANSIT"

    # 6. Destination hospital confirms ARRIVED
    arr_resp = client.post(
        f"/referrals/{ref_id}/status/ARRIVED",
        headers=headers,
    )
    assert arr_resp.status_code == 200, f"Arrive failed: {arr_resp.text}"
    assert arr_resp.json()["status"] == "ARRIVED"

    # 7. Destination hospital activates TREATMENT_ACTIVE
    treat_resp = client.post(
        f"/referrals/{ref_id}/status/TREATMENT_ACTIVE",
        headers=headers,
    )
    assert treat_resp.status_code == 200, f"Treatment failed: {treat_resp.text}"
    assert treat_resp.json()["status"] == "TREATMENT_ACTIVE"

    # 8. Destination hospital completes treatment and releases bed
    comp_resp = client.post(
        f"/referrals/{ref_id}/status/COMPLETED",
        headers=headers,
    )
    assert comp_resp.status_code == 200, f"Complete failed: {comp_resp.text}"
    assert comp_resp.json()["status"] == "COMPLETED"

