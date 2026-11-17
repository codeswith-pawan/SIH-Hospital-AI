# Database Backup, Disaster Recovery & Storage Resilience Guide
**Project:** AI Powered Smart Hospital Referral System (`SIH_Hospital_AI`)  
**Phase:** 3 — Production Readiness  

---

## 1. Disaster Recovery Objectives

- **Recovery Point Objective (RPO):** Maximum 1 hour (via hourly automated backups or continuous PostgreSQL WAL archiving).
- **Recovery Time Objective (RTO):** Maximum 30 minutes from disaster declaration to restored operational traffic.
- **Backup Frequency:** Automated hourly differential dumps and daily full dumps.
- **Retention Period:** 7 days locally, 30 days in off-site encrypted object storage.

---

## 2. Automated Backup Execution

The backup utility archives both the PostgreSQL relational database schema & data and the uploaded applicant documents into timestamped, checksummed archives.

### Running a Manual Backup
```bash
# Execute full backup
./scripts/backup_database.sh
```

### Environment Overrides
- `BACKUP_DIR`: Directory to store backups (default: `data/backups`).
- `RETENTION_DAYS`: Number of days to retain backups before purging (default: `7`).
- `DATABASE_URL`: Connection string of source database.
- `STORAGE_BASE_DIR`: Directory holding uploaded documents (default: `data/storage/documents`).

### Backup Output Files
```
data/backups/
├── sih_db_20261110_204922Z.dump           # Custom-format compressed pg_dump (with TOC)
├── sih_documents_20261110_204922Z.tar.gz   # Compressed archive of all applicant documents
└── sih_backup_20261110_204922Z.sha256      # SHA-256 cryptographic verification checksums
```

---

## 3. Disaster Recovery & Controlled Restore Procedure

### Strict Safety Invariants
1. **Never restore to `sih_hospital_dev`:** The restore script explicitly aborts if `sih_hospital_dev` is passed as the target database.
2. **Mandatory Checksum Verification:** The script verifies the SHA-256 checksum of the `.dump` archive before initiating PostgreSQL restore.
3. **Always test on a disposable database first:** Before restoring to production, verify the backup archive against a clean temporary database.

### Restore Command
```bash
./scripts/restore_database.sh \
  --db-dump data/backups/sih_db_20261110_204922Z.dump \
  --target-db-url postgresql://app_user:secret@localhost:5432/sih_hospital_prod \
  --docs-tar data/backups/sih_documents_20261110_204922Z.tar.gz \
  --restore-docs-to /var/lib/sih/documents
```

---

## 4. Verification Evidence (Phase 3 Controlled Test)

A controlled restore test was executed during Phase 3 verification:
1. Full backup created: `sih_db_20261110_204922Z.dump` (140 KB, 18 tables).
2. Disposable test database created: `sih_hospital_phase3_restore_test`.
3. Restore executed with checksum verification: **PASS**.
4. Post-restore table count: **18 public tables verified**.
5. Hospital record count: **517 hospitals verified** (500 seed hospitals + 17 test hospitals).
6. Document archive extracted and verified: **PASS**.
7. Disposable database dropped after test completion: **PASS**.
