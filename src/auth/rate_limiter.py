"""
Distributed Rate Limiting, Brute-Force Protection & Token Revocation
AI Powered Smart Hospital Referral System - Phase 17

Provides Redis-backed sliding-window rate limiting with atomic Lua scripts,
dual-key protection (client IP and username), distributed token blocklist
for JWT revocation, and strict production fail-fast enforcement.
"""

import os
import time
import uuid
import hashlib
import logging
from typing import Optional, Dict, Any, List
from collections import defaultdict
from threading import Lock
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import HTTPException

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("sih.security.audit")

# Defaults: 5 failed attempts per 60-second sliding window
MAX_FAILED_ATTEMPTS = int(os.getenv("SIH_LOGIN_MAX_ATTEMPTS", "5"))
WINDOW_SECONDS = int(os.getenv("SIH_LOGIN_WINDOW_SECONDS", "60"))

# In-memory sliding-window store: key -> list of failure timestamps
_IN_MEMORY_FAILURES: dict[str, list[float]] = defaultdict(list)
_IN_MEMORY_REVOKED_TOKENS: dict[str, float] = {}  # token_hash -> expiry_ts
_RATE_LIMIT_LOCK = Lock()

# Redis singleton state
_REDIS_CLIENT = None
_REDIS_INITIALIZED = False


# ============================================================
# ATOMIC LUA SCRIPTS FOR REDIS SLIDING WINDOW
# ============================================================

# Lua Script: Atomic Sliding Window Check
# Checks if the number of failures within the sliding window has reached limit.
# Does NOT record a failure.
LUA_SLIDING_WINDOW_CHECK = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Evict timestamps older than sliding window
redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)

-- Count remaining failure timestamps in current window
local count = redis.call("ZCARD", key)

local retry_after = 0
if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(window - (now - oldest_ts)))
    else
        retry_after = window
    end
    return { 1, count, retry_after }
end

return { 0, count, 0 }
"""

# Lua Script: Atomic Sliding Window Record Failure
# Records a new failure timestamp and evaluates if limit is breached atomically.
LUA_SLIDING_WINDOW_RECORD = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_id = ARGV[4]

-- Evict timestamps older than sliding window
redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)

-- Add current failure timestamp with unique member id
redis.call("ZADD", key, now, member_id)
redis.call("EXPIRE", key, math.ceil(window + 15))

local count = redis.call("ZCARD", key)

local retry_after = 0
if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(window - (now - oldest_ts)))
    else
        retry_after = window
    end
    return { 1, count, retry_after }
end

return { 0, count, 0 }
"""


# ============================================================
# CONFIGURATION & PRODUCTION SAFEGUARDS
# ============================================================

def is_production() -> bool:
    """Return True if running in production or staging mode."""
    env = (os.getenv("ENVIRONMENT") or os.getenv("SIH_ENV") or "").lower().strip()
    return env in ["production", "prod", "staging"]


def sanitize_redis_url(url: Optional[str]) -> str:
    """Mask credentials in Redis connection strings for safe logging."""
    if not url:
        return "<none>"
    try:
        parsed = urlparse(url)
        if parsed.password:
            return url.replace(f":{parsed.password}@", ":******@")
        return url
    except Exception:
        return "<sanitized-redis-url>"


def get_redis_url() -> Optional[str]:
    """Retrieve Redis connection URL from environment."""
    return os.getenv("SIH_REDIS_URL") or os.getenv("REDIS_URL")


def _get_redis_client():
    """
    Get or initialize Redis client.
    Enforces production fail-fast: if running in production, REDIS_URL is mandatory
    and connection failure raises RuntimeError. Silent in-memory fallback is strictly forbidden.
    """
    global _REDIS_CLIENT, _REDIS_INITIALIZED
    if _REDIS_INITIALIZED:
        return _REDIS_CLIENT

    redis_url = get_redis_url()

    if is_production():
        if not redis_url:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: Production environment requires Redis for "
                "distributed rate limiting and token revocation. Set REDIS_URL or SIH_REDIS_URL. "
                "Silent fallback to in-memory rate limiting is strictly forbidden in production."
            )
        try:
            import redis
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            _REDIS_CLIENT = client
            _REDIS_INITIALIZED = True
            logger.info("Connected to Redis for production distributed security: %s", sanitize_redis_url(redis_url))
            return _REDIS_CLIENT
        except Exception as e:
            raise RuntimeError(
                f"CRITICAL SECURITY CONFIGURATION ERROR: Failed to connect to production Redis at "
                f"'{sanitize_redis_url(redis_url)}': {e}. In-memory fallback is strictly forbidden in production."
            )

    # Development / Testing fallback
    _REDIS_INITIALIZED = True
    if not redis_url:
        logger.info("REDIS_URL not configured. Using thread-safe in-memory sliding-window rate limiter.")
        return None

    try:
        import redis
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        logger.info("Connected to Redis for distributed rate limiting: %s", sanitize_redis_url(redis_url))
        return _REDIS_CLIENT
    except Exception as e:
        logger.warning(
            "Failed to connect to Redis at %s (%s). Falling back to in-memory rate limiter in dev mode.",
            sanitize_redis_url(redis_url),
            e,
        )
        return None


