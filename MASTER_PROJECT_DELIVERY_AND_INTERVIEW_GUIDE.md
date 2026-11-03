# 🏥 SIH_Hospital_AI — Master Platform Architecture & Interview Guide

**Version:** 2.0.0 (Multi-Tier Administrative Governance Edition)  
**Status:** ALL PHASES COMPLETE (30/30 Automated Tests Passing, Clean Frontend Production Build)  
**Author:** Senior Full-Stack & Application Security Engineer / Pair Programming Partner  
**Date:** October 2026  

---

## 1. System Overview & Multi-Tier Vision

`SIH_Hospital_AI` is an intelligent, multi-tier healthcare logistics and hospital referral coordination platform. It unifies clinical operations at the hospital level with administrative oversight at the District, State, and National levels.

### The Four Administrative Tiers

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Central Government Tier                           │
│   - National capacity & interstate patient movement analytics          │
│   - Aggregate summaries across all 28 states & UTs (privacy preserving)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    State Administration Tier                           │
│   - Inter-district resource comparison & ICU strain indicators         │
│   - Strictly bounded to the administrator's assigned State             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                   District Administration Tier                         │
│   - Live facility directory, aggregate bed & ICU gauges               │
│   - Real-time district referral monitoring & bottleneck alerts         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                         Hospital Tier                                  │
│   - Physical bed inventory (GENERAL-001, ICU-001)                      │
│   - Referral lifecycle (PENDING ➔ ACCEPTED ➔ IN_TRANSIT ➔ ARRIVED...) │
│   - Clinical patient admissions & automated bed reservations           │
└────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Server-Side Enforcement**: All administrative and clinical boundaries are enforced server-side via cryptographic JWT claims validated against the hospital master database. Supplying a fabricated `hospital_id`, `district`, or `state` parameter returns an immediate `403 Forbidden`.

---

## 2. Verified Phase-by-Phase Completion Status

| Phase | Description | Deliverable | Status | Verification Evidence |
|---|---|---|---|---|
| **Phase 1** | Code Audit & Architecture | System inventory & roadmap | **COMPLETE** | Documented in `phase1_architecture_audit.md` |
| **Phase 2** | Hospital Login & Access Control | PBKDF2 hashing, JWT & RBAC | **COMPLETE** | 13/13 unit & API tests in `test_auth_and_access.py` |
| **Phase 3** | Bed Inventory & Referral Lifecycle | Physical bed allocation & auto-reserve | **COMPLETE** | 4/4 lifecycle tests in `test_referral_and_bed_lifecycle.py` |
| **Phase 4** | District Administration | District Dashboard & `/district/*` APIs | **COMPLETE** | 4/4 district isolation tests & `DistrictDashboard.tsx` |
| **Phase 5** | State Administration | State Dashboard & `/state/*` APIs | **COMPLETE** | 3/3 state boundary tests & `StateDashboard.tsx` |
| **Phase 6** | Central Administration | Central Dashboard & `/central/*` APIs | **COMPLETE** | 2/2 national aggregation tests & `CentralDashboard.tsx` |
| **Phase 7** | AI Recommendations & Analytics | ML scoring, explainability & disclaimer | **COMPLETE** | Reason generator & clinical disclaimer attached |
| **Phase 8** | Security, Privacy & Reliability | Thread-safe locks, secret isolation | **COMPLETE** | 4/4 security & concurrency tests in `test_security_and_reliability.py` |
| **Phase 9** | Automated Testing & Build | Pytest suite & Next.js production build | **COMPLETE** | **30/30 Pytest tests passing**, `next build` 0 errors |
| **Phase 10** | Final Demo & Interview Guide | Comprehensive runbook & demo script | **COMPLETE** | Master Runbook documented below |

---

## 3. Account Credentials for Live Demonstration

All accounts are pre-seeded with PBKDF2-HMAC-SHA256 hashed credentials.

