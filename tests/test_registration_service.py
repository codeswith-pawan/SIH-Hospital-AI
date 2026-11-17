"""
Unit and Integration Tests for Registration Business Logic and Service Layer
Phase 1 Task 1C Implementation Verification
"""

import pytest
import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.pg_models import (
    PgBase,
    Role,
    Hospital,
    User,
    RegistrationApplication,
    RegistrationDocument,
    ApprovalHistory,
    ApplicationTrackingToken,
)
from src.services.registration_service import RegistrationService, CANONICAL_DIVISIONS
from src.services.registration_exceptions import (
    RegistrationServiceError,
    ValidationError,
    InvalidHierarchyError,
    DuplicateApplicationError,
    ApplicationNotFoundError,
    DocumentError,
    UnauthorizedReviewerError,
    GeographicAccessError,
    SelfApprovalError,
    InvalidStageTransitionError,
    IneligibleForApprovalError,
    TrackingTokenError,
)


@pytest.fixture
def db_session():
    """In-memory SQLite session configured with full relational tables."""
    engine = create_engine("sqlite:///:memory:")
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed base roles
    for role_id, desc in [
        ("HOSPITAL", "Hospital Staff"),
        ("DISTRICT_ADMIN", "District Administrator"),
        ("STATE_ADMIN", "State Administrator"),
        ("CENTRAL_ADMIN", "Central Government Administrator"),
    ]:
        session.add(Role(id=role_id, description=desc))
    session.commit()

    yield session
    session.rollback()
    session.close()
    engine.dispose()


@pytest.fixture
def reg_service(db_session):
    """Fixture providing initialized RegistrationService."""
    return RegistrationService(db_session)


# ============================================================
# 1. PARENT-CHILD HIERARCHY TESTS
# ============================================================

def test_valid_parent_child_hierarchy(reg_service):
    """Test valid State, District, and Hospital administrative hierarchy combinations."""
    # State
    reg_service.validate_parent_child_hierarchy("STATE", "Punjab")
    reg_service.validate_parent_child_hierarchy("STATE", "Maharashtra")

    # District
    reg_service.validate_parent_child_hierarchy("DISTRICT", "Punjab", "Amritsar")
    reg_service.validate_parent_child_hierarchy("DISTRICT", "Maharashtra", "Mumbai")

    # Hospital
    reg_service.validate_parent_child_hierarchy("HOSPITAL", "Punjab", "Ludhiana")
    reg_service.validate_parent_child_hierarchy("HOSPITAL", "Delhi", "South Delhi")


def test_invalid_hierarchy_unrecognized_state(reg_service):
    """Unrecognized or empty states must be rejected."""
    with pytest.raises(InvalidHierarchyError, match="not a recognized or registered state"):
        reg_service.validate_parent_child_hierarchy("STATE", "Atlantis")

    with pytest.raises(InvalidHierarchyError, match="State is mandatory"):
        reg_service.validate_parent_child_hierarchy("STATE", "")


def test_invalid_hierarchy_district_state_mismatch(reg_service):
    """District must belong to the correct State."""
    # Mumbai belongs to Maharashtra, not Punjab
    with pytest.raises(InvalidHierarchyError, match="District 'Mumbai' belongs to State 'Maharashtra', not 'Punjab'"):
        reg_service.validate_parent_child_hierarchy("HOSPITAL", "Punjab", "Mumbai")

    with pytest.raises(InvalidHierarchyError, match="District is mandatory"):
        reg_service.validate_parent_child_hierarchy("HOSPITAL", "Punjab", None)


# ============================================================
# 2. APPLICATION CREATION & DETAIL VALIDATION
# ============================================================

