-- Migration 005: Worker Heartbeats Table for Container-Safe Observability
-- AI Powered Smart Hospital Referral System - Phase 4D-1

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_name VARCHAR(64) PRIMARY KEY,
    worker_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_success_at TIMESTAMPTZ,
    last_error_at TIMESTAMPTZ,
    last_error TEXT,
    processed_total BIGINT NOT NULL DEFAULT 0,
    failed_total BIGINT NOT NULL DEFAULT 0,
    batch_size INT NOT NULL DEFAULT 100,
    duration_seconds FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_worker_status CHECK (status IN ('RUNNING', 'STOPPED', 'FAILED', 'IDLE'))
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeat_status ON worker_heartbeats(status, last_heartbeat);
