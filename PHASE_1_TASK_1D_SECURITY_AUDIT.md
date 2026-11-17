# PHASE 1 — TASK 1D INDEPENDENT SECURITY AUDIT
**Registration API & Applicant Authentication Security Audit**
**Target System:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)
**Auditor:** Independent Security & System Architecture Review
**Date:** November 3, 2026
**Final Verdict:** **APPROVED WITH REQUIRED FIXES**

---

## 1. Audit Scope & Verification Methodology

This independent security audit examined the implementation of Phase 1 Task 1D across the following components:
- `src/services/otp_service.py`
- `src/auth/registration_auth.py`
- `src/api/registration_schemas.py`
- `src/api/registration_routes.py`
- `src/api/main.py`
- `src/services/registration_service.py`
- `src/auth/jwt_utils.py`
- `src/auth/rate_limiter.py` (Redis distributed rate limiting and token revocation)
- `tests/test_registration_api.py`
- `tests/test_registration_postgresql_live.py`
- `PHASE_1_TASK_1D_REPORT.md`

All findings were established through direct static code analysis and confirmed via empirical execution against both in-memory SQLite and live PostgreSQL 17 test environments. No modifications were made to the codebase during this audit.

---

## 2. Executive Summary & Verdict

### Final Verdict: **APPROVED WITH REQUIRED FIXES**

The core security foundations of Task 1D are structurally sound:
- **Authentication Context Isolation:** Dedicated `APPLICANT` role context is strictly separated from operational hospital staff (`HOSPITAL`) and administrative tiers.
- **Reviewer Governance & Boundaries:** Multi-tier administrative authority (`DISTRICT_ADMIN` at `DISTRICT_REVIEW`, `STATE_ADMIN` at `STATE_REVIEW`, `CENTRAL_ADMIN` at `CENTRAL_REVIEW`) and geographic boundaries are rigorously enforced across reviewer endpoints.
- **Self-Approval Prevention:** Reviewers are strictly blocked from reviewing applications where their user ID or email matches the applicant.
- **Data Minimization:** Public tracking responses strictly sanitize sensitive personal identifiers (Aadhaar, email, phone, reviewer remarks/IDs, storage keys, and tokens).
- **Database Safety:** `sih_hospital_dev` remains completely untouched (500 hospitals, 8 users, 0 registration tables).

However, **5 security findings** were identified that require remediation before moving to Task 1E, most notably the fact that **public tracking can currently be queried using an application number alone without requiring the secret tracking token**.

---

## 3. Detailed Audit Findings

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             FINDINGS SUMMARY MATRIX                              │
├─────┬─────────────────────────────────────────────────────────────┬──────────────┤
│ ID  │ Finding Description                                         │ Severity     │
├─────┼─────────────────────────────────────────────────────────────┼──────────────┤
│ F-1 │ Tracking Token is Optional in Public Tracking API           │ HIGH         │
│ F-2 │ Missing IP-Level Rate Limiting on OTP Request Endpoint      │ MEDIUM-HIGH  │
│ F-3 │ Path Traversal Sequences & Unbounded Size in Doc Metadata   │ MEDIUM-HIGH  │
│ F-4 │ Missing Rate Limiting on App Creation & Tracking Endpoints  │ MEDIUM       │
│ F-5 │ Hardcoded Token Purpose Mismatch on OTP Verification Route  │ LOW-MEDIUM   │
└─────┴─────────────────────────────────────────────────────────────┴──────────────┘
```

---

### Finding 1: Tracking Token is Optional in Public Tracking API (Accessible via Application Number Alone)
- **Component / File:** `src/api/registration_routes.py` (Line 610) & `src/services/registration_service.py` (Lines 992–1011)
- **Severity:** **HIGH**
- **Vulnerability Type:** Broken Object Level Authorization / Missing Access Control

#### Description
In `src/api/registration_routes.py`:
```python
@router.get("/public/track/{application_number}", response_model=PublicTrackingResponse)
@router.get("/track/{application_number}", response_model=PublicTrackingResponse)
def track_application_public(
    application_number: str,
    tracking_token: Optional[str] = Query(default=None, description="Optional secret tracking token for access tracking"),
    db: Session = Depends(get_db_session),
):
```
In `src/services/registration_service.py`:
```python
if tracking_token:
    token_hash = hashlib.sha256(tracking_token.strip().encode("utf-8")).hexdigest()
    tok = self.session.query(ApplicationTrackingToken).filter_by(
        application_id=app.application_id, token_hash=token_hash
    ).first()
    if not tok or tok.is_revoked:
        raise TrackingTokenError("Invalid, revoked, or non-matching tracking token.")
    ...
