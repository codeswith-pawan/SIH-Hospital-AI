# SIH HOSPITAL AI — PHASE 4D READ-ONLY AUDIT REPORT
## Notifications, Monitoring, Telemetry & Background Worker Infrastructure

**Audit Date:** 2026-11-11  
**Repository Path:** `/Users/pawankumarsharma/Desktop/SIH_Hospital_AI`  
**Git Branch:** `master` (Commit `460af41`)  
**Git Stash Status:** `stash@{0}` intact  
**Databases Inspected:** `sih_hospital_dev` (read-only verification: 500 hospitals, 8 users), `sih_hospital_phase1_run_test`  
**Audit Scope:** Read-Only Architectural & Implementation Audit of Phase 4D (Notifications, Monitoring & Telemetry)  
**Audit Verdict:** **READY FOR IMPLEMENTATION** (Architectural blueprint established; zero destructive changes permitted during audit)

---

## 1. Executive Summary

A comprehensive, strictly read-only architectural audit of Phase 4D was executed against the SIH Hospital AI codebase. The audit inspected the backend persistence layer, transactional outbox mechanism, background workers, email delivery providers, API observability/metrics, logging middleware, and frontend notification surfaces.

### Core Audit Findings
1. **Foundation Maturity (Transactional Outbox & SMTP):** The project already possesses a production-grade transactional outbox (`RegistrationEmailOutbox`) in PostgreSQL with row-level locking (`with_for_update(skip_locked=True)`), exponential backoff, worker lease timeouts (300s), and a clean provider abstraction (`BaseEmailProvider`, `SMTPEmailProvider`, `SimulatedEmailProvider`).
2. **Notification Event Vacuum (Scenarios 1, 2, 3, 6, 7, 8, 9, 10):** While the outbox worker functions correctly for hospital account activation (`ACCOUNT_ACTIVATION`), **8 of the 10 critical operational lifecycle scenarios currently generate ZERO email or outbox events**, and direct bed lifecycle operations (outside legacy referral transitions) create no in-app notifications.
3. **Critical Architectural Gap — Unmanaged Bed Expiration (Scenario 10):** Expired bed reservations (`BedReservation.expires_at < now()`) remain reserved and unavailable in inventory indefinitely unless an external HTTP client manually hits the `POST /hospitals/{hid}/reservations/{pid}/expire` API endpoint. There is **no background expiration worker or scheduled reaper**.
4. **Worker Observability Blindness:** In containerized production deployments (`docker-compose.prod.yml`), the outbox worker runs in an isolated container. The backend `/metrics` endpoint inspects in-process worker state via `get_active_worker_metrics()`, which constantly returns `"status": "NOT_RUNNING_IN_PROCESS"`. Operators have no visibility into worker heartbeats, queue lag, or dead letters.
5. **Administrative UI Disconnect:** Administrative dashboards (Central, State, District) have **zero notification integration**, leaving reviewers and health officers blind to pending registration approvals, compliance alerts, or escalation deadlines without manual polling.

---

## 2. Existing Architecture & Component Map

The following table summarizes the existing components, their responsibilities, and architectural boundaries:

| Component | File Path | Current Status | Architectural Role |
| :--- | :--- | :--- | :--- |
| **Notification Model** | `src/database/pg_models.py` | Active | Stores in-app alerts scoped strictly to `hospital_id` (`ForeignKey("hospitals.hospital_id")`). Lacks recipient user ID or administrative jurisdiction scoping. |
| **Outbox Model** | `src/database/pg_models.py` | Active | `RegistrationEmailOutbox` records queued email alerts with payload, retry count, status, lease tracking, and timestamps. |
| **Outbox Service** | `src/services/email_outbox_service.py` | Active | Manages enqueueing, atomic transaction inclusion, lease acquisition (`SKIP LOCKED`), exponential backoff, and dead-letter marking. |
| **Outbox Worker** | `src/workers/outbox_worker.py` | Active | Autonomous background daemon polling `registration_email_outbox`. Recovers dead leases, dispatches emails via provider, and tracks in-memory metrics. |
| **Email Providers** | `src/services/email_service.py` | Active | Concrete implementations for SMTP (Brevo/TLS) and Simulation mode with sender rate limits and payload sanitization. |
| **Observability API** | `src/api/observability.py` | Active | Exposes `/health/live` (process UP), `/health/ready` (DB ping, Redis ping, config checks), and `/metrics` (Prometheus/JSON operational metrics). |
| **Security Middleware** | `src/api/observability.py` | Active | `ProductionSecurityAndLoggingMiddleware` generates `X-Request-ID`, enforces HTTPS/HSTS, and structures JSON request/response logs. |
| **In-App Store** | `src/prediction/notification_store.py` | Active | Repository adapter for inserting and querying in-app hospital alerts. |
| **Referral Repository** | `src/database/pg_repository.py` | Active | Enforces in-app notification creation during referral state transitions (`NEW_REFERRAL`, `PATIENT_ARRIVED`, etc.). |
| **Registration Service**| `src/services/registration_service.py` | Active | Manages application state transitions but currently fails to enqueue outbox notifications on submission or correction requests. |
| **Account Provisioning**| `src/services/account_provisioning_service.py` | Active | Provisions approved applications and atomically enqueues `ACCOUNT_ACTIVATION` outbox events. |
| **Production Compose** | `docker-compose.prod.yml` | Partial | Defines `app`, `db`, `redis`, and `outbox_worker`. Lacks container healthchecks for `outbox_worker`. |
| **Hospital Frontend** | `frontend/components/HospitalDashboard.tsx` | Active | Integrates `NotificationPanel.tsx` with unread badge counter, polling every 30 seconds. |
| **Admin Frontends** | `frontend/components/{Central,State,District}Dashboard.tsx` | Missing | Zero notification UI or polling integration present. |

---

## 3. Actual Notification Event-Flow Analysis (Scenarios 1 – 10)

Each of the ten mandatory lifecycle scenarios was evaluated against the actual code execution path:

| # | Trigger Event | Source Component | Target Audience | In-App Alert | Outbox / Email Alert | Audit Status | Root Cause / Implementation Gap |
| :- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **1** | **Applicant Registration Submission** | `registration_service.submit_application` | Applicant & District Admin | ❌ No | ❌ No | **FAIL** | Status transitions to `SUBMITTED`, but no email outbox entry is queued for the applicant, and no notification is dispatched to district reviewers. |
| **2** | **Correction Required** | `registration_service.request_corrections` | Applicant | ❌ No | ❌ No | **FAIL** | Status transitions to `ACTION_REQUIRED`, but applicant receives no email with reviewer comments/deficiencies. |
| **3** | **Registration Approval** | `registration_service.approve_application` | Reviewers & Applicant | ❌ No | ⚠️ Partial | **PARTIAL** | Intermediate approvals (District $\rightarrow$ State, State $\rightarrow$ Central) create no reviewer alerts. Final Central approval triggers account provisioning which queues email (**PASS** for activation email, **FAIL** for approval alerts). |
| **4** | **Account Activation Initiated** | `account_provisioning_service.provision_approved_application` | Hospital Admin | N/A | ✅ Yes | **PASS** | Atomically enqueues `ACCOUNT_ACTIVATION` into `registration_email_outbox` in the provisioning DB transaction. |
| **5** | **Referral Created** | `pg_repository.create_referral_direct` | Receiving Hospital | ✅ Yes | ❌ No | **PARTIAL** | Inserts `Notification(event_type="NEW_REFERRAL")` for destination hospital. No urgent email/SMS outbox event created for critical referrals. |
| **6** | **Bed Reservation Created** | `pg_repository.reserve_bed_direct` | Hospital Staff & Patient | ⚠️ Partial | ❌ No | **PARTIAL** | Referral-linked reservation is notified via `NEW_REFERRAL`. Direct bed reservation inserts `AuditLog` but **zero** `Notification` or outbox alert. |
| **7** | **Reservation Confirmed** | `pg_repository.confirm_bed_direct` | Referring Hospital & Staff | ⚠️ Partial | ❌ No | **PARTIAL** | Referral-linked confirmation notifies source hospital (`PATIENT_ARRIVED`). Direct bed confirmation creates `AuditLog` but **no** in-app or outbox notification. |
| **8** | **Patient Admitted / Bed Occupied**| `pg_repository.occupy_bed_direct` | Referring Hospital & Staff | ⚠️ Partial | ❌ No | **PARTIAL** | Referral-linked occupancy notifies source hospital (`TREATMENT_STARTED`). Direct bed occupancy creates `AuditLog` but **no** in-app or outbox notification. |
| **9** | **Patient Discharged** | `pg_repository.discharge_patient_direct` | Referring Hospital & Staff | ⚠️ Partial | ❌ No | **PARTIAL** | Referral-linked discharge notifies source hospital (`REFERRAL_COMPLETED`). Direct bed discharge creates `AuditLog` but **no** in-app or outbox notification. |
| **10**| **Reservation Expired** | External API hit only (`POST /expire`) | Hospital Staff | ❌ No | ❌ No | **FAIL (CRITICAL)** | **No background worker exists to detect or expire reservations.** When expired manually via API, bed inventory adjusts, but no notification is generated. |

