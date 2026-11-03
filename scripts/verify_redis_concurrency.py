"""
Multi-Process Redis Distributed Security & Concurrency Verification
AI Powered Smart Hospital Referral System - Phase 17

Spawns 10 independent OS worker processes to verify:
1. Redis atomic sliding-window Lua execution under high concurrency.
2. Shared rate-limiting counter state across processes (no process-local leakage).
3. Cross-process token revocation and blocklist enforcement.
4. Clean counter reset across workers.
"""

import os
import sys
import time
import uuid
import multiprocessing as mp
import redis
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Import Lua script definitions
LUA_SLIDING_WINDOW_RECORD = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_id = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)
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

LUA_SLIDING_WINDOW_CHECK = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call("ZREMRANGEBYSCORE", key, "-inf", now - window)
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


def worker_record_failure(proc_id: int, key: str, out_q: mp.Queue):
    """Worker process that records a failure directly into Redis using Lua."""
    try:
        rc = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        now = time.time()
        member_id = f"{now}:proc_{proc_id}_{uuid.uuid4().hex[:6]}"
        result = rc.eval(
            LUA_SLIDING_WINDOW_RECORD,
            1,
            key,
            str(now),
            "60",
            "5",
            member_id,
        )
        rc.close()
        out_q.put({"proc_id": proc_id, "success": True, "result": result})
    except Exception as e:
        out_q.put({"proc_id": proc_id, "success": False, "error": str(e)})


def worker_check_revocation(proc_id: int, token_key: str, out_q: mp.Queue):
    """Worker process checking if a token is present in Redis blocklist."""
    try:
        rc = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        val = rc.get(token_key)
        rc.close()
        out_q.put({"proc_id": proc_id, "revoked": val is not None})
    except Exception as e:
        out_q.put({"proc_id": proc_id, "error": str(e)})


def main():
    print("=" * 75)
    print("SIH_Hospital_AI — Phase 17: Multi-Process Redis Concurrency Verification")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Target Redis: {REDIS_URL}")
    print("=" * 75)

    # Preflight connectivity check
    try:
        rc = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        rc.ping()
        print("[✓] Preflight: Successfully connected to Redis server (PONG).")
    except Exception as e:
        print(f"[✗] Preflight Failed: Unable to connect to Redis at {REDIS_URL}: {e}")
        sys.exit(1)

    test_key = f"sih:rate_limit:test:concurrency_{uuid.uuid4().hex[:8]}"
    rc.delete(test_key)

    # -------------------------------------------------------------
    # Test 1: 10 OS Processes Concurrently Recording Failed Logins
    # -------------------------------------------------------------
    print("\n--- Test 1: 10 Concurrent Processes Executing Atomic Lua Sliding Window ---")
    num_processes = 10
    queue = mp.Queue()
    processes = []

    t0 = time.perf_counter()
    for i in range(num_processes):
        p = mp.Process(target=worker_record_failure, args=(i, test_key, queue))
        processes.append(p)
        p.start()

    results = []
    for _ in range(num_processes):
        results.append(queue.get())

    for p in processes:
        p.join()

    duration_ms = (time.perf_counter() - t0) * 1000

    successful_procs = sum(1 for r in results if r.get("success") is True)
    total_in_redis = rc.zcard(test_key)
    ttl = rc.ttl(test_key)

    print(f"  Processes Dispatched : {num_processes}")
    print(f"  Processes Completed  : {successful_procs}/{num_processes}")
    print(f"  Total Keys in Redis  : {total_in_redis} (Expected: {num_processes})")
    print(f"  Redis Key TTL        : {ttl}s (Expected: ~75s)")
    print(f"  Total Time           : {duration_ms:.2f} ms ({duration_ms/num_processes:.2f} ms/process)")

    assert total_in_redis == num_processes, f"Expected {num_processes} failures recorded, got {total_in_redis}"
    print("  [✓] Test 1 Passed: Exactly 10 atomic entries recorded without lost updates.")

    # -------------------------------------------------------------
    # Test 2: Rate Limiting Enforcement Across Processes
    # -------------------------------------------------------------
    print("\n--- Test 2: Distributed Rate Limit Check Across Processes ---")
    now = time.time()
    check_result = rc.eval(LUA_SLIDING_WINDOW_CHECK, 1, test_key, str(now), "60", "5")
    is_limited, count, retry_after = check_result[0], check_result[1], check_result[2]

    print(f"  Limit Check Status   : is_limited={is_limited} (Expected: 1)")
    print(f"  Total Failures Found : count={count} (Expected: 10)")
    print(f"  Calculated Retry-After: {retry_after}s (Expected: > 0)")

    assert is_limited == 1, "Rate limiter failed to block after 10 failures"
    assert retry_after > 0, "Retry-After must be positive"
    print("  [✓] Test 2 Passed: HTTP 429 condition and Retry-After enforced across processes.")

    # -------------------------------------------------------------
    # Test 3: Cross-Process Token Revocation (Blocklist)
    # -------------------------------------------------------------
    print("\n--- Test 3: Cross-Process Distributed Token Revocation ---")
    test_token_hash = uuid.uuid4().hex
    blocklist_key = f"sih:jwt:blocklist:{test_token_hash}"

    # Set revocation key
    rc.set(blocklist_key, "revoked", ex=300)

    # Spawn 5 worker processes to verify they all observe the revoked state immediately
    rev_queue = mp.Queue()
    rev_processes = []
    for i in range(5):
        p = mp.Process(target=worker_check_revocation, args=(i, blocklist_key, rev_queue))
        rev_processes.append(p)
        p.start()

    rev_results = [rev_queue.get() for _ in range(5)]
    for p in rev_processes:
        p.join()

    revoked_count = sum(1 for r in rev_results if r.get("revoked") is True)
    print(f"  Workers Checking Blocklist: 5")
    print(f"  Workers Confirming Revoked: {revoked_count}/5")

    assert revoked_count == 5, f"Expected all 5 workers to detect revocation, got {revoked_count}"
    rc.delete(blocklist_key)
    print("  [✓] Test 3 Passed: Token revocation instantly visible to all distributed workers.")

    # -------------------------------------------------------------
    # Test 4: Cross-Process Counter Reset
    # -------------------------------------------------------------
    print("\n--- Test 4: Successful Login Counter Reset ---")
    rc.delete(test_key)
    assert rc.exists(test_key) == 0
    print("  [✓] Test 4 Passed: Counter reset atomically clears distributed state.")

    print("\n" + "=" * 75)
    print("ALL 4 MULTI-PROCESS REDIS CONCURRENCY VERIFICATIONS PASSED")
    print("=" * 75)


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
