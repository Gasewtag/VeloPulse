#!/usr/bin/env bash
# ==============================================================================
# VeloPulse Automated PostgreSQL Database Backup Script
# Creates compressed, timestamped database dumps and enforces retention policy.
# ==============================================================================

set -euo pipefail

# Configuration parameters with fallback defaults
POSTGRES_SERVER="${POSTGRES_SERVER:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-velopulse_user}"
POSTGRES_DB="${POSTGRES_DB:-velopulse_db}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%S")"
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_backup_${TIMESTAMP}.sql.gz"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting VeloPulse database backup for '${POSTGRES_DB}'..."

# Ensure backup destination directory exists
mkdir -p "${BACKUP_DIR}"

# Execute pg_dump directly or through Docker container
if command -v pg_dump >/dev/null 2>&1; then
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    pg_dump -h "${POSTGRES_SERVER}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --clean --if-exists --no-owner --no-privileges | gzip -9 > "${BACKUP_FILE}"
elif docker ps --format '{{.Names}}' | grep -q "postgres"; then
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep "postgres" | head -n 1)"
    echo "Executing pg_dump via docker container: ${CONTAINER_NAME}"
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${CONTAINER_NAME}" \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_FILE}"
else
    echo "ERROR: Neither pg_dump binary nor a running postgres Docker container was found." >&2
    exit 1
fi

# Verify backup archive exists and is non-empty
if [ ! -s "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file ${BACKUP_FILE} was not created or is empty!" >&2
    exit 1
fi

BACKUP_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup completed successfully: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Enforce retention policy: delete backups older than RETENTION_DAYS
echo "Applying retention policy: removing backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -name "${POSTGRES_DB}_backup_*.sql.gz" -type f -mtime +"${RETENTION_DAYS}" -exec rm -f {} +

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Database backup lifecycle completed."