---

## 4. Outbox & Worker Reliability Assessment

### A. Atomicity & Concurrency Safety
- **Verdict: PASS**
- `src/services/email_outbox_service.py` executes all queue insertions using caller-provided SQLAlchemy sessions:
  ```python
  # Atomically committed with domain state changes
  outbox_entry = RegistrationEmailOutbox(...)
  db.add(outbox_entry)
  ```
- Worker concurrency is strictly protected against race conditions using PostgreSQL row-level locks:
  ```python
  stmt = (
      select(RegistrationEmailOutbox)
      .filter(...)
      .with_for_update(skip_locked=True)
      .limit(batch_size)
  )
  ```
  This guarantees that multiple worker replicas can run concurrently without processing duplicate messages.

### B. Worker Lease Recovery & Crash Resilience
- **Verdict: PASS**
- Leases are acquired with a lease duration of 300 seconds (`lease_timeout_seconds=300`).
- If an outbox worker container crashes or is abruptly killed (OOM/SIGKILL), `recover_stale_leases()` resets stale `PROCESSING` rows back to `PENDING` if `leased_until < now()`.
- Maximum retry count defaults to 5 (`max_retries=5`) with exponential backoff ($2^{\text{retry\_count}} \times 60\text{s}$). Dead-lettered records are marked `FAILED` with the exact error message preserved in `last_error`.

### C. Docker Orchestration & Healthchecks
- **Verdict: FAIL**
- In `docker-compose.prod.yml`, the `outbox_worker` service is defined as:
  ```yaml
  outbox_worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: python -m src.workers.outbox_worker
    environment:
      - DATABASE_URL=postgresql://...
    depends_on:
      db:
        condition: service_healthy
  ```
- **Defect:** There is **no healthcheck** defined for `outbox_worker`. If the worker enters a silent deadlock, hangs on a network socket, or unhandled loop exception, Docker will report the container as healthy/running.
- **Defect:** The backend `/metrics` endpoint queries `get_active_worker_metrics()`, which inspects an in-process worker instance. Since the worker runs in a separate container, `/metrics` on the web server always outputs:
  ```json
  "worker": {
    "status": "NOT_RUNNING_IN_PROCESS"
  }
  ```

---

## 5. Email Integration Assessment (Brevo / SMTP)

### A. Provider Hierarchy & Configuration
- **Verdict: PASS**
- Implementation uses a clean provider strategy: `BaseEmailProvider` $\rightarrow$ `SimulatedEmailProvider` and `SMTPEmailProvider`.
- Configuration is loaded via `src/config.py`:
  - `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`.
  - When credentials are absent or `APP_ENV=development`, the system cleanly defaults to `SimulatedEmailProvider` without crashing.

### B. Security & Credentials
- **Verdict: PASS**
- SMTP credentials and authorization tokens are never logged.
- `SMTPEmailProvider.send_email` enforces TLS (`server.starttls()`) and wraps dispatch in a 30-second socket timeout (`timeout=30`).
- Recipient email addresses and activation tokens in logs are masked or sanitized by `ProductionSecurityAndLoggingMiddleware`.

---

## 6. Monitoring & Telemetry Assessment

### A. Health Check Endpoints
- **Verdict: PASS**
- `GET /health/live`: Returns `200 {"status": "UP", "timestamp": "..."}`. Confirms process execution.
- `GET /health/ready`: Performs live dependency validation:
  1. PostgreSQL database connectivity (`SELECT 1`).
  2. Redis cache connectivity (if enabled).
  3. Environment configuration sanity check.
  Returns `503 SERVICE UNAVAILABLE` with diagnostic reasons if the primary database is unreachable.

