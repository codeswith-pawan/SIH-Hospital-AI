# SIH HOSPITAL AI — PHASE 4A IMPLEMENTATION REPORT
## Unified PostgreSQL Hospital Inventory & Bed Management

**Execution Date:** November 11, 2026  
**Environment:** macOS (Local Darwin), PostgreSQL 17, Next.js 16.3.0, FastAPI  
**Author:** AI Engineering & Pair Programming Agent  
**Status:** Implementation Complete & Independently Verified — Ready for Review  

---

## 1. Architecture Before and After

### 1.1 Architecture Before Phase 4A
Prior to Phase 4A, the platform operated under a fragmented three-tier data divide:
1. **PostgreSQL Layer:** Handled multi-tier hospital registration applications, document verifications, role-based access control (RBAC), and user account provisioning.
2. **Flat File JSON Store (`data/bed_inventory.json`):** Operational bed capacity was stored in and queried from legacy flat JSON files via `src/prediction/reservation_store.py`.
3. **The 404 Disconnect:** When Central Review approved a hospital and `account_provisioning_service.py` provisioned its PostgreSQL records (`Hospital` and `User`), zero rows were created in the PostgreSQL `beds` table and zero records were inserted into `data/bed_inventory.json`.
4. **Dashboard Failure:** Upon logging in, `HospitalDashboard.tsx` called `GET /hospitals/{hospital_id}/inventory`. In `src/api/main.py:1087`, the endpoint read strictly from `bed_inventory.json`, raising an HTTP 404 error and crashing the operational dashboard on first login.
5. **No Mutation Capabilities:** Hospital administrators had no REST API or UI controls to adjust bed capacity, allocate triage bays, or update critical life-support readiness (oxygen plants, ventilators, ambulances).

```
[BEFORE PHASE 4A]
Registration Approval (PostgreSQL) 
       |
       v Creates Hospital & User in PG (No JSON / No physical beds)
Hospital First Login -> GET /hospitals/{id}/inventory -> Reads data/bed_inventory.json -> HTTP 404 NOT FOUND (Broken Dashboard)
```

### 1.2 Target Architecture After Phase 4A
Phase 4A establishes PostgreSQL as the authoritative single source of truth for all operational hospital bed inventories:
1. **Transactional Inventory Seeding:** Account provisioning automatically initializes physical PostgreSQL `beds` records (`GENERAL`, `ICU`, `EMERGENCY`) within the same database transaction.
2. **Unified PostgreSQL Endpoint:** `GET /hospitals/{hospital_id}/inventory` now reads authoritatively from PostgreSQL via `PgReferralRepository`. Newly approved facilities immediately return HTTP 200 with full capacity metrics.
3. **Graceful Fallback:** A non-intrusive fallback is maintained for legacy unit test mocks that only exist in `data/bed_inventory.json`, preventing regressions in older test suites.
4. **Operational CRUD & Row-Level Locking:** Added `PUT /hospitals/{hospital_id}/inventory` and `PATCH /hospitals/{hospital_id}/resources` with `SELECT ... FOR UPDATE` row locks to guarantee zero overbooking and concurrency safety across distributed Uvicorn workers.
5. **Interactive Frontend Management:** `HospitalDashboard.tsx` now renders category-wise statistics (General, ICU, Emergency) and facility support readiness (Oxygen, Ventilator, Ambulance, Blood Bank, 24x7 Emergency) with an interactive "Update Capacity & Resources" modal.

```
[AFTER PHASE 4A]
Registration Approval (PostgreSQL)
       |
       v Atomically provisions Hospital, User, AND PostgreSQL beds (GEN-*, ICU-*, EMG-*)
Hospital First Login -> GET /hospitals/{id}/inventory -> Reads PostgreSQL beds & hospital -> HTTP 200 OK (Functional Dashboard)
       |
       +---> PUT /hospitals/{id}/inventory (SELECT ... FOR UPDATE capacity adjustment)
       +---> PATCH /hospitals/{id}/resources (Oxygen, Ventilator, Ambulance live status)
```

---

