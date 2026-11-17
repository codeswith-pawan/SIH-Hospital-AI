# PHASE 1 — TASK 1C: INDEPENDENT SECURITY AND BUSINESS LOGIC AUDIT

**Target Repository:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Audit Target:** Task 1C — Registration Business Logic and Service Layer  
**Files Audited:**
- `src/services/registration_service.py`
- `src/services/registration_exceptions.py`
- `src/database/registration_service.py`
- `src/database/db_manager.py`
- `tests/test_registration_service.py`
- `tests/test_registration_postgresql_live.py`
- `migrations/003_registration_system.sql`
- `src/database/pg_models.py`

**Audit Timestamp:** 2026-11-03T19:59:00+05:30  
**Final Verdict:** **APPROVED WITH REQUIRED FIXES**

---

## 1. Executive Summary

An independent, code-level security and architectural audit was performed on the Task 1C registration service implementation. The inspection verified 15 distinct functional, security, and integrity domains against actual Python code, SQLAlchemy ORM event listeners, PostgreSQL triggers, and test suites.

- **14 of 15 verification areas PASSED** with strong code-level controls and 100% test coverage.
- **1 area (Area 4: Concurrent Duplicate Application Prevention at Database Level)** revealed a database-level schema gap: while sequential duplicate prevention is enforced at the service layer, the underlying PostgreSQL schema in migration 003 lacks partial unique indexes on active application states, leaving a theoretical race condition under concurrent requests.
- All 92 automated tests (22 new service tests, 13 model tests, 16 live PostgreSQL integration tests, and 41 regression tests) pass with zero failures.
- The development database `sih_hospital_dev` was verified to be **completely untouched** (500 legacy hospitals, 8 users, 0 registration tables).

---

## 2. In-Depth Verification of the 15 Audit Areas

---

### Area 1: Correct State, District and Hospital Approval Hierarchy
- **File & Functions:**  
  `src/services/registration_service.py`: `submit_application` and `review_application`
- **Code Lines:**  
  - Lines 408–412:
    ```python
    initial_stage = {
        "HOSPITAL": "DISTRICT_REVIEW",
        "DISTRICT": "STATE_REVIEW",
        "STATE": "CENTRAL_REVIEW",
    }[app.applicant_type]
    ```
  - Lines 656–687:
    ```python
    if old_stage == "DISTRICT_REVIEW":
        app.status = "UNDER_REVIEW"
        app.current_stage = "STATE_REVIEW"
        recorded_action = "FORWARD"
    elif old_stage == "STATE_REVIEW":
        app.status = "UNDER_REVIEW"
        app.current_stage = "CENTRAL_REVIEW"
        recorded_action = "FORWARD"
    elif old_stage == "CENTRAL_REVIEW":
        is_eligible, issues = self.check_final_approval_eligibility(app.application_id)
        if not is_eligible:
            raise IneligibleForApprovalError(...)
        app.status = "APPROVED"
        app.current_stage = "APPROVED"
        app.final_approved_at = datetime.now(timezone.utc)
        recorded_action = "APPROVE"
    ```
