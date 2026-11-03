"""
Tests for AI Recommendation Engine Evaluation, Validation & Explainability
SIH Hospital AI — Phase 20 Integrity & Safety Audit
"""

import math
import pytest
from fastapi.testclient import TestClient
import pandas as pd

from src.api.main import app
from src.utils.referral_rules import (
    evaluate_hospital_capability,
    check_bed_availability,
    check_specialty_availability,
    check_test_availability,
)
from src.prediction.recommendation import (
    generate_recommendation_reason,
    generate_disqualification_reasons,
    get_distance_zone,
)
from src.prediction.ranking_engine import (
    rank_hospitals,
    calculate_hospital_score,
)
from scripts.evaluate_recommendation_engine import (
    dcg_at_k,
    ndcg_at_k,
    evaluate_candidate_cohort,
    evaluate_clinical_scenarios,
)


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. BED AVAILABILITY HARD CONSTRAINT TESTS
# =====================================================================

def test_zero_general_beds_blocks_general_patient():
    """A hospital with 0 available general beds must be hard-blocked for general patients."""
    patient = {
        "patient_id": "P_GEN_01",
        "disease": "Appendicitis",
        "priority": "Urgent",
        "icu_required": "No",
        "spo2": 98,
        "referral_required": "Yes",
    }
    hospital_zero_gen = {
        "hospital_id": "H_NO_GEN",
        "available_beds": 0,
        "available_icu_beds": 10,
        "available_emergency_beds": 5,
        "general_surgery": "Yes",
        "emergency_24x7": "Yes",
        "oxygen_support": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_zero_gen)
    assert cap["eligible"] is False
    assert "General bed unavailable" in cap["hard_blocks"]
    assert check_bed_availability(patient, hospital_zero_gen) is False


def test_zero_icu_beds_blocks_icu_patient():
    """A hospital with 0 ICU beds must be hard-blocked when patient requires ICU."""
    patient = {
        "patient_id": "P_ICU_01",
        "disease": "Heart Attack",
        "priority": "Critical",
        "icu_required": "Yes",
        "spo2": 95,
        "referral_required": "Yes",
    }
    hospital_zero_icu = {
        "hospital_id": "H_NO_ICU",
        "available_beds": 100,
        "available_icu_beds": 0,
        "available_emergency_beds": 5,
        "cardiology": "Yes",
        "emergency_24x7": "Yes",
        "oxygen_support": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_zero_icu)
    assert cap["eligible"] is False
    assert "ICU bed unavailable" in cap["hard_blocks"]
    assert check_bed_availability(patient, hospital_zero_icu) is False


def test_zero_emergency_beds_blocks_critical_patient():
    """A hospital with 0 emergency beds must be hard-blocked for Critical patients."""
    patient = {
        "patient_id": "P_CRIT_01",
        "disease": "Trauma",
        "priority": "Critical",
        "icu_required": "No",
        "spo2": 96,
        "referral_required": "Yes",
    }
    hospital_zero_emg = {
        "hospital_id": "H_NO_EMG",
        "available_beds": 50,
        "available_icu_beds": 5,
        "available_emergency_beds": 0,
        "trauma_unit": "Yes",
        "orthopedics": "Yes",
        "emergency_24x7": "Yes",
        "oxygen_support": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_zero_emg)
    assert cap["eligible"] is False
    assert "Emergency bed unavailable" in cap["hard_blocks"]


def test_missing_or_none_bed_inventory_defaults_to_ineligible():
    """Missing or None available_beds must be treated as 0 and rejected."""
    patient = {
        "patient_id": "P_GEN_NONE",
        "disease": "Fracture",
        "priority": "Stable",
        "icu_required": "No",
        "referral_required": "Yes",
    }
    hospital_none_beds = {
        "hospital_id": "H_NONE_BEDS",
        "available_beds": None,
        "orthopedics": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_none_beds)
    assert cap["eligible"] is False
    assert "General bed unavailable" in cap["hard_blocks"]


def test_wrong_bed_type_rejected():
    """Patient needing ICU cannot be allocated a General bed if ICU is full."""
    patient = {
        "patient_id": "P_WRONG_BED",
        "disease": "Sepsis",
        "priority": "Critical",
        "icu_required": "Yes",
        "referral_required": "Yes",
    }
    hospital_only_gen = {
        "hospital_id": "H_ONLY_GEN",
        "available_beds": 500,
        "available_icu_beds": 0,
        "general_medicine": "Yes",
        "accepts_referral": "Yes",
    }
    assert check_bed_availability(patient, hospital_only_gen) is False
    cap = evaluate_hospital_capability(patient, hospital_only_gen)
    assert cap["eligible"] is False
    assert "ICU bed unavailable" in cap["hard_blocks"]


