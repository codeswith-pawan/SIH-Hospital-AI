# SIH HOSPITAL AI — PHASE 4 DISCOVERY, ARCHITECTURE AUDIT & IMPLEMENTATION ROADMAP

**Document Version:** 1.0.0  
**Status:** Audit Complete & Approved for Implementation Planning  
**Target Repository:** `SIH_Hospital_AI` (`~/Desktop/SIH_Hospital_AI`)  
**Scope:** Architecture Discovery, Data Silo Audit, 9-Journey Workflow Analysis, Unified PostgreSQL Redesign, and Implementation Roadmap  

---

## 1. Executive Summary

### 1.1 State of the System Following Phases 1, 2, and 3
Over Phases 1, 2, and 3, the Smart India Hackathon (SIH) Hospital AI platform achieved major enterprise milestones:
- **Phase 1:** Built a robust, production-grade PostgreSQL registration schema (`hospital_registration_applications`, `hospital_verification_documents`, `hospital_registration_audit_log`, `application_status_history`), a transactional state machine, RBAC permissions, and comprehensive regression suites.
- **Phase 2 (2A–2D):** Delivered a public-facing multi-step hospital registration wizard, government reviewer portals across District, State, and Central administrative tiers, secure document review, multi-channel OTP verification, account provisioning, and password reset flows with 20/20 passing Playwright end-to-end tests.
- **Phase 3:** Completed containerized production deployment infrastructure (`Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.prod.yml`), an asynchronous background transactional outbox worker (`outbox_worker.py`), Brevo SMTP email routing, structured JSON observability, and robust backup/recovery automation.

### 1.2 Primary Goals of Phase 4
While the registration, governance, and deployment layers are production-ready, this architectural discovery reveals a fundamental systemic schism in the operational hospital and clinical modules. 

The primary objective of **Phase 4** is to **bridge the operational divide**:
1. **Eliminate Multi-Engine Data Silos:** Transition operational bed inventory, reservations, referrals, patient admissions, and administrative overviews from fragmented JSON files (`data/bed_inventory.json`) and legacy SQLite (`hospital_system.db`) to the unified, transactional PostgreSQL database (`sih_hospital_prod` / `sih_hospital_dev`) backed by Redis caching.
2. **Resolve the New Hospital 404 Defect:** Ensure that newly approved and provisioned hospitals automatically initialize bed inventories and can immediately manage operational capacity, receive referrals, and access their dashboard without HTTP 404 crashes.
3. **Operationalize Hospital Bed Management:** Provide hospital administrators with live CRUD capabilities to allocate, update, reassign, and track beds (ICU, Ventilator, Oxygen, General) in real time.
4. **Synchronize Clinical Patient Lifecycle:** Connect patient admission, inpatient monitoring, bed occupancy, transfer, and discharge directly into PostgreSQL transactional models with real-time UI synchronization.
5. **Harmonize Government Analytics:** Power District, State, and Central executive dashboards directly from PostgreSQL aggregate queries, replacing unindexed JSON scans.

---

## 2. Existing Architecture & Component Inventory

### 2.1 Component & Layer Mapping

