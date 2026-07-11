#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

backup_dir=""
assume_yes=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      assume_yes=true
      shift
      ;;
    -h|--help)
      echo "usage: restore.sh BACKUP_DIRECTORY [--yes]"
      exit 0
      ;;
    *)
      [[ -z "$backup_dir" ]] || die "only one backup directory may be supplied"
      backup_dir="$1"
      shift
      ;;
  esac
done

[[ -n "$backup_dir" ]] || die "usage: restore.sh BACKUP_DIRECTORY [--yes]"
backup_dir="$(cd "$backup_dir" 2>/dev/null && pwd)" || die "backup directory not found"
for file in database.dump objects.tar.gz secrets.env manifest.env SHA256SUMS; do
  [[ -f "$backup_dir/$file" ]] || die "backup is missing $file"
done

require_command docker
require_command tar
require_env_file
verify_checksums "$backup_dir"
[[ "$(env_value_from "$backup_dir/manifest.env" BACKUP_FORMAT_VERSION)" == "1" ]] || die "unsupported backup format"

backup_aes_key="$(env_value_from "$backup_dir/secrets.env" AES_KEY)"
[[ "$backup_aes_key" == "$(env_value AES_KEY)" ]] || die "AES_KEY differs from the backup; restore its secrets.env as the deployment .env before restoring data"

if [[ "$assume_yes" != true ]]; then
  printf 'This replaces the current PostgreSQL database and MinIO bucket. Type RESTORE to continue: ' >&2
  read -r confirmation
  [[ "$confirmation" == "RESTORE" ]] || die "restore cancelled"
fi

postgres_user="$(env_value POSTGRES_USER)"
postgres_db="$(env_value POSTGRES_DB)"
minio_user="$(env_value MINIO_ROOT_USER)"
minio_password="$(env_value MINIO_ROOT_PASSWORD)"
minio_bucket="$(env_value MINIO_BUCKET)"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$work_dir/objects"
tar -C "$work_dir/objects" -xzf "$backup_dir/objects.tar.gz"

compose stop api-server web >/dev/null 2>&1 || true
compose up -d db minio redis
wait_for_service db 120
wait_for_service minio 120

info "Restoring PostgreSQL..."
compose exec -T db dropdb \
  --username "$postgres_user" \
  --if-exists \
  --force \
  "$postgres_db"
compose exec -T db createdb --username "$postgres_user" "$postgres_db"
compose exec -T db pg_restore \
  --username "$postgres_user" \
  --dbname "$postgres_db" \
  --no-owner \
  --no-acl \
  --exit-on-error <"$backup_dir/database.dump"

info "Restoring object storage..."
network="$(minio_network)"
docker run --rm \
  --network "$network" \
  --volume "$work_dir/objects:/restore:ro" \
  --env "MINIO_ROOT_USER=$minio_user" \
  --env "MINIO_ROOT_PASSWORD=$minio_password" \
  --env "MINIO_BUCKET=$minio_bucket" \
  --entrypoint /bin/sh \
  "$(mc_image)" \
  -c 'mc alias set target http://minio:9200 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mb --ignore-existing target/"$MINIO_BUCKET" >/dev/null && mc rm --recursive --force target/"$MINIO_BUCKET" >/dev/null 2>&1 || true; mc mirror --overwrite --remove /restore target/"$MINIO_BUCKET"'

compose up -d api-server web
wait_for_service api-server 300
wait_for_service web 180
info "Restore complete from $backup_dir"
