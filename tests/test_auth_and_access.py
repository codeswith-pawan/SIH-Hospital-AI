import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from src.auth.auth_store import (
    hash_password,
    verify_password,
    authenticate_user,
    seed_default_users,
)
from src.auth.authorization import (
    can_access_hospital,
    can_view_referral,
    can_accept_or_reject,
    can_update_referral_status,
    HOSPITAL,
    DISTRICT_ADMIN,
    STATE_ADMIN,
    CENTRAL_ADMIN,
)
from src.auth.jwt_utils import create_access_token, decode_access_token
from src.api.main import app


# ------------------------------------------------------------
# Unit Tests: Password Hashing & Verification
# ------------------------------------------------------------

def test_password_hashing():
    raw = "SuperSecretPassword123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert hashed.startswith("pbkdf2:sha256:100000$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_password_legacy_fallback():
    raw = "legacy_plain_pass"
    assert verify_password(raw, raw) is True
    assert verify_password("other", raw) is False


# ------------------------------------------------------------
# Unit Tests: JWT Tokens
# ------------------------------------------------------------

def test_jwt_generation_and_decoding():
    user = {
        "user_id": "USR_TEST_1",
        "username": "test_hospital",
        "role": "HOSPITAL",
        "hospital_id": "GH00046",
        "state": "Punjab",
        "district": "Amritsar",
    }
    token = create_access_token(user)
    assert token is not None
    decoded = decode_access_token(token)
    assert decoded["sub"] == "USR_TEST_1"
    assert decoded["role"] == "HOSPITAL"
    assert decoded["hospital_id"] == "GH00046"
    assert decoded["state"] == "Punjab"
    assert decoded["district"] == "Amritsar"


# ------------------------------------------------------------
# Unit Tests: Geographic RBAC Authorization Logic
# ------------------------------------------------------------

def test_hospital_access_isolation():
    hospital_user = {
        "user_id": "U1",
        "role": HOSPITAL,
        "hospital_id": "GH00046",
        "state": "Punjab",
        "district": "Amritsar",
    }

    # Can access own hospital
    assert can_access_hospital(hospital_user, "GH00046") is True

    # Cannot access another hospital even in the same city
    assert can_access_hospital(hospital_user, "GH00119") is False

    # Cannot access another hospital in another district
    assert can_access_hospital(hospital_user, "GH00002") is False


def test_district_admin_isolation():
    amritsar_admin = {
        "user_id": "U2",
        "role": DISTRICT_ADMIN,
        "hospital_id": None,
        "state": "Punjab",
        "district": "Amritsar",
    }

    # Can access hospitals inside Amritsar, Punjab
    assert can_access_hospital(amritsar_admin, "GH00046") is True

    # Cannot access hospital in Ludhiana, Punjab
    ludhiana_geo = {"hospital_id": "GH_LUDHIANA", "state": "Punjab", "district": "Ludhiana"}
    assert can_access_hospital(amritsar_admin, "GH_LUDHIANA", hospital_info=ludhiana_geo) is False

    # Cannot access hospital in Tamil Nadu
    tn_geo = {"hospital_id": "GH_CHENNAI", "state": "Tamil Nadu", "district": "Chennai"}
    assert can_access_hospital(amritsar_admin, "GH_CHENNAI", hospital_info=tn_geo) is False


def test_state_admin_isolation():
    punjab_admin = {
        "user_id": "U3",
        "role": STATE_ADMIN,
        "hospital_id": None,
        "state": "Punjab",
        "district": None,
    }

    # Can access any hospital in Punjab
    assert can_access_hospital(punjab_admin, "GH00046") is True
    ludhiana_geo = {"hospital_id": "GH_LUDHIANA", "state": "Punjab", "district": "Ludhiana"}
    assert can_access_hospital(punjab_admin, "GH_LUDHIANA", hospital_info=ludhiana_geo) is True

    # Cannot access hospital in Tamil Nadu
    tn_geo = {"hospital_id": "GH_CHENNAI", "state": "Tamil Nadu", "district": "Chennai"}
    assert can_access_hospital(punjab_admin, "GH_CHENNAI", hospital_info=tn_geo) is False


def test_central_admin_access():
    central_admin = {
        "user_id": "U4",
        "role": CENTRAL_ADMIN,
        "hospital_id": None,
        "state": None,
        "district": None,
    }
    # Can access any hospital nationwide
    assert can_access_hospital(central_admin, "GH00046") is True
    tn_geo = {"hospital_id": "GH_CHENNAI", "state": "Tamil Nadu", "district": "Chennai"}
    assert can_access_hospital(central_admin, "GH_CHENNAI", hospital_info=tn_geo) is True


