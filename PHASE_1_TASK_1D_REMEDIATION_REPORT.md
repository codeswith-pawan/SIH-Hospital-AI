# PHASE 1 — TASK 1D SECURITY REMEDIATION REPORT

**Project:** SIH Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** Phase 1 — Task 1D Security Remediation  
**Date:** 2026-11-03  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

This report documents the implementation and verification of all five remediation items identified during the independent security audit of Task 1D (`PHASE_1_TASK_1D_SECURITY_AUDIT.md`):
- **F-1 (High):** Elimination of unauthenticated status probing and application enumeration by enforcing mandatory, cryptographically hashed tracking tokens with uniform error responses.
- **F-2 (Medium-High):** Independent IP-level rate limiting on OTP request endpoints with secure client IP resolution (protecting against spoofed `X-Forwarded-For` headers) and normalized contact targets.
- **F-3 (Medium-High):** Document metadata validation hardening (enforcing 25MB file limits, MIME whitelist, SHA-256 checksum formatting, filename traversal sanitation, and authoritative server-side storage key derivation).
- **F-4 (Medium):** Abuse-prevention rate limits on application creation (`POST /api/v1/registration/applications/*`: 10 / 5 min) and tracking endpoints (`GET /api/v1/registration/track/*`: 30 / 1 min).
- **F-5 (Low-Medium):** Strict OTP purpose alignment preventing cross-purpose token replay between `REGISTRATION_OTP` and `PORTAL_ACCESS_OTP`.

All 88 registration test cases and all 41 core regression test cases passed with zero regressions. Strict database isolation on `sih_hospital_dev` was verified (500 hospitals, 8 users, 0 registration tables).

---

## 2. Remediations Implemented

### Finding F-1: Mandatory Tracking Token & Information Leak Prevention
- **Issue:** The public tracking endpoint previously permitted status queries using only `application_number`, and disclosed different error responses when an application existed versus when a token was invalid or expired.
- **Files Modified:**
  - `src/services/registration_service.py` (`track_application_public`)
  - `src/api/registration_routes.py` (`track_application_public`, `get_application_status_deprecated`)
  - `tests/test_registration_service.py`
  - `tests/test_registration_api.py`
- **Implementation Details:**
  1. `tracking_token` is now an explicit, required query parameter on both `/track/{application_number}` and `/public/track/{application_number}`.
  2. If `tracking_token` is missing or whitespace-only, a `422 Unprocessable Content` / `TrackingTokenError` is returned immediately.
  3. Validated token hash, expiration timestamp (`expires_at`), and revocation status (`is_revoked`).
  4. **Oracle Prevention:** Replaced divergent error messages with a uniform error: `TrackingTokenError("Invalid application number or tracking token.")`, which maps to HTTP `404 Not Found`. An attacker cannot distinguish between a non-existent application number, an invalid token, a revoked token, or an expired token.
  5. Authenticated applicant tracking (`GET /applications/me`) strictly validates ownership using `app.applicant_email == applicant_email` and returns HTTP `403 Forbidden` if an applicant attempts to read another applicant's record.

### Finding F-2: OTP IP-Level Rate Limiting & Proxy Verification
- **Issue:** OTP dispatch lacked IP-level rate limiting, allowing attackers to spray arbitrary phone numbers/emails from a single IP, and client IP resolution naively parsed `X-Forwarded-For`.
- **Files Modified:**
  - `src/api/registration_routes.py` (`_get_client_ip`, `request_applicant_otp`)
- **Implementation Details:**
  1. Updated `_get_client_ip`: Checks environment variable `SIH_TRUST_PROXY`. Unless explicitly set to `true` (case-insensitive), `X-Forwarded-For` and `X-Real-IP` headers are ignored, and `request.client.host` is used directly. When `SIH_TRUST_PROXY=true`, the leftmost client IP in `X-Forwarded-For` is extracted and stripped.
  2. Implemented independent IP-level rate limit: `OTP_IP_MAX_ATTEMPTS = 15` per `OTP_IP_WINDOW_SECONDS = 300` (5 minutes).
  3. Enforced target normalization (`target.strip().lower()`) prior to contact rate limit evaluation.
  4. Evaluated both IP-level and target-level rate limits *before* invoking `otp_service.request_otp()`, ensuring no SMS/email dispatch or token allocation occurs if either rate limit is exceeded.

