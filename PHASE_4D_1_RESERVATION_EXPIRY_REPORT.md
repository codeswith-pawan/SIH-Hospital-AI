# SIH HOSPITAL AI — PHASE 4D-1 IMPLEMENTATION REPORT
## Automated Bed Reservation Expiry Worker

**Completion Date:** 2026-11-11  
**Project Path:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Git Branch:** `master` (Commit `460af41`)  
**Git Stash Status:** `stash@{0}` intact  
**Protected Database (`sih_hospital_dev`):** Pristine & untouched (500 hospitals, 8 users verified)  
**Target Database (`sih_hospital_phase1_run_test`):** Migration 005 applied; live tests passing  
**Final Phase Status:** **`ACCEPTED — PHASE 4D-1`**

---

## 1. Implementation Summary

Phase 4D-1 introduces an autonomous, transactional PostgreSQL background worker (`ReservationExpiryWorker`) that automatically identifies expired bed holds and restores hospital bed capacity without requiring manual HTTP requests.

### Core Architecture Highlights
1. **Authoritative PostgreSQL Time:** Expired reservations are detected strictly against PostgreSQL database time (`func.now()`), eliminating timezone discrepancies and server clock drift.
2. **ACID Row-Level Concurrency:** Queries candidate reservations using `SELECT ... WHERE status = 'RESERVED' AND expires_at < NOW() ORDER BY expires_at ASC LIMIT :batch_size FOR UPDATE SKIP LOCKED`. Multiple concurrent workers process different queues without duplicate releases or phantom reads.
3. **Savepoint Fault Isolation:** Batch processing uses transaction savepoints (`session.begin_nested()`). A malformed or conflicting reservation is safely rolled back without aborting the remaining expirations in the batch.
4. **Guaranteed Status Policy Enforcement:** In accordance with established business policy, confirmed reservations (`status = 'CONFIRMED'`) are guaranteed and protected from automated expiry. Only unconfirmed holds (`status = 'RESERVED'`) can expire. Occupied and discharged beds are completely shielded.
5. **Accurate Category Accounting:** Mirrors `reserve_bed_direct` by restoring available capacity for General, ICU, and Emergency beds up to their licensed limits without affecting occupied counters.
6. **Container-Safe Shared Heartbeat:** Persists worker heartbeats into the PostgreSQL `worker_heartbeats` table. `/metrics` on the API container reads this shared table to expose live operational metrics and detect worker stalls (>90s stale threshold).
7. **Production Docker Compose Service:** Dedicated `reservation_expiry_worker` service added to `docker-compose.prod.yml` running as non-root user `sihuser` with native container healthcheck probe.

---

## 2. Files Created & Modified

### Created Files
1. `src/workers/reservation_expiry_worker.py`: Autonomous background daemon with batch processing, bounded exponential backoff (up to 5 min), graceful SIGINT/SIGTERM shutdown, and `--healthcheck` CLI probe.
2. `migrations/005_worker_heartbeats.sql`: Schema migration for container-safe worker heartbeat and metrics tracking.
3. `tests/test_reservation_expiry_worker.py`: Comprehensive 26-test suite covering basic behavior, state protection, reliability, concurrency, and observability.
4. `PHASE_4D_1_RESERVATION_EXPIRY_REPORT.md`: This completion deliverable.

### Modified Files
1. `src/database/pg_models.py`: Added `WorkerHeartbeat` model with status checks and timestamps.
2. `src/database/pg_repository.py`:
   - Enhanced `expire_reservation_direct` to accept either `reservation_id` or `(hospital_id, patient_id)`.
   - Added `get_expired_reservations(batch_size)` to detect candidate reservations using database time.
   - Added `process_expired_reservations_batch(batch_size, user_id)` utilizing `FOR UPDATE SKIP LOCKED` and nested savepoints.
3. `src/api/observability.py`:
   - Enhanced `get_system_metrics()` to query `worker_heartbeats` table from PostgreSQL.
   - Exposed operational metrics keys (`reservation_expiry_worker_running`, `reservation_expiry_last_success_timestamp`, etc.).
4. `docker-compose.prod.yml`:
   - Added container service `reservation_expiry_worker` with non-root security context, isolated network, and healthcheck.

---

## 3. Database Migration Details

**Migration File:** `migrations/005_worker_heartbeats.sql`

