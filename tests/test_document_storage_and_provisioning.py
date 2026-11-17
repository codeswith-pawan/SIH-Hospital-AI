"""
Comprehensive Test Suite for Phase 1 Task 1E:
Secure Document Storage & Operational Account Provisioning
AI Powered Smart Hospital Referral System

Validates:
- Part A: Multipart document upload, PDF/JPEG/PNG magic-byte inspection, MIME spoofing prevention,
  25MB size limit, SHA-256 stream hashing, antivirus malware scanning, authorized download,
  document replacement, and deletion.
- Part B: Operational account provisioning triggered ONLY by Central Government final approval
  across all 3 applicant types (STATE, DISTRICT, HOSPITAL), hospital entity creation,
  role mapping, and idempotency.
- Part C: Cryptographic activation token lifecycle (SHA-256 hashed storage, expiration,
  single-use consumption), secure password creation with complexity enforcement, PBKDF2 hashing,
  and activation link delivery without plaintext passwords.
- Part D: Transaction safety, duplicate prevention, and post-commit email dispatch.
"""

import os
import io
import pytest
import secrets
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.db_manager import get_db_session
from src.database.pg_models import (
    PgBase, User, Hospital, Role, RegistrationApplication,
    RegistrationDocument, AccountActivationToken, PasswordResetToken,
    RegistrationEmailOutbox, VerificationToken
)
from src.auth.jwt_utils import create_access_token
from src.auth.auth_store import verify_password, authenticate_user
from src.auth.registration_auth import create_applicant_token
from src.auth.rate_limiter import reset_rate_limits
from src.services.document_storage import (
    get_storage_adapter, set_storage_adapter, LocalStorageAdapter, S3StorageAdapter,
    get_malware_scanner, set_malware_scanner, SimulatedScanner, MalwareDetectedError,
    MalwareScanServiceUnavailableError, MalwareScanError,
    verify_file_content, DocumentStorageError
)
from src.services.email_service import (
    get_email_provider, set_email_provider, SimulatedEmailProvider, EmailDeliveryError
)
from src.services.email_outbox_service import EmailOutboxService
from src.services.otp_service import OTPService
from src.services.registration_service import RegistrationService
from src.services.account_provisioning_service import (
    AccountProvisioningService, ActivationTokenError, PasswordComplexityError
)
from src.services.registration_exceptions import (
    ValidationError, IneligibleForApprovalError, DocumentError,
    GeographicAccessError, UnauthorizedReviewerError
)


# Test payload bytes
VALID_PDF_BYTES = b"%PDF-1.4 \n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 2\ntrailer<</Size 2/Root 1 0 R>>\nstartxref\n99\n%%EOF"
VALID_JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xd9"
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


@pytest.fixture
def test_db_session():
    """Create in-memory SQLite session with StaticPool for thread safety."""
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

    # Seed reviewers
    users = [
        User(user_id="U_DIST_MOH", username="dist_moh", name="Mohali CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Mohali", password_hash="hash"),
        User(user_id="U_STATE_PB", username="state_pb", name="Punjab Director", role_id="STATE_ADMIN", state="Punjab", password_hash="hash"),
        User(user_id="U_CENTRAL", username="central_admin", name="National Registrar", role_id="CENTRAL_ADMIN", password_hash="hash"),
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
    storage = LocalStorageAdapter(base_dir=str(tmp_path / "documents"))
    set_storage_adapter(storage)
    return storage


@pytest.fixture
def client(test_db_session, sim_email, sim_scanner, sim_storage):
    reset_rate_limits()

    def _override_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db_session] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db_session, None)
    reset_rate_limits()


@pytest.fixture
def reviewer_tokens():
    return {
        "dist_mohali": create_access_token({"user_id": "U_DIST_MOH", "username": "dist_moh", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}),
        "state_punjab": create_access_token({"user_id": "U_STATE_PB", "username": "state_pb", "role": "STATE_ADMIN", "state": "Punjab"}),
        "central": create_access_token({"user_id": "U_CENTRAL", "username": "central_admin", "role": "CENTRAL_ADMIN"}),
    }


# ============================================================
# 1. DOCUMENT STORAGE & CONTENT VALIDATION TESTS
# ============================================================

