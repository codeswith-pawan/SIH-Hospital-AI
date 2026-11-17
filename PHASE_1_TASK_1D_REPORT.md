# PHASE 1 — TASK 1D IMPLEMENTATION REPORT
**Registration API & Applicant Authentication**
**System:** AI-Powered Smart Hospital Referral System (`SIH_Hospital_AI`)
**Date:** November 3, 2026
**Status:** **COMPLETED & VERIFIED (ALL 124 TESTS PASSING)**

---

## 1. Executive Summary

Phase 1 Task 1D implements the REST API layer and dedicated applicant authentication system for the 3-Tier Hierarchical Hospital Registration System. This layer exposes endpoints for:
1. **Applicant Authentication & Session Management (Part A):** Simulated & configurable OTP generation, OTP verification, isolated `APPLICANT` JWT session tokens, and instant token revocation / logout via the distributed Redis blocklist.
2. **Applicant Application Lifecycle (Part B):** Creation of State, District, and Hospital applications, draft saving/updating, document metadata upload with cryptographic checksums, application submission, and resubmission following reviewer correction requests.
3. **Secure Public Tracking (Part C):** Public milestone and progress tracking (`/api/registration/track/{application_number}` and `/public/track/{application_number}`) that strictly sanitizes private identifiable data (Aadhaar, contact phone, contact email, reviewer internal IDs/notes, S3 storage keys, secret tokens).
4. **Hierarchical Reviewer Governance (Part D):** Role-gated and jurisdiction-constrained endpoints for `DISTRICT_ADMIN`, `STATE_ADMIN`, and `CENTRAL_ADMIN` to query applications, verify document metadata, execute stage decisions (`FORWARD`, `APPROVE`, `REJECT`), and issue specific correction requests. Operational `HOSPITAL` users and `APPLICANT` tokens are strictly blocked from reviewer actions. Self-approval is prevented at the API boundary.

All endpoints were constructed with Pydantic v2 data models, transaction-safe database session dependency injection, distributed sliding-window rate limiting, and zero ORM model leakage.

---

## 2. Architecture & Implemented Modules

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             FastAPI Router (/api/registration)                   │
├─────────────────────────┬───────────────────────────────┬────────────────────────┤
│    Part A: Auth         │       Part B & C: Lifecycle   │    Part D: Reviewer    │
│  - /auth/otp/request    │  - /applications/{type}       │  - /review/apps        │
│  - /auth/otp/verify     │  - /applications/draft        │  - /review/apps/{id}   │
│  - /auth/logout         │  - /applications/documents    │  - /review/docs/verify │
│                         │  - /applications/submit       │  - /review/decision    │
│                         │  - /applications/me           │  - /review/correct     │
│                         │  - /track/{app_number}        │                        │
└────────────┬────────────┴───────────────┬───────────────┴───────────┬────────────┘
             │                            │                           │
             ▼                            ▼                           ▼
