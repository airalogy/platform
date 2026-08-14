#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_env_file
info "Deployment ID: $(env_value AIRALOGY_DEPLOYMENT_ID)"
compose ps

if [[ -n "$(compose ps -q api-server)" ]]; then
  verify_running_release
  running_version_payload
  printf '\n'
else
  info "API is not running."
fi

current_state="$(deployment_state_dir)/current-release.env"
if [[ -f "$current_state" ]]; then
  info "Recorded release state: $current_state"
fi