```sql
-- Migration 005: Worker Heartbeats Table for Container-Safe Observability
-- AI Powered Smart Hospital Referral System - Phase 4D-1

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_name VARCHAR(64) PRIMARY KEY,
    worker_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_success_at TIMESTAMPTZ,
    last_error_at TIMESTAMPTZ,
    last_error TEXT,
    processed_total BIGINT NOT NULL DEFAULT 0,
    failed_total BIGINT NOT NULL DEFAULT 0,
    batch_size INT NOT NULL DEFAULT 100,
    duration_seconds FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_worker_status CHECK (status IN ('RUNNING', 'STOPPED', 'FAILED', 'IDLE'))
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeat_status ON worker_heartbeats(status, last_heartbeat);
```

- **Applied To:** `sih_hospital_phase1_run_test` (Exit code: 0).
- **Protected Environment:** `sih_hospital_dev` was **NEVER** modified, migrated, or written to.

---

## 4. Expiry Eligibility Rules

A reservation is eligible for automated expiration if and only if all of the following conditions hold:

| Rule | Requirement | Validation Implementation |
| :--- | :--- | :--- |
| **Status Rule** | Must be strictly `RESERVED` | `BedReservation.status == 'RESERVED'` |
| **Guaranteed Policy** | `CONFIRMED` beds do NOT auto-expire | `CONFIRMED` rejected with `CONFIRMED_CANNOT_EXPIRE` |
| **Occupancy Shield** | `OCCUPIED` beds do NOT expire | `OCCUPIED` rejected with `BED_OCCUPIED` |
| **Discharge Shield** | `RELEASED` beds do NOT expire | `RELEASED` rejected with `ALREADY_RELEASED` |
| **Referral Active** | Referral cannot be finished | `Referral.status NOT IN ('DISCHARGED', 'CANCELLED', 'COMPLETED')` |
| **Authoritative Clock**| Timestamp earlier than DB time | `BedReservation.expires_at < func.now()` |

---

## 5. Concurrency & Locking Strategy

```
Worker 1                                           Worker 2
   │                                                  │
   ├─► SELECT reservation_id                          ├─► SELECT reservation_id
   │   FROM bed_reservations                          │   FROM bed_reservations
   │   WHERE status = 'RESERVED'                      │   WHERE status = 'RESERVED'
   │     AND expires_at < NOW()                       │     AND expires_at < NOW()
   │   FOR UPDATE SKIP LOCKED                         │   FOR UPDATE SKIP LOCKED
   │   (Locks Rows 1..100)                            │   (Skips Rows 1..100, Locks 101..200)
   │                                                  │
   ├─► SAVEPOINT sp_res_1                             ├─► SAVEPOINT sp_res_101
   │   Lock Bed & Hospital (FOR UPDATE)               │   Lock Bed & Hospital (FOR UPDATE)
   │   Recheck eligibility inside lock                │   Recheck eligibility inside lock
   │   Bed -> AVAILABLE                               │   Bed -> AVAILABLE
   │   Hospital.available += 1                        │   Hospital.available += 1
   │   BedReservation -> EXPIRED                      │   BedReservation -> EXPIRED
   │   Referral -> CANCELLED                          │   Referral -> CANCELLED
   │   Insert AuditLog (AUTO_EXPIRE)                  │   Insert AuditLog (AUTO_EXPIRE)
   │   RELEASE SAVEPOINT sp_res_1                     │   RELEASE SAVEPOINT sp_res_101
   │                                                  │
   └─► COMMIT (Releases Locks 1..100)                 └─► COMMIT (Releases Locks 101..200)
```

- **Race Condition Immunity:** If a staff member marks a bed `CONFIRMED` or `OCCUPIED` concurrently, the worker acquires the row lock, rechecks `res.status`, observes it is no longer `RESERVED`, and safely skips expiration.

---

## 6. Worker & Docker Configuration

### CLI Parameters & Environment Variables
- `RESERVATION_EXPIRY_BATCH_SIZE` (`--batch-size`): Default `100`.
- `RESERVATION_EXPIRY_POLL_INTERVAL` (`--interval`): Default `30.0` seconds.
- `RESERVATION_EXPIRY_MAX_BACKOFF` (`--max-backoff`): Default `300.0` seconds (5 min).
- `--run-once`: Executes a single processing pass and exits (ideal for cron or test suites).
- `--healthcheck`: Probes DB connectivity and heartbeat freshness (exits 0 if healthy, 1 if unhealthy).