| Role | Username | Password | Jurisdiction / Hospital Scope |
|---|---|---|---|
| **Hospital User (Primary)** | `gh00046` | `hospital123` | Regional Amritsar Medical College Hospital (`GH00046`), Amritsar, Punjab |
| **Hospital User (Secondary)** | `gh00119` | `hospital123` | District Amritsar Medical College Hospital (`GH00119`), Amritsar, Punjab |
| **Hospital User (Cross-District)**| `gh_test_other` | `hospital123` | Test Other Hospital (`GH_TEST_OTHER`), Ludhiana, Punjab |
| **District Admin (Amritsar)** | `amritsar_district_admin` | `district123` | Amritsar District, Punjab |
| **District Admin (Ludhiana)** | `ludhiana_district_admin` | `district123` | Ludhiana District, Punjab |
| **State Admin (Punjab)** | `punjab_admin` | `admin123` | Punjab State (7 Districts, 57 Hospitals) |
| **State Admin (Maharashtra)** | `maharashtra_admin` | `admin123` | Maharashtra State (6 Districts, 54 Hospitals) |
| **Central Admin (National)** | `central_admin` | `central123` | Nationwide aggregate visibility (500 Hospitals across India) |

---

## 4. Step-by-Step Demo Walkthrough

### Step 1: Hospital Clinical Referral & Auto-Reservation
1. Log in with **Hospital 1** (`gh00046` / `hospital123`).
2. Search for patient `PAT000002` (Priority: HIGH, ICU Required: Yes).
3. Review AI-ranked recommendation: View proximity, available ICU beds, and recommendation reasons (*"Nearby hospital (12 km)", "ICU beds available", "24x7 emergency"*).
4. Create a referral to **Hospital 2** (`GH00119`) requesting an `ICU` bed.
5. Log out and log in as **Hospital 2** (`gh00119` / `hospital123`).
6. Navigate to the **Referrals Inbox**.
7. Click **Accept**: Notice physical bed `ICU-001` is reserved automatically with live badge notification!
8. Source hospital dispatches the ambulance (`IN_TRANSIT`).
9. Destination hospital clicks **Mark Arrived** (bed reservation transitions to `CONFIRMED`) and then **Start Treatment** (`TREATMENT_ACTIVE`).
10. Once treatment concludes, click **Discharge / Complete**: The reserved physical bed is automatically released back to the hospital's available pool!

### Step 2: District Operational Monitoring
1. Log in as **District Admin** (`amritsar_district_admin` / `district123`).
2. Observe the **Overview Tab**: Live aggregate gauges for Amritsar (Total Hospitals, General Available, ICU Available, Active Referrals).
3. Review **Critical Alerts**: Facility-level warnings if any hospital drops below 15% ICU capacity.
4. Explore the **Hospitals Directory**: Filter facilities, inspect equipment badges (Ventilator, CT Scan, 24x7 Emergency).
5. Switch to **Referrals Tab**: Monitor real-time transit and acceptance status within Amritsar.
6. Verify Security: Attempting to query `Ludhiana` data returns a strict `403 Forbidden`.

### Step 3: State Strategic Healthcare Command
1. Log in as **State Admin** (`punjab_admin` / `admin123`).
2. Inspect the **State Overview**: 7 participating districts, 57 hospitals, and statewide bed/ICU occupancy rates.
3. Review the **Inter-District Comparison Table**: Compare Amritsar, Ludhiana, Jalandhar, and Mohali. Identify which districts have high bed strain.
4. Filter by district to analyze localized referral streams.

### Step 4: Central Government National Grid
1. Log in as **Central Admin** (`central_admin` / `central123`).
2. View the **National Overview**: 500 hospitals across India, aggregate nationwide bed capacity, and interstate emergency transfers.
3. Inspect the **State Matrix**: Compare Punjab, Maharashtra, Tamil Nadu, Uttar Pradesh, and Gujarat.
4. Verify Privacy Safeguards: Central tier sees aggregated statistics, preserving patient privacy by default.

---

## 5. Security & Technical Architecture Reference

