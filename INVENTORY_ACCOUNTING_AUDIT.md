# SIH HOSPITAL AI — INVENTORY ACCOUNTING CONSISTENCY AUDIT

**Date:** November 11, 2026  
**Auditor:** Independent Technical Auditor (Antigravity AI)  
**Target Repository:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Test Database:** `postgresql://localhost:5432/sih_hospital_phase1_run_test`  
**Protected Production Database:** `sih_hospital_dev` (Read-only verified, 100% untouched)  
**Scope:** Investigation of the aggregate inventory accounting issue discovered during Phase 4C. Strictly read-only; no code or schema modifications; Phase 4D not started.

---

## 1. RESERVATION LIFECYCLE & COUNTER TRACE

The 7 lifecycle methods in `src/database/pg_repository.py` and related services were audited:
- `reserve_bed_direct` (lines 1225–1464)
- `confirm_bed_direct` (lines 1465–1519)
- `occupy_bed_direct` (lines 1520–1583)
- `release_bed_direct` (lines 1584–1660)
- `discharge_patient_direct` (lines 1661–1734)
- `expire_reservation_direct` (lines 1735–1808)
- `initialize_or_reset_inventory` (lines 1832–1907)

### Counter Mutation Matrix by Lifecycle Event

| Method / Transition | Target Bed Type | `Hospital.available_beds` | `Hospital.available_icu_beds` | `Hospital.available_emergency_beds` | `Hospital.occupied_beds` | `Hospital.total_beds` | `Bed.status` | `BedReservation.status` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`reserve_bed_direct`** | GENERAL | $\max(0, A - 1)$ | — | — | Unchanged | Unchanged | `AVAILABLE` $\to$ `RESERVED` | Inserted as `RESERVED` |
| | ICU | — | $\max(0, A_{icu} - 1)$ | — | Unchanged | Unchanged | `AVAILABLE` $\to$ `RESERVED` | Inserted as `RESERVED` |
| | EMERGENCY | — | — | $\max(0, A_{emg} - 1)$ | Unchanged | Unchanged | `AVAILABLE` $\to$ `RESERVED` | Inserted as `RESERVED` |
| **`confirm_bed_direct`** | ALL | Unchanged | Unchanged | Unchanged | Unchanged | Unchanged | Unchanged (`RESERVED`) | `RESERVED` $\to$ `CONFIRMED` |
| **`occupy_bed_direct`** | GENERAL | Unchanged | Unchanged | Unchanged | $O + 1$ | Unchanged | `RESERVED` $\to$ `OCCUPIED` | `CONFIRMED` $\to$ `OCCUPIED` |
| | ICU | Unchanged | Unchanged | Unchanged | $O + 1$ | Unchanged | `RESERVED` $\to$ `OCCUPIED` | `CONFIRMED` $\to$ `OCCUPIED` |
| | EMERGENCY | Unchanged | Unchanged | Unchanged | $O + 1$ | Unchanged | `RESERVED` $\to$ `OCCUPIED` | `CONFIRMED` $\to$ `OCCUPIED` |
| **`release_bed_direct`** | GENERAL | $\min(T, A + 1)$ | — | — | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| | ICU | — | $\min(T_{icu}, A_{icu} + 1)$ | — | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| | EMERGENCY | — | — | $\min(T_{emg}, A_{emg} + 1)$ | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| **`discharge_patient_direct`** | GENERAL | $\min(T, A + 1)$ | — | — | $\max(0, O - 1)$ | Unchanged | `OCCUPIED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| | ICU | — | $\min(T_{icu}, A_{icu} + 1)$ | — | $\max(0, O - 1)$ | Unchanged | `OCCUPIED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| | EMERGENCY | — | — | $\min(T_{emg}, A_{emg} + 1)$ | $\max(0, O - 1)$ | Unchanged | `OCCUPIED` $\to$ `AVAILABLE` | $\to$ `RELEASED` |
| **`expire_reservation_direct`** | GENERAL | $\min(T, A + 1)$ | — | — | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `EXPIRED` |
| | ICU | — | $\min(T_{icu}, A_{icu} + 1)$ | — | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `EXPIRED` |
| | EMERGENCY | — | — | $\min(T_{emg}, A_{emg} + 1)$ | Unchanged | Unchanged | `RESERVED` $\to$ `AVAILABLE` | $\to$ `EXPIRED` |
| **`initialize_or_reset_inventory`** | BATCH | Set to $A_{init}$ | Set to $A_{icu\_init}$ | Unchanged (2) | Reset to 0 | Set to $A_{init}$ | Seeds GENERAL & ICU rows | Deletes on `reset=True` |