def test_create_hospital_application_success(reg_service, db_session):
    """Verify successful creation of a Hospital application in DRAFT status."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Fortis Hospital Mohali",
        "applicant_email": "admin@fortis-mohali.org",
        "applicant_phone": "0172-5551234",
        "state": "Punjab",
        "district": "Mohali",
        "city": "Mohali",
        "address": "Sector 62, Phase 8",
        "pincode": "160062",
        "official_designation": "Medical Superintendent",
        "nodal_officer_name": "Dr. Gurpreet Singh",
        "profile_data": {"total_beds": 250, "icu_beds": 30},
    }

    app = reg_service.create_application(data)
    db_session.commit()

    assert app.application_id.startswith("APP_")
    assert app.application_number.startswith("APP-")
    assert "HOSP" in app.application_number
    assert app.status == "DRAFT"
    assert app.current_stage == "DRAFT"
    assert app.submitted_at is None
    assert app.resubmission_version == 1
    assert app.applicant_name == "Fortis Hospital Mohali"


def test_create_application_invalid_email_or_phone(reg_service):
    """Verify validation of email and phone formats."""
    bad_email_data = {
        "applicant_type": "STATE",
        "applicant_name": "Punjab Health Secretariat",
        "applicant_email": "not-an-email",
        "applicant_phone": "0172-1234567",
        "state": "Punjab",
    }
    with pytest.raises(ValidationError, match="Invalid applicant_email"):
        reg_service.create_application(bad_email_data)

    bad_phone_data = {
        "applicant_type": "STATE",
        "applicant_name": "Punjab Health Secretariat",
        "applicant_email": "sec@punjab.gov.in",
        "applicant_phone": "123",  # Too short
        "state": "Punjab",
    }
    with pytest.raises(ValidationError, match="applicant_phone must contain at least 10 digits"):
        reg_service.create_application(bad_phone_data)


# ============================================================
# 3. DUPLICATE ACTIVE APPLICATION PREVENTION
# ============================================================

def test_prevent_duplicate_active_application_for_state(reg_service, db_session):
    """Cannot have two active applications for the same State."""
    data = {
        "applicant_type": "STATE",
        "applicant_name": "Punjab Directorate of Health",
        "applicant_email": "director@punjabhealth.gov.in",
        "applicant_phone": "0172-2233445",
        "state": "Punjab",
    }
    reg_service.create_application(data)
    db_session.commit()

    # Attempting to create second application for Punjab while first is active
    with pytest.raises(DuplicateApplicationError, match="already exists for State 'Punjab'"):
        reg_service.create_application(data)


def test_prevent_duplicate_active_application_for_district(reg_service, db_session):
    """Cannot have two active applications for the same District in a State."""
    data = {
        "applicant_type": "DISTRICT",
        "applicant_name": "Amritsar District Health Society",
        "applicant_email": "cmo@amritsarhealth.gov.in",
        "applicant_phone": "0183-2211445",
        "state": "Punjab",
        "district": "Amritsar",
    }
    reg_service.create_application(data)
    db_session.commit()

    with pytest.raises(DuplicateApplicationError, match="already exists for District 'Amritsar' in State 'Punjab'"):
        reg_service.create_application(data)


def test_duplicate_allowed_after_rejection(reg_service, db_session):
    """After an application is REJECTED, a new application for that entity can be submitted."""
    data = {
        "applicant_type": "DISTRICT",
        "applicant_name": "Jalandhar Health Office",
        "applicant_email": "cmo@jalandhar.gov.in",
        "applicant_phone": "0181-2233445",
        "state": "Punjab",
        "district": "Jalandhar",
    }
    app1 = reg_service.create_application(data)
    app1.status = "REJECTED"
    app1.current_stage = "REJECTED"
    db_session.commit()

    # Now creating a new application should succeed
    app2 = reg_service.create_application(data)
    db_session.commit()
    assert app2.application_id != app1.application_id
    assert app2.status == "DRAFT"


def test_prevent_duplicate_active_application_for_hospital_by_email(reg_service, db_session):
    """Cannot have two active hospital applications with the same canonical institutional email."""
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex Heart Institute",
        "applicant_email": "admin@apexheart.in",
        "applicant_phone": "0172-2244556",
        "state": "Punjab",
        "district": "Mohali",
    }
    reg_service.create_application(data1)
    db_session.commit()

    # Attempt second hospital with same email but different hospital name
    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex Cardiac Care",
        "applicant_email": "admin@apexheart.in",
        "applicant_phone": "0172-9988776",
        "state": "Punjab",
        "district": "Mohali",
    }
    with pytest.raises(DuplicateApplicationError, match="already exists for email 'admin@apexheart.in'"):
        reg_service.create_application(data2)


def test_case_and_whitespace_insensitive_duplicate_prevention(reg_service, db_session):
    """Duplicate prevention normalizes whitespace and casing."""
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Metro Hospital",
        "applicant_email": "contact@metrohealth.org",
        "applicant_phone": "0161-2244668",
        "state": "Punjab",
        "district": "Ludhiana",
    }
    reg_service.create_application(data1)
    db_session.commit()

    # Attempt second application with varied case and padding whitespace
    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Metro Hospital Branch 2",
        "applicant_email": "  Contact@MetroHealth.ORG  ",
        "applicant_phone": "0161-9988112",
        "state": "Punjab",
        "district": "Ludhiana",
    }
    with pytest.raises(DuplicateApplicationError, match="already exists for email 'contact@metrohealth.org'"):
        reg_service.create_application(data2)


def test_different_hospitals_same_name_different_email_allowed(reg_service, db_session):
    """
    Two different hospitals may share a generic or common name (e.g. 'Civil Hospital')
    as long as their institutional emails differ.
    """
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Civil Hospital",
        "applicant_email": "admin.mohali@civilhospital.org",
        "applicant_phone": "0172-1111222",
        "state": "Punjab",
        "district": "Mohali",
    }
    app1 = reg_service.create_application(data1)
    db_session.commit()

    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Civil Hospital",
        "applicant_email": "admin.amritsar@civilhospital.org",
        "applicant_phone": "0183-3333444",
        "state": "Punjab",
        "district": "Amritsar",
    }
    app2 = reg_service.create_application(data2)
    db_session.commit()

    assert app1.application_id != app2.application_id
    assert app1.applicant_name == app2.applicant_name == "Civil Hospital"
    assert app1.status == app2.status == "DRAFT"


def test_rejected_hospital_allows_new_application(reg_service, db_session):
    """A rejected hospital application does not prevent submitting a new application with the same email."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Sunrise Multi-Speciality",
        "applicant_email": "info@sunrisemulti.org",
        "applicant_phone": "0175-5551122",
        "state": "Punjab",
        "district": "Patiala",
    }
    app1 = reg_service.create_application(data)
    app1.status = "REJECTED"
    app1.current_stage = "REJECTED"
    db_session.commit()

    # New application with exact same email succeeds
    app2 = reg_service.create_application(data)
    db_session.commit()
    assert app2.application_id != app1.application_id
    assert app2.status == "DRAFT"


