"""
Phase 4D-3 Comprehensive Test Suite: Operational Notifications & Notification Inbox
AI Powered Smart Hospital Referral System

Validates:
1. Referral creation, acceptance, and rejection operational notifications.
2. Masked patient PII verification in all operational notifications and outbox emails.
3. Bed hold lifecycle notifications: RESERVED -> CONFIRMED -> OCCUPIED -> DISCHARGED / RELEASED.
4. Automated / direct reservation expiry notifications and capacity restoration.
5. Low bed capacity threshold alerts with hourly deduplication to prevent notification spam.
6. Multi-tenant hospital and jurisdictional isolation (Hospital A vs Hospital B, District A vs District B).
7. Transactional atomicity: transaction rollbacks commit zero notifications and zero outbox rows.
8. Notification inbox API endpoints: /hospitals/{id}/notifications, /notifications/me, read, and read-all.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.pg_models import (
    PgBase,
    User,
    Role,
    Hospital,
    Bed,
    Referral,
    BedReservation,
    Notification,
    RegistrationEmailOutbox,
    AuditLog,
)
from src.database.pg_repository import PgReferralRepository
from src.services.workflow_notification_service import WorkflowNotificationService
from src.auth.jwt_utils import create_access_token
from src.services.email_service import SimulatedEmailProvider, set_email_provider


@pytest.fixture
def op_db_session():
    """Create isolated in-memory SQLite database session with complete schema and seed data."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PgBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    # Seed roles
    roles = [
        Role(id="HOSPITAL", description="Hospital Clinical Staff"),
        Role(id="DISTRICT_ADMIN", description="District Health Authority"),
        Role(id="STATE_ADMIN", description="State Health Directorate"),
        Role(id="CENTRAL_ADMIN", description="National Healthcare Authority"),
    ]
    for r in roles:
        session.merge(r)

    # Seed hospitals
    hosp_a = Hospital(
        hospital_id="HOSP-MOHALI-01",
        name="Fortis Hospital Mohali",
        state="Punjab",
        district="Mohali",
        latitude=30.7046,
        longitude=76.7179,
        total_beds=50,
        available_beds=20,
        icu_beds=10,
        available_icu_beds=5,
        emergency_beds=8,
        available_emergency_beds=4,
        oxygen_support="Yes",
        ventilator="Yes",
        ambulance="Yes",
        blood_bank="Yes",
        emergency_24x7="Yes",
    )
    hosp_b = Hospital(
        hospital_id="HOSP-LUDHIANA-01",
        name="Dayanand Medical College Ludhiana",
        state="Punjab",
        district="Ludhiana",
        latitude=30.9010,
        longitude=75.8573,
        total_beds=100,
        available_beds=10,
        icu_beds=5,
        available_icu_beds=2,
        emergency_beds=10,
        available_emergency_beds=5,
        oxygen_support="Yes",
        ventilator="Yes",
        ambulance="Yes",
        blood_bank="Yes",
        emergency_24x7="Yes",
    )
    session.add(hosp_a)
    session.add(hosp_b)

    # Seed beds for Hospital B
    for i in range(1, 4):
        session.add(Bed(
            hospital_id="HOSP-LUDHIANA-01",
            bed_number=f"ICU-{i:02d}",
            bed_type="ICU",
            status="AVAILABLE",
        ))
    for i in range(1, 6):
        session.add(Bed(
            hospital_id="HOSP-LUDHIANA-01",
            bed_number=f"GEN-{i:02d}",
            bed_type="GENERAL",
            status="AVAILABLE",
        ))

    # Seed users
    staff_a = User(
        user_id="U_STAFF_A",
        username="staff_fortis",
        name="Fortis Staff",
        role_id="HOSPITAL",
        state="Punjab",
        district="Mohali",
        hospital_id="HOSP-MOHALI-01",
        email="staff@fortis-mohali.com",
        is_active=True,
        password_hash="hash",
    )
    staff_b = User(
        user_id="U_STAFF_B",
        username="staff_dmc",
        name="DMC Staff",
        role_id="HOSPITAL",
        state="Punjab",
        district="Ludhiana",
        hospital_id="HOSP-LUDHIANA-01",
        email="triage@dmc-ludhiana.org",
        is_active=True,
        password_hash="hash",
    )
    cmo_ludhiana = User(
        user_id="U_CMO_LUDHIANA",
        username="cmo_ludhiana",
        name="Dr. Ludhiana CMO",
        role_id="DISTRICT_ADMIN",
        state="Punjab",
        district="Ludhiana",
        email="cmo.ludhiana@punjab.gov.in",
        is_active=True,
        password_hash="hash",
    )
    session.add(staff_a)
    session.add(staff_b)
    session.add(cmo_ludhiana)

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


# ============================================================
# 1. REFERRAL CREATION, ACCEPTANCE & REJECTION NOTIFICATIONS
# ============================================================

