# Production Setup & Operations Guide
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** 3 — Production Readiness  

---

## 1. System Requirements & Architecture

The SIH Hospital AI platform is built as a hardened monolithic service designed for high throughput, strict security, and complete transactional integrity:

- **Backend:** Python 3.14+ / FastAPI ASGI with Uvicorn (4 worker processes).
- **Frontend:** Next.js 16+ Standalone Node.js server.
- **Database:** PostgreSQL 15+ Cluster (tested with PostgreSQL 17) with connection pooling (`pool_size=20`, `max_overflow=10`).
- **Distributed Cache & Rate Limiter:** Redis 7+ Sentinel or Cluster.
- **Background Worker:** Standalone Python process for transactional outbox dispatch.
- **Reverse Proxy:** Nginx or Cloudflare managing SSL/TLS termination, HSTS, and rate-limiting.

---

## 2. Step-by-Step Deployment Options

### Option A: Containerized Deployment via Docker Compose

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-org/SIH_Hospital_AI.git /opt/sih_hospital_ai
   cd /opt/sih_hospital_ai
   ```

2. **Configure Production Environment:**
   ```bash
   cp .env.production.example .env.production
   # Edit .env.production with strong passwords, Brevo credentials, and JWT secret:
   chmod 600 .env.production
   ```

3. **Build and Launch Services:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

4. **Verify Health:**
   ```bash
   curl http://localhost:8000/health/ready
   # Expected: {"ready": true, "database": {"status": "HEALTHY"}}
   ```

---

### Option B: Native Host Deployment (Systemd + Virtual Environment)

1. **Prerequisites (Ubuntu/Debian):**
   ```bash
   sudo apt-get update && sudo apt-get install -y python3-venv python3-dev build-essential libpq-dev postgresql redis-server nginx
   ```

2. **Setup Virtual Environment:**
   ```bash
   cd /opt/sih_hospital_ai
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Setup Database:**
   ```bash
   sudo -u postgres psql -c "CREATE USER sih_admin WITH PASSWORD 'SECURE_PASSWORD';"
   sudo -u postgres psql -c "CREATE DATABASE sih_hospital_prod OWNER sih_admin;"
   psql postgresql://sih_admin:SECURE_PASSWORD@localhost:5432/sih_hospital_prod -f migrations/001_initial_postgresql_schema.sql
   psql postgresql://sih_admin:SECURE_PASSWORD@localhost:5432/sih_hospital_prod -f migrations/002_referral_workflow_and_notifications.sql
   psql postgresql://sih_admin:SECURE_PASSWORD@localhost:5432/sih_hospital_prod -f migrations/003_registration_system.sql
   ```

4. **Build Frontend:**
   ```bash
   cd frontend
   npm ci
   npm run build
   ```

5. **Start Systemd Services:**
   - Configure `sih-backend.service` (runs `uvicorn src.api.main:app --workers 4`).
   - Configure `sih-outbox-worker.service` (runs `python -m src.workers.outbox_worker`).
   - Configure `sih-frontend.service` (runs `node .next/standalone/server.js`).

---

## 3. Production Health Probes & Monitoring

| Endpoint | Method | Purpose | Response |
|:---|:---|:---|:---|
| `/health/live` | GET | Liveness probe (Kubernetes/Docker) | `{"status": "UP"}` |
| `/health/ready` | GET | Readiness probe (DB, Redis, Config) | HTTP 200 (Ready) / HTTP 503 (Not Ready) |
| `/metrics` | GET | Operational statistics | Request latencies, status counts, queue stats |