```
When `tracking_token` is omitted, the token verification block is completely skipped. Any unauthenticated caller who knows or guesses an application number can query the application's category, status, stage, location, facility name, and milestone timeline.

#### Test Evidence
```python
# Call /track/{application_number} without tracking_token query parameter
resp = client.get(f"/api/registration/track/{app_number}")
assert resp.status_code == 200
# Returned complete application dossier without token:
# {'application_number': 'APP-20261103-HOSP-A0FCC15B', 'applicant_name': 'Audit Hospital', 'status': 'SUBMITTED', ...}
```

#### Required Fix
1. In `src/api/registration_routes.py`: make `tracking_token: str = Query(..., min_length=16, description="Mandatory tracking token")` required.
2. In `src/services/registration_service.py`: in `track_application_public(self, application_number: str, tracking_token: str)`:
   - Validate that `tracking_token` is non-empty; raise `TrackingTokenError("Tracking token is required.")` if missing.
   - Always verify `token_hash` against `ApplicationTrackingToken`.

---

### Finding 2: Missing IP-Level Rate Limiting on OTP Request Endpoint (OTP Spray Vulnerability)
- **Component / File:** `src/api/registration_routes.py` (Lines 118–120)
- **Severity:** **MEDIUM-HIGH**
- **Vulnerability Type:** Denial of Service / Telephony & Email Flooding (CWE-799)

#### Description
The rate limit check in `request_applicant_otp` is currently keyed on the composite of client IP and recipient target:
```python
client_ip = _get_client_ip(request)
rate_key = f"otp_request:{client_ip}:{payload.contact_target.lower().strip()}"
check_rate_limit(rate_key, max_attempts=5, window_seconds=300)
record_failure(rate_key, window_seconds=300)
```
While this prevents brute-forcing or spamming the *same* recipient target from a single IP, each recipient target receives its own independent counter. Consequently, an attacker from a single IP address can send 5 requests to `victim1@example.com`, 5 requests to `victim2@example.com`, etc., spraying thousands of OTP emails or SMS messages without triggering the 5-attempt rate limit.

#### Test Evidence
```python
statuses = [client.post('/api/registration/auth/otp/request', json={
    'contact_target': f'victim_{i}@domain.org', 'channel': 'EMAIL', 'purpose': 'PORTAL_ACCESS_OTP'
}).status_code for i in range(15)]
# Result: [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200]
# 15 consecutive requests from a single client succeeded without being throttled.
```

#### Required Fix
Enforce dual-key rate limiting in `request_applicant_otp`:
1. Check IP-level ceiling:
   ```python
   check_rate_limit(f"otp_req_ip:{client_ip}", max_attempts=15, window_seconds=300)
   record_failure(f"otp_req_ip:{client_ip}", window_seconds=300)
   ```
2. Check Target-level ceiling:
   ```python
   check_rate_limit(f"otp_req_tgt:{payload.contact_target.lower().strip()}", max_attempts=5, window_seconds=300)
   record_failure(f"otp_req_tgt:{payload.contact_target.lower().strip()}", window_seconds=300)
   ```

---

### Finding 3: Path Traversal Sequences & Unbounded Size in Document Metadata Registration
- **Component / File:** `src/api/registration_schemas.py` (Lines 150–161) & `src/services/registration_service.py` (Lines 545–565)
- **Severity:** **MEDIUM-HIGH**
- **Vulnerability Type:** Improper Input Validation / Potential Path Traversal (CWE-20 / CWE-22)

#### Description
The document metadata registration schema currently defines:
```python
class UploadDocumentMetadataRequest(BaseModel):
    document_type: str
    original_filename: str
    mime_type: str
    file_size_bytes: int = Field(..., gt=0)
    storage_key: str
    checksum_sha256: str = Field(..., min_length=64, max_length=64)