### B. Prometheus & Operational Metrics
- **Verdict: PARTIAL**
- `GET /metrics`:
  - Enforces access control via `check_metrics_access`: requires `CENTRAL_ADMIN` or `STATE_ADMIN` JWT, or valid `X-Metrics-Key` / query parameter, or loopback IP (`127.0.0.1`).
  - Reports API latency histograms, request counts, error counts, and database pool status.
- **Defects Identified:**
  1. Outputs JSON format by default rather than standard Prometheus text exposition format (`text/plain; version=0.0.4`).
  2. Missing outbox queue latency metric (age of the oldest pending unleased message).
  3. Worker metrics are disconnected when running outbox worker as a separate process/container.

### C. Structured Logging
- **Verdict: PASS**
- `ProductionSecurityAndLoggingMiddleware` assigns or propagates `X-Request-ID`.
- Logs are emitted in JSON format with timestamp, log level, request path, method, client IP, status code, and execution time ($ms$).
- Headers containing `Authorization`, `Cookie`, or `X-API-Key` are automatically redacted.

---

## 7. Frontend Notification Assessment

### A. Hospital Dashboard
- **Verdict: PASS (Functional within Scope)**
- `NotificationPanel.tsx` is embedded in `HospitalDashboard.tsx`.
- Features implemented:
  - Unread badge counter.
  - Mark single notification as read (`POST /notifications/{id}/read`).
  - Mark all notifications as read (`POST /notifications/read-all`).
  - Polling interval set to 30 seconds.
  - Visual indicators for notification severity (`INFO`, `WARNING`, `CRITICAL`).

### B. Administrative Dashboards (Central, State, District)
- **Verdict: FAIL (Completely Missing)**
- Inspection of `CentralDashboard.tsx`, `StateDashboard.tsx`, and `DistrictDashboard.tsx` reveals:
  - **Zero** notification components or bell icons.
  - Reviewers receive no UI alerts when a new hospital registers in their district.
  - State and Central admins receive no notification when an application is escalated for higher-tier approval.

---

## 8. Authorization & Privacy Assessment

### A. Multi-Tenant Data Isolation
- **Verdict: PASS / PARTIAL**
- Hospital notifications are strictly filtered by `hospital_id` in `notification_store.py`:
  ```python
  stmt = select(Notification).filter(Notification.hospital_id == current_user_hospital_id)
  ```
- **Limitation:** The `notifications` table schema mandates `hospital_id VARCHAR NOT NULL REFERENCES hospitals(hospital_id)`. Because of this constraint, administrative reviewers who are not bound to a specific hospital (e.g., District Health Officers, State Health Secretaries) cannot receive records from this table without schema modification (making `hospital_id` nullable and adding `user_id` or `role`/`jurisdiction`).

### B. Patient Privacy & PII Scrubbing
- **Verdict: PASS**
- Referral notifications in `Notification.message` summarize actions without dumping raw patient clinical notes.
- Outbox payloads store recipient email addresses for transaction delivery; email content uses parameterized templates.

---

## 9. Test Coverage Assessment

The Phase 4D domain is supported by dedicated test suites in `tests/`:

| Test File | Tests | Coverage Scope | Status |
| :--- | :---: | :--- | :--- |
| `tests/test_outbox_worker_reliability.py` | 8 | Transactional outbox enqueueing, worker lease acquisition, concurrency `SKIP LOCKED`, retry backoff, lease timeout recovery, and dead-letter marking. | **PASS** |
| `tests/test_email_delivery_and_smtp.py` | 7 | Provider resolution, simulated delivery, SMTP TLS handshake, timeout resilience, rate limiting, and email address masking. | **PASS** |
| `tests/test_observability_and_security_headers.py` | 8 | `/health/live`, `/health/ready` DB failure response, `/metrics` auth verification, `X-Request-ID` tracing, and security headers. | **PASS** |

**Current Test Gap:**
- No test verifies automated background bed reservation expiry.
- No end-to-end test validates that registration submission, corrections, or bed actions emit notifications.

---

## 10. Critical Defects & Highest-Priority Risks

