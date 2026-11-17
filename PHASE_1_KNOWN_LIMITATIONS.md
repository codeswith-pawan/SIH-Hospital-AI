# Phase 1 — Known Limitations & Production Readiness Report

**Date:** 2026-11-03  
**Project:** SIH Hospital Referral System (`~/Desktop/SIH_Hospital_AI`)  
**Scope:** Architectural Boundaries, Development vs Production Environments, External Dependencies & Deployment Requirements  

---

## 1. Executive Context

Phase 1 successfully establishes the backend core, business logic, security model, and persistence layer for the **Hierarchical Government Registration, Verification & Approval System**. In adherence to strict engineering standards, this document distinguishes between local development abstractions and external infrastructure required for production deployment.

---

## 2. Development-Only Components vs. Production Implementations

| Component | Local Development Mode | Production Deployment Requirement |
|---|---|---|
| **Email Delivery** | `SimulatedEmailProvider` (in-memory captures) | `SMTPEmailProvider` with TLS (Port 587) or Brevo transactional HTTP API client with registered domain SPF/DKIM/DMARC records. |
| **Document Storage** | `LocalStorageAdapter` (`data/documents/`) | `S3StorageAdapter` connected to AWS S3, Cloudflare R2, or MinIO with bucket encryption (SSE-S3/KMS) and private access control lists (ACLs). |
| **Malware Scanning** | `SimulatedScanner` (testing hooks) | Network-attached ClamAV daemon (`clamd`) running as a Kubernetes sidecar or dedicated VPC microservice. Scanning must remain fail-closed. |
| **Distributed Rate Limiting & Revocation**| In-memory locks (`_IN_MEMORY_FAILURES`, `_IN_MEMORY_REVOKED_TOKENS`) | Distributed Redis 7+ cluster with persistence (AOF/RDB) running atomic Lua sliding-window scripts. |
| **Email Outbox Polling** | Manual execution or test invocation (`process_outbox()`) | Dedicated daemon, Kubernetes CronJob, or Celery beat worker executing `process_outbox()` every 30–60 seconds. |

---

## 3. External Provider Dependencies

1. **Transactional Email Service:**
   - **Protocol:** SMTP over TLS (STARTTLS) or authenticated REST API.
   - **Reliability Policy:** Delivery is guaranteed to be **at-least-once**. Because standard email gateways lack distributed two-phase commit (2PC) transactions with PostgreSQL, unhandled network interruptions between socket transmission and database commit can trigger re-dispatch upon lease expiration.
   - **Idempotency Safeguard:** All activation links and password reset links are single-use tokens stored as SHA-256 digests in PostgreSQL. A duplicate email delivers the identical link and cannot be replayed once consumed.
2. **Antivirus Scanning Daemon (ClamAV):**
   - **Connectivity:** TCP socket or UNIX domain socket.
   - **Fail-Closed Availability Risk:** If the ClamAV daemon becomes unreachable or times out (>10s), the system strictly rejects file uploads with `HTTP 503 Service Unavailable`. Production environments must deploy redundant ClamAV instances to maintain high availability.
3. **Redis Caching & Revocation Layer:**
   - **Fail-Fast In Production:** `validate_production_security_config()` and `_get_redis_client()` enforce that production environments fail immediately if Redis is unreachable, preventing unmetered brute-force attacks or stale JWT reuse.

---

## 4. Unimplemented Functionality (Outside Phase 1 Scope)

The following capabilities were intentionally excluded from Phase 1 scope and are reserved for subsequent phases:
1. **Direct UIDAI Aadhaar Verification:** Document uploads accept national identity proofs as static binary documents; direct real-time Aadhaar OTP authentication via UIDAI APIs requires official government gateway integration.
2. **Automated OCR / NLP Document Verification:** Document verification is currently performed by authorized government reviewers (`DISTRICT_ADMIN`, `STATE_ADMIN`, `CENTRAL_ADMIN`) via secure streaming viewers. Automated optical character recognition of license numbers is an AI roadmap item.
3. **SMS Gateway Integration:** The schema supports `token_channel = 'SMS'` and `token_purpose = 'REGISTRATION_OTP'`, but local development delivers OTPs through the simulated email/console channel pending CDAC / NIC SMS gateway credentials.

---

## 5. Security & Operational Risks Analysis

| Risk Factor | Inherent Impact | Mitigation Implemented | Production Action Required |
|---|---|---|---|
| **Malware Scanner Disruption** | Upload pipeline denial of service. | Scanner fails closed (`HTTP 503`); infected files cannot bypass inspection. | Deploy multi-replica ClamAV cluster with health check monitoring. |
| **Outbox Worker Process Crash** | Stranded email notifications. | Configurable 300s processing leases allow recovery workers to reclaim and retry abandoned events. | Monitor dead-letter outbox items (`status = 'FAILED'`). |
| **Cross-Jurisdiction Tampering** | Unauthorized state/district data leakage. | Multi-tier RBAC enforces strict geographic matching in query filters and service methods. | Ensure database connection credentials follow least-privilege principles. |
| **Credential Replay Attacks** | Account takeover via leaked links. | Tokens are single-use, 72h/1h time-bound, and stored strictly as SHA-256 hashes. | Enforce HTTPS/HSTS across all portal domains. |
| **Account Enumeration via Reset** | Attackers mapping active user accounts. | Public password recovery returns identical generic messaging and executes dummy PBKDF2 calculations for non-existent users. | Configure Cloudflare / AWS WAF IP rate limiting on public endpoints. |
