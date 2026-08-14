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

set_env_value() {
  local key="$1"
  local value="$2"
  local temporary_file="$ENV_FILE.tmp.$$"
  [[ "$key" =~ ^[A-Z0-9_]+$ ]] || die "invalid environment key: $key"
  [[ "$value" != *$'\n'* ]] || die "$key must not contain newlines"

  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 {
      if (!replaced) {
        print key "=" value
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) {
        print key "=" value
      }
    }
  ' "$ENV_FILE" >"$temporary_file"
  chmod 600 "$temporary_file"
  mv "$temporary_file" "$ENV_FILE"
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

sha256_text() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  else
    shasum -a 256 | awk '{print $1}'
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
  local configured
  configured="$(env_value AIRALOGY_STATE_DIR)"
  if [[ -n "$configured" ]]; then
    absolute_path "$configured"
    return
  fi

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

release_metadata_required() {
  [[ "$(env_value AIRALOGY_RELEASE_METADATA_REQUIRED)" == "true" ]]
}

release_manifest_file() {
  absolute_path "$(env_value AIRALOGY_RELEASE_MANIFEST_FILE)"
}

release_metadata_file() {
  absolute_path "$(env_value AIRALOGY_RELEASE_METADATA_FILE)"
}

release_value() {
  env_value_from "$(release_metadata_file)" "$1"
}

archived_release_metadata_for_checksum() {
  local expected_checksum="$1"
  local state_dir
  [[ -n "$expected_checksum" ]] || return 0
  state_dir="$(deployment_state_dir)"
  [[ -d "$state_dir/releases" ]] || return 0
  local file
  while IFS= read -r file; do
    if [[ "$(env_value_from "$file" AIRALOGY_RELEASE_MANIFEST_SHA256)" == "$expected_checksum" ]]; then
      printf '%s\n' "$file"
      return 0
    fi
  done < <(find "$state_dir/releases" -type f -name '*.env' 2>/dev/null | sort -r)
}

activate_deployment_snapshot() {
  local snapshot_file="$1"
  local archived_manifest="${2:-}"
  local archived_metadata="${3:-}"
  [[ -f "$snapshot_file" ]] || die "previous deployment snapshot is unavailable: $snapshot_file"

  local key value
  for key in \
    PLATFORM_VERSION GIT_COMMIT \
    AIRALOGY_API_IMAGE AIRALOGY_WEB_IMAGE AIRALOGY_PROTOCOL_EXECUTOR_IMAGE \
    AIRALOGY_POSTGRES_IMAGE; do
    value="$(env_value_from "$snapshot_file" "$key")"
    [[ -n "$value" ]] || die "previous deployment snapshot is missing $key"
    set_env_value "$key" "$value"
    export "$key=$value"
  done
  value="$(env_value_from "$snapshot_file" GIT_TAG)"
  set_env_value GIT_TAG "$value"
  export GIT_TAG="$value"
  value="$(env_value_from "$snapshot_file" BUILD_TIME)"
  set_env_value BUILD_TIME "$value"
  export BUILD_TIME="$value"
  value="$(env_value_from "$snapshot_file" BUILD_DIRTY)"
  value="${value:-true}"
  set_env_value BUILD_DIRTY "$value"
  export BUILD_DIRTY="$value"

  if [[ -n "$archived_manifest" || -n "$archived_metadata" ]]; then
    [[ -f "$archived_manifest" && -f "$archived_metadata" ]] || \
      die "previous release manifest archive is incomplete"
    local manifest_checksum expected_checksum
    manifest_checksum="$(sha256_file "$archived_manifest" | awk '{print $1}')"
    expected_checksum="$(env_value_from "$archived_metadata" AIRALOGY_RELEASE_MANIFEST_SHA256)"
    [[ "$manifest_checksum" == "$expected_checksum" ]] || \
      die "previous release manifest archive checksum mismatch"
    set_env_value AIRALOGY_RELEASE_METADATA_REQUIRED true
    set_env_value AIRALOGY_RELEASE_MANIFEST_FILE "$archived_manifest"
    set_env_value AIRALOGY_RELEASE_METADATA_FILE "$archived_metadata"
    set_env_value AIRALOGY_RELEASE_MANIFEST_SHA256 "$manifest_checksum"
    export AIRALOGY_RELEASE_METADATA_REQUIRED=true
    export AIRALOGY_RELEASE_MANIFEST_FILE="$archived_manifest"
    export AIRALOGY_RELEASE_METADATA_FILE="$archived_metadata"
    export AIRALOGY_RELEASE_MANIFEST_SHA256="$manifest_checksum"
    verify_release_metadata
  else
    set_env_value AIRALOGY_RELEASE_METADATA_REQUIRED false
    set_env_value AIRALOGY_RELEASE_MANIFEST_SHA256 ""
    export AIRALOGY_RELEASE_METADATA_REQUIRED=false
    export AIRALOGY_RELEASE_MANIFEST_SHA256=""
  fi
}

configuration_revision() {
  local key
  for key in \
    PLATFORM_VERSION DEPLOYMENT_MODE LAB_STRUCTURE_MODE SIGNUP_MODE \
    SITE_URL SINGLE_LAB_UID SINGLE_LAB_DEFAULT_PROJECT_UID STORAGE_BACKEND \
    RECORD_DELETE_GRACE_DAYS MAX_LABS_PER_USER MASTERBRAIN_CALL_MODE \
    CHAT_MODEL_FAST CHAT_MODEL_ACCURATE CHAT_MODEL_DEEP \
    AIRALOGY_API_IMAGE AIRALOGY_WEB_IMAGE AIRALOGY_PROTOCOL_EXECUTOR_IMAGE \
    AIRALOGY_POSTGRES_IMAGE AIRALOGY_ENGINE_IMAGE REDIS_IMAGE MINIO_IMAGE MINIO_MC_IMAGE; do
    printf '%s=%s\n' "$key" "$(env_value "$key")"
  done | sha256_text
}

verify_release_image_reference() {
  local configured_key="$1"
  local release_key="$2"
  local configured expected
  configured="$(env_value "$configured_key")"
  expected="$(release_value "$release_key")"
  [[ -n "$configured" && "$configured" == "$expected" ]] || \
    die "$configured_key does not match the immutable release manifest"
  [[ "$configured" =~ @sha256:[0-9a-f]{64}$ ]] || \
    die "$configured_key must be pinned by sha256 digest"
}

verify_release_metadata() {
  release_metadata_required || return 0

  local manifest_file metadata_file expected_digest actual_digest version tag commit revision
  manifest_file="$(release_manifest_file)"
  metadata_file="$(release_metadata_file)"
  [[ -f "$manifest_file" ]] || die "missing release manifest: $manifest_file"
  [[ -f "$metadata_file" ]] || die "missing release metadata: $metadata_file"

  expected_digest="$(release_value AIRALOGY_RELEASE_MANIFEST_SHA256)"
  [[ "$expected_digest" =~ ^[0-9a-f]{64}$ ]] || die "release manifest checksum is invalid"
  actual_digest="$(sha256_file "$manifest_file" | awk '{print $1}')"
  [[ "$actual_digest" == "$expected_digest" ]] || die "release manifest checksum mismatch"
  [[ "$(env_value AIRALOGY_RELEASE_MANIFEST_SHA256)" == "$expected_digest" ]] || \
    die "deployment configuration does not match the release manifest checksum"

  version="$(release_value AIRALOGY_RELEASE_PRODUCT_VERSION)"
  tag="$(release_value AIRALOGY_RELEASE_TAG)"
  commit="$(release_value AIRALOGY_RELEASE_COMMIT)"
  revision="$(release_value AIRALOGY_RELEASE_DATABASE_REVISION)"
  [[ "$(env_value PLATFORM_VERSION)" == "$version" ]] || die "PLATFORM_VERSION does not match release metadata"
  [[ "$tag" == "v$version" ]] || die "release tag does not match product version"
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || die "release commit is invalid"
  grep -Fq "\"product_version\": \"$version\"" "$manifest_file" || die "release JSON and environment metadata disagree"
  grep -Fq "\"git_commit\": \"$commit\"" "$manifest_file" || die "release JSON and environment metadata disagree"
  grep -Fq "\"revision\": \"$revision\"" "$manifest_file" || die "release database revision metadata disagree"
  local digest_key release_digest
  for digest_key in \
    AIRALOGY_RELEASE_API_DIGEST AIRALOGY_RELEASE_WEB_DIGEST \
    AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_DIGEST AIRALOGY_RELEASE_POSTGRES_DIGEST; do
    release_digest="$(release_value "$digest_key")"
    grep -Fq "\"digest\": \"$release_digest\"" "$manifest_file" || \
      die "release JSON and environment metadata disagree on $digest_key"
  done

  verify_release_image_reference AIRALOGY_API_IMAGE AIRALOGY_RELEASE_API_IMAGE
  verify_release_image_reference AIRALOGY_WEB_IMAGE AIRALOGY_RELEASE_WEB_IMAGE
  verify_release_image_reference AIRALOGY_PROTOCOL_EXECUTOR_IMAGE AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_IMAGE
  verify_release_image_reference AIRALOGY_POSTGRES_IMAGE AIRALOGY_RELEASE_POSTGRES_IMAGE
}

pull_release_images() {
  local key image
  for key in \
    AIRALOGY_API_IMAGE AIRALOGY_WEB_IMAGE AIRALOGY_PROTOCOL_EXECUTOR_IMAGE \
    AIRALOGY_POSTGRES_IMAGE; do
    image="$(env_value "$key")"
    docker pull "$image"
  done
}

verify_image_identity() {
  local image="$1"
  local component="$2"
  local expected_version expected_commit actual_version actual_commit
  expected_version="$(release_value AIRALOGY_RELEASE_PRODUCT_VERSION)"
  expected_commit="$(release_value AIRALOGY_RELEASE_COMMIT)"
  actual_version="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image")"
  actual_commit="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")"
  [[ "$actual_version" == "$expected_version" ]] || die "$component image version is $actual_version; expected $expected_version"
  [[ "$actual_commit" == "$expected_commit" ]] || die "$component image commit is $actual_commit; expected $expected_commit"
}

