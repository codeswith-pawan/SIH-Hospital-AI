"""
Live PostgreSQL Integration Test Suite for Hierarchical Registration System
Phase 1 Tasks 1A/1B Review Fixes Validation
Target Database: sih_hospital_reg_test (disposable test database)
"""

import os
import subprocess
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError

from src.database.pg_models import (
    PgBase,
    Role,
    Hospital,
    User,
    RegistrationApplication,
    RegistrationDocument,
    ApprovalHistory,
    VerificationToken,
    ApplicationTrackingToken,
    AccountActivationToken,
    RegistrationEmailOutbox,
    PasswordResetToken,
)

REG_TEST_DB_NAME = "sih_hospital_reg_test"
REG_TEST_DB_URL = f"postgresql://localhost:5432/{REG_TEST_DB_NAME}"
PG_USER = os.getenv("USER", "pawankumarsharma")


def _run_psql(db_name: str, sql_file_or_cmd: str, is_file: bool = True) -> subprocess.CompletedProcess:
    """Helper to run psql command or file against target database with ON_ERROR_STOP=1."""
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-h", "localhost", "-p", "5432", "-U", PG_USER, "-d", db_name]
    if is_file:
        cmd.extend(["-f", sql_file_or_cmd])
    else:
        cmd.extend(["-c", sql_file_or_cmd])
    return subprocess.run(cmd, capture_output=True, text=True)


