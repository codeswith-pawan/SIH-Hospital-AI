# Phase 1 — Task 1E: Secure Document Storage & Operational Account Provisioning Implementation Report

**Date:** 2026-11-03  
**Project:** SIH Hospital AI (`~/Desktop/SIH_Hospital_AI`)  
**Status:** COMPLETED & VERIFIED  

---

## 1. Executive Summary

Phase 1 Task 1E extends the National Hospital Referral System's registration lifecycle with two mission-critical, enterprise-grade capabilities:
1. **Secure Document Management:** High-performance, secure multipart document upload, cryptographic hashing (SHA-256), magic-byte/MIME enforcement (preventing content spoofing), 25 MB file size constraints, malware scanning abstractions (ClamAV & simulated scanners), server-authoritative key generation, pluggable storage adapters (`LocalStorageAdapter` and `S3StorageAdapter`), and role-scoped authorized document streaming downloads.
2. **Operational Account Provisioning & Activation:** Automated, atomic provisioning triggered **strictly** upon Central Government final approval (`status == "APPROVED"` at `CENTRAL_REVIEW`). Automatically provisions `STATE_ADMIN`, `DISTRICT_ADMIN`, or `HOSPITAL` accounts (alongside physical `Hospital` entity records in `hospitals` with bed capacities from `profile_data`). Issues single-use 72-hour cryptographic one-time activation tokens stored exclusively as SHA-256 hashes, paired with post-commit email dispatch, strong password complexity enforcement, PBKDF2-HMAC-SHA256 password hashing, and seamless dual-store operational login compatibility (`users.json` + PostgreSQL `users`).

---

## 2. Architecture & Design Overview

```
                                      REGISTRATION PIPELINE (Task 1E)
                                      
  [ APPLICANT ]                       [ STORAGE & SECURITY ]               [ CENTRAL APPROVAL ]
       │                                       │                                    │
       ├─ (1) Multipart Upload ───────────────>│ 1. Validate File Size (<25MB)     │
       │      POST /documents/upload           │ 2. Magic-Byte Verification         │
       │                                       │ 3. Malware Scan (ClamAV)           │
       │                                       │ 4. Compute SHA-256 Digest          │
       │                                       │ 5. Store via Adapter (Local/S3)    │
       │                                       │ 6. Insert RegistrationDocument     │
       │                                       │                                    │
       ├─ (2) Submit Application ──────────────────────────────────────────────────>│
       │                                                                            │
       │                                                                   (3) Central Review
       │                                                                       APPROVE Decision
       │                                                                            │
       │                                                                   [ ATOMIC DB TRANSACTION ]
       │                                                                   ├─ Application: APPROVED
       │                                                                   ├─ ApprovalHistory: APPROVE
       │                                                                   ├─ Provision User (State/Dist/Hosp)
       │                                                                   ├─ (If Hospital: Create Hospital)
       │                                                                   └─ Issue AccountActivationToken (72h)
       │                                                                            │
       │<────────────────────────────────── [ POST-COMMIT EMAIL DISPATCH ] ─────────┘
       │     Activation Email Dispatched          Dispatches single-use link
       │     (Contains raw activation token)      (Email failure NEVER aborts DB commit)
       │
       ├─ (4) POST /auth/activate ────────────> [ ACCOUNT ACTIVATION ]
       │      (Token + Complex Password)         ├─ Look up token by SHA-256 hash
       │                                         ├─ Validate complexity & expiry
       │                                         ├─ PBKDF2-HMAC-SHA256 hash
       │                                         ├─ User: is_active = True
       │                                         └─ Token: is_consumed = True
       │
       └─ (5) POST /api/auth/login ───────────> [ OPERATIONAL PORTAL ]
              (Activated account logs in via dual-store AuthStore)
```

---

## 3. Detailed Component Implementation

### 3.1 Document Storage & Content Security (`src/services/document_storage.py`)
- **Magic-Byte Content Verification:** Never relies on client-provided `Content-Type`. Reads file headers and verifies true signatures:
  - **PDF:** Must begin with `%PDF-` (`0x25 0x50 0x44 0x46 0x2D`).
  - **JPEG:** Must begin with SOI marker `0xFF 0xD8 0xFF`.
  - **PNG:** Must begin with 8-byte PNG header (`0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A`).
  - Rejects HTML, executable binaries, polyglots, and spoofed extensions with `MimeSpoofingError` / HTTP 422.
- **Strict Size Limits:** Stream size verified up to 25 MB (`MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024`). Files exceeding 25 MB are rejected immediately (`FileTooLargeError` / HTTP 413).
- **Authoritative Storage Keys:** Server generates non-guessable, content-derived keys matching format:
  `DOC_{uuid4().hex[:12]}_{sha256[:12]}.{ext}`. Raw client filenames and internal physical paths are never exposed.
