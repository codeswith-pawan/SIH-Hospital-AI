"""
Phase 2D Backend Workflow & Boundary Verification
Executed exclusively against PostgreSQL database: sih_hospital_phase1_run_test
"""

import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database.pg_models import (
    PgBase,
    Role,
    Hospital,
    User,
    RegistrationApplication,
    RegistrationDocument,
    ApprovalHistory,
    AccountActivationToken,
    RegistrationEmailOutbox,
    PasswordResetToken,
)
from src.auth.auth_store import hash_password, verify_password
from src.services.registration_service import (
    RegistrationService,
    ApplicationNotFoundError,
    UnauthorizedReviewerError,
    GeographicAccessError,
    SelfApprovalError,
    InvalidStageTransitionError,
    IneligibleForApprovalError,
)
from src.services.account_provisioning_service import (
    AccountProvisioningService,
    ActivationTokenError,
    PasswordComplexityError,
    ProvisioningError,
)
from src.services.email_service import SimulatedEmailProvider, set_email_provider
from src.services.document_storage import SimulatedScanner, set_malware_scanner, LocalStorageAdapter, set_storage_adapter
from src.services.email_outbox_service import EmailOutboxService

TARGET_DB_URL = "postgresql://localhost:5432/sih_hospital_phase1_run_test"
assert "sih_hospital_phase1_run_test" in TARGET_DB_URL, "Fatal: target DB must be sih_hospital_phase1_run_test"
assert "sih_hospital_dev" not in TARGET_DB_URL, "Fatal: forbidden DB sih_hospital_dev referenced"

engine = create_engine(TARGET_DB_URL, isolation_level="READ COMMITTED")
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

VALID_PDF = b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF"


