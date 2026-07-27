#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
compose_file="$repository_root/tests/e2e/compose.yml"
compose_project="airalogy-platform-e2e"
local_no_proxy="127.0.0.1,localhost,::1"

export NO_PROXY="${NO_PROXY:+$NO_PROXY,}$local_no_proxy"
export no_proxy="${no_proxy:+$no_proxy,}$local_no_proxy"

cleanup() {
  if [[ "${E2E_KEEP_INFRA:-0}" != "1" ]]; then
    docker compose -p "$compose_project" -f "$compose_file" down --volumes --remove-orphans
  fi
}
trap cleanup EXIT INT TERM

cd "$repository_root"
mkdir -p tests/e2e/.auth tests/e2e/.runtime tests/e2e/.state
docker compose -p "$compose_project" -f "$compose_file" up --build --detach --wait db redis minio
docker compose -p "$compose_project" -f "$compose_file" run --rm createbuckets
corepack pnpm exec playwright test "$@"