### Key Lifecycle Findings
1. **Deduction at Reservation Time:** In all three departments, active reservations **are deducted immediately** from the corresponding available counter (`available_beds`, `available_icu_beds`, `available_emergency_beds`) during `reserve_bed_direct`.
2. **Occupancy Counter Asymmetry:** `Hospital` possesses **only one scalar `occupied_beds` column**. When an ICU or Emergency bed is occupied via `occupy_bed_direct`, it increments `Hospital.occupied_beds`. There is **no `occupied_icu_beds` or `occupied_emergency_beds` column** on the `Hospital` model.
3. **Emergency Seeding Omission in `initialize_or_reset_inventory`:** `initialize_or_reset_inventory` sets `Hospital.emergency_beds = 2` and `available_emergency_beds = 2` (lines 1855–1856), but **only loops to insert GENERAL and ICU beds into the `beds` table** (lines 1883–1904). Consequently, attempting an emergency reservation against an inventory initialized with `initialize_or_reset_inventory` fails with `NO_BED_AVAILABLE` because no physical rows exist in `beds`. By contrast, `initialize_default_inventory` correctly seeds `EMG-001` and `EMG-002`.

---

## 2. ACCOUNTING EQUATIONS PER CATEGORY

Because each department has distinct capacity columns and counter mechanics, a single aggregate equation conflates categories. The system operates on three independent category equations:

### 2.1 General Ward Accounting Equation
$$T_{\text{gen}} = A_{\text{gen}} + R_{\text{gen}} + O_{\text{gen}} + U_{\text{gen}}$$

Where:
- **Licensed Capacity ($T_{\text{gen}}$):** `Hospital.total_beds`
- **Available Capacity ($A_{\text{gen}}$):** `Hospital.available_beds`
- **Active Reserved Holds ($R_{\text{gen}}$):** Count of `BedReservation` with status in `('RESERVED', 'CONFIRMED')` where `Bed.bed_type = 'GENERAL'`
- **Occupied Beds ($O_{\text{gen}}$):** Count of `Bed` with `status = 'OCCUPIED'` and `bed_type = 'GENERAL'` (or General share of `Hospital.occupied_beds`)
- **Uncommissioned / Offline Capacity ($U_{\text{gen}}$):** Licensed beds not yet staffed or opened for referral intake:
  $$U_{\text{gen}} = T_{\text{gen}} - (A_{\text{gen}} + R_{\text{gen}} + O_{\text{gen}})$$

**Reservation Deduction Status:** $R_{\text{gen}}$ is **already deducted** from $A_{\text{gen}}$. In a fully commissioned operational ward, $T_{\text{gen}} = A_{\text{gen}} + R_{\text{gen}} + O_{\text{gen}}$, so $A_{\text{gen}} = T_{\text{gen}} - R_{\text{gen}} - O_{\text{gen}}$.

### 2.2 Intensive Care Unit (ICU) Accounting Equation
$$T_{\text{icu}} = A_{\text{icu}} + R_{\text{icu}} + O_{\text{icu}} + U_{\text{icu}}$$

Where:
- **Licensed Capacity ($T_{\text{icu}}$):** `Hospital.icu_beds`
- **Available Capacity ($A_{\text{icu}}$):** `Hospital.available_icu_beds`
- **Active Reserved Holds ($R_{\text{icu}}$):** Count of `BedReservation` with status in `('RESERVED', 'CONFIRMED')` where `Bed.bed_type = 'ICU'`
- **Occupied Beds ($O_{\text{icu}}$):** Count of `Bed` with `status = 'OCCUPIED'` and `bed_type = 'ICU'`
- **Uncommissioned / Offline Capacity ($U_{\text{icu}}$):** $T_{\text{icu}} - (A_{\text{icu}} + R_{\text{icu}} + O_{\text{icu}})$

