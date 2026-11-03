import os
import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.jwt_utils import create_access_token
from src.prediction.bed_reservation import (
    initialize_hospital_beds,
    reserve_bed,
    get_hospital_inventory,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    res_path = tmp_path / "test_reservations.json"
    bed_path = tmp_path / "test_bed_inventory.json"
    ref_path = tmp_path / "test_referrals.json"

    monkeypatch.setenv("SIH_RESERVATIONS_PATH", str(res_path))
    monkeypatch.setenv("SIH_BED_INVENTORY_PATH", str(bed_path))
    monkeypatch.setenv("SIH_REFERRALS_PATH", str(ref_path))
    return tmp_path


def test_password_hash_never_exposed_in_login():
    resp = client.post(
        "/login",
        json={"username": "gh00046", "password": "hospital123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "password" not in data
    assert "password" not in data.get("user", {})


def test_invalid_jwt_rejected():
    headers = {"Authorization": "Bearer invalid.malicious.token"}
    resp = client.get("/hospitals/GH00046/inventory", headers=headers)
    assert resp.status_code == 401


def test_missing_auth_header_rejected():
    resp = client.get("/hospitals/GH00046/inventory")
    assert resp.status_code == 401


def test_concurrent_bed_reservation_integrity():
    """
    Test concurrency safety:
    A hospital has exactly 1 available ICU bed.
    10 threads concurrently attempt to reserve that ICU bed for different patients.
    Integrity requirement: Exactly 1 reservation succeeds, 9 fail with NO_ICU_AVAILABLE,
    and available_icu_beds never drops below 0.
    """
    hospital_id = "GH_CONCURRENT_TEST"
    inv = initialize_hospital_beds(
        hospital_id=hospital_id,
        available_beds=5,
        available_icu_beds=1,
        reset=True,
    )

    results = []

    def attempt_reservation(patient_num: int):
        # Refresh current live inventory copy
        current_inv = get_hospital_inventory(hospital_id)
        return reserve_bed(
            hospital_id=hospital_id,
            patient_id=f"PAT_CONC_{patient_num}",
            bed_type="ICU",
            inventory=current_inv,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(attempt_reservation, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    success_count = sum(1 for r in results if r["success"] is True)
    failure_count = sum(1 for r in results if r["success"] is False)

    assert success_count == 1, f"Expected 1 success, got {success_count}"
    assert failure_count == 9, f"Expected 9 failures, got {failure_count}"

    final_inv = get_hospital_inventory(hospital_id)
    assert final_inv["available_icu_beds"] == 0
    assert final_inv["reserved_icu_beds"] == 1


def test_unauthenticated_phi_endpoints_rejected():
    """Verify that unauthenticated requests to PHI endpoints receive 401."""
    resp1 = client.get("/patients/hospital/GH00046")
    assert resp1.status_code == 401

    resp2 = client.get("/patients/hospital/GH00046/summary")
    assert resp2.status_code == 401

    resp3 = client.get("/patients/PAT000005")
    assert resp3.status_code == 401


def test_cross_hospital_phi_access_forbidden():
    """Verify that hospital staff cannot access patient rosters of other hospitals (RBAC)."""
    gh00119_token = create_access_token({
        "user_id": "u_gh00119",
        "username": "gh00119",
        "role": "HOSPITAL",
        "hospital_id": "GH00119",
    })
    headers = {"Authorization": f"Bearer {gh00119_token}"}

    resp1 = client.get("/patients/hospital/GH00046", headers=headers)
    assert resp1.status_code == 403
    assert "access denied" in resp1.json()["detail"].lower()

    resp2 = client.get("/patients/hospital/GH00046/summary", headers=headers)
    assert resp2.status_code == 403
    assert "access denied" in resp2.json()["detail"].lower()


def test_authorized_hospital_phi_access_succeeds():
    """Verify that authorized hospital staff can access their own hospital's patient roster."""
    gh00046_token = create_access_token({
        "user_id": "u_gh00046",
        "username": "gh00046",
        "role": "HOSPITAL",
        "hospital_id": "GH00046",
    })
    headers = {"Authorization": f"Bearer {gh00046_token}"}

    resp = client.get("/patients/hospital/GH00046", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["hospital_id"] == "GH00046"


def test_sql_injection_resilience():
    """Verify that SQL injection payloads are safely handled by ORM parameterization and do not cause 500s."""
    gh00046_token = create_access_token({
        "user_id": "u_gh00046",
        "username": "gh00046",
        "role": "HOSPITAL",
        "hospital_id": "GH00046",
    })
    headers = {"Authorization": f"Bearer {gh00046_token}"}

    sqli_payload = "' OR '1'='1"
    resp = client.get(f"/patients/{sqli_payload}", headers=headers)
    assert resp.status_code == 404
    assert resp.status_code != 500


def test_path_traversal_resilience():
    """Verify that path traversal strings do not access underlying filesystem resources."""
    gh00046_token = create_access_token({
        "user_id": "u_gh00046",
        "username": "gh00046",
        "role": "HOSPITAL",
        "hospital_id": "GH00046",
    })
    headers = {"Authorization": f"Bearer {gh00046_token}"}

    resp = client.get("/patients/..%2F..%2Fetc%2Fpasswd", headers=headers)
    assert resp.status_code in [404, 400]
    assert resp.status_code != 500


def test_login_rate_limiting_triggers_429():
    """Verify that repeated failed login attempts trigger HTTP 429 Too Many Requests with Retry-After header."""
    from src.auth.rate_limiter import reset_rate_limits
    reset_rate_limits()

    # 5 failed attempts
    for _ in range(5):
        resp = client.post("/login", json={"username": "brute_target", "password": "wrong_password"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid username or password."

    # 6th attempt must be throttled with HTTP 429
    resp_blocked = client.post("/login", json={"username": "brute_target", "password": "wrong_password"})
    assert resp_blocked.status_code == 429
    assert "too many failed login attempts" in resp_blocked.json()["detail"].lower()
    assert "Retry-After" in resp_blocked.headers

    # Reset for other tests
    reset_rate_limits()


def test_jwt_production_secret_requirement(monkeypatch):
    """Verify that production mode strictly fails application startup if SIH_JWT_SECRET is unset or default."""
    from src.auth.jwt_utils import get_jwt_secret, validate_production_security_config

    monkeypatch.setenv("SIH_ENV", "production")
    monkeypatch.delenv("SIH_JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_security_config()
    assert "SIH_JWT_SECRET must be set" in str(exc_info.value)

    # Short secret rejected
    monkeypatch.setenv("SIH_JWT_SECRET", "short-key-1234")
    with pytest.raises(RuntimeError):
        validate_production_security_config()

    # Valid secret accepted
    monkeypatch.setenv("SIH_JWT_SECRET", "valid-production-secret-must-be-at-least-32-chars-long!")
    assert get_jwt_secret() == "valid-production-secret-must-be-at-least-32-chars-long!"


def test_cross_hospital_patient_phi_access_forbidden():
    """Verify that hospital staff from an unrelated hospital receive 403 when trying to access patient details."""
    gh00119_token = create_access_token({
        "user_id": "u_gh00119",
        "username": "gh00119",
        "role": "HOSPITAL",
        "hospital_id": "GH00119",
    })
    headers = {"Authorization": f"Bearer {gh00119_token}"}

    # PAT000001 is a patient of GH00046, not GH00119
    resp = client.get("/patients/PAT000001", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()


def test_cross_district_patient_phi_access_forbidden():
    """Verify that district administrators receive 403 when trying to access patient records in another district."""
    jalandhar_admin_token = create_access_token({
        "user_id": "u_jal",
        "username": "dist_jalandhar",
        "role": "DISTRICT_ADMIN",
        "state": "Punjab",
        "district": "Jalandhar",
    })
    headers = {"Authorization": f"Bearer {jalandhar_admin_token}"}

    # PAT000001 visits are in Amritsar, not Jalandhar
    resp = client.get("/patients/PAT000001", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()


def test_optimized_recommendation_latency_under_threshold():
    """Verify that recommendation API executes well under 500ms (down from 9,100ms baseline)."""
    import time
    # Warm up call
    _ = client.get("/hospitals?patient_id=PAT000005")

    t0 = time.perf_counter()
    resp = client.get("/hospitals?patient_id=PAT000005")
    duration_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_hospitals"] > 0
    # Enforce performance SLA threshold: must finish in under 300 ms
    assert duration_ms < 300.0, f"Recommendation took {duration_ms:.2f}ms, expected < 300ms"