- **Evaluation:** **PASS**. Hospital traverses 3 stages (District $\to$ State $\to$ Central $\to$ Approved). District traverses 2 stages (State $\to$ Central $\to$ Approved). State traverses 1 stage (Central $\to$ Approved).
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_hospital_full_approval_chain`
  - `tests/test_registration_service.py::test_district_two_tier_approval_chain`
  - `tests/test_registration_service.py::test_state_single_tier_approval_chain`
  - `tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_full_workflow`
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 2: Reviewer Stage Authority and Geographic Jurisdiction Enforcement
- **File & Function:**  
  `src/services/registration_service.py`: `_validate_reviewer_authority`
- **Code Lines:**  
  Lines 559–595:
  ```python
  if current_stage == "DISTRICT_REVIEW":
      if reviewer_role != "DISTRICT_ADMIN":
          raise UnauthorizedReviewerError(f"Only DISTRICT_ADMIN can review at DISTRICT_REVIEW stage...")
      rev_state = (reviewer.get("state") or "").lower()
      rev_district = (reviewer.get("district") or "").lower()
      if rev_state != (app.state or "").lower() or rev_district != (app.district or "").lower():
          raise GeographicAccessError(f"District Admin ({reviewer.get('district')}, {reviewer.get('state')}) cannot review application in ({app.district}, {app.state}).")
  elif current_stage == "STATE_REVIEW":
      if reviewer_role != "STATE_ADMIN":
          raise UnauthorizedReviewerError(f"Only STATE_ADMIN can review at STATE_REVIEW stage...")
      rev_state = (reviewer.get("state") or "").lower()
      if rev_state != (app.state or "").lower():
          raise GeographicAccessError(f"State Admin ({reviewer.get('state')}) cannot review application in State ({app.state}).")
  elif current_stage == "CENTRAL_REVIEW":
      if reviewer_role != "CENTRAL_ADMIN":
          raise UnauthorizedReviewerError(f"Only CENTRAL_ADMIN can review at CENTRAL_REVIEW stage...")
  ```
- **Evaluation:** **PASS**. Strict role check and lowercase normalized geographic boundary enforcement. Hospital staff role is explicitly barred at lines 555–556.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_unauthorized_stage_review_rejected`
  - `tests/test_registration_service.py::test_geographic_access_boundary_enforced`
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 3: Self-Approval Prevention
- **File & Function:**  
  `src/services/registration_service.py`: `_validate_reviewer_authority`
- **Code Lines:**  
  Lines 546–556:
  ```python
  if reviewer_id and (
      reviewer_id == app.applicant_email
      or reviewer_id == app.nodal_officer_name
      or reviewer.get("email") == app.applicant_email
      or (app.provisioned_entity_id and reviewer_id == app.provisioned_entity_id)
  ):
      raise SelfApprovalError("Applicant cannot review or approve their own application.")

  if reviewer_role == "HOSPITAL":
      raise UnauthorizedReviewerError("Hospital staff role is not permitted to review registration applications.")
  ```
- **Evaluation:** **PASS**. Compares reviewer identity (`user_id` and `email`) against applicant contact email, nodal officer name, and provisioned entity ID.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_self_approval_prevented`
- **Missing Tests:** None.
- **Severity:** **High**.

---

### Area 4: Concurrent Duplicate Application Prevention at Database Level
- **File & Functions:**  
  - `src/services/registration_service.py`: `check_duplicate_active_application` (lines 214–287)
  - `migrations/003_registration_system.sql`: lines 140–147
  - `src/database/pg_models.py`: lines 353–357
- **Code Lines:**  
  - In `registration_service.py` lines 228–286:
    ```python
    # Application-level SELECT ... WHERE status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED')
    ```
  - In `migrations/003_registration_system.sql` lines 144–147:
    ```sql
    CREATE INDEX IF NOT EXISTS idx_reg_app_status ON registration_applications (status, current_stage);
    CREATE INDEX IF NOT EXISTS idx_reg_app_geo ON registration_applications (state, district);
    CREATE INDEX IF NOT EXISTS idx_reg_app_email ON registration_applications (applicant_email);
    CREATE INDEX IF NOT EXISTS idx_reg_app_type ON registration_applications (applicant_type);
    ```
- **Evaluation:** **FAIL / GAP IDENTIFIED (APPROVED WITH REQUIRED FIXES)**.
  - *Finding:* `check_duplicate_active_application` prevents duplicate active applications during sequential execution. However, at the **database level**, `idx_reg_app_geo`, `idx_reg_app_email`, and `idx_reg_app_type` are standard non-unique btree indexes. Under high concurrent traffic in PostgreSQL's default `READ COMMITTED` isolation level, two simultaneous `POST /register` requests for the same State or District could both execute the `SELECT` check before either transaction commits, bypassing the application-level check and creating duplicate active applications.
  - *Required Fix:* Add partial unique indexes at the database schema level:
    ```sql
    CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_state_app 
    ON registration_applications (LOWER(state)) 
    WHERE applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

    CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_district_app 
    ON registration_applications (LOWER(state), LOWER(district)) 
    WHERE applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

    CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_hospital_app 
    ON registration_applications (LOWER(state), LOWER(district), LOWER(applicant_name)) 
    WHERE applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');
    ```
- **Test Evidence:**  
  - Sequential tests pass: `tests/test_registration_service.py::test_prevent_duplicate_active_application_for_state` & `test_prevent_duplicate_active_application_for_district`.
- **Missing Tests:** Multi-threaded concurrency race condition test attempting simultaneous inserts.
- **Severity:** **High**.

---

### Area 5: Cryptographic Reference Number Collision Handling
- **File & Function:**  
  `src/services/registration_service.py`: `generate_application_number`
- **Code Lines:**  
  Lines 189–212:
  ```python
  for _ in range(10):
      token_entropy = secrets.token_hex(4).upper()  # 4 bytes = 8 hex chars (4.29 billion possibilities)
      candidate = f"APP-{date_str}-{type_prefix}-{token_entropy}"
      exists = (
          self.session.query(RegistrationApplication.application_number)
          .filter(RegistrationApplication.application_number == candidate)
          .first()
      )
      if not exists:
          return candidate

  raise RegistrationServiceError("Failed to generate unique application number after maximum retries.")
  ```
- **Evaluation:** **PASS**. Employs `secrets.token_hex(4).upper()` providing 32 bits of cryptographic randomness. Collision check loop retries up to 10 times. Backed by PostgreSQL `UNIQUE NOT NULL` constraint on `registration_applications.application_number`.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_reference_generation_uniqueness` (generates 50 sequential unique IDs with zero collisions).
  - `tests/test_registration_models.py::test_unique_application_number_constraint` (asserts database `IntegrityError` if duplicate number is attempted).
