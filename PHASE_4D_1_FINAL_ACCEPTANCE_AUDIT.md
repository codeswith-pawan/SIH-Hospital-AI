# PHASE 4D-1 — FINAL BUSINESS-RULE AND SAFETY ACCEPTANCE AUDIT
## Automated Bed Reservation Expiry Worker & Clinical Lifecycle Verification

**Audit Date:** 2026-11-11  
**Audited Repository:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Git Branch:** `master` (Commit `460af41`)  
**Git Stash Status:** `stash@{0}` intact  
**Protected Database (`sih_hospital_dev`):** Pristine & untouched (500 hospitals, 8 users verified)  
**Test Database (`sih_hospital_phase1_run_test`):** Migration 005 applied; live tests verified  
**Audit Scope:** Narrowly scoped, strictly read-only business-rule, concurrency, and safety acceptance audit of Phase 4D-1.  
**Audit Verdict:** **`ACCEPTED — PHASE 4D-1`**

---

## 1. Actual Business Workflow Trace: RESERVED → CONFIRMED → OCCUPIED

Inspection of the backend API routes, services, database models, and repository methods reveals the two operational pathways that drive bed states:

```
[ CLINICAL REFERRAL WORKFLOW ]
Incoming Transfer (PENDING)
       │
       ▼ (Destination Hospital Accepts)
ACCEPTED (Referral)  ──────►  RESERVED (BedReservation & Bed: temporary hold with expires_at)
       │
       ▼ (Ambulance Dispatched & En Route)
IN_TRANSIT (Referral) ─────►  RESERVED (Bed remains held while patient is in transit)
       │
       ▼ (Patient Arrives at Destination Facility)
ARRIVED (Referral)   ──────►  CONFIRMED (BedReservation: patient arrived, bed guaranteed)
       │
       ▼ (Patient Admitted to Bed / Clinical Treatment Begins)
TREATMENT_ACTIVE     ──────►  OCCUPIED (BedReservation & Bed: active admission)
       │
       ▼ (Discharge / Transfer / Death)
DISCHARGED           ──────►  RELEASED (Bed restored to AVAILABLE)


[ DIRECT / WALK-IN RESERVATION WORKFLOW ]
Walk-in / Direct Intake
       │
       ▼ (Bed Held)
RESERVED (BedReservation & Bed: temporary hold with expires_at)
       │
       ▼ (Patient Arrival Verified / Triage Verification)
CONFIRMED (BedReservation: guaranteed hold)
       │
       ▼ (Patient Admitted to Physical Bed)
OCCUPIED (BedReservation & Bed: occupied_beds incremented)
```

---

## 2. API Endpoints, Frontend Actions, Services & Repository Methods

| State Transition | API Endpoint(s) | Frontend Action & Component | Service Function | Repository Method |
| :--- | :--- | :--- | :--- | :--- |
| **AVAILABLE → RESERVED** | 1. `POST /referrals/{referral_id}/status/ACCEPTED`<br>2. `POST /reservation/{hospital_id}/{patient_id}/reserve` | • "Accept Referral" button on inbound transfer card in `HospitalDashboard.tsx`<br>• "Reserve Bed" action in inventory table | • `referral_store.update_referral_status`<br>• `bed_reservation.reserve_bed` | • `PgReferralRepository.atomic_accept_and_reserve`<br>• `PgReferralRepository.reserve_bed_direct` |
| **RESERVED → CONFIRMED** | 1. `POST /referrals/{referral_id}/status/ARRIVED`<br>2. `POST /reservation/{hospital_id}/{patient_id}/confirm` | • "Mark Patient Arrived" button in `HospitalDashboard.tsx`<br>• "Confirm Reservation" button in Bed Management table | • `referral_store.update_referral_status`<br>• `bed_reservation.confirm_reservation` | • `PgReferralRepository.atomic_transition_lifecycle` (status `ARRIVED`)<br>• `PgReferralRepository.confirm_bed_direct` |
| **CONFIRMED → OCCUPIED** | 1. `POST /referrals/{referral_id}/status/TREATMENT_ACTIVE`<br>2. `POST /reservation/{hospital_id}/{patient_id}/occupy` | • "Admit / Start Treatment" button in `HospitalDashboard.tsx`<br>• "Mark Bed Occupied" button in Bed Management table | • `referral_store.update_referral_status`<br>• `bed_reservation.mark_bed_occupied` | • `PgReferralRepository.atomic_transition_lifecycle` (status `TREATMENT_ACTIVE`)<br>• `PgReferralRepository.occupy_bed_direct` |