def test_transaction_remains_usable_after_duplicate_application_error(reg_service, db_session):
    """
    When duplicate creation fails and rolls back, the session must remain healthy
    and usable for subsequent operations.
    """
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Heritage Hospital",
        "applicant_email": "ops@heritage.org",
        "applicant_phone": "0181-4455667",
        "state": "Punjab",
        "district": "Jalandhar",
    }
    app1 = reg_service.create_application(data1)
    db_session.commit()

    # Trigger duplicate error
    with pytest.raises(DuplicateApplicationError):
        reg_service.create_application(data1)

    # Session must be capable of executing queries and creating other applications without error
    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Unique Care Clinic",
        "applicant_email": "ops@uniquecare.org",
        "applicant_phone": "0181-9998877",
        "state": "Punjab",
        "district": "Jalandhar",
    }
    app2 = reg_service.create_application(data2)
    db_session.commit()
    assert app2.application_id != app1.application_id
    assert app2.status == "DRAFT"


def test_same_hospital_with_changed_applicant_email_behavior(reg_service, db_session):
    """
    Demonstrate and verify the documented limitation of the applicant_email identity policy:
    Because applicant_email is the canonical uniqueness key for hospital applications,
    submitting a second application for the same physical hospital with a DIFFERENT applicant email
    is permitted by the system.
    """
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex City Hospital",
        "applicant_email": "admin@apexcity.org",
        "applicant_phone": "0172-5551100",
        "state": "Punjab",
        "district": "Mohali",
        "address": "Plot 10, Sector 70",
    }
    app1 = reg_service.create_application(data1)
    db_session.commit()

    # Same hospital name and location, but different applicant email (e.g. Medical Superintendent)
    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex City Hospital",
        "applicant_email": "superintendent@apexcity.org",
        "applicant_phone": "0172-5552200",
        "state": "Punjab",
        "district": "Mohali",
        "address": "Plot 10, Sector 70",
    }
    app2 = reg_service.create_application(data2)
    db_session.commit()

    assert app1.application_id != app2.application_id
    assert app1.applicant_name == app2.applicant_name
    assert app1.applicant_email != app2.applicant_email


def test_two_different_hospitals_sharing_applicant_email_blocked(reg_service, db_session):
    """
    Demonstrate that an administrator cannot use the same institutional email
    to register two distinct hospitals simultaneously.
    """
    data1 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Max Healthcare Phase 1",
        "applicant_email": "group.admin@maxchain.in",
        "applicant_phone": "0172-6661100",
        "state": "Punjab",
        "district": "Mohali",
    }
    reg_service.create_application(data1)
    db_session.commit()

    # Distinct facility, but same applicant email
    data2 = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Max Healthcare Phase 6",
        "applicant_email": "group.admin@maxchain.in",
        "applicant_phone": "0172-6662200",
        "state": "Punjab",
        "district": "Mohali",
    }
    with pytest.raises(DuplicateApplicationError, match="already exists for email 'group.admin@maxchain.in'"):
        reg_service.create_application(data2)


def test_unexpected_integrity_violation_not_misreported_as_duplicate(reg_service, db_session):
    """
    Verify that non-duplicate IntegrityErrors (e.g. CheckConstraint, NotNull, or FK violations)
    are NOT misreported as DuplicateApplicationError, that the transaction is rolled back,
    and that the original database exception is preserved and raised.
    """
    from sqlalchemy.exc import IntegrityError
    from unittest.mock import patch

    valid_data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Valid Test Hospital",
        "applicant_email": "valid.test@hospital.org",
        "applicant_phone": "0172-7778899",
        "state": "Punjab",
        "district": "Mohali",
    }

    # Simulate an unexpected foreign key or not-null integrity violation on session.flush
    class MockOrigException(Exception):
        pgcode = "23503"  # foreign_key_violation
        diag = None

    mock_fk_error = IntegrityError("INSERT INTO ...", params={}, orig=MockOrigException("foreign key violation"))

    with patch.object(reg_service.session, "flush", side_effect=mock_fk_error):
        with pytest.raises(IntegrityError) as exc_info:
            reg_service.create_application(valid_data)

        # Must NOT be DuplicateApplicationError
        assert not isinstance(exc_info.value, DuplicateApplicationError)
        assert exc_info.value is mock_fk_error

    # Session must be functional after the rollback executed in create_application
    app = reg_service.create_application(valid_data)
    db_session.commit()
    assert app.application_id.startswith("APP_")


