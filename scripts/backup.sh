#!/bin/sh
# IDP PostgreSQL Backup Script
# Runs daily at 03:00 MSK (00:00 UTC)
# Retention: 30 days

BACKUP_DIR="/backups"
DATE=$(date +%Y-%m-%d)
FILENAME="idp_backup_${DATE}.sql.gz"

echo "[$(date)] Starting backup..."

# pg_dump to gzipped file
PGPASSWORD="${PG_PASSWORD}" pg_dump \
  -h postgres \
  -U "${PG_USER:-idp_admin}" \
  -d "${PG_DB:-idp}" \
  --no-owner \
  --no-privileges \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

if [ $? -eq 0 ]; then
  SIZE=$(ls -lh "${BACKUP_DIR}/${FILENAME}" | awk '{print $5}')
  echo "[$(date)] Backup complete: ${FILENAME} (${SIZE})"
else
  echo "[$(date)] ERROR: Backup failed!"
  exit 1
fi

# Cleanup: remove backups older than 30 days
find "${BACKUP_DIR}" -name "idp_backup_*.sql.gz" -mtime +30 -delete
REMAINING=$(ls -1 "${BACKUP_DIR}"/idp_backup_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Cleanup done. ${REMAINING} backups retained."