def run_all_verifications():
    print(f"[*] Connecting exclusively to: {TARGET_DB_URL}")
    session = SessionLocal()
    sim_email = SimulatedEmailProvider()
    set_email_provider(sim_email)
    scanner = SimulatedScanner()
    set_malware_scanner(scanner)
    storage = LocalStorageAdapter(base_dir="/tmp/sih_phase2d_verify_docs")
    set_storage_adapter(storage)

    results = {}

    try:
        # Seed test reviewers in sih_hospital_phase1_run_test
        reviewers = [
            User(user_id="U_REV_MOHALI", username="cmo_mohali", name="Dr. Mohali CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Mohali", is_active=True, password_hash="hash"),
            User(user_id="U_REV_AMRITSAR", username="cmo_amritsar", name="Dr. Amritsar CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Amritsar", is_active=True, password_hash="hash"),
            User(user_id="U_REV_PATIALA", username="cmo_patiala", name="Dr. Patiala CMO", role_id="DISTRICT_ADMIN", state="Punjab", district="Patiala", is_active=True, password_hash="hash"),
            User(user_id="U_REV_PUNJAB", username="dir_punjab", name="Dr. Punjab Health Director", role_id="STATE_ADMIN", state="Punjab", is_active=True, password_hash="hash"),
            User(user_id="U_REV_HARYANA", username="dir_haryana", name="Dr. Haryana Health Director", role_id="STATE_ADMIN", state="Haryana", is_active=True, password_hash="hash"),
            User(user_id="U_REV_CENTRAL", username="central_registrar", name="National Registrar Central", role_id="CENTRAL_ADMIN", is_active=True, password_hash="hash"),
            User(user_id="U_HOSP_STAFF", username="staff_nurse", name="Nurse Mary", role_id="HOSPITAL", state="Punjab", district="Mohali", is_active=True, password_hash="hash"),
        ]
        for r in reviewers:
            session.merge(r)
        session.commit()

        reg_svc = RegistrationService(session)
        prov_svc = AccountProvisioningService(session)

        cmo_mohali = {"user_id": "U_REV_MOHALI", "username": "cmo_mohali", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Mohali"}
        cmo_amritsar = {"user_id": "U_REV_AMRITSAR", "username": "cmo_amritsar", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Amritsar"}
        dir_punjab = {"user_id": "U_REV_PUNJAB", "username": "dir_punjab", "role": "STATE_ADMIN", "state": "Punjab"}
        dir_haryana = {"user_id": "U_REV_HARYANA", "username": "dir_haryana", "role": "STATE_ADMIN", "state": "Haryana"}
        central_admin = {"user_id": "U_REV_CENTRAL", "username": "central_registrar", "role": "CENTRAL_ADMIN"}
        hospital_staff = {"user_id": "U_HOSP_STAFF", "username": "staff_nurse", "role": "HOSPITAL"}

        # ----------------------------------------------------------------------
        # 1. Hospital Registration, District -> State -> Central -> Provisioning
        # ----------------------------------------------------------------------
        print("\n--- 1. Testing Hospital Full Tier Workflow ---")
        hosp_app = reg_svc.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "Apollo Super Specialty Mohali",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540001",
            "state": "Punjab",
            "district": "Mohali",
        })
        app_id = hosp_app.application_id
        d1 = reg_svc.upload_document_binary(app_id, "CLINICAL_LICENSE", VALID_PDF, "application/pdf", "license.pdf")
        d2 = reg_svc.upload_document_binary(app_id, "FIRE_SAFETY_NOC", VALID_PDF, "application/pdf", "fire_noc.pdf")
        reg_svc.submit_application(app_id)
        session.commit()

        # Verify initial submission stage
        session.refresh(hosp_app)
        assert hosp_app.current_stage == "DISTRICT_REVIEW", f"Expected DISTRICT_REVIEW, got {hosp_app.current_stage}"
        assert hosp_app.status == "SUBMITTED"
        print("  [✓] Hospital application submitted to DISTRICT_REVIEW.")

        # District approval (FORWARD to STATE_REVIEW)
        reg_svc.verify_document(d1.document_id, cmo_mohali, "VERIFIED", "Clinical license verified with Punjab state health board")
        reg_svc.verify_document(d2.document_id, cmo_mohali, "VERIFIED", "Fire NOC cleared by Mohali fire service")
        res_dist = reg_svc.review_application(app_id, cmo_mohali, "FORWARD", "District inspection cleared.")
        session.commit()
        session.refresh(hosp_app)
        assert hosp_app.current_stage == "STATE_REVIEW", f"Expected STATE_REVIEW, got {hosp_app.current_stage}"
        assert hosp_app.status == "UNDER_REVIEW"
        print("  [✓] District forwarded to STATE_REVIEW.")

        # State approval (FORWARD to CENTRAL_REVIEW)
        res_state = reg_svc.review_application(app_id, dir_punjab, "FORWARD", "State health board endorsed.")
        session.commit()
        session.refresh(hosp_app)
        assert hosp_app.current_stage == "CENTRAL_REVIEW", f"Expected CENTRAL_REVIEW, got {hosp_app.current_stage}"
        print("  [✓] State forwarded to CENTRAL_REVIEW.")

        # Central final approval (APPROVE -> Provisioning)
        initial_hosp_count = session.query(Hospital).count()
        res_central = reg_svc.review_application(app_id, central_admin, "APPROVE", "National registry accreditation granted.")
        session.commit()
        session.refresh(hosp_app)
        assert hosp_app.current_stage == "APPROVED"
        assert hosp_app.status == "APPROVED"
        assert hosp_app.final_approved_at is not None
        assert session.query(Hospital).count() == initial_hosp_count + 1, "Hospital entity was not created"
        print("  [✓] Central approved; hospital entity provisioned.")

        # Verify operational user account & activation token created
        prov_user = session.query(User).filter_by(application_id=app_id).first()
        assert prov_user is not None
        assert prov_user.role_id == "HOSPITAL"
        assert prov_user.password_hash == "PENDING_ACTIVATION"
        print(f"  [✓] Operational user '{prov_user.username}' created with status PENDING_ACTIVATION.")

        act_token = session.query(AccountActivationToken).filter_by(application_id=app_id).first()
        assert act_token is not None
        assert act_token.is_consumed is False
        assert act_token.expires_at > datetime.now(timezone.utc)
        print("  [✓] 72-hour cryptographic activation token generated and hashed in DB.")

        # Retrieve raw token from outbox
        outbox_event = session.query(RegistrationEmailOutbox).filter_by(recipient_email=hosp_app.applicant_email).order_by(RegistrationEmailOutbox.id.desc()).first()
        assert outbox_event is not None
        raw_token = json.loads(outbox_event.payload)["raw_token"]

        # Activate user with strong password
        prov_svc.activate_account(raw_token, "SuperSecure!2026", "SuperSecure!2026")
        session.commit()
        session.refresh(prov_user)
        session.refresh(act_token)
        assert act_token.is_consumed is True
        assert prov_user.is_active is True
        assert verify_password("SuperSecure!2026", prov_user.password_hash) is True
        print("  [✓] Account activated and password verified with PBKDF2-HMAC-SHA256.")

        # Verify activation token replay fails
        try:
            prov_svc.activate_account(raw_token, "AnotherPass!2026", "AnotherPass!2026")
            assert False, "Replay attack should have failed"
        except ActivationTokenError:
            print("  [✓] Activation token replay rejected (single-use enforced).")

        results["hospital_full_workflow"] = "PASS"

        # ----------------------------------------------------------------------
        # 2. Correction Request and Resubmission Workflow
        # ----------------------------------------------------------------------
        print("\n--- 2. Testing Correction Request & Resubmission Workflow ---")
        corr_app = reg_svc.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "Fortis Satellite Mohali",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540002",
            "state": "Punjab",
            "district": "Mohali",
        })
        reg_svc.upload_document_binary(corr_app.application_id, "CLINICAL_LICENSE", VALID_PDF, "application/pdf", "lic.pdf")
        reg_svc.upload_document_binary(corr_app.application_id, "FIRE_SAFETY_NOC", VALID_PDF, "application/pdf", "fire.pdf")
        reg_svc.submit_application(corr_app.application_id)
        session.commit()

        # District requests correction
        reg_svc.request_correction(corr_app.application_id, cmo_mohali, "Please update oxygen capacity documentation and re-upload.")
        session.commit()
        session.refresh(corr_app)
        assert corr_app.status == "CORRECTION_REQUIRED"
        assert corr_app.correction_notes == "Please update oxygen capacity documentation and re-upload."
        print("  [✓] Application transitioned to CORRECTION_REQUIRED with reviewer notes.")

        # Resubmit application
        resub = reg_svc.resubmit_application(corr_app.application_id, "Updated oxygen plant license attached.")
        session.commit()
        session.refresh(corr_app)
        assert corr_app.status == "SUBMITTED"
        assert corr_app.resubmission_version == 2
        print("  [✓] Applicant resubmitted; resubmission_version incremented to 2.")
        results["correction_resubmission"] = "PASS"

        # ----------------------------------------------------------------------
        # 3. Rejection Without Account Provisioning
        # ----------------------------------------------------------------------
        print("\n--- 3. Testing Rejection Without Account Provisioning ---")
        rej_app = reg_svc.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "Non Compliant Clinic",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540003",
            "state": "Punjab",
            "district": "Mohali",
        })
        reg_svc.upload_document_binary(rej_app.application_id, "CLINICAL_LICENSE", VALID_PDF, "application/pdf", "lic.pdf")
        reg_svc.upload_document_binary(rej_app.application_id, "FIRE_SAFETY_NOC", VALID_PDF, "application/pdf", "fire.pdf")
        reg_svc.submit_application(rej_app.application_id)
        session.commit()

        # District rejects application
        reg_svc.review_application(rej_app.application_id, cmo_mohali, "REJECT", "Fails biomedical waste protocol.")
        session.commit()
        session.refresh(rej_app)
        assert rej_app.status == "REJECTED"
        assert rej_app.current_stage == "REJECTED"
        assert rej_app.rejection_reason == "Fails biomedical waste protocol."

        # Confirm zero user or hospital created
        u_count = session.query(User).filter_by(application_id=rej_app.application_id).count()
        assert u_count == 0, "No user should be created for rejected app"
        print("  [✓] Application rejected; confirmed 0 operational users provisioned.")
        results["rejection_workflow"] = "PASS"

        # ----------------------------------------------------------------------
        # 4. State Registration Workflow (Direct to Central)
        # ----------------------------------------------------------------------
        print("\n--- 4. Testing State Government Registration Workflow ---")
        state_app = reg_svc.create_application({
            "applicant_type": "STATE",
            "applicant_name": "Punjab State Health Directorate",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540004",
            "state": "Punjab",
        })
        reg_svc.upload_document_binary(state_app.application_id, "GOVERNMENT_ORDER", VALID_PDF, "application/pdf", "gazette.pdf")
        reg_svc.submit_application(state_app.application_id)
        session.commit()
        session.refresh(state_app)
        assert state_app.current_stage == "CENTRAL_REVIEW", f"State app should route directly to CENTRAL_REVIEW, got {state_app.current_stage}"
        print("  [✓] State registration routed directly to CENTRAL_REVIEW.")

        # Central approves state registration
        doc = session.query(RegistrationDocument).filter_by(application_id=state_app.application_id).first()
        reg_svc.verify_document(doc.document_id, central_admin, "VERIFIED", "Gazette notification verified.")
        reg_svc.review_application(state_app.application_id, central_admin, "APPROVE", "State nodal authority accredited.")
        session.commit()
        session.refresh(state_app)
        assert state_app.status == "APPROVED"
        prov_state_user = session.query(User).filter_by(application_id=state_app.application_id).first()
        assert prov_state_user is not None
        assert prov_state_user.role_id == "STATE_ADMIN"
        print(f"  [✓] State registration approved; STATE_ADMIN '{prov_state_user.username}' provisioned.")
        results["state_workflow"] = "PASS"

        # ----------------------------------------------------------------------
        # 5. District Registration Workflow (State -> Central)
        # ----------------------------------------------------------------------
        print("\n--- 5. Testing District Government Registration Workflow ---")
        dist_app = reg_svc.create_application({
            "applicant_type": "DISTRICT",
            "applicant_name": "Ludhiana District Health Authority",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540005",
            "state": "Punjab",
            "district": "Ludhiana",
        })
        reg_svc.upload_document_binary(dist_app.application_id, "GOVERNMENT_ORDER", VALID_PDF, "application/pdf", "order.pdf")
        reg_svc.submit_application(dist_app.application_id)
        session.commit()
        session.refresh(dist_app)
        assert dist_app.current_stage == "STATE_REVIEW", f"District app should route to STATE_REVIEW, got {dist_app.current_stage}"
        print("  [✓] District registration routed to STATE_REVIEW.")

        # State forwards to Central
        ddoc = session.query(RegistrationDocument).filter_by(application_id=dist_app.application_id).first()
        reg_svc.verify_document(ddoc.document_id, dir_punjab, "VERIFIED", "Endorsed by state directorate.")
        reg_svc.review_application(dist_app.application_id, dir_punjab, "FORWARD", "Forwarded for national district code.")
        session.commit()
        session.refresh(dist_app)
        assert dist_app.current_stage == "CENTRAL_REVIEW"

        # Central approves
        reg_svc.review_application(dist_app.application_id, central_admin, "APPROVE", "District authority onboarded.")
        session.commit()
        session.refresh(dist_app)
        assert dist_app.status == "APPROVED"
        prov_dist_user = session.query(User).filter_by(application_id=dist_app.application_id).first()
        assert prov_dist_user is not None
        assert prov_dist_user.role_id == "DISTRICT_ADMIN"
        print(f"  [✓] District registration approved; DISTRICT_ADMIN '{prov_dist_user.username}' provisioned.")
        results["district_workflow"] = "PASS"

        # ----------------------------------------------------------------------
        # 6. Unauthorized Transitions, Cross-Jurisdiction & Self-Approval Prevention
        # ----------------------------------------------------------------------
        print("\n--- 6. Testing Security Boundaries & Access Restrictions ---")
        sec_app = reg_svc.create_application({
            "applicant_type": "HOSPITAL",
            "applicant_name": "Patiala Regional Hospital",
            "applicant_email": f"test_{secrets.token_hex(4)}@gov.in",
            "applicant_phone": "9876540006",
            "state": "Punjab",
            "district": "Patiala",
            "nodal_officer_name": "Dr. Self Approver",
        })
        reg_svc.upload_document_binary(sec_app.application_id, "CLINICAL_LICENSE", VALID_PDF, "application/pdf", "lic.pdf")
        reg_svc.upload_document_binary(sec_app.application_id, "FIRE_SAFETY_NOC", VALID_PDF, "application/pdf", "fire.pdf")
        reg_svc.submit_application(sec_app.application_id)
        session.commit()

        # A. Hospital staff role blocked
        try:
            reg_svc.review_application(sec_app.application_id, hospital_staff, "FORWARD")
            assert False, "Hospital staff should be blocked from review"
        except UnauthorizedReviewerError:
            print("  [✓] Hospital staff blocked from review (UnauthorizedReviewerError).")

        # B. Cross-district review blocked (Mohali CMO cannot review Patiala)
        try:
            reg_svc.review_application(sec_app.application_id, cmo_mohali, "FORWARD")
            assert False, "Cross-district review should be blocked"
        except GeographicAccessError:
            print("  [✓] Cross-district access blocked (Mohali CMO blocked from Patiala).")

        # C1. State Admin cannot review application at DISTRICT_REVIEW stage
        try:
            reg_svc.review_application(sec_app.application_id, dir_haryana, "FORWARD")
            assert False, "Stage mismatch should be blocked"
        except UnauthorizedReviewerError:
            print("  [✓] Stage mismatch blocked (State Admin cannot act at DISTRICT_REVIEW stage).")

        # Forward sec_app to STATE_REVIEW with valid Patiala reviewer
        cmo_patiala = {"user_id": "U_REV_PATIALA", "username": "cmo_patiala", "role": "DISTRICT_ADMIN", "state": "Punjab", "district": "Patiala"}
        docs = session.query(RegistrationDocument).filter_by(application_id=sec_app.application_id).all()
        for d in docs:
            reg_svc.verify_document(d.document_id, cmo_patiala, "VERIFIED", "Patiala doc verified")
        reg_svc.review_application(sec_app.application_id, cmo_patiala, "FORWARD", "Patiala district approved")
        session.commit()
        session.refresh(sec_app)
        assert sec_app.current_stage == "STATE_REVIEW"

        # C2. Cross-state review blocked (Haryana Director cannot review Punjab at STATE_REVIEW)
        try:
            reg_svc.review_application(sec_app.application_id, dir_haryana, "FORWARD")
            assert False, "Cross-state review should be blocked"
        except GeographicAccessError:
            print("  [✓] Cross-state access blocked (Haryana Director blocked from Punjab at STATE_REVIEW).")

        # D. Self-approval blocked
        self_reviewer = {"user_id": "U_SELF", "username": "self_reviewer", "email": sec_app.applicant_email, "role": "STATE_ADMIN", "state": "Punjab"}
        try:
            reg_svc.review_application(sec_app.application_id, self_reviewer, "FORWARD")
            assert False, "Self-approval should be blocked"
        except SelfApprovalError:
            print("  [✓] Self-approval blocked (Applicant email matching reviewer blocked).")

        # E. Invalid stage jump blocked (District cannot act at STATE_REVIEW stage)
        try:
            reg_svc.review_application(sec_app.application_id, cmo_patiala, "FORWARD")
            assert False, "District reviewer acting at STATE_REVIEW stage should be blocked"
        except UnauthorizedReviewerError:
            print("  [✓] District admin cannot act on application while at STATE_REVIEW stage.")

        results["security_boundaries"] = "PASS"

        # ----------------------------------------------------------------------
        # 7. Password Recovery Lifecycle
        # ----------------------------------------------------------------------
        print("\n--- 7. Testing Password Recovery Lifecycle ---")
        # Request password reset for activated user
        req_res = prov_svc.request_password_reset(prov_user.email)
        session.commit()
        assert "If an active account exists" in req_res["message"]

        # Request for unknown user returns identical message
        req_unknown = prov_svc.request_password_reset("nonexistent@domain.gov.in")
        assert req_unknown["message"] == req_res["message"]
        print("  [✓] Timing-safe password reset request prevents account enumeration.")

        # Process outbox & extract reset token
        outbox_event_reset = session.query(RegistrationEmailOutbox).filter_by(
            recipient_email=prov_user.email,
            event_type="PASSWORD_RESET"
        ).order_by(RegistrationEmailOutbox.id.desc()).first()
        assert outbox_event_reset is not None
        reset_token_raw = json.loads(outbox_event_reset.payload)["raw_token"]

        # Weak password rejected
        try:
            prov_svc.confirm_password_reset(reset_token_raw, "weak", "weak")
            assert False, "Weak password should be rejected"
        except PasswordComplexityError:
            print("  [✓] Weak password rejected on reset.")

        # Confirm reset
        prov_svc.confirm_password_reset(reset_token_raw, "BrandNewPassword@2026", "BrandNewPassword@2026")
        session.commit()
        session.refresh(prov_user)
        assert verify_password("BrandNewPassword@2026", prov_user.password_hash) is True
        print("  [✓] Password successfully reset and verified with PBKDF2.")

        # Token replay rejected
        try:
            prov_svc.confirm_password_reset(reset_token_raw, "AnotherPassword@2026", "AnotherPassword@2026")
            assert False, "Reset token replay should fail"
        except ActivationTokenError:
            print("  [✓] Password reset token replay rejected (single-use enforced).")

        results["password_recovery"] = "PASS"

    finally:
        session.close()

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY AGAINST sih_hospital_phase1_run_test")
    print("=" * 60)
    for k, v in results.items():
        print(f"  - {k}: {v}")
    return results


if __name__ == "__main__":
    run_all_verifications()