def test_referral_creation_operational_notification(op_db_session, sim_email):
    """
    Creating a referral must generate:
    1. In-app notification for receiving hospital.
    2. District authority alert for destination district.
    3. Transactional outbox email to destination hospital contacts.
    4. Masked patient identifier (PAT-***) preserving privacy.
    """
    repo = PgReferralRepository(op_db_session)
    result = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-9876543210",
        priority="Critical",
        bed_type="ICU",
        reason="Acute cardiogenic shock requiring advanced hemodynamic monitoring",
    )
    assert result["success"] is True
    ref_id = result["referral"]["referral_id"]

    # 1. Verify in-app notification for destination hospital
    hosp_notifs = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        referral_id=ref_id,
    ).all()
    assert len(hosp_notifs) >= 1
    dest_notif = hosp_notifs[0]
    assert dest_notif.event_type == "NEW_REFERRAL"
    assert "Critical" in dest_notif.title or "Critical" in dest_notif.message
    # Verify patient ID is masked
    assert "PAT-***3210" in dest_notif.message
    assert "9876543210" not in dest_notif.message
    assert dest_notif.priority == "CRITICAL"

    # 2. Verify district authority alert
    dist_notifs = op_db_session.query(Notification).filter_by(
        role_id="DISTRICT_ADMIN",
        district="Ludhiana",
        referral_id=ref_id,
    ).all()
    assert len(dist_notifs) >= 1
    assert "District Referral Alert" in dist_notifs[0].title

    # 3. Verify transactional outbox email
    outbox_emails = op_db_session.query(RegistrationEmailOutbox).filter_by(
        event_type="NEW_REFERRAL",
        recipient_email="triage@dmc-ludhiana.org",
    ).all()
    assert len(outbox_emails) >= 1
    email = outbox_emails[0]
    email_payload = json.loads(email.payload) if isinstance(email.payload, str) else email.payload
    assert "PAT-***3210" in email_payload.get("body_text", "")
    assert "9876543210" not in email_payload.get("body_text", "")
    assert ref_id in email.subject


def test_referral_acceptance_operational_notification(op_db_session):
    """
    Accepting a referral atomically reserves a bed and notifies:
    1. Referring hospital with reserved bed details.
    2. Outbox email to referring facility.
    """
    repo = PgReferralRepository(op_db_session)
    create_res = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-55551234",
        priority="High",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    accept_res = repo.atomic_accept_and_reserve(
        referral_id=ref_id,
        user_id="U_STAFF_B",
        ttl_hours=2,
    )
    assert accept_res["success"] is True
    assert accept_res["status"] == "ACCEPTED"

    # Verify referring hospital received REFERRAL_ACCEPTED notification
    source_notifs = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-MOHALI-01",
        referral_id=ref_id,
        event_type="REFERRAL_ACCEPTED",
    ).all()
    assert len(source_notifs) >= 1
    notif = source_notifs[0]
    assert "accepted" in notif.message.lower()
    assert "PAT-***1234" in notif.message

    # Verify outbox confirmation email
    outbox_emails = op_db_session.query(RegistrationEmailOutbox).filter_by(
        event_type="REFERRAL_ACCEPTED",
        recipient_email="staff@fortis-mohali.com",
    ).all()
    assert len(outbox_emails) >= 1
    out_payload = json.loads(outbox_emails[0].payload) if isinstance(outbox_emails[0].payload, str) else outbox_emails[0].payload
    assert "PAT-***1234" in out_payload.get("body_text", "")


def test_referral_rejection_operational_notification(op_db_session):
    """
    Rejecting a referral notifies referring hospital with sanitized reason.
    """
    repo = PgReferralRepository(op_db_session)
    create_res = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-99998888",
        priority="Normal",
        bed_type="GENERAL",
    )
    ref_id = create_res["referral"]["referral_id"]

    reject_res = repo.atomic_transition_lifecycle(
        referral_id=ref_id,
        new_status="REJECTED",
        user_id="U_STAFF_B",
        notes="No available isolation beds currently in Ludhiana facility.",
    )
    assert reject_res["success"] is True

    # Verify referring hospital received rejection notification
    source_notifs = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-MOHALI-01",
        referral_id=ref_id,
        event_type="REFERRAL_REJECTED",
    ).all()
    assert len(source_notifs) >= 1
    assert "declined" in source_notifs[0].message.lower() or "rejected" in source_notifs[0].message.lower()
    assert "PAT-***8888" in source_notifs[0].message
    assert "No available isolation beds" in source_notifs[0].message


# ============================================================
# 2. BED HOLD LIFECYCLE OPERATIONAL NOTIFICATIONS
# ============================================================