### Docker Compose Service Definition
```yaml
  # 5. Standalone Automated Bed Reservation Expiry Worker
  reservation_expiry_worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: sih_reservation_expiry_worker_prod
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_started
      postgres:
        condition: service_healthy
    env_file:
      - .env.production
    environment:
      ENVIRONMENT: production
      DATABASE_URL: postgresql://${POSTGRES_USER:-sih_admin}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-sih_hospital_prod}
      RESERVATION_EXPIRY_POLL_INTERVAL: "30.0"
      RESERVATION_EXPIRY_BATCH_SIZE: "100"
    command: ["python", "-m", "src.workers.reservation_expiry_worker"]
    networks:
      - sih_internal
    healthcheck:
      test: ["CMD", "python", "-m", "src.workers.reservation_expiry_worker", "--healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

---

## 7. Metrics & Telemetry Implementation

`/metrics` returns live metrics from the shared `worker_heartbeats` table:

```json
{
  "reservation_expiry_worker": {
    "reservation_expiry_worker_running": true,
    "reservation_expiry_last_success_timestamp": "2026-11-11T17:24:50.123456+00:00",
    "reservation_expiry_processed_total": 58,
    "reservation_expiry_failed_total": 0,
    "reservation_expiry_batch_size": 100,
    "reservation_expiry_processing_duration_seconds": 0.428,
    "reservation_expiry_last_error_timestamp": null,
    "heartbeat_age_seconds": 12.4,
    "status": "RUNNING",
    "worker_id": "expiry_worker_48884_48ffc8f6"
  },
  "reservation_expiry_worker_running": true,
  "reservation_expiry_last_success_timestamp": "2026-11-11T17:24:50.123456+00:00",
  "reservation_expiry_processed_total": 58,
  "reservation_expiry_failed_total": 0,
  "reservation_expiry_batch_size": 100,
  "reservation_expiry_processing_duration_seconds": 0.428,
  "reservation_expiry_last_error_timestamp": null
}
```

- **Stale Detection:** If `heartbeat_age_seconds > 90.0`, `reservation_expiry_worker_running` automatically flips to `false` and status becomes `"STALE"`.
- **Privacy Assurance:** Zero patient identifiers, names, phone numbers, or tokens are logged or included in metrics.

---

## 8. Test Verification & Results

### Dedicated Test Suite: `tests/test_reservation_expiry_worker.py`
Command: `.venv/bin/python -m pytest tests/test_reservation_expiry_worker.py -v`  
Result: **26 / 26 PASSED** in 1.65s (Exit Code: 0)

| Category | # | Test Name | Result |
| :--- | :---: | :--- | :---: |
| **Basic Behavior** | 1 | `test_01_expired_eligible_reservation_detected` | **PASS** |
| | 2 | `test_02_expired_reservation_transitions_to_expired` | **PASS** |
| | 3 | `test_03_available_capacity_increases_exactly_once` | **PASS** |
| | 4 | `test_04_reserved_capacity_decreases_correctly` | **PASS** |
| | 5 | `test_05_correct_department_inventory_is_updated` | **PASS** |
| | 6 | `test_06_categories_general_icu_emergency_covered` | **PASS** |
| | 7 | `test_07_unexpired_reservation_remains_unchanged` | **PASS** |
| **State Protection**| 8 | `test_08_occupied_reservation_never_expired` | **PASS** |
| | 9 | `test_09_discharged_reservation_never_expired` | **PASS** |
| | 10 | `test_10_cancelled_reservation_never_expired` | **PASS** |
| | 11 | `test_11_already_expired_reservation_not_reprocessed` | **PASS** |
| | 12 | `test_12_confirmed_reservation_follows_business_policy` | **PASS** |
| **Reliability** | 13 | `test_13_repeated_processing_does_not_double_release` | **PASS** |
| | 14 | `test_14_database_failure_rolls_back_all_changes` | **PASS** |
| | 15 | `test_15_worker_recovers_after_transient_error` | **PASS** |
| | 16 | `test_16_empty_queue_does_not_cause_excessive_cpu` | **PASS** |
| | 17 | `test_17_graceful_shutdown_works` | **PASS** |
| | 18 | `test_18_batch_limits_are_respected` | **PASS** |
| **Concurrency** | 19 | `test_19_concurrent_workers_skip_locked_no_double_expire` | **PASS** |
| | 20 | `test_20_concurrent_confirmation_and_expiry_valid_final_state`| **PASS** |
| | 21 | `test_21_concurrent_occupancy_and_expiry_valid_counters` | **PASS** |
| | 22 | `test_22_cross_hospital_isolation` | **PASS** |
| **Observability** | 23 | `test_23_processed_metric_incremented` | **PASS** |
| | 24 | `test_24_failure_metric_incremented` | **PASS** |
| | 25 | `test_25_worker_heartbeat_stale_detection` | **PASS** |
| | 26 | `test_26_sensitive_information_absent_from_logs_and_metrics` | **PASS** |

---

## 9. Full Regression Suite Results

| Test Target / Suite | Command | Exit Code | Result | Status |
| :--- | :--- | :---: | :--- | :---: |
| **New Expiry Worker Suite** | `.venv/bin/python -m pytest tests/test_reservation_expiry_worker.py -v` | `0` | 26 / 26 passed in 1.65s | **PASS** |
| **Inventory Accounting** | `.venv/bin/python -m pytest tests/test_inventory_accounting_consistency.py -v` | `0` | 12 / 12 passed in 0.49s | **PASS** |
| **Operational Inventory** | `.venv/bin/python -m pytest tests/test_operational_inventory.py -v` | `0` | 14 / 14 passed in 0.83s | **PASS** |
| **Phase 4B (Bed Lifecycle)** | `.venv/bin/python -m pytest tests/test_phase4b_referral_bed_lifecycle.py -v` | `0` | 13 / 13 passed in 0.79s | **PASS** |
| **Phase 4C (Admin PG)** | `.venv/bin/python -m pytest tests/test_phase4c_admin_postgres.py -v` | `0` | 15 / 15 passed in 0.51s | **PASS** |
| **Referral Lifecycle** | `.venv/bin/python -m pytest tests/test_referral_and_bed_lifecycle.py -v` | `0` | 15 / 15 passed in 0.62s | **PASS** |
| **Outbox Reliability** | `.venv/bin/python -m pytest tests/test_outbox_worker_reliability.py -v` | `0` | 7 / 7 passed in 0.35s | **PASS** |
| **Observability & Security** | `.venv/bin/python -m pytest tests/test_observability_and_security_headers.py -v`| `0` | 5 / 5 passed in 0.27s | **PASS** |
| **Full Backend Regression** | `.venv/bin/python -m pytest tests/` | `0` | **368 / 368 passed** in 31.56s | **PASS** |
| **TypeScript Typecheck** | `cd frontend && npx tsc --noEmit` | `0` | 0 errors | **PASS** |
| **ESLint Check** | `cd frontend && npm run lint` | `0` | 0 fatal errors (55 warnings) | **PASS** |
| **Next.js Production Build**| `cd frontend && npm run build` | `0` | 15 / 15 routes compiled in 580ms | **PASS** |
| **Playwright Full Suite** | `cd frontend && npx playwright test` | `0` | **20 / 20 passed** in 1.1m | **PASS** |

---

## 10. Safety Boundaries & Repository Verification

1. **`git status` Verification:** Clean working branch, zero unstaged changes outside the task scope, zero commits, zero pushes.
2. **`git stash list` Verification:** `stash@{0}: On master: Backup before GitHub repository synchronization` remains completely intact.
3. **Database Isolation (`sih_hospital_dev`):**
   - Verified via direct SQL query:
     - `SELECT count(*) FROM hospitals;` $\rightarrow$ **500**
     - `SELECT count(*) FROM users;` $\rightarrow$ **8**
   - Zero migrations, writes, or tests executed against `sih_hospital_dev`.

---

## 11. Known Limitations & Phase 4D-2 Scope

- **Email Outbox Integration:** In Phase 4D-1, expired reservations restore capacity and record `AuditLog` events. Dispatching email alerts to patients and referring hospitals on expiration is part of the subsequent Phase 4D-2 event-bus integration.

---

## 12. Final Acceptance Verdict

# **ACCEPTED — PHASE 4D-1**

The automated PostgreSQL bed reservation expiry worker is fully implemented, verified with 26 dedicated tests, and validated across 368 backend tests and 20 Playwright browser tests with zero regressions. Execution has stopped in accordance with instructions. Awaiting your review.
