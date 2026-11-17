# Phase 1 — Comprehensive Final Security Audit Report

**Date:** 2026-11-03  
**Project:** SIH Hospital Referral System (`~/Desktop/SIH_Hospital_AI`)  
**Scope:** Phase 1 Security Architecture, RBAC Hierarchy, Cryptographic Integrity & Attack Surface Audit  
**Status:** AUDIT PASSED — No unresolved high or critical vulnerabilities were identified within the tested Phase 1 scope  

---

## 1. Role-Permission Matrix & Geographic Hierarchy

The system enforces strict multi-tier role-based access control (RBAC) and geographic jurisdiction boundaries across five distinct user contexts:

| Permission / Action | APPLICANT | HOSPITAL | DISTRICT_ADMIN | STATE_ADMIN | CENTRAL_ADMIN |
|---|:---:|:---:|:---:|:---:|:---:|
| **Submit Registration Application** | ✅ (Own) | ❌ | ❌ | ❌ | ❌ |
| **Track Application Status** | ✅ (Own via Token) | ❌ | ❌ | ❌ | ❌ |
| **Upload / Replace Registration Documents** | ✅ (Own draft/correction) | ❌ | ❌ | ❌ | ❌ |
| **Review District Hospital Applications** | ❌ | ❌ | ✅ (Assigned District) | ✅ (Assigned State) | ✅ (Global) |
| **Forward Hospital Application to State** | ❌ | ❌ | ✅ (Assigned District) | ❌ | ❌ |
| **Forward District Application to Central**| ❌ | ❌ | ❌ | ✅ (Assigned State) | ❌ |
| **Verify Supporting Documents** | ❌ | ❌ | ✅ (Assigned District) | ✅ (Assigned State) | ✅ (Global) |
| **Final Institutional Approval** | ❌ | ❌ | ❌ | ❌ | ✅ (Central Only) |
| **Self-Approval of Own Application** | ❌ (Strictly Blocked) | ❌ (Blocked) | ❌ (Blocked) | ❌ (Blocked) | ❌ (Blocked) |
| **Access Operational Hospital Bed Inventory**| ❌ | ✅ (Own Hospital) | ✅ (District Overview) | ✅ (State Overview) | ✅ (Global) |
| **Accept / Reject Clinical Patient Referrals**| ❌ | ✅ (Own Hospital Only)| ❌ (Forbidden) | ❌ (Forbidden) | ❌ (Forbidden) |
| **Access Government Review API Routes** | ❌ (403 Forbidden) | ❌ (403 Forbidden) | ✅ | ✅ | ✅ |

---

## 2. In-Depth Attack Surface & Vulnerability Analysis

### 2.1 Horizontal & Vertical Privilege Escalation
- **Attack Vector:** An applicant or hospital administrator attempting to call reviewer endpoints (`/api/registration/review/*`).
- **Control Enforced:** `require_reviewer_user` validates role membership in `{"DISTRICT_ADMIN", "STATE_ADMIN", "CENTRAL_ADMIN"}`. Applicant and hospital users receive immediate `HTTP 403 Forbidden`.
- **Jurisdiction Escapes:** A District Admin from Mohali attempting to review an application from Ludhiana receives `HTTP 403 Forbidden` (`"Access denied: Reviewer is not authorized for district 'Ludhiana'."`). State Admins attempting cross-state review receive identical rejection.
- **Self-Approval:** The service strictly checks `reviewer.user_id`, `reviewer.username`, and `reviewer.email` normalized via `.strip().lower()` against `app.applicant_email` and `app.nodal_officer_name`. Any match raises `SelfApprovalError` (`HTTP 403`). Verified across mixed casing, whitespace padding, user IDs, usernames, and nodal officer names in `test_self_approval_prevented` (4 distinct vectors).

### 2.2 Insecure Direct Object References (IDOR)
- **Attack Vector:** Tampering with `application_id`, `document_id`, or `hospital_id` in API paths.
- **Control Enforced:**
  - Applicants cannot view applications or documents by ID without owning the session matching `application.applicant_email` and `application.application_id`.
  - Replaced documents assign a fresh UUID `document_id` and purge the prior database row. Probing prior document IDs returns `HTTP 400 Not Found`.
  - Hospital staff attempting to update referrals belonging to another facility receive `HTTP 403 Forbidden`.

