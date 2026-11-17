-- =====================================================================
-- SIH_Hospital_AI — PostgreSQL Migration 003: Hierarchical Registration System
-- Version: 003 (Corrected & Hardened)
-- Date: 2026-11-03
-- Description: Schema for multi-tier government registration, verification,
--              document tracking, protected approval history, verification tokens,
--              reusable tracking tokens, activation tokens, and deterministic grandfathering.
-- =====================================================================

BEGIN;

-- 1. Extend hospitals table with approval and grandfathering metadata
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'PENDING' NOT NULL;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS is_grandfathered BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS application_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_hospitals_approval ON hospitals (approval_status, is_grandfathered);
CREATE INDEX IF NOT EXISTS idx_hospitals_application_id ON hospitals (application_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hospitals_application_id ON hospitals (application_id) WHERE application_id IS NOT NULL;

-- 2. Extend users table with contact and application metadata
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(30);
ALTER TABLE users ADD COLUMN IF NOT EXISTS designation VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS application_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_application_id ON users (application_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_application_id ON users (application_id) WHERE application_id IS NOT NULL;

-- 3. Registration Applications Table
CREATE TABLE IF NOT EXISTS registration_applications (
    application_id VARCHAR(64) PRIMARY KEY,
    application_number VARCHAR(64) UNIQUE NOT NULL,
    applicant_type VARCHAR(20) NOT NULL CHECK (applicant_type IN ('STATE', 'DISTRICT', 'HOSPITAL')),
    applicant_name VARCHAR(255) NOT NULL,
    applicant_email VARCHAR(255) NOT NULL,
    applicant_phone VARCHAR(30) NOT NULL,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    city VARCHAR(100),
    address TEXT,
    pincode VARCHAR(20),
    official_designation VARCHAR(100),
    nodal_officer_name VARCHAR(255),
    parent_state VARCHAR(100),
    parent_district VARCHAR(100),
    profile_data JSONB,
    current_stage VARCHAR(30) NOT NULL DEFAULT 'DRAFT'
        CHECK (current_stage IN ('DRAFT', 'SUBMITTED', 'DISTRICT_REVIEW', 'STATE_REVIEW', 'CENTRAL_REVIEW', 'APPROVED', 'REJECTED', 'CORRECTION_REQUIRED')),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'REJECTED', 'SUSPENDED')),
    resubmission_version INT NOT NULL DEFAULT 1 CHECK (resubmission_version >= 1),
    rejection_reason TEXT,
    correction_notes TEXT,
    provisioned_entity_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    resubmitted_at TIMESTAMPTZ,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    final_approved_at TIMESTAMPTZ
);

-- Ensure defaults and CHECK constraints are aligned even if table already existed
ALTER TABLE registration_applications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE registration_applications ADD COLUMN IF NOT EXISTS resubmitted_at TIMESTAMPTZ;
ALTER TABLE registration_applications ALTER COLUMN status SET DEFAULT 'DRAFT';
ALTER TABLE registration_applications ALTER COLUMN current_stage SET DEFAULT 'DRAFT';
ALTER TABLE registration_applications ALTER COLUMN resubmission_version SET DEFAULT 1;
ALTER TABLE registration_applications ALTER COLUMN submitted_at DROP NOT NULL;
ALTER TABLE registration_applications ALTER COLUMN submitted_at DROP DEFAULT;
ALTER TABLE registration_applications ALTER COLUMN created_at SET DEFAULT NOW();
ALTER TABLE registration_applications ALTER COLUMN last_updated_at SET DEFAULT NOW();