| Layer | Component | File Path / Location | Current Underlying Data Store |
| :--- | :--- | :--- | :--- |
| **Frontend** | Hospital Dashboard | `frontend/components/HospitalDashboard.tsx` | REST API (`/hospitals/{id}/inventory`, `/patients/hospital/{id}`) |
| | District Admin Portal | `frontend/components/DistrictDashboard.tsx` | REST API (`/admin/district/overview`) |
| | State Admin Portal | `frontend/components/StateDashboard.tsx` | REST API (`/admin/state/overview`) |
| | Central Admin Portal | `frontend/components/CentralDashboard.tsx` | REST API (`/admin/central/overview`) |
| | Reviewer Portal | `frontend/app/reviewer/page.tsx` | REST API (`/registration/reviewer/*`) |
| | Registration Wizard | `frontend/app/register/page.tsx` | REST API (`/registration/apply`) |
| **Backend API** | Main Application | `src/api/main.py` | PostgreSQL (`db_manager.py`) + JSON (`reservation_store.py`) |
| | Registration Router | `src/api/registration_routes.py` | PostgreSQL (`pg_models.py`, `registration_service.py`) |
| | Admin Analytics Router | `src/api/admin_routes.py` | **SQLite** (`models.py`) + JSON (`referral_store.py`) |
| | Patient Clinical Router | `src/api/patient_routes.py` | **SQLite** (`models.py`, `patient_service.py`) |
| **Auth & RBAC** | Auth Store & JWT | `src/auth/auth_store.py`, `jwt_utils.py` | PostgreSQL `users`, `roles`, `user_roles` |
| | Jurisdiction Guard | `src/auth/authorization.py` | PostgreSQL `hospitals` (with SQLite fallback) |
| **Operational Services** | Account Provisioning | `src/services/account_provisioning_service.py` | PostgreSQL `hospitals`, `users`, `user_roles` |
| | Bed Reservation Service | `src/prediction/bed_reservation.py` | **JSON file** (`data/bed_inventory.json`) |
| | Referral Store | `src/prediction/referral_store.py` | **JSON file** (`data/active_referrals.json`) |
| | Notification Store | `src/prediction/notification_store.py` | **JSON file** (`data/notifications.json`) |
| | PG Repository | `src/database/pg_repository.py` | PostgreSQL `hospitals`, `beds`, `referrals`, `notifications` |
| **Background & DB** | Outbox Worker | `src/workers/outbox_worker.py` | PostgreSQL `email_outbox` |
| | Database Engine | `src/database/db_manager.py` | PostgreSQL Connection Pool (SQLAlchemy) |
| | Legacy SQLite Engine | `src/database/database.py` | SQLite (`data/hospital_system.db`) |

---

## 3. Current Feature Completeness Matrix

| Domain | Feature | Status | Limitations / Architecture Disconnect |
| :--- | :--- | :---: | :--- |
| **Onboarding** | Public Registration Wizard | ✅ COMPLETE | Multi-step validation, document upload, verification OTP |
| | 3-Tier Review Workflow | ✅ COMPLETE | District -> State -> Central review with atomic state audit log |
| | Account Provisioning | ✅ COMPLETE | Provisions PostgreSQL `Hospital` and `User` records |
| | Password Activation | ✅ COMPLETE | Secure tokenized activation and reset flows |
| **Hospital Operations** | Dashboard Login | ✅ COMPLETE | JWT-based authentication with role verification |
| | Bed Inventory View | ⚠️ PARTIAL | **CRITICAL BUG:** Fails with HTTP 404 for newly provisioned hospitals because backend reads from `bed_inventory.json`, not PostgreSQL |
| | Bed Inventory Updates | ❌ MISSING | Read-only UI; no backend endpoints exist for hospital admins to update bed counts, oxygen capacity, or ventilator status |
| | Inpatient Patient List | ⚠️ FRAGMENTED | Reads from SQLite `patient_system.db` via `patient_routes.py`, disconnected from PostgreSQL bed assignments |
| | Referral Receipt & Triage | ⚠️ FRAGMENTED | Endpoints in `main.py` update `active_referrals.json` rather than PostgreSQL `referrals` table |
| | Notifications System | ⚠️ FRAGMENTED | UI fetches `/notifications` which reads `notifications.json`, ignoring PostgreSQL `notifications` table |
| **Administrative Portals** | District Overview | ⚠️ FRAGMENTED | Queries SQLite `Hospital` table and JSON bed files; newly registered hospitals in PostgreSQL are invisible |
| | State Overview | ⚠️ FRAGMENTED | Queries SQLite `Hospital` table; lacks live PostgreSQL telemetry |
| | Central Overview | ⚠️ FRAGMENTED | National KPIs calculated by scanning SQLite records |
| **Infrastructure** | Asynchronous Outbox | ✅ COMPLETE | Transactional outbox worker processing Brevo SMTP emails |
| | SRE Observability | ✅ COMPLETE | Structured logging, correlation IDs, Prometheus metrics |
| | Docker Deployment | ✅ COMPLETE | Multi-stage Docker Compose with Redis & PostgreSQL |

