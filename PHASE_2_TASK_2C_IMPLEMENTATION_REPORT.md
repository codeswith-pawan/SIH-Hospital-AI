# PHASE 2 — TASK 2C: APPLICANT REGISTRATION PORTAL IMPLEMENTATION REPORT

**Project:** SIH Hospital AI  
**Branch:** `master`  
**Date:** November 2026  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

Phase 2 Task 2C delivers the applicant-facing registration portal for the **Hierarchical Government Registration, Verification & Approval System**. The portal connects directly to the Phase 1 backend APIs without duplicating business logic, establishing a unified interface for healthcare facilities and administrative authorities across India.

### Key Achievements
- **6 App Router Pages Created:**
  - `/register`: Registration hub with tier selection for State, District, and Hospital applicants.
  - `/register/state`: State Directorate registration wizard.
  - `/register/district`: District Health Administration registration wizard.
  - `/register/hospital`: Hospital facility onboarding with bed and critical care capacities.
  - `/application/track`: Public unauthenticated milestone tracking using Reference Number and Secret Tracking Token.
  - `/application/status`: Authenticated applicant dashboard supporting draft resumption, document replacement, reviewer feedback inspection, and correction resubmissions.
- **Dynamic Jurisdiction Integration:** Synchronized with the backend `CANONICAL_DIVISIONS` across all 16 Indian states and their designated districts.
- **Two-Factor Email OTP Verification:** Clean modal workflow with 60-second cooldown timers and transient applicant token session management.
- **Secure Document Upload:** Client-side MIME (PDF, JPEG, PNG) and 25MB file validation with server-side ClamAV malware scanning, magic byte verification, and SHA-256 derivation.
- **Strict Data Privacy:** Zero document exposure in public tracking; zero passwords or OTPs stored in `localStorage`; applicant session tokens isolated to `sessionStorage`.
- **100% Production Build Success:** Built cleanly via Next.js 16.3.0 Turbopack and TypeScript with 0 errors.

---

## 2. Created Routes & Component Architecture

### Route Hierarchy

| Route | Purpose | Access Level | Primary Component / Actions |
|---|---|---|---|
| `/register` | Entity Selection Hub | Public | Cards for Hospital, District, State onboarding + quick links to track / resume. |
| `/register/hospital` | Hospital Facility Wizard | Public / Applicant | 4-step wizard: Facility info, Nodal Officer + OTP, Document upload, Preview & Submit. |
| `/register/district` | District Administration Form | Public / Applicant | 4-step wizard: Territorial jurisdiction, CMO contact + OTP, Government Order, Submit. |
| `/register/state` | State Directorate Form | Public / Applicant | 4-step wizard: State jurisdiction, Directorate contact + OTP, State Order, Submit. |
| `/application/track` | Public Milestone Tracker | Public | Input `application_number` + `tracking_token`; renders sanitized timeline. |
| `/application/status` | Applicant Workspace | Authenticated Applicant | 2FA OTP sign-in, document replacement, reviewer feedback, correction resubmission loop. |

### Component Architecture

1. **`RegistrationNavbar` (`frontend/components/registration/RegistrationNavbar.tsx`)**:
   - Navigation header linking Hub, Tracking, Applicant Portal, and Operations Login.
   - Government badge, active route indicators, and responsive mobile navigation.
2. **`ApplicationTimeline` (`frontend/components/registration/ApplicationTimeline.tsx`)**:
   - Visual 6-stage stepper: `DRAFT` → `SUBMITTED` → `DISTRICT_REVIEW` → `STATE_REVIEW` → `CENTRAL_REVIEW` → `APPROVED & PROVISIONED`.
   - Distinct visual states for active review (blue pulse), approved (emerald), rejected (rose), and correction-required (amber alert).
   - Milestone audit history table with action names and timestamps.
3. **`DocumentUploader` (`frontend/components/registration/DocumentUploader.tsx`)**:
   - Multi-slot uploader supporting required and optional certificates.
   - Enforces PDF, JPEG, PNG client-side validation and max 25 MB limit.
   - Displays file size formatting, verification status badges (`VERIFIED`, `PENDING`, `REJECTED`), and reviewer feedback remarks.
   - Document replacement and deletion in `DRAFT` or `CORRECTION_REQUIRED` status.
4. **`OTPModal` (`frontend/components/registration/OTPModal.tsx`)**:
   - Two-factor verification dialog requesting 6-digit OTP dispatched to applicant email.
   - 60-second cooldown timer for code resend.
   - Error states, rate limit messaging, and single-use verification.

---

## 3. Dynamic Jurisdiction Engine (`frontend/lib/jurisdictions.ts`)

Mirrors the canonical backend divisions defined in `src/services/registration_service.py` covering all 16 Indian states and their designated districts:
- **States:** Andhra Pradesh, Bihar, Delhi, Gujarat, Haryana, Kerala, Karnataka, Madhya Pradesh, Maharashtra, Odisha, Punjab, Rajasthan, Tamil Nadu, Telangana, Uttar Pradesh, West Bengal.
- **Dynamic Selection:** Selecting a State dynamically populates only canonical districts, preventing jurisdiction mismatch before API transmission.

---

