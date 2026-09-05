#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/api-env.sh"
cd "$repository_root"
compose_file="$repository_root/tests/e2e/compose.yml"
# Dedicated disposable infrastructure only; never normal development volumes.
cleanup() {
  if [[ "${E2E_KEEP_INFRA:-0}" != "1" ]]; then
    docker compose -p airalogy-platform-e2e -f "$compose_file" down --volumes --remove-orphans
  fi
}
trap cleanup EXIT
docker compose -p airalogy-platform-e2e -f "$compose_file" up --build --detach --wait db redis minio
docker compose -p airalogy-platform-e2e -f "$compose_file" run --rm createbuckets
uv --directory apps/api run --no-sync python -m alembic upgrade head
export RESEARCH_INTEGRATION_TEST=1 RESOURCE_TEST_DATABASE_URL="$DATABASE_URL" AI_ENABLED=false
uv --directory apps/api run --with pytest python -m pytest tests/test_research_integration.py tests/test_resource_postgres.py "$@"
