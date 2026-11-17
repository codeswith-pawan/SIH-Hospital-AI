# SIH HOSPITAL AI — PHASE 2D IMPLEMENTATION & VERIFICATION REPORT
## Reviewer Portal, Account Activation, Password Reset & End-to-End Hierarchical Integration

**Project:** SIH Hospital AI (AI Powered Smart Hospital Referral System)  
**Date:** November 10, 2026  
**Branch:** `master`  
**Git Safety Status:** Uncommitted changes preserved. `stash@{0}` intact. No remote push executed.  
**Database Isolation:** Zero migrations executed against `sih_hospital_dev`. Dev hospital records (500) completely untouched.

---

## 1. Executive Summary

Phase 2D delivers the complete administrative review, verification, decision-making, and account lifecycle management system for the Hierarchical Government Registration platform. Building on Phase 1's backend foundations and Phase 2A–2C's email delivery and applicant registration workflows, Phase 2D connects government reviewers (District CMOs, State Health Directors, and Central National Registrars) to applications submitted through the portal.

### Key Capabilities Delivered:
1. **Administrative Reviewer Portal (`/reviewer` & `/reviewer/applications/[id]`):** Searchable, filterable, and paginated inbox displaying applications constrained strictly to each reviewer's administrative tier and geographic jurisdiction.
2. **Interactive Application Dossier & Secure File Preview:** Detailed review interface displaying applicant metadata, physical capacity metrics, nodal authority credentials, inline verification for submitted compliance documents, and secure browser-based document preview (PDF and images).
3. **Hierarchical Multi-Tier Decision Engine:** Complete enforcement of the 3-tier governance pipeline:
   - **Hospital:** District Review $\to$ State Review $\to$ Central Review $\to$ Operational Provisioning.
   - **District:** State Review $\to$ Central Review $\to$ Operational Provisioning.
   - **State:** Central Review $\to$ Operational Provisioning.
4. **Action Modals & Document Verification:** Reviewers can verify documents, reject documents with mandatory audit remarks, forward applications, request applicant corrections with guided notes, or reject applications with mandatory legal rationale.
5. **Atomic Account Provisioning & Activation Dispatch:** Central Government approval atomically provisions operational user accounts, binds hospital entities (for hospital registrations), and queues cryptographic activation invitation tokens in the transactional PostgreSQL email outbox.
6. **Account Activation Portal (`/activate` & `/activate/resend`):** Single-use, 72-hour cryptographic token consumption interface enforcing strict password complexity rules (minimum 8 characters, uppercase, lowercase, digit, and special symbol).
7. **Password Recovery Portal (`/forgot-password` & `/reset-password`):** Timing-attack safe password recovery request and 1-hour cryptographic token reset with PBKDF2-HMAC-SHA256 password hashing.
8. **Operational Dashboard Integration:** Seamless navigation tabs embedded into District, State, and Central operational command dashboards.

---

## 2. Implemented Frontend Routes & Files