### 2.3 JWT Security, Forgery & Session Invalidation
- **Algorithm Substitution:** PyJWT is configured with `algorithms=["HS256"]`. Header `alg: "none"` or mismatched keys are rejected.
- **Secret Hygiene:** `SIH_JWT_SECRET` startup check enforces minimum 32 characters in production environments; fallback to insecure dev secret is prohibited in production.
- **Session Revocation on Password Reset:** Implemented `revoke_user_sessions(user_id)` and `is_user_session_revoked(user_id, token_iat)` in `src/auth/rate_limiter.py`. Any JWT issued prior to password reset is immediately rejected upon decoding.

### 2.4 Public Tracking Oracle & Enumeration Defense
- **Attack Vector:** Probing public tracking endpoints with sequential reference numbers to discover registered hospitals or government officials.
- **Control Enforced:** Both `application_number` and `tracking_token` are mandatory. Requests with invalid, expired, revoked, or mismatched tokens return uniform `HTTP 404 ("Application not found or tracking token invalid")`. The server leaks no timing or existence signals.
- **PII Redaction:** Tracking outputs strip phone numbers, full emails, reviewer identities, internal notes, and storage keys.

### 2.5 Document Uploads, Path Traversal & Antivirus Fail-Closed
- **Magic-Byte Sniffing:** MIME headers from multipart clients are untrusted. The backend inspects leading file bytes for `%PDF-`, `\xFF\xD8\xFF`, and `\x89PNG\r\n\x1A\n`. Mismatches raise `MimeTypeSpoofingError` (HTTP 422).
- **Path Traversal:** Filenames are never used as physical storage keys. Storage keys are generated as `DOC_<uuid4>.<ext>`, preventing `../` directory traversal or filesystem overwrites.
- **Fail-Closed Antivirus:** `ClamAVScanner` strictly fails closed:
  - Connection refused / offline daemon: raises `MalwareScanServiceUnavailableError` (HTTP 503).
  - Socket timeout: raises `MalwareScanServiceUnavailableError` (HTTP 503).
  - Parser / unexpected error: raises `MalwareScanError` (HTTP 502).
  - Infected / EICAR signature: raises `MalwareDetectedError` (HTTP 422).
  - In all failure scenarios, the upload is rejected and no file is stored.

### 2.6 Concurrency, Race Conditions & Transactional Outbox
- **Duplicate Provisioning:** Protected by PostgreSQL partial unique indexes:
  ```sql
  CREATE UNIQUE INDEX uq_users_application_id ON users (application_id) WHERE application_id IS NOT NULL;
  CREATE UNIQUE INDEX uq_hospitals_application_id ON hospitals (application_id) WHERE application_id IS NOT NULL;
  ```
- **Outbox Worker Race Conditions:** Protected by PostgreSQL `with_for_update(skip_locked=True)` so concurrent workers process non-overlapping queues.
- **At-Least-Once Delivery & Single-Use Tokens:** Email dispatches are at-least-once. Double deliveries do not present security risks because activation and password reset tokens are single-use cryptographically random tokens stored as SHA-256 digests; once consumed, replays are permanently rejected.

### 2.7 Password Recovery & Anti-Enumeration
- **Public Request:** `POST /api/registration/auth/password-reset/request` returns the identical message regardless of whether the email exists. Non-existent emails trigger a dummy PBKDF2 hash calculation to normalize response latency.
- **Hash Storage:** Tokens are never stored in plaintext; only SHA-256 hashes with 1-hour expiry are persisted.
- **Password Complexity:** Minimum 8 characters, uppercase, lowercase, digit, and special character. Passwords hashed using PBKDF2-HMAC-SHA256 with 100,000 iterations.

---

## 3. Vulnerability Remediation Summary (Phase 1)