def reset_redis_client():
    """Reset the singleton Redis client. Used for environment change testing."""
    global _REDIS_CLIENT, _REDIS_INITIALIZED
    if _REDIS_CLIENT is not None:
        try:
            _REDIS_CLIENT.close()
        except Exception:
            pass
    _REDIS_CLIENT = None
    _REDIS_INITIALIZED = False


def validate_production_redis_config():
    """
    Startup invariant check: fails application initialization if Redis configuration
    is missing or unreachable in production environments.
    """
    if not is_production():
        return

    redis_url = get_redis_url()
    if not redis_url:
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: Production environment requires Redis for "
            "distributed rate limiting and token revocation. Set REDIS_URL or SIH_REDIS_URL. "
            "Silent fallback to in-memory rate limiting is strictly forbidden in production."
        )

    try:
        import redis
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        client.close()
    except Exception as e:
        raise RuntimeError(
            f"CRITICAL SECURITY CONFIGURATION ERROR: Production Redis connectivity check failed at "
            f"'{sanitize_redis_url(redis_url)}': {e}."
        )


def get_rate_limiter_status() -> dict:
    """Return current rate limiting backend status for health checks and audits."""
    redis_client = _get_redis_client()
    backend = "redis" if redis_client is not None else "in_memory"
    return {
        "backend": backend,
        "max_attempts": MAX_FAILED_ATTEMPTS,
        "window_seconds": WINDOW_SECONDS,
        "active": True,
        "is_production": is_production(),
    }


# ============================================================
# STRUCTURED SECURITY AUDIT LOGGING
# ============================================================

def log_security_event(event_type: str, details: dict) -> None:
    """
    Record a security audit log event with sanitized metadata.
    Strictly redacts passwords, secrets, and raw authentication tokens.
    """
    sanitized = {}
    for k, v in details.items():
        if k.lower() in ["password", "secret", "token", "authorization", "auth", "plain_password"]:
            sanitized[k] = "******"
        else:
            sanitized[k] = v

    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "timestamp": timestamp,
        "event": event_type,
        **sanitized,
    }
    msg = f"[SECURITY_AUDIT] {event_type} - {sanitized}"
    if event_type in ["RATE_LIMIT_EXCEEDED", "LOGIN_FAILED", "UNAUTHORIZED_ACCESS"]:
        audit_logger.warning(msg, extra={"audit_data": log_entry})
    else:
        audit_logger.info(msg, extra={"audit_data": log_entry})


# ============================================================
# RATE LIMITING LOGIC (ATOMIC REDIS & IN-MEMORY)
# ============================================================

def _check_key_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """Internal check for a specific rate-limit key."""
    now = time.time()
    redis_client = _get_redis_client()

    if redis_client is not None:
        try:
            redis_key = f"sih:rate_limit:{key}"
            result = redis_client.eval(
                LUA_SLIDING_WINDOW_CHECK,
                1,
                redis_key,
                str(now),
                str(window_seconds),
                str(max_attempts),
            )
            # result is [is_limited, current_count, retry_after]
            is_limited = bool(result[0])
            retry_after = int(result[2])
            if is_limited:
                log_security_event("RATE_LIMIT_EXCEEDED", {
                    "key": key,
                    "retry_after": retry_after,
                    "attempts": int(result[1]),
                })
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            return
        except HTTPException:
            raise
        except Exception as e:
            if is_production():
                raise RuntimeError(f"Production Redis rate limiter error: {e}")
            logger.error("Redis rate limit check failed (%s). Falling back to in-memory check in dev.", e)

    # In-memory rate limiting fallback
    with _RATE_LIMIT_LOCK:
        timestamps = _IN_MEMORY_FAILURES[key]
        valid_timestamps = [ts for ts in timestamps if now - ts < window_seconds]
        _IN_MEMORY_FAILURES[key] = valid_timestamps

        if len(valid_timestamps) >= max_attempts:
            oldest_ts = valid_timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest_ts)))
            log_security_event("RATE_LIMIT_EXCEEDED", {
                "key": key,
                "retry_after": retry_after,
                "attempts": len(valid_timestamps),
            })
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


