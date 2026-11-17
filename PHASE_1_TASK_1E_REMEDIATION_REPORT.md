# Phase 1 — Task 1E: Security Remediation & Final Verification Report

**Date:** 2026-11-03  
**Project:** SIH Hospital Referral System (`~/Desktop/SIH_Hospital_AI`)  
**Status:** ALL REMEDIATIONS COMPLETE & VERIFIED  

---

## 1. Audit Findings & Remediations

Prior to final approval of Phase 1 Task 1E, an independent deep-dive audit identified 6 core vulnerabilities and reliability gaps across document handling, provisioning concurrency, email durability, and authentication binding. All 6 findings have been remediated, verified, and backed by automated regression tests.

| Finding ID | Severity | Area | Issue Description | Remediation Applied |
|---|---|---|---|---|
| **F-1** | **HIGH** | Transactional Outbox | Direct post-commit email dispatch lacks persistence; process crash between commit and dispatch loses activation links; transient SMTP errors drop emails permanently without retries. | Implemented durable `registration_email_outbox` table inside the provisioning transaction. Added worker with exponential backoff, state transitions (`PENDING`, `PROCESSING`, `SENT`, `FAILED`), and duplicate-worker race protection. |
| **F-2** | **HIGH** | Password Recovery | Missing password recovery workflow for provisioned operational accounts. | Implemented secure forgot-password lifecycle: anti-enumeration public responses, 1-hour single-use tokens stored as SHA-256 hashes, constant-time comparison, password complexity enforcement, PBKDF2-HMAC-SHA256 hashing, and replay protection. |
| **F-3** | **HIGH** | Provisioning Concurrency | Concurrent provisioning requests for the same approved application relied on application-level checks without database-level uniqueness constraints on `application_id`. | Added PostgreSQL partial unique indexes `uq_users_application_id` and `uq_hospitals_application_id` (`WHERE application_id IS NOT NULL`). Added row-level locking (`FOR UPDATE`) and nested savepoint recovery returning existing records cleanly. |
| **F-4** | **HIGH** | Scanner Fail-Closed | ClamAV socket errors, connection timeouts, or unexpected responses silently logged warnings and fell back to clean status (fail-open). | Hardened `ClamAVScanner` and `SimulatedScanner` to strictly fail-closed: daemon connection failure / timeout raises `MalwareScanServiceUnavailableError` (HTTP 503) and scanner errors raise `MalwareScanError` (HTTP 502/500). Uploads are rejected immediately. |
| **F-5** | **MEDIUM** | Stale Document Access | Re-uploading a document of the same type updated the existing row in place, allowing stale identifiers to retrieve replaced versions. | Document replacement now invalidates previous identifiers by assigning a fresh `document_id` and purging the previous database row and storage blob. Stale identifiers return HTTP 400 (not found). |
| **F-6** | **HIGH** | OTP Application Binding | `VerificationToken` lacked explicit application binding; an applicant with multiple applications could use an OTP generated for Application A to authorize Application B. | Added `application_id` foreign key and index to `verification_tokens`. `request_otp` binds application identity, and `verify_otp` strictly rejects attempts to authorize mismatched applications. |

---

## 2. Architecture & Detailed Implementation

### 2.1 Transactional Email Outbox (`src/services/email_outbox_service.py`)
- **Schema Persistence:** Created `registration_email_outbox` table in `migrations/003_registration_system.sql` and `src/database/pg_models.py`.
- **Atomic Enqueue:** When `provision_account`, `resend_activation_token`, or `request_password_reset` executes, the email event is inserted within the **exact same database transaction** with status `'PENDING'`.
- **Worker Execution & Concurrency Protection:**
  - Queries events where `status = 'PENDING'` OR (`status = 'FAILED'` AND `retry_count < max_retries` AND `next_retry_at <= now()`).
  - Employs PostgreSQL row-level locking via `with_for_update(skip_locked=True)` so concurrent background workers never process or dispatch the same outbox item twice.
  - Transitions to `'PROCESSING'`, executes dispatch via `email_provider`, and marks `'SENT'` on success with timestamp.
  - On transient failure: records truncated error message, increments `retry_count`, and calculates exponential backoff (`30s * 2^(retry-1)`).
