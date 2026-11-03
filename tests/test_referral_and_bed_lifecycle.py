import os
import pytest
from datetime import datetime, timedelta
import concurrent.futures

from src.prediction.bed_reservation import (
    initialize_hospital_beds,
    reserve_bed,
    confirm_reservation,
    mark_bed_occupied,
    release_bed,
    expire_reservation,
    discharge_patient,
    get_hospital_inventory,
    get_reservation,
)
from src.prediction.reservation_store import (
    load_reservations,
    save_reservation,
)
from src.prediction.referral_store import (
    create_referral,
    update_referral_status,
    get_referral,
    _save_referrals,
)


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """
    Ensure every test in this module runs with completely isolated JSON stores
    in a temporary directory, avoiding any pollution of runtime/production data.
    """
    res_path = tmp_path / "test_reservations.json"
    bed_path = tmp_path / "test_bed_inventory.json"
    ref_path = tmp_path / "test_referrals.json"

    monkeypatch.setenv("SIH_RESERVATIONS_PATH", str(res_path))
    monkeypatch.setenv("SIH_BED_INVENTORY_PATH", str(bed_path))
    monkeypatch.setenv("SIH_REFERRALS_PATH", str(ref_path))

    return tmp_path


def test_bed_reservation_general_and_icu():
    hospital_id = "GH_TEST_LIFECYCLE"
    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    # Reserve ICU bed for patient 1
    res1 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_001",
        bed_type="ICU",
        inventory=inv,
    )
    assert res1["success"] is True
    assert res1["status"] == "RESERVED"
    assert res1["reservation"]["bed_id"].startswith("ICU-")
    assert inv["available_icu_beds"] == 1
    assert inv["reserved_icu_beds"] == 1

    # Reserve GENERAL bed for patient 2
    res2 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_002",
        bed_type="GENERAL",
        inventory=inv,
    )
    assert res2["success"] is True
    assert res2["status"] == "RESERVED"
    assert res2["reservation"]["bed_id"].startswith("GENERAL-")
    assert inv["available_beds"] == 4
    assert inv["reserved_beds"] == 1


def test_no_silent_icu_downconversion_when_full():
    hospital_id = "GH_TEST_ICU_FULL"
    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=10,  # 10 general beds available
        available_icu_beds=1,  # Only 1 ICU bed
        reset=True,
    )

    # First ICU patient takes the only ICU bed
    res1 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_ICU_1",
        bed_type="ICU",
        inventory=inv,
    )
    assert res1["success"] is True

    # Second ICU patient MUST be rejected with NO_ICU_AVAILABLE,
    # NOT silently downconverted to a GENERAL bed
    res2 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_ICU_2",
        bed_type="ICU",
        inventory=inv,
    )
    assert res2["success"] is False
    assert res2["status"] == "NO_ICU_AVAILABLE"
    # General beds must remain untouched at 10
    assert inv["available_beds"] == 10


def test_duplicate_reservation_prevented():
    hospital_id = "GH_TEST_DUP"
    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    res1 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_DUP",
        bed_type="GENERAL",
        inventory=inv,
    )
    assert res1["success"] is True

    # Attempting to reserve again for the same patient in the same hospital
    res2 = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_DUP",
        bed_type="GENERAL",
        inventory=inv,
    )
    assert res2["success"] is False
    assert res2["status"] == "ALREADY_RESERVED"


