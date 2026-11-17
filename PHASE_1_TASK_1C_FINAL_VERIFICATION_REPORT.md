# Phase 1 Task 1C — Final Fix Verification Report

**Date:** November 3, 2026  
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Scope:** Review and verification of database-level duplicate prevention and IntegrityError handling  
**Final Verdict:** **APPROVED WITH LIMITATIONS**  

---

## 1. Executive Summary

This independent verification reviewed the database-level duplicate prevention mechanism and exception handling implemented for Phase 1 Task 1C in:
- `migrations/003_registration_system.sql`
- `src/database/pg_models.py`
- `src/services/registration_service.py`
- `tests/test_registration_service.py`
- `tests/test_registration_postgresql_live.py`

All 65 registration tests and all 41 regression tests passed against live PostgreSQL (`sih_hospital_reg_test`) and SQLite. The primary development database (`sih_hospital_dev`) remains 100% untouched and unmigrated.

---

## 2. Assessment of Concern A: Hospital Identity

The partial unique index `uq_reg_app_active_hospital_email` enforces uniqueness on `LOWER(TRIM(applicant_email))` for active hospital applications (`status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')`).

### Evaluation Checklist

| Question | Verification Finding | Impact / Policy Conclusion |
| :--- | :--- | :--- |
| **1. Can one administrator register multiple hospitals?** | **No (while active).** If an administrator or nodal officer uses the same email for two hospital applications, the second is blocked by `uq_reg_app_active_hospital_email`. | Prevents credential collision upon user provisioning (`UNIQUE (email)` on `users`), but restricts one admin from concurrent multi-facility registration under a single email. |
| **2. Can the same hospital have different legitimate applicant emails?** | **Yes.** Two staff members (e.g., `admin@hospital.org` and `superintendent@hospital.org`) can submit applications for the same facility. | The database index will not detect that both applications represent the same physical facility. |
| **3. Can an applicant change email during correction/resubmission?** | **No in service workflow; Yes if mutable.** `resubmit_application` only accepts notes and document updates. If contact data is mutated, changing `applicant_email` alters the uniqueness key. | The application number remains stable (`APP-XXXX`), but identity tracking shifts with email mutations. |
| **4. Is there an existing hospital registration/license identifier in schema?** | **No.** Inspecting `registration_applications` and `hospitals` reveals no top-level column for Clinical Establishment Act license number or national facility registry ID (e.g. ROHINI / NIN / ABDM HFR). | Document files (`CLINICAL_LICENSE`) store binary uploads, and metadata is stored in unstructured `profile_data` JSONB, but neither provides an indexed scalar column. |
| **5. Can current index block legitimate registrations or allow duplicates?** | **Both edge cases exist:**<br>• *False Positive:* Hospital networks using a shared central contact email cannot submit concurrent applications.<br>• *False Negative:* Same physical facility applying under two distinct staff emails is allowed concurrently. | `applicant_email` is an **applicant-account business key**, not a physical facility registry key. |

### Documented Limitation
> **Limitation Statement:** `applicant_email` functions as an **interim business key / administrative contact identity** rather than a persistent physical facility identifier. It guarantees that each active application is tied to a distinct institutional login credential (`User.email`), avoiding provisioning collisions. However, true physical facility deduplication requires introducing a dedicated scalar column (such as `facility_license_number` or ABDM `hfr_facility_id`) in a future schema migration.

---

## 3. Assessment of Concern B: IntegrityError Handling

The `IntegrityError` handler in [`RegistrationService.create_application`](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/services/registration_service.py) was inspected and refined to strictly isolate the three intended partial unique indexes:

```python
        self.session.add(application)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()

            # Extract exact PostgreSQL constraint name from driver diagnostic or SQLite error text
            constraint_name = None
            if hasattr(exc, "orig") and exc.orig is not None:
                diag = getattr(exc.orig, "diag", None)
                if diag and getattr(diag, "constraint_name", None):
                    constraint_name = diag.constraint_name
                else:
                    orig_str = str(exc.orig)
                    for target in ("uq_reg_app_active_state", "uq_reg_app_active_district", "uq_reg_app_active_hospital_email"):
                        if target in orig_str:
                            constraint_name = target
                            break

            # Only violations of the three intended partial unique indexes become DuplicateApplicationError
            if constraint_name == "uq_reg_app_active_state":
                raise DuplicateApplicationError(
                    f"An active registration application already exists for State '{state}'."
                ) from exc
            elif constraint_name == "uq_reg_app_active_district":
                raise DuplicateApplicationError(
                    f"An active registration application already exists for District '{district}' in State '{state}'."
                ) from exc
            elif constraint_name == "uq_reg_app_active_hospital_email":
                raise DuplicateApplicationError(
                    f"An active hospital application already exists for email '{applicant_email}'."
                ) from exc
            else:
                # Unexpected integrity violations (e.g. Foreign Key, NOT NULL, CHECK constraints)
                # must NOT be misreported as duplicates. Re-raise original database exception.
                raise exc

        return application
```