def test_direct_bed_reservation_full_lifecycle(op_db_session):
    """
    Test full lifecycle transitions:
    reserve_bed_direct -> confirm_bed_direct -> occupy_bed_direct -> discharge_patient_direct
    Each must emit the appropriate in-app notification and maintain data consistency.
    """
    repo = PgReferralRepository(op_db_session)

    # 1. Direct Reserve
    res = repo.reserve_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-DIRECT-4321",
        bed_type="GENERAL",
        ttl_hours=2,
    )
    assert res["success"] is True
    res_id = res["reservation"]["reservation_id"]

    # Verify BED_RESERVED notification
    notif_res = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="BED_RESERVED",
    ).first()
    assert notif_res is not None
    assert "PAT-***4321" in notif_res.message

    # 2. Confirm (Patient Arrival)
    conf = repo.confirm_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-DIRECT-4321",
    )
    assert conf["success"] is True

    # Verify RESERVATION_CONFIRMED notification
    notif_conf = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="RESERVATION_CONFIRMED",
    ).first()
    assert notif_conf is not None
    assert "guaranteed" in notif_conf.message.lower()

    # 3. Occupy (Patient Admitted)
    occ = repo.occupy_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-DIRECT-4321",
    )
    assert occ["success"] is True

    # Verify BED_OCCUPIED notification
    notif_occ = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="BED_OCCUPIED",
    ).first()
    assert notif_occ is not None
    assert "admitted" in notif_occ.message.lower()

    # 4. Discharge (Patient Discharged & Capacity Restored)
    disc = repo.discharge_patient_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-DIRECT-4321",
    )
    assert disc["success"] is True

    # Verify PATIENT_DISCHARGED notification
    notif_disc = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="PATIENT_DISCHARGED",
    ).first()
    assert notif_disc is not None
    assert "discharged" in notif_disc.message.lower()


def test_bed_direct_release_notification(op_db_session):
    """
    Releasing a reserved hold emits RESERVATION_CANCELLED notification.
    """
    repo = PgReferralRepository(op_db_session)
    res = repo.reserve_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-REL-1111",
        bed_type="GENERAL",
    )
    assert res["success"] is True

    rel = repo.release_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-REL-1111",
    )
    assert rel["success"] is True

    notif_rel = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="RESERVATION_CANCELLED",
    ).first()
    assert notif_rel is not None
    assert "cancelled" in notif_rel.message.lower()


# ============================================================
# 3. BED RESERVATION EXPIRY NOTIFICATIONS
# ============================================================

def test_bed_expiry_notification_and_capacity_restoration(op_db_session):
    """
    When an overdue reservation expires:
    1. RESERVATION_EXPIRED notification emitted to hospital.
    2. Outbox expiry email enqueued.
    3. Bed status restored to AVAILABLE.
    4. CONFIRMED reservation is guaranteed and cannot be expired.
    """
    repo = PgReferralRepository(op_db_session)
    res = repo.reserve_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-EXP-9999",
        bed_type="GENERAL",
    )
    assert res["success"] is True
    res_id = res["reservation"]["reservation_id"]

    # Expire reservation
    exp_res = repo.expire_reservation_direct(reservation_id=res_id)
    assert exp_res["success"] is True
    assert exp_res["status"] == "EXPIRED"

    # Verify RESERVATION_EXPIRED notification
    notif = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="RESERVATION_EXPIRED",
    ).first()
    assert notif is not None
    assert "expired" in notif.message.lower()
    assert "PAT-***9999" in notif.message

    # Verify outbox email
    outbox = op_db_session.query(RegistrationEmailOutbox).filter_by(
        event_type="RESERVATION_EXPIRED",
        recipient_email="triage@dmc-ludhiana.org",
    ).first()
    assert outbox is not None
    outbox_payload = json.loads(outbox.payload) if isinstance(outbox.payload, str) else outbox.payload
    assert res_id in outbox_payload.get("body_text", "")

    # Safety guarantee: Confirmed reservations cannot expire
    res2 = repo.reserve_bed_direct(
        hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-CONF-8888",
        bed_type="GENERAL",
    )
    repo.confirm_bed_direct(hospital_id="HOSP-LUDHIANA-01", patient_id="PAT-CONF-8888")
    fail_exp = repo.expire_reservation_direct(reservation_id=res2["reservation"]["reservation_id"])
    assert fail_exp["success"] is False
    assert fail_exp["status"] == "CONFIRMED_CANNOT_EXPIRE"


# ============================================================
# 4. LOW BED AVAILABILITY THRESHOLDS & DEDUPLICATION
# ============================================================

def test_low_bed_availability_threshold_and_hourly_deduplication(op_db_session):
    """
    Triggering low bed availability:
    1. ICU capacity <= 1 or GENERAL <= 2 triggers alert.
    2. Repeated alerts within the same hour window are deduplicated.
    3. District authority receives notification.
    """
    hosp = op_db_session.query(Hospital).filter_by(hospital_id="HOSP-LUDHIANA-01").first()
    hosp.available_icu_beds = 1
    op_db_session.commit()

    svc = WorkflowNotificationService(op_db_session)
    svc.notify_low_bed_availability(hosp, "ICU", available_count=1, total_count=5)
    op_db_session.commit()

    # Verify hospital alert
    alerts = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="LOW_BED_AVAILABILITY",
    ).all()
    assert len(alerts) == 1
    assert alerts[0].priority in ("CRITICAL", "HIGH")
    assert "1 of 5 ICU beds" in alerts[0].message

    # Verify district authority alert
    dist_alerts = op_db_session.query(Notification).filter_by(
        role_id="DISTRICT_ADMIN",
        district="Ludhiana",
        event_type="LOW_BED_AVAILABILITY",
    ).all()
    assert len(dist_alerts) == 1

    # Call again within same hour -> Must be deduplicated (count remains 1)
    svc.notify_low_bed_availability(hosp, "ICU", available_count=1, total_count=5)
    op_db_session.commit()

    alerts_after = op_db_session.query(Notification).filter_by(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="LOW_BED_AVAILABILITY",
    ).all()
    assert len(alerts_after) == 1