- **Log Privacy:** Raw activation tokens and passwords are never logged; recipient emails are masked (e.g. `d***@punjab.gov.in`).

### 2.2 Password Recovery & Anti-Enumeration
- **Public Request Endpoint (`POST /api/registration/auth/password-reset/request`):**
  - Rate limited per IP address (5 attempts per 5 minutes).
  - Queries active operational users by registered email.
  - If user exists: invalidates old unconsumed tokens, generates cryptographic urlsafe 32-byte token, persists SHA-256 hash in `password_reset_tokens` (1-hour expiry), and enqueues transactional outbox email.
  - If user does not exist: executes dummy PBKDF2 hash verification (`DUMMY_PBKDF2_HASH`) to ensure constant execution timing.
  - Uniform public response: `"If an active account exists for this email address, a password reset link has been dispatched."` Eliminates account enumeration.
- **Confirmation Endpoint (`POST /api/registration/auth/password-reset/confirm`):**
  - Validates password complexity (≥8 chars, uppercase, lowercase, digit, special symbol).
  - Hashes input token with SHA-256 and executes constant-time digest comparison (`hmac.compare_digest`).
  - Verifies token is not expired and not consumed.
  - Atomically consumes token (`is_consumed=True`, `consumed_at=now`) and updates password to PBKDF2-HMAC-SHA256 (100,000 iterations). Replay attempts are rejected with HTTP 400.

### 2.3 Provisioning Concurrency & Idempotency Safeguards
- **Database Level Protection:**
  ```sql
  CREATE UNIQUE INDEX IF NOT EXISTS uq_users_application_id ON users (application_id) WHERE application_id IS NOT NULL;
  CREATE UNIQUE INDEX IF NOT EXISTS uq_hospitals_application_id ON hospitals (application_id) WHERE application_id IS NOT NULL;
  ```
- **Service Layer Handling (`AccountProvisioningService.provision_account`):**
  - Queries application with row lock (`with_for_update()`).
  - If operational account already exists for this application, returns existing account idempotently without raising errors or creating duplicates.
  - Wraps creation in collision-safe recovery: if a concurrent transaction commits first, the second transaction catches `IntegrityError`, queries `existing_user`, and returns the provisioned record cleanly.

### 2.4 Fail-Closed Antivirus Scanning (`src/services/document_storage.py`)
- Hardened `ClamAVScanner.scan_bytes`:
  - Socket timeout / connection refused raises `MalwareScanServiceUnavailableError` (mapped to HTTP 503 Service Unavailable).
  - Unexpected or daemon error responses raise `MalwareScanError` (mapped to HTTP 502 Bad Gateway).
  - Malware detections raise `MalwareDetectedError` (mapped to HTTP 422).
  - Only clean files (`OK` response) proceed to storage.
- Added testing simulation hooks to `SimulatedScanner` (`simulate_unavailable`, `simulate_timeout`, `simulate_error`).

### 2.5 Document Access Authorization & Stale Identifier Invalidation
- **Applicant Scoping:** `get_document_for_download` strictly enforces `applicant_app_id == app.application_id`. Applicants cannot access documents from other applications even if sharing the same contact email.
- **Reviewer Jurisdiction:** Scoped strictly by role, current review stage, and geographic jurisdiction. Unrelated roles (e.g. `HOSPITAL`) receive HTTP 403 Forbidden.
- **Stale Identifier Elimination:** When replacing a document via multipart upload, the old `RegistrationDocument` record and physical storage blob are deleted, and a new record with a new `document_id` is created. Any request referencing the old `document_id` fails with HTTP 400 (document not found).

### 2.6 OTP Application Identity Binding (`src/services/otp_service.py`)
- Added `application_id` column and index to `verification_tokens`.
- `request_otp` resolves and binds `application_id` when `application_number` is provided.
- `verify_otp` compares `expected_application_id` with `vtoken.application_id`. Attempting to use an OTP requested for Application 1 to authorize Application 2 raises `ValidationError("Verification token is bound to a different application.")`.

