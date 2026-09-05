#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$repository_root/tests/e2e/scripts/api-env.sh"

cd "$repository_root"
uv --directory apps/api run --no-sync python -m alembic upgrade head
exec uv --directory apps/api run --no-sync python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 4100
