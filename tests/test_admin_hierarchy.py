import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.jwt_utils import create_access_token

client = TestClient(app)


@pytest.fixture
def hospital_token():
    user = {
        "user_id": "USR000001",
        "username": "gh00046",
        "role": "HOSPITAL",
        "hospital_id": "GH00046",
        "state": "Punjab",
        "district": "Amritsar",
    }
    return create_access_token(user)


@pytest.fixture
def amritsar_district_token():
    user = {
        "user_id": "USR000006",
        "username": "amritsar_district_admin",
        "role": "DISTRICT_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": "Amritsar",
    }
    return create_access_token(user)


@pytest.fixture
def ludhiana_district_token():
    user = {
        "user_id": "USR000007",
        "username": "ludhiana_district_admin",
        "role": "DISTRICT_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": "Ludhiana",
    }
    return create_access_token(user)


@pytest.fixture
def punjab_state_token():
    user = {
        "user_id": "USR000003",
        "username": "punjab_admin",
        "role": "STATE_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": None,
    }
    return create_access_token(user)


@pytest.fixture
def central_admin_token():
    user = {
        "user_id": "USR000004",
        "username": "central_admin",
        "role": "CENTRAL_ADMIN",
        "hospital_id": None,
        "state": None,
        "district": None,
    }
    return create_access_token(user)


# ------------------------------------------------------------
# District Administration Tests
# ------------------------------------------------------------

def test_district_overview_authorized(amritsar_district_token):
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["district"] == "Amritsar"
    assert "metrics" in data
    assert data["metrics"]["total_hospitals"] > 0
    assert "total_beds" in data["metrics"]
    assert "available_icu_beds" in data["metrics"]


def test_district_hospitals_authorized(amritsar_district_token):
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/hospitals", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["hospitals"]) > 0
    for h in data["hospitals"]:
        assert h["district"].lower() == "amritsar"


def test_cross_district_access_blocked(amritsar_district_token):
    # Amritsar admin attempting to query Ludhiana -> MUST be 403
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/overview?district=Ludhiana", headers=headers)
    assert resp.status_code == 403
    assert "only authorized to view district 'Amritsar'" in resp.json()["detail"]


def test_hospital_user_cannot_access_district_overview(hospital_token):
    headers = {"Authorization": f"Bearer {hospital_token}"}
    resp = client.get("/district/overview", headers=headers)
    assert resp.status_code == 403


# ------------------------------------------------------------
# State Administration Tests
# ------------------------------------------------------------

def test_state_overview_authorized(punjab_state_token):
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/state/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["state"] == "Punjab"
    assert data["metrics"]["total_hospitals"] > 0
    assert len(data["districts"]) > 0


def test_cross_state_access_blocked(punjab_state_token):
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/state/overview?state=Maharashtra", headers=headers)
    assert resp.status_code == 403
    assert "only authorized for state 'Punjab'" in resp.json()["detail"]


def test_district_admin_cannot_access_state_overview(amritsar_district_token):
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/state/overview", headers=headers)
    assert resp.status_code == 403


# ------------------------------------------------------------
# Central Administration Tests
# ------------------------------------------------------------

def test_central_overview_authorized(central_admin_token):
    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["metrics"]["participating_states"] > 0
    assert data["metrics"]["total_hospitals"] >= 100
    assert len(data["states"]) > 0


def test_state_admin_cannot_access_central_overview(punjab_state_token):
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/central/overview", headers=headers)
    assert resp.status_code == 403