# =====================================================================
# 2. CAPABILITY & STATUS CONSTRAINTS
# =====================================================================

def test_missing_specialty_blocks_hospital():
    """Stroke patient requiring neurology must be blocked if hospital lacks neurology."""
    patient = {
        "patient_id": "P_SPEC_01",
        "disease": "Stroke",
        "priority": "Critical",
        "referral_required": "Yes",
    }
    hospital_no_neuro = {
        "hospital_id": "H_NO_NEURO",
        "available_beds": 50,
        "available_emergency_beds": 10,
        "neurology": "No",
        "cardiology": "Yes",
        "emergency_24x7": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_no_neuro)
    assert cap["eligible"] is False
    assert any("neurology" in hb.lower() for hb in cap["hard_blocks"])


def test_missing_diagnostic_test_blocks_hospital():
    """Patient requiring CT Scan must be blocked if hospital lacks CT Scan."""
    patient = {
        "patient_id": "P_TEST_01",
        "disease": "Trauma",
        "priority": "Urgent",
        "required_test_1": "CT Scan",
        "referral_required": "Yes",
    }
    hospital_no_ct = {
        "hospital_id": "H_NO_CT",
        "available_beds": 50,
        "trauma_unit": "Yes",
        "ct_scan": "No",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_no_ct)
    assert cap["eligible"] is False
    assert any("ct scan" in hb.lower() for hb in cap["hard_blocks"])


def test_inactive_or_decommissioned_hospital_rejected():
    """Hospital marked as inactive or status INACTIVE must be rejected immediately."""
    patient = {
        "patient_id": "P_INACTIVE_TEST",
        "disease": "Asthma",
        "priority": "Urgent",
        "referral_required": "Yes",
    }
    hospital_inactive = {
        "hospital_id": "H_INACTIVE",
        "available_beds": 100,
        "pulmonology": "Yes",
        "accepts_referral": "Yes",
        "is_active": False,
    }
    cap1 = evaluate_hospital_capability(patient, hospital_inactive)
    assert cap1["eligible"] is False
    assert "Hospital facility is inactive or decommissioned" in cap1["hard_blocks"]

    hospital_closed = {
        "hospital_id": "H_CLOSED",
        "available_beds": 100,
        "pulmonology": "Yes",
        "accepts_referral": "Yes",
        "status": "CLOSED",
    }
    cap2 = evaluate_hospital_capability(patient, hospital_closed)
    assert cap2["eligible"] is False
    assert "Hospital facility is inactive or decommissioned" in cap2["hard_blocks"]


def test_missing_oxygen_support_blocks_hypoxemic_patient():
    """Patient with SpO2 < 94 requires oxygen support."""
    patient = {
        "patient_id": "P_HYPOX_01",
        "disease": "Pneumonia",
        "priority": "Urgent",
        "icu_required": "No",
        "spo2": 89,
        "referral_required": "Yes",
    }
    hospital_no_oxy = {
        "hospital_id": "H_NO_OXY",
        "available_beds": 20,
        "available_icu_beds": 0,
        "pulmonology": "Yes",
        "emergency_24x7": "Yes",
        "oxygen_support": "No",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital_no_oxy)
    assert cap["eligible"] is False
    assert "Oxygen support unavailable" in cap["hard_blocks"]


# =====================================================================
# 3. RANKING METRICS & TWO-STAGE SEPARATION
# =====================================================================

def test_ndcg_at_k_exact_values():
    """Verify DCG and NDCG calculations for binary relevance."""
    assert pytest.approx(ndcg_at_k([1, 0, 0], 3), 0.001) == 1.0
    assert pytest.approx(ndcg_at_k([0, 1, 0], 3), 0.001) == 0.6309
    assert pytest.approx(ndcg_at_k([0, 0, 1], 3), 0.001) == 0.5000
    assert ndcg_at_k([0, 0, 0], 3) == 0.0
    assert ndcg_at_k([], 3) == 0.0


