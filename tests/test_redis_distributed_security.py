"""
Phase 17: Comprehensive Redis Distributed Security, Authentication Hardening & Rate Limiting Test Suite
AI Powered Smart Hospital Referral System

Validates:
1. 6 failed login attempts trigger HTTP 429 + Retry-After header.
2. Dual-key rate limiting (IP-based brute-force & credential stuffing prevention).
3. Dual-key rate limiting (User-based distributed botnet protection).
4. Prevention of username enumeration (constant errors and timing protection).
5. Live Redis integration with atomic Lua sliding-window scripts.
6. Concurrent multi-thread atomic rate limiting.
7. Counter reset on successful login.
8. Distributed token revocation blocklist (/logout endpoint and JWT invalidation).
9. Production fail-fast enforcement (unreachable or unconfigured Redis raises RuntimeError).
10. JWT security: algorithm hardening (HS256 enforced, 'none' rejected), signature verification.
11. Security audit logging with credential and token redaction.
"""

import os
import time
import uuid
import pytest
import jwt
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.rate_limiter import (
    reset_rate_limits,
    reset_blocklist,
    reset_redis_client,
    _get_redis_client,
    get_rate_limiter_status,
    check_login_rate_limits,
    record_login_failure,
    record_login_success,
    revoke_token,
    is_token_revoked,
    log_security_event,
    validate_production_redis_config,
    sanitize_redis_url,
    _token_hash,
    MAX_FAILED_ATTEMPTS,
    WINDOW_SECONDS,
)
from src.auth.jwt_utils import (
    create_access_token,
    decode_access_token,
    get_jwt_secret,
    validate_production_security_config,
    ALGORITHM,
)
from src.auth.auth_store import authenticate_user, DUMMY_PBKDF2_HASH, verify_password

client = TestClient(app)
REDIS_LOCAL_URL = "redis://localhost:6379/0"


@pytest.fixture(autouse=True)
def setup_teardown_security(monkeypatch):
    """Ensure clean Redis and in-memory rate-limiter state for every test."""
    monkeypatch.setenv("REDIS_URL", REDIS_LOCAL_URL)
    monkeypatch.setenv("ENVIRONMENT", "development")
    reset_redis_client()
    reset_rate_limits()
    reset_blocklist()
    yield
    reset_rate_limits()
    reset_blocklist()
    reset_redis_client()


# ============================================================
# 1. 6 FAILED LOGIN ATTEMPTS TRIGGER HTTP 429 & RETRY-AFTER
# ============================================================

def test_six_failed_login_attempts_trigger_429():
    """Verify that 5 failed attempts are rejected with 401, and 6th triggers HTTP 429 with Retry-After."""
    target_user = f"user_test_{uuid.uuid4().hex[:6]}"

    # 5 attempts fail with 401
    for i in range(5):
        resp = client.post("/login", json={"username": target_user, "password": "wrong_password"})
        assert resp.status_code == 401, f"Attempt {i+1} expected 401, got {resp.status_code}"
        assert resp.json()["detail"] == "Invalid username or password."

    # 6th attempt must be throttled with HTTP 429
    resp_throttled = client.post("/login", json={"username": target_user, "password": "wrong_password"})
    assert resp_throttled.status_code == 429
    assert "Retry-After" in resp_throttled.headers
    retry_after = int(resp_throttled.headers["Retry-After"])
    assert 1 <= retry_after <= WINDOW_SECONDS
    assert "too many failed login attempts" in resp_throttled.json()["detail"].lower()


# ============================================================
# 2. DUAL-KEY RATE LIMITING: IP-BASED CREDENTIAL STUFFING
# ============================================================

