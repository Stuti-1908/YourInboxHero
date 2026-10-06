#!/bin/sh
# Restore a backup produced by backup_database.sh (M5/M6).
#
# DESTRUCTIVE: this overwrites the target database's current contents.
# Always double-check DATABASE_URL (in .env) points at the database you
# actually intend to restore into before running this.
#
# Usage: ./restore_database.sh <path-to-backup.sql.gz>

set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path-to-backup.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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

echo "About to restore $BACKUP_FILE into:"
echo "  $DATABASE_URL" | sed -E 's/:[^:@]+@/:****@/'  # mask the password
echo
printf "Type 'yes' to continue: "
read -r CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restoring..."
gunzip -c "$BACKUP_FILE" | docker run --rm -i postgres:17-alpine psql "$DATABASE_URL"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restore complete."