| Route / File | Component Name | Description / User Story |
|:---|:---|:---|
| `frontend/app/reviewer/page.tsx` | `ReviewerInboxPage` | Authenticated reviewer portal root. Verifies administrative role, displays KPI summary metrics, and mounts the searchable application inbox. |
| `frontend/app/reviewer/applications/[id]/page.tsx` | `ReviewerApplicationDetailPage` | Deep-link dossier route for inspecting a single application by ID with complete document checklist, history audit trail, and decision controls. |
| `frontend/components/reviewer/ReviewerPortal.tsx` | `ReviewerPortal` | Primary container component orchestrating statistics cards, tabbed views, search queries, and switching between inbox and active dossier views. |
| `frontend/components/reviewer/ReviewerDashboardStats.tsx` | `ReviewerDashboardStats` | 6-card KPI summary panel calculating Total Assigned, Awaiting My Action, Under Active Review, Correction Required, Approved & Cleared, and Rejected counts. |
| `frontend/components/reviewer/ReviewerInboxTable.tsx` | `ReviewerInboxTable` | High-density data table supporting debounced full-text search, multi-parameter filtering (Status, Stage, Application Type), pagination, and sort order. |
| `frontend/components/reviewer/ReviewerDossierView.tsx` | `ReviewerDossierView` | Comprehensive application inspection interface with capacity statistics, nodal officer details, document checklist, file preview modal, decision triggers, and audit log table. |
| `frontend/app/activate/page.tsx` | `ActivatePage` | Public token-activated account onboarding screen with dynamic password requirement checklist and confirmation redirect to operations login. |
| `frontend/app/activate/resend/page.tsx` | `ResendActivationPage` | Self-service activation resend request by Application Number and official applicant email. |
| `frontend/app/forgot-password/page.tsx` | `ForgotPasswordPage` | Public password reset request form displaying timing-safe generic response to prevent username/email enumeration. |
| `frontend/app/reset-password/page.tsx` | `ResetPasswordPage` | Public reset confirmation form parsing 1-hour reset token and updating password via PBKDF2 hashing. |
| `frontend/components/DistrictDashboard.tsx` | `DistrictDashboard` | Updated with a new tab: "Registration & Review" mounting the Reviewer Portal scoped to the logged-in CMO's district. |
| `frontend/components/StateDashboard.tsx` | `StateDashboard` | Updated with a new tab: "Registration & Review" mounting the Reviewer Portal scoped to the logged-in State Director's state. |
| `frontend/components/CentralDashboard.tsx` | `CentralDashboard` | Updated with a new tab: "National Registration & Approvals" mounting the Reviewer Portal with nationwide oversight. |
| `frontend/components/registration/RegistrationNavbar.tsx` | `RegistrationNavbar` | Added persistent navigation link to Reviewer Portal (`/reviewer`) alongside Track Application and Registration Hub. |
| `frontend/app/page.tsx` | `LoginPage` | Added "Forgot Password?" link on login card and "Activate Account" link in footer. |

---

## 3. Reviewer Portal Architecture & Workflow

### A. Dashboard Statistics Panel
Calculates live metrics from the applications returned by the backend:
- **Total Assigned:** Count of all applications visible in reviewer jurisdiction.
- **Awaiting My Action:** Applications where `current_stage` matches the reviewer's current tier (`DISTRICT_REVIEW` for District, `STATE_REVIEW` for State, `CENTRAL_REVIEW` for Central).
- **Under Active Review:** Applications in `UNDER_REVIEW` or `SUBMITTED` status.
- **Correction Required:** Applications returned to applicant for missing information.
- **Approved & Cleared:** Successfully provisioned facilities.
- **Rejected:** Applications declined due to non-compliance.

### B. Searchable Application Inbox
- **Debounced Search:** Filters by Application Number, Entity Name, Nodal Officer, City, or District.
- **Tier & Stage Filters:** Filter by Stage (`DISTRICT_REVIEW`, `STATE_REVIEW`, `CENTRAL_REVIEW`, `APPROVED`, `REJECTED`) and Type (`HOSPITAL`, `DISTRICT`, `STATE`).
- **Jurisdiction Enforced:** Backed by `/api/registration/review/applications`, which strictly restricts queries using the reviewer's JWT claims (`state` and `district`).

### C. Detailed Application Dossier & Secure Preview
- **Capacity & Facility Profile:** Displays total beds, ICU capacity, oxygen generation plants, ventilator count, and emergency ambulance coverage.
- **Document Checklist:** Shows each uploaded document (Clinical Establishment License, Fire Safety NOC, Pollution Control NOC, Medical Council Affiliation, Government Order).
- **In-Memory File Preview Modal:** Reviewers can click "Preview" to fetch the binary file via authenticated blob download (`/api/registration/applications/documents/{id}/download`), inspecting PDFs and images directly in a sandboxed iframe/modal without exposing storage URLs.
- **Inline Document Actions:** Independent verification controls for each document (`VERIFIED` or `REJECTED` with remarks).

---

## 4. Hierarchical Approval State Machine

The approval state machine enforces strict linear progression:

```
[ HOSPITAL APPLICATION ]
   │
   ▼
[ DISTRICT_REVIEW ]  ──(Reviewer: DISTRICT_ADMIN in same District)
   │  ├── FORWARD ───────► [ STATE_REVIEW ]
   │  ├── REQUEST_CORRECTION ──► [ CORRECTION_REQUIRED ] ──► (Applicant resubmits)
   │  └── REJECT ────────► [ REJECTED ] (Terminal)
   │
   ▼
[ STATE_REVIEW ]     ──(Reviewer: STATE_ADMIN in same State)
   │  ├── FORWARD ───────► [ CENTRAL_REVIEW ]
   │  ├── REQUEST_CORRECTION ──► [ CORRECTION_REQUIRED ] ──► (Applicant resubmits)
   │  └── REJECT ────────► [ REJECTED ] (Terminal)
   │
   ▼
[ CENTRAL_REVIEW ]   ──(Reviewer: CENTRAL_ADMIN Nationwide)
   │  ├── APPROVE ───────► [ APPROVED ] ──► [ ATOMIC PROVISIONING + OUTBOX EVENT ]
   │  ├── REQUEST_CORRECTION ──► [ CORRECTION_REQUIRED ] ──► (Applicant resubmits)
   │  └── REJECT ────────► [ REJECTED ] (Terminal)
```

### Boundary & Security Rules:
- **No Stage Skipping:** District Admin cannot APPROVE directly. State Admin cannot APPROVE hospital applications directly. Central Admin cannot act on an application while it remains in District Review.
- **Geographic Authorization:** Reviewers attempting to fetch or modify applications outside their assigned state/district receive `403 Forbidden` (`GeographicAccessError`).
- **Hospital Role Isolation:** Operational hospital staff attempting to access reviewer routes receive `403 Forbidden`.
- **Self-Approval Mitigation:** Applicants cannot review or approve applications where applicant email, nodal name, or entity ID matches reviewer identity (`SelfApprovalError`).

---

## 5. Decision Engine & Atomic Provisioning

When a Central Admin executes `APPROVE` on an application at the `CENTRAL_REVIEW` stage:
1. **Pre-requisite Validation:** Verification check ensures all required compliance documents are in `VERIFIED` status.
2. **Atomic Transaction:** Within a single database transaction (`session.begin_nested()` / `session.commit()`):
   - Application status updates to `APPROVED` and `current_stage` to `APPROVED`.
   - `final_approved_at` timestamp recorded.
   - For `HOSPITAL` applications, a new record is created in `hospitals` table.
   - A new administrative user is created in `users` table with status `is_active=True`, role set to `HOSPITAL`, `DISTRICT_ADMIN`, or `STATE_ADMIN`, and `password_hash="PENDING_ACTIVATION"`.
   - A 72-hour cryptographic activation token is generated (`secrets.token_urlsafe(32)`), stored as a SHA-256 hash in `account_activation_tokens`.
   - An activation event is created in `registration_email_outbox` with status `PENDING`.
3. **Outbox Post-Commit Dispatch:** The transactional outbox worker picks up the activation event, formats the activation email with the secure activation link, and dispatches via configured email provider.

---

## 6. Document Verification Workflow

- **Endpoint:** `POST /api/registration/review/documents/{id}/verify`
- **Payload:** `{"verification_status": "VERIFIED" | "REJECTED", "reviewer_remarks": "..."}`
- **Behavior:**
  - `VERIFIED`: Updates document status to `VERIFIED`, records reviewer user ID, and timestamps the review.
  - `REJECTED`: Updates status to `REJECTED` and records reviewer remarks detailing why the document failed inspection.
  - **Authorization:** Only reviewers within the application's current review tier and jurisdiction can verify documents.

---

## 7. Account Activation Workflow

- **Public Routes:** `/activate` and `/activate/resend`
- **Activation Token Handling:**
  - Token is transmitted as a URL query parameter (`/activate?token=...`).
  - Frontend auto-populates the token into the activation form.
  - Backend verifies the token hash against `account_activation_tokens`.
  - Enforces `expires_at > NOW()` (72-hour limit) and `is_consumed == False`.
- **Password Complexity Rules:**
  - Minimum 8 characters.
  - At least one uppercase letter (`[A-Z]`).
  - At least one lowercase letter (`[a-z]`).
  - At least one numeric digit (`[0-9]`).
  - At least one special symbol (`[!@#$%^&*(),.?":{}|<>]`).
  - Password and confirm password must match exactly.