def test_full_referral_and_bed_lifecycle():
    dest_hospital_id = "GH_TEST_DEST"
    source_hospital_id = "GH_TEST_SRC"

    # Initialize destination hospital with 2 ICU beds
    inv = initialize_hospital_beds(
        hospital_id=dest_hospital_id,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    # Step 1: Create referral
    create_res = create_referral(
        patient_id="PAT_FLOW_01",
        from_hospital_id=source_hospital_id,
        to_hospital_id=dest_hospital_id,
        reason="Acute respiratory distress",
        priority="HIGH",
        bed_type="ICU",
    )
    assert create_res["success"] is True
    referral_id = create_res["referral"]["referral_id"]
    assert create_res["referral"]["status"] == "PENDING"
    assert create_res["referral"]["bed_type"] == "ICU"

    # Step 2: Destination hospital ACCEPTS referral -> triggers auto-reservation
    accept_res = update_referral_status(referral_id, "ACCEPTED")
    assert accept_res["success"] is True
    ref = accept_res["referral"]
    assert ref["status"] == "ACCEPTED"
    assert ref["auto_reservation"] is True
    assert ref["reservation_status"] == "RESERVED"
    assert ref["bed_id"] is not None
    assert ref["reservation_hospital_id"] == dest_hospital_id

    # Verify destination hospital inventory changed
    dest_inv = get_hospital_inventory(dest_hospital_id)
    assert dest_inv["available_icu_beds"] == 1
    assert dest_inv["reserved_icu_beds"] == 1

    # Step 3: Source hospital dispatches patient -> IN_TRANSIT
    transit_res = update_referral_status(referral_id, "IN_TRANSIT")
    assert transit_res["success"] is True
    assert transit_res["referral"]["status"] == "IN_TRANSIT"

    # Step 4: Patient arrives at destination -> ARRIVED -> reservation CONFIRMED
    arrived_res = update_referral_status(referral_id, "ARRIVED")
    assert arrived_res["success"] is True
    assert arrived_res["referral"]["status"] == "ARRIVED"
    assert arrived_res["referral"]["reservation_status"] == "CONFIRMED"

    # Step 5: Treatment active -> TREATMENT_ACTIVE
    treat_res = update_referral_status(referral_id, "TREATMENT_ACTIVE")
    assert treat_res["success"] is True
    assert treat_res["referral"]["status"] == "TREATMENT_ACTIVE"

    # Step 6: Discharge / Completion -> COMPLETED -> Releases bed
    complete_res = update_referral_status(referral_id, "COMPLETED")
    assert complete_res["success"] is True
    assert complete_res["referral"]["status"] == "COMPLETED"
    assert complete_res["referral"]["reservation_release_status"] == "RELEASED"

    # Verify bed inventory is restored
    final_inv = get_hospital_inventory(dest_hospital_id)
    assert final_inv["available_icu_beds"] == 2
    assert final_inv["reserved_icu_beds"] == 0


def test_scenario_3_accept_referral_when_no_icu_bed_available():
    """
    Scenario 3: Try accepting a referral when no ICU bed is available.
    Must fail gracefully, leaving referral in PENDING and avoiding misleading accepted states.
    """
    dest_hospital_id = "GH_TEST_ZERO_ICU"
    src_hospital_id = "GH_TEST_SRC_03"

    # Initialize destination with 10 general beds and 0 ICU beds
    inv = initialize_hospital_beds(
        hospital_id=dest_hospital_id,
        available_beds=10,
        available_icu_beds=0,
        reset=True,
    )
    assert inv["available_icu_beds"] == 0

    create_res = create_referral(
        patient_id="PAT_SCENARIO_03",
        from_hospital_id=src_hospital_id,
        to_hospital_id=dest_hospital_id,
        reason="Severe trauma requiring critical ICU care",
        priority="CRITICAL",
        bed_type="ICU",
    )
    assert create_res["success"] is True
    ref_id = create_res["referral"]["referral_id"]
    assert create_res["referral"]["status"] == "PENDING"

    # Destination tries to accept ICU referral when 0 ICU beds exist
    accept_res = update_referral_status(ref_id, "ACCEPTED")
    assert accept_res["success"] is False
    assert accept_res["status"] == "NO_ICU_AVAILABLE"

    # Referral MUST remain PENDING — not left in misleading ACCEPTED state
    ref_after = get_referral(ref_id)
    assert ref_after["status"] == "PENDING"
    assert ref_after.get("accepted_at") is None
    assert ref_after.get("auto_reservation") is not True

    # Inventory must remain completely untouched
    dest_inv = get_hospital_inventory(dest_hospital_id)
    assert dest_inv["available_icu_beds"] == 0
    assert dest_inv["reserved_icu_beds"] == 0
    assert dest_inv["available_beds"] == 10


def test_scenario_4_reject_referral_leaves_no_bed_reserved():
    """
    Scenario 4: Reject a referral and verify that no bed remains reserved.
    """
    dest_hospital_id = "GH_TEST_REJECT_DEST"
    src_hospital_id = "GH_TEST_REJECT_SRC"

    inv = initialize_hospital_beds(
        hospital_id=dest_hospital_id,
        available_beds=5,
        available_icu_beds=3,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_SCENARIO_04",
        from_hospital_id=src_hospital_id,
        to_hospital_id=dest_hospital_id,
        reason="Observation required",
        priority="STABLE",
        bed_type="GENERAL",
    )
    ref_id = create_res["referral"]["referral_id"]

    reject_res = update_referral_status(ref_id, "REJECTED")
    assert reject_res["success"] is True
    assert reject_res["referral"]["status"] == "REJECTED"
    assert reject_res["referral"]["rejected_at"] is not None
    assert reject_res["referral"]["reservation_release_status"] == "NO_RESERVATION_LINK"

    # Destination beds unchanged
    dest_inv = get_hospital_inventory(dest_hospital_id)
    assert dest_inv["available_beds"] == 5
    assert dest_inv["reserved_beds"] == 0
    assert dest_inv["available_icu_beds"] == 3
    assert dest_inv["reserved_icu_beds"] == 0


def test_scenario_5_expire_temporary_reservation_restores_inventory():
    """
    Scenario 5: Expire a temporary reservation and verify inventory restoration.
    """
    hospital_id = "GH_TEST_EXPIRE"
    patient_id = "PAT_SCENARIO_05"

    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=2,
        available_icu_beds=1,
        reset=True,
    )

    # Reserve the 1 available ICU bed
    res = reserve_bed(
        hospital_id=hospital_id,
        patient_id=patient_id,
        bed_type="ICU",
        inventory=inv,
    )
    assert res["success"] is True
    assert inv["available_icu_beds"] == 0
    assert inv["reserved_icu_beds"] == 1

    # Simulate timeout by backdating reserved_at timestamp by 30 minutes
    reservations = load_reservations()
    res_key = f"{hospital_id}_{patient_id}"
    old_time = (datetime.now() - timedelta(minutes=30)).isoformat()
    reservations[res_key]["reserved_at"] = old_time
    save_reservation(reservations[res_key])

    # Trigger expiration
    expire_res = expire_reservation(hospital_id, patient_id, inv)
    assert expire_res["success"] is True
    assert expire_res["status"] == "EXPIRED"

    # Inventory must be restored
    refreshed_inv = get_hospital_inventory(hospital_id)
    assert refreshed_inv["available_icu_beds"] == 1
    assert refreshed_inv["reserved_icu_beds"] == 0
    assert refreshed_inv["beds"]["ICU-001"] == "AVAILABLE"

    # Another patient can now reserve the released ICU bed
    res_next = reserve_bed(
        hospital_id=hospital_id,
        patient_id="PAT_SCENARIO_05_NEXT",
        bed_type="ICU",
        inventory=refreshed_inv,
    )
    assert res_next["success"] is True
    assert res_next["reservation"]["bed_id"] == "ICU-001"