## 2. Files Created and Modified

| File Path | Action | Description |
| :--- | :---: | :--- |
| `src/database/pg_repository.py` | Modified | Added `get_hospital_inventory()`, `initialize_default_inventory()`, `update_hospital_bed_capacity()`, and `update_hospital_resources()` with atomic row locks. |
| `src/services/account_provisioning_service.py` | Modified | Integrated operational inventory initialization into `_provision_hospital_admin()` using application profile quotas. |
| `src/api/schemas.py` | Modified | Added `BedCapacityUpdateItem`, `HospitalInventoryUpdateRequest`, and `HospitalResourcesUpdateRequest` Pydantic models. |
| `src/api/main.py` | Modified | Refactored `GET /hospitals/{hospital_id}/inventory` to query PostgreSQL. Implemented `PUT /hospitals/{hospital_id}/inventory` and `PATCH /hospitals/{hospital_id}/resources`. |
| `frontend/lib/types.ts` | Modified | Extended `BedInventory` with emergency ward metrics, overall capacity totals, facility resource flags, and `BedCategoryStats`. |
| `frontend/lib/api.ts` | Modified | Added typed client functions `apiUpdateInventory()` and `apiUpdateResources()`. |
| `frontend/components/HospitalDashboard.tsx` | Modified | Enriched inventory matrix with 3 category cards (General, ICU, Emergency), facility equipment readiness indicators, and an interactive "Update Capacity & Resources" management modal. |
| `tests/test_operational_inventory.py` | Created | Comprehensive 14-test PostgreSQL integration suite covering provisioning, idempotent seeding, capacity updates, negative capacity rejection, overbooking prevention, cross-hospital access denial, and concurrency safety. |

---

## 3. Database Model and Migration Changes

### 3.1 Schema Evaluation
Inspection of the PostgreSQL database schema confirmed that the existing tables, columns, check constraints, and relationships already fully support operational bed management:
- `beds`: Contains `id`, `hospital_id`, `bed_number`, `bed_type` (`GENERAL`, `ICU`, `EMERGENCY`), `status` (`AVAILABLE`, `RESERVED`, `OCCUPIED`, `MAINTENANCE`), with unique constraint `uq_hospital_bed (hospital_id, bed_number)` and index `idx_beds_lookup`.
- `hospitals`: Contains `total_beds`, `occupied_beds`, `available_beds`, `icu_beds`, `available_icu_beds`, `emergency_beds`, `available_emergency_beds`, `oxygen_support`, `ventilator`, `ambulance`, `blood_bank`, `emergency_24x7`.
- `audit_logs`: Records all administrative capacity adjustments and resource modifications.

### 3.2 Migration Decision
Because the existing PostgreSQL models and database tables already provide all required fields and constraints, **no schema modification or migration was required**, adhering strictly to Safety Rule 11 ("Do not invent database columns without verifying the actual schema") and Rule 4 ("Never run migrations or write operations against sih_hospital_dev").

---

## 4. New and Modified API Endpoints

### 4.1 `GET /hospitals/{hospital_id}/inventory` (Refactored)
- **Authorization:** `can_access_hospital(current_user, hospital_id)`.
  - `HOSPITAL`: Strictly authorized only for its own `hospital_id`.
  - `DISTRICT_ADMIN`: Authorized for facilities within user's district and state.
  - `STATE_ADMIN`: Authorized for facilities within user's state.
  - `CENTRAL_ADMIN`: Global nationwide authorization.
- **Execution:**
  1. Executes `repo.get_hospital_inventory(hospital_id)` against PostgreSQL.
  2. Aggregates individual `Bed` records (`GENERAL`, `ICU`, `EMERGENCY`) and status (`AVAILABLE`, `RESERVED`, `OCCUPIED`).
  3. If physical beds are not yet seeded, calculates counts from `Hospital` aggregate columns.
  4. Returns `is_configured: False` for unconfigured facilities without throwing 404.
  5. Falls back to `bed_inventory.json` only if hospital is absent from PostgreSQL (for legacy test fixtures).