verify_release_images() {
  release_metadata_required || return 0
  verify_image_identity "$(env_value AIRALOGY_API_IMAGE)" "API"
  verify_image_identity "$(env_value AIRALOGY_WEB_IMAGE)" "Web"
  verify_image_identity "$(env_value AIRALOGY_PROTOCOL_EXECUTOR_IMAGE)" "Protocol executor"
  verify_image_identity "$(env_value AIRALOGY_POSTGRES_IMAGE)" "PostgreSQL"
}

running_version_payload() {
  compose exec -T api-server python3 -c \
    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4000/system/version', timeout=5).read().decode())"
}

json_string_field() {
  local field="$1"
  sed -n "s/.*\"$field\":\"\([^\"]*\)\".*/\1/p"
}

verify_running_release() {
  release_metadata_required || return 0
  local payload actual_version actual_tag actual_commit actual_revision
  payload="$(running_version_payload)"
  actual_version="$(printf '%s\n' "$payload" | json_string_field version)"
  actual_tag="$(printf '%s\n' "$payload" | json_string_field tag)"
  actual_commit="$(printf '%s\n' "$payload" | json_string_field commit)"
  actual_revision="$(printf '%s\n' "$payload" | json_string_field database_revision)"
  [[ "$actual_version" == "$(release_value AIRALOGY_RELEASE_PRODUCT_VERSION)" ]] || die "running API version does not match release metadata"
  [[ "$actual_tag" == "$(release_value AIRALOGY_RELEASE_TAG)" ]] || die "running API tag does not match release metadata"
  [[ "$actual_commit" == "$(release_value AIRALOGY_RELEASE_COMMIT)" ]] || die "running API commit does not match release metadata"
  [[ "$actual_revision" == "$(release_value AIRALOGY_RELEASE_DATABASE_REVISION)" ]] || die "running database revision does not match release metadata"
  info "Running Airalogy Platform release verified: $actual_version ($actual_commit)."
}

