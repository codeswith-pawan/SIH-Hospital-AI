# Phase 2 — Task 2B: Production Email Delivery Integration Report

**Date:** 2026-11-06  
**Project:** SIH Hospital Referral System (`~/Desktop/SIH_Hospital_AI`)  
**Branch:** `master` (HEAD: `460af41`)  
**Task:** Phase 2 Task 2B — Production Email Delivery Integration  
**Status:** IMPLEMENTED, VALIDATED & APPROVED  

---

## 1. Executive Summary

Task 2B elevates the registration and notification subsystem from Phase 1 simulation to a production-grade, fault-tolerant email delivery infrastructure. It establishes the PostgreSQL `registration_email_outbox` table as the **single source of truth** for all activation and transactional emails, eliminates dual-dispatch duplicate emails, connects OTP generation to configured email gateways, and introduces an autonomous background outbox worker process with graceful shutdown and concurrency safety.

### Key Milestones Achieved:
1. **Duplicate Activation Dispatch Eliminated:** Outbox processing is now the sole pathway for email delivery. Direct post-commit calls atomically claim and process outbox events by ID (`EmailOutboxService.process_event`), marking them `SENT` immediately or `FAILED` with exponential backoff on error. Subsequent background worker runs detect the `SENT` state and never double-deliver.
2. **Hardened SMTP Provider:** `SMTPEmailProvider` is fully configurable via standard environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`, `SMTP_TIMEOUT`), supports STARTTLS, connection timeouts, privacy-conscious email masking, and fails closed in production when unconfigured.
3. **Production Email OTP Delivery:** `ConfigurableOTPProvider` routes email verification codes through the active email provider with formatted purpose and expiration details, failing closed if delivery cannot be completed.
4. **Standalone Background Worker:** Implemented `OutboxWorker` in `src/workers/outbox_worker.py` supporting continuous queue polling, lease expiration reclamation, graceful `SIGINT`/`SIGTERM` handling, single-loop execution locks, and a CLI `--run-once` flag.
5. **Comprehensive Verification:** 12 new dedicated tests in `tests/test_email_delivery_and_smtp.py` passing 100%; all 168 Phase 1 + Phase 2 target integration tests passing without regression.

---

## 2. Architecture & Design

### 2.1 Single-Source-of-Truth Outbox Workflow

```
[Application Approved / Resend Requested]
                   │
                   ▼ (Inside DB Transaction)
┌────────────────────────────────────────────────────────┐
│ 1. AccountProvisioningService                          │
│    - Generate single-use cryptographic token           │
│    - Store SHA-256 token hash in DB                   │
│    - Enqueue event into registration_email_outbox      │
│    - Return outbox_id in provisioning result           │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼ (Post-Commit / Asynchronous)
┌────────────────────────────────────────────────────────┐
│ 2. EmailOutboxService.process_event(outbox_id)        │
│    - Acquire row lock (SKIP LOCKED)                    │
│    - Mark event: PROCESSING                            │
│    - Call active EmailProvider (SMTP / Simulated)      │
│    ┌─────────────────┴─────────────────┐               │
│    ▼ (Success)                         ▼ (Failure)     │
│ [Status = SENT]                  [Status = FAILED]     │
│ [sent_at = NOW()]                [retry_count += 1]    │
│                                  [next_retry_at = Exp] │
└────────────────────────────────────────┬───────────────┘
                                         │
                   ▼ (If Failed or Lease Abandoned)