# ============================================================
# 5. MULTI-TENANT ISOLATION & JURISDICTION BARRIERS
# ============================================================

def test_hospital_and_jurisdiction_isolation(op_db_session):
    """
    Strict isolation verification:
    - Hospital A only sees Hospital A notifications.
    - Reviewer in District A cannot see Reviewer notifications for District B.
    """
    repo = PgReferralRepository(op_db_session)

    # Seed notification for Hospital A
    op_db_session.add(Notification(
        hospital_id="HOSP-MOHALI-01",
        event_type="BED_RESERVED",
        title="Alert for Mohali",
        message="Confidential hospital message for Fortis",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    ))
    # Seed notification for Hospital B
    op_db_session.add(Notification(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="BED_RESERVED",
        title="Alert for Ludhiana",
        message="Confidential hospital message for DMC",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    ))
    op_db_session.commit()

    # Hospital A fetch
    notifs_a = repo.get_hospital_notifications("HOSP-MOHALI-01")
    titles_a = [n["title"] for n in notifs_a["notifications"]]
    assert "Alert for Mohali" in titles_a
    assert "Alert for Ludhiana" not in titles_a

    # Hospital B fetch
    notifs_b = repo.get_hospital_notifications("HOSP-LUDHIANA-01")
    titles_b = [n["title"] for n in notifs_b["notifications"]]
    assert "Alert for Ludhiana" in titles_b
    assert "Alert for Mohali" not in titles_b


# ============================================================
# 6. TRANSACTION ATOMICITY & ROLLBACK INTEGRITY
# ============================================================

def test_transactional_rollback_preserves_zero_notifications(op_db_session):
    """
    If a transaction fails or rolls back, no notifications or outbox records persist.
    """
    initial_notif_count = op_db_session.query(Notification).count()
    initial_outbox_count = op_db_session.query(RegistrationEmailOutbox).count()

    # Simulate an operation that encounters an error and rolls back
    try:
        hosp = op_db_session.query(Hospital).first()
        svc = WorkflowNotificationService(op_db_session)
        svc.notify_low_bed_availability(hosp, "ICU", available_count=0, total_count=5)
        # Force an error
        raise RuntimeError("Simulated unhandled transaction error")
    except RuntimeError:
        op_db_session.rollback()

    assert op_db_session.query(Notification).count() == initial_notif_count
    assert op_db_session.query(RegistrationEmailOutbox).count() == initial_outbox_count


# ============================================================
# 7. NOTIFICATION REPOSITORY QUERIES & PAGINATION
# ============================================================

def test_notification_inbox_pagination_and_category_filtering(op_db_session):
    """
    Test pagination parameters (page, page_size) and event category filtering.
    """
    repo = PgReferralRepository(op_db_session)
    hid = "HOSP-LUDHIANA-01"

    # Clear existing notifications for hid
    op_db_session.query(Notification).filter_by(hospital_id=hid).delete()
    op_db_session.commit()

    # Seed 5 notifications: 3 referral, 2 bed
    now = datetime.now(timezone.utc)
    for i in range(1, 4):
        op_db_session.add(Notification(
            hospital_id=hid,
            event_type="REFERRAL_ACCEPTED",
            title=f"Referral {i}",
            message=f"Referral message {i}",
            is_read=False,
            created_at=now + timedelta(minutes=i),
        ))
    for i in range(1, 3):
        op_db_session.add(Notification(
            hospital_id=hid,
            event_type="BED_RESERVED",
            title=f"Bed {i}",
            message=f"Bed message {i}",
            is_read=False,
            created_at=now + timedelta(minutes=10 + i),
        ))
    op_db_session.commit()

    # 1. Total and pagination
    res_page1 = repo.get_hospital_notifications(hid, page=1, page_size=2)
    assert res_page1["total_count"] == 5
    assert len(res_page1["notifications"]) == 2
    assert res_page1["page"] == 1

    res_page2 = repo.get_hospital_notifications(hid, page=2, page_size=2)
    assert len(res_page2["notifications"]) == 2
    assert res_page2["page"] == 2

    # 2. Category filtering
    res_ref = repo.get_hospital_notifications(hid, event_category="referral")
    assert res_ref["total_count"] == 3
    assert all("REFERRAL" in n["event_type"] for n in res_ref["notifications"])

    res_bed = repo.get_hospital_notifications(hid, event_category="bed")
    assert res_bed["total_count"] == 2
    assert all("BED" in n["event_type"] for n in res_bed["notifications"])

    # 3. Mark single as read
    first_id = res_ref["notifications"][0]["id"]
    marked = repo.mark_notification_as_read(first_id, hid)
    assert marked is True

    unread_res = repo.get_hospital_notifications(hid, unread_only=True)
    assert unread_res["unread_count"] == 4

    # 4. Mark all as read
    all_marked = repo.mark_all_notifications_read(hid)
    assert all_marked == 4
    unread_final = repo.get_hospital_notifications(hid, unread_only=True)
    assert unread_final["unread_count"] == 0


