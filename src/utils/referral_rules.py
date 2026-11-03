"""
Referral Rules & Hospital Capability Mapping
AI Powered Smart Hospital Referral System
"""
import pandas as pd
# ----------------------------------------
# Patient Test -> Hospital Column Mapping
# ----------------------------------------

TEST_TO_HOSPITAL_COLUMN = {

    "ECG": "ecg",

    "CT Scan": "ct_scan",

    "MRI": "mri",

    "X-Ray": "xray",

    "Chest X-Ray": "xray",

    "Ultrasound": "ultrasound",

    "Dialysis": "dialysis",

    "Blood Test": "blood_test",

    "CBC": "cbc",

    "Troponin Test": "troponin_test",

    "Dengue NS1 Test": "dengue_ns1_test",

    "Malaria Test": "malaria_test",

    "Blood Glucose Test": "blood_glucose_test",

    "HbA1c Test": "hba1c_test",

    "Kidney Function Test": "kidney_function_test",

    "Pulmonary Function Test": "pulmonary_function_test",

    "Blood Culture": "blood_culture",

    "Lactate Test": "lactate_test",

    "Stool Test": "stool_test",

    "Oxygen Assessment": "oxygen_support",

    "Blood Pressure Test": "general_medicine"
}


# ----------------------------------------
# Disease -> Required Hospital Specialty
# ----------------------------------------

DISEASE_SPECIALTY = {

    "Heart Attack": [
        "cardiology"
    ],

    "Stroke": [
        "neurology"
    ],

    "Kidney Failure": [
        "nephrology"
    ],

    "Pneumonia": [
        "pulmonology"
    ],

    "Asthma": [
        "pulmonology"
    ],

    "COPD": [
        "pulmonology"
    ],

    "Fracture": [
        "orthopedics"
    ],

    "Trauma": [
        "trauma_unit",
        "orthopedics"
    ],

    "Burn Injury": [
        "burn_unit"
    ],

    "Appendicitis": [
        "general_surgery"
    ],

    "Sepsis": [
        "general_medicine"
    ],

    "Dengue": [
        "general_medicine"
    ],

    "Malaria": [
        "general_medicine"
    ],

    "Viral Fever": [
        "general_medicine"
    ],

    "COVID-like Infection": [
        "pulmonology"
    ],

    "Diabetes": [
        "general_medicine"
    ],

    "Hypertension": [
        "general_medicine"
    ],

    "Food Poisoning": [
        "general_medicine"
    ]
}

# ----------------------------------------
# Check Required Tests
# ----------------------------------------

def check_test_availability(patient, hospital):
    """
    Check whether hospital has all tests
    required by the patient.
    """

    required_tests = []

    for i in range(1, 5):

        test = patient.get(
            f"required_test_{i}"
        )

        # Ignore missing / NaN tests
        if pd.isna(test):
            continue

        if test not in required_tests:
            required_tests.append(test)

    unavailable_tests = []

    for test in required_tests:

        hospital_column = TEST_TO_HOSPITAL_COLUMN.get(test)

        if hospital_column is None:
            unavailable_tests.append(test)
            continue

        if hospital.get(hospital_column) not in ("Yes", 1, True):
            unavailable_tests.append(test)

    return {
        "all_available": len(unavailable_tests) == 0,
        "unavailable_tests": unavailable_tests
    }



# ----------------------------------------
# Check Specialty
# ----------------------------------------

def check_specialty_availability(patient, hospital):
    """
    Check whether hospital has the required
    medical specialty.
    """

    disease = patient.get("disease") or "general_medicine"

    required_specialties = DISEASE_SPECIALTY.get(
        disease,
        ["general_medicine"]
    )

    unavailable_specialties = []

    for specialty in required_specialties:

        if hospital.get(specialty) not in ("Yes", 1, True):
            unavailable_specialties.append(
                specialty
            )

    return {
        "all_available": (
            len(unavailable_specialties) == 0
        ),
        "unavailable_specialties":
            unavailable_specialties
    }


# ----------------------------------------
# Check Bed Availability
# ----------------------------------------

def check_bed_availability(patient, hospital, bed_type=None):
    """
    Check whether hospital has an appropriate
    bed for the patient.
    """
    target_bed = bed_type or patient.get("bed_type")

    if target_bed == "ICU" or patient.get("icu_required") == "Yes":
        return (hospital.get("available_icu_beds") or 0) > 0

    if target_bed == "EMERGENCY" or patient.get("priority") == "Critical":
        return (hospital.get("available_emergency_beds") or 0) > 0

    return (hospital.get("available_beds") or 0) > 0


# ----------------------------------------
# Complete Hospital Eligibility
# ----------------------------------------