def test_model_ranking_cannot_bypass_safety_constraints():
    """A hospital with high ML probability cannot be ranked or returned if Stage A rejects it."""
    patient = {
        "patient_id": "P_SAFETY_GATE",
        "disease": "Heart Attack",
        "priority": "Critical",
        "icu_required": "Yes",
        "referral_required": "Yes",
    }
    # Unsafe hospital with 0 ICU beds but high ML score
    unsafe_hospital = {
        "hospital_id": "H_UNSAFE_ML",
        "distance_km": 15.0,
        "available_beds": 500,
        "available_icu_beds": 0,
        "cardiology": "Yes",
        "emergency_24x7": "Yes",
        "accepts_referral": "Yes",
        "success_probability": 0.9999,
    }
    # Safe hospital with available ICU beds and moderate ML score
    safe_hospital = {
        "hospital_id": "H_SAFE",
        "distance_km": 10.0,
        "available_beds": 50,
        "available_icu_beds": 5,
        "cardiology": "Yes",
        "emergency_24x7": "Yes",
        "accepts_referral": "Yes",
        "success_probability": 0.8500,
    }

    candidates = [unsafe_hospital, safe_hospital]
    # Stage A filter
    stage_a_passed = [h for h in candidates if evaluate_hospital_capability(patient, h)["eligible"]]

    # Assert unsafe hospital was rejected at Stage A
    assert len(stage_a_passed) == 1
    assert stage_a_passed[0]["hospital_id"] == "H_SAFE"

    # Stage B ranking only sees Stage A output
    df_ranked = rank_hospitals(pd.DataFrame(stage_a_passed), "Critical")
    assert len(df_ranked) == 1
    assert df_ranked.iloc[0]["hospital_id"] == "H_SAFE"


def test_multiple_eligible_hospitals_ranked_monotonically():
    """Verify multiple eligible facilities are sorted properly by hybrid score and distance."""
    h1 = {
        "hospital_id": "H_LOCAL_EXCELLENT",
        "distance_km": 8.0,
        "available_beds": 100,
        "available_icu_beds": 15,
        "emergency_24x7": "Yes",
        "ambulance": "Yes",
        "oxygen_support": "Yes",
        "ventilator": "Yes",
        "blood_bank": "Yes",
        "specialty_match": 1,
        "test_match": 1,
        "success_probability": 0.92,
    }
    h2 = {
        "hospital_id": "H_LOCAL_MODERATE",
        "distance_km": 35.0,
        "available_beds": 20,
        "available_icu_beds": 2,
        "emergency_24x7": "Yes",
        "ambulance": "No",
        "oxygen_support": "Yes",
        "ventilator": "No",
        "blood_bank": "No",
        "specialty_match": 1,
        "test_match": 1,
        "success_probability": 0.65,
    }
    df = pd.DataFrame([h2, h1])
    ranked = rank_hospitals(df, "Critical")
    assert ranked.iloc[0]["hospital_id"] == "H_LOCAL_EXCELLENT"
    assert ranked.iloc[0]["final_score"] > ranked.iloc[1]["final_score"]


# =====================================================================
# 4. EXPLAINABILITY & PROBABILITY LABELING
# =====================================================================

def test_recommendation_reason_generation_and_phi_protection():
    """Ensure reasons are detailed, clinically grounded, and contain zero PHI."""
    patient = {
        "patient_id": "SECRET_PAT_001",
        "name": "John Doe",
        "phone": "+91-9876543210",
        "disease": "Heart Attack",
        "priority": "Critical",
        "icu_required": "Yes",
        "spo2": 91,
        "required_test_1": "ECG",
        "required_test_2": "Troponin Test",
    }
    hospital = {
        "hospital_id": "GH0001",
        "hospital_name": "Apollo Super Specialty",
        "distance_km": 12.4,
        "available_beds": 80,
        "available_icu_beds": 14,
        "available_emergency_beds": 6,
        "cardiology": "Yes",
        "ecg": "Yes",
        "troponin_test": "Yes",
        "emergency_24x7": "Yes",
        "oxygen_support": "Yes",
        "ventilator": "Yes",
        "ambulance": "Yes",
        "blood_bank": "Yes",
        "accepts_referral": "Yes",
        "success_probability": 0.942,
    }
    reasons = generate_recommendation_reason(hospital, patient)
    assert len(reasons) >= 5

    # Check PHI protection
    for r in reasons:
        assert "SECRET_PAT_001" not in r
        assert "John Doe" not in r
        assert "9876543210" not in r

    # Check clinical grounding and non-diagnostic phrasing
    joined_reasons = " ".join(reasons)
    assert "Cardiology" in joined_reasons
    assert "14 ICU beds" in joined_reasons
    assert "24x7 emergency" in joined_reasons
    assert "94.2%" in joined_reasons
    assert "non-diagnostic" in joined_reasons