| Audit ID | Severity | Category | Vulnerability Description | Remediation Applied | Status |
|---|---|---|---|---|---|
| **AUD-01** | **CRITICAL** | Database Integrity | Concurrent duplicate active applications at database level. | Partial unique indexes on active statuses in PostgreSQL (`uq_reg_app_active_*`). | **RESOLVED** |
| **AUD-02** | **CRITICAL** | Authorization | Public tracking oracle allowed application enumeration. | Mandatory tracking tokens with uniform 404 on invalid/mismatched tokens. | **RESOLVED** |
| **AUD-03** | **HIGH** | Outbox Reliability | Transient email dispatch failures lost activation links permanently. | Transactional outbox table, row locking, worker leases, and backoff retries. | **RESOLVED** |
| **AUD-04** | **HIGH** | Antivirus Security | ClamAV errors/timeouts failed open and allowed uploads. | Hardened scanner with fail-closed exceptions (`HTTP 503` / `HTTP 502`). | **RESOLVED** |
| **AUD-05** | **HIGH** | Concurrency | Simultaneous provisioning created duplicate users/hospitals. | Partial unique constraints on `application_id` and savepoint recovery. | **RESOLVED** |
| **AUD-06** | **HIGH** | Session Security | Sessions remained active after password reset. | Implemented user session revocation (`revoke_user_sessions`) via Redis/in-memory cutoff. | **RESOLVED** |
| **AUD-07** | **MEDIUM** | Stale Document Access | Replaced documents were updated in-place, leaking prior files. | Replaced documents assign fresh `document_id` and delete old rows and blobs. | **RESOLVED** |
| **AUD-08** | **HIGH** | Authorization | `get_hospital_geo` queried SQLite only, causing false 403s on PostgreSQL. | Refactored `get_hospital_geo` to query PostgreSQL master records first. | **RESOLVED** |

---

## 4. Untested Attack Surfaces & Environmental Assumptions

The following attack vectors and operational boundaries were outside the Phase 1 specification and were not evaluated in this audit:

1. **Distributed Denial of Service (DDoS) & Layer 4/7 Flooding:**
   - Volumetric network floods, SYN floods, and massive HTTP request amplification require perimeter mitigation (Cloudflare, AWS Shield, or edge WAF) not present in local/unit testing environments.
2. **Hardware-Level & Microarchitectural Side-Channels:**
   - Physical timing attacks, cache-timing side-channels on underlying CPU cores, and memory bus sniffing against cryptographic operations (PBKDF2, HMAC-SHA256) were not benchmarked.
3. **Upstream Email Transit & External SMTP Infrastructure:**
   - Delivery security depends on external providers (e.g., Brevo, SendGrid, Amazon SES) and recipient mail transfer agents (MTA-STS, DANE, DNSSEC, SPF/DKIM/DMARC configurations). Audit verified outbox transaction isolation, worker crash recovery, and token hashing, not third-party transit encryption.
4. **Massive Sustained ClamAV Daemon Throughput:**
   - Antivirus fail-closed mechanics (daemon down, timeouts, socket disconnects) were verified using mock sockets and unit harnesses; high-concurrency saturating loads against physical `clamd` UNIX sockets remain subject to production hardware sizing.
5. **Government Identity / Biometric Oracles:**
   - Aadhaar UIDAI e-KYC or DigiLocker integration is not part of Phase 1 (OTP verification over email/SMS is implemented). Government officer identity verification is currently managed through administrative hierarchy and pre-provisioned credentials.
6. **Frontend Browser-Level Client-Side Attack Surface:**
   - The Next.js frontend currently contains only operational hospital dashboards; registration workflows (Workflows 1–11) operate strictly as backend REST APIs. Browser-specific DOM XSS, Content Security Policy (CSP) headers, Subresource Integrity (SRI), and cookie attribute policies for the applicant registration UI are deferred to Phase 2 frontend implementation.

---

## 5. Security Verification Verdict

**Final Assessment: APPROVED — No unresolved high or critical vulnerabilities were identified within the tested Phase 1 scope.**

The backend security architecture, multi-tiered RBAC hierarchy, cryptographic storage, transaction isolation, and fail-closed storage adapters demonstrate robust, defense-in-depth protection across all tested Phase 1 specifications.