- **HTTP Status Codes:**
  - `200 OK`: Successful retrieval.
  - `403 Forbidden`: Cross-hospital or cross-jurisdiction access attempted.
  - `404 Not Found`: Hospital does not exist in any store.

### 4.2 `PUT /hospitals/{hospital_id}/inventory` (New)
- **Description:** Atomically updates total bed capacity for specified bed categories.
- **Payload:**
  ```json
  {
    "bed_type": "ICU",
    "total_capacity": 15
  }
  ```
  *or bulk:*
  ```json
  {
    "capacities": [
      {"bed_type": "GENERAL", "total_capacity": 60},
      {"bed_type": "ICU", "total_capacity": 15},
      {"bed_type": "EMERGENCY", "total_capacity": 10}
    ]
  }
  ```
- **Validation & Invariants:**
  - `bed_type` must be one of `GENERAL`, `ICU`, `EMERGENCY`.
  - `total_capacity >= 0`.
  - Invariant Check: `total_capacity >= occupied_beds + reserved_beds`. If target capacity is less than currently active beds, raises `HTTP 422 Unprocessable Content`.
- **Concurrency Safety:** Uses PostgreSQL `SELECT ... FOR UPDATE` on both `Hospital` and `Bed` rows.
- **Audit Logging:** Inserts record into `audit_logs` capturing previous and new capacity states.

### 4.3 `PATCH /hospitals/{hospital_id}/resources` (New)
- **Description:** Updates hospital facility readiness and equipment telemetry.
- **Payload:**
  ```json
  {
    "oxygen_support": "Yes",
    "ventilator": "Yes",
    "ambulance": "Yes",
    "blood_bank": "Yes",
    "emergency_24x7": "Yes"
  }
  ```
- **Validation:** Normalized to `"Yes"` or `"No"`. Rejects invalid values with `HTTP 422`.
- **Audit Logging:** Inserts record into `audit_logs` with actor identity and field diffs.

---

## 5. Frontend Changes

### 5.1 `frontend/lib/types.ts`
- Added `BedCategoryStats` (`total`, `available`, `reserved`, `occupied`, `maintenance`).
- Enriched `BedInventory` with category counters, emergency bay stats, and facility equipment flags (`oxygen_support`, `ventilator`, `ambulance`, `blood_bank`, `emergency_24x7`).

### 5.2 `frontend/lib/api.ts`
- Added `apiUpdateInventory(hospitalId, data)` calling `PUT /hospitals/{hospital_id}/inventory`.
- Added `apiUpdateResources(hospitalId, resources)` calling `PATCH /hospitals/{hospital_id}/resources`.

### 5.3 `frontend/components/HospitalDashboard.tsx`
- **Matrix Expansion:** Upgraded Tab 3 to render 3 category cards:
  1. *General Inpatient Ward* (Available, Reserved, Total).
  2. *Intensive Care Unit (ICU)* (Available, Reserved, Total).
  3. *Emergency & Trauma Unit* (Available, Reserved, Total).
- **Telemetry Card:** Added *Critical Support Equipment & Readiness* section rendering real-time status badges for Oxygen Plant, Ventilator Units, Ambulances, Blood Bank, and 24x7 Emergency Services.
- **Action Controls:** Added "Update Capacity & Resources" button in the matrix header.
- **Management Modal:**
  - Inputs for General, ICU, and Emergency bay target capacities.
  - Interactive validation displaying currently committed beds (`occupied + reserved`) to prevent reducing capacity below active occupancy.
  - Dropdown toggles for critical facility readiness attributes.
  - Real-time feedback displaying inline loading indicators, descriptive error messages (HTTP 403, 404, 422), and success alerts.
  - Automatically reloads live inventory from PostgreSQL upon submission.

---

## 6. Inventory Initialization Behavior

