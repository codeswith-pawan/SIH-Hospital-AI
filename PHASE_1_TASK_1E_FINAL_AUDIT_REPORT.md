# Phase 1 — Task 1E: Final Three-Issue Audit & Verification Report

**Date:** 2026-11-03  
**Project:** SIH Hospital Referral System (`~/Desktop/SIH_Hospital_AI`)  
**Status:** ALL THREE FINDINGS RESOLVED & LIVE-VERIFIED  

---

## 1. Executive Summary & Verification Verdict

Following the Task 1E remediation audit, three critical reliability and security areas were identified for final verification:
1. **F-1: Email Outbox Crash Recovery & At-Least-Once Delivery Semantics**
2. **F-2: Password Reset Atomicity, Concurrency Serialization & Session Revocation**
3. **F-3: Migration 003 Compatibility & PostgreSQL 17 Verification**

All three issues have been implemented, tested under multithreaded concurrency against live PostgreSQL, and verified with **155 passing automated tests (114 registration + 41 core system)** with **0 failures and 0 skipped tests**.

---

## 2. Issue-by-Issue Implementation & Verification Evidence

### 2.1 F-1: Email Outbox Crash Recovery

#### 1. Worker Crash Analysis & Lease Mechanism
- **Previous Risk:** If a worker claimed an event and transitioned its status to `'PROCESSING'`, but crashed or timed out before completion, the row remained permanently stranded in `'PROCESSING'` because previous queries only polled `'PENDING'` or `'FAILED'`.
- **Lease Implementation:** Introduced a configurable processing lease (`DEFAULT_LEASE_TIMEOUT_SECONDS = 300` / 5 minutes).
- **Candidate Query:** The selection query now polls:
  ```python
  lease_cutoff = now - timedelta(seconds=lease_timeout_seconds)
  query = self.session.query(RegistrationEmailOutbox).filter(
      or_(
          RegistrationEmailOutbox.status == "PENDING",
          (
              (RegistrationEmailOutbox.status == "FAILED")
              & (RegistrationEmailOutbox.retry_count < RegistrationEmailOutbox.max_retries)
              & (RegistrationEmailOutbox.next_retry_at <= now)
          ),
          (
              (RegistrationEmailOutbox.status == "PROCESSING")
              & (RegistrationEmailOutbox.processed_at <= lease_cutoff)
              & (RegistrationEmailOutbox.retry_count < RegistrationEmailOutbox.max_retries)
          ),
      )
  ).order_by(RegistrationEmailOutbox.id.asc()).limit(batch_size)
  ```
- **Abandoned Job Poison-Pill Defense:** When an expired lease is reclaimed:
  - `event.retry_count` is immediately incremented.
  - If `event.retry_count >= event.max_retries`, the event is transitioned permanently to `'FAILED'` with `last_error = "Abandoned processing lease expired and exceeded max retries"`, preventing poison-pill messages from crashing workers indefinitely.

#### 2. Concurrent Worker Safety
- Uses PostgreSQL row-level locking via `with_for_update(skip_locked=True)`.
- If Worker A and Worker B run concurrently:
  - Worker A locks and reclaims the expired event.
  - Worker B skips the locked row and proceeds to subsequent items or finishes cleanly.
  - Verified by multithreaded test `test_postgresql_live_outbox_lease_crash_recovery_and_multithread_reclaim` in `tests/test_registration_postgresql_live.py`.

#### 3. At-Least-Once Delivery Guarantee
- Standard email transports (SMTP, external email gateways) lack distributed two-phase commit (2PC) transactions with relational databases.
- If an email provider socket accepts an email but the worker process crashes before database commit, the event's processing lease will expire and a recovery worker will re-dispatch the email.
- **Delivery Guarantee:** Explicitly documented as **At-Least-Once Delivery**.
- **Security Impact:** All activation links and password reset links use cryptographically random single-use tokens stored as SHA-256 digests. Duplicate delivery simply transmits the identical single-use link; once consumed in the database, any replay or subsequent click is safely rejected.

---

### 2.2 F-2: Password Reset Atomicity and Session Revocation

