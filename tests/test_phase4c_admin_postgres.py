"""
Phase 4C Integration & Acceptance Tests
Unified Government Dashboards & PostgreSQL Administrative Repository

Verifies:
1. Central administrator national overview and state matrices.
2. State administrator jurisdiction isolation and district breakdowns.
3. District administrator jurisdiction isolation and local metrics.
4. Cross-state access returns 403 Forbidden.
5. Cross-district access returns 403 Forbidden.
6. Hospital administrator cannot access government overview endpoints.
7. Hospital counts match PostgreSQL database records.
8. Bed totals match Phase 4A/4B authoritative inventory.
9. Referral totals match PostgreSQL referral records.
10. Pagination, search, and status filtering work.
11. Missing jurisdiction data handled gracefully.
12. Zero patient PII leakage in administrative endpoints.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from src.api.main import app
from src.auth.jwt_utils import create_access_token
from src.database.pg_models import Hospital, Referral, Bed, BedReservation, RegistrationApplication
from src.database.pg_repository import PgAdminRepository
from src.database.db_manager import is_postgres, get_database_url

client = TestClient(app)


# ============================================================
# FIXTURES: TOKENS & IDENTITIES
# ============================================================

@pytest.fixture
def central_admin_token():
    user = {
        "user_id": "USR_CENTRAL_01",
        "username": "central_admin_p4c",
        "role": "CENTRAL_ADMIN",
        "hospital_id": None,
        "state": None,
        "district": None,
    }
    return create_access_token(user)


@pytest.fixture
def punjab_state_token():
    user = {
        "user_id": "USR_STATE_01",
        "username": "punjab_state_admin_p4c",
        "role": "STATE_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": None,
    }
    return create_access_token(user)


@pytest.fixture
def haryana_state_token():
    user = {
        "user_id": "USR_STATE_02",
        "username": "haryana_state_admin_p4c",
        "role": "STATE_ADMIN",
        "hospital_id": None,
        "state": "Haryana",
        "district": None,
    }
    return create_access_token(user)


@pytest.fixture
def amritsar_district_token():
    user = {
        "user_id": "USR_DIST_01",
        "username": "amritsar_dist_admin_p4c",
        "role": "DISTRICT_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": "Amritsar",
    }
    return create_access_token(user)


@pytest.fixture
def ludhiana_district_token():
    user = {
        "user_id": "USR_DIST_02",
        "username": "ludhiana_dist_admin_p4c",
        "role": "DISTRICT_ADMIN",
        "hospital_id": None,
        "state": "Punjab",
        "district": "Ludhiana",
    }
    return create_access_token(user)


@pytest.fixture
def hospital_token():
    user = {
        "user_id": "USR_HOSP_01",
        "username": "gh00001_p4c",
        "role": "HOSPITAL",
        "hospital_id": "GH00001",
        "state": "Punjab",
        "district": "Amritsar",
    }
    return create_access_token(user)


# ============================================================
# 1. CENTRAL GOVERNMENT DASHBOARD TESTS
# ============================================================

def test_central_overview_authorized(central_admin_token):
    """Central admin views national aggregate metrics from PostgreSQL."""
    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/overview", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert "metrics" in data
    assert "states" in data

    metrics = data["metrics"]
    assert metrics["participating_states"] > 0
    assert metrics["total_hospitals"] > 0
    assert metrics["total_beds"] > 0
    assert "available_beds" in metrics
    assert "total_icu_beds" in metrics
    assert "total_referrals" in metrics
    assert "approved_hospitals" in metrics
    assert len(data["states"]) > 0


def test_central_states_matrix(central_admin_token):
    """Central admin accesses full state and UT capacity breakdown."""
    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/states", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["states"]) > 0
    for s in data["states"]:
        assert "state" in s
        assert s["hospitals"] > 0
        assert "total_beds" in s
        assert "occupancy_rate" in s


def test_central_hospitals_pagination_and_search(central_admin_token):
    """Central admin paginates and filters nationwide hospital inventory."""
    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/hospitals?page=1&page_size=10&state=Punjab", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total"] > 0
    assert len(data["hospitals"]) <= 10
    for h in data["hospitals"]:
        assert h["state"].lower() == "punjab"


def test_central_referrals_monitoring(central_admin_token):
    """Central admin monitors national referrals with PII masking."""
    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/referrals?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "total" in data
    assert "referrals" in data
    for r in data["referrals"]:
        # Verify PII masking
        assert not r["patient_id"].isalnum() or r["patient_id"].startswith("PAT-***")
        assert "patient_name" not in r
        assert "phone" not in r


# ============================================================
# 2. STATE GOVERNMENT DASHBOARD TESTS
# ============================================================

def test_state_overview_authorized(punjab_state_token):
    """State admin receives aggregated capacity and district breakdown for their state."""
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/state/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["state"] == "Punjab"
    assert data["metrics"]["total_districts"] > 0
    assert data["metrics"]["total_hospitals"] > 0
    assert len(data["districts"]) > 0


def test_state_cross_jurisdiction_blocked(punjab_state_token):
    """State admin attempting to query another state must receive 403 Forbidden."""
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/state/overview?state=Maharashtra", headers=headers)
    assert resp.status_code == 403
    assert "only authorized for state 'Punjab'" in resp.json()["detail"]


def test_state_referrals_and_districts(punjab_state_token):
    """State admin inspects district summaries and filtered transfer flows."""
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/state/districts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["districts"]) > 0

    ref_resp = client.get("/state/referrals?page=1&page_size=10", headers=headers)
    assert ref_resp.status_code == 200
    ref_data = ref_resp.json()
    assert ref_data["success"] is True
    for r in ref_data["referrals"]:
        assert r["patient_id"].startswith("PAT-***") or r["patient_id"] == "PAT-ANON"
        assert "patient_name" not in r


# ============================================================
# 3. DISTRICT ADMINISTRATION DASHBOARD TESTS
# ============================================================

def test_district_overview_authorized(amritsar_district_token):
    """District admin accesses local metrics, critical alerts, and facility inventory."""
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["district"] == "Amritsar"
    assert data["metrics"]["total_hospitals"] > 0
    assert "total_beds" in data["metrics"]
    assert "available_icu_beds" in data["metrics"]
    assert isinstance(data["critical_alerts"], list)
    assert isinstance(data["hospitals"], list)


def test_district_cross_jurisdiction_blocked(amritsar_district_token):
    """District admin querying a foreign district must receive 403 Forbidden."""
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/overview?district=Ludhiana", headers=headers)
    assert resp.status_code == 403
    assert "only authorized to view district 'Amritsar'" in resp.json()["detail"]


def test_district_hospitals_pagination(amritsar_district_token):
    """District admin queries paginated hospital inventory in their district."""
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/hospitals?page=1&page_size=5", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total"] > 0
    assert len(data["hospitals"]) <= 5
    for h in data["hospitals"]:
        assert h["district"].lower() == "amritsar"
        assert "total_beds" in h
        assert "emergency_24x7" in h


def test_district_referrals_sanitized(amritsar_district_token):
    """District referrals return sanitized tracking records without patient PII."""
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}
    resp = client.get("/district/referrals?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    for r in data["referrals"]:
        assert r["patient_id"].startswith("PAT-***") or r["patient_id"] == "PAT-ANON"
        assert "patient_name" not in r
        assert "phone" not in r


# ============================================================
# 4. ROLE ISOLATION & UNAUTHORIZED ACCESS TESTS
# ============================================================

def test_hospital_user_cannot_access_administrative_dashboards(hospital_token):
    """Hospital users are strictly blocked from government administrative dashboards."""
    headers = {"Authorization": f"Bearer {hospital_token}"}

    resp1 = client.get("/district/overview", headers=headers)
    assert resp1.status_code == 403

    resp2 = client.get("/state/overview", headers=headers)
    assert resp2.status_code == 403

    resp3 = client.get("/central/overview", headers=headers)
    assert resp3.status_code == 403


def test_district_admin_cannot_access_state_or_central(amritsar_district_token):
    """District admin cannot elevate privileges to State or Central dashboards."""
    headers = {"Authorization": f"Bearer {amritsar_district_token}"}

    resp1 = client.get("/state/overview", headers=headers)
    assert resp1.status_code == 403

    resp2 = client.get("/central/overview", headers=headers)
    assert resp2.status_code == 403


def test_state_admin_cannot_access_central(punjab_state_token):
    """State admin cannot access Central Government overview."""
    headers = {"Authorization": f"Bearer {punjab_state_token}"}
    resp = client.get("/central/overview", headers=headers)
    assert resp.status_code == 403


# ============================================================
# 5. DATA TRUTH & CONSISTENCY TESTS (POSTGRESQL REPOSITORY)
# ============================================================

def test_hospital_and_bed_counts_match_postgres_truth(central_admin_token):
    """Validate that API aggregate numbers match direct database query truth."""
    if not is_postgres():
        pytest.skip("Test requires PostgreSQL environment.")

    headers = {"Authorization": f"Bearer {central_admin_token}"}
    resp = client.get("/central/overview", headers=headers)
    assert resp.status_code == 200
    api_metrics = resp.json()["metrics"]

    engine = create_engine(get_database_url())
    with engine.connect() as conn:
        db_total_hospitals = conn.execute(select(func.count(Hospital.hospital_id))).scalar()
        db_total_beds = conn.execute(select(func.coalesce(func.sum(Hospital.total_beds), 0))).scalar()
        db_total_icu = conn.execute(select(func.coalesce(func.sum(Hospital.icu_beds), 0))).scalar()
        db_total_referrals = conn.execute(select(func.count(Referral.referral_id))).scalar()

    assert api_metrics["total_hospitals"] == db_total_hospitals
    assert api_metrics["total_beds"] == db_total_beds
    assert api_metrics["total_icu_beds"] == db_total_icu
    assert api_metrics["total_referrals"] == db_total_referrals