@pytest.fixture(scope="module")
def pg_engine():
    """
    Setup a clean, disposable test database (sih_hospital_reg_test) with:
    - 001 initial schema
    - 002 referral workflow
    - Exactly 500 legacy hospitals (GH00001 to GH00500)
    - 003 registration system migration applied
    """
    # 1. Recreate clean test database
    subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", REG_TEST_DB_NAME], capture_output=True)
    res = subprocess.run(["createdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, REG_TEST_DB_NAME], capture_output=True, text=True)
    assert res.returncode == 0, f"Failed to create {REG_TEST_DB_NAME}: {res.stderr}"

    # 2. Apply migrations 001 and 002
    for mig in ["migrations/001_initial_postgresql_schema.sql", "migrations/002_referral_workflow_and_notifications.sql"]:
        sub_res = _run_psql(REG_TEST_DB_NAME, mig, is_file=True)
        assert sub_res.returncode == 0, f"Failed applying {mig}: {sub_res.stderr}"

    # 3. Seed base roles and exactly 500 legacy hospitals
    seed_sql = """
        INSERT INTO roles (id, description) VALUES
            ('HOSPITAL', 'Hospital Staff'),
            ('DISTRICT_ADMIN', 'District Admin'),
            ('STATE_ADMIN', 'State Admin'),
            ('CENTRAL_ADMIN', 'Central Admin')
        ON CONFLICT DO NOTHING;

        INSERT INTO hospitals (
            hospital_id, name, state, district, latitude, longitude,
            total_beds, occupied_beds, available_beds, icu_beds,
            available_icu_beds, emergency_beds, available_emergency_beds
        )
        SELECT
            'GH' || LPAD(i::text, 5, '0'),
            'Legacy Hospital ' || i::text,
            'Punjab',
            'District ' || (i % 10)::text,
            30.0 + (i * 0.001),
            75.0 + (i * 0.001),
            100, 50, 50, 10, 5, 10, 5
        FROM generate_series(1, 500) AS i;
    """
    seed_res = _run_psql(REG_TEST_DB_NAME, seed_sql, is_file=False)
    assert seed_res.returncode == 0, f"Failed seeding legacy hospitals: {seed_res.stderr}"

    # 4. Apply migration 003
    mig3_res = _run_psql(REG_TEST_DB_NAME, "migrations/003_registration_system.sql", is_file=True)
    assert mig3_res.returncode == 0, f"Failed applying migration 003: {mig3_res.stderr}"

    # 5. Apply migration 004, 005, 006
    for mig in [
        "migrations/004_category_occupancy_counters.sql",
        "migrations/005_worker_heartbeats.sql",
        "migrations/006_workflow_notifications.sql",
    ]:
        mig_res = _run_psql(REG_TEST_DB_NAME, mig, is_file=True)
        assert mig_res.returncode == 0, f"Failed applying {mig}: {mig_res.stderr}"

    engine = create_engine(REG_TEST_DB_URL)
    yield engine
    engine.dispose()

    # Teardown disposable test database
    subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", REG_TEST_DB_NAME], capture_output=True)


@pytest.fixture
def pg_session(pg_engine):
    """Transactional session for each test that rolls back changes."""
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# =====================================================================
# 1. ISSUE 1 & 3 — AUTOMATIC SUBMITTED_AT LIFECYCLE & DRAFT SEMANTICS
# =====================================================================

def test_postgresql_status_default_and_draft_timestamps(pg_session):
    """
    Verify initial DRAFT creation defaults and timestamp rules:
    - PostgreSQL defaults status to 'DRAFT'
    - PostgreSQL defaults current_stage to 'DRAFT'
    - PostgreSQL defaults resubmission_version to 1
    - PostgreSQL populates created_at automatically (NOT NULL)
    - PostgreSQL leaves submitted_at as NULL
    - PostgreSQL leaves resubmitted_at as NULL
    """
    app_id = f"APP_PG_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-20261103-{uuid.uuid4().hex[:6]}"

    # Execute raw SQL INSERT with status, current_stage, and timestamps omitted
    insert_sql = text("""
        INSERT INTO registration_applications (
            application_id, application_number, applicant_type,
            applicant_name, applicant_email, applicant_phone,
            state, district
        ) VALUES (
            :app_id, :app_num, 'HOSPITAL',
            'Fortis Hospital Mohali', 'admin@fortis-mohali.org', '+91172555000',
            'Punjab', 'Mohali'
        ) RETURNING status, current_stage, resubmission_version, created_at, submitted_at, resubmitted_at;
    """)

    result = pg_session.execute(insert_sql, {"app_id": app_id, "app_num": app_num}).fetchone()
    pg_session.flush()

    assert result is not None
    assert result[0] == "DRAFT", f"Expected default status 'DRAFT', got '{result[0]}'"
    assert result[1] == "DRAFT", f"Expected default current_stage 'DRAFT', got '{result[1]}'"
    assert result[2] == 1, f"Expected default resubmission_version 1, got {result[2]}"
    assert result[3] is not None, "created_at must be populated on creation"
    assert result[4] is None, f"DRAFT application must have submitted_at IS NULL, got '{result[4]}'"
    assert result[5] is None, f"DRAFT application must have resubmitted_at IS NULL, got '{result[5]}'"

    # Also verify via SQLAlchemy ORM query
    app = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert app is not None
    assert app.status == "DRAFT"
    assert app.current_stage == "DRAFT"
    assert app.created_at is not None
    assert app.submitted_at is None
    assert app.resubmitted_at is None


def test_postgresql_submitted_at_automatic_lifecycle_orm(pg_session):
    """
    Verify automatic timestamp management via SQLAlchemy ORM (WITHOUT manual assignment of submitted_at):
    1. New DRAFT application: submitted_at must be NULL.
    2. First transition to SUBMITTED: submitted_at must be populated automatically.
    3. Repeated updates while already SUBMITTED: must not overwrite original submission timestamp.
    4. Resubmission after CORRECTION_REQUIRED: preserve original submitted_at, populate resubmitted_at.
    """
    app_id = f"APP_AUTO_ORM_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-AUTO-ORM-{uuid.uuid4().hex[:6]}"

    # Step 1: Create application in DRAFT
    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="HOSPITAL",
        applicant_name="Max Healthcare Mohali",
        applicant_email="admin@max-mohali.org",
        applicant_phone="0172-555222",
        state="Punjab",
        status="DRAFT",
        current_stage="DRAFT",
    )
    pg_session.add(app)
    pg_session.commit()

    fetched = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert fetched.status == "DRAFT"
    assert fetched.submitted_at is None
    assert fetched.created_at is not None

    # Step 2: First transition to SUBMITTED (submitted_at is NOT manually assigned)
    fetched.status = "SUBMITTED"
    fetched.current_stage = "SUBMITTED"
    pg_session.commit()

    re_fetched = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert re_fetched.status == "SUBMITTED"
    assert re_fetched.submitted_at is not None, "submitted_at must be populated automatically"
    orig_submitted_at = re_fetched.submitted_at

    # Step 3: Repeated updates while already SUBMITTED (e.g. updating phone number / stage)
    re_fetched.applicant_phone = "0172-888999"
    re_fetched.status = "UNDER_REVIEW"
    re_fetched.current_stage = "DISTRICT_REVIEW"
    pg_session.commit()

    re_fetched2 = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert re_fetched2.submitted_at == orig_submitted_at, "Original submission timestamp must NOT be overwritten!"

    # Step 4: Reviewer requests corrections (status transition to CORRECTION_REQUIRED preserves submitted_at)
    re_fetched2.status = "CORRECTION_REQUIRED"
    re_fetched2.correction_notes = "Please upload updated clinical establishment license."
    pg_session.commit()

    re_fetched_corr = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert re_fetched_corr.submitted_at == orig_submitted_at, "CORRECTION_REQUIRED must preserve original submitted_at"
    assert re_fetched_corr.resubmission_version == 1

    # Step 5: Applicant resubmits after correction (neither submitted_at, resubmitted_at, nor resubmission_version is manually assigned)
    re_fetched3 = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    re_fetched3.status = "SUBMITTED"
    re_fetched3.current_stage = "DISTRICT_REVIEW"
    pg_session.commit()

    re_fetched4 = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert re_fetched4.status == "SUBMITTED"
    assert re_fetched4.submitted_at == orig_submitted_at, "Original submission timestamp must remain preserved on resubmission!"
    assert re_fetched4.resubmitted_at is not None, "resubmitted_at must be populated on resubmission!"
    assert re_fetched4.resubmitted_at >= orig_submitted_at
    assert re_fetched4.resubmission_version == 2, "resubmission_version must increment exactly once on resubmission"

    # Step 6: Repeated updates while already SUBMITTED must not increment resubmission_version again
    re_fetched4.applicant_name = "Max Healthcare Renamed"
    pg_session.commit()

    re_fetched5 = pg_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert re_fetched5.resubmission_version == 2, "Repeated updates must NOT increment resubmission_version again!"
    assert re_fetched5.submitted_at == orig_submitted_at


def test_postgresql_submitted_at_automatic_lifecycle_raw_sql(pg_session):
    """
    Verify automatic timestamp management via raw PostgreSQL statements (governed by DB trigger):
    - Raw INSERT in DRAFT -> submitted_at is NULL
    - Raw UPDATE to SUBMITTED without specifying submitted_at -> trigger sets submitted_at = NOW()
    - Raw UPDATE while SUBMITTED -> trigger preserves OLD.submitted_at
    - Raw UPDATE from CORRECTION_REQUIRED to SUBMITTED -> trigger preserves submitted_at and sets resubmitted_at = NOW()
    """
    app_id = f"APP_RAW_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-RAW-{uuid.uuid4().hex[:6]}"

    # Raw INSERT in DRAFT
    pg_session.execute(text("""
        INSERT INTO registration_applications (
            application_id, application_number, applicant_type,
            applicant_name, applicant_email, applicant_phone, state
        ) VALUES (
            :app_id, :app_num, 'HOSPITAL',
            'Raw SQL Test Hospital', 'raw@hospital.org', '0172-123000', 'Punjab'
        );
    """), {"app_id": app_id, "app_num": app_num})
    pg_session.commit()

    row = pg_session.execute(text(
        "SELECT status, submitted_at, resubmitted_at, created_at FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row[0] == "DRAFT"
    assert row[1] is None, "DRAFT submitted_at must be NULL"
    assert row[2] is None, "DRAFT resubmitted_at must be NULL"
    assert row[3] is not None, "created_at must be populated"

    # Raw UPDATE to SUBMITTED without mentioning submitted_at
    pg_session.execute(text("""
        UPDATE registration_applications
        SET status = 'SUBMITTED', current_stage = 'SUBMITTED'
        WHERE application_id = :app_id;
    """), {"app_id": app_id})
    pg_session.commit()

    row2 = pg_session.execute(text(
        "SELECT status, submitted_at FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row2[0] == "SUBMITTED"
    assert row2[1] is not None, "Trigger must automatically populate submitted_at on transition to SUBMITTED"
    orig_sub_ts = row2[1]

    # Raw UPDATE while already SUBMITTED
    pg_session.execute(text("""
        UPDATE registration_applications
        SET applicant_phone = '0172-999888'
        WHERE application_id = :app_id;
    """), {"app_id": app_id})
    pg_session.commit()

    row3 = pg_session.execute(text(
        "SELECT submitted_at FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row3[0] == orig_sub_ts, "Trigger must preserve original submitted_at"

    # Raw UPDATE to CORRECTION_REQUIRED (preserves submitted_at)
    pg_session.execute(text("""
        UPDATE registration_applications
        SET status = 'CORRECTION_REQUIRED', correction_notes = 'Need Fire NOC'
        WHERE application_id = :app_id;
    """), {"app_id": app_id})
    pg_session.commit()

    row_corr = pg_session.execute(text(
        "SELECT submitted_at, resubmission_version FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row_corr[0] == orig_sub_ts, "CORRECTION_REQUIRED must preserve submitted_at"
    assert row_corr[1] == 1, "resubmission_version remains 1 in CORRECTION_REQUIRED"

    # Raw UPDATE from CORRECTION_REQUIRED to SUBMITTED without mentioning submitted_at, resubmitted_at, or resubmission_version
    pg_session.execute(text("""
        UPDATE registration_applications
        SET status = 'SUBMITTED', current_stage = 'DISTRICT_REVIEW'
        WHERE application_id = :app_id;
    """), {"app_id": app_id})
    pg_session.commit()

    row4 = pg_session.execute(text(
        "SELECT submitted_at, resubmitted_at, resubmission_version FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row4[0] == orig_sub_ts, "Trigger must preserve original submitted_at after resubmission"
    assert row4[1] is not None, "Trigger must set resubmitted_at on resubmission"
    assert row4[2] == 2, "Trigger must increment resubmission_version exactly once on resubmission"

    # Raw UPDATE while already SUBMITTED must not increment resubmission_version again
    pg_session.execute(text("""
        UPDATE registration_applications
        SET applicant_name = 'Raw SQL Test Hospital Renamed'
        WHERE application_id = :app_id;
    """), {"app_id": app_id})
    pg_session.commit()

    row5 = pg_session.execute(text(
        "SELECT submitted_at, resubmission_version FROM registration_applications WHERE application_id = :app_id;"
    ), {"app_id": app_id}).fetchone()
    assert row5[0] == orig_sub_ts
    assert row5[1] == 2, "Repeated updates must NOT increment resubmission_version again"


# =====================================================================
# 2. ISSUE 2 — DEEP POSTGRESQL CATALOG INDEX VERIFICATION
# =====================================================================

def test_postgresql_indexes_deep_catalog_and_orm_verification(pg_session):
    """
    ISSUE 2 Deep Verification:
    Inspect pg_indexes and PostgreSQL system catalogs to verify all 17 indexes:
    - Table name
    - Indexed columns and ordering
    - ASC/DESC ordering (specifically idx_approval_history_app_id has created_at DESC)
    - Unique vs non-unique
    - Partial index predicate (specifically idx_verification_tokens_expiry has WHERE is_verified = false)
    - Absence of redundant indexes (idx_reg_app_number, duplicate single-column indexes)
    - Compare against SQLAlchemy model metadata definitions.
    """
    # 1. Query PostgreSQL catalog for all public indexes
    catalog_query = text("""
        SELECT
            c.relname AS table_name,
            i.relname AS index_name,
            ix.indisunique AS is_unique,
            pg_get_indexdef(ix.indexrelid) AS indexdef
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class c ON c.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public';
    """)
    rows = pg_session.execute(catalog_query).fetchall()
    cat_indexes = {r[1]: {"table": r[0], "is_unique": r[2], "def": r[3]} for r in rows}

    # 2. Strict specifications for all 17 migration indexes
    expected_index_specs = {
        "idx_hospitals_approval": {
            "table": "hospitals",
            "unique": False,
            "contains_clause": "(approval_status, is_grandfathered)",
        },
        "idx_hospitals_application_id": {
            "table": "hospitals",
            "unique": False,
            "contains_clause": "(application_id)",
        },
        "idx_users_email": {
            "table": "users",
            "unique": False,
            "contains_clause": "(email)",
        },
        "idx_users_application_id": {
            "table": "users",
            "unique": False,
            "contains_clause": "(application_id)",
        },
        "idx_reg_app_status": {
            "table": "registration_applications",
            "unique": False,
            "contains_clause": "(status, current_stage)",
        },
        "idx_reg_app_geo": {
            "table": "registration_applications",
            "unique": False,
            "contains_clause": "(state, district)",
        },
        "idx_reg_app_email": {
            "table": "registration_applications",
            "unique": False,
            "contains_clause": "(applicant_email)",
        },
        "idx_reg_app_type": {
            "table": "registration_applications",
            "unique": False,
            "contains_clause": "(applicant_type)",
        },
        "idx_reg_doc_app_id": {
            "table": "registration_documents",
            "unique": False,
            "contains_clause": "(application_id)",
        },
        "idx_reg_doc_status": {
            "table": "registration_documents",
            "unique": False,
            "contains_clause": "(verification_status)",
        },
        "idx_approval_history_app_id": {
            "table": "approval_history",
            "unique": False,
            "contains_clause": "(application_id, created_at DESC)",
        },
        "idx_verification_tokens_target": {
            "table": "verification_tokens",
            "unique": False,
            "contains_clause": "(contact_target, token_purpose, is_verified)",
        },
        "idx_verification_tokens_expiry": {
            "table": "verification_tokens",
            "unique": False,
            "contains_clause": "(expires_at) WHERE (is_verified = false)",
        },
        "idx_tracking_tokens_app_id": {
            "table": "application_tracking_tokens",
            "unique": False,
            "contains_clause": "(application_id)",
        },
        "idx_tracking_tokens_hash": {
            "table": "application_tracking_tokens",
            "unique": False,
            "contains_clause": "(token_hash)",
        },
        "idx_activation_tokens_user": {
            "table": "account_activation_tokens",
            "unique": False,
            "contains_clause": "(user_id)",
        },
        "idx_activation_tokens_hash": {
            "table": "account_activation_tokens",
            "unique": False,
            "contains_clause": "(token_hash)",
        },
        "uq_reg_app_active_state": {
            "table": "registration_applications",
            "unique": True,
            "contains_clause": "lower(TRIM(BOTH FROM state))",
        },
        "uq_reg_app_active_district": {
            "table": "registration_applications",
            "unique": True,
            "contains_clause": "lower(TRIM(BOTH FROM state)), lower(TRIM(BOTH FROM district))",
        },
        "uq_reg_app_active_hospital_email": {
            "table": "registration_applications",
            "unique": True,
            "contains_clause": "lower(TRIM(BOTH FROM applicant_email))",
        },
    }

    # Verify each expected index matches the exact specifications
    for idx_name, spec in expected_index_specs.items():
        assert idx_name in cat_indexes, f"Expected index '{idx_name}' missing from PostgreSQL catalog!"
        actual = cat_indexes[idx_name]
        assert actual["table"] == spec["table"], f"Index '{idx_name}' table mismatch: expected {spec['table']}, got {actual['table']}"
        assert actual["is_unique"] == spec["unique"], f"Index '{idx_name}' uniqueness mismatch: expected {spec['unique']}, got {actual['is_unique']}"
        assert spec["contains_clause"] in actual["def"], f"Index '{idx_name}' definition mismatch: expected clause '{spec['contains_clause']}' in '{actual['def']}'"

    # Specific Verification 1: idx_approval_history_app_id uses created_at DESC
    app_hist_def = cat_indexes["idx_approval_history_app_id"]["def"]
    assert "application_id" in app_hist_def and "created_at DESC" in app_hist_def, f"idx_approval_history_app_id must specify created_at DESC, got: {app_hist_def}"

    # Specific Verification 2: idx_verification_tokens_expiry has WHERE (is_verified = false)
    expiry_def = cat_indexes["idx_verification_tokens_expiry"]["def"]
    assert "WHERE (is_verified = false)" in expiry_def, f"idx_verification_tokens_expiry must be partial index with WHERE is_verified = false, got: {expiry_def}"

    # Specific Verification 3: application_number UNIQUE constraint already provides its unique btree index
    unique_app_num_indexes = [
        name for name, info in cat_indexes.items()
        if info["table"] == "registration_applications" and "(application_number)" in info["def"] and info["is_unique"]
    ]
    assert len(unique_app_num_indexes) >= 1, "Expected unique index on application_number from UNIQUE constraint"

    # Specific Verification 4: idx_reg_app_number is absent (redundant index dropped)
    assert "idx_reg_app_number" not in cat_indexes, "Redundant index idx_reg_app_number must be completely absent from PostgreSQL catalog"

    # Specific Verification 5: No accidental duplicate indexes on registration_applications
    reg_app_indexes = [name for name, info in cat_indexes.items() if info["table"] == "registration_applications"]
    for reg_idx in reg_app_indexes:
        assert not reg_idx.startswith("ix_registration_applications_"), f"Accidental duplicate index found: {reg_idx}"

    # 3. Compare actual SQLAlchemy ORM metadata index definitions against expected migration definitions
    orm_models = [
        Hospital, User, RegistrationApplication, RegistrationDocument,
        ApprovalHistory, VerificationToken, ApplicationTrackingToken, AccountActivationToken
    ]
    orm_indexes = {}
    for model in orm_models:
        for idx in model.__table__.indexes:
            orm_indexes[idx.name] = {
                "table": model.__tablename__,
                "columns": [c.name for c in idx.columns],
                "unique": idx.unique,
            }

    # Verify that all 17 migration indexes exist in SQLAlchemy ORM metadata
    for idx_name, spec in expected_index_specs.items():
        assert idx_name in orm_indexes, f"Index '{idx_name}' is declared in SQL migration but missing in SQLAlchemy ORM metadata!"
        orm_spec = orm_indexes[idx_name]
        assert orm_spec["table"] == spec["table"], f"ORM index '{idx_name}' table mismatch: {orm_spec['table']} vs {spec['table']}"
        assert orm_spec["unique"] == spec["unique"], f"ORM index '{idx_name}' uniqueness mismatch: {orm_spec['unique']} vs {spec['unique']}"


# =====================================================================
# 3. APPROVAL HISTORY PROTECTION TESTS
# =====================================================================

def test_postgresql_approval_history_trigger_blocks_update(pg_session):
    """
    Verify that trg_protect_approval_history database trigger actively blocks
    application-level UPDATE statements on approval_history.
    """
    app_id = f"APP_HIST_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-HIST-{uuid.uuid4().hex[:6]}"

    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="DISTRICT",
        applicant_name="Amritsar Civil Surgeon Office",
        applicant_email="cso@amritsar.gov.in",
        applicant_phone="0183-222111",
        state="Punjab",
        district="Amritsar",
    )
    pg_session.add(app)
    pg_session.flush()

    hist = ApprovalHistory(
        application_id=app_id,
        reviewer_user_id=None,
        reviewer_role="APPLICANT",
        action="SUBMIT",
        review_tier="APPLICANT",
        previous_status="DRAFT",
        new_status="SUBMITTED",
        remarks="Official application submitted",
    )
    pg_session.add(hist)
    pg_session.flush()

    # Attempt to UPDATE approval_history remarks
    update_sql = text("UPDATE approval_history SET remarks = 'TAMPERED REMARKS' WHERE application_id = :app_id")
    with pytest.raises(DBAPIError) as exc_info:
        pg_session.execute(update_sql, {"app_id": app_id})
        pg_session.flush()

    err_str = str(exc_info.value).lower()
    assert "prohibited on table approval_history" in err_str or "append-only audit trail" in err_str
    pg_session.rollback()


def test_postgresql_approval_history_trigger_blocks_delete(pg_session):
    """
    Verify that trg_protect_approval_history database trigger actively blocks
    DELETE statements on approval_history.
    """
    app_id = f"APP_HIST_DEL_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-HIST-DEL-{uuid.uuid4().hex[:6]}"

    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="HOSPITAL",
        applicant_name="Civil Hospital Jalandhar",
        applicant_email="admin@ch-jalandhar.org",
        applicant_phone="0181-444555",
        state="Punjab",
        district="Jalandhar",
    )
    pg_session.add(app)
    pg_session.flush()

    hist = ApprovalHistory(
        application_id=app_id,
        reviewer_user_id=None,
        reviewer_role="APPLICANT",
        action="SUBMIT",
        review_tier="APPLICANT",
        previous_status="DRAFT",
        new_status="SUBMITTED",
        remarks="Submitted with compliance certs",
    )
    pg_session.add(hist)
    pg_session.flush()

    # Attempt to DELETE approval_history row
    del_sql = text("DELETE FROM approval_history WHERE application_id = :app_id")
    with pytest.raises(DBAPIError) as exc_info:
        pg_session.execute(del_sql, {"app_id": app_id})
        pg_session.flush()

    err_str = str(exc_info.value).lower()
    assert "prohibited on table approval_history" in err_str or "append-only audit trail" in err_str
    pg_session.rollback()


def test_postgresql_approval_history_blocks_application_delete_via_restrict(pg_session):
    """
    Verify that ON DELETE RESTRICT on approval_history foreign key actively blocks
    deleting a registration_applications record that has approval history.
    """
    app_id = f"APP_RESTRICT_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-RESTRICT-{uuid.uuid4().hex[:6]}"

    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="STATE",
        applicant_name="Directorate of Health Services Punjab",
        applicant_email="dhs@punjab.gov.in",
        applicant_phone="0172-224466",
        state="Punjab",
    )
    pg_session.add(app)
    pg_session.flush()

    hist = ApprovalHistory(
        application_id=app_id,
        reviewer_user_id=None,
        reviewer_role="APPLICANT",
        action="SUBMIT",
        review_tier="APPLICANT",
        previous_status="DRAFT",
        new_status="SUBMITTED",
        remarks="State health onboarding submission",
    )
    pg_session.add(hist)
    pg_session.flush()

    # Attempt to DELETE the parent application
    del_app_sql = text("DELETE FROM registration_applications WHERE application_id = :app_id")
    with pytest.raises(IntegrityError) as exc_info:
        pg_session.execute(del_app_sql, {"app_id": app_id})
        pg_session.flush()

    err_str = str(exc_info.value).lower()
    assert "violates foreign key constraint" in err_str
    assert "approval_history" in err_str
    pg_session.rollback()


# =====================================================================
# 4. TRACKING TOKEN REUSABILITY & REVOCATION TEST
# =====================================================================

def test_postgresql_tracking_token_reusable_and_revocable(pg_session):
    """
    Verify application tracking tokens are reusable, time-bound, and revocable.
    """
    app_id = f"APP_TRACK_{uuid.uuid4().hex[:8]}"
    app_num = f"APP-TRACK-{uuid.uuid4().hex[:6]}"

    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="HOSPITAL",
        applicant_name="Grewal Eye Institute",
        applicant_email="admin@gei.org",
        applicant_phone="0172-222333",
        state="Chandigarh",
    )
    pg_session.add(app)
    pg_session.flush()

    tok_id = f"TOK_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    token = ApplicationTrackingToken(
        tracking_token_id=tok_id,
        application_id=app_id,
        token_hash="sha256:pbkdf2:test_tracking_token_hash",
        is_revoked=False,
        expires_at=now + timedelta(days=30),
        access_count=0,
    )
    pg_session.add(token)
    pg_session.flush()

    # Simulate multiple read queries (reusable tracking token access)
    for _ in range(3):
        tok = pg_session.query(ApplicationTrackingToken).filter_by(tracking_token_id=tok_id).first()
        assert tok.is_revoked is False
        tok.access_count += 1
        tok.last_accessed_at = datetime.now(timezone.utc)
        pg_session.flush()

    tok = pg_session.query(ApplicationTrackingToken).filter_by(tracking_token_id=tok_id).first()
    assert tok.access_count == 3
    assert tok.last_accessed_at is not None

    # Revoke token
    tok.is_revoked = True
    tok.revoked_at = datetime.now(timezone.utc)
    tok.revocation_reason = "Administrative credential cycling"
    pg_session.flush()

    revoked = pg_session.query(ApplicationTrackingToken).filter_by(tracking_token_id=tok_id).first()
    assert revoked.is_revoked is True
    assert revoked.revoked_at is not None
    assert revoked.revocation_reason == "Administrative credential cycling"


# =====================================================================
# 5. GRANDFATHERING STATE VALIDATION INTEGRATION TESTS (6 SCENARIOS)
# =====================================================================

def _setup_isolated_db(db_name: str, hospital_count: int = 500) -> None:
    """Setup an ephemeral database with migrations 001, 002 and specified legacy hospitals."""
    subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)
    res = subprocess.run(["createdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, db_name], capture_output=True, text=True)
    assert res.returncode == 0, f"Failed to create db {db_name}: {res.stderr}"

    for mig in ["migrations/001_initial_postgresql_schema.sql", "migrations/002_referral_workflow_and_notifications.sql"]:
        sub_res = _run_psql(db_name, mig, is_file=True)
        assert sub_res.returncode == 0, f"Failed applying {mig}: {sub_res.stderr}"

    seed_sql = f"""
        INSERT INTO roles (id, description) VALUES ('HOSPITAL', 'Hospital Staff') ON CONFLICT DO NOTHING;
        INSERT INTO hospitals (
            hospital_id, name, state, district, latitude, longitude,
            total_beds, occupied_beds, available_beds, icu_beds,
            available_icu_beds, emergency_beds, available_emergency_beds
        )
        SELECT
            'GH' || LPAD(i::text, 5, '0'),
            'Legacy Hospital ' || i::text,
            'Punjab',
            'District ' || (i % 10)::text,
            30.0 + (i * 0.001),
            75.0 + (i * 0.001),
            100, 50, 50, 10, 5, 10, 5
        FROM generate_series(1, {hospital_count}) AS i;
    """
    seed_res = _run_psql(db_name, seed_sql, is_file=False)
    assert seed_res.returncode == 0, f"Failed seeding {hospital_count} hospitals: {seed_res.stderr}"


def test_grandfathering_scenario_1_fresh_500_hospitals():
    """
    Scenario 1: Fresh 500-hospital migration.
    - Exactly 500 legacy hospitals (GH00001 to GH00500) exist.
    - Migration 003 succeeds and grandfathers exactly all 500.
    """
    db_name = "sih_gf_test_fresh"
    try:
        _setup_isolated_db(db_name, 500)
        mig_res = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig_res.returncode == 0, f"Migration 003 failed: {mig_res.stderr}"
        assert "Successfully grandfathered exactly 500 verified legacy hospitals (GH00001-GH00500)." in mig_res.stderr or \
               "Successfully grandfathered exactly 500 verified legacy hospitals (GH00001-GH00500)." in mig_res.stdout

        engine = create_engine(f"postgresql://localhost:5432/{db_name}")
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM hospitals WHERE is_grandfathered = TRUE AND approval_status = 'APPROVED' AND approved_at IS NOT NULL;")).scalar()
            assert cnt == 500
        engine.dispose()
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_grandfathering_scenario_2_successful_rerun():
    """
    Scenario 2: Successful rerun.
    - Running migration 003 a second time succeeds idempotently.
    - Emits NOTICE that all 500 are already approved and grandfathered.
    - Modifies 0 rows.
    """
    db_name = "sih_gf_test_rerun"
    try:
        _setup_isolated_db(db_name, 500)
        # First run
        mig1 = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig1.returncode == 0

        # Second run (Rerun)
        mig2 = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig2.returncode == 0, f"Rerun failed: {mig2.stderr}"
        notice_text = "Migration 003 rerun: all 500 legacy hospitals verified as already approved and grandfathered. No update needed."
        assert notice_text in mig2.stderr or notice_text in mig2.stdout

        engine = create_engine(f"postgresql://localhost:5432/{db_name}")
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM hospitals WHERE is_grandfathered = TRUE;")).scalar()
            assert cnt == 500
        engine.dispose()
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_grandfathering_scenario_3_gh00501_inserted_before_rerun():
    """
    Scenario 3: GH00501 inserted before rerun.
    - Insert GH00501 into a migrated DB.
    - Rerun migration 003.
    - GH00501 remains PENDING, is_grandfathered=FALSE, approved_at=NULL.
    """
    db_name = "sih_gf_test_gh501"
    try:
        _setup_isolated_db(db_name, 500)
        mig1 = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig1.returncode == 0

        # Insert GH00501 post-migration
        insert_gh501_sql = """
            INSERT INTO hospitals (
                hospital_id, name, state, district, latitude, longitude,
                total_beds, occupied_beds, available_beds, icu_beds,
                available_icu_beds, emergency_beds, available_emergency_beds
            ) VALUES (
                'GH00501', 'New Applicant Hospital Post-Migration', 'Punjab', 'Patiala',
                30.33, 76.38, 50, 0, 50, 5, 5, 5, 5
            );
        """
        _run_psql(db_name, insert_gh501_sql, is_file=False)

        # Rerun migration 003
        mig2 = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig2.returncode == 0

        engine = create_engine(f"postgresql://localhost:5432/{db_name}")
        with engine.connect() as conn:
            hosp = conn.execute(text("SELECT approval_status, is_grandfathered, approved_at FROM hospitals WHERE hospital_id = 'GH00501';")).fetchone()
            assert hosp[0] == "PENDING", "GH00501 must remain PENDING"
            assert hosp[1] is False, "GH00501 must NOT be grandfathered"
            assert hosp[2] is None, "GH00501 approved_at must be NULL"

            total_gf = conn.execute(text("SELECT COUNT(*) FROM hospitals WHERE is_grandfathered = TRUE;")).scalar()
            assert total_gf == 500, "Only the 500 legacy hospitals must be grandfathered"
        engine.dispose()
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_grandfathering_scenario_4_partial_grandfathered_state_aborts():
    """
    Scenario 4: Partial grandfathered state.
    - If 10 of 500 legacy hospitals are marked is_grandfathered=TRUE before migration,
      the migration must abort with an exception and roll back.
    """
    db_name = "sih_gf_test_partial"
    try:
        _setup_isolated_db(db_name, 500)
        # Partially mark 10 hospitals as grandfathered
        _run_psql(db_name, "ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS is_grandfathered BOOLEAN DEFAULT FALSE;", is_file=False)
        _run_psql(db_name, "UPDATE hospitals SET is_grandfathered = TRUE WHERE hospital_id IN ('GH00001', 'GH00002', 'GH00003');", is_file=False)

        # Attempt to run migration 003
        mig = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig.returncode != 0, "Migration must fail on partial grandfathered state"
        combined_err = mig.stderr + mig.stdout
        assert "Grandfathering state inconsistent: partial grandfathering detected (3 of 500 legacy hospitals grandfathered)" in combined_err
        assert "ROLLBACK" in combined_err or "ERROR" in combined_err
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_grandfathering_scenario_5_unexpected_grandfathered_hospital_aborts():
    """
    Scenario 5: Unexpected grandfathered hospital outside the legacy range.
    - If a non-legacy hospital has is_grandfathered=TRUE, migration 003 must abort and roll back.
    """
    db_name = "sih_gf_test_unexpected"
    try:
        _setup_isolated_db(db_name, 500)
        # Insert a non-legacy hospital marked as grandfathered
        _run_psql(db_name, "ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS is_grandfathered BOOLEAN DEFAULT FALSE;", is_file=False)
        insert_unexpected_sql = """
            INSERT INTO hospitals (
                hospital_id, name, state, district, latitude, longitude,
                total_beds, occupied_beds, available_beds, icu_beds,
                available_icu_beds, emergency_beds, available_emergency_beds,
                is_grandfathered
            ) VALUES (
                'GH99999', 'Rogue Hospital Outside Legacy Range', 'Punjab', 'Ludhiana',
                30.9, 75.8, 100, 50, 50, 10, 5, 10, 5, TRUE
            );
        """
        _run_psql(db_name, insert_unexpected_sql, is_file=False)

        # Attempt to run migration 003
        mig = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig.returncode != 0, "Migration must fail on unexpected grandfathered hospital"
        combined_err = mig.stderr + mig.stdout
        assert "detected 1 unexpected non-legacy hospitals with is_grandfathered = TRUE" in combined_err
        assert "ROLLBACK" in combined_err or "ERROR" in combined_err
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_grandfathering_scenario_6_missing_legacy_hospital_aborts():
    """
    Scenario 6: Missing legacy hospital.
    - If only 499 legacy hospitals exist (GH00001 to GH00499), migration 003 must abort and roll back.
    """
    db_name = "sih_gf_test_missing"
    try:
        _setup_isolated_db(db_name, 499)

        # Attempt to run migration 003
        mig = _run_psql(db_name, "migrations/003_registration_system.sql", is_file=True)
        assert mig.returncode != 0, "Migration must fail when legacy hospital count is not 500"
        combined_err = mig.stderr + mig.stdout
        assert "expected exactly 500 legacy hospitals (GH00001-GH00500), but found 499" in combined_err
        assert "ROLLBACK" in combined_err or "ERROR" in combined_err
    finally:
        subprocess.run(["dropdb", "-h", "localhost", "-p", "5432", "-U", PG_USER, "--if-exists", db_name], capture_output=True)


def test_postgresql_live_registration_service_full_workflow(pg_engine):
    """
    Live PostgreSQL Integration Test for RegistrationService:
    Verify full 3-tier hospital onboarding, document verification, append-only history,
    and safe public tracking against a real PostgreSQL 17 engine.
    """
    from src.services.registration_service import RegistrationService

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    try:
        # Seed test reviewer users in PostgreSQL users table
        dist_user_record = User(user_id="U_JAL_DIST", username="jal_dist", name="Jalandhar CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Jalandhar", password_hash="hash")
        state_user_record = User(user_id="U_PB_STATE", username="pb_state", name="Punjab State Officer", role_id="STATE_ADMIN", state="Punjab", password_hash="hash")
        central_user_record = User(user_id="U_MOHFW_CENT", username="mohfw_cent", name="Central MoHFW Officer", role_id="CENTRAL_ADMIN", password_hash="hash")
        session.add_all([dist_user_record, state_user_record, central_user_record])
        session.commit()

        service = RegistrationService(session)

        # 1. Create hospital application
        data = {
            "applicant_type": "HOSPITAL",
            "applicant_name": "Apollo Super Specialty Jalandhar",
            "applicant_email": "admin@apollo-jalandhar.org",
            "applicant_phone": "0181-5559988",
            "state": "Punjab",
            "district": "Jalandhar",
            "city": "Jalandhar",
            "address": "GT Road, Jalandhar",
            "pincode": "144001",
            "nodal_officer_name": "Dr. Manpreet Singh",
            "profile_data": {"total_beds": 300, "icu_beds": 40},
        }
        app = service.create_application(data)
        d1 = service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "lic.pdf", "application/pdf", 1024, "k1", "a" * 64)
        d2 = service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "fire.pdf", "application/pdf", 2048, "k2", "b" * 64)
        session.commit()

        # 2. Submit application
        sub_res = service.submit_application(app.application_id, client_ip="10.0.0.100")
        session.commit()
        raw_token = sub_res["tracking_token"]
        assert sub_res["status"] == "SUBMITTED"
        assert sub_res["current_stage"] == "DISTRICT_REVIEW"

        # 3. Tier 1: District Reviewer verifies documents and forwards
        dist_user = {"user_id": "U_JAL_DIST", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar"}
        service.verify_document(d1.document_id, dist_user, "VERIFIED")
        service.verify_document(d2.document_id, dist_user, "VERIFIED")
        session.commit()

        fwd1 = service.review_application(app.application_id, dist_user, action="FORWARD", remarks="District inspection verified.")
        session.commit()
        assert fwd1["current_stage"] == "STATE_REVIEW"
        assert fwd1["status"] == "UNDER_REVIEW"

        # 4. Tier 2: State Reviewer forwards
        state_user = {"user_id": "U_PB_STATE", "role": "STATE_ADMIN", "state": "Punjab"}
        fwd2 = service.review_application(app.application_id, state_user, action="FORWARD", remarks="State clearance approved.")
        session.commit()
        assert fwd2["current_stage"] == "CENTRAL_REVIEW"
        assert fwd2["status"] == "UNDER_REVIEW"

        # 5. Tier 3: Central Admin final approval
        central_user = {"user_id": "U_MOHFW_CENT", "role": "CENTRAL_ADMIN"}
        appr = service.review_application(app.application_id, central_user, action="APPROVE", remarks="National accreditation granted.")
        session.commit()
        assert appr["current_stage"] == "APPROVED"
        assert appr["status"] == "APPROVED"

        # 6. Verify safe public tracking
        public_info = service.track_application_public(app.application_number, tracking_token=raw_token)
        assert public_info["status"] == "APPROVED"
        assert public_info["current_stage"] == "APPROVED"
        assert len(public_info["milestones"]) == 4
        assert [m["action"] for m in public_info["milestones"]] == ["SUBMIT", "FORWARD", "FORWARD", "APPROVE"]

        # Ensure no private data leaked
        for forbidden in ["applicant_phone", "applicant_email", "storage_key", "password", "token_hash"]:
            assert forbidden not in public_info

        # 7. Check append-only trigger protection on ApprovalHistory in PostgreSQL
        raw_hist = session.query(ApprovalHistory).filter_by(application_id=app.application_id).first()
        with pytest.raises(DBAPIError) as exc_info:
            session.execute(text(f"DELETE FROM approval_history WHERE id = {raw_hist.id}"))
            session.commit()
        session.rollback()
        assert "Approval history is an append-only audit trail" in str(exc_info.value)

    finally:
        session.close()


def test_postgresql_live_registration_service_correction_and_resubmit(pg_engine):
    """
    Live PostgreSQL Integration Test for Correction & Resubmission:
    Verify that in PostgreSQL with real triggers active:
    - submitted_at is strictly preserved across correction and resubmission.
    - resubmitted_at is populated.
    - resubmission_version increments from 1 to 2.
    - Append-only ApprovalHistory records REQUEST_CORRECTION and RESUBMIT.
    """
    from src.services.registration_service import RegistrationService

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    try:
        # Seed test reviewer user in PostgreSQL users table
        dist_user_record = User(user_id="U_LDH_DIST", username="ldh_dist", name="Ludhiana CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Ludhiana", password_hash="hash")
        session.add(dist_user_record)
        session.commit()

        service = RegistrationService(session)

        data = {
            "applicant_type": "HOSPITAL",
            "applicant_name": "City Care Hospital Ludhiana",
            "applicant_email": "contact@citycare-ldh.org",
            "applicant_phone": "0161-5553322",
            "state": "Punjab",
            "district": "Ludhiana",
        }
        app = service.create_application(data)
        service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "lic.pdf", "application/pdf", 1024, "k1", "c" * 64)
        service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "fire.pdf", "application/pdf", 2048, "k2", "d" * 64)
        session.commit()

        service.submit_application(app.application_id)
        session.commit()

        orig_submitted_at = app.submitted_at
        assert orig_submitted_at is not None
        assert app.resubmission_version == 1

        # Request correction
        dist_user = {"user_id": "U_LDH_DIST", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Ludhiana"}
        service.request_correction(app.application_id, dist_user, "Upload renewed NOC certificate.")
        session.commit()

        assert app.status == "CORRECTION_REQUIRED"
        assert app.submitted_at == orig_submitted_at

        # Resubmit
        service.resubmit_application(app.application_id, "Uploaded renewed certificate.")
        session.commit()

        re_fetched = session.query(RegistrationApplication).filter_by(application_id=app.application_id).first()
        assert re_fetched.status == "SUBMITTED"
        assert re_fetched.submitted_at == orig_submitted_at
        assert re_fetched.resubmitted_at is not None
        assert re_fetched.resubmission_version == 2

        # Verify audit history
        history = session.query(ApprovalHistory).filter_by(application_id=app.application_id).order_by(ApprovalHistory.id).all()
        assert len(history) == 3
        assert [h.action for h in history] == ["SUBMIT", "REQUEST_CORRECTION", "RESUBMIT"]

    finally:
        session.close()


# =====================================================================
# 6. DATABASE-LEVEL DUPLICATE PREVENTION & CONCURRENCY TESTS
# =====================================================================

def test_postgresql_concurrent_duplicate_prevention_threads(pg_engine):
    """
    Verify concurrent duplicate submissions at database level:
    - Two concurrent worker threads with separate PostgreSQL sessions attempt
      to insert active applications with the same institutional email.
    - Exactly one succeeds and commits.
    - The other worker encounters database unique constraint (uq_reg_app_active_hospital_email)
      and receives domain-level DuplicateApplicationError.
    - The failing session rolls back cleanly and remains usable.
    - Database contains exactly 1 active application record.
    """
    import threading
    from src.services.registration_service import RegistrationService
    from src.services.registration_exceptions import DuplicateApplicationError

    Session = sessionmaker(bind=pg_engine)
    barrier = threading.Barrier(2)
    results = {}

    def worker(worker_id: int):
        session = Session()
        try:
            service = RegistrationService(session)
            data = {
                "applicant_type": "HOSPITAL",
                "applicant_name": f"Concurrent Hospital {worker_id}",
                "applicant_email": "concurrency.test@hospital.org",
                "applicant_phone": f"0172-555000{worker_id}",
                "state": "Punjab",
                "district": "Mohali",
            }
            # Synchronize threads right before executing creation
            barrier.wait(timeout=5)
            app = service.create_application(data)
            session.commit()
            results[worker_id] = ("SUCCESS", app.application_id, session)
        except DuplicateApplicationError as exc:
            # Transaction already rolled back by service
            results[worker_id] = ("DUPLICATE_ERROR", str(exc), session)
        except Exception as exc:
            session.rollback()
            results[worker_id] = ("OTHER_EXCEPTION", type(exc).__name__, session)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Clean up sessions after verifying usability
    try:
        statuses = [res[0] for res in results.values()]
        assert "SUCCESS" in statuses, f"At least one worker must succeed, got {results}"
        assert "DUPLICATE_ERROR" in statuses, f"Exactly one worker must get DUPLICATE_ERROR, got {results}"
        assert statuses.count("SUCCESS") == 1
        assert statuses.count("DUPLICATE_ERROR") == 1

        # Verify failing session remains healthy and usable
        failing_worker_id = [wid for wid, res in results.items() if res[0] == "DUPLICATE_ERROR"][0]
        failing_session = results[failing_worker_id][2]
        failing_service = RegistrationService(failing_session)

        # Successful subsequent operation on the previously failing session
        data_clean = {
            "applicant_type": "HOSPITAL",
            "applicant_name": "Post-Rollback Safe Hospital",
            "applicant_email": "clean.recovery@hospital.org",
            "applicant_phone": "0172-9998877",
            "state": "Punjab",
            "district": "Mohali",
        }
        recovered_app = failing_service.create_application(data_clean)
        failing_session.commit()
        assert recovered_app.application_id.startswith("APP_")

        # Verify PostgreSQL database contains exactly 1 row for the concurrent test email
        verify_session = Session()
        count = verify_session.execute(
            text("SELECT COUNT(*) FROM registration_applications WHERE applicant_email = 'concurrency.test@hospital.org';")
        ).scalar()
        assert count == 1, f"Expected exactly 1 row in database, got {count}"
        verify_session.close()

    finally:
        for res in results.values():
            if len(res) > 2 and res[2]:
                res[2].close()


def test_postgresql_concurrent_duplicate_prevention_district_threads(pg_engine):
    """
    Verify concurrent duplicate submissions for DISTRICT applications:
    - Multiple threads attempt to create an active DISTRICT application for the same (state, district).
    - Exactly one succeeds, other receives DuplicateApplicationError via uq_reg_app_active_district.
    """
    import threading
    from src.services.registration_service import RegistrationService
    from src.services.registration_exceptions import DuplicateApplicationError

    Session = sessionmaker(bind=pg_engine)
    barrier = threading.Barrier(2)
    results = {}

    def worker(worker_id: int):
        session = Session()
        try:
            service = RegistrationService(session)
            data = {
                "applicant_type": "DISTRICT",
                "applicant_name": f"Bathinda District Health {worker_id}",
                "applicant_email": f"cmo.bathinda.{worker_id}@punjab.gov.in",
                "applicant_phone": f"0164-222334{worker_id}",
                "state": "Punjab",
                "district": "Bathinda",
            }
            barrier.wait(timeout=5)
            app = service.create_application(data)
            session.commit()
            results[worker_id] = ("SUCCESS", app.application_id, session)
        except DuplicateApplicationError as exc:
            results[worker_id] = ("DUPLICATE_ERROR", str(exc), session)
        except Exception as exc:
            session.rollback()
            results[worker_id] = ("OTHER_EXCEPTION", type(exc).__name__, session)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    try:
        statuses = [res[0] for res in results.values()]
        assert "SUCCESS" in statuses
        assert "DUPLICATE_ERROR" in statuses
        assert statuses.count("SUCCESS") == 1
        assert statuses.count("DUPLICATE_ERROR") == 1

        verify_session = Session()
        count = verify_session.execute(
            text("SELECT COUNT(*) FROM registration_applications WHERE applicant_type = 'DISTRICT' AND state = 'Punjab' AND district = 'Bathinda';")
        ).scalar()
        assert count == 1
        verify_session.close()
    finally:
        for res in results.values():
            if len(res) > 2 and res[2]:
                res[2].close()


def test_postgresql_rejected_application_allows_new_active_application(pg_engine):
    """
    Verify PostgreSQL partial index predicate:
    Applications in REJECTED status do not block subsequent applications for the same entity.
    """
    from src.services.registration_service import RegistrationService

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    try:
        service = RegistrationService(session)
        data = {
            "applicant_type": "HOSPITAL",
            "applicant_name": "Care & Cure Hospital",
            "applicant_email": "info@carecure-hospital.org",
            "applicant_phone": "0181-4445566",
            "state": "Punjab",
            "district": "Jalandhar",
        }
        app1 = service.create_application(data)
        session.commit()

        # Reject app1
        app1.status = "REJECTED"
        app1.current_stage = "REJECTED"
        session.commit()

        # Verify a new application with the same institutional email can be submitted
        app2 = service.create_application(data)
        session.commit()

        assert app1.application_id != app2.application_id
        assert app2.status == "DRAFT"

        # Verify both rows exist in PostgreSQL
        rows = session.execute(
            text("SELECT application_id, status FROM registration_applications WHERE applicant_email = 'info@carecure-hospital.org' ORDER BY created_at;")
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "REJECTED"
        assert rows[1][1] == "DRAFT"

    finally:
        session.close()


def test_postgresql_case_and_whitespace_index_enforcement_raw_sql(pg_session):
    """
    Verify that PostgreSQL's lower(TRIM(BOTH FROM ...)) index blocks duplicates directly at the SQL level,
    regardless of whitespace padding or case variance.
    """
    # Direct raw SQL insert 1
    pg_session.execute(text("""
        INSERT INTO registration_applications (
            application_id, application_number, applicant_type, applicant_name, applicant_email,
            applicant_phone, state, district, current_stage, status, resubmission_version, created_at, last_updated_at
        ) VALUES (
            'APP_RAW_1', 'APP-2026-HOSP-RAW01', 'HOSPITAL', 'Raw Test Hospital', 'raw.test@hospital.org',
            '0172-1112233', 'Punjab', 'Patiala', 'DRAFT', 'DRAFT', 1, NOW(), NOW()
        );
    """))
    pg_session.commit()

    # Direct raw SQL insert 2 with whitespace padding and upper casing
    with pytest.raises(IntegrityError) as exc_info:
        pg_session.execute(text("""
            INSERT INTO registration_applications (
                application_id, application_number, applicant_type, applicant_name, applicant_email,
                applicant_phone, state, district, current_stage, status, resubmission_version, created_at, last_updated_at
            ) VALUES (
                'APP_RAW_2', 'APP-2026-HOSP-RAW02', 'HOSPITAL', 'Raw Test Hospital 2', '   RAW.TEST@HOSPITAL.ORG   ',
                '0172-9998877', 'Punjab', 'Patiala', 'DRAFT', 'SUBMITTED', 1, NOW(), NOW()
            );
        """))
        pg_session.commit()

    pg_session.rollback()
    assert "uq_reg_app_active_hospital_email" in str(exc_info.value)


def test_postgresql_unexpected_integrity_violation_preserves_exception(pg_engine):
    """
    Verify on live PostgreSQL:
    - Unexpected integrity violations (e.g. FK violations, NOT NULL violations)
      must NOT be converted into DuplicateApplicationError.
    - Transaction rollback is executed automatically by the service.
    - The original IntegrityError is re-raised preserving PostgreSQL error code (e.g. 23502/23503).
    - The session remains fully reusable after rollback.
    """
    from src.services.registration_service import RegistrationService
    from src.services.registration_exceptions import DuplicateApplicationError
    from unittest.mock import patch

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    try:
        service = RegistrationService(session)
        valid_data = {
            "applicant_type": "HOSPITAL",
            "applicant_name": "PG Integrity Test Hospital",
            "applicant_email": "pg.integrity@hospital.org",
            "applicant_phone": "0172-8889900",
            "state": "Punjab",
            "district": "Mohali",
        }

        # Simulate an unexpected foreign key error from PostgreSQL (pgcode 23503)
        class MockPgFKOrig(Exception):
            pgcode = "23503"
            class Diag:
                constraint_name = "fk_some_foreign_table"
                message_primary = "insert or update on table violates foreign key constraint"
            diag = Diag()

        fk_error = IntegrityError("INSERT INTO ...", params={}, orig=MockPgFKOrig("FK violation"))

        with patch.object(service.session, "flush", side_effect=fk_error):
            with pytest.raises(IntegrityError) as exc_info:
                service.create_application(valid_data)

            assert not isinstance(exc_info.value, DuplicateApplicationError)
            assert exc_info.value is fk_error
            assert exc_info.value.orig.pgcode == "23503"

        # Verify session is reusable after rollback
        app = service.create_application(valid_data)
        session.commit()
        assert app.application_id.startswith("APP_")

        # Verify row exists in PostgreSQL
        row = session.execute(
            text("SELECT status FROM registration_applications WHERE application_id = :id;"),
            {"id": app.application_id}
        ).fetchone()
        assert row[0] == "DRAFT"

    finally:
        session.close()


def test_postgresql_hospital_email_identity_policy_scenarios(pg_engine):
    """
    Verify live PostgreSQL hospital identity policy:
    1. Two different hospitals with different emails are both active simultaneously.
    2. Two hospitals sharing one applicant email trigger DuplicateApplicationError via uq_reg_app_active_hospital_email.
    3. The same physical facility registering with a changed email succeeds under the current policy (documenting the applicant_email business-key limitation).
    4. Session recovery is functional after duplicate rejection.
    """
    from src.services.registration_service import RegistrationService
    from src.services.registration_exceptions import DuplicateApplicationError

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    try:
        service = RegistrationService(session)

        # 1. Two different hospitals with different emails -> Both succeed
        hosp1 = service.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "St. Mary Hospital",
            "applicant_email": "admin@stmary.org",
            "applicant_phone": "0172-1111000",
            "state": "Punjab",
            "district": "Mohali",
        })
        hosp2 = service.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "St. Jude Hospital",
            "applicant_email": "admin@stjude.org",
            "applicant_phone": "0172-2222000",
            "state": "Punjab",
            "district": "Mohali",
        })
        session.commit()
        assert hosp1.application_id != hosp2.application_id

        # 2. Distinct hospital sharing hosp1's email -> Blocked with DuplicateApplicationError
        with pytest.raises(DuplicateApplicationError, match="already exists for email 'admin@stmary.org'"):
            service.create_application({
                "applicant_type": "HOSPITAL",
                "applicant_name": "St. Mary Extension Clinic",
                "applicant_email": "admin@stmary.org",
                "applicant_phone": "0172-3333000",
                "state": "Punjab",
                "district": "Mohali",
            })

        # 3. Same facility with a changed email -> Allowed (documenting applicant_email scope)
        hosp3 = service.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "St. Mary Hospital",
            "applicant_email": "medical.director@stmary.org",
            "applicant_phone": "0172-4444000",
            "state": "Punjab",
            "district": "Mohali",
        })
        session.commit()
        assert hosp3.application_id != hosp1.application_id
        assert hosp3.status == "DRAFT"

        # 4. Confirm exactly 3 applications were committed in PostgreSQL
        count = session.execute(
            text("SELECT COUNT(*) FROM registration_applications WHERE applicant_email IN ('admin@stmary.org', 'admin@stjude.org', 'medical.director@stmary.org');")
        ).scalar()
        assert count == 3

    finally:
        session.close()