## 4. API Client & Session Management (`frontend/lib/api.ts`)

All registration endpoints are typed and routed through `API_BASE` (`process.env.NEXT_PUBLIC_API_URL` or `http://127.0.0.1:8000`):

- `apiSendRegistrationOTP`: Calls `POST /api/registration/auth/otp/request`.
- `apiVerifyRegistrationOTP`: Calls `POST /api/registration/auth/otp/verify`.
- `apiCreateHospitalApplication`: Calls `POST /api/registration/applications/hospital`.
- `apiCreateDistrictApplication`: Calls `POST /api/registration/applications/district`.
- `apiCreateStateApplication`: Calls `POST /api/registration/applications/state`.
- `apiGetMyApplication`: Calls `GET /api/registration/applications/me` with `Authorization: Bearer <applicant_token>`.
- `apiUpdateDraftApplication`: Calls `PUT /api/registration/applications/draft`.
- `apiUploadDocument`: Calls `POST /api/registration/applications/documents/upload` via `FormData`.
- `apiDeleteDocument`: Calls `DELETE /api/registration/applications/documents/{document_id}`.
- `apiSubmitApplication`: Calls `POST /api/registration/applications/submit`.
- `apiResubmitApplication`: Calls `POST /api/registration/applications/resubmit`.
- `apiPublicTrackApplication`: Calls `GET /api/registration/public/track/{app_number}?tracking_token={token}`.

### Storage & Security Discipline
- **Applicant Token Storage:** Uses `sessionStorage.getItem("sih_applicant_token")` and `sessionStorage.setItem("sih_applicant_token", token)`.
- **Zero LocalStorage Contamination:** Passwords, OTPs, and applicant tokens are strictly excluded from `localStorage`.
- **Session Revocation:** Signing out immediately purges `sessionStorage`.

---

## 5. Verification & Testing Evidence

### 1. Next.js Production Build
Executed `npm run build` in `frontend/`:
```
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 48ms
  Creating an optimized production build ...
✓ Compiled successfully in 836ms
✓ Finished TypeScript in 1723ms 
✓ Collecting page data using 7 workers in 391ms 
✓ Generating static pages using 7 workers (10/10) in 143ms
✓ Finalizing page optimization in 14ms 

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /application/status
├ ○ /application/track
├ ○ /register
├ ○ /register/district
├ ○ /register/hospital
└ ○ /register/state

○  (Static)  prerendered as static content
```
**Result:** 10/10 static pages compiled with Turbopack and TypeScript with 0 errors.

### 2. Backend Regression Test Suite
Executed test suites via `.venv/bin/pytest`:
```bash
.venv/bin/pytest tests/test_email_delivery_and_smtp.py tests/test_document_storage_and_provisioning.py tests/test_registration_postgresql_live.py tests/test_registration_api.py tests/test_registration_service.py tests/test_registration_models.py -q
```
**Result:** 126 passed in 7.62s.

---

## 6. Files Created & Modified

### Created Files
1. `frontend/lib/jurisdictions.ts`: Canonical divisions mapping and jurisdiction validators.
2. `frontend/components/registration/RegistrationNavbar.tsx`: Shared navigation header.
3. `frontend/components/registration/ApplicationTimeline.tsx`: Stepper, status badges, and milestone audit table.
4. `frontend/components/registration/DocumentUploader.tsx`: Multipart document uploader and file validator.
5. `frontend/components/registration/OTPModal.tsx`: Two-factor OTP request and verification modal.
6. `frontend/app/register/page.tsx`: Registration type selection hub.
7. `frontend/app/register/hospital/page.tsx`: Hospital onboarding wizard.
8. `frontend/app/register/district/page.tsx`: District authority registration form.
9. `frontend/app/register/state/page.tsx`: State directorate registration form.
10. `frontend/app/application/track/page.tsx`: Public milestone tracking portal.
11. `frontend/app/application/status/page.tsx`: Authenticated applicant status and correction workspace.

### Modified Files
1. `frontend/lib/types.ts`: Added full TypeScript definitions for registration, documents, OTP, and tracking.
2. `frontend/lib/api.ts`: Added applicant token storage helpers and typed registration API calls.
3. `frontend/app/page.tsx`: Added registration links to header navigation and login card footer.

---

## 7. Compliance Checklist

- [x] State, District, and Hospital registration forms implemented.
- [x] Dynamic jurisdiction selection (`CANONICAL_DIVISIONS`) implemented.
- [x] Applicant contact info and email OTP verification implemented.
- [x] Save draft and resume application implemented.
- [x] Document upload with file validation (PDF, JPEG, PNG <= 25MB) implemented.
- [x] Application preview before submission implemented.
- [x] Reference number (`application_number`) and `tracking_token` displayed upon submission.
- [x] Application tracking timeline with visual milestones implemented.
- [x] Correction-required status handling and resubmission loop implemented.
- [x] Clear loading, validation, and API error states implemented.
- [x] No sensitive tokens or passwords stored in `localStorage`.
- [x] Existing operational dashboards and login behaviors preserved.
- [x] Git stash `stash@{0}` intact.
- [x] No commits or pushes performed.
- [x] Database `sih_hospital_dev` untouched.