#### 1. Row-Level Locking on Token Consumption
In `src/services/account_provisioning_service.py`:
```python
input_hash = hashlib.sha256(raw_reset_token.strip().encode("utf-8")).hexdigest()
query = self.session.query(PasswordResetToken).filter_by(token_hash=input_hash)
try:
    token_record = query.with_for_update().first()
except Exception:
    token_record = query.first()
```
- In PostgreSQL, `with_for_update()` locks the specific token row for the duration of the transaction.
- When two simultaneous requests attempt to confirm the same token:
  1. Thread 1 acquires the row lock.
  2. Thread 2 blocks on the lock.
  3. Thread 1 verifies `is_consumed == False`, marks `is_consumed = True`, updates `user.password_hash`, updates `user.updated_at`, invalidates active sessions, and commits.
  4. Thread 2 unblocks, re-reads the updated row, observes `token_record.is_consumed == True`, and raises `ActivationTokenError("Password reset token has already been consumed.")`.
- Verified in live PostgreSQL with independent TCP client sessions: `test_postgresql_live_concurrent_password_reset_independent_sessions`.

#### 2. Transaction Atomicity
Inside `confirm_password_reset`, the token consumption, timestamp stamping, password update to PBKDF2-HMAC-SHA256 (100,000 iterations), and session invalidation occur within a single database transaction:
```python
token_record.is_consumed = True
token_record.consumed_at = now
user.password_hash = hash_password(password)
user.is_active = True
user.updated_at = now
self.session.flush()

revoke_user_sessions(user.user_id)
if user.username:
    revoke_user_sessions(user.username)
```

#### 3. Session & JWT Invalidation
- Added `revoke_user_sessions(user_id)` and `is_user_session_revoked(user_id, token_iat)` in `src/auth/rate_limiter.py`.
- Persists user revocation cutoff timestamp in Redis (`sih:jwt:user_revoked:<user_id>`) with thread-safe in-memory fallback.
- Updated `decode_access_token` in `src/auth/jwt_utils.py` and `decode_applicant_token` in `src/auth/registration_auth.py`:
  - When `check_revocation=True`: compares the token's `iat` against the user's latest session revocation cutoff timestamp.
  - Any JWT issued prior to password reset is immediately rejected (`None`).
  - New JWTs issued after password reset succeed normally.
- Verified in `test_password_reset_session_invalidation`.

---

### 2.3 F-3: Migration Compatibility & Clean PostgreSQL 17 Verification

#### 1. Clean Database Execution
- Tested execution of `migrations/003_registration_system.sql` against a completely clean PostgreSQL 17.11 instance (following migrations 001 and 002 with 500 legacy hospitals).
- Returncode: `0` (clean commit).
- Output: `NOTICE: Successfully grandfathered exactly 500 verified legacy hospitals (GH00001-GH00500). COMMIT`.

#### 2. DDL and Constraint Completeness
Verified all elements in PostgreSQL catalog:
- `hospitals`: `approval_status`, `is_grandfathered`, `approved_at`, `application_id`, indexes `idx_hospitals_approval`, `idx_hospitals_application_id`, partial unique index `uq_hospitals_application_id` (`WHERE application_id IS NOT NULL`).
- `users`: `email`, `phone_number`, `designation`, `application_id`, indexes `idx_users_email`, `idx_users_application_id`, partial unique index `uq_users_application_id` (`WHERE application_id IS NOT NULL`).
- `registration_applications`: full schema with lifecycle triggers and partial unique indexes:
  - `uq_reg_app_active_state` on `(LOWER(TRIM(state)))`
  - `uq_reg_app_active_district` on `(LOWER(TRIM(state)), LOWER(TRIM(district)))`
  - `uq_reg_app_active_hospital_email` on `(LOWER(TRIM(applicant_email)))`
- `registration_documents`: file size check, SHA-256 checksum, verification status.
- `approval_history`: `ON DELETE RESTRICT` foreign key, trigger `trg_protect_approval_history` (prohibiting application-level UPDATE and DELETE).
- `verification_tokens`: `application_id` foreign key, index `idx_verification_tokens_app_id`.
- `application_tracking_tokens`: `tracking_token_id`, `token_hash`, `is_revoked`, `access_count`.
- `account_activation_tokens`: `activation_token_id`, `user_id`, `token_hash`, `is_consumed`.
- `registration_email_outbox`: `outbox_id`, `status`, `retry_count`, `max_retries`, queue index `idx_email_outbox_queue`.
- `password_reset_tokens`: `reset_token_id`, `user_id`, `token_hash`, `is_consumed`, indexes.