def check_rate_limit(key: str, max_attempts: int | None = None, window_seconds: int | None = None) -> None:
    """
    Check if a given client key has exceeded the allowed failed login attempts.
    Raises HTTPException 429 with Retry-After header if limit exceeded.
    """
    limit = max_attempts or MAX_FAILED_ATTEMPTS
    window = window_seconds or WINDOW_SECONDS
    _check_key_rate_limit(f"login:{key}", limit, window)


def check_login_rate_limits(
    client_ip: str,
    username: str,
    max_attempts: int | None = None,
    window_seconds: int | None = None,
) -> None:
    """
    Dual-key rate limiting check:
    1. Checks IP-based rate limit (protects against credential stuffing across multiple accounts).
    2. Checks User-based rate limit (protects against distributed brute-force targeting one account).
    Does NOT leak whether username exists or which limit was triggered.
    """
    limit = max_attempts or MAX_FAILED_ATTEMPTS
    window = window_seconds or WINDOW_SECONDS

    # 1. Check IP rate limit
    ip_key = f"ip:{client_ip}"
    _check_key_rate_limit(ip_key, limit, window)

    # 2. Check User rate limit
    normalized_user = username.lower().strip()
    user_key = f"user:{normalized_user}"
    _check_key_rate_limit(user_key, limit, window)


def record_failure(key: str, window_seconds: int | None = None) -> None:
    """Record a failed login attempt for a generic key."""
    window = window_seconds or WINDOW_SECONDS
    limit = MAX_FAILED_ATTEMPTS
    now = time.time()
    member_id = f"{now}:{uuid.uuid4().hex[:8]}"

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_key = f"sih:rate_limit:login:{key}"
            redis_client.eval(
                LUA_SLIDING_WINDOW_RECORD,
                1,
                redis_key,
                str(now),
                str(window),
                str(limit),
                member_id,
            )
            return
        except Exception as e:
            if is_production():
                raise RuntimeError(f"Production Redis failure recording error: {e}")
            logger.error("Redis record_failure failed (%s). Recording in memory.", e)

    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_FAILURES[f"login:{key}"].append(now)


def record_login_failure(
    client_ip: str,
    username: str,
    window_seconds: int | None = None,
) -> None:
    """
    Record a failed login attempt across both IP and user keys atomically.
    Executes for both existing and non-existing usernames to prevent user enumeration.
    """
    window = window_seconds or WINDOW_SECONDS
    limit = MAX_FAILED_ATTEMPTS
    now = time.time()

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            # Record IP failure
            ip_key = f"sih:rate_limit:ip:{client_ip}"
            member_ip = f"{now}:{uuid.uuid4().hex[:8]}"
            redis_client.eval(
                LUA_SLIDING_WINDOW_RECORD,
                1,
                ip_key,
                str(now),
                str(window),
                str(limit),
                member_ip,
            )

            # Record User failure
            normalized_user = username.lower().strip()
            user_key = f"sih:rate_limit:user:{normalized_user}"
            member_user = f"{now}:{uuid.uuid4().hex[:8]}"
            redis_client.eval(
                LUA_SLIDING_WINDOW_RECORD,
                1,
                user_key,
                str(now),
                str(window),
                str(limit),
                member_user,
            )
            return
        except Exception as e:
            if is_production():
                raise RuntimeError(f"Production Redis failure recording error: {e}")
            logger.error("Redis record_login_failure failed (%s). Recording in memory.", e)

    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_FAILURES[f"ip:{client_ip}"].append(now)
        _IN_MEMORY_FAILURES[f"user:{username.lower().strip()}"].append(now)


