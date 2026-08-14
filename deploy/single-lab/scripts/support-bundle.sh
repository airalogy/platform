#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_env_file
require_command tar

state_dir="$(deployment_state_dir)"
deployment_id="$(env_value AIRALOGY_DEPLOYMENT_ID)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="$state_dir/support"
output_path="${1:-$output_dir/airalogy-platform-support-$deployment_id-$timestamp.tar.gz}"
temporary_dir="$(mktemp -d)"
bundle_dir="$temporary_dir/airalogy-platform-support"

cleanup() {
  rm -rf "$temporary_dir"
}
trap cleanup EXIT

mkdir -p "$bundle_dir" "$output_dir"
chmod 700 "$output_dir"

cat >"$bundle_dir/README.txt" <<'EOF'
This support bundle contains release identity and service health only.
It intentionally excludes .env files, secrets, logs, database contents,
research records, attachments, user identities, and customer names.
EOF

if [[ -n "$(compose ps -q api-server)" ]]; then
  running_version_payload >"$bundle_dir/runtime-version.json" 2>/dev/null || true
fi

for service in web api-server db redis minio; do
  container_id="$(compose ps -q "$service")"
  if [[ -n "$container_id" ]]; then
    docker inspect --format \
      '{"service":"'"$service"'","image_id":"{{.Image}}","product_version":"{{index .Config.Labels "org.opencontainers.image.version"}}","source_revision":"{{index .Config.Labels "org.opencontainers.image.revision"}}","state":"{{.State.Status}}","health":"{{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}"}' \
      "$container_id" >>"$bundle_dir/services.jsonl"
  fi
done

current_state="$state_dir/current-release.env"
if [[ -f "$current_state" ]]; then
  grep -E '^(AIRALOGY_DEPLOYMENT_(ACTION|STATUS|ID)|AIRALOGY_DEPLOYED_AT|PLATFORM_VERSION|GIT_(TAG|COMMIT)|DATABASE_REVISION|CONFIGURATION_REVISION|AIRALOGY_RELEASE_MANIFEST_SHA256)=' \
    "$current_state" >"$bundle_dir/deployment-state.env" || true
fi

latest_upgrade=""
if [[ -d "$state_dir/upgrades" ]]; then
  latest_upgrade="$(find "$state_dir/upgrades" -type f -name '*.env' | sort | tail -n 1)"
fi
if [[ -n "$latest_upgrade" ]]; then
  grep -E '^(UPGRADE_STARTED_AT|STATUS|TARGET_VERSION|TARGET_COMMIT|TARGET_RELEASE_MANIFEST_SHA256)=' \
    "$latest_upgrade" >"$bundle_dir/latest-upgrade.env" || true
fi

if release_metadata_required; then
  grep -E '^AIRALOGY_RELEASE_(SCHEMA_VERSION|MANIFEST_SHA256|PRODUCT_VERSION|TAG|COMMIT|DATABASE_REVISION|(API|WEB|PROTOCOL_EXECUTOR|POSTGRES)_DIGEST)=' \
    "$(release_metadata_file)" >"$bundle_dir/release-identity.env"
fi

mkdir -p "$(dirname "$output_path")"
tar -czf "$output_path" -C "$temporary_dir" airalogy-platform-support
chmod 600 "$output_path"
printf '%s\n' "$output_path"