When a hospital registration application is approved by Central Review:
1. `account_provisioning_service.py:_provision_hospital_admin()` extracts bed quotas from `profile_data`.
2. Reads `total_beds`, `icu_beds`, and `emergency_beds` (with fallback to configurable environment defaults if omitted).
3. Calculates `GENERAL` capacity as `total_beds - icu_beds - emergency_beds`.
4. Invokes `repo.initialize_default_inventory()` within the same database transaction.
5. Populates physical `Bed` records (`GEN-001...`, `ICU-001...`, `EMG-001...`) with status `'AVAILABLE'`.
6. Sets initial `Hospital` aggregate columns in sync with physical bed counts.
7. Idempotency Guard: If called repeatedly on an existing hospital, it detects existing physical beds and never generates duplicates or alters occupied/reserved counters.

---

## 7. Authorization and Concurrency Safeguards

1. **Strict Hospital Isolation:** Hospital administrators cannot read or modify inventory belonging to any other facility (`current_user["hospital_id"] == target_hospital_id`). Cross-hospital access returns `HTTP 403 Forbidden`.
2. **Jurisdiction Boundary Enforcement:** District and State reviewers can view facilities only within their assigned state and district.
3. **Pessimistic Row Locking (`SELECT ... FOR UPDATE`):** All capacity modifications acquire row-level locks on the target `Hospital` and `Bed` rows before evaluating capacity invariants, preventing race conditions when concurrent requests attempt to prune or allocate beds across multiple Uvicorn worker processes.
4. **Audit Immutability:** Every capacity initialization, bed reduction, bed expansion, and resource update persists an immutable record in `audit_logs` tracking `performed_by`, `entity_type`, `action`, `previous_state`, and `new_state`.

---

## 8. Tests Executed and Actual Results

### 8.1 Focused Operational Inventory Suite (`tests/test_operational_inventory.py`)
Ran all 14 tests against the isolated test database `sih_hospital_phase1_run_test`:

| Test Name | Result | Verification Scope |
| :--- | :---: | :--- |
| `test_newly_provisioned_hospital_receives_inventory_records` | **PASSED** | Confirms newly approved hospital automatically receives physical `Bed` records in PostgreSQL. |
| `test_repeated_provisioning_does_not_create_duplicate_records` | **PASSED** | Confirms repeated provisioning is idempotent and creates zero duplicate beds. |
| `test_existing_hospital_inventory_remains_unchanged` | **PASSED** | Confirms existing facilities retain all capacity and occupied counters during re-initialization. |
| `test_inventory_get_returns_http_200_for_correctly_provisioned_hospital` | **PASSED** | Confirms `GET /hospitals/{id}/inventory` returns HTTP 200 with full categories. |
| `test_unconfigured_inventory_returns_controlled_response` | **PASSED** | Confirms unconfigured facilities return HTTP 200 with `is_configured: False` instead of 404. |
| `test_capacity_updates_succeed_with_valid_data` | **PASSED** | Confirms `PUT /hospitals/{id}/inventory` expands ICU capacity to 8 and persists in DB. |
| `test_negative_capacity_is_rejected` | **PASSED** | Confirms negative capacity values are rejected with HTTP 422. |
| `test_capacity_below_occupied_plus_reserved_is_rejected` | **PASSED** | Confirms reducing capacity below committed beds raises HTTP 422 with descriptive detail. |
| `test_cross_hospital_access_is_denied` | **PASSED** | Confirms Admin A cannot read or modify Admin B's inventory (HTTP 403). |
| `test_unauthorized_roles_cannot_update_inventory` | **PASSED** | Confirms Reviewer and unauthorized roles cannot modify bed capacity (HTTP 403). |
| `test_concurrent_capacity_updates_do_not_corrupt_inventory` | **PASSED** | Multithreaded execution confirms row locks prevent race conditions and duplicate bed numbers. |
| `test_existing_reservation_tests_continue_passing` | **PASSED** | Confirms backward compatibility with legacy `bed_reservation.py`. |
| `test_existing_hospital_dashboard_functionality_remains_intact` | **PASSED** | Confirms top-level response contracts match `HospitalDashboard.tsx` expectations. |
| `test_resources_patch_endpoint_updates_postgresql` | **PASSED** | Confirms `PATCH /hospitals/{id}/resources` updates equipment telemetry in PostgreSQL. |

