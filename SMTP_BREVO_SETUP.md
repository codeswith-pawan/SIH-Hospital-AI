# Brevo SMTP Integration & Operational Setup Guide
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** 3 — Production Readiness  

---

## 1. Overview
The SIH Hospital AI platform routes all transactional emails (Applicant OTP verification codes, Central Approval account activation invitations, and Password Reset tokens) through Brevo (formerly Sendinblue) SMTP via STARTTLS over port 587.

The application uses an asynchronous, transactional outbox pattern to guarantee at-least-once delivery, preventing lost emails on temporary network partitions.

---

## 2. Obtaining Brevo Credentials

1. **Log in to Brevo:** Visit [https://app.brevo.com](https://app.brevo.com).
2. **Navigate to SMTP Settings:**
   - In the top-right profile dropdown, click **SMTP & API**.
   - Select the **SMTP** tab.
3. **Retrieve Connection Details:**
   - **SMTP Host:** `smtp-relay.brevo.com`
   - **Port:** `587`
   - **Login / Username:** Your Brevo account email address (e.g. `admin@yourdomain.com`).
4. **Generate Master SMTP Key:**
   - Click **Generate a new SMTP key**.
   - Give it a recognizable name (e.g., `SIH_Hospital_Prod_Key`).
   - Copy the generated master SMTP key (format: `xsmtpsib-...`).
   - *Caution:* This key is displayed only once. Store it in your secure secret manager.
5. **Verify Sender Domain:**
   - Go to **Senders, Domains & Dedicated IPs** -> **Domains**.
   - Add your official domain (e.g. `hospital.sih.gov.in`).
   - Configure the required DNS records (DKIM, SPF, and DMARC).
   - Under **Senders**, add the verified sender email (e.g., `no-reply@hospital.sih.gov.in`).

---

## 3. Configuring Environment Variables

Edit your production `.env` or system environment (e.g., `/etc/sih-hospital-ai/production.env`):

```bash
# Email Backend Selector (must be 'smtp' for live delivery)
SIH_EMAIL_BACKEND=smtp

# OTP Provider Selector (must be 'EMAIL' for SMTP OTP delivery)
SIH_OTP_PROVIDER=EMAIL

# Brevo SMTP Server Configuration
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_TIMEOUT=15

# Brevo Credentials (interchangeable between SMTP_USERNAME and SMTP_USER)
SMTP_USERNAME=your_brevo_login_email@domain.com
SMTP_PASSWORD=xsmtpsib-your_brevo_smtp_api_key_here

# Sender Address (must be authorized on Brevo)
SMTP_FROM_EMAIL=no-reply@hospital.sih.gov.in
```

---

## 4. Operational Verification & Health Diagnostics

The platform includes two safe diagnostic CLI tools:

### 4.1 Step 1: Run SMTP Health Check (Non-destructive)
Verifies DNS resolution, TCP handshake, and STARTTLS negotiation without sending any emails:

```bash
# Using python directly:
.venv/bin/python scripts/smtp_health_check.py

# Expected Output:
# [*] Step 1: Configuration Parameters Inspection (Masked)
# [*] Step 2: DNS Resolution for host 'smtp-relay.brevo.com' -> Resolved
# [*] Step 3: TCP Socket Connection to smtp-relay.brevo.com:587 -> Handshake successful
# [*] Step 4: SMTP Handshake & STARTTLS Negotiation -> TLS context verified
# [*] Step 5: SMTP Authentication Verification -> Authentication SUCCESSFUL
# RESULT: PASS
```

### 4.2 Step 2: Send Single Controlled Test Email
Dispatches a single message to a designated operator inbox for live verification:

```bash
.venv/bin/python scripts/send_test_email.py --to operator@yourdomain.gov.in

# Expected Output:
# [*] Initiating controlled test email...
#     - Recipient: o***@yourdomain.gov.in
#     - Provider:  SMTPEmailProvider
#     - Backend:   smtp
# [✓] SUCCESS: Test email accepted for delivery to o***@yourdomain.gov.in.
```

---

## 5. Security & Privacy Rules
1. **Never Log Plaintext Passwords or Keys:** All logs automatically mask usernames (`br***@example.com`) and passwords (`***`).
2. **Never Send Plaintext Passwords in Emails:** Account activation emails send single-use cryptographic tokens with 72-hour expiry, forcing the user to create their own password.
3. **No Phantom OTPs:** If SMTP delivery fails during OTP dispatch, an error is raised immediately, preventing an un-delivered OTP from being created.