# ------------------------------------------------------------
# Unit Tests: Referral View & Lifecycle Permissions
# ------------------------------------------------------------

def test_referral_view_isolation():
    referral = {
        "referral_id": "REF001",
        "from_hospital_id": "GH00046",
        "to_hospital_id": "GH00119",
        "from_state": "Punjab",
        "from_district": "Amritsar",
        "to_state": "Punjab",
        "to_district": "Amritsar",
        "status": "PENDING",
    }

    user_from = {"role": HOSPITAL, "hospital_id": "GH00046"}
    user_to = {"role": HOSPITAL, "hospital_id": "GH00119"}
    user_unrelated = {"role": HOSPITAL, "hospital_id": "GH_TEST_OTHER"}
    user_district = {"role": DISTRICT_ADMIN, "state": "Punjab", "district": "Amritsar"}
    user_other_district = {"role": DISTRICT_ADMIN, "state": "Punjab", "district": "Ludhiana"}
    user_state = {"role": STATE_ADMIN, "state": "Punjab"}
    user_other_state = {"role": STATE_ADMIN, "state": "Maharashtra"}
    user_central = {"role": CENTRAL_ADMIN}

    assert can_view_referral(user_from, referral) is True
    assert can_view_referral(user_to, referral) is True
    assert can_view_referral(user_unrelated, referral) is False
    assert can_view_referral(user_district, referral) is True
    assert can_view_referral(user_other_district, referral) is False
    assert can_view_referral(user_state, referral) is True
    assert can_view_referral(user_other_state, referral) is False
    assert can_view_referral(user_central, referral) is True


def test_referral_clinical_actions():
    referral_pending = {
        "referral_id": "REF001",
        "from_hospital_id": "GH00046",
        "to_hospital_id": "GH00119",
        "status": "PENDING",
    }

    dest_hospital = {"role": HOSPITAL, "hospital_id": "GH00119"}
    source_hospital = {"role": HOSPITAL, "hospital_id": "GH00046"}
    district_admin = {"role": DISTRICT_ADMIN, "state": "Punjab", "district": "Amritsar"}

    # Only destination can accept/reject pending
    assert can_accept_or_reject(dest_hospital, referral_pending) is True
    assert can_accept_or_reject(source_hospital, referral_pending) is False
    assert can_accept_or_reject(district_admin, referral_pending) is False

    # Admins cannot execute clinical transitions
    assert can_update_referral_status(district_admin, referral_pending, "ACCEPTED") is False

    # After ACCEPTED, only source can dispatch IN_TRANSIT
    referral_accepted = dict(referral_pending, status="ACCEPTED")
    assert can_update_referral_status(source_hospital, referral_accepted, "IN_TRANSIT") is True
    assert can_update_referral_status(dest_hospital, referral_accepted, "IN_TRANSIT") is False

    # Destination marks ARRIVED once IN_TRANSIT
    referral_in_transit = dict(referral_pending, status="IN_TRANSIT")
    assert can_update_referral_status(dest_hospital, referral_in_transit, "ARRIVED") is True
    assert can_update_referral_status(source_hospital, referral_in_transit, "ARRIVED") is False


# ------------------------------------------------------------
# Integration Tests: FastAPI Endpoints via TestClient
# ------------------------------------------------------------

client = TestClient(app)


def test_api_login_success():
    response = client.post(
        "/login",
        json={"username": "gh00046", "password": "hospital123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data
    assert data["user"]["hospital_id"] == "GH00046"
    assert data["user"]["role"] == "HOSPITAL"


def test_api_login_invalid_password():
    response = client.post(
        "/login",
        json={"username": "gh00046", "password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_api_unauthorized_cross_hospital_inventory_blocked():
    # Login as GH00046
    login_resp = client.post(
        "/login",
        json={"username": "gh00046", "password": "hospital123"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to access GH00119's inventory -> MUST be 403 Forbidden
    response = client.get("/hospitals/GH00119/inventory", headers=headers)
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


def test_api_unauthorized_cross_hospital_referrals_blocked():
    # Login as GH00046
    login_resp = client.post(
        "/login",
        json={"username": "gh00046", "password": "hospital123"}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to view GH00119's incoming referrals inbox -> MUST be 403 Forbidden
    response = client.get("/hospitals/GH00119/referrals", headers=headers)
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()