def test_ip_based_rate_limiting_blocks_credential_stuffing():
    """
    An attacker at a single IP tries 5 different usernames (credential stuffing).
    The 6th attempt (even for a brand-new username) must be blocked by the IP rate limit.
    """
    attacker_ip = f"192.168.100.{uuid.uuid4().hex[:2]}"

    # Send 5 attempts with 5 different target usernames from the same IP
    for i in range(5):
        uname = f"victim_user_{i}_{uuid.uuid4().hex[:4]}"
        resp = client.post(
            "/login",
            json={"username": uname, "password": "password123"},
            headers={"X-Forwarded-For": attacker_ip},
        )
        assert resp.status_code == 401

    # 6th attempt targeting a completely different username from the same IP must be 429
    new_uname = f"victim_user_brand_new_{uuid.uuid4().hex[:4]}"
    resp_blocked = client.post(
        "/login",
        json={"username": new_uname, "password": "password123"},
        headers={"X-Forwarded-For": attacker_ip},
    )
    assert resp_blocked.status_code == 429
    assert "too many failed login attempts" in resp_blocked.json()["detail"].lower()
    assert "Retry-After" in resp_blocked.headers


# ============================================================
# 3. DUAL-KEY RATE LIMITING: USER-BASED DISTRIBUTED BOTNET
# ============================================================

def test_user_based_rate_limiting_blocks_distributed_attack():
    """
    A distributed botnet attacks the same account from 5 different IPs.
    The 6th attempt from a 6th IP must be blocked by the user rate limit.
    """
    targeted_user = f"vip_account_{uuid.uuid4().hex[:6]}"

    # Record 5 failures from 5 completely different IPs targeting the same username
    for i in range(5):
        bot_ip = f"198.51.100.{i+10}"
        record_login_failure(client_ip=bot_ip, username=targeted_user)

    # 6th attempt from a brand-new, clean IP (never seen before)
    fresh_ip = "198.51.100.99"
    with pytest.raises(Exception) as exc_info:
        check_login_rate_limits(client_ip=fresh_ip, username=targeted_user)

    assert "429" in str(exc_info.value)


# ============================================================
# 4. ZERO USERNAME ENUMERATION & TIMING DEFENSE
# ============================================================

def test_no_username_enumeration_via_status_or_message():
    """Valid and invalid usernames return identical 401 status and error messages."""
    # Existing valid user
    resp_valid_user = client.post("/login", json={"username": "gh00046", "password": "wrong_password_999"})
    # Non-existent user
    resp_invalid_user = client.post("/login", json={"username": "non_existent_dr_smith", "password": "wrong_password_999"})

    assert resp_valid_user.status_code == 401
    assert resp_invalid_user.status_code == 401
    assert resp_valid_user.json()["detail"] == resp_invalid_user.json()["detail"]
    assert resp_valid_user.json()["detail"] == "Invalid username or password."


def test_timing_attack_protection_executes_pbkdf2_on_missing_user():
    """Verify that non-existent user authentication executes constant-time dummy PBKDF2 hash verification."""
    with patch("src.auth.auth_store.verify_password", wraps=verify_password) as mock_verify:
        result = authenticate_user("definitely_non_existent_user_xyz", "somepassword")
        assert result is None
        # Must have called verify_password with DUMMY_PBKDF2_HASH to equalize execution time
        mock_verify.assert_called_with("somepassword", DUMMY_PBKDF2_HASH)


# ============================================================
# 5. LIVE REDIS INTEGRATION & ATOMIC LUA SCRIPTS
# ============================================================

def test_live_redis_backend_and_lua_keys():
    """Verify that rate limiter actively connects to Redis, uses Lua scripts, and sets proper TTL."""
    status = get_rate_limiter_status()
    assert status["backend"] == "redis", f"Expected redis backend, got {status['backend']}"
    assert status["active"] is True

    rc = _get_redis_client()
    assert rc is not None

    test_ip = f"10.99.{uuid.uuid4().hex[:4]}"
    test_user = f"redis_audit_user_{uuid.uuid4().hex[:6]}"

    # Record 3 failures
    record_login_failure(test_ip, test_user)
    record_login_failure(test_ip, test_user)
    record_login_failure(test_ip, test_user)

    # Verify Redis keys exist
    ip_key = f"sih:rate_limit:ip:{test_ip}"
    user_key = f"sih:rate_limit:user:{test_user}"

    assert rc.exists(ip_key) == 1
    assert rc.exists(user_key) == 1

    # Verify cardinality in sorted sets
    assert rc.zcard(ip_key) == 3
    assert rc.zcard(user_key) == 3

    # Verify TTL is set and within expected bounds (window + 15)
    ttl_ip = rc.ttl(ip_key)
    assert 0 < ttl_ip <= WINDOW_SECONDS + 15


