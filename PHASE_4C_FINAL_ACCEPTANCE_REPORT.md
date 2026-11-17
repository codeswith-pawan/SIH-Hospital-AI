# SIH HOSPITAL AI — PHASE 4C FINAL ACCEPTANCE AUDIT & DATA PROVENANCE REPORT

**Date:** November 11, 2026  
**Auditor:** Independent Technical Auditor (Antigravity AI)  
**Target Repository:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Test Database:** `postgresql://localhost:5432/sih_hospital_phase1_run_test`  
**Protected Production Database:** `sih_hospital_dev` (Read-only verified, 100% untouched)  
**Audit Status:** **FUNCTIONAL CHECKS PASSED / UNCOMMISSIONED-CAPACITY CLAIM (1,933 BEDS): FAIL (PROVEN RESERVATION DOUBLE-COUNTING; TRUE UNCOMMISSIONED CAPACITY = 1,980 BEDS)**

---

## 1. EXECUTIVE SUMMARY & DATA PROVENANCE AUDIT VERDICT

Phase 4C connected Central, State, and District administrative tiers directly to authoritative PostgreSQL data.

Following the earlier sign-off, a rigorous data provenance audit was executed against live PostgreSQL records in `sih_hospital_phase1_run_test` to independently test the claim that **1,933 beds** represented uncommissioned hospital capacity.

### Verdict on Uncommissioned Capacity Claim: **FAIL**
- **Root Cause of Failure:** The previously reported figure of **1,933 beds is mathematically incorrect because active reservations were double-counted** in the macro formula $T - A - O - R$.
- **Empirical Evidence from Database Records:**
  1. The 26 newly provisioned facilities that account for uncommissioned onboarding capacity have **0 active reservations** ($R = 0$) and **0 occupied beds** ($O = 0$).
  2. The true uncommissioned capacity across these facilities is **exactly 1,980 beds** ($2,500 \text{ licensed total beds} - 520 \text{ available intake beds}$).
  3. The national active reservations ($R = 45$ at earlier audit, $56$ currently) belong entirely to other hospitals. For general beds, reservations already decremented `Hospital.available_beds`; subtracting $R$ again double-subtracted those beds. For ICU beds, reservations decremented `available_icu_beds` without modifying `available_beds`, resulting in formula artifacts ($U = -1$).
  4. The previously reported adjustment ($1,980 - 45 - 2 = 1,933$) was an ad-hoc adjustment that improperly subtracted unrelated reservations from facilities that had zero reservations.

All functional Phase 4C components (PostgreSQL query routing, geographic authorization, DISHA compliance, frontend data binding, and regression suites) remain **PASS**.

---

## 2. SECTION A: PER-HOSPITAL UNCOMMISSIONED CAPACITY RECONSTRUCTION

Every hospital in `sih_hospital_phase1_run_test` was evaluated using the exact formula:
$$U = \text{total\_beds} - \text{available\_beds} - \text{occupied\_beds} - \text{active\_reserved\_beds}$$
Where `active_reserved_beds` uses the exact dashboard API definition:
`BedReservation.status IN ('RESERVED', 'CONFIRMED')`.

### Aggregate Summary across Database

| Metric | Database Count | Notes |
| :--- | :---: | :--- |
| **Total Hospitals Evaluated** | **886** | All facilities in `sih_hospital_phase1_run_test` |
| **Sum `total_beds` ($T$)** | **57,993** | Total licensed bed capacity |
| **Sum `available_beds` ($A$)** | **56,006** | Immediately available general intake capacity |
| **Sum `occupied_beds` ($O$)** | **11** | Admitted patient occupancy |
| **Sum `active_reserved_beds` ($R$)** | **56** | Active holds (`RESERVED` / `CONFIRMED`) |
| **Aggregate Sum of Calculated $U$** | **1,920** | $\sum (T - A - O - R) = 57,993 - 56,006 - 11 - 56$ |
| **Hospitals with $U = 0$** | **798** | Baseline hospitals with 100% capacity accounted for |
| **Hospitals with $U > 0$** | **27** | Facilities with true uncommissioned capacity ($\sum U = +1,981$) |
| **Hospitals with $U < 0$** | **61** | Test facilities with ICU reservations/occupancy ($\sum U = -61$) |

### Breakdown of Facilities with Non-Zero $U$

#### 1. Facilities with Positive Uncommissioned Capacity ($U > 0$, Sum = +1,981)
All 27 facilities with $U > 0$ correspond to newly provisioned onboarding applications and test source facilities:

| Hospital ID | Hospital Name | Total Beds ($T$) | Avail Beds ($A$) | Occ Beds ($O$) | Active Res ($R$) | Calculated $U$ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `GH00509` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00510` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00511` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00512` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00513` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00514` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00515` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00516` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00519` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00520` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00521` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00522` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00501` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00502` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00503` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00504` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00505` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00506` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00507` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00508` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00517` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00518` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_REJECT_SRC` | Hospital GH_TEST_REJECT_SRC | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_SRC` | Hospital GH_TEST_SRC | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_SRC_03` | Hospital GH_TEST_SRC_03 | 50 | 20 | 0 | 0 | **30** |
| `H_SRC_87133D` | Hospital H_SRC_87133D | 50 | 20 | 0 | 0 | **30** |
| `GH_TX_FEDD5` | Tx Audit Hosp | 15 | 13 | 1 | 0 | **1** |
| **Subtotal Positive $U$** | **27 Facilities** | — | — | — | — | **+1,981** |

#### 2. Facilities with Negative Formula Artifacts ($U < 0$, 61 Facilities, Sum = -61)
61 facilities returned $U = -1$ (e.g., `GH_TEST_COMPAT_*`, `H_P4B_*`, `H_CONCUR_*`).
- **Explanation:** In these facilities, an ICU bed was reserved or occupied. The application logic decremented `Hospital.available_icu_beds` while leaving `Hospital.available_beds` unchanged ($A = T$). Evaluating the macro formula $T - A - O - R$ subtracted the ICU reservation from general beds, yielding $5 - 5 - 0 - 1 = -1$.
- Sum of negative formula artifacts = **-61**.

$$\text{Total Aggregate } U = (+1,981) + (-61) = \mathbf{1,920}$$

---

## 3. SECTION B: PROVISIONING PROVENANCE VERIFICATION

Direct database records were inspected for the 12 AIIMS Amritsar Annex, 10 Apollo Super Specialty Mohali, and 4 test-source facilities.

### Empirical Database Evidence (All 26 Facilities)

```sql
SELECT h.hospital_id, h.name, h.total_beds, h.available_beds, h.occupied_beds,
       COUNT(r.reservation_id) FILTER (WHERE r.status IN ('RESERVED', 'CONFIRMED')) as active_res,
       (h.total_beds - h.available_beds - h.occupied_beds) as true_uncommissioned
FROM hospitals h
LEFT JOIN bed_reservations r ON h.hospital_id = r.hospital_id
WHERE h.hospital_id IN ('GH00501'..'GH00522', 'GH_TEST_SRC'..)
GROUP BY h.hospital_id, h.name, h.total_beds, h.available_beds, h.occupied_beds;
```