#### 3. ORM Metadata Alignment
`src/database/pg_models.py` definitions match PostgreSQL tables, column types, foreign keys, relationships, and partial indexes.

#### 4. Persistent Environment Isolation Confirmation
- Catalog inspection of `sih_hospital_dev`:
  ```sql
  SELECT 
      (SELECT COUNT(*) FROM hospitals) as hospital_count,
      (SELECT COUNT(*) FROM users) as user_count,
      (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'registration_%') as registration_table_count;
  ```
  **Result:**
  `hospital_count: 500 | user_count: 8 | registration_table_count: 0`
- Migration 003 has **never been executed** against `sih_hospital_dev` or any persistent environment.
- All testing runs against disposable, ephemeral databases (`sih_hospital_reg_test`).

---

## 3. Files Changed

| File | Changes Made |
|---|---|
| `src/services/email_outbox_service.py` | Added `DEFAULT_LEASE_TIMEOUT_SECONDS`, lease-based crash recovery query in `process_outbox`, poison-pill max-retry protection on abandoned items, `reclaim_expired_leases()` helper, and documented at-least-once delivery semantics. |
| `src/auth/rate_limiter.py` | Added `_IN_MEMORY_USER_REVOCATIONS`, `revoke_user_sessions(user_id)`, and `is_user_session_revoked(user_id, token_iat)` with Redis support and thread-safe fallback; updated `reset_blocklist()`. |
| `src/auth/jwt_utils.py` | Updated `decode_access_token` to check `is_user_session_revoked`. |
| `src/auth/registration_auth.py` | Updated `decode_applicant_token` to check `is_user_session_revoked`. |
| `src/services/account_provisioning_service.py` | Updated `activate_account` and `confirm_password_reset` with `with_for_update()` row locking; added `revoke_user_sessions` call upon password reset. |
| `tests/test_document_storage_and_provisioning.py` | Added `test_email_outbox_crash_recovery_and_lease_expiry` (crash recovery, lease expiry, at-least-once resend, poison pill defense) and `test_password_reset_session_invalidation`. |
| `tests/test_registration_postgresql_live.py` | Added `test_postgresql_live_concurrent_password_reset_independent_sessions` (live PG concurrency with `threading.Barrier(2)` and `with_for_update`) and `test_postgresql_live_outbox_lease_crash_recovery_and_multithread_reclaim` (live PG `FOR UPDATE SKIP LOCKED`). |

---

## 4. Exact Test Commands & Outputs

All test suites were executed using `.venv/bin/pytest`.

### 4.1 Task 1E Comprehensive Suite (Unit & Functional)
**Command:**
```bash
.venv/bin/pytest tests/test_document_storage_and_provisioning.py -v
```
**Output:**
```
tests/test_document_storage_and_provisioning.py::test_multipart_upload_valid_pdf_and_jpeg_and_png PASSED [  4%]
tests/test_document_storage_and_provisioning.py::test_mime_spoofing_rejected PASSED [  9%]
tests/test_document_storage_and_provisioning.py::test_oversized_file_rejected PASSED [ 13%]
tests/test_document_storage_and_provisioning.py::test_malware_scan_failure_detection PASSED [ 18%]
tests/test_document_storage_and_provisioning.py::test_storage_adapter_failure_handled PASSED [ 22%]
tests/test_document_storage_and_provisioning.py::test_document_download_authorization PASSED [ 27%]
tests/test_document_storage_and_provisioning.py::test_document_replacement_and_deletion PASSED [ 31%]
tests/test_document_storage_and_provisioning.py::test_provisioning_state_admin_on_central_approval PASSED [ 36%]
tests/test_document_storage_and_provisioning.py::test_provisioning_district_admin_on_central_approval PASSED [ 40%]
tests/test_document_storage_and_provisioning.py::test_provisioning_hospital_admin_and_hospital_entity PASSED [ 45%]
tests/test_document_storage_and_provisioning.py::test_duplicate_provisioning_idempotency PASSED [ 50%]
tests/test_document_storage_and_provisioning.py::test_self_approval_and_pre_approval_provisioning_blocked PASSED [ 54%]
tests/test_document_storage_and_provisioning.py::test_account_activation_flow_and_password_complexity PASSED [ 59%]
tests/test_document_storage_and_provisioning.py::test_expired_activation_token_and_resend PASSED [ 63%]
tests/test_document_storage_and_provisioning.py::test_email_delivery_failure_does_not_abort_database_approval PASSED [ 68%]
tests/test_document_storage_and_provisioning.py::test_malware_scanner_fail_closed_unavailable_and_timeout PASSED [ 72%]
tests/test_document_storage_and_provisioning.py::test_transactional_email_outbox_retry_and_duplicate_worker PASSED [ 77%]
tests/test_document_storage_and_provisioning.py::test_password_recovery_full_lifecycle_and_security PASSED [ 81%]
tests/test_document_storage_and_provisioning.py::test_provisioning_concurrency_multithreaded PASSED [ 86%]
tests/test_document_storage_and_provisioning.py::test_otp_application_binding PASSED [ 90%]
tests/test_document_storage_and_provisioning.py::test_email_outbox_crash_recovery_and_lease_expiry PASSED [ 95%]
tests/test_document_storage_and_provisioning.py::test_password_reset_session_invalidation PASSED [100%]
======================== 22 passed, 7 warnings in 2.82s ========================
```

