#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command tar
require_env_file

postgres_user="$(env_value POSTGRES_USER)"
postgres_db="$(env_value POSTGRES_DB)"
minio_user="$(env_value MINIO_ROOT_USER)"
minio_password="$(env_value MINIO_ROOT_PASSWORD)"
minio_bucket="$(env_value MINIO_BUCKET)"
backup_root="$(absolute_path "$(env_value BACKUP_DIR)")"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
label="${1:-manual}"
[[ "$label" =~ ^[a-zA-Z0-9._-]+$ ]] || die "backup label contains unsupported characters"
backup_dir="$backup_root/${timestamp}-${label}"

umask 077
mkdir -p "$backup_root"
mkdir "$backup_dir" || die "backup directory already exists: $backup_dir"
mkdir "$backup_dir/objects"
chmod 700 "$backup_dir"

wait_for_service db 60
wait_for_service minio 60

api_was_running=false
api_container="$(compose ps -q api-server)"
if [[ -n "$api_container" && "$(docker inspect --format '{{.State.Running}}' "$api_container")" == "true" ]]; then
  api_was_running=true
  info "Pausing API writes for a consistent backup..."
  compose stop api-server >/dev/null
fi

resume_api() {
  trap - EXIT
  if [[ "$api_was_running" == true ]]; then
    compose start api-server >/dev/null
    wait_for_service api-server 300
  fi
}
trap resume_api EXIT

info "Creating PostgreSQL backup..."
compose exec -T db pg_dump \
  --username "$postgres_user" \
  --dbname "$postgres_db" \
  --format custom \
  --no-owner \
  --no-acl >"$backup_dir/database.dump"

info "Mirroring object storage..."
network="$(minio_network)"
docker run --rm \
  --network "$network" \
  --volume "$backup_dir/objects:/backup" \
  --env "MINIO_ROOT_USER=$minio_user" \
  --env "MINIO_ROOT_PASSWORD=$minio_password" \
  --env "MINIO_BUCKET=$minio_bucket" \
  --entrypoint /bin/sh \
  "$(mc_image)" \
  -c 'mc alias set source http://minio:9200 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite source/"$MINIO_BUCKET" /backup' \
  >&2

tar -C "$backup_dir/objects" -czf "$backup_dir/objects.tar.gz" .
rm -rf "$backup_dir/objects"

cp "$ENV_FILE" "$backup_dir/secrets.env"
chmod 600 "$backup_dir/secrets.env"

platform_version="$(tr -d '\r\n' <"$REPO_ROOT/VERSION")"
git_commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf unknown)"
cat >"$backup_dir/manifest.env" <<EOF
BACKUP_FORMAT_VERSION=1
CREATED_AT=$timestamp
PLATFORM_VERSION=$platform_version
GIT_COMMIT=$git_commit
COMPOSE_PROJECT_NAME=$(env_value COMPOSE_PROJECT_NAME)
POSTGRES_DB=$postgres_db
MINIO_BUCKET=$minio_bucket
EOF

(
  cd "$backup_dir"
  sha256_file database.dump
  sha256_file objects.tar.gz
  sha256_file secrets.env
  sha256_file manifest.env
) >"$backup_dir/SHA256SUMS"
chmod 600 "$backup_dir"/*

resume_api
api_was_running=false

info "Backup complete: $backup_dir"
printf '%s\n' "$backup_dir"