---

## 4. End-to-End Workflow Audit & Findings (The 9 Core Journeys)

### Journey 1: New Hospital Registration & Multi-Tier Review
- **Execution Path:** `POST /registration/apply` -> Reviewer Portal -> `POST /registration/reviewer/applications/{id}/approve` (District, State, Central).
- **Audit Finding:** **PASS.** The registration workflow operates cleanly against PostgreSQL tables `hospital_registration_applications` and `hospital_verification_documents`. State machine transitions are atomic, recorded in `application_status_history` and `hospital_registration_audit_log`.

### Journey 2: Hospital Provisioning, Activation & First Login
- **Execution Path:** Central approval triggers `account_provisioning_service.py:_provision_hospital_admin()` -> outbox activation email -> `POST /registration/activate` -> `POST /token` -> `GET /hospitals/{hospital_id}/inventory`.
- **Audit Finding:** **FAIL (The 404 Inventory Bug).** 
  - `_provision_hospital_admin` creates a row in PostgreSQL `Hospital` (e.g. `GH00521`).
  - It creates **zero** records in the PostgreSQL `beds` table and **zero** entries in `data/bed_inventory.json`.
  - Upon logging in, `HospitalDashboard.tsx` requests `GET /hospitals/{hospital_id}/inventory`.
  - In `src/api/main.py:1087`, `get_hospital_dashboard_inventory()` imports `get_hospital_inventory()` from `src/prediction/reservation_store.py`, which reads exclusively from `data/bed_inventory.json`.
  - Because `GH00521` does not exist in `data/bed_inventory.json`, the endpoint raises `HTTPException(status_code=404, detail="Hospital not found in bed inventory")`. The user receives a blank or broken dashboard on first login.

### Journey 3: Hospital Live Bed & Resource Management
- **Execution Path:** Hospital admin attempts to update available ICU beds, report an oxygen generator failure, or adjust emergency capacity.
- **Audit Finding:** **FAIL.** 
  - Neither `src/api/main.py` nor `src/api/admin_routes.py` contains endpoints allowing hospital staff to update total or available beds.
  - The UI component `HospitalDashboard.tsx` displays beds as static cards with no "Edit Inventory" or "Adjust Bed State" action.
  - Bed modifications only occur as side-effects of reservations in the JSON store.

### Journey 4: Referral Generation, AI Allocation & Hospital Triage
- **Execution Path:** Doctor submits patient transfer request -> AI allocation engine ranks nearest hospitals -> Target hospital receives referral.
- **Audit Finding:** **SPLIT DATA PATH.**
  - `src/database/pg_repository.py` contains production-grade methods: `create_referral()`, `atomic_accept_and_reserve()`, and `atomic_transition_lifecycle()`.
  - However, `src/api/main.py` lines 689–1035 (`reserve_bed_api`, `occupy_bed_api`, `confirm_reservation_api`, `discharge_patient_api`) still execute legacy JSON operations via `src/prediction/bed_reservation.py`.
  - Any referral initiated via legacy routes updates `data/active_referrals.json` and does not persist in PostgreSQL `referrals`.

### Journey 5: Bed Reservation & Admission Transition
- **Execution Path:** `POST /reservation/reserve` -> `POST /reservation/occupy` -> `POST /reservation/confirm`.
- **Audit Finding:** **VULNERABLE TO RACE CONDITIONS.**
  - Because reservations modify `data/bed_inventory.json` with file-level mutex locks (`threading.Lock`), they cannot scale across multiple Uvicorn workers in Docker production (as configured with 2 workers in `docker-compose.prod.yml`).
  - Workers do not share memory locks, creating write collision risks under concurrent reservation requests.

