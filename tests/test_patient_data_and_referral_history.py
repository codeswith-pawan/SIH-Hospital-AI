"""
Regression test suite for patient-specific data, recommendation zero-matches,
referral history scoping, clinical field consistency, and missing/null optional fields.
"""

import pytest
from starlette.testclient import TestClient
from src.api.main import app
from src.prediction.feature_builder import build_referral_features
from src.utils.referral_rules import check_bed_availability, evaluate_hospital_capability


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers_gh00046(client):
    res = client.post("/login", json={"username": "gh00046", "password": "hospital123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def auth_headers_other_hospital(client):
    res = client.post("/login", json={"username": "gh_test_other", "password": "hospital123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# 1. A patient with valid hospital recommendations (e.g. PAT000005)
def test_patient_with_valid_recommendations(client):
    res = client.get("/hospitals?patient_id=PAT000005")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000005"
    assert data["priority"] == "Urgent"
    assert data["total_hospitals"] > 0
    assert len(data["hospitals"]) == data["total_hospitals"]
    h0 = data["hospitals"][0]
    assert h0["hospital_id"] != ""
    assert h0["hospital_name"] != ""
    assert h0["distance_km"] is not None
    assert h0["final_score"] is not None


# 2. A valid patient with zero eligible hospitals (or referral not required, e.g. PAT000004)
def test_valid_patient_referral_not_indicated(client):
    res = client.get("/hospitals?patient_id=PAT000004")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000004"
    assert data["total_hospitals"] == 0
    assert data["priority"] == "Stable"
    assert data["referral_required"] == "No"
    assert data["message"] == "Hospital referral is not clinically required for this patient."
    assert "manageable locally" in data["reason"]
    assert data["hospitals"] == []


# 3. An unknown patient ID
def test_unknown_patient_id(client, auth_headers_gh00046):
    # Recommendations
    res_rec = client.get("/hospitals?patient_id=PAT999999")
    assert res_rec.status_code == 404
    assert "not found" in res_rec.json()["detail"].lower()

    # Referral history
    res_ref = client.get("/patients/PAT999999/referrals", headers=auth_headers_gh00046)
    assert res_ref.status_code == 404
    assert "not found" in res_ref.json()["detail"].lower()


# 4. A patient with referral history (e.g. PAT000005 viewed by destination GH00046)
def test_patient_with_referral_history(client, auth_headers_gh00046):
    res = client.get("/patients/PAT000005/referrals", headers=auth_headers_gh00046)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000005"
    assert data["total_referrals"] >= 2
    assert data["scope_restricted"] is False
    assert len(data["referrals"]) == data["total_referrals"]
    # Check referral fields
    ref_ids = [r["referral_id"] for r in data["referrals"]]
    assert "REF-2026-000006" in ref_ids
    assert "REF-2026-000007" in ref_ids


# 5. A patient with no referral history (e.g. PAT000004)
def test_patient_with_no_referral_history(client, auth_headers_gh00046):
    res = client.get("/patients/PAT000004/referrals", headers=auth_headers_gh00046)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000004"
    assert data["total_referrals"] == 0
    assert data["total_system_referrals"] == 0
    assert data["scope_restricted"] is False
    assert data["referrals"] == []
    assert "No referral records exist" in data["message"]


# 6. Referral-history API failure (unauthenticated access or invalid patient ID)
def test_referral_history_unauthenticated_and_invalid(client, auth_headers_gh00046):
    # Unauthenticated -> 401
    res_unauth = client.get("/patients/PAT000005/referrals")
    assert res_unauth.status_code == 401

    # Empty patient ID -> 400
    res_empty = client.get("/patients/%20/referrals", headers=auth_headers_gh00046)
    assert res_empty.status_code == 400
    assert "required" in res_empty.json()["detail"].lower()


# 7. Patient/referral clinical-field consistency
def test_patient_referral_clinical_consistency(client, auth_headers_gh00046):
    """
    Verify PAT000005 clinical status across endpoints:
    - Base patient demographic record: Trauma, Urgent priority, icu_required=No
    - Historical transfer referrals: Transfer from GH00119 to GH00046 with Critical priority
    """
    res_rec = client.get("/hospitals?patient_id=PAT000005")
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert rec_data["priority"] == "Urgent"

    res_ref = client.get("/patients/PAT000005/referrals", headers=auth_headers_gh00046)
    assert res_ref.status_code == 200
    ref_data = res_ref.json()
    for ref in ref_data["referrals"]:
        assert ref["patient_id"] == "PAT000005"
        assert ref["to_hospital_id"] == "GH00046"
        assert ref["priority"] == "CRITICAL"


# 8. Hospital authorization restrictions on patient history
def test_hospital_authorization_scoping_on_patient_history(client, auth_headers_other_hospital):
    """
    When GH_TEST_OTHER requests PAT000005 referrals, they should be filtered out
    and scope_restricted set to True because GH_TEST_OTHER is neither source nor destination.
    """
    res = client.get("/patients/PAT000005/referrals", headers=auth_headers_other_hospital)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000005"
    assert data["total_referrals"] == 0
    assert data["total_system_referrals"] >= 2
    assert data["scope_restricted"] is True
    assert "restricted" in data["message"].lower()


# 9. Missing or null optional clinical fields
def test_missing_or_null_optional_clinical_fields():
    """Verify that build_referral_features and capability checks handle missing/NaN coordinates and fields."""
    partial_patient = {
        "patient_id": "PAT_TEST_PARTIAL",
        "disease": None,
        "latitude": None,
        "longitude": None,
        "priority": None,
        "icu_required": None,
        "spo2": None,
    }

    dummy_hospital = {
        "hospital_id": "GH00001",
        "latitude": "31.5",
        "longitude": "74.8",
        "available_beds": 10,
        "available_icu_beds": 2,
        "available_emergency_beds": 1,
        "total_beds": 100,
        "occupied_beds": 80,
        "emergency_24x7": "Yes",
        "ambulance": "Yes",
        "oxygen_support": "Yes",
        "ventilator": "Yes",
        "blood_bank": "Yes",
        "general_medicine": "Yes",
        "accepts_referral": "Yes",
    }

    # Should not throw exception despite all optional fields being None
    features = build_referral_features(partial_patient, dummy_hospital)
    assert features["distance_km"] == 50.0  # Safe fallback
    assert features["bed_match"] == 1
    assert features["icu_match"] == 1

    bed_avail = check_bed_availability(partial_patient, dummy_hospital)
    assert bed_avail is True

    capability = evaluate_hospital_capability(partial_patient, dummy_hospital)
    assert capability["eligible"] is True


# 10. Patient requiring ICU destination filtering
def test_patient_requiring_icu_destination_filtering(client):
    """Verify that a patient requiring ICU (e.g. PAT000002) only matches hospitals with available ICU beds."""
    res = client.get("/hospitals?patient_id=PAT000002")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["patient_id"] == "PAT000002"
    assert data["priority"] == "Critical"
    assert data["total_hospitals"] > 0
    for h in data["hospitals"]:
        assert h["available_icu_beds"] > 0
        assert h["icu_beds"] > 0
        assert 0.0 <= h["success_probability"] <= 1.0


# 11. Patient with no eligible destination
def test_patient_with_no_eligible_destination(client):
    """Verify that a patient requiring an unavailable specialty returns 0 eligible hospitals gracefully."""
    from src.api.main import get_cached_patient
    _ = get_cached_patient("PAT000001")
    from src.api import main

    main._PATIENTS_CACHE["PAT_TEST_NO_DEST"] = {
        "patient_id": "PAT_TEST_NO_DEST",
        "disease": "UltraRareDisorder",
        "required_test_1": "non_existent_diagnostic_999",
        "priority": "Critical",
        "referral_required": "Yes",
        "icu_required": "Yes",
        "latitude": 31.63,
        "longitude": 74.87,
        "spo2": 85,
        "first_name": "No",
        "last_name": "Dest",
        "age": 60,
        "gender": "Male",
    }
    try:
        res = client.get("/hospitals?patient_id=PAT_TEST_NO_DEST")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["total_hospitals"] == 0
        assert "No eligible hospitals found" in data["message"]
    finally:
        main._PATIENTS_CACHE.pop("PAT_TEST_NO_DEST", None)


# 12. Patient with missing or invalid location data
def test_patient_with_missing_location_fallback(client):
    """Verify that a patient with missing/None coordinates safely falls back to default distance."""
    from src.api.main import get_cached_patient
    _ = get_cached_patient("PAT000001")
    from src.api import main

    main._PATIENTS_CACHE["PAT_TEST_NO_GEO"] = {
        "patient_id": "PAT_TEST_NO_GEO",
        "disease": "Trauma",
        "priority": "Urgent",
        "referral_required": "Yes",
        "icu_required": "No",
        "latitude": None,
        "longitude": None,
        "spo2": 95,
        "first_name": "No",
        "last_name": "Geo",
        "age": 30,
        "gender": "Female",
    }
    try:
        res = client.get("/hospitals?patient_id=PAT_TEST_NO_GEO")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["total_hospitals"] > 0
        for h in data["hospitals"]:
            assert h["distance_km"] == 50.0  # safe fallback distance
    finally:
        main._PATIENTS_CACHE.pop("PAT_TEST_NO_GEO", None)