# ============================================================
# 6. CONCURRENT MULTI-THREAD ATOMIC RATE LIMITING
# ============================================================

def test_concurrent_burst_logins_atomic_lua():
    """10 concurrent threads simultaneously record failures in Redis. All 10 must be counted atomically without race conditions."""
    rc = _get_redis_client()
    assert rc is not None

    shared_user = f"burst_user_{uuid.uuid4().hex[:6]}"
    shared_ip = "172.16.0.88"

    def worker_record(idx: int):
        record_login_failure(shared_ip, shared_user)
        return True

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_record, i) for i in range(10)]
        for f in futures:
            assert f.result() is True

    user_key = f"sih:rate_limit:user:{shared_user}"
    card = rc.zcard(user_key)
    assert card == 10, f"Expected exactly 10 recorded failures, got {card}"

    # Rate check must immediately block
    with pytest.raises(Exception):
        check_login_rate_limits(shared_ip, shared_user)


# ============================================================
# 7. COUNTER RESET ON SUCCESSFUL AUTHENTICATION
# ============================================================

def test_successful_login_resets_failure_counters():
    """Verify that a successful login resets failure counters for both IP and username."""
    user = "gh00046"
    pwd = "hospital123"
    client_ip = "192.168.1.15"

    # Record 4 failures
    for _ in range(4):
        record_login_failure(client_ip, user)

    rc = _get_redis_client()
    assert rc.zcard(f"sih:rate_limit:user:{user}") == 4
    assert rc.zcard(f"sih:rate_limit:ip:{client_ip}") == 4

    # Now successful login happens
    record_login_success(client_ip, user)

    # Redis keys must be deleted / reset
    assert rc.exists(f"sih:rate_limit:user:{user}") == 0
    assert rc.exists(f"sih:rate_limit:ip:{client_ip}") == 0


# ============================================================
# 8. DISTRIBUTED TOKEN REVOCATION & /LOGOUT ENDPOINT
# ============================================================

def test_token_revocation_lifecycle_and_logout():
    """
    Test complete token revocation lifecycle:
    1. Login to obtain access token.
    2. Access protected endpoint -> 200 OK.
    3. Call POST /logout with token -> 200 OK.
    4. Access protected endpoint with same token -> 401 Unauthorized ('Token has been revoked.').
    """
    # 1. Login
    resp_login = client.post("/login", json={"username": "gh00046", "password": "hospital123"})
    assert resp_login.status_code == 200
    token = resp_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Access protected inventory endpoint
    resp_inv = client.get("/hospitals/GH00046/inventory", headers=headers)
    assert resp_inv.status_code == 200

    # 3. Verify token hash is NOT in blocklist before logout
    assert is_token_revoked(token) is False

    # 4. Perform logout
    resp_logout = client.post("/logout", headers=headers)
    assert resp_logout.status_code == 200
    assert resp_logout.json()["success"] is True

    # 5. Token is now blocklisted in Redis
    assert is_token_revoked(token) is True
    rc = _get_redis_client()
    thash = _token_hash(token)
    assert rc.exists(f"sih:jwt:blocklist:{thash}") == 1

    # 6. Subsequent request must be rejected with 401
    resp_rejected = client.get("/hospitals/GH00046/inventory", headers=headers)
    assert resp_rejected.status_code == 401
    assert "token has been revoked" in resp_rejected.json()["detail"].lower()


def test_logout_without_auth_header_fails():
    """Calling /logout without Bearer token returns 401."""
    resp = client.post("/logout")
    assert resp.status_code == 401


