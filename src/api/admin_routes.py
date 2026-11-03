"""
Administrative Tier REST Endpoints
District, State, and Central Governance Dashboards
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import require_current_user
from src.auth.authorization import (
    DISTRICT_ADMIN,
    STATE_ADMIN,
    CENTRAL_ADMIN,
    HOSPITAL,
)
from src.database.database import SessionLocal
from src.database.models import Hospital
from src.prediction.referral_store import _load_referrals
from src.prediction.reservation_store import load_bed_inventory

router = APIRouter(tags=["administration"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# Helper Functions: Geographic Validation
# ============================================================

def resolve_district_scope(current_user: dict, district_param: str | None = None, state_param: str | None = None):
    """
    Enforce geographic boundary checks for district-level requests.
    """
    role = current_user.get("role")

    if role == HOSPITAL:
        raise HTTPException(
            status_code=403,
            detail="Hospital accounts cannot access regional administration dashboards."
        )

    if role == DISTRICT_ADMIN:
        user_district = current_user.get("district")
        user_state = current_user.get("state")
        if district_param and district_param.lower() != (user_district or "").lower():
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: You are only authorized to view district '{user_district}'."
            )
        return user_district, user_state

    if role == STATE_ADMIN:
        user_state = current_user.get("state")
        if state_param and state_param.lower() != (user_state or "").lower():
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: You are only authorized for state '{user_state}'."
            )
        target_district = district_param or "Amritsar"
        return target_district, user_state

    if role == CENTRAL_ADMIN:
        target_district = district_param or "Amritsar"
        target_state = state_param or "Punjab"
        return target_district, target_state

    raise HTTPException(status_code=403, detail="Unauthorized role.")


def resolve_state_scope(current_user: dict, state_param: str | None = None):
    """
    Enforce geographic boundary checks for state-level requests.
    """
    role = current_user.get("role")

    if role in [HOSPITAL, DISTRICT_ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access state administration dashboards."
        )

    if role == STATE_ADMIN:
        user_state = current_user.get("state")
        if state_param and state_param.lower() != (user_state or "").lower():
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: You are only authorized for state '{user_state}'."
            )
        return user_state

    if role == CENTRAL_ADMIN:
        return state_param or "Punjab"

    raise HTTPException(status_code=403, detail="Unauthorized role.")


# ============================================================
# DISTRICT ADMINISTRATION ENDPOINTS
# ============================================================

@router.get("/district/overview")
def get_district_overview(
    district: str | None = None,
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    target_district, target_state = resolve_district_scope(current_user, district, state)

    query = db.query(Hospital).filter(
        Hospital.district.ilike(target_district)
    )
    if target_state:
        query = query.filter(Hospital.state.ilike(target_state))

    hospitals = query.all()

    # Load live bed inventory to augment DB numbers with real-time active reservations
    live_inventories = load_bed_inventory()

    total_beds = 0
    available_beds = 0
    total_icu_beds = 0
    available_icu_beds = 0
    critical_alerts = []

    hosp_summary = []
    for h in hospitals:
        live = live_inventories.get(h.hospital_id)
        if live:
            h_avail_beds = live.get("available_beds", 0)
            h_avail_icu = live.get("available_icu_beds", 0)
            h_reserved_beds = live.get("reserved_beds", 0)
            h_reserved_icu = live.get("reserved_icu_beds", 0)
        else:
            h_avail_beds = h.available_beds or 0
            h_avail_icu = h.available_icu_beds or 0
            h_reserved_beds = 0
            h_reserved_icu = 0

        h_total_beds = h.total_beds or (h_avail_beds + (h.occupied_beds or 0))
        h_total_icu = h.icu_beds or (h_avail_icu + h_reserved_icu)

        total_beds += h_total_beds
        available_beds += h_avail_beds
        total_icu_beds += h_total_icu
        available_icu_beds += h_avail_icu

        # Check for hospital-level critical alerts
        if h_total_icu > 0 and (h_avail_icu / h_total_icu) <= 0.15:
            critical_alerts.append({
                "severity": "CRITICAL",
                "type": "ICU_EXHAUSTION",
                "hospital_id": h.hospital_id,
                "hospital_name": h.name,
                "message": f"Critical ICU shortage: only {h_avail_icu}/{h_total_icu} ICU beds remaining.",
            })

        hosp_summary.append({
            "hospital_id": h.hospital_id,
            "name": h.name,
            "city": h.city,
            "total_beds": h_total_beds,
            "available_beds": h_avail_beds,
            "total_icu_beds": h_total_icu,
            "available_icu_beds": h_avail_icu,
        })

    # Referrals involving this district
    referrals = _load_referrals()
    district_l = target_district.lower()

    relevant_referrals = []
    pending_count = 0
    in_transit_count = 0
    active_count = 0

    for r in referrals:
        from_dist = (r.get("from_district") or "").lower()
        to_dist = (r.get("to_district") or "").lower()
        if from_dist == district_l or to_dist == district_l:
            relevant_referrals.append(r)
            status = r.get("status")
            if status == "PENDING":
                pending_count += 1
            elif status == "IN_TRANSIT":
                in_transit_count += 1
            if status in ["PENDING", "ACCEPTED", "IN_TRANSIT", "ARRIVED", "TREATMENT_ACTIVE"]:
                active_count += 1

    if pending_count >= 3:
        critical_alerts.append({
            "severity": "WARNING",
            "type": "REFERRAL_BOTTLENECK",
            "message": f"Referral backlog detected: {pending_count} pending referrals awaiting acceptance.",
        })

    occupied_beds = max(0, total_beds - available_beds)
    bed_occupancy_rate = round((occupied_beds / total_beds * 100), 1) if total_beds > 0 else 0.0

    occupied_icu = max(0, total_icu_beds - available_icu_beds)
    icu_occupancy_rate = round((occupied_icu / total_icu_beds * 100), 1) if total_icu_beds > 0 else 0.0

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "metrics": {
            "total_hospitals": len(hospitals),
            "total_beds": total_beds,
            "available_beds": available_beds,
            "occupied_beds": occupied_beds,
            "bed_occupancy_rate": bed_occupancy_rate,
            "total_icu_beds": total_icu_beds,
            "available_icu_beds": available_icu_beds,
            "occupied_icu_beds": occupied_icu,
            "icu_occupancy_rate": icu_occupancy_rate,
            "total_active_referrals": active_count,
            "pending_referrals": pending_count,
            "in_transit_referrals": in_transit_count,
        },
        "critical_alerts": critical_alerts,
        "hospitals": hosp_summary,
    }


@router.get("/district/hospitals")
def get_district_hospitals(
    district: str | None = None,
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    target_district, target_state = resolve_district_scope(current_user, district, state)

    query = db.query(Hospital).filter(
        Hospital.district.ilike(target_district)
    )
    if target_state:
        query = query.filter(Hospital.state.ilike(target_state))

    records = query.all()
    live_inventories = load_bed_inventory()

    hospitals_list = []
    for h in records:
        live = live_inventories.get(h.hospital_id)
        avail_beds = live.get("available_beds") if live else h.available_beds
        avail_icu = live.get("available_icu_beds") if live else h.available_icu_beds

        hospitals_list.append({
            "hospital_id": h.hospital_id,
            "name": h.name,
            "state": h.state,
            "district": h.district,
            "city": h.city,
            "total_beds": h.total_beds,
            "available_beds": avail_beds or 0,
            "icu_beds": h.icu_beds or 0,
            "available_icu_beds": avail_icu or 0,
            "emergency_24x7": h.emergency_24x7 == "Yes",
            "cardiology": h.cardiology == "Yes",
            "neurology": h.neurology == "Yes",
            "ventilator": h.ventilator == "Yes",
            "ambulance": h.ambulance == "Yes",
            "ct_scan": h.ct_scan == "Yes",
        })

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "total": len(hospitals_list),
        "hospitals": hospitals_list,
    }


@router.get("/district/referrals")
def get_district_referrals(
    district: str | None = None,
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
):
    target_district, target_state = resolve_district_scope(current_user, district, state)
    referrals = _load_referrals()
    district_l = target_district.lower()

    district_referrals = [
        r for r in referrals
        if (r.get("from_district") or "").lower() == district_l
        or (r.get("to_district") or "").lower() == district_l
    ]

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "total": len(district_referrals),
        "referrals": district_referrals,
    }


# ============================================================
# STATE ADMINISTRATION ENDPOINTS (Phase 5)
# ============================================================

@router.get("/state/overview")
def get_state_overview(
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    target_state = resolve_state_scope(current_user, state)

    hospitals = db.query(Hospital).filter(
        Hospital.state.ilike(target_state)
    ).all()

    live_inventories = load_bed_inventory()

    # Aggregate by district
    district_map: dict[str, dict] = {}
    total_beds = 0
    available_beds = 0
    total_icu = 0
    available_icu = 0

    for h in hospitals:
        d = h.district or "Unknown"
        if d not in district_map:
            district_map[d] = {
                "district": d,
                "hospitals": 0,
                "total_beds": 0,
                "available_beds": 0,
                "total_icu": 0,
                "available_icu": 0,
            }

        live = live_inventories.get(h.hospital_id)
        h_avail = live.get("available_beds") if live else (h.available_beds or 0)
        h_avail_icu = live.get("available_icu_beds") if live else (h.available_icu_beds or 0)
        h_total = h.total_beds or 0
        h_total_icu = h.icu_beds or 0

        district_map[d]["hospitals"] += 1
        district_map[d]["total_beds"] += h_total
        district_map[d]["available_beds"] += h_avail
        district_map[d]["total_icu"] += h_total_icu
        district_map[d]["available_icu"] += h_avail_icu

        total_beds += h_total
        available_beds += h_avail
        total_icu += h_total_icu
        available_icu += h_avail_icu

    district_summaries = []
    for d, info in district_map.items():
        occ = round(((info["total_beds"] - info["available_beds"]) / info["total_beds"] * 100), 1) if info["total_beds"] > 0 else 0.0
        info["occupancy_rate"] = occ
        district_summaries.append(info)

    # State referrals
    referrals = _load_referrals()
    state_l = target_state.lower()
    state_referrals = [
        r for r in referrals
        if (r.get("from_state") or "").lower() == state_l
        or (r.get("to_state") or "").lower() == state_l
    ]

    return {
        "success": True,
        "state": target_state,
        "metrics": {
            "total_districts": len(district_map),
            "total_hospitals": len(hospitals),
            "total_beds": total_beds,
            "available_beds": available_beds,
            "bed_occupancy_rate": round(((total_beds - available_beds) / total_beds * 100), 1) if total_beds > 0 else 0.0,
            "total_icu_beds": total_icu,
            "available_icu_beds": available_icu,
            "icu_occupancy_rate": round(((total_icu - available_icu) / total_icu * 100), 1) if total_icu > 0 else 0.0,
            "total_referrals": len(state_referrals),
        },
        "districts": district_summaries,
    }


@router.get("/state/districts")
def get_state_districts(
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    target_state = resolve_state_scope(current_user, state)
    overview = get_state_overview(state=target_state, current_user=current_user, db=db)
    return {
        "success": True,
        "state": target_state,
        "districts": overview["districts"],
    }


@router.get("/state/referrals")
def get_state_referrals(
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
):
    target_state = resolve_state_scope(current_user, state)
    referrals = _load_referrals()
    state_l = target_state.lower()

    state_referrals = [
        r for r in referrals
        if (r.get("from_state") or "").lower() == state_l
        or (r.get("to_state") or "").lower() == state_l
    ]

    return {
        "success": True,
        "state": target_state,
        "total": len(state_referrals),
        "referrals": state_referrals,
    }


# ============================================================
# CENTRAL ADMINISTRATION ENDPOINTS (Phase 6)
# ============================================================

@router.get("/central/overview")
def get_central_overview(
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    if current_user.get("role") != CENTRAL_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Central Administrator privileges required."
        )

    hospitals = db.query(Hospital).all()
    live_inventories = load_bed_inventory()

    state_map: dict[str, dict] = {}
    total_beds = 0
    available_beds = 0
    total_icu = 0
    available_icu = 0

    for h in hospitals:
        s = h.state or "Other"
        if s not in state_map:
            state_map[s] = {
                "state": s,
                "hospitals": 0,
                "total_beds": 0,
                "available_beds": 0,
                "total_icu": 0,
                "available_icu": 0,
            }

        live = live_inventories.get(h.hospital_id)
        h_avail = live.get("available_beds") if live else (h.available_beds or 0)
        h_avail_icu = live.get("available_icu_beds") if live else (h.available_icu_beds or 0)
        h_total = h.total_beds or 0
        h_total_icu = h.icu_beds or 0

        state_map[s]["hospitals"] += 1
        state_map[s]["total_beds"] += h_total
        state_map[s]["available_beds"] += h_avail
        state_map[s]["total_icu"] += h_total_icu
        state_map[s]["available_icu"] += h_avail_icu

        total_beds += h_total
        available_beds += h_avail
        total_icu += h_total_icu
        available_icu += h_avail_icu

    state_summaries = []
    for s, info in state_map.items():
        occ = round(((info["total_beds"] - info["available_beds"]) / info["total_beds"] * 100), 1) if info["total_beds"] > 0 else 0.0
        info["occupancy_rate"] = occ
        state_summaries.append(info)

    all_referrals = _load_referrals()

    # Inter-state referrals
    interstate_referrals = [
        r for r in all_referrals
        if r.get("from_state") and r.get("to_state") and r.get("from_state") != r.get("to_state")
    ]

    return {
        "success": True,
        "metrics": {
            "participating_states": len(state_map),
            "total_hospitals": len(hospitals),
            "total_beds": total_beds,
            "available_beds": available_beds,
            "bed_occupancy_rate": round(((total_beds - available_beds) / total_beds * 100), 1) if total_beds > 0 else 0.0,
            "total_icu_beds": total_icu,
            "available_icu_beds": available_icu,
            "icu_occupancy_rate": round(((total_icu - available_icu) / total_icu * 100), 1) if total_icu > 0 else 0.0,
            "total_referrals": len(all_referrals),
            "interstate_referrals": len(interstate_referrals),
        },
        "states": state_summaries,
    }


@router.get("/central/states")
def get_central_states(
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    overview = get_central_overview(current_user=current_user, db=db)
    return {
        "success": True,
        "states": overview["states"],
    }