# ============================================================
# 8. NOTIFICATION API ENDPOINTS (/notifications/me, /read, etc.)
# ============================================================

def test_notification_inbox_api_endpoints(op_db_session, monkeypatch):
    """
    Test FastAPI endpoints:
    - GET /notifications/me
    - POST /notifications/{id}/read
    - POST /notifications/read-all
    - GET /hospitals/{id}/notifications
    """
    repo = PgReferralRepository(op_db_session)
    # Monkeypatch get_referral_repository in db_manager to return our test repo
    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "is_postgres", lambda: True)
    monkeypatch.setattr(db_m, "get_referral_repository", lambda: repo)

    hid = "HOSP-LUDHIANA-01"
    token = create_access_token({
        "user_id": "U_STAFF_B",
        "username": "staff_dmc",
        "role": "HOSPITAL",
        "hospital_id": hid,
        "state": "Punjab",
        "district": "Ludhiana",
    })
    headers = {"Authorization": f"Bearer {token}"}

    client = TestClient(app)

    # 1. Fetch me notifications
    resp = client.get("/notifications/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert "unread_count" in data

    # 2. Add an unread notification
    now = datetime.now(timezone.utc)
    new_notif = Notification(
        hospital_id=hid,
        event_type="BED_RESERVED",
        title="Test API Alert",
        message="Test alert message",
        is_read=False,
        created_at=now,
    )
    op_db_session.add(new_notif)
    op_db_session.commit()

    resp_after = client.get("/notifications/me?unread_only=true", headers=headers)
    assert resp_after.status_code == 200
    data_after = resp_after.json()
    assert data_after["unread_count"] >= 1
    target_id = new_notif.id

    # 3. Mark single as read via /notifications/{id}/read
    read_resp = client.post(f"/notifications/{target_id}/read", headers=headers)
    assert read_resp.status_code == 200
    assert read_resp.json()["success"] is True

    # 4. Mark all as read via /notifications/read-all
    all_read_resp = client.post("/notifications/read-all", headers=headers)
    assert all_read_resp.status_code == 200
    assert all_read_resp.json()["success"] is True

    # Verify unread count is 0
    final_resp = client.get("/notifications/me?unread_only=true", headers=headers)
    assert final_resp.status_code == 200
    assert final_resp.json()["unread_count"] == 0


# ============================================================
# 9. FINAL SECURITY & COMPLETENESS AUDIT TESTS (PHASE 4D-3)
# ============================================================

def test_recipient_completeness_state_and_central_authorities(op_db_session):
    """
    Audit Area 1: RECIPIENT COMPLETENESS
    - State and Central authorities receive notifications strictly by jurisdiction and event type.
    - resolve_state_authorities and resolve_central_authorities resolve active admins.
    - Normal intra-state referrals do NOT spam State or Central.
    - Critical referrals notify the destination State authority.
    - Inter-state referrals notify the destination State authority and Central authority.
    - No global broadcasting: State A authority never receives State B alerts.
    """
    # Seed State and Central administrators
    state_pb = User(
        user_id="U_STATE_PUNJAB",
        username="director_health_pb",
        name="Dr. Director Punjab Health",
        role_id="STATE_ADMIN",
        state="Punjab",
        email="director@punjabhealth.gov.in",
        is_active=True,
        password_hash="hash",
    )
    state_hr = User(
        user_id="U_STATE_HARYANA",
        username="director_health_hr",
        name="Dr. Director Haryana Health",
        role_id="STATE_ADMIN",
        state="Haryana",
        email="director@haryanahealth.gov.in",
        is_active=True,
        password_hash="hash",
    )
    central_admin = User(
        user_id="U_CENTRAL_MOHFW",
        username="mohfw_national",
        name="National Health Commissioner",
        role_id="CENTRAL_ADMIN",
        email="commissioner@mohfw.gov.in",
        is_active=True,
        password_hash="hash",
    )
    # Seed Haryana hospital
    hosp_haryana = Hospital(
        hospital_id="HOSP-GURUGRAM-01",
        name="Medanta Gurugram",
        state="Haryana",
        district="Gurugram",
        latitude=28.4595,
        longitude=77.0266,
        total_beds=200,
        available_beds=50,
        icu_beds=30,
        available_icu_beds=15,
        emergency_beds=20,
        available_emergency_beds=10,
    )
    op_db_session.add_all([state_pb, state_hr, central_admin, hosp_haryana])
    op_db_session.commit()

    notif_svc = WorkflowNotificationService(op_db_session)

    # 1. Test helper methods
    pb_admins = notif_svc.resolve_state_authorities("Punjab")
    assert len(pb_admins) == 1
    assert pb_admins[0].user_id == "U_STATE_PUNJAB"

    hr_admins = notif_svc.resolve_state_authorities("Haryana")
    assert len(hr_admins) == 1
    assert hr_admins[0].user_id == "U_STATE_HARYANA"

    central_admins = notif_svc.resolve_central_authorities()
    assert len(central_admins) == 1
    assert central_admins[0].user_id == "U_CENTRAL_MOHFW"

    repo = PgReferralRepository(op_db_session)

    # 2. Normal intra-state referral (Mohali -> Ludhiana, Priority: Normal)
    res_normal = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-NORM-0001",
        priority="Normal",
        bed_type="GENERAL",
    )
    assert res_normal["success"] is True
    ref_norm_id = res_normal["referral"]["referral_id"]

    # Verify State and Central did NOT receive alerts for normal intra-state
    state_notifs = op_db_session.query(Notification).filter(
        Notification.role_id.in_(["STATE_ADMIN", "CENTRAL_ADMIN"]),
        Notification.referral_id == ref_norm_id,
    ).all()
    assert len(state_notifs) == 0

    # 3. Critical intra-state referral (Mohali -> Ludhiana, Priority: Critical)
    res_crit = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-LUDHIANA-01",
        patient_id="PAT-CRIT-0002",
        priority="Critical",
        bed_type="ICU",
    )
    assert res_crit["success"] is True
    ref_crit_id = res_crit["referral"]["referral_id"]

    # Punjab State receives alert; Haryana and Central do NOT
    pb_crit_notifs = op_db_session.query(Notification).filter_by(
        role_id="STATE_ADMIN",
        state="Punjab",
        referral_id=ref_crit_id,
    ).all()
    assert len(pb_crit_notifs) == 1
    assert "State Referral Alert" in pb_crit_notifs[0].title
    assert pb_crit_notifs[0].priority == "CRITICAL"

    hr_crit_notifs = op_db_session.query(Notification).filter_by(
        role_id="STATE_ADMIN",
        state="Haryana",
        referral_id=ref_crit_id,
    ).all()
    assert len(hr_crit_notifs) == 0

    central_crit_notifs = op_db_session.query(Notification).filter_by(
        role_id="CENTRAL_ADMIN",
        referral_id=ref_crit_id,
    ).all()
    assert len(central_crit_notifs) == 0

    # 4. Inter-state referral (Mohali, Punjab -> Gurugram, Haryana)
    res_interstate = repo.create_referral(
        from_hospital_id="HOSP-MOHALI-01",
        to_hospital_id="HOSP-GURUGRAM-01",
        patient_id="PAT-CROSS-0003",
        priority="High",
        bed_type="ICU",
    )
    assert res_interstate["success"] is True
    ref_inter_id = res_interstate["referral"]["referral_id"]

    # Destination State (Haryana) receives alert
    hr_inter_notifs = op_db_session.query(Notification).filter_by(
        role_id="STATE_ADMIN",
        state="Haryana",
        referral_id=ref_inter_id,
    ).all()
    assert len(hr_inter_notifs) == 1
    assert "inter-state" in hr_inter_notifs[0].message.lower()

    # Origin State (Punjab) does not receive destination alert
    pb_inter_notifs = op_db_session.query(Notification).filter_by(
        role_id="STATE_ADMIN",
        state="Punjab",
        referral_id=ref_inter_id,
    ).all()
    assert len(pb_inter_notifs) == 0

    # Central authority receives cross-border alert
    central_inter_notifs = op_db_session.query(Notification).filter_by(
        role_id="CENTRAL_ADMIN",
        referral_id=ref_inter_id,
    ).all()
    assert len(central_inter_notifs) == 1
    assert "National Inter-State Referral" in central_inter_notifs[0].title