| Hospital ID | Facility Name | Licensed Capacity (`total_beds`) | Operational Intake (`available_beds`) | Occupied Beds (`occupied_beds`) | Active Holds (`active_res`) | True Uncommissioned Capacity ($U$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `GH00509` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00510` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00511` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00512` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00513` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00514` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00515` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00516` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00519` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00520` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00521` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00522` | AIIMS Amritsar Annex Super Specialty | 150 | 20 | 0 | 0 | **130** |
| `GH00501` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00502` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00503` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00504` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00505` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00506` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00507` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00508` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00517` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH00518` | Apollo Super Specialty Mohali | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_REJECT_SRC` | Hospital GH_TEST_REJECT_SRC | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_SRC` | Hospital GH_TEST_SRC | 50 | 20 | 0 | 0 | **30** |
| `GH_TEST_SRC_03` | Hospital GH_TEST_SRC_03 | 50 | 20 | 0 | 0 | **30** |
| `H_SRC_87133D` | Hospital H_SRC_87133D | 50 | 20 | 0 | 0 | **30** |
| **TOTALS** | **26 Facilities** | **2,500** | **520** | **0** | **0** | **1,980** |

### Origin of the Previous 1,933 Claim & Proof of Double Counting
1. The 26 facilities holding uncommissioned beds have **Active Reservations = 0**.
2. Their actual licensed capacity is **2,500** beds; their operational intake allocation is **520** beds; their uncommissioned capacity is **1,980 beds**.
3. In the previous report, the auditor observed the national calculation:
   $$57,126 \text{ (Total)} - 55,139 \text{ (Avail)} - 9 \text{ (Occ)} = 1,978$$
   The auditor then subtracted the national reservation count ($R = 45$):
   $$1,978 - 45 = 1,933$$
4. The auditor then attempted to force the 1,980 uncommissioned beds to equal 1,933 by asserting:
   $$1,980 - 45 \text{ (active holds)} - 2 \text{ (test offsets)} = 1,933$$
5. **Why this was invalid:**
   - Active holds did not occur at any of the 26 facilities.
   - Active holds for general beds were already subtracted from `available_beds` at their respective hospitals. Subtracting 45 from the national aggregate double-subtracted those reservations.
   - The "2 test offsets" was an ad-hoc remainder ($1,980 - 1,978 = 2$).
   - Therefore, the true uncommissioned capacity is **1,980 beds**, and the 1,933 figure was an artifact of double subtraction.

---

## 4. SECTION C: RECONCILIATION OF INVENTORY REPRESENTATIONS

### Microscopic (`beds` Table) vs Macroscopic (`hospitals` Table)

| Feature | `beds` Table | `hospitals` Table |
| :--- | :--- | :--- |
| **Architectural Role** | Granular physical bed tracking (Phase 4A/4B) | Nationwide registry & macro aggregations |
| **Record Level** | One record per physical bed (`GENERAL-001`, `ICU-001`) | One record per hospital facility (`GH00001`) |
| **Total Records in Database** | **4,279 rows** | **886 hospitals** (57,993 aggregate licensed beds) |
| **Population Mechanism** | On-demand initialization (`initialize_default_inventory`) | System onboarding & bulk registry import |

### Detailed Breakdown of the 4,279 Records in `beds`

```sql
SELECT bed_type, status, COUNT(*) FROM beds GROUP BY bed_type, status ORDER BY bed_type, status;
```

| Department (`bed_type`) | Status | Record Count |
| :--- | :--- | :---: |
| **EMERGENCY** | `AVAILABLE` | **490** |
| **GENERAL** | `AVAILABLE` | **2,754** |
| **GENERAL** | `OCCUPIED` | **2** |
| **GENERAL** | `RESERVED` | **5** |
| **ICU** | `AVAILABLE` | **933** |
| **ICU** | `OCCUPIED` | **26** |
| **ICU** | `RESERVED` | **69** |
| **TOTAL** | — | **4,279** |

### Hospital Coverage & Intentional Design
- **Hospitals with Detailed Records in `beds`:** **258 hospitals**
- **Hospitals with NO Detailed Records in `beds`:** **628 hospitals** (e.g., `GH00501`, `GH00521`, `GHBB544`)
- **Detailed Beds vs `total_beds` Comparison:**
  - In **46 hospitals**, `detailed_beds_count == total_beds`.
  - In **212 hospitals**, `detailed_beds_count != total_beds` (due to additional ICU/Emergency physical rows or partial ward initialization).
  - All 26 newly provisioned facilities have **0 detailed rows in `beds`**.
- **Business Rule Explanation:** The `beds` table was intentionally designed to instantiate physical bed records on demand when a hospital interacts with the granular bed management system or receives a direct reservation (`reserve_bed_direct:1301-1306`). The 628 hospitals without rows in `beds` operate at the aggregate level in the `hospitals` table.

---

## 5. SECTION D: AUDIT VERDICT & FINAL DECISION

### Classification of the Uncommissioned-Capacity Claim: **FAIL**

| Provenance Check | Expected / Claimed | Actual Verified Fact | Classification |
| :--- | :---: | :---: | :---: |
| **Uncommissioned Capacity Total** | 1,933 beds | **1,980 beds** (or 1,981 including `GH_TX_FEDD5`) | **FAIL** |
| **Active Holds Subtraction** | -45 beds from uncommissioned total | Active holds are in other facilities; subtracting them was double-counting | **FAIL** |
| **Provisioning Provenance (26 facilities)** | 1,980 licensed vs intake gap | Verified: 12 AIIMS (1,560) + 10 Apollo (300) + 4 Test (120) = 1,980 | **PASS** |
| **Detailed `beds` Table Integrity** | 4,279 records | Verified: 258 hospitals tracked on-demand; 628 macro-only | **PASS** |

### Overall Phase 4C Status Matrix

| Component | Audit Status | Evidence |
| :--- | :---: | :--- |
| **PostgreSQL Administrative Routing** | **PASS** | 11/11 endpoints query PostgreSQL via `PgAdminRepository` |
| **Geographic Jurisdiction Matrix** | **PASS** | 25/25 live authorization test cases passed |
| **SQL vs API Aggregation Truth** | **PASS** | 12/12 metrics identical to raw database counts |
| **DISHA Privacy & Patient Protection** | **PASS** | Zero PII in administrative APIs; 100% ID masking |
| **Frontend Dynamic Binding** | **PASS** | StatCards bound to live API; 0 build errors |
| **Integration Test Suites** | **PASS** | Phase 4C (15/15), 4A (14/14), 4B (13/13), Registration (92/92) |
| **Regression Baselines** | **BASELINE** | 390 passed, 1 skipped, 2 GH00046 baseline failures |
| **Database Safety** | **PASS** | `sih_hospital_dev` 100% untouched (500 hosp, 8 users, 4 roles) |
| **Git Safety** | **PASS** | `stash@{0}` preserved, zero commits, zero pushes |

### Conclusion
The technical architecture of Phase 4C is sound and production-ready. The administrative dashboard routes correctly to PostgreSQL without SQLite/JSON fallback, enforces geographic authorization, and respects patient privacy. The accounting claim regarding the 1,933 beds is corrected to **1,980 beds**, with the double-counting defect fully explained.

Phase 4D has not been started.
