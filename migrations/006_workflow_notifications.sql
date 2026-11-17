-- Phase 4D-2: Registration & Government Workflow Notifications Migration
-- Extends notifications table to support applicant and hierarchical government reviewer notifications.

-- 1. Allow hospital_id to be NULL for government and applicant notifications
ALTER TABLE notifications ALTER COLUMN hospital_id DROP NOT NULL;

-- 2. Add columns for users, applications, roles, jurisdictions, navigation and idempotency
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id VARCHAR(32) REFERENCES users(user_id) ON DELETE CASCADE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS application_id VARCHAR(64) REFERENCES registration_applications(application_id) ON DELETE CASCADE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS role_id VARCHAR(32) REFERENCES roles(id) ON DELETE CASCADE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS state VARCHAR(100);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS district VARCHAR(100);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS action_url VARCHAR(255);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128) UNIQUE;

-- 3. Indexes for fast reviewer, applicant, and jurisdiction notification lookups
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_app ON notifications(application_id);
CREATE INDEX IF NOT EXISTS idx_notifications_gov ON notifications(role_id, state, district, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_idempotency ON notifications(idempotency_key);