### Finding F-3: Document Metadata Validation Hardening
- **Issue:** Document upload metadata lacked file size limits, MIME type validation, storage key spoofing safeguards, and path traversal protection in filenames.
- **Files Modified:**
  - `src/api/registration_schemas.py` (`UploadDocumentMetadataRequest`)
  - `src/services/registration_service.py` (`add_document_metadata`)
- **Implementation Details:**
  1. `file_size_bytes` enforced: must be strictly positive and `<= 26,214,400` (25MB).
  2. `mime_type` whitelist: strictly constrained to `application/pdf`, `image/jpeg`, and `image/png`.
  3. `checksum_sha256`: enforced strict 64-hex lower-case regex `^[a-f0-9]{64}$`.
  4. Filename sanitation: Rejected any `original_filename` containing path separators (`/`, `\\`), directory traversal sequences (`..`), or null bytes (`\x00`), and enforced regex pattern `^[a-zA-Z0-9_\-\. ]+$` (max length 255).
  5. **Authoritative Storage Keys:** Server ignores any client-supplied storage location and derives the authoritative storage key server-side:
     `documents/{application_id}/{secrets.token_hex(16)}_{slug}`.
  6. Explicitly documented the architectural distinction between metadata registration and byte-level payload validation.

### Finding F-4: Application Creation and Public Tracking Rate Limiting
- **Issue:** Unauthenticated or authenticated burst requests against application creation and tracking endpoints could lead to database connection exhaustion.
- **Files Modified:**
  - `src/api/registration_routes.py`
- **Implementation Details:**
  1. Added sliding-window rate limit for application creation: `APP_CREATE_MAX_ATTEMPTS = 10` per `APP_CREATE_WINDOW_SECONDS = 300` (5 minutes) across `create_state_application`, `create_district_application`, and `create_hospital_application`. Key format: `app_create:{client_ip}`.
  2. Added sliding-window rate limit for public tracking: `TRACK_MAX_ATTEMPTS = 30` per `TRACK_WINDOW_SECONDS = 60` (1 minute). Key format: `track:{client_ip}`.
  3. Exceeded limits return HTTP `429 Too Many Requests` with a descriptive message and rate limit category.

### Finding F-5: OTP Purpose Alignment & Cross-Purpose Replay Prevention
- **Issue:** `VerifyOTPRequest` lacked a `purpose` parameter, permitting potential cross-purpose reuse of tokens issued for registration during portal login.
- **Files Modified:**
  - `src/api/registration_schemas.py` (`RequestOTPRequest`, `VerifyOTPRequest`)
  - `src/services/otp_service.py` (`request_otp`, `verify_otp`, `VALID_OTP_PURPOSES`)
  - `src/api/registration_routes.py` (`request_applicant_otp`, `verify_applicant_otp`)
- **Implementation Details:**
  1. Defined `VALID_OTP_PURPOSES = frozenset({"PORTAL_ACCESS_OTP", "REGISTRATION_OTP"})`.
  2. Added `purpose` field to `VerifyOTPRequest` (defaulting to `"PORTAL_ACCESS_OTP"`).
  3. Verified `purpose in VALID_OTP_PURPOSES` on both request and verify steps in `OTPService`.
  4. Token lookup matches composite key `(identifier, purpose, target)`; verification against a mismatched purpose fails with invalid/expired token error.

---

## 3. Dedicated Security Remediation Test Suite

Five new end-to-end security test functions were introduced in `tests/test_registration_api.py`:
1. `test_f1_mandatory_tracking_token_and_oracle_prevention`:
   - Rejects public tracking request lacking `tracking_token` (HTTP 422).
   - Rejects tracking with invalid/bogus token with uniform HTTP 404 `"Invalid application number or tracking token."`.
   - Rejects tracking on non-existent application number with the identical HTTP 404 message.
   - Rejects tracking with expired or revoked token with identical HTTP 404.
   - Successfully returns sanitized milestones for valid `tracking_token`.
   - Confirms authenticated `/applications/me` enforces applicant ownership (HTTP 403 on mismatched email).
