# Phase 1 Task 1C — Fix Report: Database-Level Duplicate Prevention

**Date:** November 3, 2026  
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Scope:** Resolving High-Severity Finding from Independent Security Audit (`PHASE_1_TASK_1C_SECURITY_AUDIT.md`)  
**Target Database:** `sih_hospital_reg_test` (live PostgreSQL test fixture)  
**Production/Dev Guard:** `sih_hospital_dev` remains 100% untouched and unmigrated (500 hospitals, 8 users, 0 registration tables)  

---

## 1. Executive Summary

During the Task 1C Independent Security and Business Logic Audit, a **High-severity concurrency finding** was identified:
> While `RegistrationService` performed pre-flight application-level queries to detect duplicate active applications, the underlying PostgreSQL database lacked partial unique indexes. Under concurrent incoming requests (e.g., race conditions between network retries or automated submissions), two identical active registration applications could be committed simultaneously.

This remediation implements database-level partial unique indexes across PostgreSQL and SQLAlchemy ORM metadata, backed by clean `IntegrityError` interception and transaction rollback in `RegistrationService.create_application`.

---

## 2. Canonical Identity Selection Rationale

### Hospital Entity Identity: Why `applicant_name` Was Rejected

`applicant_name` was evaluated and intentionally **rejected** as the unique identifier for hospital applications for the following structural reasons:

1. **Non-Uniqueness of Hospital Names:**  
   Common institutional titles such as *"Civil Hospital"*, *"Community Health Centre (CHC)"*, *"Sanjivani Clinic"*, or *"Apollo Clinic"* exist in multiple locations across districts and states, and can even coexist within the same metropolitan administrative boundary.
2. **Name Variance & Formatting Inconsistencies:**  
   Institutional names suffer from formatting irregularities (e.g., *"Fortis Hospital"*, *"Fortis Healthcare Ltd"*, *"Dr. Fortis Hospital"*), making name-based uniqueness constraints fragile and prone to either false positives or false negatives.
3. **Canonical Institutional Point of Contact (`applicant_email`):**  
   In the registration domain model and downstream provisioning pipeline:
   - `applicant_email` is mandatory (`VARCHAR(255) NOT NULL`).
   - The primary administrator account provisioned upon final approval uses this institutional email (`User.email`), which is subject to an unconditional database uniqueness constraint (`UNIQUE (email)` in `users`).
   - Multiple active applications with the same email would cause credential provisioning collisions and conflate notification and verification token routing.
   - Therefore, the official institutional email (`LOWER(TRIM(applicant_email))`) is the canonical entity identifier for hospital onboarding.

### Canonical Identifiers by Applicant Tier

| Applicant Tier | Canonical Identifier | Scoping Predicate |
| :--- | :--- | :--- |
| **STATE** | `LOWER(TRIM(state))` | `WHERE applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')` |
| **DISTRICT** | `(LOWER(TRIM(state)), LOWER(TRIM(district)))` | `WHERE applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')` |
| **HOSPITAL** | `LOWER(TRIM(applicant_email))` | `WHERE applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')` |

Applications with terminal or inactive states (`REJECTED`, `APPROVED`) are **excluded** by the index predicate, ensuring that rejected institutions or administrative entities can immediately submit a fresh application.

---

## 3. Schema & ORM Implementation

### A. PostgreSQL Migration (`migrations/003_registration_system.sql`)

```sql
-- Partial unique indexes to prevent concurrent duplicate active applications
-- Active statuses: DRAFT, SUBMITTED, UNDER_REVIEW, CORRECTION_REQUIRED
-- Canonical identities:
-- 1. State: LOWER(TRIM(state)) for applicant_type = 'STATE'
-- 2. District: LOWER(TRIM(state)), LOWER(TRIM(district)) for applicant_type = 'DISTRICT'
-- 3. Hospital: LOWER(TRIM(applicant_email)) for applicant_type = 'HOSPITAL'
-- (REJECTED and APPROVED applications do not prevent new applications)
CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_state
ON registration_applications (LOWER(TRIM(state)))
WHERE applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_district
ON registration_applications (LOWER(TRIM(state)), LOWER(TRIM(district)))
WHERE applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_hospital_email
ON registration_applications (LOWER(TRIM(applicant_email)))
WHERE applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');
```