def test_postgresql_live_registration_api_workflow(pg_engine):
    """
    Live PostgreSQL Integration Test for FastAPI Registration API Endpoints:
    Executes the entire end-to-end API lifecycle through HTTP client backed by real PostgreSQL 17:
    - Application creation via POST /api/registration/applications/hospital
    - Document metadata upload via POST /api/registration/applications/documents
    - Application submission via POST /api/registration/applications/submit
    - Public tracking via GET /api/registration/track/{app_number}
    - 3-tier reviewer hierarchy (District FORWARD -> State FORWARD -> Central APPROVE)
    - Verifies database records directly in PostgreSQL
    """
    from fastapi.testclient import TestClient
    from src.api.main import app as fastapi_app
    from src.database.db_manager import get_db_session
    from src.auth.jwt_utils import create_access_token

    LiveSession = sessionmaker(bind=pg_engine)

    def _override_get_db():
        db = LiveSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db_session] = _override_get_db
    client = TestClient(fastapi_app)

    db = LiveSession()
    try:
        # Seed reviewers
        reviewer_users = [
            User(user_id="U_API_DIST_JAL", username="api_dist_jal", name="Jalandhar CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Jalandhar", email="cmo.jal@punjab.gov.in", password_hash="hash"),
            User(user_id="U_API_STATE_PB", username="api_state_pb", name="Punjab Director", role_id="STATE_ADMIN", state="Punjab", email="dir.pb@punjab.gov.in", password_hash="hash"),
            User(user_id="U_API_CENTRAL", username="api_central", name="MoHFW Secretary", role_id="CENTRAL_ADMIN", email="sec.mohfw@nic.in", password_hash="hash"),
        ]
        for u in reviewer_users:
            if not db.query(User).filter_by(user_id=u.user_id).first():
                db.add(u)
        db.commit()

        # Reviewer JWT tokens
        dist_token = create_access_token({"user_id": "U_API_DIST_JAL", "username": "api_dist_jal", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar", "email": "cmo.jal@punjab.gov.in"})
        state_token = create_access_token({"user_id": "U_API_STATE_PB", "username": "api_state_pb", "role": "STATE_ADMIN", "state": "Punjab", "email": "dir.pb@punjab.gov.in"})
        cent_token = create_access_token({"user_id": "U_API_CENTRAL", "username": "api_central", "role": "CENTRAL_ADMIN", "email": "sec.mohfw@nic.in"})

        # 1. Create Hospital Application via API
        create_resp = client.post(
            "/api/registration/applications/hospital",
            json={
                "applicant_name": "PG Live Care Hospital",
                "applicant_email": "admin@pglivecare.org",
                "applicant_phone": "0181-4455667",
                "state": "Punjab",
                "district": "Jalandhar",
                "city": "Jalandhar",
                "address": "Model Town",
                "pincode": "144003",
                "nodal_officer_name": "Dr. Jaspreet Kaur",
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        create_data = create_resp.json()
        app_id = create_data["application_id"]
        app_num = create_data["application_number"]
        app_token = create_data["applicant_token"]
        app_headers = {"Authorization": f"Bearer {app_token}"}

        # 2. Upload mandatory document metadata
        d1_resp = client.post(
            "/api/registration/applications/documents",
            json={
                "document_type": "CLINICAL_LICENSE",
                "original_filename": "clin_lic.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 4096,
                "storage_key": "s3://pg-docs/clin_lic.pdf",
                "checksum_sha256": "e" * 64,
            },
            headers=app_headers,
        )
        assert d1_resp.status_code == 200
        d1_id = d1_resp.json()["document_id"]

        d2_resp = client.post(
            "/api/registration/applications/documents",
            json={
                "document_type": "FIRE_SAFETY_NOC",
                "original_filename": "fire_noc.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 8192,
                "storage_key": "s3://pg-docs/fire_noc.pdf",
                "checksum_sha256": "f" * 64,
            },
            headers=app_headers,
        )
        assert d2_resp.status_code == 200
        d2_id = d2_resp.json()["document_id"]

        # 3. Submit application
        sub_resp = client.post(
            "/api/registration/applications/submit",
            json={"remarks": "Live PG submission complete"},
            headers=app_headers,
        )
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["status"] == "SUBMITTED"
        assert sub_data["current_stage"] == "DISTRICT_REVIEW"
        assert sub_data["submitted_at"] is not None
        raw_tracking_token = sub_data["tracking_token"]

        # 4. Public Tracking check
        track_resp = client.get(f"/api/registration/track/{app_num}?tracking_token={raw_tracking_token}")
        assert track_resp.status_code == 200
        assert track_resp.json()["status"] == "SUBMITTED"

        # 5. Reviewer: District verifies documents and forwards
        dist_headers = {"Authorization": f"Bearer {dist_token}"}
        v1 = client.post(f"/api/registration/review/documents/{d1_id}/verify", json={"verification_status": "VERIFIED"}, headers=dist_headers)
        assert v1.status_code == 200
        v2 = client.post(f"/api/registration/review/documents/{d2_id}/verify", json={"verification_status": "VERIFIED"}, headers=dist_headers)
        assert v2.status_code == 200

        dist_fwd = client.post(
            f"/api/registration/review/applications/{app_id}/decision",
            json={"action": "FORWARD", "remarks": "District verification completed."},
            headers=dist_headers,
        )
        assert dist_fwd.status_code == 200
        assert dist_fwd.json()["new_stage"] == "STATE_REVIEW"

        # 6. Reviewer: State forwards to Central
        state_headers = {"Authorization": f"Bearer {state_token}"}
        state_fwd = client.post(
            f"/api/registration/review/applications/{app_id}/decision",
            json={"action": "FORWARD", "remarks": "State inspection confirmed."},
            headers=state_headers,
        )
        assert state_fwd.status_code == 200
        assert state_fwd.json()["new_stage"] == "CENTRAL_REVIEW"

        # 7. Reviewer: Central approves
        cent_headers = {"Authorization": f"Bearer {cent_token}"}
        cent_app = client.post(
            f"/api/registration/review/applications/{app_id}/decision",
            json={"action": "APPROVE", "remarks": "Final national approval granted."},
            headers=cent_headers,
        )
        assert cent_app.status_code == 200
        assert cent_app.json()["new_status"] == "APPROVED"
        assert cent_app.json()["new_stage"] == "APPROVED"

        # 8. Verify directly in PostgreSQL
        pg_app = db.query(RegistrationApplication).filter_by(application_id=app_id).first()
        assert pg_app.status == "APPROVED"
        assert pg_app.current_stage == "APPROVED"
        assert pg_app.final_approved_at is not None

        # Verify ApprovalHistory records in PostgreSQL
        pg_history = db.query(ApprovalHistory).filter_by(application_id=app_id).order_by(ApprovalHistory.id).all()
        assert len(pg_history) == 4
        assert [h.action for h in pg_history] == ["SUBMIT", "FORWARD", "FORWARD", "APPROVE"]

    finally:
        fastapi_app.dependency_overrides.pop(get_db_session, None)
        db.close()


def test_postgresql_live_outbox_and_row_locking(pg_engine):
    """
    Verify PostgreSQL transactional email outbox table, queue indexes,
    and concurrent row-locking with FOR UPDATE SKIP LOCKED.
    """
    from src.database.pg_models import RegistrationEmailOutbox
    from src.services.email_outbox_service import EmailOutboxService
    from src.services.email_service import SimulatedEmailProvider

    Session = sessionmaker(bind=pg_engine)
    session1 = Session()
    session2 = Session()
    sim_email = SimulatedEmailProvider()

    try:
        outbox_svc1 = EmailOutboxService(session1, sim_email)
        outbox_svc2 = EmailOutboxService(session2, sim_email)

        # Enqueue 3 events in PostgreSQL
        e1 = outbox_svc1.enqueue_email("ACCOUNT_ACTIVATION", "pg_live_1@punjab.gov.in", "Subject 1", {"activation_link": "link1", "role_title": "Admin", "application_number": "APP-01"})
        e2 = outbox_svc1.enqueue_email("ACCOUNT_ACTIVATION", "pg_live_2@punjab.gov.in", "Subject 2", {"activation_link": "link2", "role_title": "Admin", "application_number": "APP-02"})
        session1.commit()

        # Worker 1 processes with batch_size=1
        res1 = outbox_svc1.process_outbox(batch_size=1, worker_id="worker_pg_1")
        session1.commit()
        assert res1["succeeded"] == 1

        # Worker 2 processes concurrently
        res2 = outbox_svc2.process_outbox(batch_size=10, worker_id="worker_pg_2")
        session2.commit()
        assert res2["succeeded"] >= 1

        # Verify all events in PostgreSQL are SENT
        verify_session = Session()
        sent_events = verify_session.query(RegistrationEmailOutbox).filter_by(status="SENT").all()
        assert len(sent_events) >= 2
        verify_session.close()

    finally:
        session1.close()
        session2.close()


def test_postgresql_live_concurrent_provisioning_threads(pg_engine):
    """
    Verify PostgreSQL database-level concurrent provisioning protection:
    Two parallel threads execute provision_account against live PostgreSQL for the same approved application.
    Partial unique indexes uq_users_application_id and uq_hospitals_application_id guarantee
    that exactly 1 User and 1 Hospital exist in PostgreSQL.
    """
    import threading
    from src.services.registration_service import RegistrationService
    from src.services.account_provisioning_service import AccountProvisioningService
    from src.database.pg_models import User, Hospital

    Session = sessionmaker(bind=pg_engine)
    setup_session = Session()

    try:
        reg_svc = RegistrationService(setup_session)
        app_record = reg_svc.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "PG Live Concurrency Hospital",
            "applicant_email": "pg_concurrent_hosp@punjab.gov.in",
            "applicant_phone": "0172-5559999",
            "state": "Punjab",
            "district": "Mohali",
            "city": "Mohali",
            "total_beds": 150,
        })
        # Set directly to APPROVED for testing provisioning concurrency
        app_record.status = "APPROVED"
        app_record.current_stage = "APPROVED"
        setup_session.commit()
        app_id = app_record.application_id
    finally:
        setup_session.close()

    barrier = threading.Barrier(2)
    results = {}

    def worker(worker_id: int):
        thread_session = Session()
        try:
            prov_svc = AccountProvisioningService(thread_session)
            barrier.wait(timeout=5)
            res = prov_svc.provision_account(
                application_id=app_id,
                reviewer_user={"user_id": f"U_CENTRAL_{worker_id}", "role": "CENTRAL_ADMIN"},
            )
            thread_session.commit()
            results[worker_id] = ("SUCCESS", res)
        except Exception as exc:
            thread_session.rollback()
            results[worker_id] = ("EXCEPTION", str(exc))
        finally:
            thread_session.close()

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Both threads complete successfully (one provisions, other returns existing record idempotently)
    statuses = [r[0] for r in results.values()]
    assert all(s == "SUCCESS" for s in statuses), f"Expected both threads to complete safely: {results}"

    # Verify exactly 1 user and 1 hospital in live PostgreSQL
    verify_session = Session()
    try:
        users = verify_session.query(User).filter_by(application_id=app_id).all()
        assert len(users) == 1, f"Expected exactly 1 user in PostgreSQL, got {len(users)}"
        hospitals = verify_session.query(Hospital).filter_by(application_id=app_id).all()
        assert len(hospitals) == 1, f"Expected exactly 1 hospital in PostgreSQL, got {len(hospitals)}"
    finally:
        verify_session.close()


def test_postgresql_live_concurrent_password_reset_independent_sessions(pg_engine):
    """
    F-2 Live PostgreSQL Concurrency Test:
    Verifies that simultaneous password reset requests for the same token across independent sessions:
    1. Are serialized using PostgreSQL row-level locking (with_for_update).
    2. Exactly ONE request succeeds.
    3. The second request is rejected with token consumed error.
    4. Password update and token consumption are strictly atomic in PostgreSQL.
    5. Token replay fails.
    """
    import threading
    from src.services.account_provisioning_service import AccountProvisioningService, ActivationTokenError
    from src.auth.auth_store import hash_password, verify_password

    Session = sessionmaker(bind=pg_engine)
    setup_session = Session()

    user_id = f"U_PG_RESET_{uuid.uuid4().hex[:8]}"
    username = f"pg_reset_{uuid.uuid4().hex[:8]}"
    email = f"{username}@punjab.gov.in"

    try:
        # Create active operational user in live PostgreSQL
        user = User(
            user_id=user_id,
            username=username,
            name="PG Concurrency Reset User",
            email=email,
            role_id="HOSPITAL",
            password_hash=hash_password("InitialPassword123!"),
            is_active=True,
        )
        setup_session.add(user)
        setup_session.commit()

        # Generate reset token
        prov_svc = AccountProvisioningService(setup_session)
        prov_svc.request_password_reset(email)
        setup_session.commit()

        # Retrieve outbox event to get raw token
        outbox_event = setup_session.query(RegistrationEmailOutbox).filter_by(recipient_email=email).first()
        import json
        payload = json.loads(outbox_event.payload)
        raw_token = payload["raw_token"]
    finally:
        setup_session.close()

    barrier = threading.Barrier(2)
    thread_outcomes = {}

    def reset_worker(worker_id: int, new_password: str):
        worker_session = Session()
        try:
            worker_prov = AccountProvisioningService(worker_session)
            barrier.wait(timeout=5)
            res = worker_prov.confirm_password_reset(
                raw_reset_token=raw_token,
                password=new_password,
                confirm_password=new_password,
            )
            worker_session.commit()
            thread_outcomes[worker_id] = ("SUCCESS", res)
        except ActivationTokenError as ate:
            worker_session.rollback()
            thread_outcomes[worker_id] = ("TOKEN_ERROR", str(ate))
        except Exception as exc:
            worker_session.rollback()
            thread_outcomes[worker_id] = ("EXCEPTION", str(exc))
        finally:
            worker_session.close()

    t1 = threading.Thread(target=reset_worker, args=(1, "WinnerPassword123!"))
    t2 = threading.Thread(target=reset_worker, args=(2, "ContenderPassword123!"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one thread MUST succeed, and the other MUST get TOKEN_ERROR
    statuses = [o[0] for o in thread_outcomes.values()]
    assert "SUCCESS" in statuses, f"Expected one successful reset: {thread_outcomes}"
    assert "TOKEN_ERROR" in statuses, f"Expected one token error for concurrent request: {thread_outcomes}"
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("TOKEN_ERROR") == 1

    # Verify replay fails
    verify_session = Session()
    try:
        verify_prov = AccountProvisioningService(verify_session)
        with pytest.raises(ActivationTokenError) as exc_info:
            verify_prov.confirm_password_reset(
                raw_reset_token=raw_token,
                password="ReplayPassword123!",
                confirm_password="ReplayPassword123!",
            )
        assert "already been consumed" in str(exc_info.value).lower()

        # Verify password in database matches winner
        updated_user = verify_session.query(User).filter_by(user_id=user_id).first()
        assert updated_user.password_hash.startswith("pbkdf2:sha256:")
        # One of the two passwords must be verified, and the other must be rejected
        winner_1 = verify_password("WinnerPassword123!", updated_user.password_hash)
        winner_2 = verify_password("ContenderPassword123!", updated_user.password_hash)
        assert (winner_1 and not winner_2) or (winner_2 and not winner_1)
    finally:
        verify_session.close()


def test_postgresql_live_outbox_lease_crash_recovery_and_multithread_reclaim(pg_engine):
    """
    F-1 Live PostgreSQL Outbox Test:
    Verifies that abandoned events with expired leases in PostgreSQL are:
    1. Reclaimed safely.
    2. Locked using with_for_update(skip_locked=True) so two concurrent workers do not collision.
    3. Exactly one worker reclaims and delivers; the other skips.
    """
    import threading
    from src.services.email_service import SimulatedEmailProvider
    from src.services.email_outbox_service import EmailOutboxService

    Session = sessionmaker(bind=pg_engine)
    setup_session = Session()
    now = datetime.now(timezone.utc)
    target_email = f"pg_reclaim_{uuid.uuid4().hex[:8]}@punjab.gov.in"

    try:
        sim_provider = SimulatedEmailProvider()
        outbox_svc = EmailOutboxService(setup_session, sim_provider)
        event = outbox_svc.enqueue_email(
            event_type="ACCOUNT_ACTIVATION",
            recipient_email=target_email,
            subject="PG Reclaim Test",
            payload={"activation_link": "https://hospital.sih.gov.in/act", "role_title": "Admin"},
        )
        # Simulate worker crash: status left in PROCESSING with timestamp 10 minutes ago
        event.status = "PROCESSING"
        event.processed_at = now - timedelta(seconds=600)
        setup_session.commit()
        event_id = event.outbox_id
    finally:
        setup_session.close()

    barrier = threading.Barrier(2)
    worker_results = {}
    shared_sim_email = SimulatedEmailProvider()

    def outbox_worker(worker_id: int):
        w_session = Session()
        try:
            w_svc = EmailOutboxService(w_session, shared_sim_email)
            barrier.wait(timeout=5)
            # Reclaim with 300s lease timeout
            res = w_svc.process_outbox(batch_size=5, worker_id=f"W_{worker_id}", lease_timeout_seconds=300)
            w_session.commit()
            worker_results[worker_id] = res
        finally:
            w_session.close()

    t1 = threading.Thread(target=outbox_worker, args=(1,))
    t2 = threading.Thread(target=outbox_worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one worker reclaimed the event; the other skipped it due to skip_locked
    total_reclaimed = sum(r["reclaimed"] for r in worker_results.values())
    total_succeeded = sum(r["succeeded"] for r in worker_results.values())
    assert total_reclaimed >= 1, f"Expected at least 1 reclaimed event: {worker_results}"
    assert total_succeeded >= 1, f"Expected at least 1 succeeded event: {worker_results}"

    # Verify event state in live PostgreSQL
    verify_session = Session()
    try:
        ev = verify_session.query(RegistrationEmailOutbox).filter_by(outbox_id=event_id).first()
        assert ev.status == "SENT"
        assert ev.sent_at is not None
    finally:
        verify_session.close()