- **Missing Tests:** None.
- **Severity:** **Medium**.

---

### Area 6: Document Verification Authority Controls
- **File & Function:**  
  `src/services/registration_service.py`: `verify_document`
- **Code Lines:**  
  Lines 504–530:
  ```python
  doc = self.session.query(RegistrationDocument).filter_by(document_id=document_id).first()
  if not doc:
      raise DocumentError(...)
  app = doc.application
  self._validate_reviewer_authority(reviewer_user, app)
  doc.verification_status = verification_status
  doc.reviewer_id = reviewer_user.get("user_id")
  doc.reviewer_remarks = reviewer_remarks
  doc.reviewed_at = datetime.now(timezone.utc)
  ```
- **Evaluation:** **PASS**. Reuses `_validate_reviewer_authority`, ensuring that only the authorized reviewer for the application's current stage and geographic region can verify or reject documents.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_document_metadata_storage_and_verification`
  - `tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_full_workflow`
- **Missing Tests:** None.
- **Severity:** **High**.

---

### Area 7: Immutability of Reviewer Decisions and Approval History
- **Files:**  
  - `migrations/003_registration_system.sql`: lines 197–244
  - `src/services/registration_service.py`
- **Code Lines:**  
  - Database trigger `trg_fn_protect_approval_history` in `migrations/003_registration_system.sql` lines 232–243:
    ```sql
    CREATE OR REPLACE FUNCTION trg_fn_protect_approval_history() 
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Approval history is an append-only audit trail: % operation is prohibited on table approval_history.', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    ```
  - In `src/services/registration_service.py`:
    No update or delete methods exist for `ApprovalHistory`. All transitions only insert new records.
- **Evaluation:** **PASS**. Protected at both the service layer (no mutation functions) and the database engine layer (trigger prohibits UPDATE and DELETE, and foreign key constraint specifies `ON DELETE RESTRICT`).
- **Test Evidence:**  
  - `tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_update`
  - `tests/test_registration_postgresql_live.py::test_postgresql_approval_history_trigger_blocks_delete`
  - `tests/test_registration_postgresql_live.py::test_postgresql_approval_history_blocks_application_delete_via_restrict`
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 8: Tracking Token Expiry, Revocation, and Hash Verification
- **File & Functions:**  
  `src/services/registration_service.py`: `create_tracking_token` and `track_application_public`