---

## 3. Files Changed

1. `migrations/003_registration_system.sql`:
   - Added `uq_users_application_id` and `uq_hospitals_application_id` partial unique indexes.
   - Added `application_id` column and index `idx_verification_tokens_app_id` on `verification_tokens`.
   - Added `registration_email_outbox` table and index `idx_email_outbox_queue`.
   - Added `password_reset_tokens` table and indexes.
2. `src/database/pg_models.py`:
   - Added `RegistrationEmailOutbox` and `PasswordResetToken` SQLAlchemy models.
   - Updated `User` and `Hospital` models with partial unique indexes on `application_id`.
   - Updated `VerificationToken` with `application_id` and relationship to `RegistrationApplication`.
3. `src/services/email_outbox_service.py`:
   - New transactional outbox service managing atomic event enqueue, worker processing, row-locking with `SKIP LOCKED`, exponential backoff, and log sanitization.
4. `src/services/email_service.py`:
   - Added `send_email` method to `BaseEmailProvider`, `SimulatedEmailProvider`, and `SMTPEmailProvider`.
5. `src/services/document_storage.py`:
   - Added `MalwareScanServiceUnavailableError` and `MalwareScanError`.
   - Hardened `ClamAVScanner` and `SimulatedScanner` to strictly fail-closed.
6. `src/services/account_provisioning_service.py`:
   - Integrated `provision_account` with transactional outbox enqueue.
   - Added concurrency collision handling and savepoint rollback recovery.
   - Implemented `request_password_reset` with anti-enumeration and `confirm_password_reset` with PBKDF2 hashing.
7. `src/services/registration_service.py`:
   - Updated `upload_document_binary` to assign fresh `document_id` on replacement and purge stale blobs/rows.
   - Hardened `get_document_for_download` authorization.
8. `src/services/otp_service.py`:
   - Added application binding to `request_otp` and `verify_otp`.
9. `src/api/registration_schemas.py`:
   - Added `PasswordResetRequest`, `PasswordResetResponse`, `PasswordResetConfirmRequest`, `PasswordResetConfirmResponse`, and `OutboxProcessResponse`.
10. `src/api/registration_routes.py`:
    - Updated `_map_exception` for fail-closed scanner exceptions (HTTP 503 / 502).
    - Updated OTP routes to enforce application binding.
    - Added `/auth/password-reset/request`, `/auth/password-reset/confirm`, and `/outbox/process` endpoints.
11. `tests/test_document_storage_and_provisioning.py`:
    - Added comprehensive tests for fail-closed scanner, transactional outbox retries, duplicate workers, password recovery, multithreaded concurrency, and OTP application binding (20 total tests).
12. `tests/test_registration_postgresql_live.py`:
    - Added live PostgreSQL tests for transactional outbox queue processing with `FOR UPDATE SKIP LOCKED`, multithreaded concurrent provisioning with `threading.Barrier(2)`, and database constraints (25 total tests).

---

## 4. Required Test Evidence & Results

All tests were executed using the project's virtual environment Python (`.venv/bin/pytest`).

### 4.1 Task 1E Comprehensive Remediation Test Suite
**Command:** `.venv/bin/pytest tests/test_document_storage_and_provisioning.py -v`  
**Result:** **20 passed in 1.70s**