### Journey 6: Inpatient Clinical Care, Discharge & Bed De-allocation
- **Execution Path:** `GET /patients/hospital/{id}` -> `POST /patients/visits/{id}/discharge` -> Bed freed.
- **Audit Finding:** **DATA SILO DISCONNECT.**
  - `src/api/patient_routes.py` is mounted to serve patient data. It imports `from src.database.database import get_db` (`src/database/database.py`), which connects to a local **SQLite** file (`data/hospital_system.db`).
  - Discharging a patient in `patient_routes.py` updates SQLite `hospital_visits`, but does **not** de-allocate the bed in PostgreSQL or in `bed_inventory.json`.

### Journey 7: Notification Delivery & Alert Lifecycle
- **Execution Path:** Critical alert generated -> `GET /hospitals/{hospital_id}/notifications` -> `POST /notifications/{id}/read`.
- **Audit Finding:** **STORE MISMATCH.**
  - In `src/api/main.py:1728-1763`, notifications are read and written using `src.prediction.notification_store` (`data/notifications.json`).
  - The PostgreSQL `notifications` table (defined in `pg_models.py:Notification`) remains empty and unutilized in live API calls.

### Journey 8: District, State, and Central Administrative Oversight
- **Execution Path:** District Magistrate logs in -> `GET /admin/district/overview`.
- **Audit Finding:** **CROSS-STORE BLIND SPOT.**
  - In `src/api/admin_routes.py:16`, `SessionLocal` is imported from `src.database.database` (SQLite).
  - The route queries `db.query(Hospital)` against SQLite, then merges live counts from `load_bed_inventory()` (JSON).
  - Hospitals registered and provisioned in PostgreSQL are completely invisible to District and State dashboards.

### Journey 9: System Reliability, Background Outbox & Recovery
- **Execution Path:** Database failover, worker failure, network partition.
- **Audit Finding:** **PASS (PostgreSQL) / FAIL (Operational State).**
  - PostgreSQL registration and outbox worker recover cleanly with transactional consistency.
  - Operational bed and referral states residing in flat JSON files are unrecoverable via database point-in-time recovery and risk corruption during ungraceful process termination.

---

## 5. Critical Architectural Gaps

```
+---------------------------------------------------------------------------------------------------+
|                                  THE 3-STORAGE SYSTEMIC SPLIT                                    |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ LAYER 1: PostgreSQL ]                   [ LAYER 2: Flat JSON Files ]   [ LAYER 3: SQLite DB ]  |
|  - Registration Applications               - data/bed_inventory.json      - data/hospital_system.db|
|  - Users, Credentials & Roles (RBAC)       - data/active_referrals.json   - Patient Records       |
|  - Verification Documents                  - data/notifications.json      - Hospital Visits       |
|  - Provisioned Hospitals (Hospital table)                                 - (Queried by Admin &   |
|  - Outbox Email Queue                                                     |   Patient Routes!)    |
|                                                                                                   |
|         |                                              ^                            ^             |
|         | Provisioned (GH00521)                        | Reads Inventory            | Reads       |
|         v                                              |                            | Patients    |
|  +--------------------+                                |                            |             |
|  | Registration Admin |                                |                            |             |
|  | Approves Hospital  |--- (No JSON entry created!) ---+                            |             |
|  +--------------------+                                |                            |             |
|                                                        v                            v             |
|  [ HOSPITAL FIRST LOGIN ] -----------------> GET /inventory (404!)       GET /patients (EMPTY!)   |
+---------------------------------------------------------------------------------------------------+
```

### Gap 1: The Dual-Storage Split (PostgreSQL vs JSON Store — The 404 Bug)
- **Root Cause:** Provisioning creates database records in PostgreSQL `hospitals`. The operational API (`/hospitals/{id}/inventory`) reads exclusively from `bed_inventory.json`.
- **Impact:** Newly activated hospitals experience a broken interface on their first session.

