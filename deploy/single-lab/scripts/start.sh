#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

"$SCRIPT_DIR/preflight.sh"
if release_metadata_required; then
  pull_release_images
  verify_release_images
  compose up -d --remove-orphans
else
  compose build protocol-executor-image
  compose up -d --build --remove-orphans
fi
wait_for_service api-server 600
wait_for_service web 300
verify_running_release
write_deployment_state install

site_url="$(env_value SITE_URL)"
info "Airalogy Lab is ready at $site_url"
info "First run: open $site_url/setup and enter INITIAL_ADMIN_TOKEN from $ENV_FILE"
