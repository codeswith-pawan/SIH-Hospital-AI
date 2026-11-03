"""
AI Hospital Recommendation Engine — Comprehensive Evaluation, Integrity & Safety Suite
SIH Hospital AI — Phase 20

Strict Two-Stage Evaluation:
- Stage A: Mandatory Eligibility & Safety Filtering (bed availability, specialty, capabilities, active status).
- Stage B: Ranking & Scoring.

Evaluates:
1. Historical In-Sample Cohort (with explanation of Phase 19 fallback bug).
2. Strictly Held-Out Patient Cohort (Zero data leakage, 100% held out from training).
3. Full-Catalog Active Registry (501 hospitals, 100 clinical queries).
4. Scalability Benchmark (500 vs 5,000 hospitals).
5. 10 Clinical Scenarios.

Models Compared:
- AI Hybrid (Stage A + Priority-Weighted Score + Distance Zone Fallback)
- Transparent Rule-Based Baseline (Stage A + Clinical Heuristics)
- Pure ML Constrained Baseline (Stage A + Random Forest predict_proba)
- Pure ML Unconstrained Baseline (No Stage A + Random Forest predict_proba)
"""

import os
import sys
import time
import math
import json
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.utils.referral_rules import (
    evaluate_hospital_capability,
    check_test_availability,
    check_specialty_availability,
    check_bed_availability,
    DISEASE_SPECIALTY,
)
from src.prediction.feature_builder import (
    build_referral_features,
    calculate_distance_km,
)
from src.prediction.predict import (
    load_model,
    MODEL_FEATURES,
)
from src.prediction.ranking_engine import (
    rank_hospitals,
    get_distance_zone,
    calculate_hospital_score,
)
from src.prediction.recommendation import (
    generate_recommendation_reason,
    generate_disqualification_reasons,
)


# =====================================================================
# 1. RANKING METRICS UTILITIES
# =====================================================================

def dcg_at_k(relevance_list: List[float], k: int) -> float:
    """Compute Discounted Cumulative Gain at rank K."""
    r = np.asarray(relevance_list, dtype=float)[:k]
    if r.size:
        return float(np.sum(r / np.log2(np.arange(2, r.size + 2))))
    return 0.0


