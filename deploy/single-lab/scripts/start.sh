#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

"$SCRIPT_DIR/preflight.sh"
compose up -d --build --remove-orphans
wait_for_service api-server 600
wait_for_service web 300

site_url="$(env_value SITE_URL)"
info "Airalogy Lab is ready at $site_url"
info "First run: open $site_url/setup and enter INITIAL_ADMIN_TOKEN from $ENV_FILE"
