# PHASE 1 — TASK 1D FINAL INDEPENDENT SECURITY RE-AUDIT REPORT

**Project:** SIH Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** Phase 1 — Task 1D Final Independent Security Re-Audit  
**Auditor:** Independent Security & Code-Level Verification Agent  
**Date:** 2026-11-03  
**Status:** COMPLETE & EMPIRICALLY VERIFIED  
**Final Verdict:** **APPROVED WITH LIMITATIONS**  

---

## 1. Executive Summary

This independent code-level security re-audit evaluated the remediated implementation of **Phase 1 Task 1D: Registration API & Applicant Authentication**. The audit directly inspected the source code, conducted live API and database tests, evaluated attack vectors (application enumeration, rate-limit bypassing, path traversal, cross-purpose OTP replay), resolved test-count integrity questions, and verified database isolation on `sih_hospital_dev`.

All five findings from `PHASE_1_TASK_1D_SECURITY_AUDIT.md` have been successfully remediated and empirically verified. 

**Summary Verdict:** **APPROVED WITH LIMITATIONS**  
*Rationale for Limitations:* Document upload endpoints currently validate document *metadata* only (enforcing 25MB limits, MIME whitelists, SHA-256 formatting, filename traversal sanitation, and authoritative server storage keys). Multipart binary payload streaming, virus scanning, and physical object storage persistence are explicitly part of Phase 1 Task 1E.

---

## 2. Code-Level Verification of Findings (F-1 through F-5)

### A. Finding F-1: Mandatory Tracking Token & Information Leakage Prevention

#### 1. Code Inspection
- **`src/services/registration_service.py` (`track_application_public`, lines 1004–1066):**
  - Requires non-empty `tracking_token` parameter (line 1014).
  - Retrieves application by `application_number` (line 1018).
  - Calculates SHA-256 hash of provided tracking token (line 1026).
  - Queries `ApplicationTrackingToken` bound strictly to `(application_id, token_hash)` (line 1028).
  - Validates `is_revoked == False` and `expires_at > now` (lines 1032–1038).
  - **Uniform Error Handling (Oracle Elimination):**
    Lines 1024, 1033, and 1038 uniformly raise:
    ```python
    raise TrackingTokenError("Invalid application number or tracking token.")
    ```
- **`src/api/registration_routes.py` (`track_application_public`, lines 651–704):**
  - Decorates both `/api/registration/track/{application_number}` and `/api/registration/public/track/{application_number}`.
  - Declares `tracking_token: str = Query(..., min_length=16)` making it mandatory at the HTTP level.
  - Catches `TrackingTokenError` and maps it uniformly to `HTTP 404 Not Found` with detail `"Invalid application number or tracking token."` (line 219).
- **`src/api/registration_routes.py` (`get_applicant_own_application`, lines 426–490):**
  - Authenticated tracking via `/applications/me` strictly verifies that `app.applicant_email.lower() == applicant["applicant_email"].lower()`. Mismatched requests return `HTTP 403 Forbidden`.

#### 2. Empirical Verification Evidence
Executed against live test database and FastAPI router:
- **Missing token:** Request without `?tracking_token=` rejected with `HTTP 422 Unprocessable Content`.
- **Invalid token:** Request with bogus token rejected with `HTTP 404 ("Invalid application number or tracking token.")`.
- **Cross-application token:** Application A queried with Application B's valid token rejected with `HTTP 404 ("Invalid application number or tracking token.")`.
- **Non-existent application number:** Query for unknown application number rejected with identical `HTTP 404 ("Invalid application number or tracking token.")`. Response status, header format, and body are completely indistinguishable from an invalid token on an existing application.
- **Expired token:** Token with `expires_at` in the past rejected with `HTTP 404 ("Invalid application number or tracking token.")`.
- **Revoked token:** Token with `is_revoked = True` rejected with `HTTP 404 ("Invalid application number or tracking token.")`.
- **Valid token:** Returns `HTTP 200 OK` with public milestone history, strictly sanitizing private fields (`applicant_email`, `applicant_phone`, Aadhaar, reviewer IDs, internal reviewer remarks).

