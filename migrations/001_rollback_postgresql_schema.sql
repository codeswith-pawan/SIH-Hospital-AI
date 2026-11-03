-- =====================================================================
-- SIH_Hospital_AI — PostgreSQL Migration 001: Rollback Schema
-- Version: 001 Rollback
-- Date: 2026-10-31
-- Description: Safely drops Phase 15 tables in reverse topological order.
-- =====================================================================

BEGIN;

DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS bed_reservations CASCADE;
DROP TABLE IF EXISTS referrals CASCADE;
DROP TABLE IF EXISTS beds CASCADE;
DROP TABLE IF EXISTS hospital_visits CASCADE;
DROP TABLE IF EXISTS patients CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS hospitals CASCADE;
DROP TABLE IF EXISTS roles CASCADE;

COMMIT;