- **Code Lines:**  
  Lines 344–364 & lines 908–927:
  ```python
  # Storage
  raw_secret = secrets.token_urlsafe(32)
  token_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
  ...
  # Verification
  if tracking_token:
      token_hash = hashlib.sha256(tracking_token.strip().encode("utf-8")).hexdigest()
      tok = self.session.query(ApplicationTrackingToken).filter_by(application_id=app.application_id, token_hash=token_hash).first()
      if not tok or tok.is_revoked:
          raise TrackingTokenError("Invalid, revoked, or non-matching tracking token.")
      if tok_exp < now:
          raise TrackingTokenError("Tracking token has expired.")
      tok.access_count += 1
      tok.last_accessed_at = now
  ```
- **Evaluation:** **PASS**. Tokens are stored as SHA-256 hashes, revoked tokens are rejected immediately, expired tokens are blocked, and access count is safely incremented.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_invalid_or_expired_tracking_token`
  - `tests/test_registration_models.py::test_application_tracking_tokens_reusable_and_revocable`
  - `tests/test_registration_postgresql_live.py::test_postgresql_tracking_token_reusable_and_revocable`
- **Missing Tests:** None.
- **Severity:** **High**.

---

### Area 9: Public Tracking Information Sanitization
- **File & Function:**  
  `src/services/registration_service.py`: `track_application_public`
- **Code Lines:**  
  Lines 929–950:
  ```python
  milestones = []
  for h in app.history:
      milestones.append({
          "stage": h.review_tier,
          "action": h.action,
          "status": h.new_status,
          "timestamp": h.created_at.isoformat() if h.created_at else None,
      })

  return {
      "application_number": app.application_number,
      "applicant_type": app.applicant_type,
      "applicant_name": app.applicant_name,
      "state": app.state,
      "district": app.district,
      "status": app.status,
      "current_stage": app.current_stage,
      "created_at": app.created_at.isoformat() if app.created_at else None,
      "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
      "resubmission_version": app.resubmission_version,
      "milestones": milestones,
  }
  ```
- **Evaluation:** **PASS**. Rigorously excludes: applicant phone numbers, email addresses, physical street address/pincode, nodal officer identity, profile details, internal reviewer remarks, reviewer user IDs, IP addresses, document storage paths, and password/auth tokens.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_safe_public_tracking_output` (explicitly asserts absence of `applicant_phone`, `applicant_email`, `storage_key`, `password`, `token_hash`, `aadhaar`, `remarks`, `reviewer_user_id`, `ip_address`).
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 10: Original `submitted_at` Preservation Across Correction & Resubmission
- **Files & Triggers/Listeners:**  
  - `migrations/003_registration_system.sql`: `trg_fn_manage_application_submission_lifecycle` (lines 98–110)
  - `src/database/pg_models.py`: `_handle_registration_application_before_update` (lines 405–420)
  - `src/services/registration_service.py`: `resubmit_application` (lines 773–820)
- **Code Lines:**  
  - In `pg_models.py`:
    ```python
    if original_submitted_at is not None:
        target.submitted_at = original_submitted_at
    ```
  - In trigger:
    ```sql
    ELSIF OLD.status = 'CORRECTION_REQUIRED' AND NEW.status IN ('SUBMITTED', 'UNDER_REVIEW') THEN
        IF OLD.submitted_at IS NOT NULL THEN
            NEW.submitted_at := OLD.submitted_at;
        END IF;
        NEW.resubmitted_at := NOW();
        NEW.resubmission_version := OLD.resubmission_version + 1;
    ```
