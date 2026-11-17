"""
Phase 2D Comprehensive Test Suite: Reviewer Portal, Hierarchical Decisions & Account Lifecycle
AI Powered Smart Hospital Referral System

Validates:
1. Reviewer Authorization Matrix & Geographic Boundaries (District, State, Central, Hospital forbidden)
2. Document Verification API (VERIFIED, REJECTED, Cross-District boundary rejection)
3. Hierarchical Stage Decision Engine (FORWARD, APPROVE, REJECT, REQUEST_CORRECTION)
4. Invalid Stage Transitions & State Machine Integrity (Terminal states, stage jump boundaries)
5. Account Activation Lifecycle (password complexity, token single-use, expiry)
6. Password Reset Lifecycle (timing-safe request, token hash verification, session revocation)
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.db_manager import get_db_session
from src.database.pg_models import (
    PgBase,
    User,
    Role,
    RegistrationApplication,
    RegistrationDocument,
    RegistrationEmailOutbox,
    AccountActivationToken,
    PasswordResetToken,
)
from src.auth.jwt_utils import create_access_token
from src.auth.auth_store import hash_password, verify_password
from src.services.email_service import SimulatedEmailProvider, set_email_provider
from src.services.document_storage import SimulatedScanner, set_malware_scanner, LocalStorageAdapter, set_storage_adapter
from src.services.registration_service import RegistrationService
from src.services.account_provisioning_service import AccountProvisioningService
from src.services.email_outbox_service import EmailOutboxService
from src.auth.rate_limiter import reset_rate_limits

VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF"


@pytest.fixture
def phase2d_db_session():
    """Create in-memory SQLite session with StaticPool."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    # Seed required roles
    roles = [
        Role(id="HOSPITAL", description="Hospital Staff"),
        Role(id="DISTRICT_ADMIN", description="District Admin"),
        Role(id="STATE_ADMIN", description="State Admin"),
        Role(id="CENTRAL_ADMIN", description="Central Admin"),
    ]
    for r in roles:
        session.merge(r)

    # Seed reviewers across multiple districts and states
    users = [
        User(user_id="U_DIST_MOH", username="dist_moh", name="Mohali CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Mohali", is_active=True, password_hash="hash"),
        User(user_id="U_DIST_LUD", username="dist_lud", name="Ludhiana CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Ludhiana", is_active=True, password_hash="hash"),
        User(user_id="U_DIST_JPR", username="dist_jpr", name="Jaipur CMO", role_id="DISTRICT_ADMIN", state="Rajasthan", district="Jaipur", is_active=True, password_hash="hash"),
        User(user_id="U_STATE_PB", username="state_pb", name="Punjab Director", role_id="STATE_ADMIN", state="Punjab", is_active=True, password_hash="hash"),
        User(user_id="U_STATE_RJ", username="state_rj", name="Rajasthan Director", role_id="STATE_ADMIN", state="Rajasthan", is_active=True, password_hash="hash"),
        User(user_id="U_CENTRAL", username="central_admin", name="National Registrar", role_id="CENTRAL_ADMIN", is_active=True, password_hash="hash"),
        User(user_id="U_HOSP_USER", username="hosp_user", name="Hospital Staff", role_id="HOSPITAL", state="Punjab", district="Mohali", hospital_id="HOSP_001", is_active=True, password_hash="hash"),
    ]
    for u in users:
        session.merge(u)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sim_email():
    provider = SimulatedEmailProvider()
    set_email_provider(provider)
    return provider


@pytest.fixture
def sim_scanner():
    scanner = SimulatedScanner()
    set_malware_scanner(scanner)
    return scanner


@pytest.fixture
def sim_storage(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path / "phase2d_docs"))
    set_storage_adapter(storage)
    return storage


@pytest.fixture
def client(phase2d_db_session, sim_email, sim_scanner, sim_storage):
    reset_rate_limits()

    def _override_db():
        try:
            yield phase2d_db_session
        finally:
            pass

    app.dependency_overrides[get_db_session] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db_session, None)
    reset_rate_limits()