### Gap 2: The Multi-Engine Data Silo (SQLite in Production Routes)
- **Root Cause:** `src/api/admin_routes.py` and `src/api/patient_routes.py` maintain legacy imports from `src.database.database` (SQLite `hospital_system.db`).
- **Impact:** Administrative dashboards show stale SQLite seed data and omit newly onboarded healthcare facilities.

### Gap 3: Complete Absence of Bed & Resource Management APIs
- **Root Cause:** No endpoints exist for `POST /hospitals/{id}/beds`, `PUT /hospitals/{id}/beds/{category}`, or `PATCH /hospitals/{id}/resources`.
- **Impact:** Hospital admins cannot update capacity during emergencies, mass casualty events, or routine ward turnover.

### Gap 4: Clinical Inpatient Lifecycle Disconnection
- **Root Cause:** Inpatient admission (`HospitalVisit`) is stored in SQLite and disconnected from bed reservations (`bed_reservation.py`).
- **Impact:** A bed can be occupied in the clinical patient registry while showing as available in the referral AI allocator, or vice versa.

### Gap 5: Multi-Worker Race Hazards in Multi-Container Production
- **Root Cause:** In-memory threading locks in `reservation_store.py` cannot serialize requests across multiple Docker container instances or Uvicorn worker processes.
- **Impact:** Two patients can be concurrently assigned to the single remaining ICU bed at a facility.

---

## 6. Security, Isolation & Multi-Tenancy Audit

1. **Hospital Boundary Enforcement:**
   - In `src/auth/authorization.py`, `can_access_hospital` properly checks whether `current_user["hospital_id"] == target_hospital_id`. However, because it falls back to SQLite, an inconsistency between PostgreSQL and SQLite IDs could allow unauthorized access or false denials.
2. **Jurisdiction Isolation:**
   - District Admins must only see hospitals within their designated `district` and `state`. In `admin_routes.py:resolve_district_scope()`, scope resolution is well-structured, but relies on SQLite filtering. Migrating to PostgreSQL requires retaining strict SQL parameterized boundary queries: `WHERE district = :user_district AND state = :user_state`.
3. **Patient PII Protection:**
   - Patient names, phone numbers, and Aadhaar identifiers must never be leaked across hospitals. When returning referral lists, destination hospitals should only view relevant clinical metrics until referral acceptance.
4. **Token Security:**
   - Password reset and activation tokens are securely hashed with SHA-256 and single-use invalidation (`used_at IS NOT NULL`). This standard must be preserved during all Phase 4 extensions.

---

## 7. Proposed Phase 4 Target Architecture

```
+--------------------------------------------------------------------------------------------------+
|                                    PHASE 4 TARGET ARCHITECTURE                                    |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   +------------------------------------------------------------------------------------------+   |
|   |                                Next.js Frontend Dashboards                              |   |
|   |   - Hospital Dashboard  |  District Admin  |  State Admin  |  Central Command  | Reviewer|   |
|   +------------------------------------------------------------------------------------------+   |
|                                              |                                                   |
|                                    HTTPS / REST / SSE                                            |
|                                              v                                                   |
|   +------------------------------------------------------------------------------------------+   |
|   |                                FastAPI Unified Backend                                   |   |
|   |  [Auth / RBAC]     [Hospital Operations]     [Clinical & Beds]     [Admin Intelligence]  |   |
|   |  - JWT & Sessions   - Inventory CRUD         - Inpatient Admission - District Overview   |   |
|   |  - Scope Guard     - Real-Time Capacity      - Referral Engine     - State Overview      |   |
|   |  - Audit Logger    - Oxygen / Equipment      - Discharge Flow      - Central Command     |   |
|   +------------------------------------------------------------------------------------------+   |
|                         |                                                |                       |
|           SQLAlchemy (db_manager.py)                           Redis Client                      |
|                         v                                                v                       |
|   +----------------------------------------------+     +-------------------------------------+   |
|   |            PostgreSQL Database               |     |            Redis Cache              |   |
|   |  - hospitals (Master)                        |     |  - Hot Inventory Cache (Fast Reads) |   |
|   |  - beds (ICU, General, Oxygen, Vent)         |     |  - Atomic Locks (Redlock / Mutex)   |   |
|   |  - referrals (Full lifecycle state machine)  |     |  - Pub/Sub Real-Time Notifications  |   |
|   |  - patients & hospital_visits (Clinical)     |     +-------------------------------------+   |
|   |  - notifications & audit_logs                |                                               |
|   +----------------------------------------------+                                               |
|                                                                                                  |
|   * DEPRECATED & REMOVED: data/bed_inventory.json, data/active_referrals.json, SQLite DB         |
+--------------------------------------------------------------------------------------------------+
```