### Priority 1 Risk: Unmanaged Bed Reservation Expiration (Orphaned Inventory)
- **Impact: SEVERE (Data Integrity & Bed Blocking)**
- **Description:** A bed reservation has an `expires_at` timestamp (typically 2 to 4 hours after referral). In the current architecture, if the patient never arrives, the bed remains marked as `RESERVED` forever, reducing the hospital's available inventory and denying emergency admissions.
- **Root Cause:** Expiration logic exists solely in `pg_repository.expire_reservation_direct()`, which is only executed if an external caller explicitly invokes `POST /hospitals/{hid}/reservations/{pid}/expire`. There is no background worker or recurring scheduler to automatically sweep expired reservations.
- **Remediation:** Introduce an autonomous `InventoryExpiryWorker` (or scheduled task in the existing worker) that periodically executes an atomic PostgreSQL query:
  ```sql
  SELECT reservation_id, hospital_id, bed_id, patient_id
  FROM bed_reservations
  WHERE status = 'PENDING' AND expires_at < NOW()
  FOR UPDATE SKIP LOCKED;
  ```
  It will call `expire_reservation_direct()` for each expired reservation, restoring bed inventory and generating audit logs.

### Priority 2 Risk: Notification Vacuum Across Registration & Direct Bed Lifecycles
- **Impact: HIGH (Operational Breakdown & Review Delays)**
- **Description:** When an applicant submits a hospital registration or resubmits requested corrections, no email confirmation is dispatched, and no notification appears on the reviewing officer's dashboard. Reviewers must manually refresh tables to discover pending applications. Furthermore, direct bed reservations and discharges (outside legacy referrals) generate zero in-app notifications.
- **Root Cause:** Event hooks are completely missing in `src/services/registration_service.py` and direct repository methods (`reserve_bed_direct`, `discharge_patient_direct`).
- **Remediation:** Wire transactional outbox and notification events into `submit_application()`, `request_corrections()`, and direct inventory lifecycle transitions.

### Priority 3 Risk: Worker Observability Blindness in Production
- **Impact: MEDIUM (Operations & Reliability)**
- **Description:** When running `docker-compose.prod.yml`, the web API container and outbox worker container are separate OS processes. `/metrics` relies on memory inspection of a locally running worker, returning `NOT_RUNNING_IN_PROCESS`. Operators cannot determine if the worker is running, how many messages are pending in the queue, or if the queue is backing up.
- **Root Cause:** Worker metrics are kept in an in-memory Python object rather than read directly from database queue aggregations.
- **Remediation:** Update `src/api/observability.py` to query queue stats directly from `RegistrationEmailOutbox` in PostgreSQL (`count pending`, `count processing`, `count failed`, `max age of pending`) when generating `/metrics`.

---

## 11. Missing Features

1. **Automated Bed Reservation Expiry Worker:** Background process to sweep and expire outdated reservations.
2. **Registration Lifecycle Email Triggers:**
   - Registration Submission Confirmation (to applicant).
   - Registration Review Alert (to District Reviewer).
   - Correction Request Notification with comments (to applicant).
   - Application Rejection Notice with reasons (to applicant).
3. **Database-Backed Outbox Telemetry:** Metrics endpoint calculating live queue depth and processing lag from PostgreSQL.
4. **Outbox Worker Docker Healthcheck:** Script and configuration in `docker-compose.prod.yml` to ensure container restart on worker stall.
5. **Prometheus Exposition Format:** Native `text/plain` Prometheus metric rendering for Prometheus/Grafana scrapers.
6. **Administrative Notifications UI:** Notification bell and event feed for Central, State, and District dashboards.

---

## 12. Exact File Paths Requiring Changes

The following files are identified for Phase 4D implementation:

| File Path | Nature of Modification |
| :--- | :--- |
| `src/workers/reservation_expiry_worker.py` | **NEW FILE:** Autonomous background worker to scan and expire overdue bed reservations. |
| `src/workers/outbox_worker.py` | Add healthcheck heartbeat file/endpoint, periodic expiry sweep coordination, and database-backed metrics reporting. |
| `src/services/registration_service.py` | Add outbox enqueue calls on application submission, correction request, rejection, and review assignment. |
| `src/database/pg_repository.py` | Add in-app notification creation for direct bed operations (`reserve_bed_direct`, `confirm_bed_direct`, `occupy_bed_direct`, `discharge_patient_direct`, `expire_reservation_direct`). |
| `src/api/observability.py` | Add database-backed outbox queue metrics, oldest pending message age, and optional Prometheus text formatter. |
| `docker-compose.prod.yml` | Add healthcheck for `outbox_worker` and add `reservation_expiry_worker` service definition (or combined worker). |
| `frontend/components/shared/NotificationPanel.tsx` | Generalize notification panel to support multi-role administrative alerts. |
| `frontend/components/DistrictDashboard.tsx` | Embed notification panel with reviewer alerts. |
| `frontend/components/StateDashboard.tsx` | Embed notification panel with escalation alerts. |
| `frontend/components/CentralDashboard.tsx` | Embed notification panel with policy/registration alerts. |
| `tests/test_reservation_expiry_worker.py` | **NEW FILE:** Regression tests for automated reservation expiration and inventory restoration. |
| `tests/test_registration_lifecycle_notifications.py` | **NEW FILE:** End-to-end tests for registration outbox and notification events. |

---

## 13. Recommended Implementation Sequence

To minimize risk and maintain zero-downtime compatibility, Phase 4D should be implemented in four controlled steps:

```
Step 1: Automated Bed Expiry Worker & Inventory Integrity
  ├── Create src/workers/reservation_expiry_worker.py
  ├── Test atomic sweep with FOR UPDATE SKIP LOCKED
  └── Verify bed inventory counter restoration (available/reserved/occupied)

Step 2: Transactional Outbox Event Expansion
  ├── Wire outbox events in src/services/registration_service.py (Submission, Corrections, Rejection)
  ├── Wire in-app notifications in src/database/pg_repository.py for direct bed actions
  └── Add regression tests for event generation

Step 3: Observability & Worker Reliability Hardening
  ├── Upgrade src/api/observability.py with live PostgreSQL outbox metrics (queue lag, counts)
  ├── Add Prometheus text exposition support
  └── Configure Docker healthchecks and heartbeat in docker-compose.prod.yml

Step 4: Frontend Notification & Administrative Integration
  ├── Connect NotificationPanel to District, State, and Central dashboards
  ├── Verify unread counter, mark-as-read, and role-based filtering
  └── Run full Playwright browser and backend test suites
```

---

## 14. Dependencies & External Credentials Required

- **PostgreSQL Database:** Authoritative instance (local test `sih_hospital_phase1_run_test` for validation).
- **Brevo / SMTP Service:**
  - Production requires valid `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASSWORD`.
  - Development and CI/test environments operate seamlessly via project's `SimulatedEmailProvider` with zero external network dependencies.
- **Docker Engine & Compose:** For validating worker container healthcheck directives.

---

## 15. Acceptance Criteria for Phase 4D

1. **Automated Expiration:** Expired reservations must be automatically transitioned from `PENDING` to `EXPIRED` within 60 seconds of expiry without manual API intervention, restoring hospital capacity.
2. **Event Delivery:**
   - 100% of registration status changes (Submission, Corrections Requested, Approved, Rejected) must enqueue atomic outbox events.
   - 100% of bed lifecycle transitions (Direct & Referral) must generate structured in-app notifications.
3. **Worker Concurrency & Resilience:**
   - Multiple worker instances must process outbox entries concurrently without race conditions or duplicate sends.
   - Crashed workers must automatically release stale leases within 300 seconds.
4. **Production Observability:**
   - `/metrics` must report accurate outbox queue depth, failure counts, and worker health regardless of whether the worker is in-process or containerized.
   - `/health/ready` must report degradation if the outbox queue exceeds operational threshold or database connectivity fails.
5. **No Regression:** All 342 backend tests and 20 Playwright frontend tests must continue to pass cleanly.

---

## 16. Audit Verification & Final Verdict

- **Repository Integrity:** Verified intact. Zero Git commits, pushes, or destructive operations performed.
- **Stash Status:** `stash@{0}` intact.
- **Database Status:** `sih_hospital_dev` completely untouched (500 hospitals, 8 users confirmed via PostgreSQL catalog query).

### Audit Verdict
**READY FOR IMPLEMENTATION**  
The Phase 4D architecture, missing components, critical risks, and exact file modification blueprint have been thoroughly identified and verified. Implementation may proceed following formal review and approval.