### Verification Against Requirements:
1. **Intended Unique Index Isolation:** Only `uq_reg_app_active_state`, `uq_reg_app_active_district`, and `uq_reg_app_active_hospital_email` trigger `DuplicateApplicationError`.
2. **Foreign-Key Violations:** NOT misreported as duplicates; fallen through to `else:` and re-raised as `IntegrityError`.
3. **NOT NULL / Check Violations:** NOT misreported as duplicates; re-raised as `IntegrityError`.
4. **Transaction Rollback:** `self.session.rollback()` is executed immediately inside the `except` block before any exception is raised.
5. **Session Reusability:** Rollback clears the aborted PostgreSQL transaction status (`current transaction is aborted, commands ignored until end of transaction block`), allowing immediate subsequent queries or insertions.
6. **Exception Preservation:** Original database exception (`exc`) is re-raised intact preserving `pgcode` (`23502`, `23503`, `23514`) and diagnostic trace.

---

## 4. Test Verification Matrix

### New Test Cases Added

| Test Case | File | Description | Status |
| :--- | :--- | :--- | :--- |
| `test_different_hospitals_same_name_different_email_allowed` | `test_registration_service.py` | Two different hospitals sharing generic names (e.g. "Civil Hospital") with distinct emails succeed concurrently | **PASSED** |
| `test_same_hospital_with_changed_applicant_email_behavior` | `test_registration_service.py` | Verifies and documents that changing applicant email for same facility is permitted under current policy | **PASSED** |
| `test_two_different_hospitals_sharing_applicant_email_blocked` | `test_registration_service.py` | Administrator attempting to register two hospitals under same email is blocked with `DuplicateApplicationError` | **PASSED** |
| `test_unexpected_integrity_violation_not_misreported_as_duplicate` | `test_registration_service.py` | Simulated FK/NotNull `IntegrityError` re-raises original error, rolls back transaction, and allows session recovery | **PASSED** |
| `test_postgresql_unexpected_integrity_violation_preserves_exception` | `test_registration_postgresql_live.py` | Live PostgreSQL test verifying unexpected FK errors preserve `pgcode = '23503'`, roll back, and allow clean re-insert | **PASSED** |
| `test_postgresql_hospital_email_identity_policy_scenarios` | `test_registration_postgresql_live.py` | Live PostgreSQL test verifying multi-hospital email sharing blocked, different emails allowed, and database row count integrity | **PASSED** |

### Test Suite Execution Summary

```
1. tests/test_registration_models.py ............. 13 PASSED (0.28s)
2. tests/test_registration_service.py ............ 30 PASSED (0.75s)
3. tests/test_registration_postgresql_live.py .... 22 PASSED (2.95s)
   Subtotal: 65 registration tests PASSED (0 failures)

4. tests/test_live_postgresql_integration.py ...... 8 PASSED (1.95s)
5. tests/test_postgresql_migration_and_transactions 10 PASSED (0.73s)
6. tests/test_end_to_end_referral_workflow.py .... 10 PASSED (4.56s)
7. tests/test_auth_and_access.py ................. 13 PASSED (1.59s)
   Subtotal: 41 regression tests PASSED (0 failures)
```

---

## 5. Development Database Protection & Repository Integrity

- **Database Isolation Verification:**
  - `psql -d sih_hospital_dev -c "SELECT COUNT(*) FROM hospitals;"` -> `500`
  - `psql -d sih_hospital_dev -c "SELECT COUNT(*) FROM users;"` -> `8`
  - `psql -d sih_hospital_dev -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'registration_%';"` -> `0 rows`
- **Git State:**
  - Branch: `master`
  - No new commits or pushes performed.
  - Existing stash preserved: `stash@{0}: On master: Backup before GitHub repository synchronization`.

---

## 6. Final Verdict

### **APPROVED WITH LIMITATIONS**

1. **Approval:**
   - Database-level duplicate prevention via PostgreSQL partial unique indexes is fully functional and concurrency-safe.
   - `IntegrityError` handling strictly isolates the intended unique constraints by name (`uq_reg_app_active_*`), correctly rolls back transactions, maintains session reusability, and preserves original database exceptions for unexpected errors.
2. **Documented Limitation:**
   - `applicant_email` serves as an **interim business key / credential identity** for hospital applicants. It prevents concurrent duplicate submissions by the same applicant and protects against user provisioning collisions. Deduplication of physical facilities across different applicant emails will require a dedicated license/facility registry column in a future schema phase.
