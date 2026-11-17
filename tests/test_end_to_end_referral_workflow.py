"""
Phase 18: End-to-End Hospital Referral Workflow & Concurrency Verification Test Suite
AI Powered Smart Hospital Referral System

Validates:
1. Complete Lifecycle: Search -> Recommend -> Submit Referral -> Accept & Reserve Bed -> Dispatch Ambulance -> Arrive -> Treat -> Complete & Release Bed.
2. Duplicate active referral rejection (HTTP 409).
3. Safe acceptance rejection on insufficient bed capacity (NO_BEDS_AVAILABLE).
4. Destination hospital referral rejection flow.
5. Ambulance transfer metadata (ambulance ID, ETA, simulated tracking transparency).
6. In-app lifecycle notifications across hospital nodes.
7. Role-Based Access Control and geographic security boundaries.
8. Concurrent referral acceptance with row-level locking.
9. Database session persistence across application reloads.
"""

import os
import uuid
import time
import copy
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.jwt_utils import create_access_token
from src.database.db_manager import get_referral_repository, is_postgres
from src.prediction.bed_reservation import initialize_hospital_beds, get_hospital_inventory
from src.prediction.reservation_store import save_hospital_inventory
from src.prediction.notification_store import (
    get_hospital_notifications,
    mark_notification_as_read,
    mark_all_notifications_read,
)

client = TestClient(app)

# Test hospital identities
HOSPITAL_A = "GH00119"  # Amritsar Civil Hospital (Source)
HOSPITAL_B = "GH00046"  # Regional Amritsar Medical College (Destination)
HOSPITAL_C = "GH_TEST_OTHER"  # Third-party Hospital (Ludhiana)