def test_scenario_6_and_7_arrival_treatment_and_completion_release():
    """
    Scenario 6 & 7: Confirm patient arrival, activate treatment (mark occupied),
    and complete treatment (release occupied bed).
    """
    dest_hosp = "GH_TEST_TREAT_DEST"
    src_hosp = "GH_TEST_TREAT_SRC"

    initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=3,
        available_icu_beds=2,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_SCENARIO_06_07",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Cardiac monitoring",
        priority="HIGH",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    # 1. Accept -> RESERVED
    accept_res = update_referral_status(ref_id, "ACCEPTED")
    assert accept_res["success"] is True
    assert accept_res["referral"]["reservation_status"] == "RESERVED"

    # 2. Dispatch
    update_referral_status(ref_id, "IN_TRANSIT")

    # 3. Arrive -> CONFIRMED
    arrived_res = update_referral_status(ref_id, "ARRIVED")
    assert arrived_res["success"] is True
    assert arrived_res["referral"]["reservation_status"] == "CONFIRMED"

    # 4. Treatment Active -> OCCUPIED
    treat_res = update_referral_status(ref_id, "TREATMENT_ACTIVE")
    assert treat_res["success"] is True
    assert treat_res["referral"]["reservation_status"] == "OCCUPIED"

    # Verify reservation record on disk is OCCUPIED
    active_res = get_reservation(dest_hosp, "PAT_SCENARIO_06_07")
    assert active_res["status"] == "OCCUPIED"

    # 5. Complete treatment -> COMPLETED -> Releases occupied bed
    complete_res = update_referral_status(ref_id, "COMPLETED")
    assert complete_res["success"] is True
    assert complete_res["referral"]["reservation_release_status"] == "RELEASED"

    # Verify bed released and inventory restored
    final_inv = get_hospital_inventory(dest_hosp)
    assert final_inv["available_icu_beds"] == 2
    assert final_inv["reserved_icu_beds"] == 0
    assert final_inv["beds"][active_res["bed_id"]] == "AVAILABLE"


