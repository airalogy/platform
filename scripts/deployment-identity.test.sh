#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT

metadata_dir="$TEST_DIR/image-metadata"
release_dir="$TEST_DIR/release"
mkdir -p "$metadata_dir" "$release_dir"

for component in api web protocol-executor postgres; do
  printf 'ghcr.io/airalogy/platform-%s\n' "$component" >"$metadata_dir/$component.repository"
  printf 'sha256:%064d\n' 1 >"$metadata_dir/$component.digest"
done

node "$SCRIPT_DIR/create-release-metadata.mjs" \
  --metadata-directory "$metadata_dir" \
  --output-directory "$release_dir" \
  --env-template "$REPO_ROOT/deploy/single-lab/.env.example" \
  --release-tag "v$(tr -d '\r\n' <"$REPO_ROOT/VERSION")" \
  --git-commit 1111111111111111111111111111111111111111 \
  --created-at 2026-01-01T00:00:00Z >/dev/null

metadata_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' \
    "$release_dir/release-manifest.env"
}

snapshot="$TEST_DIR/previous-release.env"
cat >"$snapshot" <<EOF
PLATFORM_VERSION=$(metadata_value AIRALOGY_RELEASE_PRODUCT_VERSION)
GIT_TAG=$(metadata_value AIRALOGY_RELEASE_TAG)
GIT_COMMIT=$(metadata_value AIRALOGY_RELEASE_COMMIT)
BUILD_TIME=2026-01-01T00:00:00.000Z
BUILD_DIRTY=false
AIRALOGY_API_IMAGE=$(metadata_value AIRALOGY_RELEASE_API_IMAGE)
AIRALOGY_WEB_IMAGE=$(metadata_value AIRALOGY_RELEASE_WEB_IMAGE)
AIRALOGY_PROTOCOL_EXECUTOR_IMAGE=$(metadata_value AIRALOGY_RELEASE_PROTOCOL_EXECUTOR_IMAGE)
AIRALOGY_POSTGRES_IMAGE=$(metadata_value AIRALOGY_RELEASE_POSTGRES_IMAGE)
EOF

test_env="$TEST_DIR/deployment.env"
cp "$release_dir/.env.example" "$test_env"
chmod 600 "$test_env"
export AIRALOGY_ENV_FILE="$test_env"
# shellcheck source=../deploy/single-lab/scripts/lib.sh
source "$REPO_ROOT/deploy/single-lab/scripts/lib.sh"

set_env_value PLATFORM_VERSION 9.9.9
set_env_value AIRALOGY_RELEASE_METADATA_REQUIRED false
activate_deployment_snapshot \
  "$snapshot" \
  "$release_dir/release-manifest.json" \
  "$release_dir/release-manifest.env"

[[ "$(env_value_from "$test_env" PLATFORM_VERSION)" == "$(tr -d '\r\n' <"$REPO_ROOT/VERSION")" ]]
[[ "$(env_value_from "$test_env" AIRALOGY_RELEASE_METADATA_REQUIRED)" == true ]]
[[ "$(env_value_from "$test_env" AIRALOGY_RELEASE_MANIFEST_FILE)" == "$release_dir/release-manifest.json" ]]
[[ "$(env_value_from "$test_env" AIRALOGY_API_IMAGE)" == "$(metadata_value AIRALOGY_RELEASE_API_IMAGE)" ]]

source_snapshot="$TEST_DIR/source-release.env"
cat >"$source_snapshot" <<'EOF'
PLATFORM_VERSION=0.1.0
GIT_TAG=
GIT_COMMIT=unknown
BUILD_TIME=2026-01-02T00:00:00Z
BUILD_DIRTY=true
AIRALOGY_API_IMAGE=airalogy-platform-api:0.1.0
AIRALOGY_WEB_IMAGE=airalogy-platform-web:0.1.0
AIRALOGY_PROTOCOL_EXECUTOR_IMAGE=airalogy-platform-protocol-executor:0.1.0
AIRALOGY_POSTGRES_IMAGE=airalogy-platform-postgres:0.1.0
EOF
activate_deployment_snapshot "$source_snapshot"
[[ "$(env_value_from "$test_env" AIRALOGY_RELEASE_METADATA_REQUIRED)" == false ]]
[[ -z "$(env_value_from "$test_env" AIRALOGY_RELEASE_MANIFEST_SHA256)" ]]
[[ -z "$(env_value_from "$test_env" GIT_TAG)" ]]
[[ "$(env_value_from "$test_env" BUILD_DIRTY)" == true ]]

printf 'Deployment identity snapshot tests passed.\n'