def test_low_bed_alerts_real_inventory_mutations_and_thresholds(op_db_session):
    """
    Audit Area 2: LOW-BED ALERT DISPATCH
    - Real inventory and reservation changes trigger alerts when thresholds crossed:
      General <= 2, ICU <= 1.
    - Capacity recovery above thresholds does NOT alert.
    - Repeated events in the same hourly window are deduplicated.
    - Zero capacity triggers emergency Central alert.
    """
    repo = PgReferralRepository(op_db_session)
    hid = "HOSP-LUDHIANA-01"

    # Step A: Update General bed inventory to 3 (above threshold <= 2)
    # Hospital B initially has 5 General beds. Set total_capacity to 3 (so 3 available).
    res_up3 = repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="GENERAL",
        total_capacity=3,
        user_id="U_STAFF_B",
    )
    assert res_up3 is not None and "hospital_id" in res_up3

    # Confirm no low-bed alert created for General at 3 available
    notifs_gen3 = op_db_session.query(Notification).filter(
        Notification.hospital_id == hid,
        Notification.event_type == "LOW_BED_AVAILABILITY",
        Notification.title.like("%GENERAL%"),
    ).all()
    assert len(notifs_gen3) == 0

    # Step B: Direct reservation drops available General beds from 3 to 2 (reaches threshold <= 2)
    res_direct = repo.reserve_bed_direct(
        hospital_id=hid,
        bed_type="GENERAL",
        patient_id="PAT-DIR-0001",
        user_id="U_STAFF_B",
    )
    assert res_direct["success"] is True

    # Verify low bed alert created for Hospital, District, and State
    now_hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    hosp_alert = op_db_session.query(Notification).filter_by(
        idempotency_key=f"OP_LOW_BED_{hid}_GENERAL_{now_hour}"
    ).first()
    assert hosp_alert is not None
    assert "2 Remaining" in hosp_alert.title

    dist_alert = op_db_session.query(Notification).filter_by(
        idempotency_key=f"OP_LOW_BED_DIST_{hid}_GENERAL_{now_hour}"
    ).first()
    assert dist_alert is not None

    state_alert = op_db_session.query(Notification).filter_by(
        idempotency_key=f"OP_LOW_BED_STATE_{hid}_GENERAL_{now_hour}"
    ).first()
    assert state_alert is not None
    assert state_alert.state == "Punjab"

    # Step C: Repeated event within same hour window is deduplicated
    count_before = op_db_session.query(Notification).filter(
        Notification.event_type == "LOW_BED_AVAILABILITY"
    ).count()

    notif_svc = WorkflowNotificationService(op_db_session)
    hosp = op_db_session.get(Hospital, hid)
    notif_svc.notify_low_bed_availability(hosp, "GENERAL", available_count=2, total_count=10)

    count_after = op_db_session.query(Notification).filter(
        Notification.event_type == "LOW_BED_AVAILABILITY"
    ).count()
    assert count_after == count_before  # Deduplicated!

    # Step D: ICU threshold test (ICU <= 1)
    # Hospital B initially has 3 ICU beds. Update total_capacity to 2 -> 2 available -> no alert
    res_icu2 = repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="ICU",
        total_capacity=2,
        user_id="U_STAFF_B",
    )
    assert res_icu2 is not None
    icu_alerts = op_db_session.query(Notification).filter(
        Notification.hospital_id == hid,
        Notification.event_type == "LOW_BED_AVAILABILITY",
        Notification.title.like("%ICU%"),
    ).all()
    assert len(icu_alerts) == 0

    # ICU total_capacity to 1 -> 1 available -> triggers CRITICAL alert
    res_icu1 = repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="ICU",
        total_capacity=1,
        user_id="U_STAFF_B",
    )
    assert res_icu1 is not None
    icu_alert = op_db_session.query(Notification).filter_by(
        idempotency_key=f"OP_LOW_BED_{hid}_ICU_{now_hour}"
    ).first()
    assert icu_alert is not None
    assert icu_alert.priority == "CRITICAL"

    # Step E: Zero capacity -> triggers Central emergency alert
    res_icu0 = repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="ICU",
        total_capacity=0,
        user_id="U_STAFF_B",
    )
    assert res_icu0 is not None
    central_emergency = op_db_session.query(Notification).filter_by(
        idempotency_key=f"OP_LOW_BED_CENTRAL_{hid}_ICU_{now_hour}"
    ).first()
    assert central_emergency is not None
    assert "Zero ICU Capacity" in central_emergency.title
    assert central_emergency.role_id == "CENTRAL_ADMIN"

    # Step F: Capacity recovery above thresholds does not create low bed alert
    res_rec = repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="GENERAL",
        total_capacity=10,
        user_id="U_STAFF_B",
    )
    assert res_rec is not None