---

## 3. Business Definition of CONFIRMED

**Finding:** **CONFIRMED means "Patient arrival was verified."**

### Evidence from Authoritative Source Code
1. In `src/database/pg_repository.py` lines 588–610:
   ```python
   elif new_status == "ARRIVED":
       referral.arrived_at = now
       if reservation:
           reservation.status = "CONFIRMED"
       # Notification for source hospital:
       notif = Notification(
           event_type="PATIENT_ARRIVED",
           title=f"Patient Arrived: {referral_id}",
           message=f"Patient {referral.patient_id} arrived at destination hospital. Bed reservation confirmed.",
       )
   ```
2. In `src/database/pg_repository.py` lines 1536–1540 (`confirm_bed_direct`):
   ```python
   res.status = "CONFIRMED"
   if ref.status in ["PENDING", "ACCEPTED"]:
       ref.status = "ARRIVED"
       ref.arrived_at = now
   ```
3. In `frontend/components/HospitalDashboard.tsx` lines 796–800:
   The UI filter explicitly maps:
   - `ACCEPTED` $\rightarrow$ "Accepted & Reserved"
   - `IN_TRANSIT` $\rightarrow$ "In Transit"
   - `ARRIVED` $\rightarrow$ "Patient Arrived"
   - `TREATMENT_ACTIVE` $\rightarrow$ "Treatment Active"

**Conclusion:**  
- **Hospital accepted the reservation** occurs during `ACCEPTED` / `RESERVED`.
- **Patient arrival was verified** occurs during `ARRIVED` / `CONFIRMED`.
- **Patient was physically admitted** occurs during `TREATMENT_ACTIVE` / `OCCUPIED`.

---

## 4. Expiry Policy for CONFIRMED Reservations

**Finding:** Under existing business rules, **CONFIRMED reservations do NOT have an automated expiry policy.**

### Evidence from Authoritative Source Code
1. In `src/prediction/bed_reservation.py` lines 1090–1102:
   ```python
   # ----------------------------------------
   # Only RESERVED can expire
   # ----------------------------------------
   if reservation["status"] != RESERVED:
       return {
           "success": False,
           "status": "NOT_EXPIRABLE",
           "message": "Only RESERVED reservations can expire."
       }
   ```
2. **Clinical Rationale:** Once a patient's physical arrival is verified (`CONFIRMED`), the patient is present on hospital premises awaiting triage or ward transport. Automatically expiring the bed reservation in the background while the patient is physically in the hospital would create clinical chaos and double-booking.
3. **Manual Discharge / Cancellation:** If a confirmed patient is subsequently transferred elsewhere, refused care, or departs without admission, the bed is released explicitly by hospital staff via `POST /reservation/.../release` or referral status cancellation (`release_bed_direct`).
4. **Implementation Protection:** `PgReferralRepository.expire_reservation_direct` explicitly enforces this rule:
   ```python
   if res.status == "CONFIRMED":
       return {
           "success": False,
           "status": "CONFIRMED_CANNOT_EXPIRE",
           "message": "Confirmed reservations are guaranteed and cannot be automatically or directly expired. Use release or discharge instead."
       }
   ```

---

## 5. Migration 005 & Worker Heartbeat Verification

