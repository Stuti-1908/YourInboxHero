#!/bin/bash
# Nightly database backup (M5). Runs pg_dump against the production
# Postgres database (via a throwaway postgres:17-alpine container, since
# the Hetzner host itself has no Postgres client tools installed) and
# writes a timestamped, gzip-compressed dump to BACKUP_DIR, pruning
# anything older than RETENTION_DAYS.
#
# Interim measure per the production audit (M5/M6): stored on the same
# Hetzner server the app runs on, which is NOT off-site -- if this server
# is lost, these backups are lost with it. Good enough as a first line of
# defense against bad migrations, accidental deletes, or data corruption;
# revisit moving these off-server (S3/Backblaze) or upgrading to Supabase
# Pro (automatic off-site backups + point-in-time recovery) before this is
# the only backup a paying customer's data depends on.
#
# Requires bash (not /bin/sh) for `set -o pipefail` below — without it,
# `pg_dump ... | gzip` only reports gzip's exit code, so a failed pg_dump
# (e.g. the dialect-qualified-URL bug this script once had, see below)
# still looks like success and silently writes a tiny, broken backup file.
#
# Usage: ./backup_database.sh
# Expects to be run from the repo root with .env present (same file
# docker-compose reads DATABASE_URL from).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
ENV_FILE="$REPO_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi

DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d'=' -f2-)
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set in $ENV_FILE" >&2
    exit 1
fi
# The app's DATABASE_URL uses SQLAlchemy's dialect-qualified scheme
# (postgresql+psycopg2://), which pg_dump/psql don't understand as a URI
# -- they silently fall back to a local Unix-socket connection attempt
# instead of erroring on the unrecognized scheme, which is how this
# produced a tiny, broken "backup" the first time this script ran rather
# than a clear connection error.
DATABASE_URL=$(echo "$DATABASE_URL" | sed 's#^postgresql+psycopg2://#postgresql://#')

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_FILE="$BACKUP_DIR/yourinboxhero_${TIMESTAMP}.sql.gz"
TMP_FILE="${OUT_FILE}.tmp"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting backup -> $OUT_FILE"

# --no-owner/--no-acl: Supabase's managed roles won't exist on a restore
# target you control, and ownership/ACL statements referencing them would
# just fail noisily on restore for no benefit.
if docker run --rm postgres:17-alpine \
    pg_dump --no-owner --no-acl --format=plain "$DATABASE_URL" \
    | gzip > "$TMP_FILE"; then
    # Sanity check: a real dump of this schema is comfortably >1KB even
    # near-empty. Catches silent failure modes pipefail wouldn't (e.g. a
    # pg_dump that exits 0 but emits only warnings/empty output).
    MIN_BYTES=1024
    ACTUAL_BYTES=$(wc -c < "$TMP_FILE")
    if [ "$ACTUAL_BYTES" -lt "$MIN_BYTES" ]; then
        rm -f "$TMP_FILE"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: dump suspiciously small (${ACTUAL_BYTES} bytes) — treating as failed" >&2
        exit 1
    fi
    mv "$TMP_FILE" "$OUT_FILE"
    SIZE=$(du -h "$OUT_FILE" | cut -f1)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete: $OUT_FILE ($SIZE)"
else
    rm -f "$TMP_FILE"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: pg_dump failed" >&2
    exit 1
fi

# Prune backups older than RETENTION_DAYS.
find "$BACKUP_DIR" -name 'yourinboxhero_*.sql.gz' -type f -mtime +"$RETENTION_DAYS" -print -delete

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Done. Current backups:"
ls -lh "$BACKUP_DIR"/yourinboxhero_*.sql.gz 2>/dev/null || echo "(none)"