```
- `original_filename` has no path traversal checks and no `max_length=255` bound (PostgreSQL column limit). Values such as `../../../etc/shadow` are accepted and stored.
- `storage_key` allows relative path traversal sequences (e.g. `../../secrets/key`).
- `file_size_bytes` has no upper bound (`gt=0`), allowing an applicant to register a file size of 100 GB (`107374182400` bytes).
- `mime_type` has no whitelist, accepting executable scripts (e.g. `application/x-sh`).
- `checksum_sha256` only validates character length (64), not hex characters (`^[a-f0-9]{64}$`), at the schema layer (though `RegistrationService` catches non-hex, it results in a 400 rather than schema-level 422).

#### Test Evidence
```python
doc_resp = client.post('/api/registration/applications/documents', json={
    'document_type': 'CLINICAL_LICENSE',
    'original_filename': '../../../etc/shadow',
    'mime_type': 'application/x-sh',
    'file_size_bytes': 100 * 1024 * 1024 * 1024,
    'storage_key': '../../secrets/key',
    'checksum_sha256': 'a' * 64
}, headers=headers)
# Result: Status 200 OK. Filename '../../../etc/shadow' and size 107374182400 were accepted.
```

#### Required Fix
Update `UploadDocumentMetadataRequest` in `src/api/registration_schemas.py`:
```python
original_filename: str = Field(..., max_length=255, pattern=r"^[a-zA-Z0-9_\-\. ]+$")
mime_type: str = Field(..., pattern=r"^(application/pdf|image/jpeg|image/png)$")
file_size_bytes: int = Field(..., gt=0, le=26214400) # 25 MB max
storage_key: str = Field(..., max_length=512, pattern=r"^[a-zA-Z0-9_\-\./]+$")
checksum_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
```
In `src/services/registration_service.py`: validate that `storage_key` and `original_filename` do not contain `..` or null bytes.

---

### Finding 4: Missing Rate Limiting on Application Creation and Public Tracking Endpoints
- **Component / File:** `src/api/registration_routes.py` (Lines 251–370, 606–628)
- **Severity:** **MEDIUM**
- **Vulnerability Type:** Unrestricted Resource Consumption (CWE-400)

#### Description
1. `POST /api/registration/applications/state`, `/district`, and `/hospital` create database records, generate public tracking tokens, and issue JWT tokens, but have no rate-limiting decorators or checks. A script can generate hundreds of dummy applications in seconds.
2. `GET /api/registration/track/{application_number}` has no rate limiting, allowing automated enumeration of application numbers.

#### Test Evidence
- 15 consecutive requests to `POST /api/registration/applications/hospital` succeeded with HTTP 200.
- 25 consecutive requests to `GET /api/registration/track/{application_number}` succeeded with HTTP 200.

#### Required Fix
Add sliding-window rate limit checks:
- On application creation routes:
  ```python
  check_rate_limit(f"app_create:{client_ip}", max_attempts=10, window_seconds=300)
  record_failure(f"app_create:{client_ip}", window_seconds=300)
  ```
- On tracking routes:
  ```python
  check_rate_limit(f"track:{client_ip}", max_attempts=30, window_seconds=60)
  record_failure(f"track:{client_ip}", window_seconds=60)
  ```

---

### Finding 5: Hardcoded Token Purpose Mismatch on OTP Verification Route
- **Component / File:** `src/api/registration_routes.py` (Line 180) & `src/api/registration_schemas.py` (Lines 30–34)
- **Severity:** **LOW-MEDIUM**
- **Vulnerability Type:** Input Validation Inconsistency

#### Description
`POST /api/registration/auth/otp/request` allows callers to specify any valid purpose (defaulting to `"PORTAL_ACCESS_OTP"`, but permitting `"REGISTRATION_OTP"`). However, `POST /api/registration/auth/otp/verify` hardcodes `purpose="PORTAL_ACCESS_OTP"` in its call to `otp_service.verify_otp`:
```python
contact_target = otp_service.verify_otp(
    token_id=payload.token_id,
    otp=payload.otp,
    purpose="PORTAL_ACCESS_OTP",
)
```
If an applicant requests an OTP with `purpose="REGISTRATION_OTP"`, calling `/auth/otp/verify` will always fail with HTTP 422:
`"Token purpose mismatch: expected 'PORTAL_ACCESS_OTP'."`

#### Test Evidence
```python
# Request with purpose="REGISTRATION_OTP"
# Verify with token_id and valid OTP
# Result: HTTP 422: {"detail": "Token purpose mismatch: expected 'PORTAL_ACCESS_OTP'."}
```

#### Required Fix
Add `purpose: str = Field(default="PORTAL_ACCESS_OTP")` to `VerifyOTPRequest` and pass `payload.purpose` to `otp_service.verify_otp`.

---

## 4. Deep Inspection of Secure Subsystems (Passed Areas)

| Security Domain | Status | Key Mechanism Verified |
|---|---|---|
| **Cryptographic OTP Generation** | **PASS** | `secrets.randbelow(900000) + 100000` (CSPRNG, 6 digits). Raw OTP is hashed with SHA-256 before DB insertion; raw OTP is never persisted. |
| **OTP Expiry & Attempt Limits** | **PASS** | 10-minute expiration strictly enforced. Maximum 3 verification attempts enforced with constant-time comparison `hmac.compare_digest`. |
| **OTP Replay Protection** | **PASS** | `vtoken.is_verified` flag is checked before evaluation and set to `True` on success; attempts to reuse return `"token already consumed"`. |
| **OTP Log Masking** | **PASS** | `_mask_contact_target` masks emails (`a***@domain.com`) and phone numbers; raw OTP is excluded from all logger calls and API response models. |
| **Applicant Context Isolation** | **PASS** | Token role is strictly `"APPLICANT"`. Applicants cannot access reviewer routes (403 Forbidden) or operational routes (403 Forbidden). |
| **Applicant Tenant Isolation** | **PASS** | All applicant mutations (`/draft`, `/documents`, `/submit`, `/resubmit`, `/me`) derive `application_id` directly from the validated JWT token; client cannot supply foreign IDs. |
| **Reviewer Role Gating** | **PASS** | `require_reviewer_user` validates role in `{"DISTRICT_ADMIN", "STATE_ADMIN", "CENTRAL_ADMIN"}`. Explicitly rejects `HOSPITAL` and `APPLICANT`. |
| **Geographic Scoping** | **PASS** | `DISTRICT_ADMIN` cannot view/review applications outside their district/state. `STATE_ADMIN` cannot view/review outside their state. |
| **Self-Approval Prevention** | **PASS** | `_validate_reviewer_authority` blocks reviewers whose `user_id` or `email` matches the application's creator or applicant email (403 Forbidden). |
| **Token Revocation (Redis)** | **PASS** | `POST /auth/logout` revokes tokens via distributed Redis blocklist. Subsequent requests immediately fail with 401 Unauthorized. |
| **Fail-Secure Redis Outage** | **PASS** | In production (`SIH_ENV=production`), `is_token_revoked` raises `RuntimeError` rather than failing open if Redis is down. |
| **Database Isolation** | **PASS** | `sih_hospital_dev` confirmed pristine: 500 hospitals, 8 users, 0 registration tables. |

---

## 5. Test Suite Verification Summary

The test suites were executed to verify system health and non-regression:

1. **Registration API Tests (`tests/test_registration_api.py`):** **17 passed**
2. **Registration Service Tests (`tests/test_registration_service.py`):** **36 passed**
3. **Registration Model Tests (`tests/test_registration_models.py`):** **7 passed**
4. **Live PostgreSQL Registration Tests (`tests/test_registration_postgresql_live.py`):** **23 passed**
5. **System Core Regression Suites (`test_live_postgresql_integration.py`, `test_postgresql_migration_and_transactions.py`, `test_end_to_end_referral_workflow.py`, `test_auth_and_access.py`):** **41 passed**

**Total: 124 passed, 0 failures, 0 regressions.**

---

## 6. Recommendations & Remediation Plan

To move from **APPROVED WITH REQUIRED FIXES** to fully **APPROVED**:

1. **Fix F-1 (Mandatory Tracking Token):**
   - Make `tracking_token` a required query parameter on `/track/{application_number}` and `/public/track/{application_number}`.
   - Enforce mandatory token hash verification in `RegistrationService.track_application_public`.
2. **Fix F-2 (Dual-Key OTP Rate Limiting):**
   - Add IP-level ceiling (15 requests / 5 minutes) to `request_applicant_otp` alongside recipient ceiling.
3. **Fix F-3 (Document Metadata Hardening):**
   - Enforce strict Pydantic regex patterns on `original_filename`, `storage_key`, `checksum_sha256`, `mime_type`, and set `le=26214400` on `file_size_bytes`.
4. **Fix F-4 (Rate Limiting on Creation & Tracking):**
   - Add sliding-window rate limit checks to application creation endpoints and tracking routes.
5. **Fix F-5 (OTP Purpose Alignment):**
   - Align `VerifyOTPRequest` and route verification with the requested purpose.
6. **Add Automated Security Regression Tests:**
   - Add explicit tests asserting that `GET /track/{app_num}` without a tracking token returns `422 Unprocessable Content` or `401 Unauthorized`.
   - Add tests verifying rejection of path traversal in document filenames and sizes exceeding 25MB.
   - Add tests verifying single-IP OTP spray throttling.