#### 3. Remaining Limitations
- Tracking tokens are hashed using SHA-256 without per-application salt. Given that raw tokens are 128-bit cryptographically secure hex strings (`secrets.token_hex(16)`), preimage and rainbow attacks are infeasible, but future iterations could incorporate per-application salting.

---

### B. Finding F-2: OTP Rate Limiting & Proxy Verification

#### 1. Code Inspection
- **`src/api/registration_routes.py` (`_get_client_ip`, lines 80–101):**
  - Inspects `os.getenv("SIH_TRUST_PROXY", "").lower() in ("true", "1")`.
  - If `SIH_TRUST_PROXY` is not enabled, `X-Forwarded-For` and `X-Real-IP` headers are strictly ignored, and `request.client.host` is used.
  - When enabled, parses the leftmost IP in `X-Forwarded-For` and trims whitespace.
- **`src/api/registration_routes.py` (`request_applicant_otp`, lines 134–153):**
  - Normalizes target: `target = payload.contact_target.strip().lower()`.
  - Checks independent IP limit: `check_rate_limit(f"otp_req_ip:{client_ip}", max_attempts=15, window_seconds=300)`.
  - Records IP failure/attempt: `record_failure(f"otp_req_ip:{client_ip}", window_seconds=300)`.
  - Checks independent target limit: `check_rate_limit(f"otp_req_tgt:{target}", max_attempts=5, window_seconds=300)`.
  - Evaluates both limits *prior* to calling `otp_service.request_otp()`, preventing provider dispatch when limits are reached.
- **`src/services/otp_service.py` (`request_otp`, lines 180–205):**
  - Enforces active cooldown against recent unexpired tokens: raises `ValidationError` if `resend_available_at > now`.

#### 2. Empirical Verification Evidence
- **IP-Level Spray Protection:** 15 requests to 15 different email addresses from one IP succeeded. The 16th request was blocked with `HTTP 429 Too Many Requests`.
- **Target Casing Normalization:** An initial request to `user@example.com` succeeded. An immediate subsequent request to `USER@EXAMPLE.COM` was blocked by the resend cooldown (`HTTP 422 ("OTP was recently sent. Please wait 59 seconds...")`).
- **Untrusted `X-Forwarded-For` Spoofing:** With `SIH_TRUST_PROXY` unset, injecting spoofed IPs (`198.51.100.1` through `198.51.100.16`) did not bypass IP rate limiting. The 16th request was blocked based on `request.client.host`.
- **Trusted Proxy Configuration:** With `SIH_TRUST_PROXY=true`, client IPs were parsed correctly from `X-Forwarded-For`.
- **Redis Outage Behavior:** In development/testing mode, the rate limiter falls back to thread-safe in-memory sliding window storage (`_IN_MEMORY_FAILURES`). In production mode (`is_production() == True`), it strictly fails fast with `RuntimeError` per Phase 17 security specifications.

#### 3. Remaining Limitations
- When operating in development mode with in-memory fallback, rate-limit counters are process-local and do not sync across multi-process workers. Production deployments require a running Redis cluster.

---

### C. Finding F-3: Document Metadata Validation & Security

#### 1. Code Inspection
- **`src/api/registration_schemas.py` (`UploadDocumentMetadataRequest`, lines 160–205):**
  - `file_size_bytes`: Field constrained with `gt=0`, `le=26_214_400` (25MB).
  - `mime_type`: Field pattern constrained: `^(application/pdf|image/jpeg|image/png)$`.
  - `checksum_sha256`: Pattern constrained to lowercase 64-hex: `^[a-f0-9]{64}$`.
  - `original_filename`: Length `max_length=255`, regex constrained: `^[a-zA-Z0-9_\-\. ]+$`.