### 4.2 Live PostgreSQL Test Suite
**Command:**
```bash
.venv/bin/pytest tests/test_registration_postgresql_live.py -v
```
**Output:**
```
tests/test_registration_postgresql_live.py::test_postgresql_status_default_and_draft_timestamps PASSED [  3%]
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_orm PASSED [  7%]
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_raw_sql PASSED [ 11%]
tests/test_registration_postgresql_live.py::test_postgresql_indexes_deep_catalog_and_orm_verification PASSED [ 14%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_update PASSED [ 18%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_delete PASSED [ 22%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_blocks_application_delete_via_restrict PASSED [ 25%]
tests/test_registration_postgresql_live.py::test_postgresql_tracking_token_reusable_and_revocable PASSED [ 29%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_1_fresh_500_hospitals PASSED [ 33%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_2_successful_rerun PASSED [ 37%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_3_gh00501_inserted_before_rerun PASSED [ 40%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_4_partial_grandfathered_state_aborts PASSED [ 44%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_5_unexpected_grandfathered_hospital_aborts PASSED [ 48%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_6_missing_legacy_hospital_aborts PASSED [ 51%]
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_full_workflow PASSED [ 55%]
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_correction_and_resubmit PASSED [ 59%]
tests/test_registration_postgresql_live.py::test_postgresql_concurrent_duplicate_prevention_threads PASSED [ 62%]
tests/test_registration_postgresql_live.py::test_postgresql_concurrent_duplicate_prevention_district_threads PASSED [ 66%]
tests/test_registration_postgresql_live.py::test_postgresql_rejected_application_allows_new_active_application PASSED [ 70%]
tests/test_registration_postgresql_live.py::test_postgresql_case_and_whitespace_index_enforcement_raw_sql PASSED [ 74%]
tests/test_registration_postgresql_live.py::test_postgresql_unexpected_integrity_violation_preserves_exception PASSED [ 77%]
tests/test_registration_postgresql_live.py::test_postgresql_hospital_email_identity_policy_scenarios PASSED [ 81%]
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_api_workflow PASSED [ 85%]
tests/test_registration_postgresql_live.py::test_postgresql_live_outbox_and_row_locking PASSED [ 88%]
tests/test_registration_postgresql_live.py::test_postgresql_live_concurrent_provisioning_threads PASSED [ 92%]
tests/test_registration_postgresql_live.py::test_postgresql_live_concurrent_password_reset_independent_sessions PASSED [ 96%]
tests/test_registration_postgresql_live.py::test_postgresql_live_outbox_lease_crash_recovery_and_multithread_reclaim PASSED [100%]
======================== 27 passed, 1 warning in 3.70s =========================
```

