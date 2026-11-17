"""
Unit and Integration Tests for PostgreSQL Registration Schema & SQLAlchemy Models
Hierarchical Government Registration, Verification & Approval System - Phase 1 Task 1A + 1B
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

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
)


@pytest.fixture
def db_session():
    """Create a pristine, in-memory SQLite database session for model testing."""
    engine = create_engine("sqlite:///:memory:")
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed base roles
    for r_id, desc in [
        ("HOSPITAL", "Hospital Staff"),
        ("DISTRICT_ADMIN", "District Administration"),
        ("STATE_ADMIN", "State Administration"),
        ("CENTRAL_ADMIN", "Central Administration"),
    ]:
        session.add(Role(id=r_id, description=desc))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_registration_application_creation_and_relationships(db_session):
    """Verify RegistrationApplication model creation and child relationships."""
    app_id = str(uuid.uuid4())
    app_num = "APP-20261103-0001"

    app = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="HOSPITAL",
        applicant_name="Apollo Hospital Amritsar",
        applicant_email="admin@apollo-amritsar.org",
        applicant_phone="+919876543210",
        state="Punjab",
        district="Amritsar",
        city="Amritsar",
        address="100 Mall Road",
        pincode="143001",
        official_designation="Medical Superintendent",
        nodal_officer_name="Dr. Harpreet Singh",
        parent_state="Punjab",
        parent_district="Amritsar",
        profile_data={"total_beds": 250, "icu_beds": 30, "specialties": ["cardiology", "neurology"]},
        current_stage="DISTRICT_REVIEW",
        status="UNDER_REVIEW",
        resubmission_version=1,
    )
    db_session.add(app)
    db_session.commit()

    fetched = db_session.query(RegistrationApplication).filter_by(application_id=app_id).first()
    assert fetched is not None
    assert fetched.application_number == app_num
    assert fetched.applicant_type == "HOSPITAL"
    assert fetched.profile_data["total_beds"] == 250
    assert fetched.current_stage == "DISTRICT_REVIEW"
    assert fetched.status == "UNDER_REVIEW"
    assert fetched.resubmission_version == 1
    assert fetched.created_at is not None
    assert fetched.submitted_at is not None  # UNDER_REVIEW is a submitted state


def test_draft_application_submitted_at_null_until_submission(db_session):
    """
    ISSUE 3 Test:
    Verify that:
    1. A newly created DRAFT application has created_at populated and submitted_at is None.
    2. Transitioning to SUBMITTED without explicitly assigning submitted_at automatically populates submitted_at.
    3. Subsequent updates while already SUBMITTED do not overwrite the original submitted_at.
    4. Resubmission after correction preserves the original submitted_at and records resubmitted_at.
    """
    app = RegistrationApplication(
        application_id="APP_DRAFT_SEMANTICS",
        application_number="APP-DRAFT-0001",
        applicant_type="HOSPITAL",
        applicant_name="Draft Hospital",
        applicant_email="draft@hospital.org",
        applicant_phone="0172-123456",
        state="Punjab",
    )
    db_session.add(app)
    db_session.commit()

    fetched = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert fetched.status == "DRAFT"
    assert fetched.current_stage == "DRAFT"
    assert fetched.created_at is not None
    assert fetched.submitted_at is None, "DRAFT application must NOT receive a submission timestamp"

    # Transition from DRAFT to SUBMITTED without explicitly assigning submitted_at:
    fetched.status = "SUBMITTED"
    fetched.current_stage = "SUBMITTED"
    db_session.commit()

    re_fetched = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert re_fetched.status == "SUBMITTED"
    assert re_fetched.submitted_at is not None, "submitted_at must be populated automatically on transition to SUBMITTED"
    orig_sub = re_fetched.submitted_at

    # Repeated update while already SUBMITTED (e.g. updating phone):
    re_fetched.applicant_phone = "0172-998877"
    db_session.commit()

    re_fetched2 = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert re_fetched2.submitted_at == orig_sub, "Original submitted_at must NOT be overwritten on repeated updates"

    # 3. Transition from SUBMITTED to CORRECTION_REQUIRED preserves submitted_at:
    re_fetched2.status = "CORRECTION_REQUIRED"
    re_fetched2.correction_notes = "Provide updated fire safety NOC"
    db_session.commit()

    re_fetched3 = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert re_fetched3.submitted_at == orig_sub, "Transition to CORRECTION_REQUIRED must preserve submitted_at"
    assert re_fetched3.resubmission_version == 1

    # 4. CORRECTION_REQUIRED -> SUBMITTED automatically sets resubmitted_at and increments resubmission_version exactly once
    # (Notice: neither resubmitted_at nor resubmission_version is manually assigned)
    re_fetched3.status = "SUBMITTED"
    re_fetched3.current_stage = "DISTRICT_REVIEW"
    db_session.commit()

    re_fetched4 = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert re_fetched4.submitted_at == orig_sub, "Original submitted_at must remain preserved after resubmission"
    assert re_fetched4.resubmitted_at is not None, "resubmitted_at must be populated automatically on resubmission"
    assert re_fetched4.resubmission_version == 2, "resubmission_version must automatically increment exactly once"

    # 5. Repeated updates while already SUBMITTED do not increment resubmission_version again:
    re_fetched4.applicant_name = "Draft Hospital Renamed"
    db_session.commit()

    re_fetched5 = db_session.query(RegistrationApplication).filter_by(application_id="APP_DRAFT_SEMANTICS").first()
    assert re_fetched5.resubmission_version == 2, "Repeated updates must not increment resubmission_version again"
    assert re_fetched5.submitted_at == orig_sub


def test_unique_application_number_constraint(db_session):
    """Verify that application_number must be unique."""
    app1 = RegistrationApplication(
        application_id="APP_001",
        application_number="APP-UNIQUE-001",
        applicant_type="STATE",
        applicant_name="Punjab Health Dept",
        applicant_email="sec@punjab.gov.in",
        applicant_phone="0172-123456",
        state="Punjab",
    )
    db_session.add(app1)
    db_session.commit()

    app2 = RegistrationApplication(
        application_id="APP_002",
        application_number="APP-UNIQUE-001",  # Duplicate number
        applicant_type="DISTRICT",
        applicant_name="Amritsar District Office",
        applicant_email="cmo@amritsar.gov.in",
        applicant_phone="0183-123456",
        state="Punjab",
        district="Amritsar",
    )
    db_session.add(app2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_document_metadata_and_verification_status(db_session):
    """Verify registration document storage metadata and relationship to application."""
    app = RegistrationApplication(
        application_id="APP_DOC_TEST",
        application_number="APP-20261103-DOCS",
        applicant_type="HOSPITAL",
        applicant_name="City General Hospital",
        applicant_email="superintendent@citygeneral.org",
        applicant_phone="0183-555123",
        state="Punjab",
        district="Amritsar",
    )
    db_session.add(app)
    db_session.commit()

    doc = RegistrationDocument(
        document_id="DOC_001",
        application_id=app.application_id,
        document_type="CLINICAL_LICENSE",
        storage_key="applications/APP_DOC_TEST/license.pdf",
        original_filename="clinical_registration_2026.pdf",
        mime_type="application/pdf",
        file_size_bytes=1048576,
        checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        verification_status="PENDING",
    )
    db_session.add(doc)
    db_session.commit()

    fetched_app = db_session.query(RegistrationApplication).filter_by(application_id="APP_DOC_TEST").first()
    assert len(fetched_app.documents) == 1
    assert fetched_app.documents[0].document_type == "CLINICAL_LICENSE"
    assert fetched_app.documents[0].checksum_sha256.startswith("e3b0c442")
    assert fetched_app.documents[0].verification_status == "PENDING"


def test_approval_history_append_only_flow(db_session):
    """Verify that approval history entries track state transitions chronologically."""
    app = RegistrationApplication(
        application_id="APP_HIST_TEST",
        application_number="APP-20261103-HIST",
        applicant_type="DISTRICT",
        applicant_name="Amritsar Health Office",
        applicant_email="cmo@amritsar.gov.in",
        applicant_phone="0183-111222",
        state="Punjab",
        district="Amritsar",
    )
    db_session.add(app)
    db_session.commit()

    # Step 1: Initial submission
    h1 = ApprovalHistory(
        application_id=app.application_id,
        reviewer_user_id=None,
        reviewer_role="APPLICANT",
        action="SUBMIT",
        review_tier="APPLICANT",
        previous_status="DRAFT",
        new_status="SUBMITTED",
        remarks="Application submitted with all mandatory documentation.",
        ip_address="192.168.1.50",
    )
    db_session.add(h1)
    db_session.commit()

    # Step 2: State Review Forwarding
    h2 = ApprovalHistory(
        application_id=app.application_id,
        reviewer_user_id="USR000003",
        reviewer_role="STATE_ADMIN",
        action="FORWARD",
        review_tier="STATE",
        previous_status="SUBMITTED",
        new_status="STATE_APPROVED",
        remarks="CMO appointment order verified against state gazette.",
        ip_address="10.0.0.1",
    )
    db_session.add(h2)
    db_session.commit()

    fetched_app = db_session.query(RegistrationApplication).filter_by(application_id="APP_HIST_TEST").first()
    assert len(fetched_app.history) == 2
    assert fetched_app.history[0].action == "SUBMIT"
    assert fetched_app.history[1].action == "FORWARD"
    assert fetched_app.history[1].review_tier == "STATE"
    assert fetched_app.history[1].new_status == "STATE_APPROVED"


def test_verification_token_expiration_and_attempt_limits(db_session):
    """Verify verification token structure, expiry checks, and attempt counting."""
    now = datetime.now(timezone.utc)
    token = VerificationToken(
        token_id="TOK_TEST_01",
        contact_target="applicant@hospital.org",
        token_channel="EMAIL",
        token_purpose="REGISTRATION_OTP",
        token_hash="pbkdf2:sha256:100000$test_salt$test_hash",
        attempt_count=0,
        max_attempts=3,
        is_verified=False,
        expires_at=now + timedelta(minutes=10),
        resend_available_at=now + timedelta(seconds=60),
    )
    db_session.add(token)
    db_session.commit()

    fetched = db_session.query(VerificationToken).filter_by(token_id="TOK_TEST_01").first()
    assert fetched is not None
    assert fetched.is_verified is False
    assert fetched.attempt_count == 0

    # Simulate failed attempts
    fetched.attempt_count += 1
    db_session.commit()
    assert fetched.attempt_count == 1
    assert fetched.attempt_count < fetched.max_attempts

    # Exceed attempts
    fetched.attempt_count = 3
    db_session.commit()
    assert fetched.attempt_count >= fetched.max_attempts


def test_account_activation_token_single_use(db_session):
    """Verify activation token single-use semantics."""
    user = User(
        user_id="USR_NEW_01",
        username="dr_sharma",
        password_hash="pbkdf2:sha256:100000$salt$hash",
        name="Dr. Sharma",
        role_id="HOSPITAL",
        is_active=False,  # Inactive until activation token is redeemed
    )
    db_session.add(user)
    db_session.commit()

    now = datetime.now(timezone.utc)
    act_token = AccountActivationToken(
        activation_token_id="ACT_TOK_01",
        user_id=user.user_id,
        token_hash="secure_hash_string",
        is_consumed=False,
        expires_at=now + timedelta(hours=24),
    )
    db_session.add(act_token)
    db_session.commit()

    # Redeem token
    fetched_token = db_session.query(AccountActivationToken).filter_by(activation_token_id="ACT_TOK_01").first()
    assert fetched_token.is_consumed is False
    fetched_token.is_consumed = True
    fetched_token.consumed_at = datetime.now(timezone.utc)

    # Activate user
    user.is_active = True
    db_session.commit()

    re_fetched_user = db_session.query(User).filter_by(user_id="USR_NEW_01").first()
    re_fetched_token = db_session.query(AccountActivationToken).filter_by(activation_token_id="ACT_TOK_01").first()

    assert re_fetched_user.is_active is True
    assert re_fetched_token.is_consumed is True
    assert re_fetched_token.consumed_at is not None


def test_hospital_grandfathering_logic_simulation(db_session):
    """
    Simulate the migration 003 grandfathering SQL logic:
    Verify existing seeded hospitals are updated to APPROVED and is_grandfathered=True,
    while subsequent new hospitals default to PENDING and is_grandfathered=False.
    """
    # 1. Seed 3 legacy hospitals (simulating existing GH00001 to GH00500)
    for i in range(1, 4):
        h = Hospital(
            hospital_id=f"GH0000{i}",
            name=f"Existing Hospital {i}",
            state="Punjab",
            district="Amritsar",
            latitude=31.63,
            longitude=74.87,
            total_beds=100,
            # Note: Before migration 003 runs, columns start with defaults
            approval_status="PENDING",
            is_grandfathered=False,
        )
        db_session.add(h)
    db_session.commit()

    initial_hospitals = db_session.query(Hospital).all()
    assert len(initial_hospitals) == 3
    assert all(h.approval_status == "PENDING" for h in initial_hospitals)
    assert all(h.is_grandfathered is False for h in initial_hospitals)

    # 2. Execute Grandfathering Update Statement (as in migration 003)
    now = datetime.now(timezone.utc)
    db_session.execute(
        update(Hospital)
        .where(Hospital.is_grandfathered == False)
        .values(
            approval_status="APPROVED",
            is_grandfathered=True,
            approved_at=now,
        )
    )
    db_session.commit()

    # 3. Verify all existing hospitals are now approved & grandfathered
    grandfathered = db_session.query(Hospital).all()
    assert len(grandfathered) == 3
    for h in grandfathered:
        assert h.approval_status == "APPROVED"
        assert h.is_grandfathered is True
        assert h.approved_at is not None

    # 4. Insert a NEW hospital post-migration (simulating an unapproved applicant)
    new_hospital = Hospital(
        hospital_id="GH00501",
        name="New Applicant Hospital",
        state="Punjab",
        district="Ludhiana",
        latitude=30.90,
        longitude=75.85,
        total_beds=50,
        # Default behavior:
        approval_status="PENDING",
        is_grandfathered=False,
    )
    db_session.add(new_hospital)
    db_session.commit()

    # 5. Verify the new hospital is NOT grandfathered and remains PENDING
    unapproved = db_session.query(Hospital).filter_by(hospital_id="GH00501").first()
    assert unapproved.approval_status == "PENDING"
    assert unapproved.is_grandfathered is False
    assert unapproved.approved_at is None


def test_registration_application_default_status_and_stage_draft(db_session):
    """
    ISSUE 1 Regression Test:
    Verify that an application inserted without explicitly specifying status or current_stage
    successfully defaults to 'DRAFT' and complies with the CHECK constraints.
    """
    app = RegistrationApplication(
        application_id="APP_DEFAULT_TEST",
        application_number="APP-20261103-DEFAULT",
        applicant_type="HOSPITAL",
        applicant_name="Civil Hospital Jalandhar",
        applicant_email="admin@civil-jalandhar.gov.in",
        applicant_phone="0181-222333",
        state="Punjab",
        district="Jalandhar",
        # Notice: status, current_stage, resubmission_version omitted to verify defaults
    )
    db_session.add(app)
    db_session.commit()

    fetched = db_session.query(RegistrationApplication).filter_by(application_id="APP_DEFAULT_TEST").first()
    assert fetched is not None
    assert fetched.status == "DRAFT"
    assert fetched.current_stage == "DRAFT"
    assert fetched.resubmission_version == 1


def test_registration_check_constraints_enforcement(db_session):
    """
    ISSUE 5 Regression Test:
    Verify that invalid enum values for applicant_type, current_stage, status, and invalid
    numeric bounds are rejected by database CHECK constraints.
    """
    # 1. Invalid applicant_type
    with pytest.raises(IntegrityError):
        invalid_app = RegistrationApplication(
            application_id="APP_INVALID_TYPE",
            application_number="APP-INV-TYPE",
            applicant_type="INVALID_TYPE",  # Not in ('STATE', 'DISTRICT', 'HOSPITAL')
            applicant_name="Invalid Entity",
            applicant_email="test@invalid.org",
            applicant_phone="12345",
            state="Punjab",
        )
        db_session.add(invalid_app)
        db_session.commit()
    db_session.rollback()

    # 2. Invalid status (e.g. legacy 'PENDING' which is not in allowed registration statuses)
    with pytest.raises(IntegrityError):
        invalid_status = RegistrationApplication(
            application_id="APP_INVALID_STATUS",
            application_number="APP-INV-STATUS",
            applicant_type="HOSPITAL",
            applicant_name="Invalid Entity",
            applicant_email="test@invalid.org",
            applicant_phone="12345",
            state="Punjab",
            status="PENDING",  # NOT in ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'REJECTED', 'SUSPENDED')
        )
        db_session.add(invalid_status)
        db_session.commit()
    db_session.rollback()

    # 3. Invalid resubmission_version (< 1)
    with pytest.raises(IntegrityError):
        invalid_version = RegistrationApplication(
            application_id="APP_INVALID_VER",
            application_number="APP-INV-VER",
            applicant_type="HOSPITAL",
            applicant_name="Invalid Entity",
            applicant_email="test@invalid.org",
            applicant_phone="12345",
            state="Punjab",
            resubmission_version=0,  # Must be >= 1
        )
        db_session.add(invalid_version)
        db_session.commit()
    db_session.rollback()


def test_approval_history_protection_and_restrict_delete(db_session):
    """
    ISSUE 3 Regression Test:
    Verify that an application with approval history CANNOT be deleted (ON DELETE RESTRICT),
    preventing audit log erasure.
    """
    app = RegistrationApplication(
        application_id="APP_RESTRICT_TEST",
        application_number="APP-20261103-RESTRICT",
        applicant_type="STATE",
        applicant_name="Haryana Health Mission",
        applicant_email="sec@haryana.gov.in",
        applicant_phone="0172-998877",
        state="Haryana",
    )
    db_session.add(app)
    db_session.commit()

    history_entry = ApprovalHistory(
        application_id=app.application_id,
        reviewer_user_id=None,
        reviewer_role="APPLICANT",
        action="SUBMIT",
        review_tier="APPLICANT",
        previous_status="DRAFT",
        new_status="SUBMITTED",
        remarks="Submitted for administrative verification",
    )
    db_session.add(history_entry)
    db_session.commit()

    # Attempt to delete the parent registration application
    # Because of ForeignKey(..., ondelete="RESTRICT"), this deletion must be blocked
    db_session.delete(app)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Verify both application and history record remain intact
    surviving_app = db_session.query(RegistrationApplication).filter_by(application_id="APP_RESTRICT_TEST").first()
    surviving_hist = db_session.query(ApprovalHistory).filter_by(application_id="APP_RESTRICT_TEST").first()
    assert surviving_app is not None
    assert surviving_hist is not None


def test_application_tracking_tokens_reusable_and_revocable(db_session):
    """
    ISSUE 4 Regression Test:
    Verify that application tracking tokens are reusable (access_count increments on status lookups),
    time-bound, and revocable (is_revoked with reason), rather than single-use.
    """
    app = RegistrationApplication(
        application_id="APP_TRACK_REUSE",
        application_number="APP-20261103-TRACK",
        applicant_type="HOSPITAL",
        applicant_name="Max Healthcare Mohali",
        applicant_email="admin@max-mohali.org",
        applicant_phone="0172-555666",
        state="Punjab",
    )
    db_session.add(app)
    db_session.commit()

    now = datetime.now(timezone.utc)
    token = ApplicationTrackingToken(
        tracking_token_id="TRACK_TOK_001",
        application_id=app.application_id,
        token_hash="sha256_tracking_token_hash",
        is_revoked=False,
        expires_at=now + timedelta(days=30),
        access_count=0,
    )
    db_session.add(token)
    db_session.commit()

    # Simulate 3 status queries by the applicant over time (Reusable access)
    for _ in range(3):
        fetched = db_session.query(ApplicationTrackingToken).filter_by(tracking_token_id="TRACK_TOK_001").first()
        assert fetched.is_revoked is False
        exp = fetched.expires_at if fetched.expires_at.tzinfo else fetched.expires_at.replace(tzinfo=timezone.utc)
        assert exp > datetime.now(timezone.utc)
        fetched.access_count += 1
        fetched.last_accessed_at = datetime.now(timezone.utc)
        db_session.commit()

    fetched = db_session.query(ApplicationTrackingToken).filter_by(tracking_token_id="TRACK_TOK_001").first()
    assert fetched.access_count == 3
    assert fetched.last_accessed_at is not None
    assert fetched.is_revoked is False

    # Simulate administrative or security revocation
    fetched.is_revoked = True
    fetched.revoked_at = datetime.now(timezone.utc)
    fetched.revocation_reason = "Nodal officer phone number updated"
    db_session.commit()

    revoked_token = db_session.query(ApplicationTrackingToken).filter_by(tracking_token_id="TRACK_TOK_001").first()
    assert revoked_token.is_revoked is True
    assert revoked_token.revoked_at is not None
    assert revoked_token.revocation_reason == "Nodal officer phone number updated"


def test_submitted_at_preserved_against_manual_overwrite(db_session):
    """
    REGRESSION TEST:
    Verify that SQLAlchemy ORM listener strictly preserves original persisted submitted_at
    against manual application-level overwrite attempts across the entire application lifecycle:
    1. Create DRAFT application and submit it.
    2. Save original submitted_at.
    3. Manually attempt to overwrite submitted_at through ORM.
    4. Commit and assert original timestamp remains unchanged.
    5. Request correction and assert timestamp remains unchanged.
    6. Resubmit and assert timestamp remains unchanged, resubmitted_at populated, resubmission_version increments from 1 to 2.
    7. Perform ordinary update and assert resubmission_version does not increment again.
    """
    # 1. Create DRAFT application and submit it
    app = RegistrationApplication(
        application_id="APP_OVERWRITE_REGRESSION",
        application_number="APP-20261103-OVERWRITE",
        applicant_type="HOSPITAL",
        applicant_name="Apex Super Specialty Hospital",
        applicant_email="director@apex-hospital.org",
        applicant_phone="0172-223344",
        state="Punjab",
        status="DRAFT",
        current_stage="DRAFT",
    )
    db_session.add(app)
    db_session.commit()
    assert app.submitted_at is None

    # Transition to SUBMITTED
    app.status = "SUBMITTED"
    app.current_stage = "SUBMITTED"
    db_session.commit()

    # 2. Save original submitted_at
    fetched = db_session.query(RegistrationApplication).filter_by(application_id="APP_OVERWRITE_REGRESSION").first()
    assert fetched.submitted_at is not None
    orig_sub = fetched.submitted_at

    # 3. Manually attempt to overwrite submitted_at through ORM
    bogus_timestamp = datetime(2099, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    fetched.submitted_at = bogus_timestamp

    # 4. Commit and assert original timestamp remains unchanged
    db_session.commit()

    fetched_after_overwrite = db_session.query(RegistrationApplication).filter_by(application_id="APP_OVERWRITE_REGRESSION").first()
    assert fetched_after_overwrite.submitted_at == orig_sub, (
        f"Original submitted_at was overwritten! Expected {orig_sub}, got {fetched_after_overwrite.submitted_at}"
    )

    # 5. Request correction and assert timestamp remains unchanged
    fetched_after_overwrite.status = "CORRECTION_REQUIRED"
    fetched_after_overwrite.correction_notes = "Please submit updated clinical establishment license"
    db_session.commit()

    fetched_correction = db_session.query(RegistrationApplication).filter_by(application_id="APP_OVERWRITE_REGRESSION").first()
    assert fetched_correction.submitted_at == orig_sub
    assert fetched_correction.resubmission_version == 1

    # 6. Resubmit and assert timestamp remains unchanged, resubmitted_at populated, resubmission_version increments from 1 to 2
    fetched_correction.status = "SUBMITTED"
    fetched_correction.current_stage = "DISTRICT_REVIEW"
    db_session.commit()

    fetched_resubmit = db_session.query(RegistrationApplication).filter_by(application_id="APP_OVERWRITE_REGRESSION").first()
    assert fetched_resubmit.submitted_at == orig_sub, "Original submitted_at must remain preserved after resubmission"
    assert fetched_resubmit.resubmitted_at is not None, "resubmitted_at must be populated on resubmission"
    assert fetched_resubmit.resubmission_version == 2, "resubmission_version must increment from 1 to 2"

    # 7. Perform ordinary update and assert resubmission_version does not increment again
    fetched_resubmit.applicant_phone = "0172-998811"
    db_session.commit()

    fetched_final = db_session.query(RegistrationApplication).filter_by(application_id="APP_OVERWRITE_REGRESSION").first()
    assert fetched_final.resubmission_version == 2, "Ordinary update must not increment resubmission_version again"
    assert fetched_final.submitted_at == orig_sub, "submitted_at must remain strictly preserved"