# ============================================================
# 4. REFERENCE GENERATION UNIQUENESS
# ============================================================

def test_reference_generation_uniqueness(reg_service):
    """Reference numbers must be non-guessable, unique, and collision-free."""
    generated = set()
    for _ in range(50):
        ref = reg_service.generate_application_number("HOSPITAL")
        assert ref.startswith("APP-")
        assert "-HOSP-" in ref
        assert ref not in generated
        generated.add(ref)

    assert len(generated) == 50


# ============================================================
# 5. DRAFT SUBMISSION & MANDATORY DOCUMENTS
# ============================================================

def test_draft_submission_requires_mandatory_documents(reg_service, db_session):
    """Submission must enforce presence of mandatory documents before progressing."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apollo Clinic Ludhiana",
        "applicant_email": "admin@apollo-ldh.org",
        "applicant_phone": "0161-5558899",
        "state": "Punjab",
        "district": "Ludhiana",
    }
    app = reg_service.create_application(data)
    db_session.commit()

    # Attempt submit without any documents
    with pytest.raises(DocumentError, match="Missing mandatory hospital documents"):
        reg_service.submit_application(app.application_id)

    # Add only Clinical License (still missing Fire Safety NOC)
    reg_service.add_document_metadata(
        application_id=app.application_id,
        document_type="CLINICAL_LICENSE",
        original_filename="license.pdf",
        mime_type="application/pdf",
        file_size_bytes=102400,
        storage_key="docs/license.pdf",
        checksum_sha256="a" * 64,
    )
    db_session.commit()

    with pytest.raises(DocumentError, match="Missing mandatory hospital documents: FIRE_SAFETY_NOC"):
        reg_service.submit_application(app.application_id)

    # Add Fire Safety NOC
    reg_service.add_document_metadata(
        application_id=app.application_id,
        document_type="FIRE_SAFETY_NOC",
        original_filename="fire_noc.pdf",
        mime_type="application/pdf",
        file_size_bytes=204800,
        storage_key="docs/fire_noc.pdf",
        checksum_sha256="b" * 64,
    )
    db_session.commit()

    # Submission now succeeds
    result = reg_service.submit_application(app.application_id, client_ip="192.168.1.100")
    db_session.commit()

    assert result["status"] == "SUBMITTED"
    assert result["current_stage"] == "DISTRICT_REVIEW"
    assert result["submitted_at"] is not None
    assert "tracking_token" in result

    # Check ApprovalHistory was inserted
    history = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).all()
    assert len(history) == 1
    assert history[0].action == "SUBMIT"
    assert history[0].review_tier == "APPLICANT"
    assert history[0].previous_status == "DRAFT"
    assert history[0].new_status == "SUBMITTED"
    assert history[0].ip_address == "192.168.1.100"


# ============================================================
# 6. DOCUMENT VERIFICATION & METADATA STORAGE
# ============================================================

def test_document_metadata_storage_and_verification(reg_service, db_session):
    """Verify document metadata checks and authorized reviewer verification."""
    data = {
        "applicant_type": "DISTRICT",
        "applicant_name": "Patiala District Health",
        "applicant_email": "cmo@patiala.gov.in",
        "applicant_phone": "0175-2233445",
        "state": "Punjab",
        "district": "Patiala",
    }
    app = reg_service.create_application(data)
    doc = reg_service.add_document_metadata(
        application_id=app.application_id,
        document_type="GOVERNMENT_ORDER",
        original_filename="govt_order_patiala.pdf",
        mime_type="application/pdf",
        file_size_bytes=512000,
        storage_key="docs/govt_order_patiala.pdf",
        checksum_sha256="c" * 64,
    )
    db_session.commit()

    assert doc.verification_status == "PENDING"

    # Submit district application -> enters STATE_REVIEW stage
    reg_service.submit_application(app.application_id)
    db_session.commit()

    # Verify document by authorized STATE_ADMIN
    state_reviewer = {"user_id": "U_STATE_01", "role": "STATE_ADMIN", "state": "Punjab"}
    verified_doc = reg_service.verify_document(
        document_id=doc.document_id,
        reviewer_user=state_reviewer,
        verification_status="VERIFIED",
        reviewer_remarks="Government order verified with secretariat records.",
    )
    db_session.commit()

    assert verified_doc.verification_status == "VERIFIED"
    assert verified_doc.reviewer_id == "U_STATE_01"
    assert verified_doc.reviewed_at is not None


# ============================================================
# 7. CORRECTION & RESUBMISSION LIFECYCLE
# ============================================================

def test_correction_request_and_applicant_resubmission(reg_service, db_session):
    """
    Verify complete correction and resubmission lifecycle:
    - Reviewer requests correction.
    - Application status becomes CORRECTION_REQUIRED.
    - ApprovalHistory records REQUEST_CORRECTION.
    - Applicant resubmits.
    - submitted_at is strictly preserved.
    - resubmission_version increments from 1 to 2.
    - ApprovalHistory records RESUBMIT.
    """
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Ivy Hospital Mohali",
        "applicant_email": "ivy@mohali.org",
        "applicant_phone": "0172-7778899",
        "state": "Punjab",
        "district": "Mohali",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "lic.pdf", "application/pdf", 100, "k1", "d" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "fire.pdf", "application/pdf", 100, "k2", "e" * 64)
    db_session.commit()

    reg_service.submit_application(app.application_id)
    db_session.commit()

    orig_sub = app.submitted_at
    assert orig_sub is not None
    assert app.resubmission_version == 1

    # District reviewer requests correction
    district_reviewer = {"user_id": "U_DIST_01", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}
    corr_res = reg_service.request_correction(
        application_id=app.application_id,
        reviewer_user=district_reviewer,
        correction_notes="Please upload higher-resolution Fire NOC.",
        client_ip="10.0.0.1",
    )
    db_session.commit()

    assert corr_res["status"] == "CORRECTION_REQUIRED"
    assert app.status == "CORRECTION_REQUIRED"
    assert app.correction_notes == "Please upload higher-resolution Fire NOC."
    assert app.submitted_at == orig_sub

    # Verify history entry
    hist = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).order_by(ApprovalHistory.id).all()
    assert len(hist) == 2
    assert hist[1].action == "REQUEST_CORRECTION"
    assert hist[1].review_tier == "DISTRICT"
    assert hist[1].remarks == "Please upload higher-resolution Fire NOC."

    # Applicant resubmits
    resub_res = reg_service.resubmit_application(
        application_id=app.application_id,
        applicant_notes="Uploaded corrected Fire NOC with 600 DPI scan.",
        client_ip="192.168.1.50",
    )
    db_session.commit()

    assert resub_res["status"] == "SUBMITTED"
    assert app.status == "SUBMITTED"
    assert app.submitted_at == orig_sub, "Original submitted_at must remain strictly preserved"
    assert app.resubmitted_at is not None
    assert app.resubmission_version == 2, "resubmission_version must increment to 2"

    # Verify history entry for RESUBMIT
    hist = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).order_by(ApprovalHistory.id).all()
    assert len(hist) == 3
    assert hist[2].action == "RESUBMIT"
    assert hist[2].review_tier == "APPLICANT"
    assert hist[2].previous_status == "CORRECTION_REQUIRED"
    assert hist[2].new_status == "SUBMITTED"


# ============================================================
# 8. MULTI-TIER APPROVAL FLOW (HOSPITAL, DISTRICT, STATE)
# ============================================================

def test_hospital_full_approval_chain(reg_service, db_session):
    """
    Hospital 3-tier approval chain:
    1. District Admin approves -> advances to STATE_REVIEW.
    2. State Admin approves -> advances to CENTRAL_REVIEW.
    3. Central Admin approves -> final status APPROVED.
    """
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Civil Hospital Amritsar",
        "applicant_email": "civil@amritsar.org",
        "applicant_phone": "0183-5551122",
        "state": "Punjab",
        "district": "Amritsar",
        "nodal_officer_name": "Dr. R. Sharma",
    }
    app = reg_service.create_application(data)
    d1 = reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "lic.pdf", "application/pdf", 100, "k1", "1" * 64)
    d2 = reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "fire.pdf", "application/pdf", 100, "k2", "2" * 64)
    db_session.commit()

    reg_service.submit_application(app.application_id)
    db_session.commit()
    assert app.current_stage == "DISTRICT_REVIEW"

    # Step 1: District Reviewer verifies documents and approves/forwards
    dist_user = {"user_id": "U_AMRITSAR_DIST", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Amritsar"}
    reg_service.verify_document(d1.document_id, dist_user, "VERIFIED")
    reg_service.verify_document(d2.document_id, dist_user, "VERIFIED")
    db_session.commit()

    step1 = reg_service.review_application(app.application_id, dist_user, action="FORWARD", remarks="District inspection verified.")
    db_session.commit()
    assert step1["current_stage"] == "STATE_REVIEW"
    assert step1["status"] == "UNDER_REVIEW"

    # Step 2: State Reviewer approves/forwards
    state_user = {"user_id": "U_PUNJAB_STATE", "role": "STATE_ADMIN", "state": "Punjab"}
    step2 = reg_service.review_application(app.application_id, state_user, action="FORWARD", remarks="State bed quota allocated.")
    db_session.commit()
    assert step2["current_stage"] == "CENTRAL_REVIEW"
    assert step2["status"] == "UNDER_REVIEW"

    # Step 3: Central Admin final approval
    central_user = {"user_id": "U_MOHFW_CENTRAL", "role": "CENTRAL_ADMIN"}
    step3 = reg_service.review_application(app.application_id, central_user, action="APPROVE", remarks="National accreditation granted.")
    db_session.commit()
    assert step3["current_stage"] == "APPROVED"
    assert step3["status"] == "APPROVED"
    assert app.final_approved_at is not None

    # Check total history entries
    history = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).order_by(ApprovalHistory.id).all()
    assert len(history) == 4
    assert [h.action for h in history] == ["SUBMIT", "FORWARD", "FORWARD", "APPROVE"]
    assert [h.review_tier for h in history] == ["APPLICANT", "DISTRICT", "STATE", "CENTRAL"]


def test_district_two_tier_approval_chain(reg_service, db_session):
    """
    District 2-tier approval chain:
    1. State Admin approves -> advances to CENTRAL_REVIEW.
    2. Central Admin approves -> final status APPROVED.
    """
    data = {
        "applicant_type": "DISTRICT",
        "applicant_name": "Ludhiana District Health Society",
        "applicant_email": "cmo@ludhiana.gov.in",
        "applicant_phone": "0161-2233445",
        "state": "Punjab",
        "district": "Ludhiana",
        "nodal_officer_name": "Dr. K. Singh",
    }
    app = reg_service.create_application(data)
    d = reg_service.add_document_metadata(app.application_id, "GOVERNMENT_ORDER", "order.pdf", "application/pdf", 100, "k1", "3" * 64)
    db_session.commit()

    reg_service.submit_application(app.application_id)
    db_session.commit()
    assert app.current_stage == "STATE_REVIEW"

    state_user = {"user_id": "U_PUNJAB_STATE", "role": "STATE_ADMIN", "state": "Punjab"}
    reg_service.verify_document(d.document_id, state_user, "VERIFIED")
    db_session.commit()

    reg_service.review_application(app.application_id, state_user, action="FORWARD")
    db_session.commit()
    assert app.current_stage == "CENTRAL_REVIEW"

    central_user = {"user_id": "U_CENTRAL_01", "role": "CENTRAL_ADMIN"}
    reg_service.review_application(app.application_id, central_user, action="APPROVE")
    db_session.commit()
    assert app.status == "APPROVED"


def test_state_single_tier_approval_chain(reg_service, db_session):
    """
    State 1-tier approval chain:
    1. Central Admin reviews and approves directly.
    """
    data = {
        "applicant_type": "STATE",
        "applicant_name": "Haryana Health Mission",
        "applicant_email": "dir@haryanahealth.gov.in",
        "applicant_phone": "0172-9988776",
        "state": "Haryana",
        "nodal_officer_name": "Sh. R. Verma",
    }
    app = reg_service.create_application(data)
    d = reg_service.add_document_metadata(app.application_id, "GOVERNMENT_ORDER", "secretariat.pdf", "application/pdf", 100, "k1", "4" * 64)
    db_session.commit()

    reg_service.submit_application(app.application_id)
    db_session.commit()
    assert app.current_stage == "CENTRAL_REVIEW"

    central_user = {"user_id": "U_CENTRAL_01", "role": "CENTRAL_ADMIN"}
    reg_service.verify_document(d.document_id, central_user, "VERIFIED")
    db_session.commit()

    reg_service.review_application(app.application_id, central_user, action="APPROVE")
    db_session.commit()
    assert app.status == "APPROVED"


# ============================================================
# 9. SECURITY & AUTHORIZATION CONSTRAINTS
# ============================================================

def test_unauthorized_stage_review_rejected(reg_service, db_session):
    """Reviewers cannot act on stages outside their role authority."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Global Hospital Bathinda",
        "applicant_email": "info@global-bathinda.org",
        "applicant_phone": "0164-5551234",
        "state": "Punjab",
        "district": "Bathinda",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "l.pdf", "application/pdf", 100, "k1", "5" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "f.pdf", "application/pdf", 100, "k2", "6" * 64)
    db_session.commit()

    reg_service.submit_application(app.application_id)
    db_session.commit()
    assert app.current_stage == "DISTRICT_REVIEW"

    # State Admin cannot act at DISTRICT_REVIEW stage
    state_user = {"user_id": "U_STATE_01", "role": "STATE_ADMIN", "state": "Punjab"}
    with pytest.raises(UnauthorizedReviewerError, match="Only DISTRICT_ADMIN can review at DISTRICT_REVIEW stage"):
        reg_service.review_application(app.application_id, state_user, action="FORWARD")

    # Hospital staff can NEVER review
    hospital_staff = {"user_id": "U_HOSP_01", "role": "HOSPITAL", "hospital_id": "GH00001"}
    with pytest.raises(UnauthorizedReviewerError, match="Hospital staff role is not permitted to review"):
        reg_service.review_application(app.application_id, hospital_staff, action="FORWARD")