def record_success(key: str) -> None:
    """Reset failure counter upon successful authentication for a generic key."""
    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_key = f"sih:rate_limit:login:{key}"
            redis_client.delete(redis_key)
        except Exception as e:
            logger.error("Redis record_success failed (%s).", e)

    with _RATE_LIMIT_LOCK:
        if f"login:{key}" in _IN_MEMORY_FAILURES:
            del _IN_MEMORY_FAILURES[f"login:{key}"]
        if key in _IN_MEMORY_FAILURES:
            del _IN_MEMORY_FAILURES[key]


def record_login_success(client_ip: str, username: str) -> None:
    """Reset both IP and User failure counters upon successful authentication."""
    normalized_user = username.lower().strip()
    redis_client = _get_redis_client()

    if redis_client is not None:
        try:
            ip_key = f"sih:rate_limit:ip:{client_ip}"
            user_key = f"sih:rate_limit:user:{normalized_user}"
            redis_client.delete(ip_key, user_key)
        except Exception as e:
            logger.error("Redis record_login_success failed (%s).", e)

    with _RATE_LIMIT_LOCK:
        if f"ip:{client_ip}" in _IN_MEMORY_FAILURES:
            del _IN_MEMORY_FAILURES[f"ip:{client_ip}"]
        if f"user:{normalized_user}" in _IN_MEMORY_FAILURES:
            del _IN_MEMORY_FAILURES[f"user:{normalized_user}"]


def reset_rate_limits() -> None:
    """Clear all rate limit data. Used for testing teardown."""
    try:
        redis_client = _get_redis_client()
        if redis_client is not None:
            keys = redis_client.keys("sih:rate_limit:*")
            if keys:
                redis_client.delete(*keys)
    except Exception:
        pass

    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_FAILURES.clear()


# ============================================================
# TOKEN REVOCATION & BLOCKLIST (DISTRIBUTED LOGOUT)
# ============================================================

def _token_hash(token: str) -> str:
    """Generate SHA-256 digest of token to avoid storing raw sensitive tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def revoke_token(token: str, exp_timestamp: Optional[float] = None) -> bool:
    """
    Add a JWT to the distributed revocation blocklist.
    Redis key: sih:jwt:blocklist:<token_hash>
    TTL: remaining lifetime in seconds.
    """
    token_hash = _token_hash(token)
    now = time.time()

    if exp_timestamp is not None:
        remaining = int(exp_timestamp - now)
    else:
        remaining = 3600  # Default 1 hour fallback

    if remaining <= 0:
        # Already expired; no need to persist in blocklist
        return True

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_key = f"sih:jwt:blocklist:{token_hash}"
            redis_client.set(redis_key, "revoked", ex=remaining)
            log_security_event("TOKEN_REVOKED", {
                "token_hash": token_hash[:16] + "...",
                "ttl_seconds": remaining,
            })
            return True
        except Exception as e:
            if is_production():
                raise RuntimeError(f"Production Redis token revocation error: {e}")
            logger.error("Redis revoke_token failed (%s). Using in-memory blocklist.", e)

    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_REVOKED_TOKENS[token_hash] = now + remaining
        log_security_event("TOKEN_REVOKED", {
            "token_hash": token_hash[:16] + "...",
            "ttl_seconds": remaining,
            "backend": "in_memory",
        })
    return True


def is_token_revoked(token: str) -> bool:
    """
    Check if a JWT has been revoked / blocklisted.
    Returns True if token hash exists in Redis blocklist or active in-memory store.
    """
    token_hash = _token_hash(token)
    now = time.time()

    redis_client = _get_redis_client()
    if redis_client is not None:
        try:
            redis_key = f"sih:jwt:blocklist:{token_hash}"
            val = redis_client.get(redis_key)
            return val is not None
        except Exception as e:
            if is_production():
                raise RuntimeError(f"Production Redis blocklist check error: {e}")
            logger.error("Redis is_token_revoked check failed (%s). Checking in-memory.", e)

    with _RATE_LIMIT_LOCK:
        exp = _IN_MEMORY_REVOKED_TOKENS.get(token_hash)
        if exp is not None:
            if exp > now:
                return True
            else:
                del _IN_MEMORY_REVOKED_TOKENS[token_hash]
    return False


def reset_blocklist() -> None:
    """Clear all blocklisted tokens. Used for testing teardown."""
    try:
        redis_client = _get_redis_client()
        if redis_client is not None:
            keys = redis_client.keys("sih:jwt:blocklist:*")
            if keys:
                redis_client.delete(*keys)
    except Exception:
        pass

    with _RATE_LIMIT_LOCK:
        _IN_MEMORY_REVOKED_TOKENS.clear()