def test_scenario_8_duplicate_acceptance_prevented():
    """
    Scenario 8: Submit duplicate acceptance requests and verify that duplicate
    reservations cannot occur.
    """
    dest_hosp = "GH_TEST_DUP_DEST"
    src_hosp = "GH_TEST_DUP_SRC"

    initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=5,
        available_icu_beds=3,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_SCENARIO_08",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Severe infection",
        priority="URGENT",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    # First acceptance succeeds
    accept_1 = update_referral_status(ref_id, "ACCEPTED")
    assert accept_1["success"] is True
    assert accept_1["referral"]["status"] == "ACCEPTED"

    inv_after_1 = get_hospital_inventory(dest_hosp)
    assert inv_after_1["available_icu_beds"] == 2
    assert inv_after_1["reserved_icu_beds"] == 1

    # Second acceptance MUST fail with INVALID_TRANSITION
    accept_2 = update_referral_status(ref_id, "ACCEPTED")
    assert accept_2["success"] is False
    assert accept_2["status"] == "INVALID_TRANSITION"

    # Inventory must NOT be decremented a second time
    inv_after_2 = get_hospital_inventory(dest_hosp)
    assert inv_after_2["available_icu_beds"] == 2
    assert inv_after_2["reserved_icu_beds"] == 1