- **`src/services/registration_service.py` (`add_document_metadata`, lines 560–614):**
  - Defense-in-depth size validation: checks `file_size_bytes <= 26_214_400`.
  - Defense-in-depth MIME whitelist validation against `VALID_DOCUMENT_MIME_TYPES`.
  - Path traversal and null byte rejection:
    ```python
    if ".." in original_filename or "/" in original_filename or "\\" in original_filename or "\x00" in original_filename:
        raise ValidationError("Invalid filename: path traversal sequences and separators are forbidden.")
    ```
  - **Authoritative Server-Side Storage Key Derivation:**
    Lines 600–605 completely disregard any client-provided storage key and authoritatively generate:
    ```python
    server_storage_key = f"documents/{application_id}/{secrets.token_hex(16)}_{clean_filename}"
    ```
- **`src/api/registration_routes.py` (`upload_document_metadata`, lines 522–550):**
  - Uses authenticated applicant context to ensure documents are attached to the applicant's own application.

#### 2. Empirical Verification Evidence
- **Directory traversal (`../../etc/passwd`):** Rejected with `HTTP 422`.
- **Absolute path (`/var/log/secrets.txt`):** Rejected with `HTTP 422`.
- **Backslash traversal (`..\\windows\\system32`):** Rejected with `HTTP 422`.
- **Null byte (`test.pdf\x00.exe`):** Rejected with `HTTP 422`.
- **Oversized file (`26,214,401` bytes):** Rejected with `HTTP 422`.
- **Invalid MIME (`application/x-sh`):** Rejected with `HTTP 422`.
- **Invalid checksum (uppercase hex or 63 chars):** Rejected with `HTTP 422`.
- **Forged storage key override:** Request specifying `storage_key: "s3://hacked-bucket/overwritten.pdf"` was overridden by the server and persisted as `documents/APP_.../c5613c..._valid_order.pdf`.

#### 3. Remaining Limitations & Deferred Scope
- **Metadata Only:** The current endpoint registers metadata records in PostgreSQL. It does not accept binary payloads (multipart/form-data) or stream bytes to object storage.
- **Remaining Task 1E Scope:**
  1. Multipart/streamed binary file upload endpoint.
  2. S3/MinIO/blob storage adapter integration.
  3. Antivirus scanning integration (ClamAV) on binary streams.
  4. Magic-byte (file signature) binary verification (e.g. `python-magic`) to ensure payload bytes match declared MIME headers.

---

### D. Finding F-4: Endpoint Rate Limiting

#### 1. Code Inspection
- **`src/api/registration_routes.py`:**
  - `create_state_application` (lines 288–290): `check_rate_limit(f"app_create:{client_ip}", max_attempts=10, window_seconds=300)`.
  - `create_district_application` (lines 336–338): `check_rate_limit(f"app_create:{client_ip}", max_attempts=10, window_seconds=300)`.
  - `create_hospital_application` (lines 384–386): `check_rate_limit(f"app_create:{client_ip}", max_attempts=10, window_seconds=300)`.
  - `track_application_public` (lines 664–668): `check_rate_limit(f"track:{client_ip}", max_attempts=30, window_seconds=60)`.

#### 2. Empirical Verification Evidence
- **Application Creation Rate Limiting:** 10 hospital applications created sequentially from one IP succeeded; the 11th request was blocked with `HTTP 429 Too Many Requests`.
- **Public Tracking Rate Limiting:** 30 tracking queries from one IP succeeded; the 31st request was blocked with `HTTP 429 Too Many Requests`.
- **Independent Rate-Limit Keys:** Exhausting the public tracking limit (30 requests -> 429) did not block application creation requests from the same IP, verifying strict namespace isolation between `track:{ip}` and `app_create:{ip}`.
- **Rate-Limit Reset:** Invoking `reset_rate_limits()` immediately restored access across all limited keys.

---

### E. Finding F-5: OTP Purpose Alignment & Identity Binding