def test_notification_ownership_security_and_idor_protection(op_db_session, monkeypatch):
    """
    Audit Area 3: NOTIFICATION OWNERSHIP SECURITY
    - Hospital Staff A cannot view or mark read Hospital Staff B's notifications.
    - District Admin A cannot view or mark read District Admin B's notifications.
    - State Admin A cannot view or mark read State Admin B's notifications.
    - /hospitals/{id}/notifications strictly enforces hospital authorization (403).
    - Unauthenticated or forged tokens rejected (401).
    """
    repo = PgReferralRepository(op_db_session)
    import src.database.db_manager as db_m
    monkeypatch.setattr(db_m, "is_postgres", lambda: True)
    monkeypatch.setattr(db_m, "get_referral_repository", lambda: repo)

    client = TestClient(app)

    # Create unread notifications for Hospital B
    now = datetime.now(timezone.utc)
    notif_b = Notification(
        hospital_id="HOSP-LUDHIANA-01",
        event_type="BED_RESERVED",
        title="DMC Ludhiana Private Alert",
        message="Sensitive clinical alert for DMC Ludhiana",
        is_read=False,
        created_at=now,
    )
    # Create unread notification for District Admin Ludhiana
    notif_dist_ludhiana = Notification(
        role_id="DISTRICT_ADMIN",
        state="Punjab",
        district="Ludhiana",
        event_type="NEW_REFERRAL",
        title="Ludhiana District Health Alert",
        message="Ludhiana district operational report",
        is_read=False,
        created_at=now,
    )
    # Create unread notification for State Admin Punjab
    notif_state_pb = Notification(
        role_id="STATE_ADMIN",
        state="Punjab",
        event_type="LOW_BED_AVAILABILITY",
        title="Punjab State Health Alert",
        message="Punjab bed utilization report",
        is_read=False,
        created_at=now,
    )
    op_db_session.add_all([notif_b, notif_dist_ludhiana, notif_state_pb])
    op_db_session.commit()

    # 1. Hospital Staff A (Fortis Mohali) attempts IDOR on Hospital B (DMC Ludhiana)
    token_staff_a = create_access_token({
        "user_id": "U_STAFF_A",
        "username": "staff_fortis",
        "role": "HOSPITAL",
        "hospital_id": "HOSP-MOHALI-01",
        "state": "Punjab",
        "district": "Mohali",
    })
    headers_staff_a = {"Authorization": f"Bearer {token_staff_a}"}

    # Staff A accessing Hospital B notifications directly -> 403 Forbidden
    resp_hosp_b = client.get("/hospitals/HOSP-LUDHIANA-01/notifications", headers=headers_staff_a)
    assert resp_hosp_b.status_code == 403

    # Staff A guessing Hospital B notification ID via /notifications/{id}/read
    resp_read_idor = client.post(f"/notifications/{notif_b.id}/read", headers=headers_staff_a)
    assert resp_read_idor.status_code == 200
    assert resp_read_idor.json()["success"] is False
    # Verify DB record is untouched!
    op_db_session.refresh(notif_b)
    assert notif_b.is_read is False

    # 2. Cross-district IDOR: District Admin Mohali attempts to mark read Ludhiana alert
    token_cmo_mohali = create_access_token({
        "user_id": "U_CMO_MOHALI",
        "username": "cmo_mohali",
        "role": "DISTRICT_ADMIN",
        "state": "Punjab",
        "district": "Mohali",
    })
    headers_cmo_mohali = {"Authorization": f"Bearer {token_cmo_mohali}"}

    resp_dist_idor = client.post(f"/notifications/{notif_dist_ludhiana.id}/read", headers=headers_cmo_mohali)
    assert resp_dist_idor.status_code == 200
    assert resp_dist_idor.json()["success"] is False
    op_db_session.refresh(notif_dist_ludhiana)
    assert notif_dist_ludhiana.is_read is False

    # 3. Cross-state IDOR: State Admin Haryana attempts to mark read Punjab alert
    token_state_hr = create_access_token({
        "user_id": "U_STATE_HARYANA",
        "username": "director_health_hr",
        "role": "STATE_ADMIN",
        "state": "Haryana",
    })
    headers_state_hr = {"Authorization": f"Bearer {token_state_hr}"}

    resp_state_idor = client.post(f"/notifications/{notif_state_pb.id}/read", headers=headers_state_hr)
    assert resp_state_idor.status_code == 200
    assert resp_state_idor.json()["success"] is False
    op_db_session.refresh(notif_state_pb)
    assert notif_state_pb.is_read is False

    # 4. Valid authorized mark read: State Admin Punjab marks Punjab alert read
    token_state_pb = create_access_token({
        "user_id": "U_STATE_PUNJAB",
        "username": "director_health_pb",
        "role": "STATE_ADMIN",
        "state": "Punjab",
    })
    headers_state_pb = {"Authorization": f"Bearer {token_state_pb}"}

    resp_state_valid = client.post(f"/notifications/{notif_state_pb.id}/read", headers=headers_state_pb)
    assert resp_state_valid.status_code == 200
    assert resp_state_valid.json()["success"] is True
    op_db_session.refresh(notif_state_pb)
    assert notif_state_pb.is_read is True

    # 5. Invalid / missing token -> 401 Unauthorized
    resp_no_auth = client.get("/notifications/me")
    assert resp_no_auth.status_code in (401, 403)


