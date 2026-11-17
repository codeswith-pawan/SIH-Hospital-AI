"""
Operational Inventory & Bed Management Test Suite (Phase 4A)
AI Powered Smart Hospital Referral System
Target Database: sih_hospital_phase1_run_test
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.database.pg_models import (
    PgBase,
    Hospital,
    User,
    Bed,
    BedReservation,
    AuditLog,
    RegistrationApplication,
    AccountActivationToken,
)
from src.database.pg_repository import PgReferralRepository
from src.services.account_provisioning_service import AccountProvisioningService
from src.auth.jwt_utils import create_access_token
from src.api.main import app

TEST_DB_URL = "postgresql://localhost:5432/sih_hospital_phase1_run_test"


@pytest.fixture(scope="module")
def pg_engine():
    """Engine bound strictly to the isolated test database."""
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """Transactional session per test."""
    Session = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def api_client(pg_session, monkeypatch):
    """TestClient overriding get_db_session to use the isolated test session."""
    from src.database.db_manager import get_db_session
    def _override_get_db_session():
        yield pg_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _create_test_hospital_and_user(session, hospital_id: str, role_id: str = "HOSPITAL", total_beds: int = 20, icu_beds: int = 5):
    """Helper to seed hospital and user."""
    now = datetime.now(timezone.utc)
    hosp = Hospital(
        hospital_id=hospital_id,
        name=f"Test Hospital {hospital_id}",
        state="Punjab",
        district="Amritsar",
        city="Amritsar",
        latitude=31.63,
        longitude=74.87,
        total_beds=total_beds,
        available_beds=total_beds,
        occupied_beds=0,
        icu_beds=icu_beds,
        available_icu_beds=icu_beds,
        emergency_beds=5,
        available_emergency_beds=5,
        oxygen_support="Yes",
        ventilator="Yes",
        ambulance="Yes",
        blood_bank="Yes",
        emergency_24x7="Yes",
        approval_status="APPROVED",
        is_grandfathered=False,
        approved_at=now,
    )
    session.add(hosp)

    user = User(
        user_id=f"U_{hospital_id}",
        username=f"admin_{hospital_id.lower()}",
        name=f"Admin {hospital_id}",
        password_hash="TEST_HASH",
        role_id=role_id,
        hospital_id=hospital_id if role_id == "HOSPITAL" else None,
        state="Punjab",
        district="Amritsar",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return hosp, user


# ============================================================
# 1. NEWLY PROVISIONED HOSPITAL RECEIVES INVENTORY RECORDS
# ============================================================

def test_newly_provisioned_hospital_receives_inventory_records(pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    app_id = f"APP_{uuid.uuid4().hex[:8].upper()}"
    app_num = f"SIH-HOSP-2026-{uuid.uuid4().hex[:4].upper()}"

    app_rec = RegistrationApplication(
        application_id=app_id,
        application_number=app_num,
        applicant_type="HOSPITAL",
        applicant_name=f"Auto Hospital {hosp_id}",
        applicant_email=f"contact_{hosp_id.lower()}@hospital.gov.in",
        applicant_phone="9876543210",
        state="Punjab",
        district="Amritsar",
        city="Amritsar",
        address="Sector 14 Medical Enclave",
        pincode="143001",
        status="APPROVED",
        current_stage="CENTRAL_REVIEW",
        profile_data={
            "total_beds": 30,
            "icu_beds": 6,
            "emergency_beds": 4,
            "oxygen_support": "Yes",
            "ventilator": "Yes",
        },
    )
    pg_session.add(app_rec)
    pg_session.flush()

    prov_svc = AccountProvisioningService(pg_session)
    res = prov_svc.provision_account(
        app_rec.application_id,
        reviewer_user={"user_id": "U_CENTRAL_01", "role": "CENTRAL_ADMIN"},
    )

    assert res["is_already_provisioned"] is False
    prov_hosp_id = res["hospital_id"]
    assert prov_hosp_id is not None

    # Verify Bed records created in PostgreSQL
    beds = pg_session.execute(select(Bed).where(Bed.hospital_id == prov_hosp_id)).scalars().all()
    assert len(beds) > 0

    gen_beds = [b for b in beds if b.bed_type == "GENERAL"]
    icu_beds = [b for b in beds if b.bed_type == "ICU"]
    emg_beds = [b for b in beds if b.bed_type == "EMERGENCY"]

    assert len(gen_beds) == 20  # 30 total - 6 icu - 4 emergency
    assert len(icu_beds) == 6
    assert len(emg_beds) == 4

    repo = PgReferralRepository(pg_session)
    inv = repo.get_hospital_inventory(prov_hosp_id)
    assert inv is not None
    assert inv["available_beds"] == 20
    assert inv["available_icu_beds"] == 6
    assert inv["available_emergency_beds"] == 4
    assert inv["total_capacity"] == 30
    assert inv["is_configured"] is True


# ============================================================
# 2. REPEATED PROVISIONING DOES NOT CREATE DUPLICATE RECORDS
# ============================================================

def test_repeated_provisioning_does_not_create_duplicate_records(pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    app_id = f"APP_{uuid.uuid4().hex[:8].upper()}"
    app_rec = RegistrationApplication(
        application_id=app_id,
        application_number=f"SIH-DUP-{uuid.uuid4().hex[:4].upper()}",
        applicant_type="HOSPITAL",
        applicant_name=f"Dup Test Hospital {hosp_id}",
        applicant_email=f"dup_{hosp_id.lower()}@hospital.gov.in",
        applicant_phone="9876543211",
        state="Punjab",
        district="Amritsar",
        status="APPROVED",
        current_stage="CENTRAL_REVIEW",
        profile_data={"total_beds": 15, "icu_beds": 3, "emergency_beds": 2},
    )
    pg_session.add(app_rec)
    pg_session.flush()

    prov_svc = AccountProvisioningService(pg_session)
    reviewer = {"user_id": "U_CENTRAL_01", "role": "CENTRAL_ADMIN"}
    res1 = prov_svc.provision_account(app_rec.application_id, reviewer_user=reviewer)
    prov_hosp_id = res1["hospital_id"]

    initial_bed_count = pg_session.execute(
        select(Bed).where(Bed.hospital_id == prov_hosp_id)
    ).scalars().all()
    count_1 = len(initial_bed_count)
    assert count_1 > 0

    # Repeat provisioning
    res2 = prov_svc.provision_account(app_rec.application_id, reviewer_user=reviewer)
    assert res2["is_already_provisioned"] is True

    beds_after = pg_session.execute(
        select(Bed).where(Bed.hospital_id == prov_hosp_id)
    ).scalars().all()
    assert len(beds_after) == count_1


# ============================================================
# 3. EXISTING HOSPITAL INVENTORY REMAINS UNCHANGED
# ============================================================

def test_existing_hospital_inventory_remains_unchanged(pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    _create_test_hospital_and_user(pg_session, hosp_id, total_beds=25, icu_beds=5)

    repo = PgReferralRepository(pg_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 15, "ICU": 5, "EMERGENCY": 5})

    inv_before = repo.get_hospital_inventory(hosp_id)

    # Re-running initialize_default_inventory should not overwrite or add extra beds
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 15, "ICU": 5, "EMERGENCY": 5})
    inv_after = repo.get_hospital_inventory(hosp_id)

    assert inv_before["available_beds"] == inv_after["available_beds"] == 15
    assert inv_before["available_icu_beds"] == inv_after["available_icu_beds"] == 5
    assert inv_before["total_capacity"] == inv_after["total_capacity"] == 25


# ============================================================
# 4. INVENTORY GET RETURNS HTTP 200 FOR CORRECTLY PROVISIONED HOSPITAL
# ============================================================

def test_inventory_get_returns_http_200_for_correctly_provisioned_hospital(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id, total_beds=18, icu_beds=4)

    repo = PgReferralRepository(pg_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 10, "ICU": 4, "EMERGENCY": 4})
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.get(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["hospital_id"] == hosp_id
    assert "inventory" in data
    inv = data["inventory"]
    assert inv["available_beds"] == 10
    assert inv["available_icu_beds"] == 4
    assert inv["available_emergency_beds"] == 4
    assert inv["is_configured"] is True


# ============================================================
# 5. UNCONFIGURED INVENTORY RETURNS A CONTROLLED RESPONSE
# ============================================================

def test_unconfigured_inventory_returns_controlled_response(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id, total_beds=0, icu_beds=0)
    hosp.available_beds = 0
    hosp.available_icu_beds = 0
    hosp.emergency_beds = 0
    hosp.available_emergency_beds = 0
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.get(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    inv = data["inventory"]
    assert inv["is_configured"] is False
    assert inv["total_capacity"] == 0


# ============================================================
# 6. CAPACITY UPDATES SUCCEED WITH VALID DATA
# ============================================================

def test_capacity_updates_succeed_with_valid_data(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id)
    repo = PgReferralRepository(pg_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 10, "ICU": 3, "EMERGENCY": 3})
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.put(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
        json={"bed_type": "ICU", "total_capacity": 8},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    inv = data["inventory"]
    assert inv["total_icu_beds"] == 8
    assert inv["available_icu_beds"] == 8

    # Verify in DB
    updated_beds = pg_session.execute(
        select(Bed).where(Bed.hospital_id == hosp_id, Bed.bed_type == "ICU")
    ).scalars().all()
    assert len(updated_beds) == 8


# ============================================================
# 7. NEGATIVE CAPACITY IS REJECTED
# ============================================================

def test_negative_capacity_is_rejected(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id)
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.put(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
        json={"bed_type": "ICU", "total_capacity": -3},
    )

    assert resp.status_code == 422


# ============================================================
# 8. CAPACITY BELOW OCCUPIED PLUS RESERVED IS REJECTED
# ============================================================

def test_capacity_below_occupied_plus_reserved_is_rejected(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id)
    repo = PgReferralRepository(pg_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 10, "ICU": 4, "EMERGENCY": 2})

    # Mark 2 ICU beds as occupied/reserved
    icu_beds = pg_session.execute(
        select(Bed).where(Bed.hospital_id == hosp_id, Bed.bed_type == "ICU")
    ).scalars().all()
    icu_beds[0].status = "OCCUPIED"
    icu_beds[1].status = "RESERVED"
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    # Reducing to 1 when occupied(1)+reserved(1) = 2 should fail
    resp = api_client.put(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
        json={"bed_type": "ICU", "total_capacity": 1},
    )

    assert resp.status_code == 422
    assert "occupied and 1 reserved" in resp.json()["detail"].lower()


# ============================================================
# 9. CROSS-HOSPITAL ACCESS IS DENIED
# ============================================================

def test_cross_hospital_access_is_denied(api_client, pg_session):
    hosp_a = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp_b = f"GH{uuid.uuid4().hex[:5].upper()}"
    _create_test_hospital_and_user(pg_session, hosp_a)
    _, user_b = _create_test_hospital_and_user(pg_session, hosp_b)
    pg_session.commit()

    # User B tries to read/write Hospital A
    token_b = create_access_token({
        "user_id": user_b.user_id,
        "username": user_b.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_b,
        "state": "Punjab",
        "district": "Amritsar",
    })

    get_resp = api_client.get(
        f"/hospitals/{hosp_a}/inventory",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_resp.status_code == 403

    put_resp = api_client.put(
        f"/hospitals/{hosp_a}/inventory",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"bed_type": "GENERAL", "total_capacity": 50},
    )
    assert put_resp.status_code == 403


# ============================================================
# 10. UNAUTHORIZED ROLES CANNOT UPDATE INVENTORY
# ============================================================

def test_unauthorized_roles_cannot_update_inventory(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    _create_test_hospital_and_user(pg_session, hosp_id)
    pg_session.commit()

    # Public or reviewer tokens cannot update inventory
    token_rev = create_access_token({
        "user_id": "U_REV_01",
        "username": "rev_user",
        "role": "REVIEWER",
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.put(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token_rev}"},
        json={"bed_type": "GENERAL", "total_capacity": 30},
    )
    assert resp.status_code == 403


# ============================================================
# 11. CONCURRENT CAPACITY UPDATES DO NOT CORRUPT INVENTORY
# ============================================================

def test_concurrent_capacity_updates_do_not_corrupt_inventory(pg_engine):
    Session = sessionmaker(bind=pg_engine, autocommit=False, autoflush=False)
    setup_session = Session()

    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    _create_test_hospital_and_user(setup_session, hosp_id)
    repo = PgReferralRepository(setup_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 10, "ICU": 5, "EMERGENCY": 5})
    setup_session.commit()
    setup_session.close()

    def update_task(target_cap):
        s = Session()
        try:
            r = PgReferralRepository(s)
            r.update_hospital_bed_capacity(hosp_id, "GENERAL", target_cap, user_id="CONCURRENCY_TEST")
            return True
        except Exception:
            s.rollback()
            return False
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(update_task, cap) for cap in [12, 14, 16]]
        results = [f.result() for f in futures]

    assert any(results)

    verify_session = Session()
    final_beds = verify_session.execute(
        select(Bed).where(Bed.hospital_id == hosp_id, Bed.bed_type == "GENERAL")
    ).scalars().all()
    # Check no duplicate bed numbers
    bed_numbers = [b.bed_number for b in final_beds]
    assert len(bed_numbers) == len(set(bed_numbers))
    verify_session.close()


# ============================================================
# 12. EXISTING RESERVATION TESTS COMPATIBILITY
# ============================================================

def test_existing_reservation_tests_continue_passing():
    from src.prediction.bed_reservation import reserve_bed, release_bed, initialize_hospital_beds
    hosp = f"GH_TEST_COMPAT_{uuid.uuid4().hex[:6]}"
    p_id = f"PAT_COMPAT_{uuid.uuid4().hex[:6]}"
    inv = initialize_hospital_beds(
        hospital_id=hosp,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )
    res = reserve_bed(hosp, p_id, "ICU", inv)
    assert res["success"] is True
    assert inv["available_icu_beds"] == 1
    assert inv["reserved_icu_beds"] == 1


# ============================================================
# 13. HOSPITAL DASHBOARD RESPONSE INTEGRITY
# ============================================================

def test_existing_hospital_dashboard_functionality_remains_intact(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id, total_beds=20, icu_beds=5)
    repo = PgReferralRepository(pg_session)
    repo.initialize_default_inventory(hosp_id, capacities={"GENERAL": 12, "ICU": 4, "EMERGENCY": 4})
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.get(
        f"/hospitals/{hosp_id}/inventory",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Top-level legacy keys must be present for HospitalDashboard.tsx
    assert "available_beds" in data
    assert "available_icu_beds" in data
    assert "reserved_beds" in data
    assert "reserved_icu_beds" in data
    assert data["available_beds"] == 12
    assert data["available_icu_beds"] == 4


# ============================================================
# 14. RESOURCES UPDATE VIA PATCH ENDPOINT
# ============================================================

def test_resources_patch_endpoint_updates_postgresql(api_client, pg_session):
    hosp_id = f"GH{uuid.uuid4().hex[:5].upper()}"
    hosp, user = _create_test_hospital_and_user(pg_session, hosp_id)
    pg_session.commit()

    token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role": "HOSPITAL",
        "hospital_id": hosp_id,
        "state": "Punjab",
        "district": "Amritsar",
    })

    resp = api_client.patch(
        f"/hospitals/{hosp_id}/resources",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "oxygen_support": "No",
            "ventilator": "No",
            "ambulance": "Yes",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    inv = data["inventory"]
    assert inv["oxygen_support"] == "No"
    assert inv["ventilator"] == "No"
    assert inv["ambulance"] == "Yes"

    # Verify persisted in PostgreSQL
    h = pg_session.execute(select(Hospital).where(Hospital.hospital_id == hosp_id)).scalar_one()
    assert h.oxygen_support == "No"
    assert h.ventilator == "No"
    assert h.ambulance == "Yes"