### Architectural Tenets of Phase 4
1. **Single Source of Truth:** PostgreSQL is the sole relational database. SQLite (`hospital_system.db`) and JSON state files are migrated and retired.
2. **Transaction Isolation:** All bed allocation, reservation, occupancy, and discharge events execute within atomic PostgreSQL transactions (`SELECT ... FOR UPDATE`) to prevent race conditions across distributed workers.
3. **Redis Real-Time Acceleration:** Operational bed counts are cached in Redis with key invalidation on transaction commit, enabling sub-millisecond dashboard telemetry.
4. **Zero Unprovisioned Hospitals:** Account provisioning automatically populates default bed quotas in the PostgreSQL `beds` table, immediately rendering the hospital operational.

---

## 8. Prioritized Implementation Roadmap

### Phase 4A: Unified Operational Hospital Inventory & Bed Management
*Focus: Eliminate the 404 bug, deprecate `bed_inventory.json`, and provide hospital inventory CRUD.*
1. **Inventory Schema & Provisioning Unification:**
   - Update `account_provisioning_service.py` to automatically seed `beds` records (General, ICU, Emergency, Ventilator) when an application is approved.
   - Seed existing provisioned hospitals into the PostgreSQL `beds` table if missing.
2. **PostgreSQL-Powered Inventory Endpoints:**
   - Rewrite `GET /hospitals/{hospital_id}/inventory` in `src/api/main.py` to query PostgreSQL `beds` and `hospitals` via `src/database/pg_repository.py`.
   - Implement `PUT /hospitals/{hospital_id}/inventory` allowing authorized hospital staff to update total/available bed counts and operational status.
   - Implement `PATCH /hospitals/{hospital_id}/resources` to update oxygen plant availability and ventilator counts.
3. **Frontend Bed Management UI:**
   - Enhance `HospitalDashboard.tsx` with an interactive "Update Inventory" modal and real-time capacity adjustments.

### Phase 4B: Clinical Inpatient & Referral Lifecycle Synchronization
*Focus: Retire SQLite, unify patient visits and referrals in PostgreSQL.*
1. **Patient & Inpatient Unification:**
   - Migrate `src/api/patient_routes.py` and `patient_service.py` to use `src.database.db_manager.get_db` and PostgreSQL `pg_models.Patient` and `pg_models.HospitalVisit`.
   - Synchronize bed occupancy: admitting a patient marks a bed occupied in PostgreSQL; discharging a patient frees the bed atomically.
2. **PostgreSQL Referral Lifecycle:**
   - Refactor `reserve_bed_api`, `occupy_bed_api`, and `discharge_patient_api` in `src/api/main.py` to route directly through `pg_repository.py`.
   - Deprecate `data/active_referrals.json`.

### Phase 4C: Government Jurisdiction Intelligence & Administrative Command
*Focus: Power District, State, and Central dashboards from live PostgreSQL aggregates.*
1. **Admin Route Migration:**
   - Refactor `src/api/admin_routes.py` to use PostgreSQL `get_db` from `db_manager.py`.
   - Replace JSON file scanning with fast PostgreSQL aggregate SQL queries (`COUNT`, `SUM`, `FILTER (WHERE status = 'OCCUPIED')`).