#### 1. Code Inspection
- **`src/services/otp_service.py`:**
  - Defines `VALID_OTP_PURPOSES = frozenset({"PORTAL_ACCESS_OTP", "REGISTRATION_OTP", "LOGIN_OTP", "PASSWORD_RESET_OTP"})` (lines 33–35).
  - `request_otp` (lines 164–167): Validates `purpose in VALID_OTP_PURPOSES`.
  - `verify_otp` (lines 252–265): Validates `purpose in VALID_OTP_PURPOSES` and checks `vtoken.token_purpose == purpose`. Mismatches raise `ValidationError("Token purpose mismatch: expected '...'.")`.
  - Composite storage key in provider: `key = f"{contact_target}:{purpose}"`.
- **`src/api/registration_schemas.py` (`VerifyOTPRequest`, lines 34–40):**
  - Includes `purpose: str = Field(default="PORTAL_ACCESS_OTP", pattern=...)`.
- **`src/api/registration_routes.py` (`verify_applicant_otp`, lines 200–205):**
  - Passes `payload.purpose` into `otp_service.verify_otp(...)`.

#### 2. Empirical Verification Evidence
- **Purpose Alignment:** OTP requested with `REGISTRATION_OTP` and verified with `REGISTRATION_OTP` succeeds and returns applicant JWT token.
- **Cross-Purpose Rejection:** OTP requested with `REGISTRATION_OTP` and verified with `PORTAL_ACCESS_OTP` is rejected with `ValidationError: Token purpose mismatch: expected 'PORTAL_ACCESS_OTP'`.
- **Contact Target Binding:** Verification tokens are strictly bound to `contact_target`.
- **Single-Use Replay Prevention:** Consuming an OTP marks `is_verified = True`. A second verification attempt of the same token raises `ValidationError("This verification token has already been consumed.")`.
- **Expired Token Rejection:** Setting `expires_at` in the past causes verification to fail with `ValidationError("Verification OTP has expired. Please request a new OTP.")`.
- **Attempt Lockout:** 3 incorrect OTP entries exhaust `max_attempts`. A 4th attempt with the correct code is rejected with `ValidationError("Maximum verification attempts exceeded. Please request a new OTP.")`.

---

## 3. Test Suite Integrity & Regression Analysis

### A. Investigation of Test Count Discrepancy (11 vs 13 Model Tests)

During the audit, the report history was examined to investigate why model tests were previously cited as 11 instead of 13.

1. **Inspection of `tests/test_registration_models.py`:**
   Direct inspection of `tests/test_registration_models.py` revealed **13 distinct test functions**:
   - `test_registration_application_creation_and_relationships` (line 52)
   - `test_draft_application_submitted_at_null_until_submission` (line 93)
   - `test_unique_application_number_constraint` (line 166)
   - `test_document_metadata_and_verification_status` (line 196)
   - `test_approval_history_append_only_flow` (line 232)
   - `test_verification_token_expiration_and_attempt_limits` (line 285)
   - `test_account_activation_token_single_use` (line 320)
   - `test_hospital_grandfathering_logic_simulation` (line 362)
   - `test_registration_application_default_status_and_stage_draft` (line 434)
   - `test_registration_check_constraints_enforcement` (line 461)
   - `test_approval_history_protection_and_restrict_delete` (line 515)
   - `test_application_tracking_tokens_reusable_and_revocable` (line 560)
   - `test_submitted_at_preserved_against_manual_overwrite` (line 617)

2. **Execution Verification:**
   Running `pytest tests/test_registration_models.py -v` collected and executed **all 13 tests**; all 13 passed cleanly in 0.32s.

3. **Root Cause Determination:**
   In `PHASE_1_TASK_1D_REMEDIATION_REPORT.md` Section 4.1, the breakdown table recorded:
   - `tests/test_registration_service.py`: 32 passed
   - `tests/test_registration_models.py`: 11 passed
   
   In reality, `test_registration_service.py` has **30 tests** and `test_registration_models.py` has **13 tests** ($30 + 13 = 43$). The discrepancy was purely a **typographical transposition in the summary markdown table** of the remediation report. **Zero test functions were removed, skipped, or weakened.**