- **Atomic Consumption:** Token is marked `is_consumed=True`, `consumed_at=NOW()`, and the user's password hash is updated using PBKDF2-HMAC-SHA256 (100,000 iterations).

---

## 8. Password Reset Workflow

- **Public Routes:** `/forgot-password` and `/reset-password`
- **Timing-Attack & Enumeration Defense:**
  - `POST /api/registration/auth/password-reset/request`
  - Returns identical response: `"If an active account exists with the provided email address, a password reset link has been dispatched."` regardless of whether the email exists.
  - Internal hash timing simulation prevents side-channel timing analysis.
- **Reset Token Lifecycle:**
  - Token expires in 1 hour.
  - Stored exclusively as SHA-256 hash in `password_reset_tokens`.
  - Replay prevention: Consumed immediately upon first successful reset.
  - Updates password hash and invalidates prior sessions.

---

## 9. Operational Dashboard Integration

The Reviewer Portal has been integrated directly into the existing operational dashboards:
- **District Operations Dashboard (`frontend/components/DistrictDashboard.tsx`):**
  - Added "Registration & Review" tab.
  - Filters automatically to applications originating within the district.
- **State Operations Dashboard (`frontend/components/StateDashboard.tsx`):**
  - Added "Registration & Review" tab.
  - Filters automatically to applications across all districts within the state.
- **Central Operations Dashboard (`frontend/components/CentralDashboard.tsx`):**
  - Added "National Registration & Approvals" tab.
  - Provides nationwide visibility and final accreditation authority.

---

## 10. Backend API & Endpoint Inventory

| Endpoint | Method | Role Required | Geographic Scope |
|:---|:---|:---|:---|
| `/api/registration/review/applications` | GET | `DISTRICT_ADMIN`, `STATE_ADMIN`, `CENTRAL_ADMIN` | Enforced by user's assigned jurisdiction |
| `/api/registration/review/applications/{id}` | GET | Reviewer role | Strict boundary check matching application |
| `/api/registration/review/documents/{id}/verify` | POST | Reviewer role | Restricted to current stage reviewer |
| `/api/registration/review/applications/{id}/decision` | POST | Reviewer role | Enforces state machine transitions |
| `/api/registration/review/applications/{id}/request-correction` | POST | Reviewer role | Restricted to current stage reviewer |
| `/api/registration/applications/documents/{id}/download` | GET | Applicant or Reviewer | Validates applicant ownership or reviewer scope |
| `/api/registration/auth/activate` | POST | Public | Validates single-use 72h activation token |
| `/api/registration/auth/activation/resend` | POST | Public | Validates application number & email |
| `/api/registration/auth/password-reset/request` | POST | Public | Timing-safe request endpoint |
| `/api/registration/auth/password-reset/confirm` | POST | Public | Validates 1h reset token & updates password |

---

## 11. Security Audit & Boundary Matrix

| Security Check | Implementation | Test Status |
|:---|:---|:---|
| **Role Authorization** | Hospital staff cannot access reviewer routes (returns 403) | **VERIFIED (Passed)** |
| **District Isolation** | District CMO cannot access applications from other districts | **VERIFIED (Passed)** |
| **State Isolation** | State Director cannot access applications from other states | **VERIFIED (Passed)** |
| **Self-Approval Block** | Applicant cannot approve or forward their own application | **VERIFIED (Passed)** |
| **Terminal Protection** | Applications already APPROVED or REJECTED cannot be reviewed | **VERIFIED (Passed)** |
| **Password Complexity** | Weak passwords (< 8 chars, no symbol/digit) rejected with 422 | **VERIFIED (Passed)** |
| **Token Single-Use** | Activation and Reset tokens cannot be reused (replay rejected) | **VERIFIED (Passed)** |
| **Token Expiry** | Expired tokens rejected with 400 Bad Request | **VERIFIED (Passed)** |
| **Secure Download** | Document binary downloaded via authenticated JWT blob stream | **VERIFIED (Passed)** |

---

## 12. Data Privacy & Leaks Audit