┌─────────────────────────┐  ┌─────────────────────────┐ ┌─────────────────────────┐
│       OTPService        │  │   RegistrationService   │ │    RegistrationAuth     │
│  - SimulatedProvider    │  │  - Hierarchy Validation │ │  - require_applicant_   │
│  - SHA-256 OTP Hash     │  │  - Document Rules       │ │    user (role=APPLICANT)│
│  - Cooldown & Limits    │  │  - Stage Transitions    │ │  - require_reviewer_    │
│  - VerificationToken    │  │  - Append-Only History  │ │    user (roles in Admin)│
└─────────────────────────┘  └─────────────────────────┘ └─────────────────────────┘
```

### A. Core Source Files Created / Modified

| File | Type | Purpose |
|---|---|---|
| `src/services/otp_service.py` | New Service | Base OTP provider interface, `SimulatedOTPProvider` (in-memory, no secret leakage in logs), `ConfigurableOTPProvider`, and `OTPService` managing 6-digit cryptographic OTP generation, 60s cooldowns, max 3 verification attempts, constant-time `hmac.compare_digest` verification, and PostgreSQL `verification_tokens` table persistence. |
| `src/auth/registration_auth.py` | New Auth | `create_applicant_token()`, `decode_applicant_token()`, `require_applicant_user()` dependency (enforcing token non-revocation and `role == "APPLICANT"`), and `require_reviewer_user()` dependency (allowing only `DISTRICT_ADMIN`, `STATE_ADMIN`, `CENTRAL_ADMIN`, rejecting operational `HOSPITAL` and `APPLICANT`). |
| `src/api/registration_schemas.py` | New Schemas | Strictly validated Pydantic models with regex patterns (e.g., 64-char hex checksums, positive byte lengths <= 25MB, standard email/phone validation) preventing ORM leakage and invalid input states. |
| `src/api/registration_routes.py` | New Router | 17 REST endpoints implementing authentication, application submission, document registration, public tracking, and reviewer decision workflows. Configured with exception mappers (`_map_exception`) and sliding-window rate limiters. |
| `src/services/registration_service.py` | Updated Service | Added `update_draft_application()` for saving draft edits prior to submission; updated `review_application()` and `request_correction()` return dictionaries to supply response schemas with backward compatibility. |
| `src/api/main.py` | Updated App | Registered `registration_router` on `fastapi_app` under `/api/registration`. |
| `src/auth/jwt_utils.py` | Updated Auth | Added optional `email` claim to JWT access tokens so reviewer emails are verified for self-approval checks. |

---

## 3. Security Controls & Authorization Matrix

### A. Role Isolation Matrix

| Actor Role | Allowed Endpoints | Forbidden Endpoints | Enforcement Mechanism |
|---|---|---|---|
| `Anonymous / Public` | `/auth/otp/request`<br>`/auth/otp/verify`<br>`/track/{app_number}` | All authenticated endpoints | Missing `Authorization: Bearer <token>` header raises 401 Unauthorized |
| `APPLICANT` | `/applications/*`<br>`/applications/me`<br>`/applications/documents`<br>`/applications/submit`<br>`/applications/resubmit`<br>`/auth/logout` | `/review/*`<br>Operational endpoints (`/hospitals/{id}/inventory`, `/referrals/*`, `/district/*`, etc.) | `require_reviewer_user` checks `role != "APPLICANT"`; operational route checks `can_access_hospital` / `resolve_district_scope` reject with 403 Forbidden |
| `HOSPITAL` (Operational Staff) | Operational clinical dashboard & referrals | `/review/*`<br>Applicant registration endpoints | `require_reviewer_user` explicitly raises 403 Forbidden with `"Hospital staff role is not permitted to review registration applications."` |
| `DISTRICT_ADMIN` | `/review/applications` (filtered to their District & State)<br>`/review/applications/{id}` (matching District & State)<br>`/review/documents/{id}/verify`<br>`/review/applications/{id}/decision` (`DISTRICT_REVIEW` stage only) | Reviewing outside assigned District/State; reviewing in `STATE_REVIEW` or `CENTRAL_REVIEW` stages | Geographic jurisdiction checks raise 403 Forbidden; stage authority checks raise 403 Forbidden |
| `STATE_ADMIN` | `/review/applications` (filtered to their State)<br>`/review/applications/{id}` (matching State)<br>`/review/documents/{id}/verify`<br>`/review/applications/{id}/decision` (`STATE_REVIEW` stage only) | Reviewing outside assigned State; reviewing in `DISTRICT_REVIEW` or `CENTRAL_REVIEW` stages | Geographic jurisdiction checks raise 403 Forbidden; stage authority checks raise 403 Forbidden |
| `CENTRAL_ADMIN` | `/review/applications` (National scope)<br>`/review/applications/{id}`<br>`/review/documents/{id}/verify`<br>`/review/applications/{id}/decision` (`CENTRAL_REVIEW` stage only) | Reviewing earlier stages directly | Stage authority checks raise 403 Forbidden |

### B. Self-Approval Prevention
When an administrative reviewer attempts to approve or forward an application where their own user ID or verified email matches the applicant's record, `RegistrationService` raises `SelfApprovalError`, and the route responds with `403 Forbidden`:
```json
{
  "detail": "Applicant cannot review or approve their own application."
}
```

### C. Public Tracking Data Minimization
Public tracking responses via `/api/registration/track/{application_number}` only reveal:
- Application public reference number (`APP-YYYYMMDD-TT-XXXXXXXX`)
- Applicant type (`STATE`, `DISTRICT`, `HOSPITAL`)
- Applicant facility name
- State and District
- Current status (`SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`)
- Current stage (`DISTRICT_REVIEW`, `STATE_REVIEW`, `CENTRAL_REVIEW`, `APPROVED`)
- High-level audit milestone timeline (Action, Stage, Status, Timestamp)

**Strictly Excluded from Public Output:**
- Personal emails and phone numbers
- Aadhaar numbers and applicant contact details
- Internal reviewer user IDs, remarks, and IP addresses
- S3/MinIO document storage keys and SHA-256 checksums
- Internal authentication, tracking, and verification tokens

### D. Rate Limiting Safeguards
- **OTP Request Rate Limit:** Enforced via dual protection:
  - 60-second database-level cooldown per contact target.
  - Sliding-window Redis/in-memory rate limiting (max 5 requests per 300 seconds per client IP and contact target).
- **OTP Verification Rate Limit:** Max 3 attempts per token before invalidation; sliding-window rate limit of max 10 verification calls per 300 seconds.

---

## 4. API Endpoints Catalog

### Part A: Applicant Authentication
| Method | Route | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/registration/auth/otp/request` | Dispatches 6-digit OTP to email or phone | None (Rate Limited) |
| `POST` | `/api/registration/auth/otp/verify` | Validates OTP and returns restricted `APPLICANT` JWT | None (Rate Limited) |
| `POST` | `/api/registration/auth/logout` | Revokes applicant JWT token via distributed blocklist | Bearer (APPLICANT) |

### Part B: Applicant Lifecycle
| Method | Route | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/registration/applications/state` | Initiates State Level application in DRAFT | None / APPLICANT |
| `POST` | `/api/registration/applications/district` | Initiates District Level application in DRAFT | None / APPLICANT |
| `POST` | `/api/registration/applications/hospital` | Initiates Hospital Level application in DRAFT | None / APPLICANT |
| `PUT` | `/api/registration/applications/draft` | Updates draft application details | Bearer (APPLICANT) |
| `POST` | `/api/registration/applications/documents` | Uploads document metadata with SHA-256 checksum | Bearer (APPLICANT) |
| `POST` | `/api/registration/applications/submit` | Validates mandatory documents & submits application | Bearer (APPLICANT) |
| `GET` | `/api/registration/applications/me` | Fetches applicant's application and document states | Bearer (APPLICANT) |
| `POST` | `/api/registration/applications/resubmit` | Resubmits application after correction | Bearer (APPLICANT) |

### Part C: Public Tracking
| Method | Route | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/registration/track/{application_number}` | Safe public tracking of application milestones | None |
| `GET` | `/api/registration/public/track/{app_number}` | Alias route for safe public tracking | None |

### Part D: Reviewer Governance
| Method | Route | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/registration/review/applications` | Lists applications filtered by reviewer jurisdiction | Bearer (REVIEWER) |
| `GET` | `/api/registration/review/applications/{app_id}` | Full application review dossier with documents & audit | Bearer (REVIEWER) |
| `POST` | `/api/registration/review/documents/{doc_id}/verify` | Verifies or rejects uploaded document metadata | Bearer (REVIEWER) |
| `POST` | `/api/registration/review/applications/{app_id}/decision` | Executes stage decision (`FORWARD`, `APPROVE`, `REJECT`) | Bearer (REVIEWER) |
| `POST` | `/api/registration/review/applications/{app_id}/request-correction` | Requests applicant correction with reviewer notes | Bearer (REVIEWER) |

---

## 5. Verification & Empirical Test Results

### A. Registration API Test Suite (`tests/test_registration_api.py`)
Executed 17 comprehensive unit/integration test cases:
```
tests/test_registration_api.py::test_applicant_otp_request_and_verification_flow PASSED
tests/test_registration_api.py::test_applicant_otp_invalid_code_and_attempt_limit PASSED
tests/test_registration_api.py::test_applicant_otp_cooldown_rate_limit PASSED
tests/test_registration_api.py::test_applicant_logout_and_token_invalidation PASSED
tests/test_registration_api.py::test_create_state_and_district_and_hospital_applications PASSED
tests/test_registration_api.py::test_update_draft_application_and_submit PASSED
tests/test_registration_api.py::test_applicant_token_cannot_access_operational_or_reviewer_routes PASSED
tests/test_registration_api.py::test_applicant_ownership_isolation PASSED
tests/test_registration_api.py::test_public_tracking_privacy_sanitization PASSED
tests/test_registration_api.py::test_reviewer_workflow_geographic_access_and_hierarchy PASSED
tests/test_registration_api.py::test_correction_request_and_applicant_resubmission_api PASSED
tests/test_registration_api.py::test_self_approval_prevention_via_api PASSED
tests/test_registration_api.py::test_otp_api_rate_limiting PASSED
tests/test_registration_api.py::test_document_metadata_validation_errors PASSED
tests/test_registration_api.py::test_reviewer_application_listing_and_filtering PASSED
tests/test_registration_api.py::test_public_tracking_not_found_and_token_verification PASSED
tests/test_registration_api.py::test_resubmit_without_correction_required_fails PASSED
============================== 17 passed in 1.22s ==============================
```

### B. Live PostgreSQL API Integration Test (`tests/test_registration_postgresql_live.py`)
Executed complete live PostgreSQL test suite including end-to-end API HTTP calls against live PostgreSQL 17:
```
tests/test_registration_postgresql_live.py::test_postgresql_status_default_and_draft_timestamps PASSED
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_orm PASSED
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_raw_sql PASSED
tests/test_registration_postgresql_live.py::test_postgresql_indexes_deep_catalog_and_orm_verification PASSED
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_update PASSED
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_delete PASSED
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_blocks_application_delete_via_restrict PASSED
tests/test_registration_postgresql_live.py::test_postgresql_tracking_token_reusable_and_revocable PASSED
tests/test_grandfathering_scenario_1_fresh_500_hospitals PASSED
tests/test_grandfathering_scenario_2_successful_rerun PASSED
tests/test_grandfathering_scenario_3_gh00501_inserted_before_rerun PASSED
tests/test_grandfathering_scenario_4_partial_grandfathered_state_aborts PASSED
tests/test_grandfathering_scenario_5_unexpected_grandfathered_hospital_aborts PASSED
tests/test_grandfathering_scenario_6_missing_legacy_hospital_aborts PASSED
tests/test_postgresql_live_registration_service_full_workflow PASSED
tests/test_postgresql_live_registration_service_correction_and_resubmit PASSED
tests/test_postgresql_concurrent_duplicate_prevention_threads PASSED
tests/test_postgresql_concurrent_duplicate_prevention_district_threads PASSED
tests/test_postgresql_rejected_application_allows_new_active_application PASSED
tests/test_postgresql_case_and_whitespace_index_enforcement_raw_sql PASSED
tests/test_postgresql_unexpected_integrity_violation_preserves_exception PASSED
tests/test_postgresql_hospital_email_identity_policy_scenarios PASSED
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_api_workflow PASSED
============================== 23 passed in 3.25s ==============================
```

### C. Complete Registration Suite
```bash
.venv/bin/pytest tests/test_registration_api.py tests/test_registration_service.py tests/test_registration_models.py tests/test_registration_postgresql_live.py -v
```
**Result: 83 passed in 4.18s**

### D. System Regression Test Suites
```bash
.venv/bin/pytest tests/test_live_postgresql_integration.py tests/test_postgresql_migration_and_transactions.py tests/test_end_to_end_referral_workflow.py tests/test_auth_and_access.py -v
```
**Result: 41 passed in 5.93s**

**Combined Total: 124 passed, 0 failed, 0 regressions.**

---

## 6. Database Isolation Verification

`sih_hospital_dev` was protected throughout the entire implementation and testing process.

Direct PostgreSQL verification command:
```python
conn = psycopg2.connect(dbname="sih_hospital_dev", user="pawankumarsharma", host="localhost", port=5432)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM hospitals;")
h_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM users;")
u_count = cur.fetchone()[0]
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name IN ('registration_applications', 'registration_documents', 'approval_history', 'verification_tokens', 'application_tracking_tokens', 'account_activation_tokens');
""")
tables = cur.fetchall()
```

**Output:**
```
sih_hospital_dev verification:
Hospitals count: 500 (Expected: 500)
Users count: 8 (Expected: 8)
Registration tables present: 0 (Expected: 0)
```
- Exactly 500 legacy hospitals present.
- Exactly 8 operational users present.
- Exactly 0 registration tables present.
- Migration `003_registration_system.sql` has not been executed on `sih_hospital_dev`.
- Git stash `stash@{0}` is preserved intact.
- Zero commits or pushes performed.

---

## 7. Next Steps

Phase 1 Task 1D is complete. Awaiting user review and authorization before proceeding to Phase 1 Task 1E.