### B. Full Test Execution Results

#### 1. Registration Test Suites (88/88 PASSED)
```bash
.venv/bin/pytest tests/test_registration_api.py tests/test_registration_service.py tests/test_registration_models.py tests/test_registration_postgresql_live.py -v
```
- `tests/test_registration_api.py`: **22 passed**
- `tests/test_registration_service.py`: **30 passed**
- `tests/test_registration_models.py`: **13 passed**
- `tests/test_registration_postgresql_live.py`: **23 passed**
- **Total: 88 passed, 0 failed in 4.77s**

#### 2. Core System Regression Suites (41/41 PASSED)
```bash
.venv/bin/pytest tests/test_live_postgresql_integration.py tests/test_postgresql_migration_and_transactions.py tests/test_end_to_end_referral_workflow.py tests/test_auth_and_access.py -v
```
- `tests/test_live_postgresql_integration.py`: **8 passed**
- `tests/test_postgresql_migration_and_transactions.py`: **10 passed**
- `tests/test_end_to_end_referral_workflow.py`: **10 passed**
- `tests/test_auth_and_access.py`: **13 passed**
- **Total: 41 passed, 0 failed in 5.65s**

**Combined Total: 129 tests passed, 0 failures, 0 regressions.**

---

## 4. Database & Git Safety Verification

### A. Development Database Isolation (`sih_hospital_dev`)
Executed direct catalog query against `sih_hospital_dev`:
```sql
SELECT count(*) AS hospital_count FROM hospitals;
SELECT count(*) AS user_count FROM users;
SELECT count(*) AS reg_tables_count 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE 'registration_%';
```
**Results:**
- `hospital_count`: **500** (intact)
- `user_count`: **8** (intact)
- `reg_tables_count`: **0** (no registration tables exist in development database)
- **Confirmation:** Migration 003 has **not** been executed against `sih_hospital_dev`.

### B. Git Working Tree Integrity
Executed `git status -s && git stash list`:
- Zero commits or pushes have been executed.
- Working directory changes remain uncommitted and unstaged.
- Existing stash preserved:
  `stash@{0}: On master: Backup before GitHub repository synchronization`

---

## 5. Scope Boundary & Remaining Work for Task 1E

| Component | Status in Task 1D | Deferred Scope for Task 1E |
| :--- | :--- | :--- |
| **Document Metadata** | Complete & Hardened (Validation, traversal sanitation, server storage key generation) | N/A |
| **Binary File Ingestion** | Not Implemented | Multipart form-data streaming upload endpoint |
| **Object Store Integration** | Abstracted via storage keys | S3 / MinIO / Local filesystem binary storage adapter |
| **Antivirus Scanning** | Not Implemented | ClamAV stream scanner integration |
| **Magic-Byte Inspection** | Not Implemented | Libmagic / `python-magic` signature verification on file payloads |
| **SMS/Email Gateway** | Simulated Provider | Production Twilio/SendGrid/SES gateway adapters with vault credentials |

---

## 6. Final Audit Verdict

```
================================================================================
FINAL VERDICT: APPROVED WITH LIMITATIONS
================================================================================
```

### Summary of Justification:
1. All five security audit findings (F-1 through F-5) are robustly remediated and verified with empirical test evidence.
2. Public tracking status enumeration oracles are eliminated via mandatory tracking tokens and uniform HTTP 404 responses.
3. Dual-key rate limiting protects OTP dispatch against spray and brute-force attacks.
4. Document metadata is strictly validated and filenames are sanitized against traversal attacks.
5. All 13 registration model tests and all 30 service tests are intact and passing.
6. The core operational system passes all 41 regression tests with zero degradation.
7. Development database isolation on `sih_hospital_dev` is 100% preserved.
8. The "Limitations" qualification accurately reflects that binary payload streaming, storage adapters, and virus scanning are designated for Phase 1 Task 1E.

**Task 1D is formally approved. Do not proceed to Task 1E without explicit user instruction.**