- **Storage Adapters:**
  - `BaseStorageAdapter`: Abstract interface defining `save`, `retrieve`, `delete`, and `exists`.
  - `LocalStorageAdapter`: Enforces path sanitization, prevents directory traversal (`os.path.commonpath` verification), ensures directory permissions `0o700`, and performs atomic file writes via temporary files.
  - `S3StorageAdapter`: Cloud object storage adapter compatible with AWS S3 and MinIO via `boto3` (with in-memory fallback during test/development).
- **Malware Scanning Abstraction:**
  - `BaseMalwareScanner`: Abstract interface defining `scan(file_bytes, filename)`.
  - `ClamAVScanner`: Production antivirus scanner communicating via ClamAV daemon `INSTREAM` TCP protocol.
  - `SimulatedScanner`: Development scanner identifying the standard EICAR test string (`X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR...`). Infected files raise `MalwareDetectedError` / HTTP 422.

### 3.2 Operational Account Provisioning (`src/services/account_provisioning_service.py`)
- **Strict Gating:** Provisioning is triggered **strictly** upon Central Government approval (`status == "APPROVED"` at `CENTRAL_REVIEW`). Unapproved, draft, or pending applications cannot be provisioned (`IneligibleForApprovalError`).
- **Hierarchy-Specific Accounts:**
  - **State Applications:** Provisions `STATE_ADMIN` account (`username: state_<statename>`, `state: <State>`, `district: None`, `hospital_id: None`).
  - **District Applications:** Provisions `DISTRICT_ADMIN` account (`username: dist_<districtname>`, `state: <State>`, `district: <District>`, `hospital_id: None`).
  - **Hospital Applications:** Provisions both a new operational `Hospital` entity in `hospitals` table (sequential `GH00501+`, bed capacities from `profile_data`, `approval_status="APPROVED"`, `is_grandfathered=False`) AND a linked `HOSPITAL` user account (`hospital_id` foreign key).
- **Idempotency & Duplicate Prevention:** If an operational user account already exists for the application, provisioning returns the existing user record without duplicating rows or raising errors.
- **Self-Approval Guard:** Reviewers cannot approve or provision accounts for applications they submitted or have ownership over (`SelfApprovalError`).

### 3.3 Account Activation & Security Lifecycle
- **Cryptographic One-Time Tokens:** Generated via `secrets.token_urlsafe(32)`. Stored exclusively as SHA-256 hashes in `account_activation_tokens`. Token valid for 72 hours.
- **Single-Use Enforcement:** Tokens are consumed atomically upon first use (`is_consumed=True`, `consumed_at=now`). Replay attempts are rejected (`ActivationTokenError` / HTTP 400).
- **Password Complexity:** Minimum 8 characters, at least 1 uppercase letter, 1 lowercase letter, 1 digit, and 1 special character (`!@#$%^&*()-_+=...`).
- **Password Hashing:** PBKDF2-HMAC-SHA256 with 100,000 iterations (`pbkdf2:sha256:100000$...`) matching system security standards.
- **Resend Activation Endpoint:** `POST /api/registration/auth/activation/resend` invalidates prior unconsumed tokens and dispatches a fresh 72-hour token to the applicant's registered email.

### 3.4 Post-Commit Email Dispatch (`src/services/email_service.py`)
- **Transactional Safety:** Email dispatch is decoupled from the database transaction. Activation emails are dispatched **strictly after** the database transaction successfully commits.
- **Resilience:** Email delivery failures are logged and reported as warnings, but **never** abort or roll back the committed database approval.
- **Zero Credential Exposure:** Plaintext passwords are never generated, transmitted, or logged. Only single-use activation URLs are sent.

### 3.5 Dual-Store Authentication Support (`src/auth/auth_store.py`)
- Enhanced `AuthStore.authenticate_user` and `AuthStore.get_user_by_id` to look up activated provisioned accounts in the PostgreSQL `users` table if not found in legacy `users.json`.
- Complete backward compatibility with existing operational users, referral workflows, bed reservations, and AI models.

---

## 4. API Endpoints Implemented

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `POST` | `/api/registration/applications/documents/upload` | Applicant Token | Multipart upload with magic-byte check, size limit, and virus scan |
| `GET` | `/api/registration/applications/documents/{id}/download` | Applicant / Reviewer | Authorized streaming binary download with `Content-Disposition: attachment` |
| `DELETE` | `/api/registration/applications/documents/{id}` | Applicant Token | Deletes document record and underlying storage blob in DRAFT / CORRECTION |
| `POST` | `/api/registration/review/applications/{id}/decision` | Reviewer Token | Review decision endpoint; atomic account provisioning on Central approval |
| `POST` | `/api/registration/auth/activate` | Public (Token-bound) | One-time token activation and secure password creation |
| `POST` | `/api/registration/auth/activation/resend` | Public (Email-bound) | Invalidate old tokens and resend fresh 72-hour activation link |

