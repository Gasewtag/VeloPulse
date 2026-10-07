#!/usr/bin/env bash
# ==============================================================================
# VeloPulse Database Restore Script
# Restores compressed database dump into target PostgreSQL instance.
# ==============================================================================

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <path_to_backup.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file '${BACKUP_FILE}' does not exist!" >&2
    exit 1
fi

POSTGRES_SERVER="${POSTGRES_SERVER:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-velopulse_user}"
POSTGRES_DB="${POSTGRES_DB:-velopulse_db}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Restoring database '${POSTGRES_DB}' from '${BACKUP_FILE}'..."

if command -v psql >/dev/null 2>&1; then
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    gunzip -c "${BACKUP_FILE}" | psql -h "${POSTGRES_SERVER}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
elif docker ps --format '{{.Names}}' | grep -q "postgres"; then
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep "postgres" | head -n 1)"
    echo "Executing psql restore via docker container: ${CONTAINER_NAME}"
    gunzip -c "${BACKUP_FILE}" | docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
else
    echo "ERROR: Neither psql binary nor a running postgres Docker container was found." >&2
    exit 1
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Database restoration completed successfully."
