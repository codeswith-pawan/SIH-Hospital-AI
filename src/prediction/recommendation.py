"""
Hospital Recommendation Explanation
AI Powered Smart Hospital Referral System
"""


"""
Hospital Recommendation Explanation & Disqualification Rationale
AI Powered Smart Hospital Referral System
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from src.utils.referral_rules import (
    DISEASE_SPECIALTY,
    evaluate_hospital_capability,
    check_test_availability,
    check_specialty_availability,
)


def get_distance_zone(distance_km: float) -> str:
    """Classify hospital by distance."""
    if distance_km <= 50:
        return "LOCAL"
    elif distance_km <= 200:
        return "REGIONAL"
    return "EXTENDED"


def generate_recommendation_reason(
    hospital: Dict[str, Any],
    patient: Dict[str, Any]
) -> List[str]:
    """
    Generate human-readable, clinically grounded reasons for recommending a hospital.
    Protects patient privacy by excluding any patient PHI/PII.
    """
    reasons = []

    if not isinstance(hospital, dict) or not isinstance(patient, dict) or not hospital or not patient:
        return reasons

    # -------------------------------
    # 1. Proximity & Geographic Zone
    # -------------------------------
    distance = hospital.get("distance_km")
    if distance is not None:
        try:
            dist_val = round(float(distance), 1)
            zone = get_distance_zone(dist_val)
            if dist_val <= 10:
                reasons.append(f"Immediate proximity to patient ({dist_val} km - {zone} zone)")
            elif dist_val <= 50:
                reasons.append(f"Nearby facility ({dist_val} km - {zone} zone)")
            else:
                reasons.append(f"Distance: {dist_val} km ({zone} zone fallback)")
        except (ValueError, TypeError):
            pass

    # -------------------------------
    # 2. Specialty Alignment
    # -------------------------------
    disease = patient.get("disease")
    if disease:
        specialties = DISEASE_SPECIALTY.get(disease, [])
        matched_specs = [
            s.replace("_", " ").title()
            for s in specialties
            if hospital.get(s) == "Yes"
        ]
        if matched_specs:
            reasons.append(
                f"Specialty match: {', '.join(matched_specs)} available for {disease}"
            )
        elif hospital.get("specialty_match") == 1:
            reasons.append(f"Clinical specialty aligned with patient diagnosis ({disease})")

    # -------------------------------
    # 3. Diagnostic Test Capabilities
    # -------------------------------
    patient_tests = []
    for i in range(1, 5):
        t = patient.get(f"required_test_{i}")
        if t and not pd.isna(t) and t not in patient_tests:
            patient_tests.append(t)
    if patient_tests:
        test_check = check_test_availability(patient, hospital)
        if test_check.get("all_available"):
            reasons.append(f"Diagnostic capabilities confirmed: {', '.join(patient_tests)}")

    # -------------------------------
    # 4. Bed Capacity by Clinical Need
    # -------------------------------
    is_icu = patient.get("icu_required") == "Yes" or patient.get("bed_type") == "ICU"
    is_crit = patient.get("priority") == "Critical" or patient.get("bed_type") == "EMERGENCY"

    if is_icu:
        icu = hospital.get("available_icu_beds") or 0
        reasons.append(f"{icu} ICU beds currently available")
    elif is_crit:
        emg = hospital.get("available_emergency_beds") or 0
        reasons.append(f"{emg} Emergency beds currently available")
    else:
        beds = hospital.get("available_beds") or 0
        reasons.append(f"{beds} General inpatient beds currently available")

    # -------------------------------
    # 5. Emergency & Critical Infrastructure
    # -------------------------------
    if hospital.get("emergency_24x7") in ("Yes", 1, True):
        reasons.append("24x7 emergency medical service")

    if hospital.get("oxygen_support") in ("Yes", 1, True):
        reasons.append("Dedicated oxygen support infrastructure")

    if hospital.get("ventilator") in ("Yes", 1, True) and (is_icu or is_crit):
        reasons.append("Advanced mechanical ventilator support available")

    if hospital.get("ambulance") in ("Yes", 1, True):
        reasons.append("Hospital ambulance transport service available")

    if hospital.get("blood_bank") in ("Yes", 1, True) and (is_crit or is_icu):
        reasons.append("On-site blood bank operational")

    # -------------------------------
    # 6. AI Model Transfer Probability
    # -------------------------------
    prob = hospital.get("success_probability")
    if prob is not None:
        try:
            prob_float = float(prob)
            if 0.0 <= prob_float <= 1.0:
                pct = round(prob_float * 100, 1)
                reasons.append(f"AI historical match score: {pct}% (statistical estimate based on capability & capacity; non-diagnostic)")
        except (ValueError, TypeError):
            pass

    return reasons


def generate_disqualification_reasons(
    hospital: Dict[str, Any],
    patient: Dict[str, Any],
    bed_type: Optional[str] = None
) -> List[str]:
    """
    Generate clear, clinical and operational reasons why a hospital
    was deemed ineligible for this patient.
    """
    if not isinstance(hospital, dict) or not isinstance(patient, dict):
        return ["Invalid hospital or patient record."]

    capability = evaluate_hospital_capability(
        patient,
        hospital,
        bed_type=bed_type
    )

    if capability["eligible"]:
        return []

    return capability.get("hard_blocks", ["Hospital does not meet clinical requirements."])


def generate_top_recommendations(
    ranked_hospitals,
    patient,
    top_n=5
):
    """
    Return top N hospitals with
    recommendation reasons.
    """

    if ranked_hospitals.empty:
        return []

    recommendations = []

    top_hospitals = ranked_hospitals.head(
        top_n
    )

    for _, hospital in top_hospitals.iterrows():

        hospital_dict = hospital.to_dict() if hasattr(hospital, "to_dict") else dict(hospital)
        reasons = generate_recommendation_reason(
            hospital_dict,
            patient
        )

        recommendations.append({

            "rank": int(
                hospital.get("rank", 0)
            ),

            "hospital_id": hospital.get(
                "hospital_id"
            ),

            "hospital_name": hospital.get(
                "hospital_name"
            ),

            "distance_km": hospital.get(
                "distance_km"
            ),

            "hospital_score": hospital.get(
                "hospital_score"
            ),

            "reasons": reasons
        })

    return recommendations