**Result:** `14 passed in 0.96s`

### 8.2 Registration & Account Provisioning Regression Suites
Executed regression suites covering registration, document storage, provisioning, and reviewer workflows:
- `tests/test_document_storage_and_provisioning.py` (22 tests) -> **PASSED**
- `tests/test_registration_api.py` (22 tests) -> **PASSED**
- `tests/test_registration_service.py` (30 tests) -> **PASSED**
- `tests/test_phase2d_reviewer_and_lifecycle.py` (15 tests) -> **PASSED**

**Result:** `89 passed in 4.48s`

### 8.3 Referral & Reservation Regression Suites
- `tests/test_referral_and_bed_lifecycle.py` (15 tests) -> **PASSED**
- `tests/test_end_to_end_referral_workflow.py` (10 tests) -> **PASSED**
- `tests/test_referral_engine.py` -> **PASSED**
- `tests/test_referral_rules.py` -> **PASSED**

**Result:** `25 passed in 11.02s`

### 8.4 Full Backend Test Suite
Executed all test files across the entire `tests/` directory:
- **Total Tests Collected:** 365
- **Passed:** **363**
- **Failed (Documented Baseline):** **2** (`test_inventory_counters_truth_consistency` in `test_ui_defects_and_serialization.py` and its duplicate, where test expects 16 available ICU beds on GH00046 while actual inventory has 15).
- **Execution Time:** 35.50s

### 8.5 Frontend Build, TypeScript & Lint
- `next build`: **Passed** (Compiled successfully in 322ms, TypeScript finished in 1841ms, static pages generated: 15/15).
- `next lint` (ESLint): **Passed with 0 errors** (55 non-fatal stylistic warnings).

### 8.6 Playwright End-to-End Tests
Executed the complete desktop and mobile Playwright browser automation suite (`frontend/e2e/phase2d_browser_workflows.spec.ts`):
- Desktop workflows (10 tests): **10/10 PASSED**
- Mobile viewport workflows (10 tests): **10/10 PASSED**
- **Total:** **20 passed in 54.3s**

---

## 9. Known Limitations

1. **GH00046 Baseline Test Failure:** The pre-existing test in `test_ui_defects_and_serialization.py` expects 16 available ICU beds on `GH00046` whereas `bed_inventory.json` defines 15 available and 7 reserved. In strict accordance with Project Rule 9, this test assertion was preserved unmodified.
2. **Legacy Flat JSON Store Coexistence:** While `GET /hospitals/{id}/inventory` and capacity management APIs now run authoritatively on PostgreSQL, the legacy file `data/bed_inventory.json` is preserved on disk for backward compatibility with older offline unit tests.

---

## 10. Remaining Phase 4B Dependencies

The following tasks are explicitly scoped for **Phase 4B** and were intentionally not implemented in Phase 4A to maintain modularity:
1. **Clinical Inpatient Synchronization:** Migration of `src/api/patient_routes.py` from SQLite (`hospital_system.db`) to PostgreSQL `patients` and `hospital_visits` tables.
2. **Referral State Machine Redirection:** Directing `reserve_bed_api` and `occupy_bed_api` in `src/api/main.py` through `PgReferralRepository.atomic_accept_and_reserve()` instead of `bed_reservation.py`.
3. **Automatic Bed Release on Discharge:** Linking patient discharge events directly to atomic bed de-allocation in PostgreSQL.

---

## 11. Git and Database Safety Verification

1. **`sih_hospital_dev` Invariant:** Verified via direct read-only query that `sih_hospital_dev` remains 100% untouched:
   - `hospitals`: 500
   - `users`: 8
   - `roles`: 4
   - `hospital_registration_applications`: `None` (table absent)
2. **Git Stash Preservation:** Verified `stash@{0}` (`On master: Backup before GitHub repository synchronization`) is intact.
3. **No Unsanctioned Git Commands:** Zero commits, zero pushes, zero checkouts, and zero branch resets were executed.

---
*Phase 4A is complete, verified, and ready for acceptance review. Phase 4B has not been started.*
