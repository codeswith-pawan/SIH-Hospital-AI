"""
Administrative Tier REST Endpoints
District, State, and Central Governance Dashboards (Phase 4C)

Connects government administrative tiers to PostgreSQL authoritative data.
Enforces multi-tier jurisdictional authorization (Central, State, District),
performs SQL-level aggregations, provides pagination and search, and
sanitizes responses to ensure zero patient PII leakage.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import require_current_user
from src.auth.authorization import (
    DISTRICT_ADMIN,
    STATE_ADMIN,
    CENTRAL_ADMIN,
    HOSPITAL,
)
from src.database.db_manager import get_db_session
from src.database.pg_repository import PgAdminRepository

router = APIRouter(tags=["administration"])


# ============================================================
# Helper Functions: Geographic Validation
# ============================================================

def resolve_district_scope(current_user: dict, district_param: str | None = None, state_param: str | None = None):
    """
    Enforce geographic boundary checks for district-level requests.
    - HOSPITAL role: strictly forbidden (403).
    - DISTRICT_ADMIN: restricted strictly to user's assigned district (403 on mismatch).
    - STATE_ADMIN: authorized across all districts within user's assigned state (403 on state mismatch).
    - CENTRAL_ADMIN: global national jurisdiction across all states and districts.
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
    - HOSPITAL & DISTRICT_ADMIN: strictly forbidden (403).
    - STATE_ADMIN: restricted strictly to user's assigned state (403 on mismatch).
    - CENTRAL_ADMIN: global national jurisdiction across all states.
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
# DISTRICT ADMINISTRATION ENDPOINTS (Phase 4C)
# ============================================================

@router.get("/district/overview")
def get_district_overview(
    district: str | None = None,
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    District health overview: live PostgreSQL bed counts, ICU occupancy,
    active transfer workflows, registration status, and operational critical alerts.
    """
    target_district, target_state = resolve_district_scope(current_user, district, state)
    repo = PgAdminRepository(db)

    overview = repo.get_district_metrics(target_district, target_state)
    hosp_paged = repo.get_paginated_hospitals(
        district=target_district,
        state=target_state,
        page=1,
        page_size=25,
    )

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "metrics": overview["metrics"],
        "critical_alerts": overview["critical_alerts"],
        "hospitals": hosp_paged["hospitals"],
    }


@router.get("/district/hospitals")
def get_district_hospitals(
    district: str | None = None,
    state: str | None = None,
    search: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    District hospital facility catalogue with pagination, search, and capability flags.
    """
    target_district, target_state = resolve_district_scope(current_user, district, state)
    repo = PgAdminRepository(db)

    result = repo.get_paginated_hospitals(
        district=target_district,
        state=target_state,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "total": result["total"],
        "count": len(result["hospitals"]),
        "page": page,
        "page_size": page_size,
        "hospitals": result["hospitals"],
    }


@router.get("/district/referrals")
def get_district_referrals(
    district: str | None = None,
    state: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    District referral tracking with pagination and privacy-preserving PII masking.
    """
    target_district, target_state = resolve_district_scope(current_user, district, state)
    repo = PgAdminRepository(db)

    result = repo.get_paginated_referrals(
        district=target_district,
        state=target_state,
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "district": target_district,
        "state": target_state,
        "total": result["total"],
        "count": len(result["referrals"]),
        "page": page,
        "page_size": page_size,
        "referrals": result["referrals"],
    }


# ============================================================
# STATE ADMINISTRATION ENDPOINTS (Phase 4C)
# ============================================================

@router.get("/state/overview")
def get_state_overview(
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    State health command overview: district-wise capacity matrix,
    statewide bed occupancy, critical care utilization, and registration progress.
    """
    target_state = resolve_state_scope(current_user, state)
    repo = PgAdminRepository(db)

    metrics = repo.get_state_metrics(target_state)
    districts = repo.get_state_districts_summary(target_state)

    return {
        "success": True,
        "state": target_state,
        "metrics": metrics,
        "districts": districts,
    }


@router.get("/state/districts")
def get_state_districts(
    state: str | None = None,
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    List of districts and aggregated capacity for a state jurisdiction.
    """
    target_state = resolve_state_scope(current_user, state)
    repo = PgAdminRepository(db)
    districts = repo.get_state_districts_summary(target_state)

    return {
        "success": True,
        "state": target_state,
        "districts": districts,
    }


@router.get("/state/referrals")
def get_state_referrals(
    state: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    State-level inter-district and cross-hospital patient transfer flows (PII-safe).
    """
    target_state = resolve_state_scope(current_user, state)
    repo = PgAdminRepository(db)

    result = repo.get_paginated_referrals(
        state=target_state,
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "state": target_state,
        "total": result["total"],
        "count": len(result["referrals"]),
        "page": page,
        "page_size": page_size,
        "referrals": result["referrals"],
    }


@router.get("/state/hospitals")
def get_state_hospitals(
    state: str | None = None,
    district: str | None = None,
    search: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    State-level hospital facility catalog with district filter, search, and pagination.
    """
    target_state = resolve_state_scope(current_user, state)
    repo = PgAdminRepository(db)

    result = repo.get_paginated_hospitals(
        state=target_state,
        district=district,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "state": target_state,
        "total": result["total"],
        "count": len(result["hospitals"]),
        "page": page,
        "page_size": page_size,
        "hospitals": result["hospitals"],
    }


# ============================================================
# CENTRAL ADMINISTRATION ENDPOINTS (Phase 4C)
# ============================================================

@router.get("/central/overview")
def get_central_overview(
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    National health command overview: macro-level state capacity distribution,
    total empanelled hospitals, nationwide ICU availability, and interstate transfer tracking.
    """
    if current_user.get("role") != CENTRAL_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Central Administrator privileges required."
        )

    repo = PgAdminRepository(db)
    metrics = repo.get_central_metrics()
    states = repo.get_central_states_summary()

    return {
        "success": True,
        "metrics": metrics,
        "states": states,
    }


@router.get("/central/states")
def get_central_states(
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    State and Union Territory capacity matrix for Central Government surveillance.
    """
    if current_user.get("role") != CENTRAL_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Central Administrator privileges required."
        )

    repo = PgAdminRepository(db)
    states = repo.get_central_states_summary()

    return {
        "success": True,
        "states": states,
    }


@router.get("/central/hospitals")
def get_central_hospitals(
    state: str | None = None,
    district: str | None = None,
    search: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    National hospital catalogue with multi-state/district filtering, search, and pagination.
    """
    if current_user.get("role") != CENTRAL_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Central Administrator privileges required."
        )

    repo = PgAdminRepository(db)
    result = repo.get_paginated_hospitals(
        state=state,
        district=district,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "total": result["total"],
        "count": len(result["hospitals"]),
        "page": page,
        "page_size": page_size,
        "hospitals": result["hospitals"],
    }


@router.get("/central/referrals")
def get_central_referrals(
    state: str | None = None,
    district: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    """
    National and inter-state patient referral monitoring with PII masking.
    """
    if current_user.get("role") != CENTRAL_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Central Administrator privileges required."
        )

    repo = PgAdminRepository(db)
    result = repo.get_paginated_referrals(
        state=state,
        district=district,
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "total": result["total"],
        "count": len(result["referrals"]),
        "page": page,
        "page_size": page_size,
        "referrals": result["referrals"],
    }