### Persistence Model
- **Master Data**: Relational SQLite (`data/hospital_system.db`) housing 500 geocoded hospitals and 50,000 synthetic patient records.
- **Dynamic State Machine**: High-speed JSON runtime stores (`referrals.json`, `bed_inventory.json`, `reservations.json`, `users.json`) with atomic file replacements (`temp_path` ➔ `os.replace`) and reentrant locks (`RESERVATION_LOCK = Lock()`).
- **Test Isolation**: Environment variable overrides (`SIH_USERS_PATH`, `SIH_REFERRALS_PATH`, `SIH_BED_INVENTORY_PATH`, `SIH_RESERVATIONS_PATH`) ensure tests run against ephemeral temporary files without ever modifying user or demo data.

### Cryptography & Authorization
- **Passwords**: Salted PBKDF2 with SHA-256 (100,000 iterations, 16-byte cryptographically secure random salt).
- **Session Tokens**: JWT (JSON Web Tokens) with standard HMAC-SHA256 signatures, subject (`sub`), role, and geographic claims with strict 60-minute expiration.
- **Non-Silent Safety Rules**: Under no circumstances does the system silently down-convert an invalid ICU request to General beds. If ICU capacity is depleted, `NO_ICU_AVAILABLE` is returned explicitly.
- **Concurrency Protection**: Critical bed allocation sections are protected by mutex locks; tests confirm 10 concurrent threads competing for 1 bed results in exactly 1 success and 9 clean rejections without double-booking.

---

## 6. Interview Talking Points & Architectural Defense

### Q1: Why four separate administrative tiers instead of standard RBAC?
> *"In a national healthcare system like India's, clinical autonomy must be separated from geographic oversight. A hospital user has write access to patient treatment and bed assignments for their specific hospital only. District administrators need operational monitoring over local facilities and referral bottlenecks. State administrators need inter-district capacity load-balancing. Central authorities need strategic aggregate data for interstate resource mobilization. By baking the `State ➔ District ➔ Hospital` geographic hierarchy into the backend, our APIs enforce tenant isolation at every level."*

### Q2: How did you solve race conditions during bed reservations?
> *"When multiple ambulances or referrals target the last available ICU bed simultaneously, naive database queries suffer from check-then-act race conditions resulting in double-booking. We implemented a synchronized reservation lock that refreshes the live state under the lock, validates physical bed IDs, reserves the specific physical bed (e.g., `ICU-001`), decrements aggregate inventory, and atomically commits the transaction before releasing the lock. We verified this with a 10-thread concurrent stress test where exactly one thread succeeded."*

### Q3: How is patient privacy maintained at higher administrative levels?
> *"Following the principle of data minimization, higher administrative tiers (State and Central) do not receive personally identifiable clinical information (PHI) such as patient names or medical histories. Their endpoints return aggregated sums, utilization percentages, and anonymized referral counts. Identifiable clinical records remain scoped strictly to the source and destination hospital personnel."*

### Q4: If scaling this to national production, what would you evolve?
> *"1. Migrate from atomic JSON stores to a distributed PostgreSQL cluster with row-level locks (`SELECT ... FOR UPDATE`) and Read Replicas for administrative analytics.*  
> *2. Connect the referral exchange to ABDM (Ayushman Bharat Digital Mission) using HL7 FHIR standards for unified electronic health records.*  
> *3. Deploy Redis for sub-millisecond hospital live bed cache and distributed lock management across horizontally scaled FastAPI microservices."*

---

## 7. Startup & Reproduction Commands

### Backend Startup
```bash
cd ~/Desktop/SIH_Hospital_AI
source .venv/bin/activate
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Startup
```bash
cd ~/Desktop/SIH_Hospital_AI/frontend
npm run dev
# Open http://localhost:3000 in your browser
```

### Running Test Suite
```bash
cd ~/Desktop/SIH_Hospital_AI
PYTHONPATH=. .venv/bin/python -m pytest tests/test_auth_and_access.py tests/test_referral_and_bed_lifecycle.py tests/test_admin_hierarchy.py tests/test_security_and_reliability.py -v
```