@pytest.fixture
def auth_tokens():
    return {
        "dist_mohali": create_access_token({"user_id": "U_DIST_MOH", "username": "dist_moh", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}),
        "dist_ludhiana": create_access_token({"user_id": "U_DIST_LUD", "username": "dist_lud", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Ludhiana"}),
        "dist_jaipur": create_access_token({"user_id": "U_DIST_JPR", "username": "dist_jpr", "role": "DISTRICT_ADMIN", "state": "Rajasthan", "district": "Jaipur"}),
        "state_punjab": create_access_token({"user_id": "U_STATE_PB", "username": "state_pb", "role": "STATE_ADMIN", "state": "Punjab"}),
        "state_rajasthan": create_access_token({"user_id": "U_STATE_RJ", "username": "state_rj", "role": "STATE_ADMIN", "state": "Rajasthan"}),
        "central": create_access_token({"user_id": "U_CENTRAL", "username": "central_admin", "role": "CENTRAL_ADMIN"}),
        "hospital_staff": create_access_token({"user_id": "U_HOSP_USER", "username": "hosp_user", "role": "HOSPITAL", "state": "Punjab", "district": "Mohali"}),
    }


def _seed_application(session, applicant_type="HOSPITAL", state="Punjab", district="Mohali", stage="DISTRICT_REVIEW", status="SUBMITTED"):
    reg_svc = RegistrationService(session)
    suffix = secrets.token_hex(4).upper()
    app = reg_svc.create_application({
        "applicant_type": applicant_type,
        "applicant_name": f"{state} {district} Test Facility {suffix}",
        "applicant_email": f"test_{suffix.lower()}@gov.in",
        "applicant_phone": "9876543210",
        "state": state,
        "district": district if applicant_type != "STATE" else None,
    })
    # Add required documents
    doc_type = "GOVERNMENT_ORDER" if applicant_type in ["STATE", "DISTRICT"] else "CLINICAL_LICENSE"
    reg_svc.upload_document_binary(app.application_id, doc_type, VALID_PDF_BYTES, "application/pdf", "doc1.pdf")
    if applicant_type == "HOSPITAL":
        reg_svc.upload_document_binary(app.application_id, "FIRE_SAFETY_NOC", VALID_PDF_BYTES, "application/pdf", "doc2.pdf")

    app.current_stage = stage
    app.status = status
    app.submitted_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(app)
    return app


# ==============================================================================
# 1. REVIEWER AUTHORIZATION & GEOGRAPHIC BOUNDARIES
# ==============================================================================

def test_reviewer_role_authorization_hospital_staff_rejected(client, auth_tokens):
    """Hospital staff role cannot access reviewer endpoints (403 Forbidden)."""
    headers = {"Authorization": f"Bearer {auth_tokens['hospital_staff']}"}
    resp = client.get("/api/registration/review/applications", headers=headers)
    assert resp.status_code == 403


def test_district_reviewer_geographic_boundary(client, phase2d_db_session, auth_tokens):
    """District reviewer can only see and access applications within their district."""
    app_moh = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")
    app_lud = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Ludhiana", "DISTRICT_REVIEW")
    app_jpr = _seed_application(phase2d_db_session, "HOSPITAL", "Rajasthan", "Jaipur", "DISTRICT_REVIEW")

    moh_headers = {"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    resp = client.get("/api/registration/review/applications", headers=moh_headers)
    assert resp.status_code == 200
    ids = [item["application_id"] for item in resp.json()["applications"]]
    assert app_moh.application_id in ids
    assert app_lud.application_id not in ids
    assert app_jpr.application_id not in ids

    # Direct detail access outside district must return 403
    resp_cross = client.get(f"/api/registration/review/applications/{app_lud.application_id}", headers=moh_headers)
    assert resp_cross.status_code == 403


def test_state_reviewer_geographic_boundary(client, phase2d_db_session, auth_tokens):
    """State reviewer sees all applications within state, blocked from other states."""
    app_moh = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "STATE_REVIEW")
    app_lud = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Ludhiana", "STATE_REVIEW")
    app_jpr = _seed_application(phase2d_db_session, "HOSPITAL", "Rajasthan", "Jaipur", "STATE_REVIEW")

    pb_headers = {"Authorization": f"Bearer {auth_tokens['state_punjab']}"}
    resp = client.get("/api/registration/review/applications", headers=pb_headers)
    assert resp.status_code == 200
    ids = [item["application_id"] for item in resp.json()["applications"]]
    assert app_moh.application_id in ids
    assert app_lud.application_id in ids
    assert app_jpr.application_id not in ids

    # Detail access to Rajasthan application must return 403
    resp_cross = client.get(f"/api/registration/review/applications/{app_jpr.application_id}", headers=pb_headers)
    assert resp_cross.status_code == 403


def test_central_reviewer_nationwide_access(client, phase2d_db_session, auth_tokens):
    """Central reviewer can view applications across all states and districts."""
    app_moh = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "CENTRAL_REVIEW")
    app_jpr = _seed_application(phase2d_db_session, "HOSPITAL", "Rajasthan", "Jaipur", "CENTRAL_REVIEW")

    central_headers = {"Authorization": f"Bearer {auth_tokens['central']}"}
    resp = client.get("/api/registration/review/applications", headers=central_headers)
    assert resp.status_code == 200
    ids = [item["application_id"] for item in resp.json()["applications"]]
    assert app_moh.application_id in ids
    assert app_jpr.application_id in ids


# ==============================================================================
# 2. DOCUMENT VERIFICATION API
# ==============================================================================

def test_document_verification_lifecycle(client, phase2d_db_session, auth_tokens):
    """Reviewers can verify or reject documents with remarks and geographic security."""
    app = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")
    doc = phase2d_db_session.query(RegistrationDocument).filter_by(application_id=app.application_id).first()

    moh_headers = {"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    lud_headers = {"Authorization": f"Bearer {auth_tokens['dist_ludhiana']}"}

    # Cross-district reviewer verification must return 403
    resp_cross = client.post(
        f"/api/registration/review/documents/{doc.document_id}/verify",
        json={"verification_status": "VERIFIED", "reviewer_remarks": "Cross-district review attempt"},
        headers=lud_headers
    )
    assert resp_cross.status_code == 403

    # Reject document
    resp_reject = client.post(
        f"/api/registration/review/documents/{doc.document_id}/verify",
        json={"verification_status": "REJECTED", "reviewer_remarks": "Stamp is illegible"},
        headers=moh_headers
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["verification_status"] == "REJECTED"

    # Verify document
    resp_verify = client.post(
        f"/api/registration/review/documents/{doc.document_id}/verify",
        json={"verification_status": "VERIFIED", "reviewer_remarks": "Verified against state medical registry"},
        headers=moh_headers
    )
    assert resp_verify.status_code == 200
    assert resp_verify.json()["verification_status"] == "VERIFIED"


# ==============================================================================
# 3. HIERARCHICAL STAGE TRANSITIONS & DECISION ENGINE
# ==============================================================================

def test_hospital_complete_hierarchical_approval_to_provisioning(client, phase2d_db_session, auth_tokens, sim_email):
    """Hospital application flows: DISTRICT_REVIEW -> STATE_REVIEW -> CENTRAL_REVIEW -> APPROVED."""
    app = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")
    # Verify all documents before decision
    docs = phase2d_db_session.query(RegistrationDocument).filter_by(application_id=app.application_id).all()
    for d in docs:
        d.verification_status = "VERIFIED"
    phase2d_db_session.commit()

    # Step 1: District Reviewer forwards to State
    resp1 = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "FORWARD", "remarks": "Verified local facilities. Forwarding to State."},
        headers={"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    )
    assert resp1.status_code == 200
    assert resp1.json()["new_stage"] == "STATE_REVIEW"

    # Step 2: State Reviewer forwards to Central
    resp2 = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "FORWARD", "remarks": "State health directorate approved. Forwarding to Central."},
        headers={"Authorization": f"Bearer {auth_tokens['state_punjab']}"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["new_stage"] == "CENTRAL_REVIEW"

    # Step 3: Central Reviewer approves and triggers provisioning
    resp3 = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "APPROVE", "remarks": "National registration granted."},
        headers={"Authorization": f"Bearer {auth_tokens['central']}"}
    )
    assert resp3.status_code == 200
    assert resp3.json()["new_stage"] == "APPROVED"
    assert resp3.json()["new_status"] == "APPROVED"
    assert resp3.json()["provisioning_user_id"] is not None

    # Verify RegistrationEmailOutbox event enqueued
    outbox_event = phase2d_db_session.query(RegistrationEmailOutbox).filter_by(recipient_email=app.applicant_email, event_type="ACCOUNT_ACTIVATION").first()
    assert outbox_event is not None
    assert outbox_event.status in ("PENDING", "SENT")
    assert outbox_event.event_type == "ACCOUNT_ACTIVATION"


def test_invalid_decision_transitions_blocked(client, phase2d_db_session, auth_tokens):
    """Verify that stage skipping and unauthorized actions are blocked by state machine."""
    app = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")

    # Central reviewer cannot act on application while at DISTRICT_REVIEW stage
    resp_central_early = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "APPROVE", "remarks": "Bypassing early stages"},
        headers={"Authorization": f"Bearer {auth_tokens['central']}"}
    )
    assert resp_central_early.status_code == 403

    # Fast-forward app to APPROVED terminal status
    app.status = "APPROVED"
    app.current_stage = "APPROVED"
    phase2d_db_session.commit()

    # Any decision on terminal status must return 400
    resp_terminal = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "FORWARD", "remarks": "Already approved"},
        headers={"Authorization": f"Bearer {auth_tokens['central']}"}
    )
    assert resp_terminal.status_code == 400


