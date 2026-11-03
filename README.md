# 🏥 SIH Hospital AI: Smart Hospital Referral & Capacity Management System

> **An Intelligent, Distributed Clinical Decision Support and Multi-Tier Healthcare Referral Coordination Platform**  
> *Developed as an Engineering Prototype for the Smart India Hackathon (SIH) / Final-Year B.Tech CSE Capstone Project.*

[![Python](https://img.shields.io/badge/Python-3.14.3-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16.3.0-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19.2.8-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17.11-336791?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-8.10.3-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.9.0-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38B2AC?style=flat-square&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

---

## 📖 Table of Contents

- [1. Project Overview](#1-project-overview)
- [2. Problem Statement](#2-problem-statement)
- [3. Project Objectives](#3-project-objectives)
- [4. Key Features](#4-key-features)
- [5. System Architecture](#5-system-architecture)
- [6. Technology Stack](#6-technology-stack)
- [7. Four-Tier Dashboard Architecture](#7-four-tier-dashboard-architecture)
  - [Hospital Operational Dashboard](#hospital-operational-dashboard)
  - [District Administration Dashboard](#district-administration-dashboard)
  - [State Health Administration Dashboard](#state-health-administration-dashboard)
  - [Central Government Administration Dashboard](#central-government-administration-dashboard)
- [8. AI-Powered Hospital Recommendation System](#8-ai-powered-hospital-recommendation-system)
  - [Stage A: Deterministic Eligibility Gating](#stage-a-deterministic-eligibility-gating)
  - [Stage B: Heuristic & Machine Learning Hybrid Ranking](#stage-b-heuristic--machine-learning-hybrid-ranking)
  - [Tiered Geographic Fallback Mechanism](#tiered-geographic-fallback-mechanism)
- [9. Patient Referral Lifecycle](#9-patient-referral-lifecycle)
  - [Lifecycle States & Transitions](#lifecycle-states--transitions)
  - [Referral Authorization Matrix](#referral-authorization-matrix)
  - [Bed & ICU Inventory Management](#bed--icu-inventory-management)
- [10. Database Architecture](#10-database-architecture)
- [11. Authentication and Security](#11-authentication-and-security)
  - [PBKDF2 Password Hashing & Timing Defense](#pbkdf2-password-hashing--timing-defense)
  - [JWT Authentication & Redis Token Blocklisting](#jwt-authentication--redis-token-blocklisting)
  - [Redis Distributed Rate Limiting](#redis-distributed-rate-limiting)
  - [Geographic Role-Based Access Control (RBAC)](#geographic-role-based-access-control-rbac)
  - [ACID Transactions & Row-Level Bed Locking](#acid-transactions--row-level-bed-locking)
- [12. Project Directory Structure](#12-project-directory-structure)
- [13. System Requirements](#13-system-requirements)
- [14. Installation and Local Setup](#14-installation-and-local-setup)
- [15. Environment Variables](#15-environment-variables)
- [16. Database Setup](#16-database-setup)
- [17. Redis Setup](#17-redis-setup)
- [18. Backend Execution](#18-backend-execution)
- [19. Frontend Execution](#19-frontend-execution)
- [20. Running Tests](#20-running-tests)
- [21. API Documentation](#21-api-documentation)
- [22. Development Demo Accounts](#22-development-demo-accounts)
- [23. Current Project Status](#23-current-project-status)
- [24. Limitations and Future Scope](#24-limitations-and-future-scope)
  - [Current Limitations](#current-limitations)
  - [Planned Features & Roadmap](#planned-features--roadmap)
- [25. Datasets & Documentation References](#25-datasets--documentation-references)
- [26. Medical and Clinical Disclaimer](#26-medical-and-clinical-disclaimer)
- [27. Author and Project Information](#27-author-and-project-information)

---

## 1. Project Overview

**SIH Hospital AI** is an intelligent, distributed healthcare platform designed to streamline hospital-to-hospital patient referrals, eliminate emergency transfer delays, and prevent critical bed contention across public and private healthcare facilities.

When a primary or secondary healthcare facility cannot provide specialized clinical care or lacks life-support equipment for an unstable patient, transferring that patient to an appropriate tertiary facility is time-critical. Historically, this coordination has relied on manual, ad-hoc telephone calls, word-of-mouth bed availability checks, and uncoordinated transfers that often route emergency patients to facilities lacking critical specialties or ICU beds.

This platform replaces fragmented, paper-based referral processes with a centralized, auditable system. It combines:
- A **Two-Stage Clinical Decision Support (CDS)** engine integrating deterministic medical safety rules and a trained **Random Forest** classification model (34 clinical and infrastructure features).
- A **Two-Phase Bed Reservation** mechanism with transactional row-level locks preventing double-booking during transit.
- A **Distributed Security Layer** powered by Redis 8 (sliding-window rate limiting and instant JWT token revocation).
- A **Four-Tier Dashboard Suite** (Hospital, District, State, Central Government) built with Next.js 16 and React 19.

---

## 2. Problem Statement

Across regional and national healthcare infrastructures, emergency patient transfers encounter severe structural obstacles:

1. **Information Asymmetry:** Referring doctors lack verified, real-time visibility into specialty availability, diagnostic equipment (CT, MRI), and operational ICU beds at neighboring hospitals.
2. **Secondary Transfer Delays:** Patients suffering from acute emergencies (e.g., Acute Myocardial Infarction, Severe Polytrauma, Acute Ischemic Stroke) are frequently sent to unequipped facilities, necessitating hazardous secondary transfers during the critical "golden hour."
3. **Bed Contention & Verbal Holds:** Informal telephone bed holds frequently break down under emergency room pressures, leading to situations where patients arrive via ambulance only to find no available ICU beds.
4. **Lack of Administrative Oversight:** District Health Offices and State Health Departments lack consolidated real-time analytics to monitor regional bed deficits, inter-district transfer loads, and facility overload.
5. **Unauthorized Access & Audit Gaps:** Sensitive medical transfer histories often lack granular, role-based access control and tamper-evident audit logging.

---

## 3. Project Objectives

- **Enforce Medical Safety Gating:** Ensure that patient referrals strictly adhere to non-negotiable clinical prerequisites (specialty alignment, diagnostic equipment availability, and verified ICU capacity).
- **Prevent Bed Double-Booking:** Guarantee bed holds via atomic PostgreSQL transactions and row-level locking (`SELECT ... FOR UPDATE`) during the patient transit window.
- **Provide Explainable AI Guidance:** Provide clinicians with transparent, human-readable medical justifications explaining why specific hospitals were prioritized or disqualified.
- **Enable Hierarchical Healthcare Oversight:** Empower District, State, and Central health authorities with partitioned dashboards reflecting their exact geographic jurisdictions.
- **Harden Distributed System Security:** Implement distributed sliding-window rate limiting, cryptographically secure password hashing (PBKDF2-HMAC-SHA256), and real-time session revocation via Redis.

---

## 4. Key Features

| Category | Highlights | Implementation State |
|---|---|---|
| **AI Recommendation** | Two-stage hybrid engine: Stage A deterministic medical rules + Stage B Random Forest ML model with priority weights. | **Implemented** |
| **Geographic Fallbacks** | Proximity tiers: `LOCAL` ($\le 50$ km), `REGIONAL` ($50-200$ km), and `EXTENDED` ($> 200$ km). | **Implemented** |
| **Bed & ICU Management** | Tracks general, ICU, and emergency beds; two-phase reservation hold (`HELD` $\rightarrow$ `CONFIRMED` $\rightarrow$ `OCCUPIED`). | **Implemented** |
| **Referral Lifecycle** | Structured 7-state progression with role-specific state transition validation and audit timestamps. | **Implemented** |
| **Concurrency Control** | PostgreSQL ACID transactions with row-level locks (`SELECT ... FOR UPDATE`) preventing race conditions. | **Implemented** |
| **Security & RBAC** | PBKDF2-HMAC-SHA256 (100,000 iterations), timing-attack defenses, JWT auth, and Redis token revocation blocklist. | **Implemented** |
| **Distributed Rate Limiting** | Redis-backed sliding-window counter via atomic Lua script (5 attempts / 60 seconds). | **Implemented** |
| **Real-Time Alerts** | In-app emergency notifications for receiving hospitals upon referral creation or bed hold. | **Implemented** |
| **Multi-Tier Dashboards** | Partitioned operational and analytical dashboards for Hospital, District, State, and Central tiers. | **Implemented** |
| **Government Onboarding** | 4-tier hierarchical registration & approval system (Central $\rightarrow$ State $\rightarrow$ District $\rightarrow$ Hospital). | **Planned** |
| **Free Email OTP** | Integration with Brevo (Sendinblue) for registration verification and password reset workflows. | **Planned** |
| **Live GPS Telemetry** | Real-time GPS ambulance telemetry and IoT vehicle tracking (currently uses manual ambulance ID and ETA). | **Planned** |

---

## 5. System Architecture

The following diagram illustrates the interaction between the Next.js presentation layer, the FastAPI backend services, the decision support pipeline, and the distributed data stores:

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Layer (Next.js 16.3.0 / React 19)"]
        UI_HOSP["Hospital Dashboard\n(Triage, Referral, Bed Hold)"]
        UI_DIST["District Dashboard\n(District Hospitals & Capacity)"]
        UI_STATE["State Dashboard\n(Cross-District Regional Flow)"]
        UI_CENTRAL["Central Dashboard\n(Pan-India Health Overview)"]
    end

    subgraph APILayer ["API Gateway & Security Layer (FastAPI)"]
        RATE_MW["Redis Distributed Rate Limiter\n(Sliding-Window Atomic Lua Script)"]
        AUTH_MW["JWT Authentication & RBAC\n(HS256 + Redis Token Blocklist)"]
        ROUTER_CORE["Core Referral Router\n(/hospitals, /referrals, /reservation)"]
        ROUTER_PATIENT["Patient Router\n(/patients/*)"]
        ROUTER_ADMIN["Admin Analytics Router\n(/district/*, /state/*, /central/*)"]
    end

    subgraph BusinessLogic ["Clinical Intelligence & Business Logic Layer"]
        STAGE_A["Stage A: Deterministic Rule Gate\n(Specialty, Beds, Equipment Safety Checks)"]
        STAGE_B["Stage B: Priority-Aware Hybrid Ranker\n(Clinical Heuristics + ML Prediction)"]
        ML_MODEL["Random Forest Classifier\n(34 Clinical & Resource Features)"]
        BED_MGR["Bed Reservation Service\n(Two-Phase Locking & Expiration)"]
        NOTIF_SVC["Emergency Notification Engine\n(In-App Alerts)"]
    end

    subgraph DataInfrastructure ["Data & Caching Infrastructure"]
        PG_DB[("PostgreSQL 17.11 Database\n(10 Normalized Relational Tables\nACID Row-Level Locking)")]
        REDIS_CACHE[("Redis 8.10.3 In-Memory Cache\n(Sliding Window Counters & JWT Blocklist)")]
    end

    UI_HOSP -->|HTTP Bearer JWT| RATE_MW
    UI_DIST -->|HTTP Bearer JWT| RATE_MW
    UI_STATE -->|HTTP Bearer JWT| RATE_MW
    UI_CENTRAL -->|HTTP Bearer JWT| RATE_MW

    RATE_MW --> REDIS_CACHE
    RATE_MW --> AUTH_MW
    AUTH_MW -->|Token Blocklist Check| REDIS_CACHE

    AUTH_MW --> ROUTER_CORE
    AUTH_MW --> ROUTER_PATIENT
    AUTH_MW --> ROUTER_ADMIN

    ROUTER_CORE --> STAGE_A
    STAGE_A -->|Eligible Facilities| STAGE_B
    STAGE_B --> ML_MODEL
    ROUTER_CORE --> BED_MGR
    ROUTER_CORE --> NOTIF_SVC

    ROUTER_PATIENT --> PG_DB
    ROUTER_ADMIN --> PG_DB
    BED_MGR -->|SELECT ... FOR UPDATE| PG_DB
    NOTIF_SVC --> PG_DB
```

---

## 6. Technology Stack

### Backend & Machine Learning
- **Programming Language:** Python `3.14.3`
- **Web Framework:** FastAPI `0.141.1` (Async ASGI, Pydantic v2 validation)
- **ASGI Server:** Uvicorn `0.52.3`
- **Relational Database:** PostgreSQL `17.11` (`sih_hospital_dev`)
- **ORM & Query Engine:** SQLAlchemy `2.0.52` with raw transactional queries
- **Distributed Cache:** Redis `8.10.3` (via `redis-py` `8.1.0`)
- **Machine Learning Library:** Scikit-Learn `1.9.0` (`RandomForestClassifier`)
- **Model Serialization:** Joblib `1.5.3` (Singleton model cache loader)
- **Data Manipulation:** Pandas `3.0.5` & NumPy `2.5.2`
- **Session Tokens:** PyJWT `2.13.0` (HS256 signature enforcement)
- **Test Harness:** Pytest `9.1.1`

### Frontend & User Interface
- **Framework:** Next.js `16.3.0` (App Router, Turbopack)
- **UI Library:** React `19.2.8`
- **Styling Engine:** Tailwind CSS `v4`
- **Programming Language:** TypeScript `5.x`

---

## 7. Four-Tier Dashboard Architecture

SIH Hospital AI provides dedicated user interfaces tailored to each level of healthcare administration:

```
+----------------------------------------------------------------------------------------------------+
|                                    4-TIER DASHBOARD CAPABILITIES                                   |
+--------------------------+-----------------------+------------------------+------------------------+
| Hospital Dashboard       | District Dashboard    | State Dashboard        | Central Dashboard      |
+--------------------------+-----------------------+------------------------+------------------------+
| * Patient Triage & Roster| * District Bed Counts | * Statewide Bed Stats  | * Pan-India Capacity   |
| * AI Hospital Matcher    | * Facility Comparison | * Inter-District Flow  | * 36 States/UTs Status |
| * 2-Phase Bed Hold Lock  | * Local Active Referrals| * Critical ICU Deficits| * National Emergencies |
| * Ambulance ETA Input    | * Facility Capacity % | * Cross-Boundary Alerts| * National Metrics     |
| * Emergency Notification | * Bed Deficit Triggers| * Regional Heatmap     | * System Health Status |
+--------------------------+-----------------------+------------------------+------------------------+
```

### Hospital Operational Dashboard
- **Intended Audience:** Attending Physicians, Triage Nurses, and Emergency Department Staff.
- **Capabilities:**
  - Clinical patient triage input (Condition, Triage Level, Diagnostic Needs).
  - One-click trigger for AI hospital recommendation with medical justifications.
  - Interactive two-phase bed reservation hold with a 30-minute lock window.
  - Manual ambulance identifier assignment and estimated time of arrival (ETA in minutes).
  - Incoming/outgoing referral progression and audible emergency in-app notifications.

### District Administration Dashboard
- **Intended Audience:** Chief Medical Officers (CMO) and District Health Officers.
- **Scope:** Single district jurisdiction (e.g., Amritsar, Ludhiana).
- **Capabilities:**
  - Hospital-by-hospital capacity breakdown across the district.
  - Real-time metrics: general bed occupancy rate, ICU bed reserves, emergency readiness flags.
  - Local intra-district and outbound referral monitoring.

### State Health Administration Dashboard
- **Intended Audience:** State Health Directors and Health Secretaries.
- **Scope:** Single state jurisdiction (e.g., Punjab, Maharashtra).
- **Capabilities:**
  - District-by-district capacity comparison and ranking.
  - Early-warning indicators for districts experiencing severe ICU or ventilator shortages.
  - Cross-district patient movement analytics.

### Central Government Administration Dashboard
- **Intended Audience:** Ministry of Health & Family Welfare (MoHFW) National Health Authorities.
- **Scope:** Pan-India national jurisdiction.
- **Capabilities:**
  - Aggregated metrics: total hospitals, nationwide bed availability, cumulative ICU reserves.
  - State-by-state hospital distribution and real-time active emergency referral traffic.
  - National infrastructure health and service availability monitoring.

---

## 8. AI-Powered Hospital Recommendation System

The recommendation engine functions as an explainable, **Two-Stage Hybrid Clinical Decision Support (CDS)** architecture:

```
Incoming Referral Request (Patient Disease, Triage Priority, Required Tests/Equipment)
                               │
                               ▼
+───────────────────────────────────────────────────────────────────────────────+
| STAGE A: Deterministic Rule-Based Medical Gating (src/utils/referral_rules.py)|
| 1. Specialty Availability Check  -> Must have Cardiology for Heart Attack, etc|
| 2. Mandatory Bed Check           -> Critical priority requires ICU Beds > 0   |
| 3. Mandatory Diagnostics Check   -> Must have CT, MRI, Ventilator if required |
+───────────────────────────────────────────────────────────────────────────────+
                               │
                               ├─► Disqualified Facilities (Logged with medical rationale)
                               │
                               ▼ Eligible Hospital Pool
+───────────────────────────────────────────────────────────────────────────────+
| STAGE B: Priority-Aware Hybrid Scoring (ranking_engine.py & predict.py)       |
| 1. Clinical Heuristic Suitability (0 - 100 points based on capacity & gear)   |
| 2. ML Probability Inference (Random Forest Classifier, 34 Features)           |
| 3. Dynamic Priority Blending:                                                 |
|    - Critical Urgency : 85% Heuristic Score + 15% ML Probability              |
|    - Urgent Priority  : 75% Heuristic Score + 25% ML Probability              |
|    - Stable Priority  : 65% Heuristic Score + 35% ML Probability              |
| 4. Geographic Fallback Partitioning:                                          |
|    - LOCAL (<= 50 km)   -> Primary Recommendation Pool                        |
|    - REGIONAL (50-200 km)-> Regional Fallback Pool                            |
|    - EXTENDED (> 200 km)-> Extended Fallback Pool                             |
+───────────────────────────────────────────────────────────────────────────────+
                               │
                               ▼
Ranked Recommendations with Clinical Explanations & Geographic Rationale
```

### Stage A: Deterministic Eligibility Gating
Before statistical ranking begins, candidate facilities must satisfy strict medical rules:
1. **Medical Specialty Rule:** The hospital must have the specialty department matching the patient's condition (e.g., *Heart Attack* $\rightarrow$ Cardiology; *Kidney Failure* $\rightarrow$ Nephrology/Dialysis; *Trauma* $\rightarrow$ Trauma Unit & Orthopedics).
2. **Critical Care Rule:** If patient priority is `Critical`, candidate facilities with zero available ICU beds are disqualified.
3. **Diagnostic Capability Rule:** Facilities lacking the specific diagnostic imaging or life-support apparatus required by the clinical presentation (CT Scan, MRI, Ventilator, Oxygen Support, Blood Bank) are eliminated.

### Stage B: Heuristic & Machine Learning Hybrid Ranking
For facilities clearing Stage A:
- **Clinical Heuristic Score (0 to 100):** Evaluates resource adequacy, spare bed capacity ratios, emergency readiness, and travel distance.
- **Machine Learning Inference:** The trained `RandomForestClassifier` processes a **34-feature vector** (including distance, available beds, occupancy rate, life support capabilities, one-hot encoded disease categories, and triage urgency) to output an estimated historical success probability ($0.0$ to $1.0$).
- **Priority-Weighted Formula:**
  - $\text{Score}_{\text{Critical}} = (0.85 \times \text{RuleScore}_{\text{norm}} + 0.15 \times \text{MLScore}) \times 100$
  - $\text{Score}_{\text{Urgent}} = (0.75 \times \text{RuleScore}_{\text{norm}} + 0.25 \times \text{MLScore}) \times 100$
  - $\text{Score}_{\text{Stable}} = (0.65 \times \text{RuleScore}_{\text{norm}} + 0.35 \times \text{MLScore}) \times 100$

### Tiered Geographic Fallback Mechanism
Hospitals are partitioned by road distance:
- `LOCAL`: $0 - 50$ km (Default primary recommendation pool).
- `REGIONAL`: $> 50 - 200$ km (Activated automatically if no local facility satisfies clinical criteria).
- `EXTENDED`: $> 200$ km (Emergency statewide fallback for super-specialty interventions).

---

## 9. Patient Referral Lifecycle

The system models the patient transfer process as a finite state machine preventing lost referrals, uncoordinated transfers, and premature bed releases:

```mermaid
stateDiagram-v2
    [*] --> PENDING: Doctor Creates Referral (POST /referrals)
    PENDING --> APPROVED: Target Hospital Accepts (30m Bed Hold Placed)
    PENDING --> REJECTED: Target Hospital Declines (Clinical Reason Stated)
    APPROVED --> IN_TRANSIT: Ambulance Dispatched (Manual ID & ETA Assigned)
    APPROVED --> CANCELLED: Source Hospital Cancels (Bed Hold Freed)
    IN_TRANSIT --> ADMITTED: Patient Arrives at ER (Bed Marked Occupied)
    IN_TRANSIT --> CANCELLED: Patient Diverted / Aborted (Bed Hold Freed)
    ADMITTED --> COMPLETED: Care Finalized & Discharged (Bed Freed)
    REJECTED --> [*]
    CANCELLED --> [*]
    COMPLETED --> [*]
```

### Lifecycle States & Transitions
- `PENDING`: Referral logged by source hospital doctor; awaiting triage review by receiving facility. No bed reserved.
- `APPROVED`: Receiving hospital accepts the patient; an atomic **30-minute reservation hold** (`HELD`) is placed on the target bed type.
- `REJECTED`: Receiving hospital declines transfer due to capacity constraints or clinical criteria; reason logged and notified to source doctor.
- `IN_TRANSIT`: Patient is onboard the transfer ambulance; manual ambulance identifier and estimated minutes to arrival (ETA) are attached. Bed status transitions to `CONFIRMED`.
- `ADMITTED`: Patient physically arrives at the receiving emergency room; the bed status transitions from reserved to `OCCUPIED`.
- `CANCELLED`: Transfer aborted due to patient stabilization or alternate routing; bed lock is instantly released back to the general pool.
- `COMPLETED`: Patient receives treatment and is officially discharged; bed record is marked `AVAILABLE` and sanitized.

### Referral Authorization Matrix
Access to a referral is strictly bounded by the participant institutions:

| Participant Role | Permitted Status Transitions |
|---|---|
| **Destination (Receiving) Hospital** | `APPROVED`, `REJECTED`, `ADMITTED`, `COMPLETED` |
| **Source (Referring) Hospital** | `IN_TRANSIT`, `CANCELLED` |
| **Unauthorized Outside Hospital** | **Access Denied (`HTTP 403 Forbidden`)** |

Every referral record maintains an auditable timestamp timeline:
`created_at` $\rightarrow$ `accepted_at` $\rightarrow$ `in_transit_at` $\rightarrow$ `admitted_at` $\rightarrow$ `completed_at` (or `rejected_at` / `cancelled_at`).

### Bed & ICU Inventory Management
- Tracks physical beds across three categories: `GENERAL`, `ICU`, and `EMERGENCY`.
- Validates hospital identity, patient identity, requested bed category, and active reservation state.
- Automatically releases reservation holds if an attached referral is cancelled or rejected.

---

## 10. Database Architecture

The relational schema is implemented in **PostgreSQL 17.11** (`sih_hospital_dev`) with **10 normalized tables** managed via SQLAlchemy 2.0 ORM:

```
+----------------------------------------------------------------------------------------------------+
|                                      POSTGRESQL 17 SCHEMA MAP                                      |
+--------------------------+-----------------------+------------------------+------------------------+
| Administrative & Users   | Clinical Operations   | Resource Management    | Audit & Notifications  |
+--------------------------+-----------------------+------------------------+------------------------+
| * roles                  | * patients            | * beds                 | * notifications        |
| * users                  | * hospital_visits     | * bed_reservations     | * audit_logs           |
| * hospitals              | * referrals           |                        |                        |
+--------------------------+-----------------------+------------------------+------------------------+
```

### Key Relational Tables
1. **`roles`:** Administrative authorization roles (`CENTRAL_ADMIN`, `STATE_ADMIN`, `DISTRICT_ADMIN`, `HOSPITAL`).
2. **`hospitals`:** Institutional profiles, geographic coordinates, bed counters, clinical specialty flags (`cardiology`, `neurology`, `oncology`), and equipment flags (`ct_scan`, `mri`, `ventilator`, `oxygen_support`).
3. **`users`:** Staff and administrative accounts, hashed passwords, role assignments, and geographic jurisdiction scoping (`state`, `district`, `hospital_id`).
4. **`patients`:** Master patient index, demographic records, and recorded baseline medical conditions.
5. **`hospital_visits`:** Inpatient admission records, triage category, admission/discharge timestamps, and physician notes.
6. **`beds`:** Physical bed records (`GENERAL`, `ICU`, `EMERGENCY`), current occupancy status (`AVAILABLE`, `RESERVED`, `OCCUPIED`), and linked `patient_id`.
7. **`referrals`:** Inter-hospital transfer records, source and destination foreign keys, clinical priority, specialty requested, ambulance ID, ETA minutes, and lifecycle status.
8. **`bed_reservations`:** Active and historical bed reservation holds, expiration timestamps (default 30 minutes), and status (`HELD`, `CONFIRMED`, `OCCUPIED`, `RELEASED`, `EXPIRED`).
9. **`notifications`:** Emergency hospital alert feed, priority rating (`NORMAL`, `URGENT`, `CRITICAL`), read/unread states, and creation timestamps.
10. **`audit_logs`:** Append-only security audit trail recording user IDs, IP addresses, entity types, actions taken, and structured JSON payloads.

---

## 11. Authentication and Security

### PBKDF2 Password Hashing & Timing Defense
- Passwords are encrypted using **PBKDF2-HMAC-SHA256** with **100,000 iterations** and a 16-byte cryptographically secure salt (`secrets.token_hex(16)`).
- To eliminate **timing attacks** and username enumeration, login requests for invalid usernames execute a dummy hash comparison (`DUMMY_PBKDF2_HASH`), ensuring identical server latency regardless of whether a user exists.

### JWT Authentication & Redis Token Blocklisting
- Stateless authentication uses **HS256** signed JSON Web Tokens containing user ID, role, and geographic claims.
- When a user logs out (`POST /logout`), the token identifier (`jti`) is written to **Redis** with a TTL matching the token's remaining lifespan. The `require_current_user` FastAPI dependency verifies this blocklist on every incoming request, ensuring instant revocation.

### Redis Distributed Rate Limiting
- Configured in `src/auth/rate_limiter.py` to prevent brute-force credential stuffing across multiple backend workers.
- Uses an atomic Redis Lua script executing a sliding-window counter:
  - Default policy: **5 failed attempts per 60 seconds** per client IP and username.
  - Exceeding the threshold immediately triggers an `HTTP 429 Too Many Requests` response with a `Retry-After` header.

### Geographic Role-Based Access Control (RBAC)
- **Central Admin:** Unrestricted pan-India read access.
- **State Admin:** Bound strictly to records matching `user.state`. Inquiries outside the state trigger `HTTP 403 Forbidden`.
- **District Admin:** Bound strictly to `user.state` and `user.district`.
- **Hospital Staff:** Restricted strictly to their own `user.hospital_id`. Staff cannot inspect patient charts or manipulate beds belonging to outside facilities.

### ACID Transactions & Row-Level Bed Locking
- All bed reservation requests execute inside PostgreSQL transactions using `SELECT ... FOR UPDATE` row locks.
- If concurrent requests contest the last remaining bed, subsequent transactions block until the first commits. Subsequent queries read the updated availability of 0 and return an `HTTP 409 Conflict: Insufficient Beds Available`, eliminating race conditions and double bookings.

---

## 12. Project Directory Structure

```
SIH_Hospital_AI/
├── data/                               # Project datasets and runtime stores
│   ├── bed_inventory.json              # Bed inventory runtime cache
│   ├── hospitals.csv                   # Synthetic hospital database
│   ├── patients.csv                    # Synthetic patient demographic dataset
│   └── runtime/                        # Runtime JSON state files
│       ├── referrals.json
│       └── users.json                  # Pre-seeded development users
├── datasets/final/                     # Baseline clinical referral training data
│   ├── hospitals.csv
│   ├── patients.csv
│   └── referrals.csv
├── docs/                               # System documentation and medical assumptions
│   ├── data_dictionary.md              # Dataset schema definitions
│   └── medical_assumptions.md          # Clinical assumptions & triage rules
├── frontend/                           # Next.js 16.3.0 frontend application
│   ├── app/
│   │   ├── layout.tsx                  # Global HTML shell & CSS import
│   │   ├── page.tsx                    # Dynamic dashboard router based on role
│   │   └── globals.css                 # Tailwind CSS directives
│   ├── components/
│   │   ├── CentralDashboard.tsx        # National administrative overview
│   │   ├── StateDashboard.tsx          # State healthcare administration
│   │   ├── DistrictDashboard.tsx       # District health officer dashboard
│   │   ├── HospitalDashboard.tsx       # Hospital operational & triage dashboard
│   │   └── shared/                     # Reusable UI widgets (Header, StatCard, etc.)
│   ├── lib/                            # API client, auth token store, TypeScript types
│   ├── package.json                    # Frontend dependencies (Next 16, React 19, Tailwind)
│   └── tsconfig.json                   # TypeScript configuration
├── migrations/                         # PostgreSQL SQL migration scripts
│   ├── 001_initial_postgresql_schema.sql
│   ├── 001_rollback_postgresql_schema.sql
│   └── 002_referral_workflow_and_notifications.sql
├── models/                             # Trained machine learning model weights
│   └── referral_success_model.joblib   # Scikit-learn Random Forest model artifact
├── notebooks/                          # Jupyter analysis and model training notebooks
├── scripts/                            # Administrative and migration scripts
│   ├── evaluate_recommendation_engine.py
│   ├── migrate_to_postgres.py
│   ├── verify_live_postgres_concurrency.py
│   └── verify_redis_concurrency.py
├── src/                                # Backend source code (FastAPI)
│   ├── api/
│   │   ├── main.py                     # Root API application & core referral routes
│   │   ├── patient_routes.py           # Patient admission and clinical visit routes
│   │   ├── admin_routes.py             # District, State, and Central analytics routes
│   │   └── schemas.py                  # Pydantic v2 validation transfer models
│   ├── auth/
│   │   ├── auth_store.py               # PBKDF2 hashing, user lookup, timing defense
│   │   ├── authorization.py            # Geographic RBAC access checks
│   │   ├── dependencies.py             # FastAPI security dependencies
│   │   ├── jwt_utils.py                # JWT signing & Redis blocklist checking
│   │   └── rate_limiter.py             # Redis sliding-window rate limiting
│   ├── database/
│   │   ├── db_manager.py               # SQLAlchemy engine & transaction management
│   │   ├── pg_models.py                # Declarative relational schema (10 tables)
│   │   └── pg_repository.py            # Data access repository with row-level locks
│   ├── prediction/
│   │   ├── bed_reservation.py          # Bed hold logic and reservation state machine
│   │   ├── feature_builder.py          # 34-feature extraction pipeline
│   │   ├── notification_store.py       # Hospital alert management
│   │   ├── predict.py                  # Random Forest model singleton and scoring
│   │   ├── ranking_engine.py           # Priority-aware hybrid ranking algorithm
│   │   ├── recommendation.py           # Clinical explanation generator
│   │   └── referral_engine.py          # Referral progression state machine
│   └── utils/
│       └── referral_rules.py           # Deterministic medical gating rules
├── tests/                              # Automated Pytest test suite (132 tests)
│   ├── test_admin_hierarchy.py
│   ├── test_ai_recommendation_evaluation.py
│   ├── test_auth_and_access.py
│   ├── test_end_to_end_referral_workflow.py
│   ├── test_live_postgresql_integration.py
│   ├── test_patient_data_and_referral_history.py
│   ├── test_postgresql_migration_and_transactions.py
│   ├── test_redis_distributed_security.py
│   ├── test_referral_and_bed_lifecycle.py
│   ├── test_security_and_reliability.py
│   └── test_ui_defects_and_serialization.py
├── pytest.ini                          # Pytest configuration
├── README.md                           # Project documentation
└── SIH_HOSPITAL_AI_COMPLETE_SYSTEM_AUDIT.md # Master Technical Audit Report
```

---

## 13. System Requirements

### Hardware Requirements
- **CPU:** 64-bit multi-core processor (Intel Core i5/i7/Apple Silicon M-Series or AMD Ryzen equivalent).
- **Memory (RAM):** Minimum 8 GB (16 GB recommended for running Backend, Frontend, PostgreSQL, and Redis simultaneously).
- **Disk Space:** Minimum 5 GB free disk storage.

### Software Dependencies
- **Operating System:** macOS (Sonoma/Sequoia), Linux (Ubuntu 22.04+), or Windows 11 (via WSL2).
- **Python:** Version `3.11` to `3.14` (Verified on Python `3.14.3`).
- **Node.js:** Version `20.x` or `22.x` with `npm` `10+`.
- **PostgreSQL:** Version `16.x` or `17.x` (Verified on PostgreSQL `17.11`).
- **Redis Server:** Version `7.x` or `8.x` (Verified on Redis `8.10.3`).

---

## 14. Installation and Local Setup

Follow these commands to configure the development environment locally:

### 1. Clone the Repository
```bash
git clone https://github.com/codeswith-pawan/SIH_Hospital_AI.git
cd SIH_Hospital_AI
```

### 2. Set Up Python Virtual Environment
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate       # On macOS / Linux
# .venv\Scripts\activate        # On Windows

# Upgrade pip and packaging tools
pip install --upgrade pip setuptools wheel

# Install required backend dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary redis scikit-learn pandas numpy joblib pyjwt pytest httpx
```

### 3. Set Up Next.js Frontend
```bash
cd frontend
npm install
cd ..
```

---

## 15. Environment Variables

Create a `.env` file in the project root. For development, configure the following placeholders:

```env
# ==============================================================================
# SIH HOSPITAL AI: DEVELOPMENT ENVIRONMENT CONFIGURATION
# ==============================================================================

# Application Environment Mode (development / testing / production)
SIH_ENV=development
ENVIRONMENT=development

# Database Connection (PostgreSQL)
# Format: postgresql+psycopg2://<user>:<password>@<host>:<port>/<dbname>
SIH_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/sih_hospital_dev
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/sih_hospital_dev

# Database Connection Pool Settings
SIH_DB_POOL_SIZE=10
SIH_DB_MAX_OVERFLOW=20
SIH_DB_POOL_TIMEOUT=30
SIH_DB_POOL_RECYCLE=1800

# Redis Cache & Rate Limiting Connection
SIH_REQUIRE_REDIS=true
SIH_REDIS_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0

# Authentication & JWT Configuration
# Minimum 32 characters in production environments
SIH_JWT_SECRET=super_secret_development_key_minimum_32_characters_long_for_security
SIH_LOGIN_MAX_ATTEMPTS=5
SIH_LOGIN_WINDOW_SECONDS=60

# Data Storage Paths (Optional Overrides)
SIH_USERS_PATH=data/runtime/users.json
SIH_BED_INVENTORY_PATH=data/bed_inventory.json
SIH_RESERVATIONS_PATH=data/reservations.json
SIH_REFERRALS_PATH=data/runtime/referrals.json
SIH_NOTIFICATIONS_PATH=data/runtime/notifications.json
```

---

## 16. Database Setup

Ensure PostgreSQL is running locally on port 5432:

```bash
# Verify PostgreSQL status (macOS Homebrew)
brew services list | grep postgresql

# Start PostgreSQL service if inactive
brew services start postgresql@17

# Create the application development database
createdb sih_hospital_dev
```

Apply the SQL migration scripts to construct the 10 relational tables:

```bash
# Apply initial schema migration
psql -d sih_hospital_dev -f migrations/001_initial_postgresql_schema.sql

# Apply referral workflow & notifications migration
psql -d sih_hospital_dev -f migrations/002_referral_workflow_and_notifications.sql

# (Optional) Seed database from existing datasets
python scripts/migrate_to_postgres.py
```

---

## 17. Redis Setup

Ensure Redis Server is running locally on port 6379:

```bash
# Verify Redis status (macOS Homebrew)
brew services list | grep redis

# Start Redis service if inactive
brew services start redis

# Test Redis connectivity
redis-cli ping
# Expected response: PONG
```

---

## 18. Backend Execution

Start the FastAPI application using `uvicorn`:

```bash
# Activate virtual environment
source .venv/bin/activate

# Launch ASGI server on port 8000
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

- **API Base URL:** `http://localhost:8000`
- **Interactive Swagger Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **Health Check Endpoint:** `http://localhost:8000/health`

---

## 19. Frontend Execution

In a separate terminal, launch the Next.js development server:

```bash
cd frontend
npm run dev
```

- **Web Application URL:** `http://localhost:3000`
- **Build Production Bundle:** `npm run build`
- **Run Production Server:** `npm run start`

---

## 20. Running Tests

The test suite validates database integration, multi-process concurrency, distributed rate limiting, referral workflows, and the AI recommendation pipeline.

### Execute Test Suite
```bash
# Run pytest from the project root
source .venv/bin/activate
pytest -v
```

### Verified Test Suite Status (November 3, 2026)

| Test Module | Tests | Status | Focus Area |
|---|---|---|---|
| `tests/test_admin_hierarchy.py` | 8 | Passed | District, State, Central RBAC isolation |
| `tests/test_ai_recommendation_evaluation.py`| 13 | Passed | Two-stage gating & ML candidate scoring |
| `tests/test_auth_and_access.py` | 12 | Passed | PBKDF2 hashing & timing attack defense |
| `tests/test_end_to_end_referral_workflow.py`| 21 | Passed | Complete referral lifecycle transitions |
| `tests/test_live_postgresql_integration.py` | 12 | Passed | PostgreSQL connection pool & constraints |
| `tests/test_patient_data_and_referral_history.py`| 9 | Passed | Patient lookup & referral timeline audit |
| `tests/test_postgresql_migration_and_transactions.py`| 12 | Passed | Atomic transactions & rollback verification |
| `tests/test_recommendation.py` | 3 | Passed | Recommendation explanation generator |
| `tests/test_redis_distributed_security.py` | 12 | Passed | Distributed sliding-window rate limiting |
| `tests/test_referral_and_bed_lifecycle.py` | 17 | Passed | Two-phase bed reservation locking |
| `tests/test_referral_engine.py` | 1 | Passed | Referral engine state machine |
| `tests/test_referral_rules.py` | 2 | Passed | Medical specialty and equipment rules |
| `tests/test_security_and_reliability.py` | 9 | Passed | JWT secret validation & token blocklist |
| `tests/test_ui_defects_and_serialization.py`| 2 Passed, 1 Failed | Disclosed Below | UI state serialization & inventory truth |
| **Total** | **131 Passed, 1 Failed** | **99.2% Passing** | 132 Total Tests Collected |

> **Transparent Test Failure Disclosure:**  
> The single failing test (`test_ui_defects_and_serialization.py::test_inventory_counters_truth_consistency`) asserts that hospital `GH00046` has 16 available ICU beds, but 15 are found. This occurs because an active bed reservation was created during an earlier end-to-end integration test against `data/bed_inventory.json`. This demonstrates file-based state drift and reinforces why PostgreSQL transactions are being established as the sole source of truth.

---

## 21. API Documentation

FastAPI automatically serves interactive API documentation at `/docs` and `/redoc`. The backend exposes **44 total endpoints** across major modules:

| Endpoint | HTTP Method | Authorized Roles | Purpose |
|---|---|---|---|
| `/health` | `GET` | Public | System status check (verifies PostgreSQL and Redis) |
| `/login` | `POST` | Public (Rate Limited)| Authenticate user credentials and return signed JWT |
| `/logout` | `POST` | Authenticated | Revoke active JWT session via Redis blocklist |
| `/hospitals` | `GET` | Public / Doctors | Execute Two-Stage Hybrid Recommendation for triage input |
| `/referrals` | `POST` | Hospital Staff | Create active referral and place atomic bed reservation |
| `/referrals/{id}` | `GET` | Hospital / Admin | Retrieve referral details and audit timeline |
| `/referrals/{id}/status/{status}` | `POST` | Hospital Staff | Transition referral lifecycle state (`APPROVED`, `IN_TRANSIT`, etc.) |
| `/reservation/{hid}/{pid}/reserve`| `POST` | Hospital Staff | Place atomic 30-minute reservation hold on hospital bed |
| `/hospitals/{id}/inventory` | `GET` | Hospital Staff | Fetch real-time available beds, ICU counts, and equipment status |
| `/hospitals/{id}/notifications`| `GET`| Hospital Staff | Fetch real-time emergency clinical alerts |
| `/patients/hospital/{id}` | `GET` | Scoped Hospital Staff| List patient roster for authorized hospital |
| `/district/overview` | `GET` | District / State / Central | District-wide hospital capacity and referral analytics |
| `/state/overview` | `GET` | State / Central Admin | Statewide aggregated bed stats and inter-district flow |
| `/central/overview` | `GET` | Central Admin | Pan-India healthcare capacity summary |

---

## 22. Development Demo Accounts

> ⚠️ **DEVELOPMENT TESTING ONLY:**  
> The following accounts are pre-seeded in `data/runtime/users.json` for local evaluation, testing, and UI demonstration. **Never use these default credentials in production environments.**

| Username | Password | Role | Assigned Jurisdiction | Description |
|---|---|---|---|---|
| `central_admin` | `central123` | `CENTRAL_ADMIN` | Pan-India (National) | Ministry of Health National Health Administrator |
| `punjab_admin` | `admin123` | `STATE_ADMIN` | State: Punjab | Punjab State Health Department Director |
| `maharashtra_admin`| `admin123`| `STATE_ADMIN` | State: Maharashtra | Maharashtra State Health Department Director |
| `amritsar_district_admin`| `district123`| `DISTRICT_ADMIN` | Amritsar, Punjab | Amritsar District Chief Medical Officer |
| `ludhiana_district_admin`| `district123`| `DISTRICT_ADMIN` | Ludhiana, Punjab | Ludhiana District Chief Medical Officer |
| `gh00046` | `hospital123` | `HOSPITAL` | Amritsar, Punjab | Regional Amritsar Medical College Hospital Staff |
| `gh00119` | `hospital123` | `HOSPITAL` | Amritsar, Punjab | District Amritsar Medical College Hospital Staff |
| `gh_test_other` | `hospital123`| `HOSPITAL` | Ludhiana, Punjab | Test Other Hospital Staff |

---

## 23. Current Project Status

- **Status:** **Advanced Engineering Prototype / Research System**
- **Academic Context:** Developed as a capstone engineering project for the **Smart India Hackathon (SIH)** / Final-Year B.Tech Computer Science and Engineering (CSE) curriculum.
- **Maturity Level:**
  - Prototype-ready for demonstration, simulation, and academic evaluation.
  - Multi-process PostgreSQL transactional concurrency and Redis rate limiting independently verified.
  - Not certified for real-world autonomous clinical decision-making.

---

## 24. Limitations and Future Scope

### Current Limitations
1. **Synthetic Data Dependency:** Evaluated using synthetic hospital capabilities and patient triage datasets. Not connected to real hospital EHRs.
2. **Static User Store:** User authentication currently resolves against `data/runtime/users.json`. The PostgreSQL `users` table exists but requires unification.
3. **Manual Ambulance Telemetry:** Ambulance tracking currently relies on manual ambulance ID assignment and physician-estimated ETA minutes. **Live GPS telemetry is not implemented.**
4. **No Automated User Registration:** Institutional accounts are pre-seeded; no self-registration or document upload portal is currently operational.
5. **No Password Recovery:** Forgot-password and self-service password reset endpoints are not yet implemented.

### Planned Features & Roadmap
- **Hierarchical Government Registration (Planned):** A 4-tier onboarding workflow (Central $\rightarrow$ State $\rightarrow$ District $\rightarrow$ Individual Hospital) with document verification (medical licenses, fire safety NOCs) and privacy-scrubbed public tracking.
- **Free Email OTP Verification (Planned):** Integration with Brevo (Sendinblue) for free-tier email verification and password recovery.
- **FHIR / ABDM Interoperability (Planned):** Integration with Ayushman Bharat Digital Mission (ABDM) protocols for standardized Health ID (ABHA) and Electronic Health Record (EHR) data sharing.
- **Real-Time GPS Telemetry (Planned):** IoT and GPS tracker integration for live ambulance position tracking on interactive maps.
- **WebSocket Notifications (Planned):** Bidirectional WebSocket channels for instantaneous push alerts across clinical workstations.

---

## 25. Datasets & Documentation References

The project includes structured data dictionaries, synthetic datasets, and technical audit documentation:

- [`docs/data_dictionary.md`](docs/data_dictionary.md) — Definitions for hospital, patient, and referral dataset fields.
- [`docs/medical_assumptions.md`](docs/medical_assumptions.md) — Clinical assumptions, triage rules, and specialty mappings.
- [`SIH_HOSPITAL_AI_COMPLETE_SYSTEM_AUDIT.md`](SIH_HOSPITAL_AI_COMPLETE_SYSTEM_AUDIT.md) — 20-section master architectural audit, gap analysis, and implementation roadmap.
- `datasets/final/` — Synthetic benchmark datasets (`hospitals.csv`, `patients.csv`, `referrals.csv`).

---

## 26. Medical and Clinical Disclaimer

> ⚠️ **MEDICAL & CLINICAL DISCLAIMER:**  
> **SIH Hospital AI is an academic research and engineering prototype.**  
> It has **NOT** been certified as a medical device under ISO 13485, IEC 62304, or the Central Drugs Standard Control Organisation (CDSCO) guidelines.  
> It is **NOT deployed in real-world hospitals**, does not process real protected health information (PHI), and must **NEVER** be used as the sole or autonomous basis for actual clinical diagnosis, patient management, or emergency healthcare dispatch. All transfer decisions must be validated by licensed medical professionals.

---

## 27. Author and Project Information

- **Author:** Pawan Kumar Sharma ([@codeswith-pawan](https://github.com/codeswith-pawan))
- **Project Repository:** [codeswith-pawan/SIH_Hospital_AI](https://github.com/codeswith-pawan/SIH_Hospital_AI)
- **Track:** Healthcare & Biomedical Technology / Smart India Hackathon (SIH)
- **Domain:** Final-Year B.Tech Computer Science and Engineering (CSE) Capstone Project