def test_geographic_access_boundary_enforced(reg_service, db_session):
    """District and State Admins cannot review applications outside their jurisdiction."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex Hospital Amritsar",
        "applicant_email": "apex@amritsar.org",
        "applicant_phone": "0183-5558888",
        "state": "Punjab",
        "district": "Amritsar",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "l.pdf", "application/pdf", 100, "k1", "7" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "f.pdf", "application/pdf", 100, "k2", "8" * 64)
    db_session.commit()
    reg_service.submit_application(app.application_id)
    db_session.commit()

    # District Admin of Ludhiana attempts to review Amritsar hospital
    ludhiana_admin = {"user_id": "U_LDH_ADMIN", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Ludhiana"}
    with pytest.raises(GeographicAccessError, match="cannot review application in"):
        reg_service.review_application(app.application_id, ludhiana_admin, action="FORWARD")

    # Advance to State Review
    amritsar_admin = {"user_id": "U_ASR_ADMIN", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Amritsar"}
    reg_service.review_application(app.application_id, amritsar_admin, action="FORWARD")
    db_session.commit()
    assert app.current_stage == "STATE_REVIEW"

    # State Admin of Maharashtra attempts to review Punjab hospital
    maharashtra_admin = {"user_id": "U_MH_ADMIN", "role": "STATE_ADMIN", "state": "Maharashtra"}
    with pytest.raises(GeographicAccessError, match="cannot review application in State"):
        reg_service.review_application(app.application_id, maharashtra_admin, action="FORWARD")


def test_self_approval_prevented(reg_service, db_session):
    """Applicants cannot approve their own registration applications."""
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Super Specialty Jalandhar",
        "applicant_email": "dr.sharma@hospital.org",
        "applicant_phone": "0181-5551234",
        "state": "Punjab",
        "district": "Jalandhar",
        "nodal_officer_name": "Dr. Sharma",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "l.pdf", "application/pdf", 100, "k1", "9" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "f.pdf", "application/pdf", 100, "k2", "a" * 64)
    db_session.commit()
    reg_service.submit_application(app.application_id)
    db_session.commit()

    # 1. Reviewer whose user_id matches applicant email
    self_reviewer_id = {"user_id": "dr.sharma@hospital.org", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar"}
    with pytest.raises(SelfApprovalError, match="Applicant cannot review"):
        reg_service.review_application(app.application_id, self_reviewer_id, action="FORWARD")

    # 2. Reviewer whose email has different casing and trailing whitespace
    self_reviewer_casing = {"user_id": "U_DIST_01", "email": " DR.SHARMA@HOSPITAL.ORG ", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar"}
    with pytest.raises(SelfApprovalError, match="Applicant cannot review"):
        reg_service.review_application(app.application_id, self_reviewer_casing, action="FORWARD")

    # 3. Reviewer whose username matches applicant email
    self_reviewer_username = {"user_id": "U_REV_99", "username": "dr.sharma@hospital.org", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar"}
    with pytest.raises(SelfApprovalError, match="Applicant cannot review"):
        reg_service.review_application(app.application_id, self_reviewer_username, action="FORWARD")

    # 4. Reviewer matching nodal officer name case-insensitively
    self_reviewer_nodal = {"user_id": "dr. sharma", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Jalandhar"}
    with pytest.raises(SelfApprovalError, match="Applicant cannot review"):
        reg_service.review_application(app.application_id, self_reviewer_nodal, action="FORWARD")


# ============================================================
# 10. SAFE PUBLIC TRACKING SERVICE
# ============================================================

def test_safe_public_tracking_output(reg_service, db_session):
    """
    Public tracking service must expose ONLY safe milestone data:
    - Never expose Aadhaar, phone numbers, email addresses.
    - Never expose document storage paths or checksums.
    - Never expose internal reviewer remarks or password hashes.
    """
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Private Healthcare Facility",
        "applicant_email": "secret_doctor@private.org",
        "applicant_phone": "0172-9999999",
        "state": "Punjab",
        "district": "Mohali",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "sec.pdf", "application/pdf", 100, "private/storage/sec.pdf", "f" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "fire.pdf", "application/pdf", 100, "private/storage/fire.pdf", "0" * 64)
    db_session.commit()

    sub_res = reg_service.submit_application(app.application_id)
    db_session.commit()
    raw_token = sub_res["tracking_token"]

    public_info = reg_service.track_application_public(app.application_number, tracking_token=raw_token)

    # 1. Assert safe fields are present
    assert public_info["application_number"] == app.application_number
    assert public_info["applicant_name"] == "Private Healthcare Facility"
    assert public_info["state"] == "Punjab"
    assert public_info["district"] == "Mohali"
    assert public_info["status"] == "SUBMITTED"
    assert public_info["current_stage"] == "DISTRICT_REVIEW"
    assert len(public_info["milestones"]) == 1
    assert public_info["milestones"][0]["action"] == "SUBMIT"

    # 2. Strict Security Assertions: FORBIDDEN fields must not leak
    for forbidden_key in ["applicant_phone", "applicant_email", "storage_key", "password", "token_hash", "aadhaar"]:
        assert forbidden_key not in public_info

    # 3. Milestones must not leak reviewer remarks or reviewer IDs
    milestone = public_info["milestones"][0]
    assert "remarks" not in milestone
    assert "reviewer_user_id" not in milestone
    assert "ip_address" not in milestone


def test_invalid_or_expired_tracking_token(reg_service, db_session):
    """Invalid or expired tracking tokens must raise TrackingTokenError."""
    data = {
        "applicant_type": "STATE",
        "applicant_name": "Goa Health Department",
        "applicant_email": "health@goa.gov.in",
        "applicant_phone": "0832-2233445",
        "state": "Punjab",  # Using known state
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "GOVERNMENT_ORDER", "o.pdf", "application/pdf", 100, "k", "1" * 64)
    db_session.commit()
    sub_res = reg_service.submit_application(app.application_id)
    db_session.commit()

    # Wrong token
    with pytest.raises(TrackingTokenError, match="Invalid application number or tracking token"):
        reg_service.track_application_public(app.application_number, tracking_token="bogus_token_12345")

    # Expire token manually
    tok = db_session.query(ApplicationTrackingToken).filter_by(application_id=app.application_id).first()
    tok.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    with pytest.raises(TrackingTokenError, match="Invalid application number or tracking token"):
        reg_service.track_application_public(app.application_number, tracking_token=sub_res["tracking_token"])


# ============================================================
# 11. FINAL APPROVAL ELIGIBILITY CHECKS
# ============================================================

def test_final_approval_eligibility_checks(reg_service, db_session):
    """
    Final approval requires:
    - Application at CENTRAL_REVIEW stage.
    - All attached documents in VERIFIED status.
    - Mandatory documents present.
    """
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Patiala Medical Center",
        "applicant_email": "pmc@patiala.org",
        "applicant_phone": "0175-5554321",
        "state": "Punjab",
        "district": "Patiala",
        "nodal_officer_name": "Dr. B. Gill",
    }
    app = reg_service.create_application(data)
    d1 = reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "l.pdf", "application/pdf", 100, "k1", "a" * 64)
    d2 = reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "f.pdf", "application/pdf", 100, "k2", "b" * 64)
    db_session.commit()
    reg_service.submit_application(app.application_id)
    db_session.commit()

    # Case 1: Ineligible because currently at DISTRICT_REVIEW and documents are PENDING
    is_eligible, issues = reg_service.check_final_approval_eligibility(app.application_id)
    assert is_eligible is False
    assert any("CENTRAL_REVIEW" in issue for issue in issues)
    assert any("pending verification" in issue for issue in issues)

    # Advance to CENTRAL_REVIEW and verify documents
    app.current_stage = "CENTRAL_REVIEW"
    app.status = "UNDER_REVIEW"
    d1.verification_status = "VERIFIED"
    d2.verification_status = "VERIFIED"
    db_session.commit()

    # Case 2: Now eligible
    is_eligible, issues = reg_service.check_final_approval_eligibility(app.application_id)
    assert is_eligible is True
    assert len(issues) == 0


# ============================================================
# 12. TRANSACTION ROLLBACK INTEGRITY
# ============================================================

def test_transaction_rollback_on_review_failure(reg_service, db_session):
    """
    Verify that if a multi-step operation fails, the session can be rolled back cleanly
    without leaving corrupted partial state.
    """
    data = {
        "applicant_type": "HOSPITAL",
        "applicant_name": "Rollback Test Hospital",
        "applicant_email": "admin@rollback.org",
        "applicant_phone": "0172-5550000",
        "state": "Punjab",
        "district": "Mohali",
    }
    app = reg_service.create_application(data)
    reg_service.add_document_metadata(app.application_id, "CLINICAL_LICENSE", "l.pdf", "application/pdf", 100, "k1", "c" * 64)
    reg_service.add_document_metadata(app.application_id, "FIRE_SAFETY_NOC", "f.pdf", "application/pdf", 100, "k2", "d" * 64)
    db_session.commit()
    reg_service.submit_application(app.application_id)
    db_session.commit()

    initial_hist_count = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).count()

    # Attempt an unauthorized review operation in a nested try/except
    unauthorized_reviewer = {"user_id": "U_BAD_ROLE", "role": "CENTRAL_ADMIN"}
    try:
        reg_service.review_application(app.application_id, unauthorized_reviewer, action="FORWARD")
    except UnauthorizedReviewerError:
        db_session.rollback()

    # Verify state rolled back cleanly
    re_fetched = db_session.query(RegistrationApplication).filter_by(application_id=app.application_id).first()
    assert re_fetched.current_stage == "DISTRICT_REVIEW"
    assert re_fetched.status == "SUBMITTED"
    final_hist_count = db_session.query(ApprovalHistory).filter_by(application_id=app.application_id).count()
    assert final_hist_count == initial_hist_count