def test_rejection_workflow_and_terminal_state(client, phase2d_db_session, auth_tokens):
    """Rejection sets status to REJECTED and blocks subsequent reviews."""
    app = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")

    resp_valid = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "REJECT", "remarks": "Facility does not satisfy emergency trauma protocol"},
        headers={"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["new_status"] == "REJECTED"

    # Terminal rejection blocks subsequent decision
    resp_subsequent = client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "FORWARD", "remarks": "Re-forwarding rejected app"},
        headers={"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    )
    assert resp_subsequent.status_code == 400


def test_correction_request_workflow(client, phase2d_db_session, auth_tokens):
    """Reviewer requests correction; status becomes CORRECTION_REQUIRED."""
    app = _seed_application(phase2d_db_session, "HOSPITAL", "Punjab", "Mohali", "DISTRICT_REVIEW")

    resp = client.post(
        f"/api/registration/review/applications/{app.application_id}/request-correction",
        json={"correction_notes": "Please re-upload clear clinical license and update bed count"},
        headers={"Authorization": f"Bearer {auth_tokens['dist_mohali']}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CORRECTION_REQUIRED"


# ==============================================================================
# 4. ACCOUNT ACTIVATION LIFECYCLE
# ==============================================================================

def test_account_activation_lifecycle_and_security(client, phase2d_db_session, auth_tokens, sim_email):
    """Test full activation: token hashing, password complexity, single-use, expiry."""
    reg_svc = RegistrationService(phase2d_db_session)
    app = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Punjab Activation Test",
        "applicant_email": "act_test_user@punjab.gov.in",
        "applicant_phone": "9876543230",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    phase2d_db_session.commit()

    # Central Admin approves
    client.post(
        f"/api/registration/review/applications/{app.application_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {auth_tokens['central']}"},
    )

    # Extract raw activation token from dispatched email
    sent = sim_email.get_last_email(app.applicant_email)
    assert sent is not None
    link = sent["activation_link"]
    raw_token = link.split("token=")[-1]
    assert len(raw_token) > 20

    # 1. Weak password rejected (< 8 chars)
    resp_weak = client.post(
        "/api/registration/auth/activate",
        json={"activation_token": raw_token, "password": "Short1!", "confirm_password": "Short1!"}
    )
    assert resp_weak.status_code in [400, 422]

    # 2. Mismatched passwords rejected
    resp_mismatch = client.post(
        "/api/registration/auth/activate",
        json={"activation_token": raw_token, "password": "StrongPassword!2026", "confirm_password": "DifferentPassword!2026"}
    )
    assert resp_mismatch.status_code in [400, 422]

    # 3. Valid activation
    resp_success = client.post(
        "/api/registration/auth/activate",
        json={"activation_token": raw_token, "password": "StrongPassword!2026", "confirm_password": "StrongPassword!2026"}
    )
    assert resp_success.status_code == 200
    data = resp_success.json()
    assert data["user_id"] is not None

    # 4. Token cannot be reused (single-use)
    resp_reuse = client.post(
        "/api/registration/auth/activate",
        json={"activation_token": raw_token, "password": "AnotherPassword!2026", "confirm_password": "AnotherPassword!2026"}
    )
    assert resp_reuse.status_code == 400


def test_expired_activation_token_fails(client, phase2d_db_session):
    """Expired activation token is rejected."""
    raw_token = secrets.token_urlsafe(32)
    tok = AccountActivationToken(
        activation_token_id=f"ACT-{secrets.token_hex(4)}",
        application_id=None,
        user_id="U_DIST_MOH",
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_consumed=False
    )
    phase2d_db_session.add(tok)
    phase2d_db_session.commit()

    resp = client.post(
        "/api/registration/auth/activate",
        json={"activation_token": raw_token, "password": "StrongPassword!2026", "confirm_password": "StrongPassword!2026"}
    )
    assert resp.status_code == 400


# ==============================================================================
# 5. PASSWORD RESET LIFECYCLE
# ==============================================================================

def test_password_recovery_request_timing_safe_and_reset(client, phase2d_db_session, sim_email):
    """Password reset request returns timing-safe message and confirmation updates password."""
    # Seed active user
    user = User(
        user_id="U_RESET_TEST_P2D",
        username="dr_sharma_p2d",
        name="Dr. Sharma",
        email="dr_sharma_p2d@hospital.gov.in",
        role_id="HOSPITAL",
        state="Punjab",
        district="Mohali",
        is_active=True,
        password_hash="pbkdf2:sha256:100000$oldsalt$fakehash"
    )
    phase2d_db_session.add(user)
    phase2d_db_session.commit()

    # Request for valid email
    resp_valid = client.post(
        "/api/registration/auth/password-reset/request",
        json={"email": "dr_sharma_p2d@hospital.gov.in"}
    )
    assert resp_valid.status_code == 200
    assert "If an active account exists" in resp_valid.json()["message"]

    # Request for nonexistent email returns same message (enumeration prevention)
    resp_invalid = client.post(
        "/api/registration/auth/password-reset/request",
        json={"email": "nonexistent@fake.gov.in"}
    )
    assert resp_invalid.status_code == 200
    assert "If an active account exists" in resp_invalid.json()["message"]

    # Verify reset token in DB and dispatch email outbox
    outbox_svc = EmailOutboxService(phase2d_db_session, sim_email)
    outbox_svc.process_outbox()

    sent = sim_email.get_last_email("dr_sharma_p2d@hospital.gov.in")
    assert sent is not None
    reset_link = sent["body_text"].split("token=")[-1].split("\n")[0].strip()

    # Weak password rejected
    weak_res = client.post(
        "/api/registration/auth/password-reset/confirm",
        json={"reset_token": reset_link, "password": "weak", "confirm_password": "weak"}
    )
    assert weak_res.status_code == 422

    # Confirm password reset
    resp_confirm = client.post(
        "/api/registration/auth/password-reset/confirm",
        json={"reset_token": reset_link, "password": "NewSecretPassword@2026", "confirm_password": "NewSecretPassword@2026"}
    )
    assert resp_confirm.status_code == 200
    assert "successfully reset" in resp_confirm.json()["message"].lower()

    # Token cannot be reused
    resp_confirm_again = client.post(
        "/api/registration/auth/password-reset/confirm",
        json={"reset_token": reset_link, "password": "NewSecretPassword@2026", "confirm_password": "NewSecretPassword@2026"}
    )
    assert resp_confirm_again.status_code == 400


def test_account_provisioning_yes_no_normalization(phase2d_db_session):
    """
    Regression verification for hospital emergency_24x7 and accepts_referral normalization.
    Ensures boolean and string values conform to PostgreSQL CHECK constraint ('Yes', 'No').
    """
    from src.database.pg_models import Hospital

    # Create dummy application for hospital
    app = RegistrationApplication(
        application_id="app-hosp-yesno-test",
        application_number="APP-20261111-HOSPYESNO",
        applicant_type="HOSPITAL",
        applicant_name="Test Normalization Hospital",
        applicant_email="hosp_yesno@example.com",
        applicant_phone="9876543299",
        state="Punjab",
        district="Ludhiana",
        city="Ludhiana",
        address="Civil Lines",
        pincode="141001",
        status="APPROVED",
        current_stage="APPROVED",
        profile_data={
            "emergency_24x7": True,
            "accepts_referral": "false",
            "total_beds": 60,
            "available_beds": 25,
            "icu_beds": 8,
            "available_icu_beds": 3,
        }
    )
    phase2d_db_session.add(app)
    phase2d_db_session.commit()

    service = AccountProvisioningService(phase2d_db_session)
    res = service.provision_account(
        application_id=app.application_id,
        reviewer_user={"user_id": "U_CENTRAL_01", "role": "CENTRAL_ADMIN", "username": "central_admin"}
    )

    hosp = phase2d_db_session.query(Hospital).filter_by(application_id=app.application_id).first()
    assert hosp is not None
    assert hosp.emergency_24x7 == "Yes"
    assert hosp.accepts_referral == "No"


def test_auth_store_database_user_authentication_and_lookup(phase2d_db_session, monkeypatch):
    """
    Regression verification for auth_store.py relational database user lookup.
    Ensures active provisioned database users authenticate and can be looked up by ID.
    """
    from src.auth.auth_store import authenticate_user, get_user_by_id

    # Create active provisioned DB user
    pwd_hash = hash_password("ValidPassword@2026")
    db_user = User(
        user_id="U_PROVISIONED_P2D_TEST",
        username="dr_prov_test",
        name="Dr. Provisioned Test",
        email="dr_prov@hospital.gov.in",
        phone_number="9876543201",
        role_id="HOSPITAL",
        state="Punjab",
        district="Amritsar",
        is_active=True,
        password_hash=pwd_hash,
    )
    phase2d_db_session.add(db_user)
    phase2d_db_session.commit()

    # Monkeypatch get_session_factory to return session maker pointing to test DB session
    class DummySessionFactory:
        def __call__(self):
            return phase2d_db_session
        def __enter__(self):
            return phase2d_db_session
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("src.database.db_manager.get_session_factory", lambda: DummySessionFactory())

    # Successful authentication
    auth_res = authenticate_user("dr_prov_test", "ValidPassword@2026")
    assert auth_res is not None
    assert auth_res["user_id"] == "U_PROVISIONED_P2D_TEST"
    assert auth_res["role"] == "HOSPITAL"

    # Invalid password fails
    fail_res = authenticate_user("dr_prov_test", "WrongPassword@2026")
    assert fail_res is None

    # Lookup by user ID succeeds
    user_lookup = get_user_by_id("U_PROVISIONED_P2D_TEST")
    assert user_lookup is not None
    assert user_lookup["username"] == "dr_prov_test"
    assert user_lookup["district"] == "Amritsar"


def test_reviewer_application_lookup_by_number_and_id(phase2d_db_session):
    """
    Regression verification for get_reviewer_application_detail.
    Ensures reviewer can look up applications by UUID or human-readable application_number.
    """
    client = TestClient(app)
    app.dependency_overrides[get_db_session] = lambda: phase2d_db_session

    app_rec = RegistrationApplication(
        application_id="app-uuid-lookup-1234",
        application_number="APP-20261111-LOOKUPTEST",
        applicant_type="HOSPITAL",
        applicant_name="Lookup Test Hospital",
        applicant_email="lookup_test@hospital.gov.in",
        applicant_phone="9876543288",
        state="Punjab",
        district="Amritsar",
        status="UNDER_REVIEW",
        current_stage="DISTRICT_REVIEW",
    )
    phase2d_db_session.add(app_rec)
    phase2d_db_session.commit()

    # Create district reviewer token
    reviewer_token = create_access_token({
        "user_id": "U_DIST_AMRITSAR",
        "username": "dist_amritsar",
        "role": "DISTRICT_ADMIN",
        "state": "Punjab",
        "district": "Amritsar",
    })
    headers = {"Authorization": f"Bearer {reviewer_token}"}

    # 1. Lookup via application_id (UUID)
    resp_id = client.get(f"/api/registration/review/applications/{app_rec.application_id}", headers=headers)
    assert resp_id.status_code == 200
    assert resp_id.json()["application_number"] == "APP-20261111-LOOKUPTEST"

    # 2. Lookup via application_number (APP-...)
    resp_num = client.get(f"/api/registration/review/applications/{app_rec.application_number}", headers=headers)
    assert resp_num.status_code == 200
    assert resp_num.json()["application_id"] == "app-uuid-lookup-1234"