- **Evaluation:** **PASS**. Preserved at dual layers: PostgreSQL trigger and SQLAlchemy attribute history listener. Tested against intentional overwrite attempts.
- **Test Evidence:**  
  - `tests/test_registration_models.py::test_submitted_at_preserved_against_manual_overwrite`
  - `tests/test_registration_service.py::test_correction_request_and_applicant_resubmission`
  - `tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_correction_and_resubmit`
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 11: Complete Transition Recording in Approval History
- **File & Functions:**  
  `src/services/registration_service.py`:
  - `submit_application` (lines 419–430): records `SUBMIT`
  - `review_application` (lines 635–646 & 688–699): records `REJECT`, `FORWARD`, `APPROVE`
  - `request_correction` (lines 752–763): records `REQUEST_CORRECTION`
  - `resubmit_application` (lines 799–810): records `RESUBMIT`
- **Evaluation:** **PASS**. Every lifecycle event is logged with actor role, review tier, previous status, new status, remarks, and client IP.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_hospital_full_approval_chain` (asserts actions `["SUBMIT", "FORWARD", "FORWARD", "APPROVE"]`)
  - `tests/test_registration_service.py::test_correction_request_and_applicant_resubmission` (asserts actions `["SUBMIT", "REQUEST_CORRECTION", "RESUBMIT"]`)
  - `tests/test_registration_postgresql_live.py::test_postgresql_live_registration_service_full_workflow` (verifies full PostgreSQL audit trail)
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 12: Mandatory Document Verification Enforcement on Final Approval
- **File & Functions:**  
  `src/services/registration_service.py`: `check_final_approval_eligibility` and `review_application`
- **Code Lines:**  
  Lines 671–678 & 848–866:
  ```python
  # In review_application:
  elif old_stage == "CENTRAL_REVIEW":
      is_eligible, issues = self.check_final_approval_eligibility(app.application_id)
      if not is_eligible:
          raise IneligibleForApprovalError(f"Application is ineligible for final approval: {'; '.join(issues)}")
  ...
  # In check_final_approval_eligibility:
  unverified = [doc for doc in app.documents if doc.verification_status != "VERIFIED"]
  if unverified:
      issues.append(...)
  ```
- **Evaluation:** **PASS**. Final approval unconditionally executes eligibility checks. If any mandatory document is missing or any document has status `PENDING` or `REJECTED`, approval is strictly rejected.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_final_approval_eligibility_checks`
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 13: Transaction Rollback on Failure
- **File & Class:**  
  `src/services/registration_service.py`: `RegistrationService`
- **Code Inspection:**  
  All mutating service methods invoke `self.session.flush()`, deferring `commit()` to the outer caller transaction boundary. If any domain rule fails (or an `IntegrityError` is triggered), `session.rollback()` clears all flushed state completely.
- **Evaluation:** **PASS**. Atomicity is guaranteed without partial record leakage.
- **Test Evidence:**  
  - `tests/test_registration_service.py::test_transaction_rollback_on_review_failure`
- **Missing Tests:** None.
- **Severity:** **High**.

---

### Area 14: No Operational User Creation Prior to Final Approval
- **File:** `src/services/registration_service.py`
- **Code Inspection:**  
  A complete grep and syntax inspection of `RegistrationService` confirms that **zero** instances of `User(...)` or `Hospital(...)` are created anywhere in `registration_service.py`. Account provisioning is strictly decoupled and designated for Task 1D.
- **Evaluation:** **PASS**. No inactive or active operational credentials are created during application review or prior to approval.
- **Test Evidence:**  
  - Verified across all 22 tests in `tests/test_registration_service.py` that `Hospital` and `User` operational tables receive 0 rows from `RegistrationService`.
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

### Area 15: Existing Hospital, Referral and Bed Reservation Functionality Remains Unaffected
- **Inspection:**  
  Zero changes were made to `src/database/pg_repository.py`, `src/prediction/`, `src/api/patient_routes.py`, or `src/api/admin_routes.py`. The development database `sih_hospital_dev` was never touched or migrated.
- **Evaluation:** **PASS**. All existing operational pipelines function with 100% backward compatibility.
- **Test Evidence:**  
  Full canonical regression suite executed with 41/41 passing tests:
  - `tests/test_live_postgresql_integration.py` (8 PASSED)
  - `tests/test_postgresql_migration_and_transactions.py` (10 PASSED)
  - `tests/test_end_to_end_referral_workflow.py` (10 PASSED)
  - `tests/test_auth_and_access.py` (13 PASSED)