- **No Passwords in Storage or Logs:** User passwords are never logged, never cached in `localStorage`, and never returned in API responses.
- **No Raw Tokens in Public Responses:** Public tracking endpoints (`/api/registration/applications/track`) return sanitized milestone timelines without internal notes, reviewer user IDs, or sensitive tokens.
- **Sanitized Outbox Payloads:** Log records mask recipient email addresses (`_mask_email`).
- **No Token Leaks in Client URLs:** Document downloads use `Authorization: Bearer <jwt>` headers rather than query parameter access tokens.

---

## 13. Live Email Delivery Status

- **Status:** **PENDING CREDENTIAL CONFIGURATION**
- **Architecture Ready:** Brevo SMTP configuration parameters (`SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USE_TLS=true`, `SMTP_FROM_EMAIL=noreply@hospital-referral.gov.in`) are fully integrated and tested with fail-closed behavior in production mode.
- **Current Mode:** Automated tests run with `SimulatedEmailProvider` to prevent unauthenticated network calls and ensure 100% reproducible testing. Live credentials will be supplied in staging/production environment files.

---

## 14. Test Suites & Verification Results

### Complete Test Run (70 Passed, 0 Failed, 0 Skipped):
```bash
.venv/bin/pytest tests/test_phase2d_reviewer_and_lifecycle.py tests/test_email_delivery_and_smtp.py tests/test_document_storage_and_provisioning.py tests/test_registration_api.py -v
```

### Breakdown of Test Results:
1. `tests/test_phase2d_reviewer_and_lifecycle.py`: **12 Passed**
   - Reviewer role authorization (Hospital staff rejected: 403)
   - District reviewer geographic boundary enforcement
   - State reviewer geographic boundary enforcement
   - Central reviewer nationwide access
   - Document verification lifecycle (VERIFIED, REJECTED, Cross-district 403)
   - Hospital complete hierarchical approval to provisioning
   - Invalid decision transitions blocked (Central early review: 403; Terminal app: 400)
   - Rejection workflow and terminal state
   - Correction request workflow
   - Account activation lifecycle & password complexity enforcement
   - Expired activation token rejection (400)
   - Password recovery request timing-safe response & reset confirmation
2. `tests/test_email_delivery_and_smtp.py`: **14 Passed**
3. `tests/test_document_storage_and_provisioning.py`: **24 Passed**
4. `tests/test_registration_api.py`: **20 Passed**

**Total Test Count:** **70 Passed in 3.44s**

---

## 15. Non-Mocked / Real Database Evidence

- **Isolated Test Database:** All tests run against SQLite in-memory databases with `StaticPool` and full foreign key constraint checks.
- **`sih_hospital_dev` Protection:** Verified that zero migrations or schema changes were applied to the local PostgreSQL development database (`sih_hospital_dev`). All 500 hospital records remain intact and unchanged.

---

## 16. Frontend Build Verification

Executed Next.js 16.3.0 Turbopack production build:
```bash
cd frontend && npm run build
```

**Build Output:**
```
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 121ms
  Creating an optimized production build ...
✓ Compiled successfully in 981ms
  Finished TypeScript in 1768ms
  Collecting page data using 7 workers in 362ms
✓ Generating static pages using 7 workers (15/15) in 158ms
  Finalizing page optimization in 7ms

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /activate
├ ○ /activate/resend
├ ○ /application/status
├ ○ /application/track
├ ○ /forgot-password
├ ○ /register
├ ○ /register/district
├ ○ /register/hospital
├ ○ /register/state
├ ○ /reset-password
├ ○ /reviewer
└ ƒ /reviewer/applications/[id]

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```
**Result:** **0 TypeScript errors, 0 compilation warnings, 15 routes generated.**

---

## 17. Database Constraints & Migration Safety

- Migration `migrations/003_registration_system.sql` defines:
  - `chk_reg_doc_verification_status` (`PENDING`, `VERIFIED`, `REJECTED`)
  - `chk_email_outbox_status` (`PENDING`, `PROCESSING`, `SENT`, `FAILED`)
  - `chk_reg_app_stage` and `chk_reg_app_status`
- Migration file remains unmodified during this phase.

---

## 18. Known Limitations & Edge Cases Handled

