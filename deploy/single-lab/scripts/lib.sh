#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/../.." && pwd)"
COMPOSE_FILE="$DEPLOY_DIR/compose.yml"
ENV_FILE="${AIRALOGY_ENV_FILE:-$DEPLOY_DIR/.env}"

export AIRALOGY_ENV_FILE="$ENV_FILE"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '%s\n' "$*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

require_env_file() {
  [[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE; run scripts/generate-env.sh first"
}

env_value_from() {
  local file="$1"
  local key="$2"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); value=$0 } END { print value }' "$file"
}

env_value() {
  local key="$1"
  if printenv "$key" >/dev/null 2>&1; then
    printenv "$key"
  else
    env_value_from "$ENV_FILE" "$key"
  fi
}

compose() {
  docker compose \
    --project-directory "$DEPLOY_DIR" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    "$@"
}

absolute_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s/%s\n' "$DEPLOY_DIR" "${path#./}"
  fi
}

file_mode() {
  if stat -c '%a' "$1" >/dev/null 2>&1; then
    stat -c '%a' "$1"
  else
    stat -f '%Lp' "$1"
  fi
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1"
  else
    shasum -a 256 "$1"
  fi
}

verify_checksums() {
  local directory="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$directory" && sha256sum -c SHA256SUMS)
  else
    (cd "$directory" && shasum -a 256 -c SHA256SUMS)
  fi
}

deployment_state_dir() {
  local project safe_project digest env_file_identity
  project="$(env_value COMPOSE_PROJECT_NAME)"
  safe_project="${project//[^a-zA-Z0-9_.-]/_}"
  env_file_identity="$(cd "$(dirname "$ENV_FILE")" && pwd -P)/$(basename "$ENV_FILE")"
  if command -v sha256sum >/dev/null 2>&1; then
    digest="$(printf '%s' "$env_file_identity" | sha256sum | awk '{print $1}')"
  else
    digest="$(printf '%s' "$env_file_identity" | shasum -a 256 | awk '{print $1}')"
  fi
  printf '%s/state/%s-%s\n' "$DEPLOY_DIR" "$safe_project" "${digest:0:16}"
}

wait_for_service() {
  local service="$1"
  local timeout="${2:-180}"
  local started now container_id health status
  started="$(date +%s)"

  while true; do
    container_id="$(compose ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      if [[ "$health" == "healthy" || "$health" == "running" ]]; then
        return 0
      fi
      if [[ "$health" == "unhealthy" || "$health" == "exited" || "$health" == "dead" ]]; then
        compose logs --tail=100 "$service" >&2 || true
        info "error: $service entered state: $health"
        return 1
      fi
    fi

    now="$(date +%s)"
    if (( now - started >= timeout )); then
      compose logs --tail=100 "$service" >&2 || true
      info "error: timed out waiting for $service"
      return 1
    fi
    sleep 3
  done
}

minio_network() {
  local container_id
  container_id="$(compose ps -q minio)"
  [[ -n "$container_id" ]] || die "MinIO container is not running"
  docker inspect \
    --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' \
    "$container_id" | head -n 1
}

mc_image() {
  printf '%s\n' 'quay.io/minio/mc:RELEASE.2024-03-25T16-41-14Z'
}