def test_scenario_9_concurrent_reservations_for_last_available_bed():
    """
    Scenario 9: Simulate concurrent reservation requests for the same last available bed.
    Exactly 1 thread must succeed; all others must fail.
    """
    hospital_id = "GH_TEST_CONCURRENT"

    # Exactly 1 ICU bed available
    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=5,
        available_icu_beds=1,
        reset=True,
    )
    assert inv["available_icu_beds"] == 1

    num_concurrent_requests = 10
    results = []

    def attempt_reserve(idx):
        patient_id = f"PAT_CONCURRENT_{idx}"
        return reserve_bed(
            hospital_id=hospital_id,
            patient_id=patient_id,
            bed_type="ICU",
            inventory=inv,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent_requests) as executor:
        futures = [executor.submit(attempt_reserve, i) for i in range(num_concurrent_requests)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successes = [r for r in results if r["success"] is True]
    failures = [r for r in results if r["success"] is False]

    # Exactly ONE thread gets the bed
    assert len(successes) == 1
    assert successes[0]["status"] == "RESERVED"
    assert successes[0]["reservation"]["bed_id"] == "ICU-001"

    # All other 9 threads fail with NO_ICU_AVAILABLE
    assert len(failures) == 9
    for f in failures:
        assert f["status"] == "NO_ICU_AVAILABLE"

    # Final inventory is consistent: 0 available ICU, 1 reserved ICU
    final_inv = get_hospital_inventory(hospital_id)
    assert final_inv["available_icu_beds"] == 0
    assert final_inv["reserved_icu_beds"] == 1
    assert final_inv["beds"]["ICU-001"] == "RESERVED"


def test_scenario_10_failure_between_status_update_and_reservation_rollback(monkeypatch):
    """
    Scenario 10: Simulate a failure during referral persistence after bed reservation.
    Bed reservation must roll back completely so no phantom reservation or lost bed count remains.
    """
    dest_hosp = "GH_TEST_ROLLBACK_DEST"
    src_hosp = "GH_TEST_ROLLBACK_SRC"

    inv = initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_SCENARIO_10",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Respiratory distress",
        priority="CRITICAL",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    # Monkeypatch _save_referrals to simulate crash/disk-full exception
    def failing_save(referrals):
        raise IOError("Simulated disk write failure during referral persistence")

    import src.prediction.referral_store as ref_store_mod
    monkeypatch.setattr(ref_store_mod, "_save_referrals", failing_save)

    # Acceptance should catch disk write failure and rollback the reserved bed
    with pytest.raises(IOError, match="Simulated disk write failure"):
        update_referral_status(ref_id, "ACCEPTED")

    # Verify bed was rolled back: available ICU count must still be 2, reserved 0
    dest_inv = get_hospital_inventory(dest_hosp)
    assert dest_inv["available_icu_beds"] == 2
    assert dest_inv["reserved_icu_beds"] == 0
    assert dest_inv["beds"]["ICU-001"] == "AVAILABLE"
    assert dest_inv["beds"]["ICU-002"] == "AVAILABLE"

    # Verify reservation record is RELEASED
    res_record = get_reservation(dest_hosp, "PAT_SCENARIO_10")
    assert res_record["status"] == "RELEASED"


def test_inventory_consistency_counters_match_physical_beds():
    """
    Verify mathematical consistency: aggregate counters must match physical bed registry
    across complex multi-step cycles.
    """
    hosp = "GH_TEST_MATH_CHECK"
    inv = initialize_hospital_beds(
        hospital_id=hosp,
        available_beds=4,
        available_icu_beds=3,
        reset=True,
    )

    # Perform a sequence of operations
    reserve_bed(hosp, "P1", "ICU", inv)
    reserve_bed(hosp, "P2", "ICU", inv)
    reserve_bed(hosp, "P3", "GENERAL", inv)
    confirm_reservation(hosp, "P1", inv)
    release_bed(hosp, "P2", inv)

    latest_inv = get_hospital_inventory(hosp)
    beds = latest_inv["beds"]
    gen_beds = {k: v for k, v in beds.items() if k.startswith("GENERAL")}
    icu_beds = {k: v for k, v in beds.items() if k.startswith("ICU")}

    actual_avail_gen = sum(1 for s in gen_beds.values() if s == "AVAILABLE")
    actual_res_gen = sum(1 for s in gen_beds.values() if s == "RESERVED")
    actual_avail_icu = sum(1 for s in icu_beds.values() if s == "AVAILABLE")
    actual_res_icu = sum(1 for s in icu_beds.values() if s == "RESERVED")

    assert latest_inv["available_beds"] == actual_avail_gen == 3
    assert latest_inv["reserved_beds"] == actual_res_gen == 1
    assert latest_inv["available_icu_beds"] == actual_avail_icu == 2
    assert latest_inv["reserved_icu_beds"] == actual_res_icu == 1


def test_api_referral_acceptance_and_bed_reservation_flow():
    """
    Test end-to-end API lifecycle:
    1. Create referral
    2. Accept via POST /referrals/{id}/status/ACCEPTED
    3. Verify reservation returned in JSON response
    4. Verify inventory endpoint reflects reservation
    """
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.auth.jwt_utils import create_access_token

    client = TestClient(app)

    dest_hosp = "GH_API_TEST_DEST"
    src_hosp = "GH_API_TEST_SRC"

    initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_API_01",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Acute cardiac syndrome",
        priority="CRITICAL",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    # Generate token for destination hospital user
    dest_token = create_access_token({
        "user_id": "USR_DEST_01",
        "username": "dest_user",
        "role": "HOSPITAL",
        "hospital_id": dest_hosp,
        "district": "Bathinda",
        "state": "Punjab",
    })
    headers = {"Authorization": f"Bearer {dest_token}"}

    # Accept referral via API
    resp = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["status"] == "ACCEPTED"
    assert data["reservation"]["auto_reservation"] is True
    assert data["reservation"]["reservation_status"] == "RESERVED"
    assert data["reservation"]["bed_id"].startswith("ICU-")
    assert data["reservation"]["bed_type"] == "ICU"

    # Query inventory endpoint via API
    inv_resp = client.get(f"/hospitals/{dest_hosp}/inventory", headers=headers)
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()["inventory"]
    assert inv_data["available_icu_beds"] == 1
    assert inv_data["reserved_icu_beds"] == 1


def test_api_referral_acceptance_fails_when_no_bed():
    """
    Test API rejection when destination hospital has 0 beds of requested type:
    POST /referrals/{id}/status/ACCEPTED returns 409 and referral remains PENDING.
    """
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.auth.jwt_utils import create_access_token

    client = TestClient(app)

    dest_hosp = "GH_API_NO_BED"
    src_hosp = "GH_API_SRC_02"

    initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=10,
        available_icu_beds=0,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_API_02",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Critical ICU need",
        priority="CRITICAL",
        bed_type="ICU",
    )
    ref_id = create_res["referral"]["referral_id"]

    dest_token = create_access_token({
        "user_id": "USR_DEST_02",
        "username": "dest_user_nobed",
        "role": "HOSPITAL",
        "hospital_id": dest_hosp,
        "district": "Bathinda",
        "state": "Punjab",
    })
    headers = {"Authorization": f"Bearer {dest_token}"}

    # Attempt acceptance via API
    resp = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=headers)
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data
    assert data["detail"]["success"] is False
    assert data["detail"]["status"] == "NO_ICU_AVAILABLE"

    # Verify referral was NOT accepted
    get_resp = client.get(f"/referrals/{ref_id}", headers=headers)
    assert get_resp.status_code == 200
    ref_data = get_resp.json()["referral"]
    assert ref_data["status"] == "PENDING"
    assert ref_data.get("accepted_at") is None