┌────────────────────────────────────────────────────────┐
│ 3. Autonomous OutboxWorker Daemon                      │
│    - Polls with SKIP LOCKED                            │
│    - Reclaims abandoned PROCESSING events (>300s)      │
│    - Retries eligible FAILED events with backoff       │
│    - NO new activation tokens are generated           │
└────────────────────────────────────────────────────────┘
```

### 2.2 Dual-Dispatch Bug Root Cause & Resolution
- **Root Cause:** In Phase 1, `provision_account()` enqueued an `ACCOUNT_ACTIVATION` event with status `PENDING` into `registration_email_outbox`, but `registration_routes.py` also called `dispatch_activation_email()` directly. Because direct dispatch bypassed the outbox table and left the record in `PENDING`, any subsequent outbox worker execution picked up the record and dispatched the activation email a second time.
- **Resolution:** `dispatch_activation_email()` was refactored to invoke `EmailOutboxService.process_event(outbox_id)`. The event is atomically transitioned to `PROCESSING` $\rightarrow$ `SENT` in PostgreSQL during the initial dispatch. If the initial dispatch fails, the event is recorded as `FAILED` with exponential retry backoff, allowing the background worker to safely deliver it later without duplicate tokens.

---

## 3. Files Modified & Created

| File | Status | Description |
|---|---|---|
| [src/services/email_service.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/services/email_service.py) | **Modified** | Hardened `SMTPEmailProvider` with standard env vars (`SMTP_*`), STARTTLS toggle, timeout, recipient masking, and production fail-close enforcement in `get_email_provider()`. |
| [src/services/email_outbox_service.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/services/email_outbox_service.py) | **Modified** | Added `process_event(outbox_id)` for atomic single-event processing with row locking (`SKIP LOCKED`). |
| [src/services/account_provisioning_service.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/services/account_provisioning_service.py) | **Modified** | Bound provisioning and resend results to `outbox_id`; refactored `dispatch_activation_email()` to process through the outbox as single source of truth. |
| [src/services/otp_service.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/services/otp_service.py) | **Modified** | Connected `ConfigurableOTPProvider` to active `email_provider.send_email()`; added formatted email templates with purpose labels; ensured delivery failure strictly fails closed. |
| [src/workers/__init__.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/workers/__init__.py) | **Created** | Asynchronous workers package initializer. |
| [src/workers/outbox_worker.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/src/workers/outbox_worker.py) | **Created** | Standalone autonomous outbox worker daemon and CLI with `SKIP LOCKED`, graceful shutdown (`SIGINT`/`SIGTERM`), and `--run-once` flag. |
| [tests/test_email_delivery_and_smtp.py](file:///Users/pawankumarsharma/Desktop/SIH_Hospital_AI/tests/test_email_delivery_and_smtp.py) | **Created** | Comprehensive 12-test suite covering SMTP delivery, authentication errors, timeouts, production fail-close, OTP routing, outbox single delivery, log privacy, and worker lifecycle. |

---

## 4. Test Execution & Verification

### 4.1 New Email & SMTP Test Suite
- **Command:** `.venv/bin/pytest tests/test_email_delivery_and_smtp.py -v`
- **Results:** 12 passed / 12 executed (100% pass rate in 0.38s)

```
tests/test_email_delivery_and_smtp.py::test_smtp_successful_delivery_mock PASSED
tests/test_email_delivery_and_smtp.py::test_smtp_authentication_failure PASSED
tests/test_email_delivery_and_smtp.py::test_smtp_timeout_handling PASSED
tests/test_email_delivery_and_smtp.py::test_missing_smtp_host_configuration PASSED
tests/test_email_delivery_and_smtp.py::test_missing_production_smtp_configuration_fails_closed PASSED
tests/test_email_delivery_and_smtp.py::test_otp_email_delivery_via_configured_email_provider PASSED
tests/test_email_delivery_and_smtp.py::test_otp_delivery_failure_fails_closed PASSED
tests/test_email_delivery_and_smtp.py::test_activation_email_single_delivery_and_outbox_state PASSED
tests/test_email_delivery_and_smtp.py::test_activation_dispatch_failure_retained_in_outbox_for_retry PASSED
tests/test_email_delivery_and_smtp.py::test_no_sensitive_tokens_or_passwords_in_logs PASSED
tests/test_email_delivery_and_smtp.py::test_outbox_worker_run_once PASSED
tests/test_email_delivery_and_smtp.py::test_outbox_worker_prevents_duplicate_concurrent_loops PASSED
```

### 4.2 Comprehensive Target Regression Suite
- **Command:**
  ```bash
  .venv/bin/pytest tests/test_email_delivery_and_smtp.py \
                   tests/test_document_storage_and_provisioning.py \
                   tests/test_registration_postgresql_live.py \
                   tests/test_registration_api.py \
                   tests/test_registration_service.py \
                   tests/test_registration_models.py \
                   tests/test_live_postgresql_integration.py \
                   tests/test_postgresql_migration_and_transactions.py \
                   tests/test_end_to_end_referral_workflow.py \
                   tests/test_auth_and_access.py -q
  ```
- **Results:** **168 passed**, 0 failed, 0 skipped in 12.94s.

---

## 5. Local SMTP Testing Configuration Guide

To test with a local mock SMTP server (such as MailHog, Mailpit, or Python `aiosmtpd`), configure the following environment variables:

### 5.1 Environment Variables
```bash
# Email Backend Selection
export SIH_EMAIL_BACKEND="smtp"

# SMTP Server Parameters
export SMTP_HOST="127.0.0.1"
export SMTP_PORT="1025"            # Standard MailHog / Mailpit SMTP port
export SMTP_USERNAME=""            # Leave empty for unauthenticated local servers
export SMTP_PASSWORD=""            # Leave empty for unauthenticated local servers
export SMTP_FROM_EMAIL="no-reply@hospital.sih.gov.in"
export SMTP_USE_TLS="false"        # Set to 'false' for plain local test servers
export SMTP_TIMEOUT="10"

# OTP Provider Routing
export SIH_OTP_PROVIDER="EMAIL"     # Routes OTP generation to active SMTP provider
```

### 5.2 Standalone Outbox Worker Execution
Run the background worker to continuously monitor and deliver enqueued outbox emails:

```bash
# Continuous daemon mode (polls every 5 seconds)
python -m src.workers.outbox_worker --interval 5.0 --batch-size 10

# Single-pass execution (ideal for cron or test runners)
python -m src.workers.outbox_worker --run-once
```

---

## 6. Known Limitations & Phase 2 Roadmap

1. **SMS Gateway Client:** `channel="SMS"` OTP delivery currently validates inputs and logs in non-production environments; an external SMS gateway adapter (e.g., Twilio or CDAC Mobile Seva Gateway) will be integrated in a subsequent task.
2. **Expired Token Purge Routine:** Tokens remain in PostgreSQL tables after expiration; a periodic maintenance job should be scheduled to purge expired rows older than 30 days.
3. **Frontend Integration (Task 2C):** Phase 2 Task 2B strictly focused on backend email infrastructure; the Next.js frontend UI components for applicant registration, OTP entry, and reviewer inboxes are scheduled for upcoming Phase 2 tasks.

---

## 7. Verification Confirmation

- **Database Isolation:** PostgreSQL development database `sih_hospital_dev` was untouched (500 hospitals, 8 users, 0 registration tables).
- **Git State:** `stash@{0}` is intact. No git commits or pushes were executed.