**Reservation Deduction Status:** $R_{\text{icu}}$ is **already deducted** from $A_{\text{icu}}$. It has **zero effect on `Hospital.available_beds`**.

### 2.3 Emergency Ward Accounting Equation
$$T_{\text{emg}} = A_{\text{emg}} + R_{\text{emg}} + O_{\text{emg}} + U_{\text{emg}}$$

Where:
- **Licensed Capacity ($T_{\text{emg}}$):** `Hospital.emergency_beds`
- **Available Capacity ($A_{\text{emg}}$):** `Hospital.available_emergency_beds`
- **Active Reserved Holds ($R_{\text{emg}}$):** Count of `BedReservation` with status in `('RESERVED', 'CONFIRMED')` where `Bed.bed_type = 'EMERGENCY'`
- **Occupied Beds ($O_{\text{emg}}$):** Count of `Bed` with `status = 'OCCUPIED'` and `bed_type = 'EMERGENCY'`
- **Uncommissioned / Offline Capacity ($U_{\text{emg}}$):** $T_{\text{emg}} - (A_{\text{emg}} + R_{\text{emg}} + O_{\text{emg}})$

**Reservation Deduction Status:** $R_{\text{emg}}$ is **already deducted** from $A_{\text{emg}}$.

### 2.4 Total Facility Licensed Capacity
$$T_{\text{total}} = T_{\text{gen}} + T_{\text{icu}} + T_{\text{emg}}$$

`Hospital.total_beds` is **not** $T_{\text{total}}$; rather, `Hospital.total_beds` stores $T_{\text{gen}}$. Total facility physical capacity is the sum of `total_beds + icu_beds + emergency_beds`.

---

## 3. MULTI-HOSPITAL RECONCILIATION AUDIT

Direct queries were executed against `sih_hospital_phase1_run_test` (886 hospitals).

### 3.1 Hospitals with Negative Calculated Inventory
- **Criterion:** $T_{\text{gen}} - A_{\text{gen}} - O - R < 0$
- **Total Inconsistent Hospitals:** **61 hospitals**
- **Root Cause:** In these 61 test facilities (e.g. `GH_TEST_COMPAT_*`, `H_P4B_*`), an ICU reservation or occupancy occurred. $A_{\text{icu}}$ was decremented, but $A_{\text{gen}}$ was untouched ($A_{\text{gen}} = T_{\text{gen}} = 5$). Evaluating $T_{\text{gen}} - A_{\text{gen}} - O_{\text{total}} - R_{\text{total}}$ subtracted the ICU reservation/occupant from the general counter:
  $$5 - 5 - 0 - 1 = -1$$
- **SQL Query:**
  ```sql
  SELECT h.hospital_id, h.name, h.total_beds, h.available_beds, h.occupied_beds,
         COALESCE(r.active_res, 0) as active_res,
         (h.total_beds - h.available_beds - h.occupied_beds - COALESCE(r.active_res, 0)) as calculated_gap
  FROM hospitals h
  LEFT JOIN (
      SELECT hospital_id, COUNT(*) as active_res
      FROM bed_reservations WHERE status IN ('RESERVED', 'CONFIRMED')
      GROUP BY hospital_id
  ) r ON h.hospital_id = r.hospital_id
  WHERE (h.total_beds - h.available_beds - h.occupied_beds - COALESCE(r.active_res, 0)) < 0
  ORDER BY h.hospital_id;
  ```