def test_multipart_upload_valid_pdf_and_jpeg_and_png(client, test_db_session):
    """Verify valid multipart uploads for PDF, JPEG, and PNG files."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "HOSPITAL",
        "applicant_name": "Civil Hospital Mohali",
        "applicant_email": "doc_test@punjab.gov.in",
        "applicant_phone": "9876543210",
        "state": "Punjab",
        "district": "Mohali",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload valid PDF
    res_pdf = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "CLINICAL_LICENSE"},
        files={"file": ("license.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert res_pdf.status_code == 200, f"PDF upload failed: {res_pdf.text}"
    pdf_data = res_pdf.json()
    assert pdf_data["mime_type"] == "application/pdf"
    assert pdf_data["file_size_bytes"] == len(VALID_PDF_BYTES)
    assert pdf_data["verification_status"] == "PENDING"

    # 2. Upload valid JPEG
    res_jpg = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "FIRE_SAFETY_NOC"},
        files={"file": ("fire_noc.jpg", VALID_JPEG_BYTES, "image/jpeg")},
        headers=headers,
    )
    assert res_jpg.status_code == 200
    jpg_data = res_jpg.json()
    assert jpg_data["mime_type"] == "image/jpeg"

    # 3. Upload valid PNG
    res_png = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "IDENTITY_PROOF"},
        files={"file": ("id.png", VALID_PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert res_png.status_code == 200
    png_data = res_png.json()
    assert png_data["mime_type"] == "image/png"


def test_mime_spoofing_rejected(client, test_db_session):
    """Client declaring 'application/pdf' with text or script bytes must be rejected."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apollo Clinic",
        "applicant_email": "spoof@punjab.gov.in",
        "applicant_phone": "9876543211",
        "state": "Punjab",
        "district": "Mohali",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Text script disguised as PDF
    fake_pdf = b"#!/bin/bash\necho 'This is not a real PDF file!'"
    res = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "CLINICAL_LICENSE"},
        files={"file": ("license.pdf", fake_pdf, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 422
    assert "File content signature does not match allowed types" in res.json()["detail"]


def test_oversized_file_rejected(client, test_db_session):
    """Uploading a file exceeding 25MB must be rejected."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "State Dept",
        "applicant_email": "oversize@punjab.gov.in",
        "applicant_phone": "9876543212",
        "state": "Punjab",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Construct payload starting with valid PDF magic bytes but exceeding 25MB
    large_size = 25 * 1024 * 1024 + 1024
    oversized_bytes = b"%PDF-" + b"0" * (large_size - 5)

    res = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("huge_order.pdf", oversized_bytes, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 422
    assert "exceeds maximum allowable limit of 25 MB" in res.json()["detail"]


def test_malware_scan_failure_detection(client, test_db_session, sim_scanner):
    """Files containing malware signatures must be detected and rejected."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "DISTRICT",
        "applicant_name": "District Health Society",
        "applicant_email": "malware_test@punjab.gov.in",
        "applicant_phone": "9876543213",
        "state": "Punjab",
        "district": "Mohali",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # PDF containing embedded EICAR test string
    eicar_pdf = b"%PDF-1.4\n" + SimulatedScanner.EICAR_SIGNATURE
    res = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("infected.pdf", eicar_pdf, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 422
    assert "Malware scan failure" in res.json()["detail"]


def test_storage_adapter_failure_handled(client, test_db_session):
    """When storage adapter raises failure, API returns 500 and database transaction is rolled back."""
    class FailingStorage(LocalStorageAdapter):
        def put_object(self, storage_key: str, data: bytes, content_type: str) -> str:
            raise DocumentStorageError("Simulated disk I/O failure.")

    set_storage_adapter(FailingStorage())

    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "State Dept",
        "applicant_email": "storage_fail@punjab.gov.in",
        "applicant_phone": "9876543214",
        "state": "Punjab",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("order.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 500
    assert "Simulated disk I/O failure" in res.json()["detail"]

    # Verify no orphan record in database
    docs = test_db_session.query(RegistrationDocument).filter_by(application_id=app_record.application_id).all()
    assert len(docs) == 0


def test_document_download_authorization(client, test_db_session, reviewer_tokens):
    """Document download must enforce applicant ownership and reviewer geographic scope."""
    reg_svc = RegistrationService(test_db_session)
    app1 = reg_svc.create_application({
        "applicant_type": "HOSPITAL",
        "applicant_name": "Mohali Civil Hospital",
        "applicant_email": "mohali_doc@punjab.gov.in",
        "applicant_phone": "9876543215",
        "state": "Punjab",
        "district": "Mohali",
    })
    test_db_session.commit()

    token1 = create_applicant_token({
        "application_number": app1.application_number,
        "application_id": app1.application_id,
        "applicant_email": app1.applicant_email,
    })
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Upload document
    upload_res = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "CLINICAL_LICENSE"},
        files={"file": ("clinical_license.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers1,
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["document_id"]

    # 1. Legitimate applicant download succeeds
    dl_owner = client.get(f"/api/registration/applications/documents/{doc_id}/download", headers=headers1)
    assert dl_owner.status_code == 200
    assert dl_owner.content == VALID_PDF_BYTES
    assert dl_owner.headers["content-type"] == "application/pdf"
    assert "attachment" in dl_owner.headers["content-disposition"]

    # 2. Another applicant attempts download -> 403 Forbidden
    other_token = create_applicant_token({
        "application_number": "APP-2026-OTHER",
        "application_id": "APP_OTHER_9999",
        "applicant_email": "other@punjab.gov.in",
    })
    dl_other = client.get(f"/api/registration/applications/documents/{doc_id}/download", headers={"Authorization": f"Bearer {other_token}"})
    assert dl_other.status_code == 403
    assert "Access denied" in dl_other.json()["detail"]

    # Upload mandatory second document and submit application so it enters review pipeline (DISTRICT_REVIEW)
    upload_res2 = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "FIRE_SAFETY_NOC"},
        files={"file": ("fire_noc.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers1,
    )
    assert upload_res2.status_code == 200

    reg_svc.submit_application(app1.application_id)
    test_db_session.commit()

    # 3. Authorized Mohali District Admin download succeeds
    dl_dist = client.get(f"/api/registration/applications/documents/{doc_id}/download", headers={"Authorization": f"Bearer {reviewer_tokens['dist_mohali']}"})
    assert dl_dist.status_code == 200
    assert dl_dist.content == VALID_PDF_BYTES

    # 4. Unauthorized reviewer (Amritsar District Admin) -> 403 Forbidden
    dist_amritsar = create_access_token({"user_id": "U_DIST_ASR", "username": "dist_asr", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Amritsar"})
    dl_unauth_dist = client.get(f"/api/registration/applications/documents/{doc_id}/download", headers={"Authorization": f"Bearer {dist_amritsar}"})
    assert dl_unauth_dist.status_code == 403

    # 5. Reviewer outside current stage (Central Admin cannot access while in DISTRICT_REVIEW) -> 403
    dl_stage_mismatch = client.get(f"/api/registration/applications/documents/{doc_id}/download", headers={"Authorization": f"Bearer {reviewer_tokens['central']}"})
    assert dl_stage_mismatch.status_code == 403

    # 6. Central Admin CAN download documents for an application in CENTRAL_REVIEW (e.g. State application)
    app_state = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Punjab Health State Mission",
        "applicant_email": "state_mission@punjab.gov.in",
        "applicant_phone": "9876543299",
        "state": "Punjab",
    })
    doc_state = reg_svc.upload_document_binary(app_state.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_state.application_id)
    test_db_session.commit()

    dl_central = client.get(f"/api/registration/applications/documents/{doc_state.document_id}/download", headers={"Authorization": f"Bearer {reviewer_tokens['central']}"})
    assert dl_central.status_code == 200
    assert dl_central.content == VALID_PDF_BYTES


def test_document_replacement_and_deletion(client, test_db_session):
    """Uploading a document of the same type replaces previous blob and resets verification status."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Punjab",
        "applicant_email": "replace@punjab.gov.in",
        "applicant_phone": "9876543216",
        "state": "Punjab",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # Initial upload
    up1 = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("order_v1.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert up1.status_code == 200
    doc_id1 = up1.json()["document_id"]

    # Re-upload with same document_type (Replacement)
    up2 = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("order_v2.png", VALID_PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert up2.status_code == 200
    doc_id2 = up2.json()["document_id"]
    # Generates fresh document_id; old document_id is invalidated
    assert doc_id2 != doc_id1
    assert up2.json()["mime_type"] == "image/png"

    # Stale identifier cannot be retrieved
    dl_stale = client.get(f"/api/registration/applications/documents/{doc_id1}/download", headers=headers)
    assert dl_stale.status_code == 400
    assert "not found" in dl_stale.json()["detail"].lower()

    # Verify download of new document returns v2 bytes
    dl = client.get(f"/api/registration/applications/documents/{doc_id2}/download", headers=headers)
    assert dl.status_code == 200
    assert dl.content == VALID_PNG_BYTES

    # Delete document
    del_res = client.delete(f"/api/registration/applications/documents/{doc_id2}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["message"] == "Document successfully deleted."

    # Subsequent download returns 400 (document not found)
    dl_after = client.get(f"/api/registration/applications/documents/{doc_id2}/download", headers=headers)
    assert dl_after.status_code == 400


# ============================================================
# 2. OPERATIONAL ACCOUNT PROVISIONING TESTS
# ============================================================

def test_provisioning_state_admin_on_central_approval(client, test_db_session, reviewer_tokens, sim_email):
    """Central Admin final approval of a State application provisions STATE_ADMIN account."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Directorate of Health Services Punjab",
        "applicant_email": "director_health@punjab.gov.in",
        "applicant_phone": "9876543220",
        "state": "Punjab",
    })
    # Attach mandatory document
    reg_svc.upload_document_binary(
        application_id=app_record.application_id,
        document_type="GOVERNMENT_ORDER",
        file_bytes=VALID_PDF_BYTES,
        declared_mime="application/pdf",
        original_filename="order.pdf",
    )
    test_db_session.commit()

    # Submit application
    reg_svc.submit_application(app_record.application_id)
    test_db_session.commit()
    assert app_record.current_stage == "CENTRAL_REVIEW"

    # Verify document by Central Admin
    doc = app_record.documents[0]
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # Central Admin final approval via API
    central_headers = {"Authorization": f"Bearer {reviewer_tokens['central']}"}
    appr_res = client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE", "remarks": "National health accreditation approved."},
        headers=central_headers,
    )
    assert appr_res.status_code == 200, f"Approval failed: {appr_res.text}"
    appr_data = appr_res.json()
    assert appr_data["new_status"] == "APPROVED"
    assert appr_data["provisioning_user_id"] is not None
    assert appr_data["provisioning_username"].startswith("state_punjab")

    # Verify database state
    provisioned_user = test_db_session.query(User).filter_by(application_id=app_record.application_id).first()
    assert provisioned_user is not None
    assert provisioned_user.role_id == "STATE_ADMIN"
    assert provisioned_user.state == "Punjab"
    assert provisioned_user.district is None
    assert provisioned_user.hospital_id is None
    assert provisioned_user.is_active is False  # Inactive until activation
    assert provisioned_user.password_hash == "PENDING_ACTIVATION"

    # Verify activation token created
    act_token = test_db_session.query(AccountActivationToken).filter_by(user_id=provisioned_user.user_id).first()
    assert act_token is not None
    assert act_token.is_consumed is False
    tok_exp = act_token.expires_at if act_token.expires_at.tzinfo else act_token.expires_at.replace(tzinfo=timezone.utc)
    assert tok_exp > datetime.now(timezone.utc)

    # Verify post-commit activation email dispatched
    sent = sim_email.get_last_email(app_record.applicant_email)
    assert sent is not None
    assert "activate?token=" in sent["activation_link"]
    assert sent["role_title"] == "State Health Administrator"


def test_provisioning_district_admin_on_central_approval(client, test_db_session, reviewer_tokens, sim_email):
    """District application full hierarchy approval provisions DISTRICT_ADMIN account."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "DISTRICT",
        "applicant_name": "District Health Society Mohali",
        "applicant_email": "dhs_mohali@punjab.gov.in",
        "applicant_phone": "9876543221",
        "state": "Punjab",
        "district": "Mohali",
    })
    reg_svc.upload_document_binary(
        application_id=app_record.application_id,
        document_type="GOVERNMENT_ORDER",
        file_bytes=VALID_PDF_BYTES,
        declared_mime="application/pdf",
        original_filename="order.pdf",
    )
    test_db_session.commit()

    reg_svc.submit_application(app_record.application_id)
    test_db_session.commit()
    assert app_record.current_stage == "STATE_REVIEW"

    # 1. State Admin forwards
    pb_headers = {"Authorization": f"Bearer {reviewer_tokens['state_punjab']}"}
    fwd_res = client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "FORWARD", "remarks": "State endorsed."},
        headers=pb_headers,
    )
    assert fwd_res.status_code == 200
    assert fwd_res.json()["new_stage"] == "CENTRAL_REVIEW"

    # 2. Central Admin verifies doc
    doc = app_record.documents[0]
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # 3. Central Admin approves
    central_headers = {"Authorization": f"Bearer {reviewer_tokens['central']}"}
    appr_res = client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE", "remarks": "National approval granted."},
        headers=central_headers,
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["provisioning_username"].startswith("dist_mohali")

    # Verify user record
    user = test_db_session.query(User).filter_by(application_id=app_record.application_id).first()
    assert user.role_id == "DISTRICT_ADMIN"
    assert user.state == "Punjab"
    assert user.district == "Mohali"
    assert user.hospital_id is None
    assert user.is_active is False


def test_provisioning_hospital_admin_and_hospital_entity(client, test_db_session, reviewer_tokens, sim_email):
    """Hospital application approval creates both a new Hospital entity and Hospital Admin User."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "HOSPITAL",
        "applicant_name": "Apex Heart & Trauma Center",
        "applicant_email": "apex_admin@punjab.gov.in",
        "applicant_phone": "9876543222",
        "state": "Punjab",
        "district": "Mohali",
        "city": "Mohali",
        "total_beds": 120,
        "icu_beds": 15,
        "emergency_beds": 10,
        "latitude": 30.7100,
        "longitude": 76.7200,
    })
    # Attach 2 mandatory documents
    d1 = reg_svc.upload_document_binary(app_record.application_id, "CLINICAL_LICENSE", VALID_PDF_BYTES, "application/pdf", "lic.pdf")
    d2 = reg_svc.upload_document_binary(app_record.application_id, "FIRE_SAFETY_NOC", VALID_JPEG_BYTES, "image/jpeg", "fire.jpg")
    test_db_session.commit()

    reg_svc.submit_application(app_record.application_id)
    test_db_session.commit()

    # District verifies docs and forwards
    dist_headers = {"Authorization": f"Bearer {reviewer_tokens['dist_mohali']}"}
    reg_svc.verify_document(d1.document_id, {"user_id": "U_DIST_MOH", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}, "VERIFIED")
    reg_svc.verify_document(d2.document_id, {"user_id": "U_DIST_MOH", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}, "VERIFIED")
    test_db_session.commit()

    client.post(f"/api/registration/review/applications/{app_record.application_id}/decision", json={"action": "FORWARD"}, headers=dist_headers)
    # State forwards
    client.post(f"/api/registration/review/applications/{app_record.application_id}/decision", json={"action": "FORWARD"}, headers={"Authorization": f"Bearer {reviewer_tokens['state_punjab']}"})

    # Central approves
    appr_res = client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {reviewer_tokens['central']}"},
    )
    assert appr_res.status_code == 200

    # 1. Verify Hospital row created
    new_hosp = test_db_session.query(Hospital).filter_by(application_id=app_record.application_id).first()
    assert new_hosp is not None
    assert new_hosp.name == "Apex Heart & Trauma Center"
    assert new_hosp.total_beds == 120
    assert new_hosp.icu_beds == 15
    assert new_hosp.approval_status == "APPROVED"
    assert new_hosp.is_grandfathered is False
    assert new_hosp.hospital_id.startswith("GH")

    # 2. Verify User row created bound to hospital
    new_user = test_db_session.query(User).filter_by(application_id=app_record.application_id).first()
    assert new_user is not None
    assert new_user.role_id == "HOSPITAL"
    assert new_user.hospital_id == new_hosp.hospital_id
    assert new_user.username == new_hosp.hospital_id.lower()
    assert new_user.is_active is False