### B. SQLAlchemy 2.0 Model Parity (`src/database/pg_models.py`)

Added to `RegistrationApplication.__table_args__`:

```python
        Index(
            "uq_reg_app_active_state",
            func.lower(func.trim(text("state"))),
            unique=True,
            postgresql_where=text("applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
        Index(
            "uq_reg_app_active_district",
            func.lower(func.trim(text("state"))),
            func.lower(func.trim(text("district"))),
            unique=True,
            postgresql_where=text("applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
        Index(
            "uq_reg_app_active_hospital_email",
            func.lower(func.trim(text("applicant_email"))),
            unique=True,
            postgresql_where=text("applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
            sqlite_where=text("applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')"),
        ),
```

---

## 4. Service-Layer Exception Handling & Session Recovery

In `src/services/registration_service.py`:

```python
        self.session.add(application)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            err_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)
            err_msg_lower = err_msg.lower()
            if "uq_reg_app_active_state" in err_msg or ("state" in err_msg_lower and "unique" in err_msg_lower):
                raise DuplicateApplicationError(
                    f"An active registration application already exists for State '{state}'."
                ) from exc
            elif "uq_reg_app_active_district" in err_msg or ("district" in err_msg_lower and "unique" in err_msg_lower):
                raise DuplicateApplicationError(
                    f"An active registration application already exists for District '{district}' in State '{state}'."
                ) from exc
            elif "uq_reg_app_active_hospital_email" in err_msg or ("applicant_email" in err_msg_lower and "unique" in err_msg_lower):
                raise DuplicateApplicationError(
                    f"An active hospital application already exists for email '{applicant_email}'."
                ) from exc
            elif "application_number" in err_msg_lower:
                raise DuplicateApplicationError(
                    f"Application number conflict occurred ({app_num}). Please retry."
                ) from exc
            else:
                raise DuplicateApplicationError(
                    f"An active registration application already exists or integrity constraint violated: {err_msg}"
                ) from exc

        return application
```

### Guarantees Enforced:
1. **Immediate Database Validation on Flush:** `flush()` forces the INSERT statement into the transaction pipeline immediately, executing unique index verification prior to returning.
2. **Deterministic Rollback:** On constraint violation, `self.session.rollback()` clears the PostgreSQL aborted transaction status, preventing `PendingRollbackError` on subsequent requests.
3. **Domain Exception Translation:** Database driver exceptions (`psycopg2.errors.UniqueViolation`, `sqlite3.IntegrityError`) are never leaked to API callers; they are mapped to `DuplicateApplicationError`.

---

## 5. Verification & Test Evidence

### A. Live PostgreSQL Integration Tests (`tests/test_registration_postgresql_live.py`)

All **20 tests passed** against live PostgreSQL (`sih_hospital_reg_test`):

```
tests/test_registration_postgresql_live.py::test_postgresql_status_default_and_draft_timestamps PASSED [  5%]
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_orm PASSED [ 10%]
tests/test_registration_postgresql_live.py::test_postgresql_submitted_at_automatic_lifecycle_raw_sql PASSED [ 15%]
tests/test_registration_postgresql_live.py::test_postgresql_indexes_deep_catalog_and_orm_verification PASSED [ 20%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_update PASSED [ 25%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_delete PASSED [ 30%]
tests/test_registration_postgresql_live.py::test_postgresql_approval_history_blocks_application_delete_via_restrict PASSED [ 35%]
tests/test_registration_postgresql_live.py::test_postgresql_tracking_token_reusable_and_revocable PASSED [ 40%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_1_fresh_500_hospitals PASSED [ 45%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_2_successful_rerun PASSED [ 50%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_3_gh00501_inserted_before_rerun PASSED [ 55%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_4_partial_grandfathered_state_aborts PASSED [ 60%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_5_unexpected_grandfathered_hospital_aborts PASSED [ 65%]
tests/test_registration_postgresql_live.py::test_grandfathering_scenario_6_missing_legacy_hospital_aborts PASSED [ 70%]
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_full_workflow PASSED [ 75%]
tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_correction_and_resubmit PASSED [ 80%]
tests/test_registration_postgresql_live.py::test_postgresql_concurrent_duplicate_prevention_threads PASSED [ 85%]
tests/test_registration_postgresql_live.py::test_postgresql_concurrent_duplicate_prevention_district_threads PASSED [ 90%]
tests/test_registration_postgresql_live.py::test_postgresql_rejected_application_allows_new_active_application PASSED [ 95%]
tests/test_registration_postgresql_live.py::test_postgresql_case_and_whitespace_index_enforcement_raw_sql PASSED [100%]

============================== 20 passed in 3.91s ==============================
```