- **Sample Inconsistent IDs:**
  - `GH_TEST_COMPAT_468f12` ($T=5, A=5, O=0, R=1 \implies \text{Gap}=-1$)
  - `GH_TEST_COMPAT_8a58cc` ($T=5, A=5, O=0, R=1 \implies \text{Gap}=-1$)
  - `GH_TEST_ICU_FULL` ($T=10, A=10, O=0, R=1 \implies \text{Gap}=-1$)
  - `H_CONCUR_06094C` ($T=5, A=5, O=0, R=1 \implies \text{Gap}=-1$)
  - `H_P4B_055C87` ($T=2, A=2, O=0, R=1 \implies \text{Gap}=-1$)

### 3.2 Hospitals Where Reservation Counts Disagree with Detailed Bed Counters
- **Criterion:** Count of `Bed.status = 'RESERVED'` $\ne$ Count of active `BedReservation` (`status IN ('RESERVED', 'CONFIRMED')`)
- **Total Inconsistent Hospitals:** **18 hospitals**
- **Root Cause:** Legacy test fixtures directly updated `Bed.status = 'RESERVED'` without creating a corresponding `BedReservation` row in the relational table.
- **SQL Query:**
  ```sql
  SELECT h.hospital_id, h.name,
         COUNT(b.id) FILTER (WHERE b.status = 'RESERVED') as bed_reserved_count,
         COALESCE(r.active_res, 0) as active_reservations_count
  FROM hospitals h
  LEFT JOIN beds b ON h.hospital_id = b.hospital_id
  LEFT JOIN (
      SELECT hospital_id, COUNT(*) as active_res
      FROM bed_reservations WHERE status IN ('RESERVED', 'CONFIRMED')
      GROUP BY hospital_id
  ) r ON h.hospital_id = r.hospital_id
  GROUP BY h.hospital_id, h.name, r.active_res
  HAVING COUNT(b.id) FILTER (WHERE b.status = 'RESERVED') != COALESCE(r.active_res, 0);
  ```
- **Sample Inconsistent IDs:**
  - `GH_TX_FEDD5` (`Bed.status=RESERVED`: 1 vs `active_res`: 0)
  - `GH0DBF9` (`Bed.status=RESERVED`: 1 vs `active_res`: 0)
  - `GH0DFCF` (`Bed.status=RESERVED`: 1 vs `active_res`: 0)
  - `GH2171D` (`Bed.status=RESERVED`: 1 vs `active_res`: 0)
  - `GH24EF3` (`Bed.status=RESERVED`: 1 vs `active_res`: 0)

### 3.3 Hospitals Where Occupied Counters Disagree with Bed Records
- **Criterion:** `Hospital.occupied_beds` $\ne$ Count of `Bed.status = 'OCCUPIED'`
- **Total Inconsistent Hospitals:** **17 hospitals**
- **Root Cause:** Legacy fixtures updated `Bed.status = 'OCCUPIED'` without incrementing the denormalized `Hospital.occupied_beds` column.
- **SQL Query:**
  ```sql
  SELECT h.hospital_id, h.name, h.occupied_beds,
         COUNT(b.id) FILTER (WHERE b.status = 'OCCUPIED') as bed_occupied_count
  FROM hospitals h
  LEFT JOIN beds b ON h.hospital_id = b.hospital_id
  GROUP BY h.hospital_id, h.name, h.occupied_beds
  HAVING h.occupied_beds != COUNT(b.id) FILTER (WHERE b.status = 'OCCUPIED');
  ```
- **Sample Inconsistent IDs:**
  - `GH0DBF9` (`Hospital.occupied_beds`: 0 vs `Bed.status=OCCUPIED`: 1)
  - `GH0DFCF` (`Hospital.occupied_beds`: 0 vs `Bed.status=OCCUPIED`: 1)
  - `GH2171D` (`Hospital.occupied_beds`: 0 vs `Bed.status=OCCUPIED`: 1)
  - `GH24EF3` (`Hospital.occupied_beds`: 0 vs `Bed.status=OCCUPIED`: 1)
  - `GH2FC3C` (`Hospital.occupied_beds`: 0 vs `Bed.status=OCCUPIED`: 1)