1. **Email Delivery Simulation in Dev:** In local development without live Brevo SMTP credentials, email delivery remains simulated via `SimulatedEmailProvider`.
2. **Re-submission Version Tracking:** Resubmission after `CORRECTION_REQUIRED` increments `resubmission_version` and moves the application back to its appropriate tier for re-inspection.
3. **Audit History Completeness:** Every decision, forwarding, rejection, and document review creates an unmodifiable record in `approval_history` storing reviewer user ID, role, review tier, previous status, new status, remarks, and client IP address.

---

## 19. Exact Files Created & Modified

### New Frontend Files:
- `frontend/components/reviewer/ReviewerDashboardStats.tsx`: KPI metrics calculation component.
- `frontend/components/reviewer/ReviewerInboxTable.tsx`: Full-featured data table with debounced search, filtering, and pagination.
- `frontend/components/reviewer/ReviewerDossierView.tsx`: Comprehensive application review view with document verification and action modals.
- `frontend/components/reviewer/ReviewerPortal.tsx`: Main reviewer container component.
- `frontend/app/reviewer/page.tsx`: Protected `/reviewer` route.
- `frontend/app/reviewer/applications/[id]/page.tsx`: Protected dossier route `/reviewer/applications/[id]`.
- `frontend/app/activate/page.tsx`: Public `/activate` account activation page.
- `frontend/app/activate/resend/page.tsx`: Public `/activate/resend` activation link resend page.
- `frontend/app/forgot-password/page.tsx`: Public `/forgot-password` recovery request page.
- `frontend/app/reset-password/page.tsx`: Public `/reset-password` token confirmation page.

### Modified Frontend Files:
- `frontend/lib/types.ts`: Added reviewer data types, document items, decision payloads, and activation response schemas.
- `frontend/lib/api.ts`: Added Reviewer API client functions (`apiGetReviewerApplications`, `apiVerifyReviewerDocument`, `apiExecuteReviewDecision`, `apiReviewerRequestCorrection`, `apiDownloadDocumentBlob`, `apiActivateAccount`, `apiResendActivation`, `apiRequestPasswordReset`, `apiConfirmPasswordReset`).
- `frontend/components/DistrictDashboard.tsx`: Integrated Reviewer Portal tab.
- `frontend/components/StateDashboard.tsx`: Integrated Reviewer Portal tab.
- `frontend/components/CentralDashboard.tsx`: Integrated Reviewer Portal tab.
- `frontend/components/registration/RegistrationNavbar.tsx`: Added `/reviewer` navigation link.
- `frontend/app/page.tsx`: Added "Forgot Password?" and "Activate Account" links.

### New Test Files:
- `tests/test_phase2d_reviewer_and_lifecycle.py`: 12 comprehensive automated tests verifying the reviewer matrix, hierarchical transitions, document verification, account activation, and password recovery.

---

## 20. Git Status & Stash Verification

- **Branch:** `master`
- **Git Commit:** None executed.
- **Git Push:** None executed.
- **Stash Status:** `stash@{0}: On master: Backup before GitHub repository synchronization` remains 100% intact.
- **Working Tree:** All changes remain in the local working tree ready for inspection.

---

## 21. Acceptance Criteria Checklist

- [x] Complete Reviewer Portal with KPI stats, searchable inbox, and pagination.
- [x] Detailed Dossier view with capacity statistics, nodal credentials, and document checklist.
- [x] In-browser document preview modal for PDFs and images via authenticated blob streaming.
- [x] Document verification API with `VERIFIED` and `REJECTED` actions and remarks requirement.
- [x] Hierarchical decision engine enforcing linear progression (Hospital, District, State).
- [x] Atomic operational provisioning upon final Central Government approval.
- [x] Transactional outbox event creation for account activation email dispatch.
- [x] Account activation portal (`/activate`, `/activate/resend`) with password complexity checks.
- [x] Password reset portal (`/forgot-password`, `/reset-password`) with timing-attack prevention.
- [x] District, State, and Central operational dashboard navigation integration.
- [x] Zero modifications or migrations applied to `sih_hospital_dev`.
- [x] No commit or push performed; stash preserved.
- [x] 70 passing backend tests; 0 errors in Next.js Turbopack build.

---

## 22. Conclusion & Readiness for User Review

Phase 2D has been implemented with complete fidelity to architectural specifications, strict geographic access controls, and zero regressions. The system is ready for user review.
