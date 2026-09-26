#!/bin/sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
output="${1:-backups/leadprophet-$(date +%Y%m%d-%H%M%S).dump}"
mkdir -p "$(dirname "$output")"
pg_dump --format=custom --no-owner --no-acl --file="$output" "$DATABASE_URL"
pg_restore --list "$output" >/dev/null
echo "PostgreSQL backup verified: $output"