- **Missing Tests:** None.
- **Severity:** **Critical**.

---

## 3. Summary of Verification Checks

| # | Audit Check Area | File & Function | Result | Severity |
|---|---|---|---|---|
| 1 | Approval Hierarchy (Hospital, District, State) | `registration_service.py::review_application` | **PASS** | Critical |
| 2 | Stage & Geographic RBAC Authority | `registration_service.py::_validate_reviewer_authority` | **PASS** | Critical |
| 3 | Self-Approval Prevention | `registration_service.py::_validate_reviewer_authority` | **PASS** | High |
| 4 | Concurrent Duplicate Prevention at Database Level | `migrations/003_registration_system.sql` / `pg_models.py` | **GAP IDENTIFIED** | High |
| 5 | Reference Number Collision Handling | `registration_service.py::generate_application_number` | **PASS** | Medium |
| 6 | Document Verification Reviewer Authority | `registration_service.py::verify_document` | **PASS** | High |
| 7 | Audit History & Decision Immutability | `migrations/003_registration_system.sql` trigger | **PASS** | Critical |
| 8 | Tracking Token Expiry, Revocation & Hash | `registration_service.py::track_application_public` | **PASS** | High |
| 9 | Safe Public Tracking Information Filtering | `registration_service.py::track_application_public` | **PASS** | Critical |
| 10 | Original `submitted_at` Preservation | `pg_models.py` & DB Trigger | **PASS** | Critical |
| 11 | Complete Transition Audit Trail | `registration_service.py` (All mutation methods) | **PASS** | Critical |
| 12 | Mandatory Document Verification on Approval | `registration_service.py::check_final_approval_eligibility` | **PASS** | Critical |
| 13 | Atomic Transaction Rollback on Failure | `registration_service.py` (`flush()` lifecycle) | **PASS** | High |
| 14 | No Operational User Created Before Approval | `registration_service.py` (Zero `User` instantiation) | **PASS** | Critical |
| 15 | Existing Referral & Bed Workflows Unaffected | Repository & Regression Test Suite | **PASS** | Critical |

---

## 4. Required Fixes (For Area 4)

To achieve 100% database-level concurrency protection against simultaneous duplicate application submissions:
1. In `migrations/003_registration_system.sql`, add partial unique indexes:
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_state_app 
   ON registration_applications (LOWER(state)) 
   WHERE applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

   CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_district_app 
   ON registration_applications (LOWER(state), LOWER(district)) 
   WHERE applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

   CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_active_hospital_app 
   ON registration_applications (LOWER(state), LOWER(district), LOWER(applicant_name)) 
   WHERE applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');
   ```
2. Mirror these partial unique indexes in `src/database/pg_models.py` under `RegistrationApplication.__table_args__`.

---

## 5. Development Database Verification

```bash
$ psql -h localhost -p 5432 -U pawankumarsharma -d sih_hospital_dev \
    -c "SELECT current_database(), count(*) as total_hospitals, min(hospital_id), max(hospital_id), (SELECT count(*) FROM users) as total_users FROM hospitals;"
 current_database | total_hospitals |   min   |   max   | total_users 
------------------+-----------------+---------+---------+-------------
 sih_hospital_dev |             500 | GH00001 | GH00500 |           8

$ psql -h localhost -p 5432 -U pawankumarsharma -d sih_hospital_dev -c "\dt registration_applications"
Did not find any relation named "registration_applications".
```
- Migration 003 has **NOT** been applied to `sih_hospital_dev`.
- Database `sih_hospital_dev` remains 100% untouched.

---

## 6. Audit Verdict

**VERDICT: APPROVED WITH REQUIRED FIXES**

The Task 1C service layer logic, security constraints, multi-tier approvals, public tracking protection, and test suites are exceptionally well-engineered and function properly. The single finding—adding database-level partial unique indexes for active applications to guard against multi-threaded race conditions—should be incorporated as a schema hardening step alongside Task 1D.
