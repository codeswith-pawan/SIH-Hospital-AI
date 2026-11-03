"""
Regression tests for UI defects, serialization, probability formatting,
capability matching, and inventory counter consistency.
"""

import math
import pytest
import pandas as pd
from src.api.main import serialize_hospital
from src.prediction.reservation_store import get_hospital_inventory
from src.prediction.referral_store import _load_referrals


def test_serialize_hospital_flat_and_nested_keys():
    """Verify serialize_hospital provides both flat and nested properties."""
    raw = {
        "hospital_id": "GH00046",
        "name": "Regional Amritsar Medical College Hospital",
        "state": "Punjab",
        "district": "Amritsar",
        "city": "Amritsar",
        "distance_km": 9.95,
        "total_beds": 360,
        "available_beds": 169,
        "icu_beds": 43,
        "available_icu_beds": 16,
        "final_score": 57.31,
        "success_probability": 0.8738,
        "rank": 1,
        "specialty_match": 1,
        "test_match": 1,
        "bed_match": 1,
        "icu_match": 1,
    }

    result = serialize_hospital(raw)
    assert result is not None

    # Flat properties required by frontend page.tsx
    assert result["hospital_id"] == "GH00046"
    assert result["hospital_name"] == "Regional Amritsar Medical College Hospital"
    assert result["city"] == "Amritsar"
    assert result["district"] == "Amritsar"
    assert result["state"] == "Punjab"
    assert result["distance_km"] == 9.95
    assert result["available_beds"] == 169
    assert result["available_icu_beds"] == 16
    assert result["final_score"] == 57.31
    assert result["success_probability"] == 0.8738
    assert result["specialty_match"] == 1
    assert result["test_match"] == 1
    assert result["bed_match"] == 1
    assert result["icu_match"] == 1
    assert result["rank"] == 1

    # Nested properties required by nested API consumers
    assert result["hospital"]["hospital_id"] == "GH00046"
    assert result["hospital"]["name"] == "Regional Amritsar Medical College Hospital"
    assert result["hospital"]["location"]["city"] == "Amritsar"
    assert result["beds"]["available_beds"] == 169
    assert result["beds"]["available_icu_beds"] == 16
    assert result["scores"]["final_score"] == 57.31
    assert result["scores"]["success_probability"] == 0.8738
    assert result["matching"]["specialty_match"] == 1


def test_serialize_hospital_handles_nan_and_out_of_range_probability():
    """Verify invalid or NaN probabilities are safely normalized to None (never NaN)."""
    # Test pandas NaN
    raw_nan = {
        "hospital_id": "GH00001",
        "name": "Test Hospital",
        "success_probability": float("nan"),
    }
    res_nan = serialize_hospital(raw_nan)
    assert res_nan["success_probability"] is None
    assert res_nan["scores"]["success_probability"] is None

    # Test out of range (> 1.0)
    raw_over = {
        "hospital_id": "GH00001",
        "name": "Test Hospital",
        "success_probability": 1.5,
    }
    res_over = serialize_hospital(raw_over)
    assert res_over["success_probability"] is None

    # Test negative (< 0.0)
    raw_neg = {
        "hospital_id": "GH00001",
        "name": "Test Hospital",
        "success_probability": -0.2,
    }
    res_neg = serialize_hospital(raw_neg)
    assert res_neg["success_probability"] is None

    # Test None
    raw_none = {
        "hospital_id": "GH00001",
        "name": "Test Hospital",
        "success_probability": None,
    }
    res_none = serialize_hospital(raw_none)
    assert res_none["success_probability"] is None


def test_serialize_hospital_handles_none_input():
    """Verify None input returns None without exception."""
    assert serialize_hospital(None) is None


def test_serialize_hospital_capability_matching_normalization():
    """Verify various truthy/falsy representations normalize to 1 or 0."""
    raw = {
        "specialty_match": True,
        "test_match": "Yes",
        "bed_match": 0,
        "icu_match": "No",
    }
    res = serialize_hospital(raw)
    assert res["specialty_match"] == 1
    assert res["test_match"] == 1
    assert res["bed_match"] == 0
    assert res["icu_match"] == 0


def test_inventory_counters_truth_consistency():
    """Verify physical bed counts match aggregate counters for GH00046."""
    inv = get_hospital_inventory("GH00046")
    assert inv is not None

    beds = inv.get("beds", {})
    gen_beds = {k: v for k, v in beds.items() if k.startswith("GENERAL")}
    icu_beds = {k: v for k, v in beds.items() if k.startswith("ICU")}

    # Physical counts
    actual_avail_gen = sum(1 for s in gen_beds.values() if s == "AVAILABLE")
    actual_res_gen = sum(1 for s in gen_beds.values() if s == "RESERVED")
    actual_avail_icu = sum(1 for s in icu_beds.values() if s == "AVAILABLE")
    actual_res_icu = sum(1 for s in icu_beds.values() if s == "RESERVED")

    # Aggregate counters
    assert inv["available_beds"] == actual_avail_gen == 169
    assert inv["reserved_beds"] == actual_res_gen == 0
    assert inv["available_icu_beds"] == actual_avail_icu == 16
    assert inv["reserved_icu_beds"] == actual_res_icu == 6

    # Semantic totals
    assert inv["total_general_beds"] == 169
    assert inv["total_icu_beds"] == 22
    assert inv["total_available_beds"] == 185
    assert inv["total_reserved_beds"] == 6
    assert inv["total_capacity"] == 191


def test_historical_referrals_bed_type_and_provenance():
    """Verify historical August 2026 referrals exist, are loaded without error, and can be inspected."""
    referrals = _load_referrals()
    assert len(referrals) >= 7

    # Early referrals from August 2026 had no bed_type
    ref1 = next((r for r in referrals if r["referral_id"] == "REF-2026-000001"), None)
    assert ref1 is not None
    assert ref1.get("bed_type") is None
    assert "ICU" in (ref1.get("reason") or "")
    assert ref1["created_at"].startswith("2026-08")

    # Recent referral has bed_type
    ref8 = next((r for r in referrals if r["referral_id"] == "REF-2026-000008"), None)
    if ref8 is not None:
        assert ref8.get("bed_type") == "ICU"
