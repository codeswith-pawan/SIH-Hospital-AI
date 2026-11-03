import json
import os
from pathlib import Path
from datetime import datetime

from src.prediction.bed_reservation import (
    reserve_bed,
    release_bed,
    confirm_reservation,
    mark_bed_occupied,
    discharge_patient,
)

from src.prediction.reservation_store import (
    get_hospital_inventory,
)


def get_store_path() -> Path:
    env_path = os.getenv("SIH_REFERRALS_PATH")
    if env_path:
        return Path(env_path)
    return Path("data/runtime/referrals.json")


ACTIVE_STATUSES = [
    "PENDING",
    "ACCEPTED",
    "IN_TRANSIT",
    "ARRIVED",
    "TREATMENT_ACTIVE",
]


def _load_referrals():
    store_path = get_store_path()
    if not store_path.exists():
        return []

    try:
        with open(
            store_path,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ):
        return []


def _save_referrals(referrals):
    store_path = get_store_path()
    store_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        store_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            referrals,
            file,
            indent=2,
            ensure_ascii=False
        )


def _generate_referral_id(referrals):
    number = len(referrals) + 1

    return (
        f"REF-{datetime.now().year}-"
        f"{number:06d}"
    )


def create_referral(
    patient_id,
    from_hospital_id,
    to_hospital_id,
    reason,
    priority,
    bed_type="GENERAL",
    user_id=None,
):
    from src.database.db_manager import is_postgres, get_referral_repository
    from src.prediction.notification_store import create_notification

    if is_postgres():
        try:
            repo = get_referral_repository()
            return repo.create_referral(
                patient_id=patient_id,
                from_hospital_id=from_hospital_id,
                to_hospital_id=to_hospital_id,
                reason=reason,
                priority=priority,
                bed_type=bed_type,
                user_id=user_id,
            )
        except Exception:
            pass

    referrals = _load_referrals()

    # ----------------------------------------
    # Prevent duplicate active referral
    # ----------------------------------------

    for referral in referrals:

        if (
            referral["patient_id"] == patient_id
            and referral["status"] in ACTIVE_STATUSES
        ):
            return {
                "success": False,
                "status": "ACTIVE_REFERRAL_EXISTS",
                "message": (
                    "Patient already has "
                    "an active referral."
                ),
                "referral": referral,
            }

    now = datetime.now().isoformat()

    from src.auth.authorization import get_hospital_geo
    from_geo = get_hospital_geo(from_hospital_id) or {}
    to_geo = get_hospital_geo(to_hospital_id) or {}

    referral = {
        "referral_id":
            _generate_referral_id(
                referrals
            ),

        "patient_id":
            patient_id,

        "from_hospital_id":
            from_hospital_id,

        "to_hospital_id":
            to_hospital_id,

        "from_state":
            from_geo.get("state"),

        "from_district":
            from_geo.get("district"),

        "to_state":
            to_geo.get("state"),

        "to_district":
            to_geo.get("district"),

        "reason":
            reason,

        "priority":
            priority,

        "bed_type":
            bed_type,

        "status":
            "PENDING",

        "created_at":
            now,

        "accepted_at":
            None,

        "rejected_at":
            None,

        "in_transit_at":
            None,

        "arrived_at":
            None,

        "treatment_started_at":
            None,

        "completed_at":
            None,

        "transferred_at":
            None,

        "died_at":
            None,

        "closed_at":
            None,
    }

    referrals.append(
        referral
    )

    _save_referrals(
        referrals
    )

    create_notification(
        hospital_id=to_hospital_id,
        event_type="NEW_REFERRAL",
        title=f"New Incoming Referral: {referral['referral_id']}",
        message=f"Patient {patient_id} referred from {from_hospital_id} for {bed_type} bed. Reason: {reason or 'Clinical transfer'}.",
        referral_id=referral["referral_id"],
        priority="CRITICAL" if priority in ["Critical", "CRITICAL"] else "NORMAL",
    )

    return {
        "success": True,
        "status": "PENDING",
        "message":
            "Referral created successfully.",
        "referral":
            referral,
    }


def get_referral(referral_id):
    from src.database.db_manager import is_postgres, get_referral_repository
    if is_postgres():
        try:
            repo = get_referral_repository()
            ref = repo.get_referral(referral_id)
            if ref:
                return ref
        except Exception:
            pass

    referrals = _load_referrals()

    for referral in referrals:
        if referral["referral_id"] == referral_id:
            return referral

    return None


def get_patient_referrals(
    patient_id
):
    from src.database.db_manager import is_postgres, get_referral_repository
    if is_postgres():
        try:
            repo = get_referral_repository()
            refs = repo.get_patient_referrals(patient_id)
            if refs:
                return refs
        except Exception:
            pass

    referrals = _load_referrals()

    return [
        referral
        for referral in referrals
        if referral["patient_id"] == patient_id
    ]


