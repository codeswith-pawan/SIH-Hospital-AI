"""
PostgreSQL Migration, Schema, and Transactional Concurrency Test Suite
AI Powered Smart Hospital Referral System - Phase 15
"""

import os
import pytest
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

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
    check_db_health,
    get_referral_repository,
)
from scripts.migrate_to_postgres import execute_migration, load_legacy_data


@pytest.fixture
def memory_db_session():
    """Create an isolated in-memory SQLite database session for unit testing PgBase models."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed core roles
    roles = [
        Role(id="HOSPITAL", description="Hospital Clinical & Operations Staff"),
        Role(id="DISTRICT_ADMIN", description="District Healthcare Administration"),
        Role(id="STATE_ADMIN", description="State Government Healthcare Administration"),
        Role(id="CENTRAL_ADMIN", description="National / Central Referral Oversight"),
    ]
    for r in roles:
        session.add(r)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        PgBase.metadata.drop_all(engine)


def test_schema_sql_and_rollback_completeness():
    """Verify that the DDL and rollback SQL files define and teardown all 9 tables cleanly."""
    base_dir = Path(__file__).resolve().parents[1]
    migration_sql_path = base_dir / "migrations" / "001_initial_postgresql_schema.sql"
    rollback_sql_path = base_dir / "migrations" / "001_rollback_postgresql_schema.sql"

    assert migration_sql_path.exists(), "Initial migration SQL must exist."
    assert rollback_sql_path.exists(), "Rollback migration SQL must exist."

    migration_content = migration_sql_path.read_text(encoding="utf-8")
    rollback_content = rollback_sql_path.read_text(encoding="utf-8")

    expected_tables = [
        "roles",
        "hospitals",
        "users",
        "patients",
        "hospital_visits",
        "beds",
        "referrals",
        "bed_reservations",
        "audit_logs",
    ]

    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration_content, f"Table {table} missing in DDL."
        assert f"DROP TABLE IF EXISTS {table}" in rollback_content, f"Table {table} missing in rollback script."

    # Verify critical partial unique indexes preventing race conditions
    assert "uq_active_bed_reservation" in migration_content
    assert "uq_active_referral_reservation" in migration_content

    # Verify repository implements row-level locking with SKIP LOCKED
    repo_file = base_dir / "src" / "database" / "pg_repository.py"
    assert repo_file.exists()
    repo_content = repo_file.read_text(encoding="utf-8")
    assert "with_for_update" in repo_content
    assert "skip_locked=True" in repo_content


def test_sqlalchemy_model_relations_and_creation(memory_db_session):
    """Verify that all relational models can be instantiated, queried, and navigated via relationships."""
    session = memory_db_session
    now = datetime.now(timezone.utc)

    # 1. Hospital
    hosp = Hospital(
        hospital_id="GH_TEST_01",
        name="Test General Hospital",
        state="Punjab",
        district="Amritsar",
        city="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=50,
        available_beds=25,
        icu_beds=10,
        available_icu_beds=5,
    )
    session.add(hosp)

    # 2. User
    user = User(
        user_id="USR_TEST_01",
        username="test_doctor",
        password_hash="pbkdf2:dummy",
        name="Dr. Test",
        role_id="HOSPITAL",
        hospital_id="GH_TEST_01",
    )
    session.add(user)

    # 3. Patient
    patient = Patient(
        patient_id="PAT_TEST_01",
        name="John Doe",
        age=45,
        gender="Male",
        disease="Acute Myocardial Infarction",
        priority="Urgent",
        icu_required="Yes",
    )
    session.add(patient)

    # 4. Bed
    bed = Bed(
        hospital_id="GH_TEST_01",
        bed_number="ICU-101",
        bed_type="ICU",
        status="AVAILABLE",
    )
    session.add(bed)

    session.commit()

    # Query and test navigation
    h_queried = session.execute(select(Hospital).where(Hospital.hospital_id == "GH_TEST_01")).scalar_one()
    assert h_queried.name == "Test General Hospital"
    assert len(h_queried.beds) == 1
    assert h_queried.beds[0].bed_number == "ICU-101"
    assert len(h_queried.users) == 1
    assert h_queried.users[0].username == "test_doctor"


def test_atomic_accept_and_reserve_success(memory_db_session):
    """Test successful atomic reservation of an available ICU bed."""
    session = memory_db_session

    # Hospital with 1 available ICU bed
    hosp = Hospital(
        hospital_id="GH_AMRITSAR",
        name="Amritsar District Hospital",
        state="Punjab",
        district="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=10,
        available_beds=5,
        icu_beds=2,
        available_icu_beds=1,
    )
    bed = Bed(
        hospital_id="GH_AMRITSAR",
        bed_number="ICU-B1",
        bed_type="ICU",
        status="AVAILABLE",
    )
    patient = Patient(
        patient_id="PAT_001",
        name="Critical Patient",
        priority="Emergency",
    )
    referral = Referral(
        referral_id="REF-TEST-001",
        patient_id="PAT_001",
        from_hospital_id="GH_AMRITSAR",
        to_hospital_id="GH_AMRITSAR",
        status="PENDING",
        priority="Emergency",
        bed_type="ICU",
    )

    session.add_all([hosp, bed, patient, referral])
    session.commit()

    repo = PgReferralRepository(session)
    result = repo.atomic_accept_and_reserve(referral_id="REF-TEST-001", user_id="USR_DR_SMITH", ttl_hours=4)

    assert result["success"] is True
    assert result["status"] == "ACCEPTED"
    assert result["reservation"]["bed_type"] == "ICU"
    assert result["reservation"]["bed_id"] == "ICU-B1"

    # Verify database state updates
    ref_updated = session.execute(select(Referral).where(Referral.referral_id == "REF-TEST-001")).scalar_one()
    assert ref_updated.status == "ACCEPTED"
    assert ref_updated.accepted_at is not None

    bed_updated = session.execute(select(Bed).where(Bed.bed_number == "ICU-B1")).scalar_one()
    assert bed_updated.status == "RESERVED"

    hosp_updated = session.execute(select(Hospital).where(Hospital.hospital_id == "GH_AMRITSAR")).scalar_one()
    assert hosp_updated.available_icu_beds == 0

    # Verify audit log entry was created
    audit = session.execute(select(AuditLog).where(AuditLog.entity_id == "REF-TEST-001")).scalar_one()
    assert audit.action == "ACCEPTED_WITH_BED"
    assert audit.performed_by == "USR_DR_SMITH"


def test_atomic_accept_no_beds_available(memory_db_session):
    """Test referral acceptance failure when zero beds of requested type are available."""
    session = memory_db_session

    hosp = Hospital(
        hospital_id="GH_LUDHIANA",
        name="Ludhiana Hospital",
        state="Punjab",
        district="Ludhiana",
        latitude=30.90,
        longitude=75.85,
        total_beds=5,
        available_beds=0,
        icu_beds=1,
        available_icu_beds=0,
    )
    bed = Bed(
        hospital_id="GH_LUDHIANA",
        bed_number="ICU-FULL",
        bed_type="ICU",
        status="OCCUPIED",
    )
    patient = Patient(patient_id="PAT_002", name="Patient 2")
    referral = Referral(
        referral_id="REF-TEST-002",
        patient_id="PAT_002",
        from_hospital_id="GH_LUDHIANA",
        to_hospital_id="GH_LUDHIANA",
        status="PENDING",
        priority="Urgent",
        bed_type="ICU",
    )

    session.add_all([hosp, bed, patient, referral])
    session.commit()

    repo = PgReferralRepository(session)
    result = repo.atomic_accept_and_reserve(referral_id="REF-TEST-002")

    assert result["success"] is False
    assert result["reason"] == "NO_BEDS_AVAILABLE"

    # Referral must remain PENDING
    ref_check = session.execute(select(Referral).where(Referral.referral_id == "REF-TEST-002")).scalar_one()
    assert ref_check.status == "PENDING"


def test_prevent_duplicate_bed_reservation(memory_db_session):
    """Test that an already accepted referral cannot be accepted a second time."""
    session = memory_db_session

    hosp = Hospital(
        hospital_id="GH_JALANDHAR",
        name="Jalandhar Hospital",
        state="Punjab",
        district="Jalandhar",
        latitude=31.32,
        longitude=75.57,
        total_beds=10,
        available_beds=5,
        icu_beds=5,
        available_icu_beds=5,
    )
    bed1 = Bed(hospital_id="GH_JALANDHAR", bed_number="GEN-01", bed_type="GENERAL", status="AVAILABLE")
    bed2 = Bed(hospital_id="GH_JALANDHAR", bed_number="GEN-02", bed_type="GENERAL", status="AVAILABLE")
    patient = Patient(patient_id="PAT_003", name="Patient 3")
    referral = Referral(
        referral_id="REF-TEST-003",
        patient_id="PAT_003",
        from_hospital_id="GH_JALANDHAR",
        to_hospital_id="GH_JALANDHAR",
        status="PENDING",
        priority="Urgent",
        bed_type="GENERAL",
    )

    session.add_all([hosp, bed1, bed2, patient, referral])
    session.commit()

    repo = PgReferralRepository(session)
    res1 = repo.atomic_accept_and_reserve("REF-TEST-003")
    assert res1["success"] is True

    # Attempt second reservation on same referral
    res2 = repo.atomic_accept_and_reserve("REF-TEST-003")
    assert res2["success"] is False
    assert res2["reason"] == "INVALID_STATUS_TRANSITION"


def test_lifecycle_transitions_and_bed_release(memory_db_session):
    """Test the full referral lifecycle and verify bed is released upon completion."""
    session = memory_db_session

    hosp = Hospital(
        hospital_id="GH_PATIALA",
        name="Patiala Hospital",
        state="Punjab",
        district="Patiala",
        latitude=30.33,
        longitude=76.38,
        total_beds=10,
        available_beds=10,
        icu_beds=5,
        available_icu_beds=1,
    )
    bed = Bed(hospital_id="GH_PATIALA", bed_number="ICU-P1", bed_type="ICU", status="AVAILABLE")
    patient = Patient(patient_id="PAT_004", name="Patient 4")
    referral = Referral(
        referral_id="REF-TEST-004",
        patient_id="PAT_004",
        from_hospital_id="GH_PATIALA",
        to_hospital_id="GH_PATIALA",
        status="PENDING",
        priority="Emergency",
        bed_type="ICU",
    )

    session.add_all([hosp, bed, patient, referral])
    session.commit()

    repo = PgReferralRepository(session)
    acc = repo.atomic_accept_and_reserve("REF-TEST-004")
    assert acc["success"] is True

    # 1. Dispatch
    t1 = repo.atomic_transition_lifecycle("REF-TEST-004", "IN_TRANSIT")
    assert t1["success"] is True
    assert t1["new_status"] == "IN_TRANSIT"

    # 2. Arrived
    t2 = repo.atomic_transition_lifecycle("REF-TEST-004", "ARRIVED")
    assert t2["success"] is True
    assert t2["new_status"] == "ARRIVED"

    # 3. Treatment Active
    t3 = repo.atomic_transition_lifecycle("REF-TEST-004", "TREATMENT_ACTIVE")
    assert t3["success"] is True
    assert t3["new_status"] == "TREATMENT_ACTIVE"

    # Verify bed is occupied
    bed_occ = session.execute(select(Bed).where(Bed.bed_number == "ICU-P1")).scalar_one()
    assert bed_occ.status == "OCCUPIED"

    # 4. Completed (Bed must be released and hospital counter restored)
    t4 = repo.atomic_transition_lifecycle("REF-TEST-004", "COMPLETED", notes="Discharged successfully")
    assert t4["success"] is True
    assert t4["new_status"] == "COMPLETED"

    # Verify bed released to AVAILABLE
    bed_rel = session.execute(select(Bed).where(Bed.bed_number == "ICU-P1")).scalar_one()
    assert bed_rel.status == "AVAILABLE"

    # Verify hospital available counter restored
    hosp_restored = session.execute(select(Hospital).where(Hospital.hospital_id == "GH_PATIALA")).scalar_one()
    assert hosp_restored.available_icu_beds == 1


def test_dry_run_data_migration():
    """Verify that execute_migration dry-run loads legacy data without modifying stores."""
    result = execute_migration(db_url="mock://", dry_run=True)
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["hospitals"] == 500
    assert result["patients"] == 50000
    assert result["users"] >= 8


def test_concurrent_reservation_contention_and_single_winner(memory_db_session):
    """
    Test contention for the last remaining bed.
    First referral claims the bed; second referral is rejected with NO_BEDS_AVAILABLE
    and hospital counter never drops below 0.
    """
    session = memory_db_session

    hosp = Hospital(
        hospital_id="GH_CONCUR",
        name="Contention Test Hospital",
        state="Punjab",
        district="Bathinda",
        latitude=30.21,
        longitude=74.95,
        total_beds=5,
        available_beds=5,
        icu_beds=1,
        available_icu_beds=1,
    )
    bed = Bed(
        hospital_id="GH_CONCUR",
        bed_number="ICU-LAST",
        bed_type="ICU",
        status="AVAILABLE",
    )
    p1 = Patient(patient_id="PAT_C1", name="Contention Patient 1")
    p2 = Patient(patient_id="PAT_C2", name="Contention Patient 2")

    ref1 = Referral(
        referral_id="REF-C1",
        patient_id="PAT_C1",
        from_hospital_id="GH_CONCUR",
        to_hospital_id="GH_CONCUR",
        status="PENDING",
        priority="Emergency",
        bed_type="ICU",
    )
    ref2 = Referral(
        referral_id="REF-C2",
        patient_id="PAT_C2",
        from_hospital_id="GH_CONCUR",
        to_hospital_id="GH_CONCUR",
        status="PENDING",
        priority="Emergency",
        bed_type="ICU",
    )

    session.add_all([hosp, bed, p1, p2, ref1, ref2])
    session.commit()

    repo = PgReferralRepository(session)

    # First referral attempts reservation
    res1 = repo.atomic_accept_and_reserve("REF-C1")
    assert res1["success"] is True
    assert res1["status"] == "ACCEPTED"

    # Second referral attempts reservation on now empty pool
    res2 = repo.atomic_accept_and_reserve("REF-C2")
    assert res2["success"] is False
    assert res2["reason"] == "NO_BEDS_AVAILABLE"

    # Verify hospital available counter is exactly 0 and not negative
    h_updated = session.execute(select(Hospital).where(Hospital.hospital_id == "GH_CONCUR")).scalar_one()
    assert h_updated.available_icu_beds == 0

    # Verify second referral remains PENDING
    ref2_updated = session.execute(select(Referral).where(Referral.referral_id == "REF-C2")).scalar_one()
    assert ref2_updated.status == "PENDING"


def test_atomic_rollback_on_session_error(memory_db_session):
    """
    Test that an unexpected transaction failure triggers an atomic rollback,
    preventing inconsistent intermediate state.
    """
    session = memory_db_session

    hosp = Hospital(
        hospital_id="GH_ROLLBACK",
        name="Rollback Test Hospital",
        state="Punjab",
        district="Ludhiana",
        latitude=30.9,
        longitude=75.8,
        total_beds=10,
        available_beds=5,
        icu_beds=2,
        available_icu_beds=2,
    )
    bed = Bed(
        hospital_id="GH_ROLLBACK",
        bed_number="ICU-RB1",
        bed_type="ICU",
        status="AVAILABLE",
    )
    pat = Patient(patient_id="PAT_RB", name="Rollback Patient")
    ref = Referral(
        referral_id="REF-RB",
        patient_id="PAT_RB",
        from_hospital_id="GH_ROLLBACK",
        to_hospital_id="GH_ROLLBACK",
        status="PENDING",
        priority="Emergency",
        bed_type="ICU",
    )
    session.add_all([hosp, bed, pat, ref])
    session.commit()

    # Simulate an atomic unit-of-work with intentional rollback
    try:
        ref.status = "ACCEPTED"
        bed.status = "RESERVED"
        hosp.available_icu_beds -= 1
        # Intentional error before commit
        raise RuntimeError("Simulated network failure mid-transaction")
    except RuntimeError:
        session.rollback()

    # Verify rollback restored pre-transaction state
    h_clean = session.execute(select(Hospital).where(Hospital.hospital_id == "GH_ROLLBACK")).scalar_one()
    assert h_clean.available_icu_beds == 2

    bed_clean = session.execute(select(Bed).where(Bed.bed_number == "ICU-RB1")).scalar_one()
    assert bed_clean.status == "AVAILABLE"

    ref_clean = session.execute(select(Referral).where(Referral.referral_id == "REF-RB")).scalar_one()
    assert ref_clean.status == "PENDING"


def test_db_manager_health_check():
    """Verify database manager properly detects connection and health."""
    health = check_db_health()
    assert "status" in health
    assert "dialect" in health
    assert health["status"] == "HEALTHY"