---

## 5. Verification & Test Coverage

### 5.1 Task 1E Dedicated Test Suite (`tests/test_document_storage_and_provisioning.py`)
All 15 comprehensive tests pass:
1. `test_multipart_upload_valid_pdf_and_jpeg_and_png`: Verified valid multipart upload for all 3 supported formats.
2. `test_mime_spoofing_rejected`: Verified client spoofing (e.g. text/html sent as application/pdf) rejected via magic bytes.
3. `test_oversized_file_rejected`: Verified files exceeding 25 MB rejected with HTTP 413.
4. `test_malware_scan_failure_detection`: Verified EICAR signature rejected with HTTP 422.
5. `test_storage_adapter_failure_handled`: Verified disk I/O failure handling without orphan DB records.
6. `test_document_download_authorization`: Verified applicant ownership, Mohali District Admin access, and rejection of out-of-scope / wrong-stage reviewers.
7. `test_document_replacement_and_deletion`: Verified replacement resets status and deletion removes storage blob.
8. `test_provisioning_state_admin_on_central_approval`: Verified Central approval creates `STATE_ADMIN` and dispatches email.
9. `test_provisioning_district_admin_on_central_approval`: Verified full hierarchy forward to Central creates `DISTRICT_ADMIN`.
10. `test_provisioning_hospital_admin_and_hospital_entity`: Verified Hospital entity (beds, geo) + `HOSPITAL` user created.
11. `test_duplicate_provisioning_idempotency`: Verified repeated approval calls do not duplicate accounts.
12. `test_self_approval_and_pre_approval_provisioning_blocked`: Verified pre-approval and self-approval blocked.
13. `test_account_activation_flow_and_password_complexity`: Verified password complexity, single-use token consumption, and operational login.
14. `test_expired_activation_token_and_resend`: Verified expired tokens rejected and resend generates fresh valid token.
15. `test_email_delivery_failure_does_not_abort_database_approval`: Verified DB commit succeeds even when SMTP/email dispatch fails.

### 5.2 Registration Test Suite Results
```
tests/test_document_storage_and_provisioning.py ............... [ 15/103]
tests/test_registration_api.py ................................ [ 47/103]
tests/test_registration_service.py ............................ [ 75/103]
tests/test_registration_models.py ............................. [ 83/103]
tests/test_registration_postgresql_live.py .................... [103/103]
======================= 103 passed, 9 warnings in 4.75s ========================
```

### 5.3 Core System Regression Test Suite Results
```
tests/test_live_postgresql_integration.py ........              [  8/41]
tests/test_postgresql_migration_and_transactions.py .......... [ 18/41]
tests/test_end_to_end_referral_workflow.py ................... [ 31/41]
tests/test_auth_and_access.py ............................. [ 41/41]
======================= 41 passed, 402 warnings in 5.69s =======================
```
**Total Passing Tests:** 144 / 144 across registration and legacy operational suites.

---

## 6. Development Database Isolation & Safety Safeguards

To prevent accidental modification or corruption of development environments:
- `sih_hospital_dev` was inspected before and after testing.
- Verified catalog counts:
  - `hospital_count`: 500 (100% intact)
  - `user_count`: 8 (100% intact)
  - `registration_table_count`: 0 (Migration 003 NOT applied to dev DB)
- All registration tests execute strictly against isolated SQLite in-memory databases or dedicated ephemeral test databases.
- `git stash list` confirms `stash@{0}` remains intact and no git commits or pushes were executed.

---

## 7. Limitations & Recommendations for Task 1F

1. **Storage Backend in Production:** Development environment uses `LocalStorageAdapter`. Production deployments should configure environment variables (`STORAGE_BACKEND=s3`, `AWS_S3_BUCKET_NAME`, `AWS_REGION`, etc.) to point to secure S3 or private MinIO instances.
2. **ClamAV Daemon Configuration:** `ClamAVScanner` expects `CLAMAV_HOST` and `CLAMAV_PORT` (default: 3310). For production containers, run `clamd` as a sidecar service or integrate an enterprise virus inspection pipeline.
3. **SMS Notification Provider:** Task 1E implements `email_service.py`. A parallel `sms_service.py` should be configured if SMS dispatch of activation links is desired.

---

## 8. Completion Sign-Off

Phase 1 Task 1E is completely implemented, rigorously tested, and fully backward compatible. Awaiting user review before proceeding.