-- Trigger to automatically manage submitted_at, resubmitted_at, and last_updated_at lifecycle
CREATE OR REPLACE FUNCTION trg_fn_manage_application_submission_lifecycle()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IN ('SUBMITTED', 'UNDER_REVIEW') OR NEW.current_stage IN ('SUBMITTED', 'DISTRICT_REVIEW', 'STATE_REVIEW', 'CENTRAL_REVIEW') THEN
            IF NEW.submitted_at IS NULL THEN
                NEW.submitted_at := NOW();
            END IF;
        ELSE
            NEW.submitted_at := NULL;
        END IF;
        NEW.last_updated_at := NOW();
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        -- 1. Initial submission: transition from DRAFT (or submitted_at was NULL) to SUBMITTED
        IF (OLD.status = 'DRAFT' OR OLD.submitted_at IS NULL) AND
           (NEW.status IN ('SUBMITTED', 'UNDER_REVIEW') OR NEW.current_stage IN ('SUBMITTED', 'DISTRICT_REVIEW', 'STATE_REVIEW', 'CENTRAL_REVIEW')) THEN
            IF NEW.submitted_at IS NULL THEN
                NEW.submitted_at := NOW();
            END IF;

        -- 2. Resubmission after CORRECTION_REQUIRED:
        ELSIF OLD.status = 'CORRECTION_REQUIRED' AND NEW.status IN ('SUBMITTED', 'UNDER_REVIEW') THEN
            -- Preserve original submission timestamp:
            IF OLD.submitted_at IS NOT NULL THEN
                NEW.submitted_at := OLD.submitted_at;
            ELSIF NEW.submitted_at IS NULL THEN
                NEW.submitted_at := NOW();
            END IF;
            -- Explicit resubmission timestamp policy: preserve original submitted_at, record in resubmitted_at
            NEW.resubmitted_at := NOW();
            -- Increment resubmission_version exactly once upon resubmission
            NEW.resubmission_version := OLD.resubmission_version + 1;

        -- 3. Repeated updates while already SUBMITTED or UNDER_REVIEW:
        ELSIF OLD.submitted_at IS NOT NULL THEN
            -- Preserve original submission timestamp (never overwrite)
            NEW.submitted_at := OLD.submitted_at;
            -- Preserve existing resubmission_version on repeated updates (do not increment again)
            IF NEW.resubmission_version IS NULL OR NEW.resubmission_version = OLD.resubmission_version THEN
                NEW.resubmission_version := OLD.resubmission_version;
            END IF;
        END IF;

        -- Preserve existing resubmitted_at if not explicitly updating it
        IF OLD.resubmitted_at IS NOT NULL AND NEW.resubmitted_at IS NULL THEN
            NEW.resubmitted_at := OLD.resubmitted_at;
        END IF;

        NEW.last_updated_at := NOW();
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_application_submission_lifecycle ON registration_applications;
CREATE TRIGGER trg_application_submission_lifecycle
BEFORE INSERT OR UPDATE ON registration_applications
FOR EACH ROW
EXECUTE FUNCTION trg_fn_manage_application_submission_lifecycle();

-- Note: application_number UNIQUE automatically creates a unique btree index.
-- Drop legacy redundant non-unique index if present
DROP INDEX IF EXISTS idx_reg_app_number;

CREATE INDEX IF NOT EXISTS idx_reg_app_status ON registration_applications (status, current_stage);
CREATE INDEX IF NOT EXISTS idx_reg_app_geo ON registration_applications (state, district);
CREATE INDEX IF NOT EXISTS idx_reg_app_email ON registration_applications (applicant_email);
CREATE INDEX IF NOT EXISTS idx_reg_app_type ON registration_applications (applicant_type);

-- Partial unique indexes to prevent concurrent duplicate active applications
-- Active statuses: DRAFT, SUBMITTED, UNDER_REVIEW, CORRECTION_REQUIRED
-- Canonical identities:
-- 1. State: LOWER(TRIM(state)) for applicant_type = 'STATE'
-- 2. District: LOWER(TRIM(state)), LOWER(TRIM(district)) for applicant_type = 'DISTRICT'
-- 3. Hospital: LOWER(TRIM(applicant_email)) for applicant_type = 'HOSPITAL'
-- (REJECTED and APPROVED applications do not prevent new applications)
CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_state
ON registration_applications (LOWER(TRIM(state)))
WHERE applicant_type = 'STATE' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_district
ON registration_applications (LOWER(TRIM(state)), LOWER(TRIM(district)))
WHERE applicant_type = 'DISTRICT' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_app_active_hospital_email
ON registration_applications (LOWER(TRIM(applicant_email)))
WHERE applicant_type = 'HOSPITAL' AND status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'CORRECTION_REQUIRED');