def ndcg_at_k(relevance_list: List[float], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain at rank K."""
    dcg_max = dcg_at_k(sorted(relevance_list, reverse=True), k)
    if not dcg_max:
        return 0.0
    return dcg_at_k(relevance_list, k) / dcg_max


# =====================================================================
# 2. CANDIDATE-LEVEL BENCHMARK RUNNER (STAGE A + STAGE B)
# =====================================================================

def evaluate_candidate_cohort(
    cohort_patient_ids: List[str],
    patients_df: pd.DataFrame,
    hospitals_df: pd.DataFrame,
    referrals_subset_df: pd.DataFrame,
    model=None,
    allow_phase19_fallback: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates Hybrid, Rule-Based, Pure ML Constrained, and Pure ML Unconstrained on candidate pools.
    Strictly separates Stage A (eligibility) from Stage B (ranking).
    When allow_phase19_fallback is True, reproduces the Phase 19 bug for audit comparison.
    """
    if model is None:
        model = load_model()

    keys = ["hybrid", "rule", "ml_constrained", "ml_unconstrained"]
    metrics = {
        k: {
            "top1": [], "p1": [], "p3": [], "p5": [],
            "r1": [], "r3": [], "r5": [],
            "ndcg1": [], "ndcg3": [], "ndcg5": [],
            "lat": [], "elig_viol": 0, "bed_viol": 0, "spec_viol": 0, "total_recs": 0,
            "queries_with_recs": 0,
        }
        for k in keys
    }

    total_queries = 0
    queries_zero_eligible = 0

    for pid in cohort_patient_ids:
        pat_rows = patients_df[patients_df["patient_id"] == pid]
        if pat_rows.empty:
            continue
        pat = pat_rows.iloc[0].to_dict()
        pat_refs = referrals_subset_df[referrals_subset_df["patient_id"] == pid]
        cand_hosp_ids = pat_refs["hospital_id"].tolist()
        cand_hosps = hospitals_df[hospitals_df["hospital_id"].isin(cand_hosp_ids)].to_dict("records")
        gt_map = dict(zip(pat_refs["hospital_id"], pat_refs["referral_success"]))

        total_queries += 1
        cand_data = []
        feature_rows = []
        disease = pat.get("disease")
        priority = pat.get("priority", "Urgent")

        for h in cand_hosps:
            h_copy = h.copy()
            feat = build_referral_features(pat, h_copy)
            h_copy["distance_km"] = feat["distance_km"]
            h_copy["specialty_match"] = feat["specialty_match"]
            h_copy["test_match"] = feat["test_match"]
            cand_data.append(h_copy)

            row = feat.copy()
            for f in MODEL_FEATURES:
                if f.startswith("disease_"):
                    row[f] = int(disease == f[len("disease_"):])
                elif f.startswith("priority_"):
                    row[f] = int(priority == f[len("priority_"):])
            feature_rows.append(row)

        batch_X = pd.DataFrame(feature_rows, columns=MODEL_FEATURES)
        probs = model.predict_proba(batch_X)[:, 1]

        for i, h_copy in enumerate(cand_data):
            p_val = float(probs[i])
            h_copy["success_probability"] = 0.5 if math.isnan(p_val) else p_val
            h_copy["distance_zone"] = get_distance_zone(h_copy["distance_km"])
            h_copy["hospital_score"] = calculate_hospital_score(h_copy, priority)
            r_norm = h_copy["hospital_score"] / 100.0
            ml_s = min(max(h_copy["success_probability"], 0.0), 1.0)
            rw, mw = (0.85, 0.15) if priority == "Critical" else (0.75, 0.25) if priority == "Urgent" else (0.65, 0.35)
            h_copy["final_score"] = (r_norm * rw + ml_s * mw) * 100.0
            h_copy["gt"] = gt_map.get(h_copy["hospital_id"], 0)

        # Stage A: Mandatory Clinical Capability Filter
        cand_el = [h for h in cand_data if evaluate_hospital_capability(pat, h)["eligible"]]

        if not cand_el:
            queries_zero_eligible += 1
            if allow_phase19_fallback:
                # Phase 19 bug: silently fell back to ineligible candidate pool
                cand_el = cand_data

        # Stage B: Ranking for Constrained Models
        # 1. AI Hybrid Engine
        t0 = time.perf_counter()
        df_hybrid = pd.DataFrame(cand_el).sort_values(
            by=["final_score", "hospital_score", "distance_km"],
            ascending=[False, False, True]
        ) if cand_el else pd.DataFrame()
        t_hybrid = (time.perf_counter() - t0) * 1000.0

        # 2. Rule-Based Only Baseline
        t0_r = time.perf_counter()
        df_rule = pd.DataFrame(cand_el).sort_values(
            by=["hospital_score", "distance_km"],
            ascending=[False, True]
        ) if cand_el else pd.DataFrame()
        t_rule = (time.perf_counter() - t0_r) * 1000.0

        # 3. Pure ML Constrained Baseline (Stage A applied)
        t0_ml_c = time.perf_counter()
        df_ml_c = pd.DataFrame(cand_el).sort_values(
            by=["success_probability", "distance_km"],
            ascending=[False, True]
        ) if cand_el else pd.DataFrame()
        t_ml_c = (time.perf_counter() - t0_ml_c) * 1000.0

        # 4. Pure ML Unconstrained Baseline (No Stage A filter applied)
        t0_ml_u = time.perf_counter()
        df_ml_u = pd.DataFrame(cand_data).sort_values(
            by=["success_probability", "distance_km"],
            ascending=[False, True]
        )
        t_ml_u = (time.perf_counter() - t0_ml_u) * 1000.0

        for name, m, df, lat_val in [
            ("hybrid", metrics["hybrid"], df_hybrid, t_hybrid),
            ("rule", metrics["rule"], df_rule, t_rule),
            ("ml_constrained", metrics["ml_constrained"], df_ml_c, t_ml_c),
            ("ml_unconstrained", metrics["ml_unconstrained"], df_ml_u, t_ml_u),
        ]:
            m["lat"].append(lat_val)
            if df.empty:
                continue

            m["queries_with_recs"] += 1
            gt_ranked = df["gt"].tolist()
            total_pos = sum(gt_ranked)
            if total_pos == 0:
                continue

            m["top1"].append(int(gt_ranked[0] == 1))
            m["p1"].append(gt_ranked[0])
            m["p3"].append(sum(gt_ranked[:3]) / min(3, len(gt_ranked)))
            m["p5"].append(sum(gt_ranked[:5]) / min(5, len(gt_ranked)))
            m["r1"].append(gt_ranked[0] / total_pos)
            m["r3"].append(sum(gt_ranked[:3]) / total_pos)
            m["r5"].append(sum(gt_ranked[:5]) / total_pos)
            m["ndcg1"].append(ndcg_at_k(gt_ranked, 1))
            m["ndcg3"].append(ndcg_at_k(gt_ranked, 3))
            m["ndcg5"].append(ndcg_at_k(gt_ranked, 5))

            top_recs = df.head(5).to_dict("records")
            for r in top_recs:
                m["total_recs"] += 1
                cap = evaluate_hospital_capability(pat, r)
                if not cap["eligible"]:
                    m["elig_viol"] += 1
                if not check_bed_availability(pat, r):
                    m["bed_viol"] += 1
                if not check_specialty_availability(pat, r)["all_available"]:
                    m["spec_viol"] += 1

    def summarize(m: Dict[str, Any]) -> Dict[str, Any]:
        lat_arr = np.asarray(m["lat"], dtype=float)
        tot_recs = max(1, m["total_recs"])
        return {
            "queries_evaluated": total_queries,
            "queries_with_recommendations": m["queries_with_recs"],
            "top_1_accuracy": round(float(np.mean(m["top1"])), 4) if m["top1"] else 0.0,
            "precision_at_1": round(float(np.mean(m["p1"])), 4) if m["p1"] else 0.0,
            "precision_at_3": round(float(np.mean(m["p3"])), 4) if m["p3"] else 0.0,
            "precision_at_5": round(float(np.mean(m["p5"])), 4) if m["p5"] else 0.0,
            "recall_at_1": round(float(np.mean(m["r1"])), 4) if m["r1"] else 0.0,
            "recall_at_3": round(float(np.mean(m["r3"])), 4) if m["r3"] else 0.0,
            "recall_at_5": round(float(np.mean(m["r5"])), 4) if m["r5"] else 0.0,
            "ndcg_at_1": round(float(np.mean(m["ndcg1"])), 4) if m["ndcg1"] else 0.0,
            "ndcg_at_3": round(float(np.mean(m["ndcg3"])), 4) if m["ndcg3"] else 0.0,
            "ndcg_at_5": round(float(np.mean(m["ndcg5"])), 4) if m["ndcg5"] else 0.0,
            "total_recommendations_evaluated": m["total_recs"],
            "eligibility_violation_rate": round(m["elig_viol"] / tot_recs, 4),
            "bed_mismatch_rate": round(m["bed_viol"] / tot_recs, 4),
            "specialty_mismatch_rate": round(m["spec_viol"] / tot_recs, 4),
            "latency_mean_ms": round(float(np.mean(lat_arr)), 2),
            "latency_p50_ms": round(float(np.percentile(lat_arr, 50)), 2),
            "latency_p95_ms": round(float(np.percentile(lat_arr, 95)), 2),
        }

    return {
        "cohort_size": total_queries,
        "queries_zero_eligible": queries_zero_eligible,
        "models": {k: summarize(metrics[k]) for k in keys},
    }


# =====================================================================
# 3. FULL-CATALOG PRODUCTION PIPELINE EVALUATION (501 HOSPITALS)
# =====================================================================

def evaluate_full_catalog_production(
    patients_df: pd.DataFrame,
    hospitals_df: pd.DataFrame,
    model=None,
    num_patients: int = 100,
) -> Dict[str, Any]:
    """
    Evaluates the complete production recommendation pipeline across all 501 hospitals.
    Asserts zero eligibility violations, zero bed mismatches, and zero specialty mismatches.
    """
    if model is None:
        model = load_model()

    referral_patients = patients_df[patients_df["referral_required"] == "Yes"].head(num_patients).to_dict("records")
    hospitals_base = hospitals_df.to_dict("records")

    total_recommendations = 0
    eligibility_violations = 0
    bed_mismatches = 0
    specialty_mismatches = 0
    zone_counts = {"LOCAL": 0, "REGIONAL": 0, "EXTENDED": 0}
    latencies = []

    for pat in referral_patients:
        t0 = time.perf_counter()
        eligible = []
        feature_rows = []
        disease = pat.get("disease")
        priority = pat.get("priority", "Urgent")

        # Stage A: Eligibility Filtering
        for h in hospitals_base:
            cap = evaluate_hospital_capability(pat, h)
            if not cap["eligible"]:
                continue

            feat = build_referral_features(pat, h)
            h_data = h.copy()
            h_data.update(feat)
            eligible.append(h_data)

            row = feat.copy()
            for f in MODEL_FEATURES:
                if f.startswith("disease_"):
                    row[f] = int(disease == f[len("disease_"):])
                elif f.startswith("priority_"):
                    row[f] = int(priority == f[len("priority_"):])
            feature_rows.append(row)

        if not eligible:
            latencies.append((time.perf_counter() - t0) * 1000.0)
            continue

        # Stage B: Scoring and Ranking
        batch_X = pd.DataFrame(feature_rows, columns=MODEL_FEATURES)
        probs = model.predict_proba(batch_X)[:, 1]

        for idx, h_data in enumerate(eligible):
            p_val = float(probs[idx])
            h_data["success_probability"] = 0.5 if math.isnan(p_val) else round(p_val, 4)

        eligible_df = pd.DataFrame(eligible)
        ranked = rank_hospitals(eligible_df, priority).head(10)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        recs = ranked.to_dict("records")
        for r in recs:
            total_recommendations += 1
            z = r.get("distance_zone", get_distance_zone(r.get("distance_km", 50)))
            zone_counts[z] = zone_counts.get(z, 0) + 1

            cap = evaluate_hospital_capability(pat, r)
            if not cap["eligible"]:
                eligibility_violations += 1

            if not check_bed_availability(pat, r):
                bed_mismatches += 1

            spec = check_specialty_availability(pat, r)
            if not spec["all_available"]:
                specialty_mismatches += 1

    lat_arr = np.asarray(latencies, dtype=float)
    return {
        "patients_evaluated": len(referral_patients),
        "total_recommendations_produced": total_recommendations,
        "eligibility_violation_rate": round(eligibility_violations / max(1, total_recommendations), 6),
        "bed_mismatch_rate": round(bed_mismatches / max(1, total_recommendations), 6),
        "specialty_mismatch_rate": round(specialty_mismatches / max(1, total_recommendations), 6),
        "zone_distribution": {
            k: round(v / max(1, total_recommendations), 4) for k, v in zone_counts.items()
        },
        "latency_mean_ms": round(float(np.mean(lat_arr)), 2),
        "latency_p50_ms": round(float(np.percentile(lat_arr, 50)), 2),
        "latency_p95_ms": round(float(np.percentile(lat_arr, 95)), 2),
    }


# =====================================================================
# 4. SCALABILITY BENCHMARK (500 VS 5,000 HOSPITALS)
# =====================================================================

def evaluate_scalability(
    hospitals_df: pd.DataFrame,
    patient: Dict[str, Any],
    model=None,
) -> Dict[str, Any]:
    """Measures latency scaling between 500 active hospitals and 5,000 synthetic hospitals."""
    if model is None:
        model = load_model()

    h500 = hospitals_df.to_dict("records")

    # Construct 5,000 synthetic facilities by cloning with unique IDs
    h5000 = []
    for i in range(10):
        for h in h500:
            h_c = h.copy()
            h_c["hospital_id"] = f"{h['hospital_id']}_rep{i}"
            h5000.append(h_c)

    def benchmark_catalog(catalog: List[Dict[str, Any]]) -> Dict[str, float]:
        lats = []
        for _ in range(5):
            t0 = time.perf_counter()
            el = []
            feats = []
            dis = patient.get("disease", "Asthma")
            pri = patient.get("priority", "Urgent")
            for h in catalog:
                if not evaluate_hospital_capability(patient, h)["eligible"]:
                    continue
                f = build_referral_features(patient, h)
                hd = h.copy()
                hd.update(f)
                el.append(hd)
                r = f.copy()
                for feat_name in MODEL_FEATURES:
                    if feat_name.startswith("disease_"):
                        r[feat_name] = int(dis == feat_name[len("disease_"):])
                    elif feat_name.startswith("priority_"):
                        r[feat_name] = int(pri == feat_name[len("priority_"):])
                feats.append(r)

            if el:
                b_X = pd.DataFrame(feats, columns=MODEL_FEATURES)
                probs = model.predict_proba(b_X)[:, 1]
                for idx, hd in enumerate(el):
                    hd["success_probability"] = float(probs[idx])
                el_df = pd.DataFrame(el)
                rank_hospitals(el_df, pri).head(10)

            lats.append((time.perf_counter() - t0) * 1000.0)

        lat_arr = np.asarray(lats, dtype=float)
        return {
            "catalog_size": len(catalog),
            "eligible_found": len(el),
            "mean_ms": round(float(np.mean(lat_arr)), 2),
            "p50_ms": round(float(np.percentile(lat_arr, 50)), 2),
            "p95_ms": round(float(np.percentile(lat_arr, 95)), 2),
        }

    return {
        "catalog_500": benchmark_catalog(h500),
        "catalog_5000": benchmark_catalog(h5000),
    }


# =====================================================================
# 5. 10 CLINICAL SCENARIOS
# =====================================================================

def evaluate_clinical_scenarios(
    hospitals_df: pd.DataFrame,
    model=None
) -> List[Dict[str, Any]]:
    """Test 10 specific clinical scenarios across urgent, critical, ICU, general, and boundary conditions."""
    if model is None:
        model = load_model()

    hospitals_list = hospitals_df.to_dict("records")

    scenarios = [
        {
            "id": "SCENARIO_01_URGENT",
            "name": "Urgent Patient",
            "description": "Patient with acute asthma needing pulmonology and urgent inpatient care.",
            "patient": {
                "patient_id": "SIM_URGENT_01",
                "disease": "Asthma",
                "priority": "Urgent",
                "icu_required": "No",
                "spo2": 95,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "Pulmonary Function Test",
            },
            "expected_behavior": "Returns hospitals with pulmonology and general beds; local distance prioritized.",
        },
        {
            "id": "SCENARIO_02_CRITICAL",
            "name": "Critical Patient",
            "description": "Heart Attack patient with low SpO2 needing 24x7 emergency and cardiology.",
            "patient": {
                "patient_id": "SIM_CRIT_02",
                "disease": "Heart Attack",
                "priority": "Critical",
                "icu_required": "No",
                "spo2": 91,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "ECG",
                "required_test_2": "Troponin Test",
            },
            "expected_behavior": "Enforces 24x7 emergency service, oxygen support, emergency beds, and cardiology.",
        },
        {
            "id": "SCENARIO_03_ICU_REQUIRED",
            "name": "ICU Required Patient",
            "description": "Sepsis patient requiring ICU bed, ventilator, and blood culture.",
            "patient": {
                "patient_id": "SIM_ICU_03",
                "disease": "Sepsis",
                "priority": "Critical",
                "icu_required": "Yes",
                "spo2": 88,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "Blood Culture",
            },
            "expected_behavior": "Hard filters out facilities with 0 ICU beds or missing blood culture.",
        },
        {
            "id": "SCENARIO_04_GENERAL_WARD",
            "name": "General Ward Patient",
            "description": "Stable patient with fracture requiring orthopedics and general inpatient bed.",
            "patient": {
                "patient_id": "SIM_GEN_04",
                "disease": "Fracture",
                "priority": "Stable",
                "icu_required": "No",
                "spo2": 98,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "X-Ray",
            },
            "expected_behavior": "Returns facilities with orthopedics and available general beds.",
        },
        {
            "id": "SCENARIO_05_EMERGENCY_CASE",
            "name": "Emergency Trauma Case",
            "description": "Polytrauma patient requiring 24x7 emergency, trauma unit, and ambulance.",
            "patient": {
                "patient_id": "SIM_EMG_05",
                "disease": "Trauma",
                "priority": "Critical",
                "icu_required": "Yes",
                "ambulance_required": "Yes",
                "spo2": 92,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "CT Scan",
            },
            "expected_behavior": "Enforces trauma unit capability, emergency service, oxygen, and ambulance.",
        },
        {
            "id": "SCENARIO_06_NO_REFERRAL",
            "name": "Patient Not Requiring Referral",
            "description": "Mild condition manageable locally without referral.",
            "patient": {
                "patient_id": "SIM_NO_REF_06",
                "disease": "Viral Fever",
                "priority": "Stable",
                "icu_required": "No",
                "spo2": 99,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "No",
            },
            "expected_behavior": "Returns exactly 0 hospitals with non-referral justification.",
        },
        {
            "id": "SCENARIO_07_NO_ELIGIBLE",
            "name": "No Eligible Hospital",
            "description": "Rare clinical requirement not matching any facility in catalog.",
            "patient": {
                "patient_id": "SIM_NO_ELIG_07",
                "disease": "NonExistentDiseaseXYZ",
                "priority": "Critical",
                "icu_required": "Yes",
                "spo2": 90,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "UnavailableExoticTestXYZ",
            },
            "expected_behavior": "Returns 0 hospitals gracefully without unhandled exceptions.",
        },
        {
            "id": "SCENARIO_08_MISSING_LOCATION",
            "name": "Missing Location Coordinates",
            "description": "Patient record with NaN / None latitude and longitude.",
            "patient": {
                "patient_id": "SIM_NO_LOC_08",
                "disease": "Kidney Failure",
                "priority": "Urgent",
                "icu_required": "No",
                "spo2": 96,
                "latitude": None,
                "longitude": None,
                "referral_required": "Yes",
                "required_test_1": "Dialysis",
            },
            "expected_behavior": "Falls back to safe default distance (50.0 km) and processes cleanly.",
        },
        {
            "id": "SCENARIO_09_MISSING_CAPABILITY",
            "name": "Missing Diagnostic Capability",
            "description": "Patient requires MRI which is missing in a subset of candidate facilities.",
            "patient": {
                "patient_id": "SIM_MISS_TEST_09",
                "disease": "Stroke",
                "priority": "Critical",
                "icu_required": "Yes",
                "spo2": 93,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
                "required_test_1": "MRI",
            },
            "expected_behavior": "All returned hospitals must have MRI == 'Yes'; disqualification reasons generated for others.",
        },
        {
            "id": "SCENARIO_10_ZERO_AVAILABLE_BEDS",
            "name": "Zero Available Beds",
            "description": "Patient needing general ward evaluated against hospital with 0 beds.",
            "patient": {
                "patient_id": "SIM_ZERO_BED_10",
                "disease": "Dengue",
                "priority": "Urgent",
                "icu_required": "No",
                "spo2": 97,
                "latitude": 30.7333,
                "longitude": 76.7794,
                "referral_required": "Yes",
            },
            "expected_behavior": "A hospital with 0 available beds must be strictly hard blocked as ineligible.",
        },
    ]

    results = []

    for s in scenarios:
        p = s["patient"]
        t0 = time.perf_counter()

        passed = True
        notes = []

        if p.get("referral_required") != "Yes":
            recs = []
            lat = (time.perf_counter() - t0) * 1000.0
        else:
            eligible = []
            feature_rows = []
            disease = p.get("disease")
            priority = p.get("priority", "Urgent")

            for h in hospitals_list:
                cap = evaluate_hospital_capability(p, h)
                if not cap["eligible"]:
                    continue

                feat = build_referral_features(p, h)
                h_data = h.copy()
                h_data.update(feat)
                eligible.append(h_data)

                row = feat.copy()
                for f in MODEL_FEATURES:
                    if f.startswith("disease_"):
                        row[f] = int(disease == f[len("disease_"):])
                    elif f.startswith("priority_"):
                        row[f] = int(priority == f[len("priority_"):])
                feature_rows.append(row)

            if eligible:
                batch_X = pd.DataFrame(feature_rows, columns=MODEL_FEATURES)
                probs = model.predict_proba(batch_X)[:, 1]
                for idx, h_data in enumerate(eligible):
                    p_val = float(probs[idx])
                    h_data["success_probability"] = 0.5 if math.isnan(p_val) else round(p_val, 4)
                eligible_df = pd.DataFrame(eligible)
                ranked = rank_hospitals(eligible_df, priority).head(10)
                recs = ranked.to_dict("records")
            else:
                recs = []
            lat = (time.perf_counter() - t0) * 1000.0

        if s["id"] == "SCENARIO_06_NO_REFERRAL":
            if len(recs) != 0:
                passed = False
                notes.append(f"Expected 0 hospitals for referral_required='No', got {len(recs)}")

        elif s["id"] == "SCENARIO_07_NO_ELIGIBLE":
            if len(recs) != 0:
                passed = False
                notes.append(f"Expected 0 hospitals for impossible clinical requirement, got {len(recs)}")

        elif s["id"] == "SCENARIO_03_ICU_REQUIRED":
            for r in recs:
                if (r.get("available_icu_beds") or 0) <= 0:
                    passed = False
                    notes.append(f"Hospital {r['hospital_id']} has 0 ICU beds for ICU patient")

        elif s["id"] == "SCENARIO_09_MISSING_CAPABILITY":
            for r in recs:
                if r.get("mri") != "Yes":
                    passed = False
                    notes.append(f"Hospital {r['hospital_id']} missing required MRI")

        elif s["id"] == "SCENARIO_08_MISSING_LOCATION":
            if not recs:
                passed = False
                notes.append("Expected valid recommendations via fallback distance, got empty list")

        elif s["id"] == "SCENARIO_10_ZERO_AVAILABLE_BEDS":
            zero_bed_h = {
                "hospital_id": "TEST_ZERO_BED",
                "hospital_name": "Zero Bed Facility",
                "distance_km": 10.0,
                "available_beds": 0,
                "available_icu_beds": 0,
                "available_emergency_beds": 0,
                "general_medicine": "Yes",
                "accepts_referral": "Yes",
            }
            cap_check = evaluate_hospital_capability(p, zero_bed_h)
            if cap_check["eligible"]:
                passed = False
                notes.append("Zero bed facility was incorrectly evaluated as eligible")

        sample_reasons = []
        if recs:
            sample_reasons = generate_recommendation_reason(recs[0], p)

        results.append({
            "scenario_id": s["id"],
            "name": s["name"],
            "description": s["description"],
            "expected_behavior": s["expected_behavior"],
            "passed": passed,
            "hospitals_returned": len(recs),
            "latency_ms": round(lat, 2),
            "notes": notes if notes else ["Passed all clinical and structural assertions."],
            "sample_reasons": sample_reasons[:3],
        })

    return results


# =====================================================================
# 6. MAIN RUNNER (INTEGRITY AUDIT & BENCHMARK)
# =====================================================================

def run_full_evaluation(cohort_size: int = 200) -> Dict[str, Any]:
    """Execute complete Phase 20 evaluation integrity audit."""
    print("=" * 85)
    print("SIH Hospital AI — Phase 20: AI Recommendation Evaluation Integrity Audit")
    print("=" * 85)

    patients_df = pd.read_csv(os.path.join(PROJECT_ROOT, "datasets/final/patients.csv"))
    hospitals_df = pd.read_csv(os.path.join(PROJECT_ROOT, "datasets/final/hospitals.csv"))
    referrals_df = pd.read_csv(os.path.join(PROJECT_ROOT, "datasets/final/referrals.csv"))

    model = load_model()

    # 1. Identify Held-Out Patients (Zero data leakage)
    train_df, test_df = train_test_split(
        referrals_df,
        test_size=0.20,
        random_state=42,
        stratify=referrals_df["referral_success"]
    )
    train_pids = set(train_df["patient_id"])
    test_pids = set(test_df["patient_id"])
    heldout_pids = test_pids - train_pids
    heldout_refs = test_df[test_df["patient_id"].isin(heldout_pids)]
    succ_heldout = heldout_refs.groupby("patient_id")["referral_success"].agg(["count", "sum"])
    eval_heldout_pids = succ_heldout[
        (succ_heldout["count"] >= 2) & (succ_heldout["sum"] >= 1)
    ].index.tolist()[:cohort_size]

    # 2. In-Sample Historical Cohort (For Phase 19 comparison)
    succ_all = referrals_df.groupby("patient_id")["referral_success"].agg(["count", "sum"])
    eval_in_sample_pids = succ_all[
        (succ_all["count"] >= 3) & (succ_all["sum"] >= 1)
    ].index.tolist()[:cohort_size]

    print(f"\n[1/5] Benchmarking Strictly Held-Out Patient Cohort (N={len(eval_heldout_pids)}, Zero Data Leakage)...")
    heldout_benchmark = evaluate_candidate_cohort(
        cohort_patient_ids=eval_heldout_pids,
        patients_df=patients_df,
        hospitals_df=hospitals_df,
        referrals_subset_df=test_df,
        model=model,
        allow_phase19_fallback=False,
    )

    print(f"[2/5] Benchmarking In-Sample Historical Cohort (N={len(eval_in_sample_pids)}, Strict Stage A Enforcement)...")
    in_sample_strict = evaluate_candidate_cohort(
        cohort_patient_ids=eval_in_sample_pids,
        patients_df=patients_df,
        hospitals_df=hospitals_df,
        referrals_subset_df=referrals_df,
        model=model,
        allow_phase19_fallback=False,
    )

    print(f"[3/5] Reproducing Phase 19 Fallback Bug Cohort (N={len(eval_in_sample_pids)}, Audit Evidence)...")
    in_sample_buggy = evaluate_candidate_cohort(
        cohort_patient_ids=eval_in_sample_pids,
        patients_df=patients_df,
        hospitals_df=hospitals_df,
        referrals_subset_df=referrals_df,
        model=model,
        allow_phase19_fallback=True,
    )

    print("\n[4/5] Benchmarking Full-Catalog Active Production Pipeline (501 Hospitals, 100 Queries)...")
    full_catalog_benchmark = evaluate_full_catalog_production(
        patients_df=patients_df,
        hospitals_df=hospitals_df,
        model=model,
        num_patients=100,
    )

    sample_patient = patients_df[patients_df["referral_required"] == "Yes"].iloc[0].to_dict()
    print("Measuring Latency Scaling (500 vs 5,000 Hospitals)...")
    scalability = evaluate_scalability(hospitals_df=hospitals_df, patient=sample_patient, model=model)

    print("\n[5/5] Evaluating 10 Clinical Scenarios...")
    scenarios = evaluate_clinical_scenarios(hospitals_df=hospitals_df, model=model)
    scenarios_passed = sum(1 for s in scenarios if s["passed"])
    print(f"Scenarios Passed: {scenarios_passed}/{len(scenarios)}")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "catalog_size": len(hospitals_df),
        "heldout_zero_leakage_benchmark": heldout_benchmark,
        "in_sample_strict_benchmark": in_sample_strict,
        "in_sample_phase19_bug_reproduction": in_sample_buggy,
        "full_catalog_production": full_catalog_benchmark,
        "scalability": scalability,
        "clinical_scenarios": scenarios,
    }

    # Print summary tables
    print("\n" + "=" * 105)
    print("TABLE 1: ZERO-LEAKAGE HELD-OUT COHORT BENCHMARK (Strictly Unseen Patients, N=200)")
    print("=" * 105)
    header = f"{'Metric':<28} | {'AI Hybrid (Constrained)':<24} | {'Rule-Based (Constrained)':<24} | {'Pure ML (Constrained)':<22} | {'Pure ML (Unconstrained)':<24}"
    print(header)
    print("-" * 105)

    display_metrics = [
        ("Top-1 Accuracy", "top_1_accuracy", "{:.2%}"),
        ("Precision@1", "precision_at_1", "{:.4f}"),
        ("Precision@3", "precision_at_3", "{:.4f}"),
        ("Precision@5", "precision_at_5", "{:.4f}"),
        ("Recall@1", "recall_at_1", "{:.4f}"),
        ("Recall@3", "recall_at_3", "{:.4f}"),
        ("Recall@5", "recall_at_5", "{:.4f}"),
        ("NDCG@1", "ndcg_at_1", "{:.4f}"),
        ("NDCG@3", "ndcg_at_3", "{:.4f}"),
        ("NDCG@5", "ndcg_at_5", "{:.4f}"),
        ("Eligibility Violation Rate", "eligibility_violation_rate", "{:.2%}"),
        ("Bed-Type Mismatch Rate", "bed_mismatch_rate", "{:.2%}"),
        ("Specialty Mismatch Rate", "specialty_mismatch_rate", "{:.2%}"),
        ("Mean Latency (ms)", "latency_mean_ms", "{:.2f} ms"),
        ("P50 Latency (ms)", "latency_p50_ms", "{:.2f} ms"),
        ("P95 Latency (ms)", "latency_p95_ms", "{:.2f} ms"),
    ]

    h_m = heldout_benchmark["models"]["hybrid"]
    r_m = heldout_benchmark["models"]["rule"]
    mc_m = heldout_benchmark["models"]["ml_constrained"]
    mu_m = heldout_benchmark["models"]["ml_unconstrained"]

    for label, key, fmt in display_metrics:
        print(f"{label:<28} | {fmt.format(h_m[key]):<24} | {fmt.format(r_m[key]):<24} | {fmt.format(mc_m[key]):<22} | {fmt.format(mu_m[key]):<24}")
    print("=" * 105)

    print("\n" + "=" * 105)
    print("TABLE 2: AUDIT OF PHASE 19 FALLBACK BUG (Why Phase 19 reported 13.73% eligibility violations)")
    print("=" * 105)
    print(f"{'Condition':<40} | {'Elig Violation Rate':<20} | {'Specialty Mismatch':<20} | {'Bed Mismatch':<15}")
    print("-" * 105)
    b_h = in_sample_buggy["models"]["hybrid"]
    s_h = in_sample_strict["models"]["hybrid"]
    print(f"{'Phase 19 Buggy Fallback (In-Sample)':<40} | {b_h['eligibility_violation_rate']:.2%}{'':<14} | {b_h['specialty_mismatch_rate']:.2%}{'':<14} | {b_h['bed_mismatch_rate']:.2%}")
    print(f"{'Phase 20 Strict Stage A (In-Sample)':<40} | {s_h['eligibility_violation_rate']:.2%}{'':<14} | {s_h['specialty_mismatch_rate']:.2%}{'':<14} | {s_h['bed_mismatch_rate']:.2%}")
    print(f"{'Phase 20 Strict Stage A (Held-Out)':<40} | {h_m['eligibility_violation_rate']:.2%}{'':<14} | {h_m['specialty_mismatch_rate']:.2%}{'':<14} | {h_m['bed_mismatch_rate']:.2%}")
    print(f"{'Full-Catalog Active Production (501)':<40} | {full_catalog_benchmark['eligibility_violation_rate']:.2%}{'':<14} | {full_catalog_benchmark['specialty_mismatch_rate']:.2%}{'':<14} | {full_catalog_benchmark['bed_mismatch_rate']:.2%}")
    print("=" * 105)

    print("\n" + "=" * 105)
    print("TABLE 3: SCALABILITY & LATENCY BENCHMARK")
    print("=" * 105)
    s500 = scalability["catalog_500"]
    s5000 = scalability["catalog_5000"]
    print(f"500 Hospitals Active Catalog   : Mean = {s500['mean_ms']} ms | P50 = {s500['p50_ms']} ms | P95 = {s500['p95_ms']} ms | Eligible = {s500['eligible_found']}")
    print(f"5,000 Hospitals Scaled Catalog : Mean = {s5000['mean_ms']} ms | P50 = {s5000['p50_ms']} ms | P95 = {s5000['p95_ms']} ms | Eligible = {s5000['eligible_found']}")
    print("=" * 105)

    out_dir = os.path.join(PROJECT_ROOT, "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "ai_recommendation_evaluation_results.json")
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nEvaluation artifact saved to: {out_file}")

    return report


if __name__ == "__main__":
    run_full_evaluation(cohort_size=200)