```
tests/test_document_storage_and_provisioning.py::test_multipart_upload_valid_pdf_and_jpeg_and_png PASSED [  5%]
tests/test_document_storage_and_provisioning.py::test_mime_spoofing_rejected PASSED [ 10%]
tests/test_document_storage_and_provisioning.py::test_oversized_file_rejected PASSED [ 15%]
tests/test_document_storage_and_provisioning.py::test_malware_scan_failure_detection PASSED [ 20%]
tests/test_document_storage_and_provisioning.py::test_storage_adapter_failure_handled PASSED [ 25%]
tests/test_document_storage_and_provisioning.py::test_document_download_authorization PASSED [ 30%]
tests/test_document_storage_and_provisioning.py::test_document_replacement_and_deletion PASSED [ 35%]
tests/test_document_storage_and_provisioning.py::test_provisioning_state_admin_on_central_approval PASSED [ 40%]
tests/test_document_storage_and_provisioning.py::test_provisioning_district_admin_on_central_approval PASSED [ 45%]
tests/test_document_storage_and_provisioning.py::test_provisioning_hospital_admin_and_hospital_entity PASSED [ 50%]
tests/test_document_storage_and_provisioning.py::test_duplicate_provisioning_idempotency PASSED [ 55%]
tests/test_document_storage_and_provisioning.py::test_self_approval_and_pre_approval_provisioning_blocked PASSED [ 60%]
tests/test_document_storage_and_provisioning.py::test_account_activation_flow_and_password_complexity PASSED [ 65%]
tests/test_document_storage_and_provisioning.py::test_expired_activation_token_and_resend PASSED [ 70%]
tests/test_document_storage_and_provisioning.py::test_email_delivery_failure_does_not_abort_database_approval PASSED [ 75%]
tests/test_document_storage_and_provisioning.py::test_malware_scanner_fail_closed_unavailable_and_timeout PASSED [ 80%]
tests/test_document_storage_and_provisioning.py::test_transactional_email_outbox_retry_and_duplicate_worker PASSED [ 85%]
tests/test_document_storage_and_provisioning.py::test_password_recovery_full_lifecycle_and_security PASSED [ 90%]
tests/test_document_storage_and_provisioning.py::test_provisioning_concurrency_multithreaded PASSED [ 95%]
tests/test_document_storage_and_provisioning.py::test_otp_application_binding PASSED [100%]
======================== 20 passed in 1.70s ========================
```

### 4.2 All Registration Test Suites (Combined)
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
**Result:** **110 passed in 5.02s** (0 failed, 0 skipped)

### 4.3 Core Legacy Regression Test Suites
**Command:**
```bash
.venv/bin/pytest \
  tests/test_live_postgresql_integration.py \
  tests/test_postgresql_migration_and_transactions.py \
  tests/test_end_to_end_referral_workflow.py \
  tests/test_auth_and_access.py \
  -v
```
**Result:** **41 passed in 5.75s** (0 failed, 0 skipped)

### 4.4 PostgreSQL Live Tests Isolation
- All PostgreSQL live tests execute strictly against the dedicated ephemeral `sih_hospital_reg_test` database (auto-created and dropped per run).
- Migration 003 was **NOT** executed against the development database `sih_hospital_dev`.
- Catalog inspection of `sih_hospital_dev`:
  ```sql
  SELECT 
      (SELECT COUNT(*) FROM hospitals) as hospital_count,
      (SELECT COUNT(*) FROM users) as user_count,
      (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'registration_%') as registration_table_count;
  ```
  **Output:**
  `hospital_count: 500 | user_count: 8 | registration_table_count: 0` (100% intact).

### 4.5 Git Integrity
- No commits or pushes have occurred.
- `git stash list` confirms `stash@{0}: On master: Backup before GitHub repository synchronization` remains untouched.

---

## 5. Remaining Limitations

1. **Outbox Worker Deployment:** In production, the outbox worker (`process_outbox`) should be executed periodically via a background daemon (e.g., Celery, systemd timer, or scheduled Cron) to poll and dispatch pending emails with low latency.
2. **ClamAV Network Connectivity:** Production deployments should ensure the ClamAV daemon is reachable via private VPC networking or a container sidecar. Because scanning is fail-closed, any network disruption will purposefully block uploads until connectivity is restored.

---

## 6. Explicit Confirmations

1. **No git commit or git push** was performed during this remediation.
2. The existing stash `stash@{0}` remains intact and preserved.
3. Development database `sih_hospital_dev` was **never migrated** and preserves all 500 hospitals and 8 users.
4. Operational accounts are **never provisioned before final Central approval**.
5. Plaintext passwords are **never transmitted, logged, or stored**.
6. Task 1F has **not** been started. Execution is paused awaiting user review.
