#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

build_db=false
pull=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-db)
      build_db=true
      shift
      ;;
    --no-pull)
      pull=false
      shift
      ;;
    -h|--help)
      echo "usage: upgrade.sh [--build-db] [--no-pull]"
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

"$SCRIPT_DIR/preflight.sh"
wait_for_service api-server 60
wait_for_service web 60

running_image_id() {
  local service="$1"
  local container_id
  container_id="$(compose ps -q "$service")"
  [[ -n "$container_id" ]] || return 1
  docker inspect --format '{{.Image}}' "$container_id"
}

current_api_image="$(running_image_id api-server)" || die "api-server must be running before upgrade"
current_web_image="$(running_image_id web)" || die "web must be running before upgrade"
current_db_image=""
if [[ "$build_db" == true ]]; then
  current_db_image="$(running_image_id db)" || die "db must be running before --build-db upgrade"
fi

backup_path="$("$SCRIPT_DIR/backup.sh" pre-upgrade)"
[[ "$backup_path" != *$'\n'* && -d "$backup_path" ]] || die "backup.sh did not return exactly one backup directory"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
state_dir="$(deployment_state_dir)"
state_file="$state_dir/last-upgrade.env"
mkdir -p "$state_dir"
chmod 700 "$state_dir"

previous_api="airalogy-platform-api:rollback-$timestamp"
previous_web="airalogy-platform-web:rollback-$timestamp"
previous_db=""
docker image tag "$current_api_image" "$previous_api"
docker image tag "$current_web_image" "$previous_web"
if [[ "$build_db" == true ]]; then
  previous_db="airalogy-platform-postgresql:rollback-$timestamp"
  docker image tag "$current_db_image" "$previous_db"
fi

cat >"$state_file" <<EOF
UPGRADE_STARTED_AT=$timestamp
BACKUP_PATH=$backup_path
PREVIOUS_API_IMAGE=$previous_api
PREVIOUS_WEB_IMAGE=$previous_web
PREVIOUS_DB_IMAGE=$previous_db
STATUS=building
EOF
chmod 600 "$state_file"

set_upgrade_status() {
  local status="$1"
  sed -i.bak "s/^STATUS=.*/STATUS=$status/" "$state_file"
  rm -f "$state_file.bak"
}

previous_containers_stopped=false
new_release_started=false

restart_previous_containers() {
  info "Restarting the pre-upgrade application containers..."
  compose start api-server web >/dev/null
  wait_for_service api-server 300
  wait_for_service web 180
}

restart_on_early_exit() {
  local exit_code="$?"
  trap - EXIT
  if [[ "$exit_code" -ne 0 && "$previous_containers_stopped" == true && "$new_release_started" == false ]]; then
    restart_previous_containers || info "Automatic restart failed. Run scripts/rollback.sh."
  fi
  exit "$exit_code"
}
trap restart_on_early_exit EXIT

recover_previous_release() {
  info "Restoring the pre-upgrade release and backup..."
  export AIRALOGY_API_IMAGE="$previous_api"
  export AIRALOGY_WEB_IMAGE="$previous_web"
  if [[ -n "$previous_db" ]]; then
    export AIRALOGY_POSTGRES_IMAGE="$previous_db"
  fi
  "$SCRIPT_DIR/restore.sh" "$backup_path" --yes
}

build_service() {
  local service="$1"
  local build_args=(build)
  if [[ "$pull" == true ]]; then
    build_args+=(--pull)
  fi
  build_args+=("$service")
  compose "${build_args[@]}"
}

info "Stopping API and Web during the memory-intensive image build..."
compose stop api-server web >/dev/null
previous_containers_stopped=true

build_failed=false
if [[ "$build_db" == true ]] && ! build_service db; then
  build_failed=true
fi
if [[ "$build_failed" == false ]] && ! build_service api-server; then
  build_failed=true
fi
if [[ "$build_failed" == false ]] && ! build_service web; then
  build_failed=true
fi

if [[ "$build_failed" == true ]]; then
  set_upgrade_status failed
  if restart_previous_containers; then
    previous_containers_stopped=false
    info "Upgrade build failed; the pre-upgrade containers were restarted."
  else
    info "Upgrade build and automatic restart failed. Run scripts/rollback.sh."
  fi
  exit 1
fi

set_upgrade_status starting
new_release_started=true
if ! compose up -d --remove-orphans; then
  set_upgrade_status failed
  if recover_previous_release; then
    info "Upgrade startup failed; the pre-upgrade release was restored."
  else
    info "Upgrade startup and automatic recovery failed. Run scripts/rollback.sh."
  fi
  exit 1
fi

if wait_for_service api-server 600 && wait_for_service web 300; then
  set_upgrade_status complete
  previous_containers_stopped=false
  trap - EXIT
  info "Upgrade complete. Rollback state: $state_file"
else
  set_upgrade_status failed
  if recover_previous_release; then
    info "Upgrade health check failed; the pre-upgrade release was restored."
  else
    info "Upgrade health check and automatic recovery failed. Run scripts/rollback.sh."
  fi
  exit 1
fi