### 4.3 All Registration Test Suites (Combined)
**Command:**
```bash
.venv/bin/pytest \
  tests/test_document_storage_and_provisioning.py \
  tests/test_registration_api.py \
  tests/test_registration_service.py \
  tests/test_registration_models.py \
  tests/test_registration_postgresql_live.py \
  -v
```
**Output:** **114 passed in 6.26s** (0 failed, 0 skipped).

### 4.4 Core Regression Test Suites
**Command:**
```bash
.venv/bin/pytest \
  tests/test_live_postgresql_integration.py \
  tests/test_postgresql_migration_and_transactions.py \
  tests/test_end_to_end_referral_workflow.py \
  tests/test_auth_and_access.py \
  -v
```
**Output:** **41 passed in 5.45s** (0 failed, 0 skipped).

### Total Combined Test Result
**155 passed, 0 failed, 0 skipped.**

---

## 5. Remaining Limitations

1. **SMTP Transport Idempotency:** SMTP protocol itself does not support distributed two-phase commit transactions. If an application process crashes after the SMTP server accepts an email but before database commit, a duplicate email will be dispatched upon lease recovery. This at-least-once delivery behavior is safe because activation and password reset tokens are single-use tokens; duplicate receipt of an identical token link cannot be reused or replayed once consumed.
2. **Cron/Daemon Polling:** While `process_outbox` handles crash recovery and lease expiration automatically when called, production environments require an external scheduler (systemd timer, Kubernetes CronJob, or Celery beat) to trigger worker execution periodically.

---

## 6. Git Status and Stash Confirmation

### Git Status
```
On branch master
Your branch is up to date with 'new-origin/master'.

Changes to be committed:
	new file:   PHASE_1_TASK_1A_1B_CORRECTION_REPORT.md
	new file:   PHASE_1_TASK_1A_1B_REPORT.md
	new file:   migrations/003_registration_system.sql
	modified:   src/database/pg_models.py
	new file:   tests/test_registration_models.py
	new file:   tests/test_registration_postgresql_live.py

Changes not staged for commit:
	modified:   migrations/003_registration_system.sql
	modified:   src/api/main.py
	modified:   src/auth/auth_store.py
	modified:   src/auth/jwt_utils.py
	modified:   src/auth/rate_limiter.py
	modified:   src/database/db_manager.py
	modified:   src/database/pg_models.py
	modified:   tests/test_registration_postgresql_live.py

Untracked files:
	PHASE_1_TASK_1C_DUPLICATE_PREVENTION_FIX_REPORT.md
	PHASE_1_TASK_1C_FINAL_VERIFICATION_REPORT.md
	PHASE_1_TASK_1C_REPORT.md
	PHASE_1_TASK_1C_SECURITY_AUDIT.md
	PHASE_1_TASK_1D_FINAL_VERIFICATION_REPORT.md
	PHASE_1_TASK_1D_REMEDIATION_REPORT.md
	PHASE_1_TASK_1D_REPORT.md
	PHASE_1_TASK_1D_SECURITY_AUDIT.md
	PHASE_1_TASK_1E_FINAL_AUDIT_REPORT.md
	PHASE_1_TASK_1E_REMEDIATION_REPORT.md
	PHASE_1_TASK_1E_REPORT.md
	src/api/registration_routes.py
	src/api/registration_schemas.py
	src/auth/registration_auth.py
	src/database/registration_service.py
	src/services/
	tests/test_document_storage_and_provisioning.py
	tests/test_registration_api.py
	tests/test_registration_service.py
```

### Git Stash
```
stash@{0}: On master: Backup before GitHub repository synchronization
```
- `stash@{0}` is preserved and intact.
- No `git commit` or `git push` has occurred. `HEAD` remains at commit `460af41`.

---

## 7. Database Isolation Confirmation

Catalog check against `sih_hospital_dev`:
```sql
SELECT 
    (SELECT COUNT(*) FROM hospitals) as hospital_count,
    (SELECT COUNT(*) FROM users) as user_count,
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'registration_%') as registration_table_count;
```
**Output:**
```
 hospital_count | user_count | registration_table_count 
----------------+------------+--------------------------
            500 |          8 |                        0
(1 row)
```

- Development database `sih_hospital_dev` has **never been migrated** with migration 003.
- All 500 baseline hospitals and 8 baseline users are completely intact.
- Task 1F has not been started. Awaiting user review.
