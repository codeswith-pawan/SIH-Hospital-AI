-- =====================================================================
-- SIH_Hospital_AI — PostgreSQL Migration 001: Initial Relational Schema
-- Version: 001
-- Date: 2026-10-31
-- Description: Normalized relational schema with row-locking support,
--              partial unique indexes, check constraints, and audit logging.
-- =====================================================================

BEGIN;

-- 1. Roles Reference
CREATE TABLE IF NOT EXISTS roles (
    id VARCHAR(32) PRIMARY KEY,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed Canonical Administrative Roles
INSERT INTO roles (id, description) VALUES
    ('HOSPITAL', 'Hospital Clinical & Operations Staff'),
    ('DISTRICT_ADMIN', 'District Healthcare Administration'),
    ('STATE_ADMIN', 'State Government Healthcare Administration'),
    ('CENTRAL_ADMIN', 'National / Central Referral Oversight')
ON CONFLICT (id) DO NOTHING;

-- 2. Hospitals Master
CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    city VARCHAR(100),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    total_beds INT NOT NULL DEFAULT 0 CHECK (total_beds >= 0),
    occupied_beds INT NOT NULL DEFAULT 0 CHECK (occupied_beds >= 0),
    available_beds INT NOT NULL DEFAULT 0 CHECK (available_beds >= 0),
    icu_beds INT NOT NULL DEFAULT 0 CHECK (icu_beds >= 0),
    available_icu_beds INT NOT NULL DEFAULT 0 CHECK (available_icu_beds >= 0),
    emergency_beds INT NOT NULL DEFAULT 0 CHECK (emergency_beds >= 0),
    available_emergency_beds INT NOT NULL DEFAULT 0 CHECK (available_emergency_beds >= 0),
    emergency_24x7 VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (emergency_24x7 IN ('Yes', 'No')),
    accepts_referral VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (accepts_referral IN ('Yes', 'No')),
    ambulance VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (ambulance IN ('Yes', 'No')),
    oxygen_support VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (oxygen_support IN ('Yes', 'No')),
    ventilator VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (ventilator IN ('Yes', 'No')),
    blood_bank VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (blood_bank IN ('Yes', 'No')),
    cardiology VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (cardiology IN ('Yes', 'No')),
    neurology VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (neurology IN ('Yes', 'No')),
    nephrology VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (nephrology IN ('Yes', 'No')),
    pulmonology VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (pulmonology IN ('Yes', 'No')),
    orthopedics VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (orthopedics IN ('Yes', 'No')),
    general_medicine VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (general_medicine IN ('Yes', 'No')),
    general_surgery VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (general_surgery IN ('Yes', 'No')),
    trauma_unit VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (trauma_unit IN ('Yes', 'No')),
    burn_unit VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (burn_unit IN ('Yes', 'No')),
    ct_scan VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (ct_scan IN ('Yes', 'No')),
    mri VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (mri IN ('Yes', 'No')),
    xray VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (xray IN ('Yes', 'No')),
    ultrasound VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (ultrasound IN ('Yes', 'No')),
    ecg VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (ecg IN ('Yes', 'No')),
    dialysis VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (dialysis IN ('Yes', 'No')),
    blood_test VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (blood_test IN ('Yes', 'No')),
    cbc VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (cbc IN ('Yes', 'No')),
    troponin_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (troponin_test IN ('Yes', 'No')),
    dengue_ns1_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (dengue_ns1_test IN ('Yes', 'No')),
    malaria_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (malaria_test IN ('Yes', 'No')),
    blood_glucose_test VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (blood_glucose_test IN ('Yes', 'No')),
    hba1c_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (hba1c_test IN ('Yes', 'No')),
    kidney_function_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (kidney_function_test IN ('Yes', 'No')),
    pulmonary_function_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (pulmonary_function_test IN ('Yes', 'No')),
    blood_culture VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (blood_culture IN ('Yes', 'No')),
    lactate_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (lactate_test IN ('Yes', 'No')),
    stool_test VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (stool_test IN ('Yes', 'No')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hospitals_geo ON hospitals (state, district);

-- 3. Users Master
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(32) PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role_id VARCHAR(32) NOT NULL REFERENCES roles(id) ON UPDATE CASCADE,
    hospital_id VARCHAR(32) REFERENCES hospitals(hospital_id) ON DELETE SET NULL,
    state VARCHAR(100),
    district VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role_id);
CREATE INDEX IF NOT EXISTS idx_users_hospital ON users (hospital_id);

-- 4. Patients Master
CREATE TABLE IF NOT EXISTS patients (
    patient_id VARCHAR(32) PRIMARY KEY,
    abha_id VARCHAR(64) UNIQUE,
    name VARCHAR(255) NOT NULL,
    age INT CHECK (age >= 0 AND age <= 130),
    gender VARCHAR(20),
    disease VARCHAR(255),
    priority VARCHAR(20) NOT NULL CHECK (priority IN ('Critical', 'Urgent', 'Stable')),
    icu_required VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (icu_required IN ('Yes', 'No')),
    ambulance_required VARCHAR(10) NOT NULL DEFAULT 'No' CHECK (ambulance_required IN ('Yes', 'No')),
    referral_required VARCHAR(10) NOT NULL DEFAULT 'Yes' CHECK (referral_required IN ('Yes', 'No')),
    spo2 INT CHECK (spo2 >= 0 AND spo2 <= 100),
    systolic_bp INT,
    diastolic_bp INT,
    heart_rate INT,
    respiratory_rate INT,
    temperature DOUBLE PRECISION,
    severity_score DOUBLE PRECISION,
    state VARCHAR(100),
    district VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patients_priority ON patients (priority, icu_required);
CREATE INDEX IF NOT EXISTS idx_patients_geo ON patients (state, district);

-- 5. Hospital Visits
CREATE TABLE IF NOT EXISTS hospital_visits (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'NEW' 
        CHECK (status IN ('NEW', 'ACTIVE', 'COMPLETED', 'DISCHARGED', 'TRANSFERRED', 'DIED')),
    admission_type VARCHAR(30) NOT NULL DEFAULT 'DIRECT'
        CHECK (admission_type IN ('DIRECT', 'REFERRAL', 'EMERGENCY')),
    admitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    treatment_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hospital_visits_lookup ON hospital_visits (hospital_id, patient_id, status);

-- 6. Physical Bed Inventory
CREATE TABLE IF NOT EXISTS beds (
    id BIGSERIAL PRIMARY KEY,
    hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    bed_number VARCHAR(50) NOT NULL,
    bed_type VARCHAR(20) NOT NULL CHECK (bed_type IN ('GENERAL', 'ICU', 'EMERGENCY')),
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN ('AVAILABLE', 'RESERVED', 'OCCUPIED', 'MAINTENANCE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_hospital_bed UNIQUE (hospital_id, bed_number)
);

CREATE INDEX IF NOT EXISTS idx_beds_lookup ON beds (hospital_id, bed_type, status);

-- 7. Referrals Lifecycle Tracking
CREATE TABLE IF NOT EXISTS referrals (
    referral_id VARCHAR(64) PRIMARY KEY,
    patient_id VARCHAR(32) NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    from_hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE RESTRICT,
    to_hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'IN_TRANSIT', 'ARRIVED', 'TREATMENT_ACTIVE', 'COMPLETED', 'DISCHARGED', 'TRANSFERRED', 'DIED', 'CANCELLED')),
    priority VARCHAR(20) NOT NULL,
    bed_type VARCHAR(20) NOT NULL CHECK (bed_type IN ('GENERAL', 'ICU', 'EMERGENCY', 'Not specified')),
    reason TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    arrived_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_referrals_lookup ON referrals (to_hospital_id, from_hospital_id, status);
CREATE INDEX IF NOT EXISTS idx_referrals_patient ON referrals (patient_id);

-- 8. Bed Reservations Ledger
CREATE TABLE IF NOT EXISTS bed_reservations (
    reservation_id VARCHAR(64) PRIMARY KEY,
    referral_id VARCHAR(64) NOT NULL REFERENCES referrals(referral_id) ON DELETE CASCADE,
    hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    bed_id BIGINT NOT NULL REFERENCES beds(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'RESERVED'
        CHECK (status IN ('RESERVED', 'CONFIRMED', 'OCCUPIED', 'RELEASED', 'EXPIRED', 'CANCELLED')),
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partial Unique Index 1: A physical bed cannot have multiple active holds
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_bed_reservation
ON bed_reservations (bed_id)
WHERE status IN ('RESERVED', 'CONFIRMED', 'OCCUPIED');

-- Partial Unique Index 2: A referral cannot have duplicate active reservations
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_referral_reservation
ON bed_reservations (referral_id)
WHERE status IN ('RESERVED', 'CONFIRMED', 'OCCUPIED');

CREATE INDEX IF NOT EXISTS idx_reservations_referral ON bed_reservations (referral_id);
CREATE INDEX IF NOT EXISTS idx_reservations_expiry ON bed_reservations (expires_at) WHERE status = 'RESERVED';

-- 9. Audit Logging
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    action VARCHAR(50) NOT NULL,
    performed_by VARCHAR(64),
    previous_state JSONB,
    new_state JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs (created_at DESC);

COMMIT;