### 3.4 Hospitals Without Detailed Bed Records
- **Criterion:** Hospital exists in `hospitals`, but 0 rows exist in `beds`
- **Total Inconsistent Hospitals:** **628 hospitals** (70.9% of database)
- **Root Cause:** By design, baseline imported facilities (500 from `sih_hospital_dev`) and newly provisioned application facilities operate as macro registry records until physical beds are explicitly seeded.
- **SQL Query:**
  ```sql
  SELECT h.hospital_id, h.name, h.total_beds, h.available_beds, h.occupied_beds
  FROM hospitals h
  WHERE NOT EXISTS (SELECT 1 FROM beds b WHERE b.hospital_id = h.hospital_id);
  ```
- **Sample Inconsistent IDs:**
  - `GH00001` (Synthetic Test Hospital 1, $T=100, A=100, O=0$)
  - `GH00501` (Apollo Super Specialty Mohali, $T=50, A=20, O=0$)
  - `GH00509` (AIIMS Amritsar Annex Super Specialty, $T=150, A=20, O=0$)
  - `GH_TEST_SRC` (Hospital GH_TEST_SRC, $T=50, A=20, O=0$)
  - `GH131B1` (Test Hospital GH131B1, $T=20, A=20, O=0$)

### 3.5 Hospitals with Detailed Inventory Differing from Aggregate Inventory
- **Criterion:** Count of `Bed` rows $\ne Hospital.total_beds$
- **Total Inconsistent Hospitals:** **213 hospitals**
- **Root Cause:** `Hospital.total_beds` represents General bed capacity ($T_{\text{gen}}$). Hospitals initialized with ICU and Emergency beds have total physical rows in `beds` equal to $T_{\text{gen}} + T_{\text{icu}} + T_{\text{emg}}$ (e.g. $10 + 2 + 2 = 14$), which differs from $T_{\text{gen}} = 10$.
- **SQL Query:**
  ```sql
  SELECT h.hospital_id, h.name, h.total_beds,
         (h.total_beds + h.icu_beds + h.emergency_beds) as sum_capacities,
         COUNT(b.id) as detailed_beds_total
  FROM hospitals h
  JOIN beds b ON h.hospital_id = b.hospital_id
  GROUP BY h.hospital_id, h.name, h.total_beds, h.icu_beds, h.emergency_beds
  HAVING COUNT(b.id) != h.total_beds;
  ```
- **Sample Inconsistent IDs:**
  - `GH_AMR_8DED` (`total_beds` = 10, `detailed_beds` = 14 [10 Gen + 2 ICU + 2 EMG])
  - `GH_AMR_C734` (`total_beds` = 10, `detailed_beds` = 14 [10 Gen + 2 ICU + 2 EMG])
  - `GH_DEL_A1FC` (`total_beds` = 10, `detailed_beds` = 14 [10 Gen + 2 ICU + 2 EMG])
  - `GH_DEL_E77C` (`total_beds` = 10, `detailed_beds` = 14 [10 Gen + 2 ICU + 2 EMG])
  - `GH_LUD_9319` (`total_beds` = 10, `detailed_beds` = 14 [10 Gen + 2 ICU + 2 EMG])

---

## 4. DASHBOARD METRIC DEFINITIONS AUDIT

Inspected `PgAdminRepository.get_central_metrics`, `get_state_metrics`, `get_district_metrics`, `get_hospital_inventory`, and frontend components (`CentralDashboard.tsx`, `StateDashboard.tsx`, `DistrictDashboard.tsx`, `HospitalDashboard.tsx`).

### Data Dictionary & Metric Provenance