def check_hospital_eligibility(patient, hospital):
    """
    Determine whether a hospital is eligible
    for patient referral.
    """

    if hospital.get("is_active") is False or hospital.get("status") in ("INACTIVE", "DECOMMISSIONED", "CLOSED"):
        return False

    if hospital.get("accepts_referral") not in ("Yes", 1, True):
        return False

    test_result = check_test_availability(
        patient,
        hospital
    )

    if not test_result["all_available"]:
        return False

    specialty_result = check_specialty_availability(
        patient,
        hospital
    )

    if not specialty_result["all_available"]:
        return False

    if not check_bed_availability(
        patient,
        hospital
    ):
        return False

    return True

# ----------------------------------------
# Detailed Hospital Capability Assessment
# ----------------------------------------

def evaluate_hospital_capability(
    patient,
    hospital,
    bed_type=None
):
    """
    Detailed hospital capability assessment.

    Returns:
        eligible
        hard_blocks
        warnings
        unavailable_tests
        unavailable_specialties
    """

    hard_blocks = []
    warnings = []

    # --------------------------------
    # Referral acceptance & Active Status
    # --------------------------------

    if hospital.get("is_active") is False or hospital.get("status") in ("INACTIVE", "DECOMMISSIONED", "CLOSED"):
        hard_blocks.append(
            "Hospital facility is inactive or decommissioned"
        )

    if hospital.get("accepts_referral") not in ("Yes", 1, True):

        hard_blocks.append(
            "Hospital does not accept referrals"
        )

    # --------------------------------
    # Required Tests
    # --------------------------------

    test_result = check_test_availability(
        patient,
        hospital
    )

    unavailable_tests = test_result[
        "unavailable_tests"
    ]

    if unavailable_tests:

        hard_blocks.append(
            "Required tests unavailable: "
            + ", ".join(unavailable_tests)
        )

    # --------------------------------
    # Required Specialty
    # --------------------------------

    specialty_result = (
        check_specialty_availability(
            patient,
            hospital
        )
    )

    unavailable_specialties = (
        specialty_result[
            "unavailable_specialties"
        ]
    )

    if unavailable_specialties:

        hard_blocks.append(
            "Required specialty unavailable: "
            + ", ".join(
                unavailable_specialties
            )
        )

    target_bed = bed_type or patient.get("bed_type")

    # --------------------------------
    # ICU Bed Requirement
    # --------------------------------

    if target_bed == "ICU" or patient.get("icu_required") == "Yes":

        if (hospital.get("available_icu_beds") or 0) <= 0:

            hard_blocks.append(
                "ICU bed unavailable"
            )

    # --------------------------------
    # Critical / Emergency Bed Requirement
    # --------------------------------

    elif target_bed == "EMERGENCY" or patient.get("priority") == "Critical":

        # Critical cases require emergency support
        if hospital.get("emergency_24x7") not in ("Yes", 1, True):

            hard_blocks.append(
                "24x7 emergency service unavailable"
            )

        # Emergency bed
        if (hospital.get("available_emergency_beds") or 0) <= 0:

            hard_blocks.append(
                "Emergency bed unavailable"
            )

    # --------------------------------
    # General Inpatient Bed Requirement
    # --------------------------------

    else:

        if (hospital.get("available_beds") or 0) <= 0:

            hard_blocks.append(
                "General bed unavailable"
            )

    # --------------------------------
    # Oxygen warning / requirement
    # --------------------------------

    try:

        spo2 = float(
            patient.get("spo2")
        )

        if spo2 < 94:

            if hospital.get("oxygen_support") not in ("Yes", 1, True):

                hard_blocks.append(
                    "Oxygen support unavailable"
                )

    except (
        KeyError,
        TypeError,
        ValueError
    ):

        pass

    # --------------------------------
    # Ventilator warning / capability
    # --------------------------------

    if patient.get("priority") == "Critical":

        if hospital.get("ventilator") not in ("Yes", 1, True):

            warnings.append(
                "Ventilator support unavailable"
            )

    # --------------------------------
    # Ambulance
    # --------------------------------

    if patient.get(
        "ambulance_required"
    ) == "Yes":

        if hospital.get("ambulance") not in ("Yes", 1, True):

            warnings.append(
                "Hospital ambulance unavailable"
            )

    # --------------------------------
    # Final decision
    # --------------------------------

    eligible = (
        len(hard_blocks) == 0
    )

    return {
        "eligible": eligible,
        "hard_blocks": hard_blocks,
        "warnings": warnings,
        "unavailable_tests":
            unavailable_tests,
        "unavailable_specialties":
            unavailable_specialties
    }