# ============================================================
# 9. PRODUCTION FAIL-FAST ENFORCEMENT
# ============================================================

def test_production_fails_fast_when_redis_url_missing(monkeypatch):
    """Production mode must immediately fail fast if REDIS_URL is unset."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("SIH_REDIS_URL", raising=False)
    reset_redis_client()

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_redis_config()
    assert "Production environment requires Redis" in str(exc_info.value)
    assert "strictly forbidden in production" in str(exc_info.value).lower()

    with pytest.raises(RuntimeError):
        _get_redis_client()

    # Reset environment before teardown
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", REDIS_LOCAL_URL)
    reset_redis_client()


def test_production_fails_fast_when_redis_unreachable(monkeypatch):
    """Production mode must immediately fail fast if Redis connection fails."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:9999/0")  # Invalid port
    reset_redis_client()

    with pytest.raises(RuntimeError) as exc_info:
        validate_production_redis_config()
    assert "Production Redis connectivity check failed" in str(exc_info.value)

    with pytest.raises(RuntimeError):
        _get_redis_client()

    # Reset environment before teardown
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REDIS_URL", REDIS_LOCAL_URL)
    reset_redis_client()


# ============================================================
# 10. JWT SECURITY & ALGORITHM HARDENING
# ============================================================

def test_jwt_none_algorithm_attack_rejected():
    """Tokens signed with 'none' algorithm must be strictly rejected."""
    secret = get_jwt_secret()
    # Craft token with alg: none
    payload = {
        "sub": "USR000001",
        "user_id": "USR000001",
        "username": "gh00046",
        "role": "HOSPITAL",
        "exp": time.time() + 3600,
    }
    # Create unsigned none-alg token
    none_token = jwt.encode(payload, key="", algorithm="none")

    # decode_access_token must reject none-alg token
    decoded = decode_access_token(none_token)
    assert decoded is None

    # Request with none-alg token must be rejected with 401
    resp = client.get("/hospitals/GH00046/inventory", headers={"Authorization": f"Bearer {none_token}"})
    assert resp.status_code == 401


def test_jwt_wrong_secret_signature_rejected():
    """Tokens signed with a different secret must be strictly rejected."""
    payload = {
        "sub": "USR000001",
        "user_id": "USR000001",
        "username": "gh00046",
        "role": "HOSPITAL",
        "exp": time.time() + 3600,
    }
    forged_token = jwt.encode(payload, key="completely-wrong-secret-signature", algorithm=ALGORITHM)

    decoded = decode_access_token(forged_token)
    assert decoded is None

    resp = client.get("/hospitals/GH00046/inventory", headers={"Authorization": f"Bearer {forged_token}"})
    assert resp.status_code == 401


# ============================================================
# 11. SECURITY AUDIT LOGGING & CREDENTIAL REDACTION
# ============================================================

def test_security_audit_logging_redacts_credentials():
    """Verify that log_security_event redacts passwords, secrets, and raw tokens from audit records."""
    captured_logs = []

    class AuditHandler:
        def handle(self, record):
            captured_logs.append(record)

    handler = MagicMock()
    with patch("src.auth.rate_limiter.audit_logger") as mock_logger:
        log_security_event("LOGIN_FAILED", {
            "ip": "10.0.0.1",
            "username": "admin",
            "password": "SuperSecretPassword123!",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload",
        })

        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        msg = args[0]
        extra = kwargs.get("extra", {})

        # Verify password and token are redacted
        assert "SuperSecretPassword123!" not in msg
        assert "sensitive_payload" not in msg
        assert "******" in msg

        audit_data = extra.get("audit_data", {})
        assert audit_data.get("password") == "******"
        assert audit_data.get("token") == "******"


def test_sanitize_redis_url_masks_password():
    """Verify credentials in Redis URLs are masked in logs."""
    url = "redis://:supersecretpass@redis.example.com:6379/0"
    sanitized = sanitize_redis_url(url)
    assert "supersecretpass" not in sanitized
    assert "******" in sanitized