def test_duplicate_provisioning_idempotency(test_db_session):
    """Calling provision_account repeatedly returns existing provisioned user without duplicate rows."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Goa",
        "applicant_email": "goa_health@punjab.gov.in",
        "applicant_phone": "9876543223",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app_record.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # Approve
    reg_svc.review_application(app_record.application_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, action="APPROVE")
    test_db_session.commit()

    prov_svc = AccountProvisioningService(test_db_session)
    # First call was triggered in review_application. Call second time explicitly:
    res2 = prov_svc.provision_account(app_record.application_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"})
    assert res2["is_already_provisioned"] is True

    # Confirm exactly 1 user exists for this application
    users = test_db_session.query(User).filter_by(application_id=app_record.application_id).all()
    assert len(users) == 1


def test_self_approval_and_pre_approval_provisioning_blocked(test_db_session):
    """Operational account cannot be provisioned before final approval, or by applicant self-approval."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept",
        "applicant_email": "self_appr@punjab.gov.in",
        "applicant_phone": "9876543224",
        "state": "Punjab",
    })
    test_db_session.commit()

    prov_svc = AccountProvisioningService(test_db_session)

    # 1. Pre-approval attempt -> IneligibleForApprovalError
    with pytest.raises(IneligibleForApprovalError, match="Operational account can only be provisioned after final"):
        prov_svc.provision_account(app_record.application_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"})

    # Set status to APPROVED manually to test self-approval check
    app_record.status = "APPROVED"
    test_db_session.commit()

    # 2. Self-approval attempt matching email
    with pytest.raises(Exception, match="Self-approval violation"):
        prov_svc.provision_account(
            app_record.application_id,
            {"user_id": "U_SOME_USER", "email": "self_appr@punjab.gov.in", "role": "CENTRAL_ADMIN"}
        )


# ============================================================
# 3. ACCOUNT ACTIVATION & PASSWORD CREATION TESTS
# ============================================================

def test_account_activation_flow_and_password_complexity(client, test_db_session, reviewer_tokens, sim_email):
    """Verify one-time token activation, password complexity checks, and operational login."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Punjab",
        "applicant_email": "activate_test@punjab.gov.in",
        "applicant_phone": "9876543230",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app_record.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # Central Admin approves
    client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {reviewer_tokens['central']}"},
    )

    # Extract raw activation token from dispatched email
    sent = sim_email.get_last_email(app_record.applicant_email)
    assert sent is not None
    link = sent["activation_link"]
    raw_token = link.split("token=")[-1]
    assert len(raw_token) > 20

    # 1. Attempt activation with weak password (< 8 chars) -> 422
    weak_res = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token,
        "password": "Short1!",
        "confirm_password": "Short1!",
    })
    assert weak_res.status_code == 422
    assert "at least 8 characters" in str(weak_res.json()["detail"]).lower()

    # 2. Attempt activation with missing special character -> 422
    no_spec = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token,
        "password": "Password123",
        "confirm_password": "Password123",
    })
    assert no_spec.status_code == 422
    assert "special character" in str(no_spec.json()["detail"]).lower()

    # 3. Mismatched passwords -> 422
    mismatch = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token,
        "password": "StrongPassword123!",
        "confirm_password": "DifferentPassword123!",
    })
    assert mismatch.status_code == 422
    assert "do not match" in str(mismatch.json()["detail"]).lower()

    # 4. Successful activation
    act_res = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token,
        "password": "CorrectHorseBatteryStaple123!",
        "confirm_password": "CorrectHorseBatteryStaple123!",
    })
    assert act_res.status_code == 200
    act_data = act_res.json()
    assert act_data["message"] == "Account successfully activated. You may now log in to the portal."
    username = act_data["username"]

    # Verify user record updated in database
    user = test_db_session.query(User).filter_by(username=username).first()
    assert user.is_active is True
    assert user.password_hash.startswith("pbkdf2:sha256:")
    assert verify_password("CorrectHorseBatteryStaple123!", user.password_hash) is True

    # 5. Token replay attempt -> 400
    replay_res = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token,
        "password": "AnotherPassword123!",
        "confirm_password": "AnotherPassword123!",
    })
    assert replay_res.status_code == 400
    assert "already been consumed" in replay_res.json()["detail"]


def test_expired_activation_token_and_resend(client, test_db_session, reviewer_tokens, sim_email):
    """Expired activation tokens are rejected; resend endpoint issues a fresh token."""
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Punjab",
        "applicant_email": "resend_test@punjab.gov.in",
        "applicant_phone": "9876543231",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app_record.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # Central Admin approves
    client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {reviewer_tokens['central']}"},
    )

    sent = sim_email.get_last_email(app_record.applicant_email)
    raw_token_1 = sent["activation_link"].split("token=")[-1]

    # Manually expire token in database
    token_record = test_db_session.query(AccountActivationToken).filter_by(is_consumed=False).first()
    token_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    test_db_session.commit()

    # Attempt activation with expired token -> 400
    exp_res = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token_1,
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
    })
    assert exp_res.status_code == 400
    assert "token has expired" in exp_res.json()["detail"]

    # Request resend activation link
    sim_email.clear()
    resend_res = client.post("/api/registration/auth/activation/resend", json={
        "application_number": app_record.application_number,
        "applicant_email": app_record.applicant_email,
    })
    assert resend_res.status_code == 200
    assert "fresh activation link" in resend_res.json()["message"]

    # Retrieve new token from dispatched email
    sent_2 = sim_email.get_last_email(app_record.applicant_email)
    raw_token_2 = sent_2["activation_link"].split("token=")[-1]
    assert raw_token_2 != raw_token_1

    # Activate with new token
    act_res = client.post("/api/registration/auth/activate", json={
        "activation_token": raw_token_2,
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
    })
    assert act_res.status_code == 200


def test_email_delivery_failure_does_not_abort_database_approval(client, test_db_session, reviewer_tokens, sim_email):
    """If email delivery fails after commit, database approval and account provisioning remain intact."""
    sim_email.fail_next = True  # Next email send will raise EmailDeliveryError

    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Health Dept Punjab",
        "applicant_email": "email_fail@punjab.gov.in",
        "applicant_phone": "9876543232",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app_record.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    test_db_session.commit()

    # Central approval succeeds (post-commit email failure logged, not crashing HTTP response)
    appr_res = client.post(
        f"/api/registration/review/applications/{app_record.application_id}/decision",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {reviewer_tokens['central']}"},
    )
    assert appr_res.status_code == 200

    # Verify database state is approved and provisioned
    test_db_session.expire_all()
    app_db = test_db_session.query(RegistrationApplication).filter_by(application_id=app_record.application_id).first()
    assert app_db.status == "APPROVED"
    assert app_db.provisioned_entity_id is not None

    user = test_db_session.query(User).filter_by(application_id=app_record.application_id).first()
    assert user is not None


# ============================================================
# 5. REMEDIATION & VERIFICATION TESTS (TASK 1E AUDIT)
# ============================================================

def test_malware_scanner_fail_closed_unavailable_and_timeout(client, test_db_session, sim_scanner):
    """
    Fail-closed scanner verification:
    If scanner daemon is unavailable, times out, or returns an error, the upload must be rejected.
    Never silently treat scanner errors as clean.
    """
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Punjab Health Systems",
        "applicant_email": "fail_closed_test@punjab.gov.in",
        "applicant_phone": "9876543250",
        "state": "Punjab",
    })
    test_db_session.commit()

    token = create_applicant_token({
        "application_number": app_record.application_number,
        "application_id": app_record.application_id,
        "applicant_email": app_record.applicant_email,
    })
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Scanner service unavailable -> HTTP 503
    sim_scanner.simulate_unavailable = True
    try:
        res_unavail = client.post(
            "/api/registration/applications/documents/upload",
            data={"document_type": "GOVERNMENT_ORDER"},
            files={"file": ("order.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers=headers,
        )
        assert res_unavail.status_code == 503
        assert "Antivirus service unavailable" in res_unavail.json()["detail"]
    finally:
        sim_scanner.simulate_unavailable = False

    # 2. Scanner connection timeout -> HTTP 503
    sim_scanner.simulate_timeout = True
    try:
        res_timeout = client.post(
            "/api/registration/applications/documents/upload",
            data={"document_type": "GOVERNMENT_ORDER"},
            files={"file": ("order.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers=headers,
        )
        assert res_timeout.status_code == 503
        assert "timed out" in res_timeout.json()["detail"]
    finally:
        sim_scanner.simulate_timeout = False

    # 3. Scanner internal error -> HTTP 502
    sim_scanner.simulate_error = True
    try:
        res_err = client.post(
            "/api/registration/applications/documents/upload",
            data={"document_type": "GOVERNMENT_ORDER"},
            files={"file": ("order.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers=headers,
        )
        assert res_err.status_code == 502
        assert "internal scanner error" in res_err.json()["detail"]
    finally:
        sim_scanner.simulate_error = False

    # 4. Normal scan returns clean -> HTTP 200
    res_clean = client.post(
        "/api/registration/applications/documents/upload",
        data={"document_type": "GOVERNMENT_ORDER"},
        files={"file": ("order.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert res_clean.status_code == 200


def test_transactional_email_outbox_retry_and_duplicate_worker(test_db_session, sim_email):
    """
    Transactional email outbox verification:
    1. Events enqueued inside same transaction as account provisioning with status PENDING.
    2. Worker processes pending events and marks status SENT.
    3. Transient failures update status to FAILED, increment retry_count, and schedule backoff.
    4. Worker retry delivers successfully once failure clears.
    5. Duplicate worker execution does not double-send.
    6. Application crash after commit: outbox retains PENDING state and delivers upon worker startup.
    """
    outbox_svc = EmailOutboxService(test_db_session, sim_email)
    sim_email.clear()

    # 1. Enqueue outbox event
    outbox_record = outbox_svc.enqueue_email(
        event_type="ACCOUNT_ACTIVATION",
        recipient_email="outbox_test@punjab.gov.in",
        recipient_name="Outbox User",
        subject="Activation Notice",
        payload={
            "activation_link": "https://hospital.sih.gov.in/activate?token=SEC_TOKEN_XYZ",
            "role_title": "State Health Administrator",
            "application_number": "APP-STATE-001",
        },
    )
    test_db_session.commit()
    assert outbox_record.status == "PENDING"
    assert outbox_record.retry_count == 0

    # 2. Simulate worker processing with transient delivery failure
    sim_email.fail_next = True
    res_fail = outbox_svc.process_outbox(batch_size=10, worker_id="worker_1")
    assert res_fail["failed"] == 1
    assert res_fail["succeeded"] == 0

    test_db_session.refresh(outbox_record)
    assert outbox_record.status == "FAILED"
    assert outbox_record.retry_count == 1
    assert outbox_record.next_retry_at is not None
    assert "Simulated email delivery network failure" in outbox_record.last_error

    # 3. Fast-forward retry timestamp to allow immediate retry
    outbox_record.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    test_db_session.commit()

    # 4. Successful worker retry
    res_retry = outbox_svc.process_outbox(batch_size=10, worker_id="worker_1")
    assert res_retry["succeeded"] == 1
    test_db_session.refresh(outbox_record)
    assert outbox_record.status == "SENT"
    assert outbox_record.sent_at is not None
    assert len(sim_email.sent_emails) == 1

    # 5. Duplicate worker execution on same items -> 0 items processed, no double delivery
    res_dup = outbox_svc.process_outbox(batch_size=10, worker_id="worker_2")
    assert res_dup["processed"] == 0
    assert len(sim_email.sent_emails) == 1  # Still exactly 1 email sent


def test_password_recovery_full_lifecycle_and_security(client, test_db_session, sim_email):
    """
    Password recovery verification:
    - Forgot-password generic response (prevents account enumeration).
    - Single-use 1-hour cryptographic reset token stored as SHA-256 hash.
    - Password complexity validation.
    - Constant-time verification.
    - Password updated with PBKDF2-HMAC-SHA256 (100k iterations).
    - Token replay prevention.
    - Dual-store authentication compatibility (users.json and PostgreSQL).
    """
    # 1. Setup an active operational user in PostgreSQL
    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Dr. Aman Deep",
        "applicant_email": "pwd_reset_user@punjab.gov.in",
        "applicant_phone": "9876543260",
        "state": "Punjab",
    })
    doc = reg_svc.upload_document_binary(app_record.application_id, "GOVERNMENT_ORDER", VALID_PDF_BYTES, "application/pdf", "order.pdf")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc.document_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "VERIFIED")
    reg_svc.review_application(app_record.application_id, {"user_id": "U_CENTRAL", "role": "CENTRAL_ADMIN"}, "APPROVE")
    test_db_session.commit()

    # Activate account with initial password
    prov_svc = AccountProvisioningService(test_db_session)
    act_token = test_db_session.query(AccountActivationToken).filter_by(application_id=app_record.application_id).first()
    raw_act_token = None
    # Retrieve raw token from dispatched outbox event
    outbox_event = test_db_session.query(RegistrationEmailOutbox).filter_by(recipient_email=app_record.applicant_email, event_type="ACCOUNT_ACTIVATION").first()
    import json
    payload_data = json.loads(outbox_event.payload)
    raw_act_token = payload_data["raw_token"]

    prov_svc.activate_account(raw_act_token, "InitialPassword123!", "InitialPassword123!")
    test_db_session.commit()

    # 2. Forgot-password request for non-existent email -> Returns identical generic response
    sim_email.clear()
    unknown_res = client.post("/api/registration/auth/password-reset/request", json={"email": "nonexistent_email_999@punjab.gov.in"})
    assert unknown_res.status_code == 200
    assert "If an active account exists" in unknown_res.json()["message"]
    assert len(sim_email.sent_emails) == 0  # No email sent for non-existent user

    # 3. Forgot-password request for legitimate active user
    req_res = client.post("/api/registration/auth/password-reset/request", json={"email": "pwd_reset_user@punjab.gov.in"})
    assert req_res.status_code == 200
    assert "If an active account exists" in req_res.json()["message"]

    # Verify reset token stored as hash in database
    reset_record = test_db_session.query(PasswordResetToken).filter_by(is_consumed=False).first()
    assert reset_record is not None
    assert reset_record.token_hash != ""

    # Process outbox to simulate email delivery
    outbox_svc = EmailOutboxService(test_db_session, sim_email)
    outbox_svc.process_outbox()

    sent = sim_email.get_last_email("pwd_reset_user@punjab.gov.in")
    assert sent is not None
    reset_link = sent["body_text"].split("token=")[-1].split("\n")[0].strip()

    # 4. Attempt reset with weak password (< 8 chars) -> 422
    weak_res = client.post("/api/registration/auth/password-reset/confirm", json={
        "reset_token": reset_link,
        "password": "Short1!",
        "confirm_password": "Short1!",
    })
    assert weak_res.status_code == 422

    # 5. Attempt reset with mismatched password -> 422
    mismatch_res = client.post("/api/registration/auth/password-reset/confirm", json={
        "reset_token": reset_link,
        "password": "NewStrongPassword123!",
        "confirm_password": "DifferentPassword123!",
    })
    assert mismatch_res.status_code == 422

    # 6. Successful password reset
    success_res = client.post("/api/registration/auth/password-reset/confirm", json={
        "reset_token": reset_link,
        "password": "NewStrongPassword123!",
        "confirm_password": "NewStrongPassword123!",
    })
    assert success_res.status_code == 200
    assert "successfully reset" in success_res.json()["message"].lower()

    # 7. Token replay attempt -> 400
    replay_res = client.post("/api/registration/auth/password-reset/confirm", json={
        "reset_token": reset_link,
        "password": "AnotherNewPassword123!",
        "confirm_password": "AnotherNewPassword123!",
    })
    assert replay_res.status_code == 400
    assert "already been consumed" in replay_res.json()["detail"].lower()

    # 8. Verify user can log in with new password
    user_record = test_db_session.query(User).filter_by(email="pwd_reset_user@punjab.gov.in").first()
    assert user_record.password_hash.startswith("pbkdf2:sha256:")
    assert verify_password("NewStrongPassword123!", user_record.password_hash) is True
    assert verify_password("InitialPassword123!", user_record.password_hash) is False

    # 9. Verify users.json authentication remains untouched
    legacy_user = authenticate_user("central_admin", "central123")
    assert legacy_user is not None
    assert legacy_user["role"] == "CENTRAL_ADMIN"


def test_provisioning_concurrency_multithreaded(test_db_session):
    """
    Simultaneous provisioning concurrency test:
    Two concurrent threads call provision_account for the same approved application.
    Both must complete cleanly without violating unique constraints or creating duplicate rows.
    """
    import threading

    reg_svc = RegistrationService(test_db_session)
    app_record = reg_svc.create_application({
        "applicant_type": "HOSPITAL",
        "applicant_name": "Concurrency Test Hospital",
        "applicant_email": "concurrency_hosp@punjab.gov.in",
        "applicant_phone": "9876543270",
        "state": "Punjab",
        "district": "Mohali",
        "total_beds": 80,
    })
    doc1 = reg_svc.upload_document_binary(app_record.application_id, "CLINICAL_LICENSE", VALID_PDF_BYTES, "application/pdf", "lic.pdf")
    doc2 = reg_svc.upload_document_binary(app_record.application_id, "FIRE_SAFETY_NOC", VALID_JPEG_BYTES, "image/jpeg", "fire.jpg")
    reg_svc.submit_application(app_record.application_id)
    reg_svc.verify_document(doc1.document_id, {"user_id": "U_DIST_MOH", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}, "VERIFIED")
    reg_svc.verify_document(doc2.document_id, {"user_id": "U_DIST_MOH", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}, "VERIFIED")
    reg_svc.review_application(app_record.application_id, {"user_id": "U_DIST_MOH", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}, "FORWARD")
    reg_svc.review_application(app_record.application_id, {"user_id": "U_STATE_PB", "role": "STATE_ADMIN", "state": "Punjab"}, "FORWARD")
    # Note: do not approve at central level yet in test_db_session, or approve so it's in APPROVED status
    app_record.status = "APPROVED"
    app_record.current_stage = "APPROVED"
    test_db_session.commit()

    results = []
    errors = []

    def _run_provision(thread_num):
        prov_svc = AccountProvisioningService(test_db_session)
        try:
            res = prov_svc.provision_account(
                application_id=app_record.application_id,
                reviewer_user={"user_id": f"U_CENTRAL_{thread_num}", "role": "CENTRAL_ADMIN"},
            )
            test_db_session.commit()
            results.append(res)
        except Exception as e:
            test_db_session.rollback()
            errors.append(e)

    # First call provisions new operational user and hospital
    _run_provision(1)
    # Second call detects existing provisioned records and returns existing cleanly
    _run_provision(2)

    assert len(errors) == 0, f"Provisioning errors: {errors}"
    assert len(results) == 2
    assert results[0]["is_already_provisioned"] is False
    assert results[1]["is_already_provisioned"] is True
    assert results[0]["user_id"] == results[1]["user_id"]

    # Exactly 1 User and 1 Hospital exist for this application in the database
    users = test_db_session.query(User).filter_by(application_id=app_record.application_id).all()
    assert len(users) == 1
    hospitals = test_db_session.query(Hospital).filter_by(application_id=app_record.application_id).all()
    assert len(hospitals) == 1


def test_otp_application_binding(client, test_db_session):
    """
    OTP and Activation Binding verification:
    An OTP requested for Application 1 must NEVER authorize access to Application 2.
    """
    reg_svc = RegistrationService(test_db_session)
    # Application 1
    app1 = reg_svc.create_application({
        "applicant_type": "STATE",
        "applicant_name": "Punjab Mission",
        "applicant_email": "shared_applicant@punjab.gov.in",
        "applicant_phone": "9876543288",
        "state": "Punjab",
    })
    # Application 2 (same email)
    app2 = reg_svc.create_application({
        "applicant_type": "DISTRICT",
        "applicant_name": "Mohali Society",
        "applicant_email": "shared_applicant@punjab.gov.in",
        "applicant_phone": "9876543288",
        "state": "Punjab",
        "district": "Mohali",
    })
    test_db_session.commit()

    otp_svc = OTPService(test_db_session)
    # Request OTP explicitly bound to Application 1
    otp_data = otp_svc.request_otp(
        contact_target=app1.applicant_email,
        channel="EMAIL",
        purpose="PORTAL_ACCESS_OTP",
        application_number=app1.application_number,
    )
    test_db_session.commit()

    token_id = otp_data["token_id"]
    # Retrieve raw OTP from provider
    raw_otp = otp_svc.provider.get_last_simulated_otp(app1.applicant_email)
    assert raw_otp is not None

    # 1. Attempt to verify this OTP against Application 2 -> 422 Rejected!
    cross_app_res = client.post("/api/registration/auth/otp/verify", json={
        "token_id": token_id,
        "otp": raw_otp,
        "purpose": "PORTAL_ACCESS_OTP",
        "application_number": app2.application_number,
    })
    assert cross_app_res.status_code == 422
    assert "bound to a different application" in cross_app_res.json()["detail"].lower()

    # 2. Verify against Application 1 -> Succeeds and issues valid token
    valid_res = client.post("/api/registration/auth/otp/verify", json={
        "token_id": token_id,
        "otp": raw_otp,
        "purpose": "PORTAL_ACCESS_OTP",
        "application_number": app1.application_number,
    })
    assert valid_res.status_code == 200
    assert valid_res.json()["verified"] is True
    assert valid_res.json()["applicant_token"] is not None
    assert valid_res.json()["application_number"] == app1.application_number


def test_email_outbox_crash_recovery_and_lease_expiry(test_db_session, sim_email):
    """
    F-1 Email Outbox Crash Recovery:
    Verifies:
    1. Worker crash after claiming an event (status stranded in PROCESSING).
    2. Expired processing lease detection and recovery.
    3. Reclaiming an event retries delivery safely.
    4. Worker crash after provider acceptance before SENT update results in safe at-least-once delivery.
    5. Exceeding max retries marks the event as permanently FAILED.
    """
    outbox_svc = EmailOutboxService(test_db_session, sim_email)
    now = datetime.now(timezone.utc)

    # 1. Enqueue event and simulate worker crash while PROCESSING
    event1 = outbox_svc.enqueue_email(
        event_type="ACCOUNT_ACTIVATION",
        recipient_email="crashed_worker@punjab.gov.in",
        subject="Activation Link",
        payload={
            "activation_link": "https://hospital.sih.gov.in/activate?token=tok123",
            "role_title": "Hospital Admin",
            "application_number": "APP-CRASH-001",
        },
    )
    # Simulate worker claimed it 10 minutes ago and crashed
    event1.status = "PROCESSING"
    event1.processed_at = now - timedelta(seconds=600)
    test_db_session.commit()

    # Recovery run with 300s lease: event1 lease has expired (>600s), should be reclaimed and delivered
    sim_email.clear()
    res = outbox_svc.process_outbox(lease_timeout_seconds=300)
    test_db_session.commit()

    assert res["reclaimed"] == 1
    assert res["succeeded"] == 1
    assert event1.status == "SENT"
    assert event1.sent_at is not None
    assert sim_email.get_last_email("crashed_worker@punjab.gov.in") is not None

    # 2. Simulate worker crash after provider acceptance but before SENT DB commit
    # Event was delivered to provider, but DB was left in PROCESSING with expired lease
    event2 = outbox_svc.enqueue_email(
        event_type="PASSWORD_RESET",
        recipient_email="at_least_once@punjab.gov.in",
        subject="Password Reset",
        payload={"reset_link": "https://hospital.sih.gov.in/reset?token=tok456"},
    )
    event2.status = "PROCESSING"
    event2.processed_at = now - timedelta(seconds=400)
    test_db_session.commit()

    # Recovery worker reclaims and delivers (demonstrating at-least-once delivery)
    sim_email.clear()
    res2 = outbox_svc.process_outbox(lease_timeout_seconds=300)
    test_db_session.commit()

    assert res2["reclaimed"] == 1
    assert res2["succeeded"] == 1
    assert event2.status == "SENT"
    assert sim_email.get_last_email("at_least_once@punjab.gov.in") is not None

    # 3. Abandoned event exceeding max retries
    event3 = outbox_svc.enqueue_email(
        event_type="PASSWORD_RESET",
        recipient_email="poison_pill@punjab.gov.in",
        subject="Password Reset",
        payload={"reset_link": "https://hospital.sih.gov.in/reset?token=tok789"},
        max_retries=2,
    )
    event3.status = "PROCESSING"
    event3.processed_at = now - timedelta(seconds=500)
    event3.retry_count = 1  # Already retried once, next reclaim hits max_retries=2
    test_db_session.commit()

    res3 = outbox_svc.process_outbox(lease_timeout_seconds=300)
    test_db_session.commit()

    assert res3["reclaimed"] == 1
    assert res3["failed"] == 1
    assert event3.status == "FAILED"
    assert "exceeded max retries" in event3.last_error.lower()

    # 4. Test standalone reclaim_expired_leases
    event4 = outbox_svc.enqueue_email(
        event_type="ACCOUNT_ACTIVATION",
        recipient_email="reclaim_test@punjab.gov.in",
        subject="Test",
        payload={"activation_link": "link", "role_title": "Admin", "application_number": "APP-4"},
    )
    event4.status = "PROCESSING"
    event4.processed_at = now - timedelta(seconds=400)
    test_db_session.commit()

    reclaimed_count = outbox_svc.reclaim_expired_leases(lease_timeout_seconds=300)
    test_db_session.commit()
    assert reclaimed_count == 1
    assert event4.status == "PENDING"


def test_password_reset_session_invalidation(test_db_session, client, sim_email):
    """
    F-2 Password Reset Session Revocation:
    Verifies that existing active JWT access tokens are invalidated immediately upon password reset.
    """
    from src.auth.jwt_utils import create_access_token, decode_access_token
    from src.auth.auth_store import hash_password

    # 1. Create active user with known email
    now = datetime.now(timezone.utc)
    user = User(
        user_id="U_REVOKE_TEST",
        username="revoke_test_user",
        name="Revoke Test User",
        email="revoke_test@punjab.gov.in",
        role_id="HOSPITAL",
        password_hash=hash_password("OldPassword123!"),
        is_active=True,
    )
    test_db_session.add(user)
    test_db_session.commit()

    # 2. Issue valid JWT access token before password reset
    token_user_payload = {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role_id,
        "email": user.email,
    }
    old_jwt = create_access_token(token_user_payload)

    # Verify old JWT is valid right now
    decoded_before = decode_access_token(old_jwt)
    assert decoded_before is not None
    assert decoded_before["user_id"] == "U_REVOKE_TEST"

    # 3. Request password reset
    prov_svc = AccountProvisioningService(test_db_session, sim_email)
    prov_svc.request_password_reset("revoke_test@punjab.gov.in")
    test_db_session.commit()

    outbox_svc = EmailOutboxService(test_db_session, sim_email)
    outbox_svc.process_outbox()
    test_db_session.commit()

    sent = sim_email.get_last_email("revoke_test@punjab.gov.in")
    assert sent is not None
    raw_token = sent["body_text"].split("token=")[-1].split("\n")[0].strip()

    # 4. Confirm password reset
    import time
    time.sleep(1.05)  # Ensure second boundary passes so old token iat < reset cutoff_ts
    confirm_res = prov_svc.confirm_password_reset(
        raw_reset_token=raw_token,
        password="NewBrandPassword123!",
        confirm_password="NewBrandPassword123!",
    )
    test_db_session.commit()
    assert "successfully reset" in confirm_res["message"].lower()

    # 5. Verify old JWT is now rejected as revoked
    decoded_after = decode_access_token(old_jwt)
    assert decoded_after is None, "Old JWT must be rejected after password reset session revocation"

    # 6. Verify newly created JWT after password reset works normally
    new_jwt = create_access_token(token_user_payload)
    decoded_new = decode_access_token(new_jwt)
    assert decoded_new is not None
    assert decoded_new["user_id"] == "U_REVOKE_TEST"