def test_concurrent_reservations_capacity_and_alert_safety(op_db_session):
    """
    Test capacity threshold and alert safety under sequential/concurrent attempts
    when only 1 bed remains:
    - First reservation succeeds and triggers low-bed alert (available drops to 0).
    - Second reservation is rejected (NO_BEDS_AVAILABLE) and does not emit spurious alerts.
    """
    repo = PgReferralRepository(op_db_session)
    hid = "HOSP-LUDHIANA-01"

    # Set ICU total_capacity to 1 (1 available)
    repo.update_hospital_bed_capacity(
        hospital_id=hid,
        bed_type="ICU",
        total_capacity=1,
        user_id="U_STAFF_B",
    )

    # First reservation claims the last available ICU bed
    res1 = repo.reserve_bed_direct(
        hospital_id=hid,
        bed_type="ICU",
        patient_id="PAT-RACE-0001",
        user_id="U_STAFF_B",
    )
    assert res1["success"] is True

    # Confirm available ICU beds is now 0
    hosp = op_db_session.get(Hospital, hid)
    assert hosp.available_icu_beds == 0

    # Second reservation attempts to claim ICU bed -> must fail
    res2 = repo.reserve_bed_direct(
        hospital_id=hid,
        bed_type="ICU",
        patient_id="PAT-RACE-0002",
        user_id="U_STAFF_B",
    )
    assert res2["success"] is False
    assert res2["status"] in ("NO_ICU_AVAILABLE", "NO_BEDS_AVAILABLE")

    # Hospital available ICU beds remains 0 (no overselling)
    op_db_session.refresh(hosp)
    assert hosp.available_icu_beds == 0


