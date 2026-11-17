"""
Persistent Reservation Store
AI Powered Smart Hospital Referral System
"""

import json
import os
from threading import Lock


def get_store_path():
    return os.getenv("SIH_RESERVATIONS_PATH", "data/reservations.json")


STORE_LOCK = Lock()


def ensure_store():
    """
    Create reservation storage if it does not exist.
    """
    store_path = get_store_path()
    directory = os.path.dirname(store_path)

    if directory:
        os.makedirs(
            directory,
            exist_ok=True
        )

    if not os.path.exists(store_path):

        with open(
            store_path,
            "w"
        ) as file:

            json.dump(
                {},
                file,
                indent=4
            )


def load_reservations():
    """
    Load all reservations from disk.
    """

    ensure_store()

    with STORE_LOCK:

        with open(
            get_store_path(),
            "r"
        ) as file:

            return json.load(file)


def save_reservations(
    reservations
):
    """
    Save all reservations to disk.
    """

    ensure_store()

    store_path = get_store_path()

    with STORE_LOCK:

        temp_path = (
            store_path + ".tmp"
        )

        with open(
            temp_path,
            "w"
        ) as file:

            json.dump(
                reservations,
                file,
                indent=4
            )

        os.replace(
            temp_path,
            store_path
        )


def save_reservation(
    reservation
):
    """
    Save or update one reservation.
    """

    reservations = load_reservations()

    key = (
        reservation["hospital_id"]
        + "_"
        + reservation["patient_id"]
    )

    reservations[key] = reservation

    save_reservations(
        reservations
    )


def get_reservation(
    hospital_id,
    patient_id
):
    """
    Get one reservation.
    """
    try:
        from src.database.db_manager import is_postgres, get_referral_repository
        if is_postgres():
            repo = get_referral_repository()
            res = repo.get_reservation_direct(hospital_id, patient_id)
            if res is not None:
                return res
    except Exception:
        pass

    reservations = load_reservations()

    key = (
        hospital_id
        + "_"
        + patient_id
    )

    return reservations.get(
        key
    )


def get_all_reservations():
    """
    Return all stored reservations.
    """

    return load_reservations()

# ============================================================
# Persistent Bed Inventory
# ============================================================

def get_inventory_path():
    return os.getenv("SIH_BED_INVENTORY_PATH", "data/bed_inventory.json")


def ensure_inventory_store():
    """
    Create bed inventory storage if it does not exist.
    """
    inventory_path = get_inventory_path()
    directory = os.path.dirname(
        inventory_path
    )

    if directory:
        os.makedirs(
            directory,
            exist_ok=True
        )

    if not os.path.exists(
        inventory_path
    ):

        with open(
            inventory_path,
            "w"
        ) as file:

            json.dump(
                {},
                file,
                indent=4
            )


def load_bed_inventory():
    """
    Load all hospital bed inventories.
    """

    ensure_inventory_store()

    with STORE_LOCK:

        with open(
            get_inventory_path(),
            "r"
        ) as file:

            return json.load(file)


def save_bed_inventory(
    inventory_map
):
    """
    Persist all hospital bed inventories.
    """

    ensure_inventory_store()

    inventory_path = get_inventory_path()

    with STORE_LOCK:

        temp_path = (
            inventory_path + ".tmp"
        )

        with open(
            temp_path,
            "w"
        ) as file:

            json.dump(
                inventory_map,
                file,
                indent=4
            )

        os.replace(
            temp_path,
            inventory_path
        )


def save_hospital_inventory(
    inventory
):
    """
    Save or update one hospital inventory.
    """

    inventory_map = (
        load_bed_inventory()
    )

    hospital_id = inventory[
        "hospital_id"
    ]

    inventory_map[
        hospital_id
    ] = inventory

    save_bed_inventory(
        inventory_map
    )


def get_hospital_inventory(
    hospital_id
):
    """
    Get one hospital's persistent inventory
    and recalculate bed counts from actual
    bed-level status.
    """
    try:
        from src.database.db_manager import is_postgres, get_referral_repository
        if is_postgres():
            repo = get_referral_repository()
            inv = repo.get_hospital_inventory(hospital_id)
            if inv is not None:
                return inv
    except Exception:
        pass

    inventory_map = (
        load_bed_inventory()
    )

    inventory = inventory_map.get(
        hospital_id
    )

    if inventory is None:
        return None

    beds = inventory.get(
        "beds",
        {}
    )

    general_beds = {
        bed_id: status
        for bed_id, status in beds.items()
        if bed_id.startswith("GENERAL")
    }

    icu_beds = {
        bed_id: status
        for bed_id, status in beds.items()
        if bed_id.startswith("ICU")
    }

    inventory["available_beds"] = sum(
        status == "AVAILABLE"
        for status in general_beds.values()
    )

    inventory["reserved_beds"] = sum(
        status == "RESERVED"
        for status in general_beds.values()
    )

    inventory["available_icu_beds"] = sum(
        status == "AVAILABLE"
        for status in icu_beds.values()
    )

    inventory["reserved_icu_beds"] = sum(
        status == "RESERVED"
        for status in icu_beds.values()
    )

    # Explicit semantic counters for UI and API consumers
    inventory["available_general_beds"] = inventory["available_beds"]
    inventory["reserved_general_beds"] = inventory["reserved_beds"]
    inventory["total_general_beds"] = (
        inventory["available_general_beds"] + inventory["reserved_general_beds"]
    )
    inventory["total_icu_beds"] = (
        inventory["available_icu_beds"] + inventory["reserved_icu_beds"]
    )
    inventory["total_available_beds"] = (
        inventory["available_beds"] + inventory["available_icu_beds"]
    )
    inventory["total_reserved_beds"] = (
        inventory["reserved_beds"] + inventory["reserved_icu_beds"]
    )
    inventory["total_capacity"] = (
        inventory["total_available_beds"] + inventory["total_reserved_beds"]
    )

    return inventory


def clear_reservations():
    """
    Clear all stored reservations.

    Intended mainly for test setup/reset.
    """

    save_reservations({})