-- Link application_id foreign keys back from hospitals and users
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_hospitals_application' AND table_name = 'hospitals'
    ) THEN
        ALTER TABLE hospitals ADD CONSTRAINT fk_hospitals_application
        FOREIGN KEY (application_id) REFERENCES registration_applications(application_id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_users_application' AND table_name = 'users'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT fk_users_application
        FOREIGN KEY (application_id) REFERENCES registration_applications(application_id) ON DELETE SET NULL;
    END IF;
END $$;

-- 4. Registration Documents Table
CREATE TABLE IF NOT EXISTS registration_documents (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR(64) UNIQUE NOT NULL,
    application_id VARCHAR(64) NOT NULL REFERENCES registration_applications(application_id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL
        CHECK (document_type IN ('CLINICAL_LICENSE', 'FIRE_SAFETY_NOC', 'POLLUTION_CONTROL_NOC', 'MEDICAL_COUNCIL_AFFILIATION', 'GOVERNMENT_ORDER', 'IDENTITY_PROOF', 'OTHER')),
    storage_key VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    checksum_sha256 VARCHAR(64) NOT NULL,
    verification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED')),
    reviewer_id VARCHAR(32) REFERENCES users(user_id) ON DELETE SET NULL,
    reviewer_remarks TEXT,
    reviewed_at TIMESTAMPTZ,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE registration_documents ALTER COLUMN uploaded_at SET DEFAULT NOW();

-- Note: document_id UNIQUE already creates a unique index.
CREATE INDEX IF NOT EXISTS idx_reg_doc_app_id ON registration_documents (application_id);
CREATE INDEX IF NOT EXISTS idx_reg_doc_status ON registration_documents (verification_status);

-- 5. Approval History Table (Protected Append-Only Audit Trail)
-- Uses ON DELETE RESTRICT so that registration_applications with approval history cannot be deleted
CREATE TABLE IF NOT EXISTS approval_history (
    id BIGSERIAL PRIMARY KEY,
    application_id VARCHAR(64) NOT NULL REFERENCES registration_applications(application_id) ON DELETE RESTRICT,
    reviewer_user_id VARCHAR(32) REFERENCES users(user_id) ON DELETE SET NULL,
    reviewer_role VARCHAR(32) NOT NULL,
    action VARCHAR(50) NOT NULL
        CHECK (action IN ('SUBMIT', 'FORWARD', 'APPROVE', 'REJECT', 'REQUEST_CORRECTION', 'RESUBMIT', 'SUSPEND', 'REACTIVATE')),
    review_tier VARCHAR(30) NOT NULL
        CHECK (review_tier IN ('APPLICANT', 'DISTRICT', 'STATE', 'CENTRAL')),
    previous_status VARCHAR(30) NOT NULL,
    new_status VARCHAR(30) NOT NULL,
    remarks TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure foreign key constraint uses ON DELETE RESTRICT
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc ON rc.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'approval_history' AND rc.delete_rule = 'CASCADE'
    ) THEN
        ALTER TABLE approval_history DROP CONSTRAINT IF EXISTS approval_history_application_id_fkey;
        ALTER TABLE approval_history ADD CONSTRAINT approval_history_application_id_fkey
            FOREIGN KEY (application_id) REFERENCES registration_applications(application_id) ON DELETE RESTRICT;
    END IF;
END $$;

ALTER TABLE approval_history ALTER COLUMN created_at SET DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_approval_history_app_id ON approval_history (application_id, created_at DESC);

-- Trigger to protect approval_history against application-level UPDATE and DELETE
CREATE OR REPLACE FUNCTION trg_fn_protect_approval_history()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Approval history is an append-only audit trail: % operation is prohibited on table approval_history.', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_approval_history ON approval_history;
CREATE TRIGGER trg_protect_approval_history
BEFORE UPDATE OR DELETE ON approval_history
FOR EACH ROW
EXECUTE FUNCTION trg_fn_protect_approval_history();

-- 6. Verification Tokens Table (Email & SMS OTPs)
CREATE TABLE IF NOT EXISTS verification_tokens (
    id BIGSERIAL PRIMARY KEY,
    token_id VARCHAR(64) UNIQUE NOT NULL,
    contact_target VARCHAR(255) NOT NULL,
    token_channel VARCHAR(20) NOT NULL CHECK (token_channel IN ('EMAIL', 'SMS')),
    token_purpose VARCHAR(30) NOT NULL
        CHECK (token_purpose IN ('REGISTRATION_OTP', 'LOGIN_OTP', 'PASSWORD_RESET_OTP', 'PORTAL_ACCESS_OTP')),
    token_hash VARCHAR(255) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INT NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    resend_available_at TIMESTAMPTZ NOT NULL,
    application_id VARCHAR(64) REFERENCES registration_applications(application_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE verification_tokens ALTER COLUMN created_at SET DEFAULT NOW();
ALTER TABLE verification_tokens ADD COLUMN IF NOT EXISTS application_id VARCHAR(64) REFERENCES registration_applications(application_id) ON DELETE CASCADE;

-- Note: token_id UNIQUE already creates a unique index.
CREATE INDEX IF NOT EXISTS idx_verification_tokens_target ON verification_tokens (contact_target, token_purpose, is_verified);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_expiry ON verification_tokens (expires_at) WHERE is_verified = FALSE;
CREATE INDEX IF NOT EXISTS idx_verification_tokens_app_id ON verification_tokens (application_id);

-- 7. Application Tracking Tokens Table (Reusable, Time-Bound, Revocable Tracking Access)
CREATE TABLE IF NOT EXISTS application_tracking_tokens (
    id BIGSERIAL PRIMARY KEY,
    tracking_token_id VARCHAR(64) UNIQUE NOT NULL,
    application_id VARCHAR(64) NOT NULL REFERENCES registration_applications(application_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ,
    access_count INT NOT NULL DEFAULT 0 CHECK (access_count >= 0),
    revoked_at TIMESTAMPTZ,
    revocation_reason VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE application_tracking_tokens ALTER COLUMN created_at SET DEFAULT NOW();

ALTER TABLE application_tracking_tokens ADD COLUMN IF NOT EXISTS access_count INT NOT NULL DEFAULT 0;
ALTER TABLE application_tracking_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
ALTER TABLE application_tracking_tokens ADD COLUMN IF NOT EXISTS revocation_reason VARCHAR(255);

-- Note: tracking_token_id UNIQUE already creates a unique index.
CREATE INDEX IF NOT EXISTS idx_tracking_tokens_app_id ON application_tracking_tokens (application_id);
CREATE INDEX IF NOT EXISTS idx_tracking_tokens_hash ON application_tracking_tokens (token_hash);

-- 8. Account Activation Tokens Table (Post-Approval Onboarding)
CREATE TABLE IF NOT EXISTS account_activation_tokens (
    id BIGSERIAL PRIMARY KEY,
    activation_token_id VARCHAR(64) UNIQUE NOT NULL,
    application_id VARCHAR(64) REFERENCES registration_applications(application_id) ON DELETE SET NULL,
    user_id VARCHAR(32) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    is_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE account_activation_tokens ALTER COLUMN created_at SET DEFAULT NOW();

-- Note: activation_token_id UNIQUE already creates a unique index.
CREATE INDEX IF NOT EXISTS idx_activation_tokens_user ON account_activation_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_activation_tokens_hash ON account_activation_tokens (token_hash);

-- 9. Transactional Email Outbox Table (Durable Delivery, Retry & Audit)
CREATE TABLE IF NOT EXISTS registration_email_outbox (
    id BIGSERIAL PRIMARY KEY,
    outbox_id VARCHAR(64) UNIQUE NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    recipient_name VARCHAR(255),
    subject VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')),
    retry_count INT NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INT NOT NULL DEFAULT 3 CHECK (max_retries > 0),
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_email_outbox_queue ON registration_email_outbox (status, next_retry_at);

-- 10. Password Reset Tokens Table (Time-Bound, Single-Use, Cryptographically Hashed)
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    reset_token_id VARCHAR(64) UNIQUE NOT NULL,
    user_id VARCHAR(32) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    is_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_hash ON password_reset_tokens (token_hash);

-- 11. Deterministic Grandfathering of Exactly Verified 500 Legacy Hospitals
DO $$
DECLARE
    v_legacy_total INT;
    v_legacy_grandfathered INT;
    v_legacy_approved INT;
    v_non_legacy_grandfathered INT;
    v_updated_count INT;
BEGIN
    -- 1. Verify existence of the exact expected legacy hospital set: GH00001 through GH00500
    SELECT COUNT(*) INTO v_legacy_total
    FROM hospitals
    WHERE hospital_id ~ '^GH[0-9]{5}$'
      AND hospital_id >= 'GH00001'
      AND hospital_id <= 'GH00500';

    IF v_legacy_total <> 500 THEN
        RAISE EXCEPTION 'Grandfathering aborted: expected exactly 500 legacy hospitals (GH00001-GH00500), but found %', v_legacy_total;
    END IF;

    -- 2. Verify that NO hospital outside the legacy set is grandfathered
    SELECT COUNT(*) INTO v_non_legacy_grandfathered
    FROM hospitals
    WHERE is_grandfathered = TRUE
      AND NOT (hospital_id ~ '^GH[0-9]{5}$' AND hospital_id >= 'GH00001' AND hospital_id <= 'GH00500');

    IF v_non_legacy_grandfathered > 0 THEN
        RAISE EXCEPTION 'Grandfathering aborted: detected % unexpected non-legacy hospitals with is_grandfathered = TRUE', v_non_legacy_grandfathered;
    END IF;

    -- 3. Check grandfathered status within the legacy set
    SELECT COUNT(*) INTO v_legacy_grandfathered
    FROM hospitals
    WHERE hospital_id ~ '^GH[0-9]{5}$'
      AND hospital_id >= 'GH00001'
      AND hospital_id <= 'GH00500'
      AND is_grandfathered = TRUE;

    IF v_legacy_grandfathered = 0 THEN
        -- Case A: Fresh migration run — grandfather all 500 legacy hospitals
        UPDATE hospitals
        SET approval_status = 'APPROVED',
            is_grandfathered = TRUE,
            approved_at = NOW()
        WHERE hospital_id ~ '^GH[0-9]{5}$'
          AND hospital_id >= 'GH00001'
          AND hospital_id <= 'GH00500'
          AND is_grandfathered = FALSE;

        GET DIAGNOSTICS v_updated_count = ROW_COUNT;
        IF v_updated_count <> 500 THEN
            RAISE EXCEPTION 'Grandfathering update failed: expected 500 updated rows, but updated %', v_updated_count;
        END IF;

        RAISE NOTICE 'Successfully grandfathered exactly % verified legacy hospitals (GH00001-GH00500).', v_updated_count;

    ELSIF v_legacy_grandfathered = 500 THEN
        -- Case B: Idempotent rerun — verify that all 500 are also APPROVED and have approved_at set
        SELECT COUNT(*) INTO v_legacy_approved
        FROM hospitals
        WHERE hospital_id ~ '^GH[0-9]{5}$'
          AND hospital_id >= 'GH00001'
          AND hospital_id <= 'GH00500'
          AND is_grandfathered = TRUE
          AND approval_status = 'APPROVED'
          AND approved_at IS NOT NULL;

        IF v_legacy_approved <> 500 THEN
            RAISE EXCEPTION 'Grandfathering state inconsistent: all 500 legacy hospitals are marked grandfathered, but only % are APPROVED with non-null approved_at.', v_legacy_approved;
        END IF;

        RAISE NOTICE 'Migration 003 rerun: all 500 legacy hospitals verified as already approved and grandfathered. No update needed.';

    ELSE
        -- Case C: Partial grandfathered state (0 < v_legacy_grandfathered < 500)
        RAISE EXCEPTION 'Grandfathering state inconsistent: partial grandfathering detected (% of 500 legacy hospitals grandfathered). Aborting and rolling back.', v_legacy_grandfathered;
    END IF;
END $$;

COMMIT;