2. **Real-Time Jurisdiction Analytics:**
   - Display newly registered and approved hospitals immediately in District, State, and Central executive tables.
   - Expose bottleneck analytics: transfer wait times, bed saturation rates, and inter-district referral spikes.

### Phase 4D: Real-Time Notifications, SRE Hardening & Live Telemetry
*Focus: Live event streaming and production resilience.*
1. **Unified Notification Hub:**
   - Refactor `GET /hospitals/{hospital_id}/notifications` and mark-read routes to read/write PostgreSQL `notifications`.
   - Implement Server-Sent Events (SSE) or WebSocket push for incoming referral alerts.
2. **Regression & E2E Validation:**
   - Maintain pass rate across the 20 existing Playwright tests.
   - Author new Playwright E2E tests for hospital bed inventory updates, patient admission, and referral lifecycle.

---

## 9. API & Database Schema Impact Analysis

### 9.1 Database Schema Extensions (PostgreSQL)

```sql
-- Migration 004: Operational Bed Inventory & Equipment Attributes
ALTER TABLE beds 
  ADD COLUMN IF NOT EXISTS total_capacity INTEGER NOT NULL DEFAULT 10,
  ADD COLUMN IF NOT EXISTS occupied_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reserved_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS available_count INTEGER GENERATED ALWAYS AS (total_capacity - occupied_count - reserved_count) STORED;

-- Add Resource & Facility telemetry to hospitals table
ALTER TABLE hospitals
  ADD COLUMN IF NOT EXISTS oxygen_plant_operational BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS oxygen_cylinders_available INTEGER NOT NULL DEFAULT 20,
  ADD COLUMN IF NOT EXISTS ventilators_total INTEGER NOT NULL DEFAULT 5,
  ADD COLUMN IF NOT EXISTS ventilators_available INTEGER NOT NULL DEFAULT 5,
  ADD COLUMN IF NOT EXISTS last_inventory_update TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Indexing for sub-millisecond district and state aggregations
CREATE INDEX IF NOT EXISTS idx_hospitals_state_district ON hospitals(state, district);
CREATE INDEX IF NOT EXISTS idx_beds_hospital_type ON beds(hospital_id, bed_type);
```

### 9.2 API Endpoint Modifications & Additions