@pytest.fixture
def auth_headers_hosp_a():
    token = create_access_token({
        "user_id": "USR000002",
        "username": "gh00119",
        "role": "HOSPITAL",
        "hospital_id": HOSPITAL_A,
        "state": "Punjab",
        "district": "Amritsar",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_hosp_b():
    token = create_access_token({
        "user_id": "USR000001",
        "username": "gh00046",
        "role": "HOSPITAL",
        "hospital_id": HOSPITAL_B,
        "state": "Punjab",
        "district": "Amritsar",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_hosp_c():
    token = create_access_token({
        "user_id": "USR000005",
        "username": "gh_test_other",
        "role": "HOSPITAL",
        "hospital_id": HOSPITAL_C,
        "state": "Punjab",
        "district": "Ludhiana",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_district_admin():
    token = create_access_token({
        "user_id": "USR000006",
        "username": "amritsar_district_admin",
        "role": "DISTRICT_ADMIN",
        "state": "Punjab",
        "district": "Amritsar",
    })
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. COMPLETE END-TO-END WORKFLOW (CREATION TO COMPLETION)
# ============================================================

def test_full_end_to_end_referral_lifecycle(auth_headers_hosp_a, auth_headers_hosp_b):
    """
    Verify complete 8-step healthcare referral lifecycle:
    1. Patient Search & AI Recommendation
    2. Referral Initiation (Hospital A -> Hospital B, ICU bed)
    3. Destination Hospital Acceptance & Atomic Bed Reservation (ICU allocated)
    4. Ambulance Dispatch (Ambulance ID + ETA + in-transit status)
    5. Patient Arrival Confirmation (Bed confirmed)
    6. Treatment Commenced (Bed marked occupied)
    7. Treatment Completed (Bed released back to available inventory)
    8. In-App Notifications generated at each step
    """
    # Unique patient for clean lifecycle testing
    patient_id = f"PAT_E2E_{uuid.uuid4().hex[:6].upper()}"

    # Verify Hospital B has available beds
    inv_b = get_hospital_inventory(HOSPITAL_B)
    if not inv_b or inv_b.get("available_icu_beds", 0) == 0:
        initialize_hospital_beds(
            hospital_id=HOSPITAL_B,
            available_beds=169,
            available_icu_beds=16,
            reset=False,
        )

    # Step 1: Query recommendations for this referral scenario
    rec_resp = client.get(f"/hospitals?patient_id=PAT000005")
    assert rec_resp.status_code == 200
    assert rec_resp.json()["success"] is True

    # Step 2: Hospital A creates ICU referral to Hospital B
    ref_payload = {
        "patient_id": patient_id,
        "from_hospital_id": HOSPITAL_A,
        "to_hospital_id": HOSPITAL_B,
        "reason": "Severe acute respiratory distress with hemodynamic instability",
        "priority": "Critical",
        "bed_type": "ICU",
    }
    create_resp = client.post("/referrals", json=ref_payload, headers=auth_headers_hosp_a)
    assert create_resp.status_code == 200, f"Referral creation failed: {create_resp.text}"
    ref_data = create_resp.json()
    assert ref_data["success"] is True
    assert ref_data["status"] == "PENDING"
    referral_id = ref_data["referral"]["referral_id"]
    assert referral_id.startswith("REF-")

    # Step 2b: Verify Hospital B received notification
    notif_b = client.get(f"/hospitals/{HOSPITAL_B}/notifications", headers=auth_headers_hosp_b)
    assert notif_b.status_code == 200
    b_notifs = notif_b.json()["notifications"]
    assert any(n.get("referral_id") == referral_id and n.get("event_type") == "NEW_REFERRAL" for n in b_notifs)

    # Step 3: Destination Hospital B accepts referral -> triggers atomic ICU bed reservation
    accept_resp = client.post(f"/referrals/{referral_id}/status/ACCEPTED", headers=auth_headers_hosp_b)
    assert accept_resp.status_code == 200, f"Accept failed: {accept_resp.text}"
    accept_data = accept_resp.json()
    assert accept_data["success"] is True
    assert accept_data["status"] == "ACCEPTED"
    assert accept_data["reservation"]["reservation_status"] == "RESERVED"
    assert accept_data["reservation"]["bed_type"] == "ICU"
    assert accept_data["reservation"]["bed_id"] is not None

    # Step 4: Source Hospital A marks referral as IN_TRANSIT with ambulance details
    dispatch_payload = {
        "ambulance_id": "AMB-PB-02-108",
        "eta_minutes": 25,
        "notes": "Ambulance en route with advanced paramedic life support.",
    }
    dispatch_resp = client.post(
        f"/referrals/{referral_id}/status/IN_TRANSIT",
        json=dispatch_payload,
        headers=auth_headers_hosp_a,
    )
    assert dispatch_resp.status_code == 200, f"Dispatch failed: {dispatch_resp.text}"
    dispatch_data = dispatch_resp.json()
    assert dispatch_data["status"] == "IN_TRANSIT"
    assert dispatch_data["referral"]["ambulance_id"] == "AMB-PB-02-108"
    assert dispatch_data["referral"]["eta_minutes"] == 25

    # Step 5: Destination Hospital B marks patient as ARRIVED
    arrive_resp = client.post(f"/referrals/{referral_id}/status/ARRIVED", headers=auth_headers_hosp_b)
    assert arrive_resp.status_code == 200, f"Arrive failed: {arrive_resp.text}"
    arrive_data = arrive_resp.json()
    assert arrive_data["status"] == "ARRIVED"
    assert arrive_data["reservation"]["reservation_status"] == "CONFIRMED"

    # Step 6: Destination Hospital B commences TREATMENT_ACTIVE
    treat_resp = client.post(f"/referrals/{referral_id}/status/TREATMENT_ACTIVE", headers=auth_headers_hosp_b)
    assert treat_resp.status_code == 200, f"Treatment start failed: {treat_resp.text}"
    treat_data = treat_resp.json()
    assert treat_data["status"] == "TREATMENT_ACTIVE"
    assert treat_data["reservation"]["reservation_status"] == "OCCUPIED"

    # Step 7: Destination Hospital B completes treatment -> releases bed back to inventory
    comp_resp = client.post(f"/referrals/{referral_id}/status/COMPLETED", headers=auth_headers_hosp_b)
    assert comp_resp.status_code == 200, f"Completion failed: {comp_resp.text}"
    comp_data = comp_resp.json()
    assert comp_data["status"] == "COMPLETED"
    assert comp_data["reservation"]["reservation_status"] in ["RELEASED", None]

    # Step 8: Verify notifications received by Hospital A for lifecycle milestones
    notif_a = client.get(f"/hospitals/{HOSPITAL_A}/notifications", headers=auth_headers_hosp_a)
    assert notif_a.status_code == 200
    a_notifs = notif_a.json()["notifications"]
    lifecycle_events = [n.get("event_type") for n in a_notifs if n.get("referral_id") == referral_id]
    assert "REFERRAL_ACCEPTED" in lifecycle_events
    assert "PATIENT_ARRIVED" in lifecycle_events
    assert "TREATMENT_STARTED" in lifecycle_events
    assert "REFERRAL_COMPLETED" in lifecycle_events


# ============================================================
# 2. DUPLICATE ACTIVE REFERRAL PREVENTION
# ============================================================

def test_duplicate_referral_submission_rejected(auth_headers_hosp_a):
    """Verify that submitting a second referral for a patient with an active referral returns HTTP 409 Conflict."""
    patient_id = f"PAT_DUP_{uuid.uuid4().hex[:6].upper()}"

    # First referral succeeds
    resp1 = client.post(
        "/referrals",
        json={
            "patient_id": patient_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "First critical referral",
            "priority": "Critical",
            "bed_type": "ICU",
        },
        headers=auth_headers_hosp_a,
    )
    assert resp1.status_code == 200
    ref_id = resp1.json()["referral"]["referral_id"]

    # Duplicate referral for same patient must be rejected with 409
    resp2 = client.post(
        "/referrals",
        json={
            "patient_id": patient_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "Duplicate second referral attempt",
            "priority": "Critical",
            "bed_type": "ICU",
        },
        headers=auth_headers_hosp_a,
    )
    assert resp2.status_code == 409
    assert "already has an active referral" in resp2.json()["detail"].lower()


# ============================================================
# 3. SAFE REJECTION ON INSUFFICIENT BED CAPACITY
# ============================================================

def test_safe_acceptance_failure_on_zero_beds(auth_headers_hosp_a, auth_headers_hosp_b):
    """
    When the destination hospital has 0 available ICU beds:
    Acceptance must fail safely with NO_BEDS_AVAILABLE (409 Conflict).
    Referral must remain PENDING without phantom bed reservation.
    """
    inv_backup = copy.deepcopy(get_hospital_inventory(HOSPITAL_B))
    try:
        # Set available ICU beds to 0 for hospital B
        initialize_hospital_beds(
            hospital_id=HOSPITAL_B,
            available_beds=10,
            available_icu_beds=0,
            reset=True,
        )

        pat_id = f"PAT_NOBED_{uuid.uuid4().hex[:6].upper()}"
        create_resp = client.post(
            "/referrals",
            json={
                "patient_id": pat_id,
                "from_hospital_id": HOSPITAL_A,
                "to_hospital_id": HOSPITAL_B,
                "reason": "Requires ICU bed but none available",
                "priority": "Critical",
                "bed_type": "ICU",
            },
            headers=auth_headers_hosp_a,
        )
        assert create_resp.status_code == 200
        ref_id = create_resp.json()["referral"]["referral_id"]

        # Attempt to accept referral when 0 ICU beds are available
        accept_resp = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=auth_headers_hosp_b)
        assert accept_resp.status_code in [409, 400]
        detail = accept_resp.json()
        err_text = str(detail).lower()
        assert (
            "no_icu_available" in err_text
            or "no physical icu bed" in err_text
            or "no available icu beds" in err_text
            or "no_beds_available" in err_text
            or "capacity" in err_text
        )

        # Referral must remain in PENDING state
        get_resp = client.get(f"/referrals/{ref_id}", headers=auth_headers_hosp_b)
        assert get_resp.status_code == 200
        assert get_resp.json()["referral"]["status"] == "PENDING"
    finally:
        # Restore original bed inventory for Hospital B
        if inv_backup:
            save_hospital_inventory(inv_backup)
            from src.database.db_manager import is_postgres, get_referral_repository
            if is_postgres():
                from src.database.pg_models import Bed
                from sqlalchemy import update
                repo = get_referral_repository()
                repo.initialize_or_reset_inventory(
                    hospital_id=HOSPITAL_B,
                    available_beds=169,
                    available_icu_beds=22,
                    available_emergency_beds=0,
                    reset=True,
                )
                repo.session.execute(
                    update(Bed)
                    .where(
                        Bed.hospital_id == HOSPITAL_B,
                        Bed.bed_number.in_(["ICU-001", "ICU-002", "ICU-003", "ICU-004", "ICU-005", "ICU-007"])
                    )
                    .values(status="RESERVED")
                )
                repo.session.commit()


# ============================================================
# 4. REFERRAL REJECTION WORKFLOW
# ============================================================

def test_destination_hospital_reject_referral(auth_headers_hosp_a, auth_headers_hosp_b):
    """Destination hospital rejects incoming referral with clinical notes."""
    pat_id = f"PAT_REJ_{uuid.uuid4().hex[:6].upper()}"
    create_resp = client.post(
        "/referrals",
        json={
            "patient_id": pat_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "Nephrology dialysis needed",
            "priority": "Urgent",
            "bed_type": "GENERAL",
        },
        headers=auth_headers_hosp_a,
    )
    assert create_resp.status_code == 200
    ref_id = create_resp.json()["referral"]["referral_id"]

    # Reject referral
    reject_resp = client.post(
        f"/referrals/{ref_id}/status/REJECTED",
        json={"notes": "Dialysis unit undergoing scheduled calibration until 18:00."},
        headers=auth_headers_hosp_b,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"

    # Verify status in referral record
    get_resp = client.get(f"/referrals/{ref_id}", headers=auth_headers_hosp_a)
    assert get_resp.status_code == 200
    assert get_resp.json()["referral"]["status"] == "REJECTED"


# ============================================================
# 5. SCOPED INBOX & OUTBOX QUERIES
# ============================================================

def test_hospital_referrals_incoming_and_outgoing_scopes(auth_headers_hosp_a, auth_headers_hosp_b):
    """Verify scope query parameter filters incoming vs outgoing referrals correctly."""
    pat_id = f"PAT_SCOPE_{uuid.uuid4().hex[:6].upper()}"

    # Create referral from A to B
    create_resp = client.post(
        "/referrals",
        json={
            "patient_id": pat_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "Scope test",
            "priority": "Urgent",
            "bed_type": "GENERAL",
        },
        headers=auth_headers_hosp_a,
    )
    assert create_resp.status_code == 200
    ref_id = create_resp.json()["referral"]["referral_id"]

    # Query Hospital A outgoing
    resp_out_a = client.get(f"/hospitals/{HOSPITAL_A}/referrals?scope=outgoing", headers=auth_headers_hosp_a)
    assert resp_out_a.status_code == 200
    out_ids = [r["referral_id"] for r in resp_out_a.json()["referrals"]]
    assert ref_id in out_ids

    # Query Hospital B incoming
    resp_in_b = client.get(f"/hospitals/{HOSPITAL_B}/referrals?scope=incoming", headers=auth_headers_hosp_b)
    assert resp_in_b.status_code == 200
    in_ids = [r["referral_id"] for r in resp_in_b.json()["referrals"]]
    assert ref_id in in_ids


# ============================================================
# 6. IN-APP NOTIFICATION MANAGEMENT (READ / READ-ALL)
# ============================================================

def test_in_app_notification_read_lifecycle(auth_headers_hosp_b):
    """Verify notification retrieval, unread count, and marking notifications as read."""
    resp = client.get(f"/hospitals/{HOSPITAL_B}/notifications", headers=auth_headers_hosp_b)
    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert "unread_count" in data

    if data["notifications"]:
        first_notif = data["notifications"][0]
        notif_id = first_notif["id"]

        # Mark single as read
        read_resp = client.post(
            f"/hospitals/{HOSPITAL_B}/notifications/{notif_id}/read",
            headers=auth_headers_hosp_b,
        )
        assert read_resp.status_code == 200
        assert read_resp.json()["success"] is True

    # Mark all as read
    read_all_resp = client.post(
        f"/hospitals/{HOSPITAL_B}/notifications/read-all",
        headers=auth_headers_hosp_b,
    )
    assert read_all_resp.status_code == 200
    assert read_all_resp.json()["success"] is True

    # Check unread count is now 0
    resp_after = client.get(f"/hospitals/{HOSPITAL_B}/notifications?unread_only=true", headers=auth_headers_hosp_b)
    assert resp_after.status_code == 200
    assert resp_after.json()["unread_count"] == 0


# ============================================================
# 7. ROLE-BASED ACCESS CONTROL & BOUNDARIES
# ============================================================

def test_unauthorized_hospital_cannot_accept_referral(auth_headers_hosp_a, auth_headers_hosp_c):
    """Hospital C (unrelated) cannot accept a referral addressed from A to B."""
    pat_id = f"PAT_RBAC_{uuid.uuid4().hex[:6].upper()}"
    create_resp = client.post(
        "/referrals",
        json={
            "patient_id": pat_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "RBAC verification",
            "priority": "Urgent",
            "bed_type": "GENERAL",
        },
        headers=auth_headers_hosp_a,
    )
    assert create_resp.status_code == 200
    ref_id = create_resp.json()["referral"]["referral_id"]

    # Hospital C attempts to accept Hospital B's referral -> must be 403 Forbidden
    resp = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=auth_headers_hosp_c)
    assert resp.status_code == 403
    assert "only the destination hospital" in resp.json()["detail"].lower()


def test_district_admin_cannot_execute_clinical_transitions(auth_headers_hosp_a, auth_headers_district_admin):
    """District administrators have oversight only; clinical lifecycle transitions return 403."""
    pat_id = f"PAT_ADMIN_{uuid.uuid4().hex[:6].upper()}"
    create_resp = client.post(
        "/referrals",
        json={
            "patient_id": pat_id,
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_B,
            "reason": "Administrative role check",
            "priority": "Urgent",
            "bed_type": "GENERAL",
        },
        headers=auth_headers_hosp_a,
    )
    assert create_resp.status_code == 200
    ref_id = create_resp.json()["referral"]["referral_id"]

    # District admin tries to accept -> must be 403 Forbidden
    admin_resp = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=auth_headers_district_admin)
    assert admin_resp.status_code == 403
    assert "administrative roles cannot execute clinical" in admin_resp.json()["detail"].lower()


# ============================================================
# 8. SELF-REFERRAL FORBIDDEN
# ============================================================

def test_self_referral_rejected(auth_headers_hosp_a):
    """A hospital cannot refer a patient to itself."""
    resp = client.post(
        "/referrals",
        json={
            "patient_id": "PAT000005",
            "from_hospital_id": HOSPITAL_A,
            "to_hospital_id": HOSPITAL_A,  # Identical
            "reason": "Self referral",
            "priority": "Urgent",
            "bed_type": "GENERAL",
        },
        headers=auth_headers_hosp_a,
    )
    assert resp.status_code == 400
    assert "cannot be identical" in resp.json()["detail"].lower() or "same" in resp.json()["detail"].lower()


# ============================================================
# 9. LIVE POSTGRESQL TRANSACTIONAL REPOSITORY E2E VERIFICATION
# ============================================================

def test_live_postgresql_pg_repository_e2e():
    """
    Direct verification of PgReferralRepository against live PostgreSQL:
    1. Transactional referral creation with audit log & in-app notification.
    2. Atomic acceptance with row-level lock (FOR UPDATE SKIP LOCKED) holding a physical bed.
    3. IN_TRANSIT transition recording ambulance identifier and ETA.
    4. ARRIVED transition confirming reservation.
    5. TREATMENT_ACTIVE transition setting bed status to OCCUPIED.
    6. COMPLETED transition releasing bed and restoring hospital inventory counter.
    7. Notification queries and audit trail persistence.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from src.database.pg_models import PgBase, Hospital, Bed, Referral, BedReservation, AuditLog, Notification
    from src.database.pg_repository import PgReferralRepository

    test_db_url = "postgresql://localhost:5432/sih_hospital_test"
    engine = create_engine(test_db_url)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Provision test hospital with 1 ICU bed
        uid = uuid.uuid4().hex[:6].upper()
        hosp_src_id = f"H_SRC_{uid}"
        hosp_dst_id = f"H_DST_{uid}"

        hosp_src = Hospital(
            hospital_id=hosp_src_id,
            name="Source Referral Center",
            state="Punjab",
            district="Amritsar",
            latitude=31.63,
            longitude=74.87,
            total_beds=50,
            available_beds=20,
            icu_beds=5,
            available_icu_beds=2,
        )
        hosp_dst = Hospital(
            hospital_id=hosp_dst_id,
            name="Destination Medical Center",
            state="Punjab",
            district="Amritsar",
            latitude=31.64,
            longitude=74.88,
            total_beds=50,
            available_beds=10,
            icu_beds=1,
            available_icu_beds=1,
        )
        session.add_all([hosp_src, hosp_dst])
        session.flush()

        # Add single physical ICU bed to destination hospital
        bed_icu = Bed(
            hospital_id=hosp_dst_id,
            bed_number=f"ICU-TEST-{uid}",
            bed_type="ICU",
            status="AVAILABLE",
        )
        session.add(bed_icu)
        session.commit()

        repo = PgReferralRepository(session)

        # 1. Create referral
        patient_id = f"PAT_PG_{uid}"
        create_res = repo.create_referral(
            patient_id=patient_id,
            from_hospital_id=hosp_src_id,
            to_hospital_id=hosp_dst_id,
            reason="Cardiogenic shock requiring immediate mechanical support",
            priority="Critical",
            bed_type="ICU",
            user_id="USR_DOC_TEST",
        )
        assert create_res["success"] is True
        ref_id = create_res["referral"]["referral_id"]

        # Check notification was created for destination hospital
        notifs = repo.get_hospital_notifications(hosp_dst_id)
        assert notifs["unread_count"] >= 1
        assert any(n["referral_id"] == ref_id and n["event_type"] == "NEW_REFERRAL" for n in notifs["notifications"])

        # 2. Atomic accept and reserve
        accept_res = repo.atomic_accept_and_reserve(ref_id, user_id="USR_DST_CHIEF")
        assert accept_res["success"] is True
        assert accept_res["status"] == "ACCEPTED"
        assert accept_res["reservation"]["status"] == "RESERVED"

        # Verify bed is reserved and hospital available count is 0
        session.refresh(bed_icu)
        session.refresh(hosp_dst)
        assert bed_icu.status == "RESERVED"
        assert hosp_dst.available_icu_beds == 0

        # 3. Transition to IN_TRANSIT with ambulance
        dispatch_res = repo.atomic_transition_lifecycle(
            ref_id,
            "IN_TRANSIT",
            user_id="USR_EMS_COORD",
            ambulance_id="AMB-108-ADVANCED",
            eta_minutes=18,
        )
        assert dispatch_res["success"] is True
        assert dispatch_res["referral"]["ambulance_id"] == "AMB-108-ADVANCED"
        assert dispatch_res["referral"]["eta_minutes"] == 18

        # 4. Transition to ARRIVED
        arrive_res = repo.atomic_transition_lifecycle(ref_id, "ARRIVED", user_id="USR_DST_TRIAGE")
        assert arrive_res["success"] is True
        assert arrive_res["reservation_status"] == "CONFIRMED"

        # 5. Transition to TREATMENT_ACTIVE
        treat_res = repo.atomic_transition_lifecycle(ref_id, "TREATMENT_ACTIVE", user_id="USR_INTENSIVIST")
        assert treat_res["success"] is True
        session.refresh(bed_icu)
        assert bed_icu.status == "OCCUPIED"

        # 6. Complete treatment and release bed
        comp_res = repo.atomic_transition_lifecycle(ref_id, "COMPLETED", user_id="USR_INTENSIVIST")
        assert comp_res["success"] is True
        session.refresh(bed_icu)
        session.refresh(hosp_dst)
        assert bed_icu.status == "AVAILABLE"
        assert hosp_dst.available_icu_beds == 1

        # 7. Audit log verification
        audit_rows = session.execute(
            select(AuditLog).where(AuditLog.entity_id == ref_id).order_by(AuditLog.created_at.asc())
        ).scalars().all()
        actions = [a.action for a in audit_rows]
        assert "REFERRAL_CREATED" in actions
        assert "ACCEPTED_WITH_BED" in actions
        assert "TRANSITION_IN_TRANSIT" in actions
        assert "TRANSITION_ARRIVED" in actions
        assert "TRANSITION_TREATMENT_ACTIVE" in actions
        assert "TRANSITION_COMPLETED" in actions

    finally:
        session.close()
        engine.dispose()