2. `test_f2_otp_ip_level_rate_limiting_and_target_spray`:
   - Enforces IP-level ceiling (15 requests) across differing destination phone numbers from the same client IP.
   - Verifies 16th request receives HTTP 429 `"Too many OTP requests from this IP address."`.
   - Verifies `SIH_TRUST_PROXY` handling: ignores spoofed `X-Forwarded-For` when flag is disabled.
3. `test_f3_document_metadata_security_validation`:
   - Rejects files exceeding 25MB (HTTP 422).
   - Rejects disallowed MIME types such as `application/x-sh` (HTTP 422).
   - Rejects path traversal filenames (`../../etc/passwd`) and null bytes (HTTP 422).
   - Rejects non-64-hex checksums (HTTP 422).
   - Verifies server-generated authoritative storage key overrides client-supplied keys.
4. `test_f4_application_creation_and_tracking_rate_limiting`:
   - Validates 10 allowed application creations in 5-minute sliding window, and triggers HTTP 429 on the 11th request.
   - Validates 30 allowed public tracking lookups in 1-minute window, and triggers HTTP 429 on the 31st request.
5. `test_f5_otp_purpose_alignment_and_mismatch`:
   - Requests OTP with purpose `"REGISTRATION_OTP"`.
   - Verifies that attempting verification with `"PORTAL_ACCESS_OTP"` fails (HTTP 400).
   - Confirms subsequent verification with matching `"REGISTRATION_OTP"` succeeds.

---

## 4. Verification & Test Execution Results

### 4.1 Registration Test Suites (88/88 PASSED)
```bash
.venv/bin/pytest tests/test_registration_api.py tests/test_registration_service.py tests/test_registration_models.py tests/test_registration_postgresql_live.py -v
```
**Results:**
- `tests/test_registration_api.py`: 22 passed
- `tests/test_registration_service.py`: 32 passed
- `tests/test_registration_models.py`: 11 passed
- `tests/test_registration_postgresql_live.py`: 23 passed
- **Total:** **88 passed, 0 failed** in 4.77s.

### 4.2 Core System Regression Suites (41/41 PASSED)
```bash
.venv/bin/pytest tests/test_live_postgresql_integration.py tests/test_postgresql_migration_and_transactions.py tests/test_end_to_end_referral_workflow.py tests/test_auth_and_access.py -v
```
**Results:**
- `tests/test_live_postgresql_integration.py`: 8 passed
- `tests/test_postgresql_migration_and_transactions.py`: 10 passed
- `tests/test_end_to_end_referral_workflow.py`: 10 passed
- `tests/test_auth_and_access.py`: 13 passed
- **Total:** **41 passed, 0 failed** in 5.61s.

### 4.3 Development Database Isolation (`sih_hospital_dev`)
```sql
SELECT count(*) AS hospital_count FROM hospitals;
SELECT count(*) AS user_count FROM users;
SELECT count(*) AS reg_tables_count FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'registration_%';
```
**Output:**
```
 hospital_count: 500
 user_count:     8
 reg_tables_count: 0
```
*Confirmed: The development database remains untouched with zero registration tables installed.*

### 4.4 Git Safety & Working Tree Status
```bash
git status -s && git stash list
```
- No git commits or pushes have been performed.
- Existing stash `stash@{0}: On master: Backup before GitHub repository synchronization` remains completely preserved.

---

## 5. Architectural & Security Limitations

While all five audit findings have been resolved, the following systemic considerations remain documented for subsequent phases:
1. **In-Memory Rate Limiting:** The default rate limiter relies on an in-memory sliding window when Redis is unavailable. In a multi-worker production cluster without shared Redis, rate limits are enforced per-worker rather than globally.
2. **Document Content Inspection:** F-3 validates document metadata before binary storage. Full virus scanning (e.g. ClamAV) and magic-byte deep inspection must occur in the binary ingestion service (Phase 1 Task 1E / S3 object store adapter) prior to serving files to reviewers.
3. **SMS/Email Gateway Integration:** In mock testing mode, OTPs are returned in debug payloads for automation. In production deployment, real gateway adapters must be enabled with secret credentials loaded from vault/environment variables.

---

## 6. Final Verdict

**TASK 1D SECURITY REMEDIATION STATUS: COMPLETE, VERIFIED & APPROVED.**
All remediation requirements have been implemented and validated against live PostgreSQL and FastAPI test environments. No further work on Task 1D is required. Proceeding to Task 1E is pending explicit user approval.