| Method | Endpoint | Description | Changes Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/hospitals/{id}/inventory` | Retrieve hospital bed & resource telemetry | Replace `reservation_store.py` with `pg_repository.py`. Return real data for newly provisioned hospitals. |
| `PUT` | `/hospitals/{id}/inventory` | Update capacity for a bed category | **NEW ENDPOINT.** Enforces `can_access_hospital` guard. Updates PostgreSQL `beds` atomically. |
| `PATCH` | `/hospitals/{id}/resources` | Update oxygen/ventilator telemetry | **NEW ENDPOINT.** Updates `hospitals` table. |
| `GET` | `/patients/hospital/{id}` | Retrieve admitted inpatients | Point from SQLite to PostgreSQL `patients` / `hospital_visits`. |
| `POST` | `/patients/admit` | Admit patient and assign bed | **NEW ENDPOINT.** Atomic transaction: creates visit and increments `beds.occupied_count`. |
| `POST` | `/patients/{id}/discharge` | Discharge patient and free bed | Atomic transaction: updates visit status and decrements `beds.occupied_count`. |
| `GET` | `/admin/district/overview` | District administrative analytics | Switch `SessionLocal` from SQLite to PostgreSQL `db_manager.py`. |
| `GET` | `/admin/state/overview` | State administrative analytics | Switch from SQLite to PostgreSQL. |
| `GET` | `/admin/central/overview` | National command analytics | Switch from SQLite to PostgreSQL. |

---

## 10. Frontend Impact & Component Refactoring

1. **`frontend/components/HospitalDashboard.tsx`:**
   - Replace read-only stat counters with an interactive "Manage Beds" drawer/modal.
   - Add state management for updating bed counts (`apiUpdateHospitalInventory`).
   - Add error boundary with clear feedback for network timeouts.
2. **`frontend/lib/api.ts`:**
   - Add typed API client functions:
     - `apiUpdateBedInventory(hospitalId, bedData)`
     - `apiUpdateResources(hospitalId, resourceData)`
     - `apiAdmitPatient(patientData)`
     - `apiDischargePatient(visitId)`
3. **`frontend/components/DistrictDashboard.tsx` & `StateDashboard.tsx`:**
   - Display real-time badge indicating whether an affiliated hospital is verified/active in PostgreSQL.
   - Provide direct links to newly registered facilities.

---

## 11. Testing & Acceptance Criteria

### 11.1 Test Suite Expansion
1. **Unit & Integration Tests (`tests/test_operational_inventory.py`):**
   - Verify `_provision_hospital_admin()` automatically seeds initial beds in PostgreSQL.
   - Verify `GET /hospitals/{new_id}/inventory` returns HTTP 200 with default capacity immediately after activation.
   - Verify `PUT /hospitals/{id}/inventory` rejects negative values and enforces role authorization.
   - Verify concurrent reservation requests serialize correctly without overselling capacity.
2. **Full Regression Safety:**
   - Verify all 349 passing backend tests continue passing.
   - Preserve known baseline inventory test expectation (GH00046: 15 available beds).
   - Ensure `sih_hospital_dev` remains pristine and untouched.
3. **Playwright End-to-End Tests (`frontend/e2e/phase4_inventory.spec.ts`):**
   - Complete full flow: Register hospital -> Approve at all 3 tiers -> Activate account -> Log in -> Open dashboard -> Verify inventory is displayed -> Update bed counts -> Refresh page and verify persistence.

---

## 12. Risks, Edge Cases & Mitigation Strategies

| Risk | Consequence | Mitigation Strategy |
| :--- | :--- | :--- |
| **Data Inconsistency during Migration** | Hospitals existing in SQLite but missing from PostgreSQL might disappear. | Run a safe, one-way idempotency migration script that syncs any missing historical records from SQLite to PostgreSQL prior to retirement. |
| **Concurrent Overselling of Beds** | Multiple referral transfers reserve the last available ICU bed simultaneously. | Use PostgreSQL row-level locks (`SELECT * FROM beds WHERE ... FOR UPDATE`) inside the reservation transaction. |
| **Accidental Modification of Dev DB** | `sih_hospital_dev` must never be touched or altered. | All tests and migrations run strictly against isolated test databases or Docker production containers (`sih_postgres_prod`), guarded by environment checks. |
| **Regression in Registration Flow** | Phase 4 changes could break existing Phase 1–3 onboarding. | Run `verify_phase2d_backend_workflows.py` and the 20-test Playwright suite before and after any Phase 4 code merge. |

---

## 13. Recommended First Implementation Task

### Recommendation: Phase 4A — Operational Inventory & Bed Provisioning Unification
**Target Task:** Resolve the New Hospital 404 Bug and unify `GET /hospitals/{id}/inventory` on PostgreSQL.

**Files & Components Involved:**
1. `src/services/account_provisioning_service.py`: Add automatic seeding of PostgreSQL `beds` records upon hospital approval.
2. `src/database/pg_repository.py`: Add `get_hospital_inventory_from_db()` and `update_hospital_bed_capacity()`.
3. `src/api/main.py`: Refactor `get_hospital_dashboard_inventory()` to use `pg_repository` instead of `src.prediction.reservation_store.py`.
4. `tests/test_operational_inventory.py`: Add automated tests verifying that a newly approved hospital has functional inventory without 404 errors.

---
*Roadmap formulated and approved for review. No code or database changes have been applied.*