def test_api_duplicate_acceptance_returns_409():
    """
    Test API prevents duplicate acceptance: second call returns 409 INVALID_TRANSITION.
    """
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.auth.jwt_utils import create_access_token

    client = TestClient(app)

    dest_hosp = "GH_API_DUP_DEST"
    src_hosp = "GH_API_DUP_SRC"

    initialize_hospital_beds(
        hospital_id=dest_hosp,
        available_beds=5,
        available_icu_beds=2,
        reset=True,
    )

    create_res = create_referral(
        patient_id="PAT_API_DUP",
        from_hospital_id=src_hosp,
        to_hospital_id=dest_hosp,
        reason="Trauma management",
        priority="URGENT",
        bed_type="GENERAL",
    )
    ref_id = create_res["referral"]["referral_id"]

    dest_token = create_access_token({
        "user_id": "USR_DEST_DUP",
        "username": "dest_user_dup",
        "role": "HOSPITAL",
        "hospital_id": dest_hosp,
        "district": "Bathinda",
        "state": "Punjab",
    })
    headers = {"Authorization": f"Bearer {dest_token}"}

    # 1. First acceptance
    resp1 = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=headers)
    assert resp1.status_code == 200

    # 2. Duplicate acceptance is blocked by role/status rules
    resp2 = client.post(f"/referrals/{ref_id}/status/ACCEPTED", headers=headers)
    assert resp2.status_code in [403, 409]