write_deployment_state() {
  local action="$1"
  local status="${2:-succeeded}"
  local state_dir current_file event_id payload payload_version manifest_checksum
  state_dir="$(deployment_state_dir)"
  current_file="$state_dir/current-release.env"
  event_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-$action"
  mkdir -p "$state_dir/events" "$state_dir/releases"
  chmod 700 "$state_dir"

  payload="$(running_version_payload 2>/dev/null || true)"
  payload_version="$(printf '%s\n' "$payload" | json_string_field version)"
  manifest_checksum=""
  if release_metadata_required && [[ "$payload_version" == "$(release_value AIRALOGY_RELEASE_PRODUCT_VERSION)" ]]; then
    manifest_checksum="$(env_value AIRALOGY_RELEASE_MANIFEST_SHA256)"
  fi
  {
    printf 'AIRALOGY_DEPLOYMENT_ACTION=%s\n' "$action"
    printf 'AIRALOGY_DEPLOYMENT_STATUS=%s\n' "$status"
    printf 'AIRALOGY_DEPLOYED_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'AIRALOGY_DEPLOYMENT_ID=%s\n' "$(env_value AIRALOGY_DEPLOYMENT_ID)"
    printf 'PLATFORM_VERSION=%s\n' "$payload_version"
    printf 'GIT_TAG=%s\n' "$(printf '%s\n' "$payload" | json_string_field tag)"
    printf 'GIT_COMMIT=%s\n' "$(printf '%s\n' "$payload" | json_string_field commit)"
    printf 'BUILD_TIME=%s\n' "$(printf '%s\n' "$payload" | json_string_field build_time)"
    printf 'BUILD_DIRTY=%s\n' "$(printf '%s\n' "$payload" | sed -n 's/.*"dirty":\([^,}]*\).*/\1/p')"
    printf 'DATABASE_REVISION=%s\n' "$(printf '%s\n' "$payload" | json_string_field database_revision)"
    printf 'CONFIGURATION_REVISION=%s\n' "$(configuration_revision)"
    printf 'AIRALOGY_API_IMAGE=%s\n' "$(env_value AIRALOGY_API_IMAGE)"
    printf 'AIRALOGY_WEB_IMAGE=%s\n' "$(env_value AIRALOGY_WEB_IMAGE)"
    printf 'AIRALOGY_PROTOCOL_EXECUTOR_IMAGE=%s\n' "$(env_value AIRALOGY_PROTOCOL_EXECUTOR_IMAGE)"
    printf 'AIRALOGY_POSTGRES_IMAGE=%s\n' "$(env_value AIRALOGY_POSTGRES_IMAGE)"
    printf 'AIRALOGY_RELEASE_MANIFEST_SHA256=%s\n' "$manifest_checksum"
  } >"$current_file"
  chmod 600 "$current_file"
  cp "$current_file" "$state_dir/events/$event_id.env"

  if [[ -n "$manifest_checksum" ]]; then
    cp "$(release_manifest_file)" "$state_dir/releases/$event_id.json"
    cp "$(release_metadata_file)" "$state_dir/releases/$event_id.env"
  fi
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
  env_value MINIO_MC_IMAGE
}
