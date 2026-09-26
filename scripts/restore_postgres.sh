#!/bin/sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${1:?usage: restore_postgres.sh BACKUP.dump}"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$DATABASE_URL" "$1"
echo "PostgreSQL restore complete: $1"