def test_disqualification_reasons_output():
    """Verify disqualification reasons properly enumerate blocking causes."""
    patient = {
        "patient_id": "P_DISQ_01",
        "disease": "Stroke",
        "priority": "Critical",
        "icu_required": "Yes",
        "spo2": 90,
    }
    hospital = {
        "hospital_id": "GH_INELIGIBLE",
        "hospital_name": "Rural Clinic",
        "available_beds": 0,
        "available_icu_beds": 0,
        "available_emergency_beds": 0,
        "neurology": "No",
        "emergency_24x7": "No",
        "oxygen_support": "No",
        "accepts_referral": "No",
    }
    disq = generate_disqualification_reasons(hospital, patient)
    assert len(disq) >= 3
    assert any("referral" in d.lower() for d in disq)
    assert any("neurology" in d.lower() for d in disq)
    assert any("icu" in d.lower() for d in disq)


# =====================================================================
# 5. ROBUSTNESS & EDGE CASES
# =====================================================================

def test_missing_location_coordinates_fallback():
    """Verify distance calculation does not crash when latitude/longitude are NaN or None."""
    patient = {
        "patient_id": "P_NO_COORDS",
        "disease": "Diabetes",
        "priority": "Stable",
        "icu_required": "No",
        "latitude": None,
        "longitude": None,
        "referral_required": "Yes",
    }
    hospital = {
        "hospital_id": "GH_HOSP_01",
        "latitude": 30.7333,
        "longitude": 76.7794,
        "available_beds": 20,
        "available_icu_beds": 5,
        "general_medicine": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient, hospital)
    assert cap["eligible"] is True


def test_extreme_and_invalid_inputs_resilience():
    """Ensure pipeline handles malformed vitals, NaN probabilities, and empty dicts."""
    reasons = generate_recommendation_reason({}, {})
    assert reasons == []

    disq = generate_disqualification_reasons({}, {})
    assert len(disq) > 0

    patient_bad_spo2 = {
        "patient_id": "P_BAD_VITAL",
        "disease": "Asthma",
        "priority": "Urgent",
        "spo2": "INVALID_NUMBER",
        "referral_required": "Yes",
    }
    hospital = {
        "hospital_id": "GH_01",
        "available_beds": 10,
        "pulmonology": "Yes",
        "accepts_referral": "Yes",
    }
    cap = evaluate_hospital_capability(patient_bad_spo2, hospital)
    assert isinstance(cap["eligible"], bool)


def test_invalid_model_probabilities_clipping():
    """Verify probabilities outside [0, 1] or NaN are handled gracefully in reasons and ranking."""
    hospital_nan_prob = {
        "hospital_id": "H_NAN_PROB",
        "distance_km": 10.0,
        "available_beds": 50,
        "available_icu_beds": 5,
        "emergency_24x7": "Yes",
        "ambulance": "Yes",
        "oxygen_support": "Yes",
        "ventilator": "Yes",
        "blood_bank": "Yes",
        "specialty_match": 1,
        "test_match": 1,
        "success_probability": float("nan"),
    }
    patient = {
        "patient_id": "P_NAN_TEST",
        "disease": "Asthma",
        "priority": "Urgent",
    }
    reasons = generate_recommendation_reason(hospital_nan_prob, patient)
    # NaN probability must not be formatted into reasons
    assert not any("nan" in r.lower() for r in reasons)


# =====================================================================
# 6. API ENDPOINT INTEGRATION
# =====================================================================

def test_get_hospitals_recommendation_api(client):
    """Test GET /hospitals with valid patient returns ranked list with explainability, disclaimer, and counts."""
    response = client.get("/hospitals?patient_id=PAT015796")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "ai_disclaimer" in data
    assert "disqualified_hospitals_count" in data
    assert "hospitals" in data
    assert isinstance(data["hospitals"], list)

    if data["hospitals"]:
        first = data["hospitals"][0]
        assert "hospital_id" in first
        assert "hospital_name" in first
        assert "distance_km" in first
        assert "reasons" in first
        assert isinstance(first["reasons"], list)


def test_get_hospitals_non_referral_patient(client):
    """Test GET /hospitals with patient where referral_required == 'No' returns 0 hospitals."""
    patients_df = pd.read_csv("datasets/final/patients.csv")
    non_ref_p = patients_df[patients_df["referral_required"] == "No"].iloc[0]["patient_id"]

    response = client.get(f"/hospitals?patient_id={non_ref_p}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_hospitals"] == 0
    assert data["referral_required"] == "No"
    assert "not clinically required" in data["message"].lower()
    assert len(data["hospitals"]) == 0
