#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

config_only=false
if [[ "${1:-}" == "--config-only" ]]; then
  config_only=true
elif [[ $# -gt 0 ]]; then
  die "usage: preflight.sh [--config-only]"
fi

require_command docker
require_env_file

required=(
  COMPOSE_PROJECT_NAME SITE_URL SITE_ADDRESS TLS_EMAIL BACKUP_DIR
  AIRALOGY_API_IMAGE AIRALOGY_WEB_IMAGE SECRET_KEY AES_KEY INNER_API_KEY
  INITIAL_ADMIN_TOKEN POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
  MINIO_ROOT_USER MINIO_ROOT_PASSWORD MINIO_BUCKET
)
for key in "${required[@]}"; do
  [[ -n "$(env_value "$key")" ]] || die "$key is required in $ENV_FILE"
done

for key in SECRET_KEY AES_KEY INNER_API_KEY INITIAL_ADMIN_TOKEN POSTGRES_PASSWORD MINIO_ROOT_PASSWORD; do
  value="$(env_value "$key")"
  [[ "$value" != *replace-with* && "$value" != change-me-* ]] || die "$key still uses a placeholder"
done

[[ "$(env_value DEPLOYMENT_MODE)" == "single_lab" ]] || die "DEPLOYMENT_MODE must be single_lab"
[[ "$(env_value APP_ENV)" == "production" ]] || die "APP_ENV must be production"
[[ "$(env_value SECRET_KEY)" =~ ^.{32,}$ ]] || die "SECRET_KEY must contain at least 32 characters"
[[ "$(env_value INNER_API_KEY)" =~ ^.{32,}$ ]] || die "INNER_API_KEY must contain at least 32 characters"
[[ "$(env_value INITIAL_ADMIN_TOKEN)" =~ ^.{32,}$ ]] || die "INITIAL_ADMIN_TOKEN must contain at least 32 characters"
[[ "$(env_value AES_KEY)" =~ ^[0-9a-fA-F]{64}$ ]] || die "AES_KEY must be 64 hexadecimal characters"
[[ ! "$(env_value AES_KEY)" =~ ^0+$ ]] || die "AES_KEY must not be all zeros"
[[ "$(env_value POSTGRES_USER)" =~ ^[a-zA-Z][a-zA-Z0-9_]*$ ]] || die "POSTGRES_USER contains unsupported characters"
[[ "$(env_value POSTGRES_DB)" =~ ^[a-zA-Z][a-zA-Z0-9_]*$ ]] || die "POSTGRES_DB contains unsupported characters"
[[ "$(env_value MINIO_BUCKET)" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || die "MINIO_BUCKET is invalid"
[[ "$(env_value SITE_URL)" =~ ^https?://[^/]+/?$ ]] || die "SITE_URL must be an HTTP(S) origin without a path"
component_build_memory_mb="$(env_value COMPONENT_BUILD_MEMORY_MB)"
component_build_memory_mb="${component_build_memory_mb:-3072}"
[[ "$component_build_memory_mb" =~ ^[0-9]+$ ]] || die "COMPONENT_BUILD_MEMORY_MB must be an integer"
(( component_build_memory_mb >= 3072 )) || die "COMPONENT_BUILD_MEMORY_MB must be at least 3072"

web_build_memory_mb="$(env_value WEB_BUILD_MEMORY_MB)"
web_build_memory_mb="${web_build_memory_mb:-4096}"
[[ "$web_build_memory_mb" =~ ^[0-9]+$ ]] || die "WEB_BUILD_MEMORY_MB must be an integer"
(( web_build_memory_mb >= 4096 )) || die "WEB_BUILD_MEMORY_MB must be at least 4096"

mode="$(file_mode "$ENV_FILE")"
if (( 8#$mode & 077 )); then
  die "$ENV_FILE permissions are too broad ($mode); run chmod 600 '$ENV_FILE'"
fi

compose config --quiet

if [[ "$config_only" != true ]]; then
  docker info >/dev/null 2>&1 || die "Docker daemon is not available"
fi

info "Preflight checks passed."
