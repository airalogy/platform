#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

assume_yes=false
if [[ "${1:-}" == "--yes" ]]; then
  assume_yes=true
elif [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "usage: rollback.sh [--yes]"
  exit 0
elif [[ $# -gt 0 ]]; then
  die "usage: rollback.sh [--yes]"
fi

require_env_file
state_file="$(deployment_state_dir)/last-upgrade.env"
[[ -f "$state_file" ]] || die "no upgrade state found at $state_file"

backup_path="$(env_value_from "$state_file" BACKUP_PATH)"
previous_api="$(env_value_from "$state_file" PREVIOUS_API_IMAGE)"
previous_web="$(env_value_from "$state_file" PREVIOUS_WEB_IMAGE)"
previous_db="$(env_value_from "$state_file" PREVIOUS_DB_IMAGE)"
previous_snapshot="$(env_value_from "$state_file" PREVIOUS_DEPLOYMENT_SNAPSHOT)"
previous_release_manifest="$(env_value_from "$state_file" PREVIOUS_RELEASE_MANIFEST)"
previous_release_metadata="$(env_value_from "$state_file" PREVIOUS_RELEASE_METADATA)"
[[ -n "$backup_path" && -d "$backup_path" ]] || die "rollback backup is unavailable"
[[ -n "$previous_api" && -n "$previous_web" ]] || die "previous application images are unavailable"
[[ -n "$previous_snapshot" && -f "$previous_snapshot" ]] || die "previous deployment identity is unavailable"
docker image inspect "$previous_api" >/dev/null 2>&1 || die "missing image $previous_api"
docker image inspect "$previous_web" >/dev/null 2>&1 || die "missing image $previous_web"

if [[ "$assume_yes" != true ]]; then
  printf 'Rollback restores the pre-upgrade database and objects. Type ROLLBACK to continue: ' >&2
  read -r confirmation
  [[ "$confirmation" == "ROLLBACK" ]] || die "rollback cancelled"
fi

export AIRALOGY_API_IMAGE="$previous_api"
export AIRALOGY_WEB_IMAGE="$previous_web"
if [[ -n "$previous_db" ]]; then
  docker image inspect "$previous_db" >/dev/null 2>&1 || die "missing image $previous_db"
  export AIRALOGY_POSTGRES_IMAGE="$previous_db"
fi
export AIRALOGY_PROTOCOL_EXECUTOR_IMAGE="$(env_value_from "$previous_snapshot" AIRALOGY_PROTOCOL_EXECUTOR_IMAGE)"
"$SCRIPT_DIR/restore.sh" "$backup_path" --yes
activate_deployment_snapshot "$previous_snapshot" "$previous_release_manifest" "$previous_release_metadata"
verify_running_release
sed -i.bak 's/^STATUS=.*/STATUS=rolled_back/' "$state_file"
rm -f "$state_file.bak"
write_deployment_state rollback
info "Rollback complete."
