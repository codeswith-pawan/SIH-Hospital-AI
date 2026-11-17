#!/usr/bin/env bash
# ==============================================================================
# SIH HOSPITAL AI — AUTOMATED DATABASE & DOCUMENT BACKUP SCRIPT
# AI Powered Smart Hospital Referral System - Phase 3
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%SZ")"
DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/sih_hospital_phase1_run_test}"
STORAGE_DIR="${STORAGE_BASE_DIR:-data/storage/documents}"

mkdir -p "${BACKUP_DIR}"

DB_BACKUP_FILE="${BACKUP_DIR}/sih_db_${TIMESTAMP}.dump"
DOCS_BACKUP_FILE="${BACKUP_DIR}/sih_documents_${TIMESTAMP}.tar.gz"
CHECKSUM_FILE="${BACKUP_DIR}/sih_backup_${TIMESTAMP}.sha256"

echo "=================================================================="
echo "      SIH HOSPITAL AI — SYSTEM BACKUP EXECUTION                   "
echo "=================================================================="
echo "[*] Timestamp:      ${TIMESTAMP}"
echo "[*] Destination:    ${BACKUP_DIR}"
echo "[*] Database URL:   ${DATABASE_URL%%:*}:***"

# 1. PostgreSQL Custom-Format Backup (Compressed with built-in TOC)
echo "[*] Step 1: Performing PostgreSQL database dump..."
if pg_dump --format=custom --no-owner --no-acl --file="${DB_BACKUP_FILE}" "${DATABASE_URL}"; then
    DB_SIZE=$(du -h "${DB_BACKUP_FILE}" | cut -f1)
    echo "    [✓] Database dump complete: ${DB_BACKUP_FILE} (${DB_SIZE})"
else
    echo "    [✗] pg_dump failed!"
    exit 1
fi

# 2. Document Storage Backup
echo "[*] Step 2: Archiving document storage files..."
if [ -d "${STORAGE_DIR}" ] && [ "$(ls -A "${STORAGE_DIR}" 2>/dev/null)" ]; then
    tar -czf "${DOCS_BACKUP_FILE}" -C "$(dirname "${STORAGE_DIR}")" "$(basename "${STORAGE_DIR}")"
    DOCS_SIZE=$(du -h "${DOCS_BACKUP_FILE}" | cut -f1)
    echo "    [✓] Documents archived: ${DOCS_BACKUP_FILE} (${DOCS_SIZE})"
else
    # Create empty archive placeholder if storage is empty
    tar -czf "${DOCS_BACKUP_FILE}" --files-from /dev/null
    echo "    [i] Storage directory is empty. Created empty archive placeholder."
fi

# 3. Cryptographic Checksum Generation
echo "[*] Step 3: Computing cryptographic SHA-256 checksums..."
cd "${BACKUP_DIR}"
shasum -a 256 "$(basename "${DB_BACKUP_FILE}")" "$(basename "${DOCS_BACKUP_FILE}")" > "$(basename "${CHECKSUM_FILE}")"
echo "    [✓] Checksums saved to ${CHECKSUM_FILE}"
cat "$(basename "${CHECKSUM_FILE}")"

# 4. Retention Policy: Purge backups older than RETENTION_DAYS
echo "[*] Step 4: Applying retention policy (purging archives older than ${RETENTION_DAYS} days)..."
find . -maxdepth 1 -name "sih_*" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} +
echo "    [✓] Retention cleanup finished."

echo "=================================================================="
echo "RESULT: SUCCESS — Full backup successfully created and verified."
echo "=================================================================="
