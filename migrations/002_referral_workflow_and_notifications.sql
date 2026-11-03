-- Phase 18: End-to-End Hospital Referral Workflow & Notifications Migration
-- AI Powered Smart Hospital Referral System

-- 1. Add ambulance_id and eta_minutes to referrals table
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS ambulance_id VARCHAR(64);
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS eta_minutes INTEGER;

-- 2. Create notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    hospital_id VARCHAR(32) NOT NULL REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    referral_id VARCHAR(64) REFERENCES referrals(referral_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'NORMAL' NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- 3. Create index for fast hospital notification queries
CREATE INDEX IF NOT EXISTS idx_notifications_hospital ON notifications(hospital_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_referral ON notifications(referral_id);