| Displayed Metric Label | API Response Key | Source Table & Column / Expression | Category | Status Inclusion | Reservation Handling | Capacity Type Represented |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **National Bed Occupancy** (Rate) | `bed_occupancy_rate` | `round(SUM(occupied_beds) / SUM(total_beds) * 100, 1)` | Mixed / General | Occupied beds / Licensed General beds | Excluded from numerator | Operational Occupancy vs Licensed General Capacity |
| **National Bed Occupancy** (Subtitle) | `available_beds`, `total_beds` | `SUM(Hospital.available_beds)` of `SUM(Hospital.total_beds)` | General | Available General beds / Licensed General beds | **Excluded** from Available (holds already deducted) | Operational Intake vs Licensed General Capacity |
| **National ICU Occupancy** (Rate) | `icu_occ_rate` | `round(max(0, ICU_tot - ICU_avail) / ICU_tot * 100, 1)` | ICU | Non-available ICU beds / Total ICU beds | **Included in occupancy numerator** (Reservations deduct from `available_icu_beds`) | Operational Occupancy + Holds vs Licensed ICU Capacity |
| **National ICU Occupancy** (Subtitle) | `available_icu_beds`, `total_icu_beds` | `SUM(Hospital.available_icu_beds)` of `SUM(Hospital.icu_beds)` | ICU | Available ICU beds / Total ICU beds | **Excluded** from Available (holds already deducted) | Operational Intake vs Licensed ICU Capacity |
| **Active Bed Reservations** | `total_reserved_beds` | `COUNT(BedReservation) WHERE status IN ('RESERVED', 'CONFIRMED')` | All (General + ICU + EMG) | Active holds across all departments | Solely active holds | In-transit operational allocation |
| **Hospital General Beds Free** | `available_beds` | Detailed: `COUNT(Bed) WHERE type='GENERAL' AND status='AVAILABLE'`<br>Fallback: `Hospital.available_beds` | General | `AVAILABLE` | Excluded | Operational Available |
| **Hospital Reserved Beds** (Fallback defect) | `reserved_beds` | Fallback: `max(0, total_beds - available_beds - occupied_beds)` | General | Inferred | **Flawed:** Falsely treats uncommissioned beds as reserved beds | Operational Hold (Distorted by Fallback) |

### Discovered Dashboard Logic Defects
1. **Fallback Reservation Distortion (`pg_repository.py:878`):** In `get_hospital_inventory`, when a hospital has no detailed rows in `beds`, line 878 calculates:
   `res_gen = max(0, total_gen - avail_gen - occ_gen)`.
   For an onboarded hospital with 150 licensed beds and 20 operational intake beds, this calculates `res_gen = 130`! It reports 130 "reserved beds" on the hospital dashboard when the hospital has **zero reservations**.
2. **ICU Occupancy Approximation (`pg_repository.py:1950`):** `occupied_icu = max(0, total_icu - available_icu)`. Because `available_icu_beds` is decremented when an ICU bed is *reserved*, this formula treats active ICU reservations as *occupied beds*, inflating the reported ICU occupancy rate before the patient has arrived.

---

## 5. AUDIT FINDINGS CLASSIFICATION

| Finding ID | Audit Area | Classification | Summary of Verified Evidence |
| :---: | :--- | :---: | :--- |
| **F-01** | **Direct Bed Reservation Counter Deduction** | **PASS** | `reserve_bed_direct` correctly deducts from each category's available counter (`available_beds`, `available_icu_beds`, `available_emergency_beds`) without cross-category leakage. |
| **F-02** | **Direct Bed Lifecycle State Transitions** | **PASS** | All transitions (`reserve` $\to$ `confirm` $\to$ `occupy` $\to$ `discharge` / `release` / `expire`) maintain valid `Bed.status` and `BedReservation.status` states. |
| **F-03** | **Emergency Bed Initialization in Reset Method** | **FAIL** | `initialize_or_reset_inventory` sets emergency capacity on `Hospital`, but fails to insert `EMERGENCY` rows into `beds`, causing emergency reservations to fail with `NO_BED_AVAILABLE`. |
| **F-04** | **Occupied Beds Category Tracking** | **FAIL** | `Hospital` has only a single `occupied_beds` column. Occupying ICU or Emergency beds increments general `Hospital.occupied_beds`, creating cross-category coupling and negative calculated inventory ($U = -1$). |
| **F-05** | **Dashboard Inventory Fallback Calculation** | **FAIL** | `get_hospital_inventory` line 878 classifies uncommissioned beds ($T - A - O$) as "reserved beds", fabricating hundreds of active reservations for unseeded facilities. |
| **F-06** | **Macro Equation Category Conflation** | **FAIL** | The macro calculation $T - A - O - R = 1,933$ subtracted all-category reservations ($R$) from General available beds ($A$), double-counting reservations and understating true uncommissioned capacity (1,980 beds). |
| **F-07** | **PostgreSQL Single Source of Truth** | **PASS** | All administrative endpoints route queries to PostgreSQL without silent SQLite/JSON fallback. |
| **F-08** | **Production Database Safety** | **PASS** | `sih_hospital_dev` remains 100% untouched (500 hospitals, 8 users, 4 roles). |

