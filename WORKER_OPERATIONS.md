# Transactional Outbox Background Worker Operations Guide
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** 3 — Production Readiness  

---

## 1. Architectural Overview
The `OutboxWorker` is an autonomous background process that guarantees reliable, transactional delivery of outbound notifications (Account Activation, OTP verification, and Password Reset) using the **Transactional Outbox Pattern**:

```
[Application Transaction]
       │
       ▼ (Atomic commit)
[registration_email_outbox table (status=PENDING)]
       │
       ▼ (Poll via SELECT ... FOR UPDATE SKIP LOCKED)
[OutboxWorker Process]
       │
       ├─► Reclaims expired worker leases (> 300s)
       ├─► Dispatches via SMTPEmailProvider (Brevo)
       │       │
       │       ├─► Success: Mark status=SENT, sent_at=NOW()
       │       └─► Failure: Mark status=FAILED, increment retry_count,
       │                    compute exponential backoff (30s * 2^retry)
       ▼
[Delivery Complete / Dead-Letter Queue]
```

---

## 2. Delivery Guarantees & Fault Tolerance

### 2.1 At-Least-Once Delivery
- Because SMTP lacks a distributed Two-Phase Commit (2PC) protocol, a rare crash occurring immediately after SMTP server acceptance but before the database status update completes can result in a redelivery upon restart.
- Operational account provisioning and password reset tokens enforce single-use hashing at the database layer, ensuring duplicate email delivery does not compromise security.

### 2.2 Concurrency & Multi-Worker Scaling
- Worker instances use PostgreSQL `FOR UPDATE SKIP LOCKED`. Multiple worker processes on separate containers or nodes can safely poll the queue simultaneously without duplicate processing or thread contention.

### 2.3 Abandoned Lease Recovery
- If a worker process abruptly dies (e.g. OOM or node crash) while processing an event, the row remains in `PROCESSING` state.
- Surviving or restarted workers automatically reclaim rows where `status = 'PROCESSING'` and `processed_at < NOW() - lease_timeout` (default 300s).

### 2.4 Exponential Backoff & Max Retries
- Failed deliveries use exponential backoff:
  - Attempt 1: 30 seconds
  - Attempt 2: 60 seconds
  - Attempt 3: 120 seconds
  - Attempt 4: 240 seconds
  - Attempt 5: 480 seconds
- After `max_retries` (default: 5), the event is marked permanently `FAILED` with the last error recorded, preventing infinite retry loops.

---

## 3. Operational Commands & Deployment

### 3.1 Running as a Continuous Background Daemon
```bash
# Production daemon execution
.venv/bin/python -m src.workers.outbox_worker --interval 5.0 --batch-size 25
```

### 3.2 Running in Single-Pass (Cron / Test) Mode
```bash
# Execute a single processing pass and exit (ideal for container healthchecks or crontab)
.venv/bin/python -m src.workers.outbox_worker --run-once
```

### 3.3 Systemd Service Template (`/etc/systemd/system/sih-outbox-worker.service`)
```ini
[Unit]
Description=SIH Hospital AI Transactional Outbox Worker
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=sihuser
Group=sihgroup
WorkingDirectory=/opt/sih_hospital_ai
EnvironmentFile=/etc/sih-hospital-ai/production.env
ExecStart=/opt/sih_hospital_ai/.venv/bin/python -m src.workers.outbox_worker --interval 5.0 --batch-size 25
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

---

## 4. Operational Monitoring & Health

Query current queue status directly via the `/metrics` endpoint:
```bash
curl -s http://localhost:8000/metrics | jq .email_outbox_queue
```
Example Output:
```json
{
  "pending": 0,
  "processing": 0,
  "sent": 142,
  "failed": 0
}
```