#### Key Highlights of Live PostgreSQL Concurrency Verification:
1. `test_postgresql_concurrent_duplicate_prevention_threads`:
   - Two concurrent worker threads synchronized with a `threading.Barrier` attempted to create an active application with the identical email `concurrency.test@hospital.org`.
   - Exactly one thread succeeded (`SUCCESS`).
   - The other thread caught the database unique index violation and returned `DuplicateApplicationError`.
   - The failing worker session executed a rollback and immediately performed a clean second application insertion without error.
   - Database verified: `SELECT COUNT(*) FROM registration_applications` returned exactly `1`.
2. `test_postgresql_indexes_deep_catalog_and_orm_verification`:
   - Verified all **20 indexes** in `pg_indexes` catalog and SQLAlchemy ORM metadata matching table names, uniqueness flags, and predicate clauses.

### B. Unit & Service-Layer Tests (`tests/test_registration_service.py`)

All **27 tests passed**:

```
tests/test_registration_service.py::test_valid_parent_child_hierarchy PASSED [  3%]
tests/test_registration_service.py::test_invalid_hierarchy_unrecognized_state PASSED [  7%]
tests/test_registration_service.py::test_invalid_hierarchy_district_state_mismatch PASSED [ 11%]
tests/test_registration_service.py::test_create_hospital_application_success PASSED [ 14%]
tests/test_registration_service.py::test_create_application_invalid_email_or_phone PASSED [ 18%]
tests/test_registration_service.py::test_prevent_duplicate_active_application_for_state PASSED [ 22%]
tests/test_registration_service.py::test_prevent_duplicate_active_application_for_district PASSED [ 25%]
tests/test_registration_service.py::test_duplicate_allowed_after_rejection PASSED [ 29%]
tests/test_registration_service.py::test_prevent_duplicate_active_application_for_hospital_by_email PASSED [ 33%]
tests/test_registration_service.py::test_case_and_whitespace_insensitive_duplicate_prevention PASSED [ 37%]
tests/test_registration_service.py::test_different_hospitals_same_name_different_email_allowed PASSED [ 40%]
tests/test_registration_service.py::test_rejected_hospital_allows_new_application PASSED [ 44%]
tests/test_registration_service.py::test_transaction_remains_usable_after_duplicate_application_error PASSED [ 48%]
...
============================== 27 passed in 0.52s ==============================
```

### C. Regression Suites

| Suite | Scope | Status | Result |
| :--- | :--- | :--- | :--- |
| `tests/test_live_postgresql_integration.py` | Core referral workflow & live database integrity | **PASSED** | 8 passed in 1.95s |
| `tests/test_postgresql_migration_and_transactions.py` | Transaction atomicity & bed locks | **PASSED** | 10 passed in 0.73s |
| `tests/test_end_to_end_referral_workflow.py` | End-to-end referral routing & notifications | **PASSED** | 10 passed in 4.56s |
| `tests/test_auth_and_access.py` | RBAC & geographical jurisdiction enforcement | **PASSED** | 13 passed in 1.59s |
| `tests/test_registration_models.py` | Model constraints, triggers & listeners | **PASSED** | 13 passed in 0.28s |

### D. Production Database Isolation Check

```
psql -d sih_hospital_dev:
- hospitals count: 500
- users count: 8
- registration_% tables: 0
```
`sih_hospital_dev` remains 100% untouched and preserved.

---

## 6. Conclusion

The High-severity concurrency finding from the Task 1C Security Audit is completely resolved. The registration pipeline now guarantees data integrity under extreme concurrency through database-enforced partial unique indexes in PostgreSQL and SQLite, while providing graceful rollback and domain-level error handling at the application layer.