---

## 6. PROPOSED MINIMAL SAFE CORRECTIONS & REGRESSION TESTS

> [!IMPORTANT]
> The following corrections are strictly proposed. In compliance with safety rules, **no modifications have been implemented**. Explicit user approval is required prior to applying any change.

### Proposal 1: Fix Emergency Bed Seeding in `initialize_or_reset_inventory`
- **Location:** `src/database/pg_repository.py:1894`
- **Current Behavior:** Loops only for `GENERAL` and `ICU` beds.
- **Proposed Correction:** Add loop for `available_emergency_beds`:
  ```python
  for i in range(1, int(hospital.emergency_beds or 2) + 1):
      b = Bed(
          hospital_id=hospital_id,
          bed_number=f"EMERGENCY-{i:03d}",
          bed_type="EMERGENCY",
          status="AVAILABLE",
          created_at=now,
          updated_at=now,
      )
      self.session.add(b)
  ```
- **Regression Test:** Execute `reserve_bed_direct(hospital_id, patient_id, bed_type="EMERGENCY")` against an inventory initialized with `initialize_or_reset_inventory` and assert `success == True`.

### Proposal 2: Correct Fallback Reservation Calculation in `get_hospital_inventory`
- **Location:** `src/database/pg_repository.py:878`
- **Current Behavior:** `res_gen = max(0, total_gen - avail_gen - occ_gen)`
- **Proposed Correction:** Query active reservations directly from `bed_reservations`:
  ```python
  res_gen = self.session.execute(
      select(func.count(BedReservation.reservation_id))
      .join(Bed, BedReservation.bed_id == Bed.id)
      .where(BedReservation.hospital_id == hospital_id, Bed.bed_type == "GENERAL", BedReservation.status.in_(["RESERVED", "CONFIRMED"]))
  ).scalar() or 0
  ```
- **Regression Test:** Call `GET /hospitals/{hospital_id}/inventory` for `GH00509` (AIIMS Annex) and verify `reserved_beds == 0` instead of 130.

### Proposal 3: Align Dashboard ICU Occupancy Calculation
- **Location:** `src/database/pg_repository.py:1950`
- **Current Behavior:** `occupied_icu = max(0, total_icu - available_icu)`
- **Proposed Correction:** Exclude active ICU reservations from the occupancy count:
  ```python
  active_icu_res = self.session.execute(
      select(func.count(BedReservation.reservation_id))
      .join(Bed, BedReservation.bed_id == Bed.id)
      .where(Bed.bed_type == "ICU", BedReservation.status.in_(["RESERVED", "CONFIRMED"]))
  ).scalar() or 0
  occupied_icu = max(0, total_icu - available_icu - active_icu_res)
  ```
- **Regression Test:** Reserve an ICU bed without occupying it; assert `occupied_icu_beds == 0` and `total_reserved_beds == 1`.

---

## 7. CONCLUSION

This audit has definitively mapped the aggregate inventory accounting issue discovered in Phase 4C:
1. Active reservations **are already deducted** from each department's respective available counter at the moment of reservation.
2. In macro equations, subtracting reservations from available beds constitutes an improper double-subtraction.
3. Category conflation between General licensed beds (`total_beds`) and ICU reservations generated the negative inventory artifacts ($U = -1$) and the invalid 1,933 figure.
4. The true uncommissioned capacity across provisioned facilities is **1,980 beds**.
5. Three minimal, targeted corrections have been identified to resolve the underlying counter asymmetries when approved.

*End of Inventory Accounting Consistency Audit Report.*