def update_referral_status(
    referral_id,
    new_status,
    notes=None,
    ambulance_id=None,
    eta_minutes=None,
    user_id=None,
):
    from src.database.db_manager import is_postgres, get_referral_repository
    from src.prediction.notification_store import create_notification

    if is_postgres():
        try:
            repo = get_referral_repository()
            if new_status == "ACCEPTED":
                return repo.atomic_accept_and_reserve(referral_id, user_id=user_id)
            else:
                return repo.atomic_transition_lifecycle(
                    referral_id=referral_id,
                    new_status=new_status,
                    user_id=user_id,
                    notes=notes,
                    ambulance_id=ambulance_id,
                    eta_minutes=eta_minutes,
                )
        except Exception:
            pass

    referrals = _load_referrals()

    referral = None

    for item in referrals:

        if (
            item["referral_id"]
            == referral_id
        ):
            referral = item
            break

    if referral is None:
        return {
            "success": False,
            "status": "NOT_FOUND",
            "message":
                "Referral not found.",
            "referral": None,
        }

    current_status = referral[
        "status"
    ]

    allowed_transitions = {
        "PENDING": [
            "ACCEPTED",
            "REJECTED",
        ],

        "ACCEPTED": [
            "IN_TRANSIT",
        ],

        "IN_TRANSIT": [
            "ARRIVED",
        ],

        "ARRIVED": [
            "TREATMENT_ACTIVE",
        ],

        "TREATMENT_ACTIVE": [
            "COMPLETED",
            "TRANSFERRED",
            "DIED",
        ],
    }

    allowed = allowed_transitions.get(
        current_status,
        []
    )

    if new_status not in allowed:

        return {
            "success": False,
            "status": "INVALID_TRANSITION",
            "message": (
                f"Cannot change referral "
                f"from {current_status} "
                f"to {new_status}."
            ),
            "referral": referral,
        }

    now = datetime.now().isoformat()

    # ----------------------------------------
    # Atomic Bed Reservation on ACCEPTED
    # ----------------------------------------
    # When a referral is accepted, automatically and atomically
    # reserve a physical bed at the destination hospital.
    # If no bed is available, the referral remains PENDING and
    # is NOT marked ACCEPTED, preventing misleading accepted states.
    # ----------------------------------------

    if new_status == "ACCEPTED":

        destination_hospital_id = referral.get("to_hospital_id")
        patient_id = referral.get("patient_id")
        bed_type = referral.get("bed_type", "GENERAL")

        if not destination_hospital_id or not patient_id:
            return {
                "success": False,
                "status": "MISSING_HOSPITAL_OR_PATIENT",
                "message": "Cannot accept referral: Destination hospital or patient ID is missing.",
                "referral": referral,
            }

        inventory = get_hospital_inventory(destination_hospital_id)
        if inventory is None:
            return {
                "success": False,
                "status": "INVENTORY_NOT_FOUND",
                "message": f"Cannot accept referral: Bed inventory not found for hospital {destination_hospital_id}.",
                "referral": referral,
            }

        reservation_result = reserve_bed(
            hospital_id=destination_hospital_id,
            patient_id=patient_id,
            bed_type=bed_type,
            inventory=inventory,
        )

        if not reservation_result.get("success"):
            return {
                "success": False,
                "status": reservation_result.get("status", "RESERVATION_FAILED"),
                "message": (
                    f"Referral cannot be accepted: {reservation_result.get('message', 'Bed reservation failed.')}"
                ),
                "referral": referral,
            }

        referral["status"] = "ACCEPTED"
        referral["accepted_at"] = now
        referral["reservation_hospital_id"] = destination_hospital_id
        referral["bed_type"] = bed_type
        referral["reservation_status"] = reservation_result["status"]
        referral["bed_id"] = reservation_result["reservation"]["bed_id"]
        referral["auto_reservation"] = True
        referral.pop("reservation_message", None)

        try:
            _save_referrals(referrals)
            create_notification(
                hospital_id=referral["from_hospital_id"],
                event_type="REFERRAL_ACCEPTED",
                title=f"Referral Accepted: {referral_id}",
                message=f"Hospital {destination_hospital_id} accepted referral. Bed {referral['bed_id']} reserved.",
                referral_id=referral_id,
            )
        except Exception as exc:
            # Rollback bed reservation if saving referral fails
            release_bed(
                hospital_id=destination_hospital_id,
                patient_id=patient_id,
                inventory=inventory,
            )
            raise exc

        return {
            "success": True,
            "status": "ACCEPTED",
            "message": "Referral status updated.",
            "referral": referral,
        }

    # ----------------------------------------
    # Other Status Transitions
    # ----------------------------------------

    referral["status"] = new_status
    if notes:
        referral["notes"] = notes

    if new_status == "IN_TRANSIT":
        referral["in_transit_at"] = now
        referral["ambulance_id"] = ambulance_id or "AMB-108-PB"
        referral["eta_minutes"] = eta_minutes or 25
        create_notification(
            hospital_id=referral["to_hospital_id"],
            event_type="AMBULANCE_DISPATCHED",
            title=f"Ambulance Dispatched: {referral_id}",
            message=f"Patient in transit via Ambulance {referral['ambulance_id']}. ETA: {referral['eta_minutes']} mins (Simulated tracking, manually updated).",
            referral_id=referral_id,
        )

    elif new_status == "ARRIVED":
        referral["arrived_at"] = now
        res_hosp = referral.get("reservation_hospital_id")
        pat_id = referral.get("patient_id")
        if res_hosp and pat_id:
            inv = get_hospital_inventory(res_hosp)
            if inv is not None:
                confirm_res = confirm_reservation(res_hosp, pat_id, inv)
                if confirm_res.get("success"):
                    referral["reservation_status"] = "CONFIRMED"
        create_notification(
            hospital_id=referral["from_hospital_id"],
            event_type="PATIENT_ARRIVED",
            title=f"Patient Arrived: {referral_id}",
            message=f"Patient {pat_id} arrived at destination hospital. Bed confirmed.",
            referral_id=referral_id,
        )

    elif new_status == "TREATMENT_ACTIVE":
        referral["treatment_started_at"] = now
        res_hosp = referral.get("reservation_hospital_id")
        pat_id = referral.get("patient_id")
        if res_hosp and pat_id:
            occupy_res = mark_bed_occupied(res_hosp, pat_id)
            if occupy_res.get("success"):
                referral["reservation_status"] = "OCCUPIED"
        create_notification(
            hospital_id=referral["from_hospital_id"],
            event_type="TREATMENT_STARTED",
            title=f"Treatment Commenced: {referral_id}",
            message=f"Clinical treatment started for patient {pat_id}.",
            referral_id=referral_id,
        )

    elif new_status in [
        "REJECTED",
        "CANCELLED",
        "COMPLETED",
        "DISCHARGED",
        "TRANSFERRED",
        "DIED",
    ]:
        if new_status == "REJECTED":
            referral["rejected_at"] = now
            create_notification(
                hospital_id=referral["from_hospital_id"],
                event_type="REFERRAL_REJECTED",
                title=f"Referral Rejected: {referral_id}",
                message=f"Hospital {referral['to_hospital_id']} rejected referral.",
                referral_id=referral_id,
                priority="URGENT",
            )
        elif new_status == "COMPLETED":
            referral["completed_at"] = now
            referral["closed_at"] = now
            create_notification(
                hospital_id=referral["from_hospital_id"],
                event_type="REFERRAL_COMPLETED",
                title=f"Referral Completed: {referral_id}",
                message=f"Referral completed and bed released.",
                referral_id=referral_id,
            )
        elif new_status == "TRANSFERRED":
            referral["transferred_at"] = now
            referral["closed_at"] = now
        elif new_status == "DIED":
            referral["died_at"] = now
            referral["closed_at"] = now
        else:
            referral["closed_at"] = now

        reservation_hospital_id = referral.get("reservation_hospital_id")
        patient_id = referral.get("patient_id")

        if reservation_hospital_id and patient_id:
            inventory = get_hospital_inventory(reservation_hospital_id)
            if inventory is not None:
                release_result = release_bed(
                    hospital_id=reservation_hospital_id,
                    patient_id=patient_id,
                    inventory=inventory,
                )
                if not release_result.get("success") and release_result.get("status") == "BED_OCCUPIED":
                    release_result = discharge_patient(
                        hospital_id=reservation_hospital_id,
                        patient_id=patient_id,
                        inventory=inventory,
                    )

                referral["reservation_release_status"] = release_result.get("status")
                if release_result.get("success"):
                    referral["reservation_status"] = "RELEASED"
            else:
                referral["reservation_release_status"] = "INVENTORY_NOT_FOUND"
        else:
            referral["reservation_release_status"] = "NO_RESERVATION_LINK"

    _save_referrals(referrals)

    return {
        "success": True,
        "status": new_status,
        "message": "Referral status updated.",
        "referral": referral,
    }

def attach_reservation(
    referral_id,
    hospital_id,
    bed_type
):
    referrals = _load_referrals()

    for referral in referrals:

        if referral["referral_id"] == referral_id:

            referral["reservation_hospital_id"] = (
                hospital_id
            )

            referral["bed_type"] = (
                bed_type
            )

            _save_referrals(
                referrals
            )

            return {
                "success": True,
                "status": "UPDATED",
                "referral": referral,
            }

    return {
        "success": False,
        "status": "NOT_FOUND",
        "message": "Referral not found.",
        "referral": None,
    }