1. **Table Schema in Isolated Test Database (`sih_hospital_phase1_run_test`):**
   - Table `worker_heartbeats` exists with primary key `worker_name`, check constraint `chk_worker_status IN ('RUNNING', 'STOPPED', 'FAILED', 'IDLE')`, index `idx_worker_heartbeat_status`, and columns:
     `worker_id`, `status`, `last_heartbeat`, `last_success_at`, `last_error_at`, `processed_total`, `failed_total`, `batch_size`, `duration_seconds`.
2. **Live Read & Write Verification:**
   - Executed probe with `ReservationExpiryWorker.record_heartbeat()`:
     ```python
     Worker heartbeat read: reservation_expiry_worker audit_test_worker RUNNING 154 0.123
     check_worker_health() probe: True
     ```
   - Exit code: `0`. Heartbeat read/update verified functional.

---

## 6. Inspection of the 26 Expiry Tests (Real PostgreSQL Concurrency)

The test file `tests/test_reservation_expiry_worker.py` was inspected:
- **Connection Configuration:** Connects directly via `DATABASE_URL="postgresql://localhost:5432/sih_hospital_phase1_run_test"`.
- **Zero Mocks in Concurrency Tests:**
  - `test_19_concurrent_workers_skip_locked_no_double_expire`: Executes two live worker threads (`worker_alpha`, `worker_beta`) running against real PostgreSQL sessions using `SELECT ... FOR UPDATE SKIP LOCKED`. Validates that all 6 reservations are claimed and expired across the two workers with zero duplicates.
  - `test_20_concurrent_confirmation_and_expiry_valid_final_state`: Spawns concurrent threads executing live `confirm_bed_direct` vs `run_once`, testing PostgreSQL row-level locking race resolution. Validates that the final status is either `CONFIRMED` or `EXPIRED`, never corrupted.
  - `test_21_concurrent_occupancy_and_expiry_valid_counters`: Executes concurrent `occupy_bed_direct` vs `run_once` against live PostgreSQL. Validates that inventory counters (`available_beds`, `occupied_beds`) remain mathematically consistent.
  - `test_22_cross_hospital_isolation`: Validates multi-tenant isolation across distinct hospital records in PostgreSQL.
- Only `test_15` (transient connection error recovery) uses a wrapped session factory to simulate a network drop on the first attempt; all other 25 tests execute directly against the PostgreSQL engine.

---

## 7. Full Backend Test Suite Output & Exit Code

- **Command:** `cd /Users/pawankumarsharma/Desktop/SIH_Hospital_AI && .venv/bin/python -m pytest tests/`
- **Output:**
  ```
  collected 368 items
  ...
  ====================== 368 passed, 413 warnings in 32.36s ======================
  ```
- **Exit Code:** `0` (Zero failures, zero errors across 25 test suites).

---

## 8. Playwright Browser Suite Output & Exit Code

- **Command:** `cd /Users/pawankumarsharma/Desktop/SIH_Hospital_AI/frontend && npx playwright test`
- **Output:**
  ```
  Running 20 tests using 1 worker
  ...
    ✓ 10 passed on Desktop Chrome
    ✓ 10 passed on Mobile Chrome (Pixel 7)
    20 passed (1.0m)
  ```
- **Exit Code:** `0` (100% pass across Desktop and Mobile viewports).

---

## 9. Safety Invariant Verification

| Check | Expected | Actual | Status |
| :--- | :--- | :--- | :---: |
| **`sih_hospital_dev` Records** | 500 hospitals, 8 users | `hospitals`: 500, `users`: 8 | **PASS** |
| **`sih_hospital_dev` Writes/Migrations** | Zero writes or schema changes | No tables or records altered | **PASS** |
| **`git stash list`** | `stash@{0}` intact | `stash@{0}: On master: Backup before GitHub repository synchronization` | **PASS** |
| **Git Commits & Pushes** | Zero commits, zero pushes | Working directory on master, zero commits added | **PASS** |

---

## Final Acceptance Verdict

# **ACCEPTED — PHASE 4D-1**

All business rules, clinical state definitions, concurrency protections, database migrations, and safety invariants have been rigorously verified and confirmed.
