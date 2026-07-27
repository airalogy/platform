#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
runtime_dir="$repository_root/tests/e2e/.runtime"
mkdir -p "$runtime_dir/protocols"

export APP_ENV=development
export DEPLOYMENT_MODE=community
export LAB_STRUCTURE_MODE=structured
export SIGNUP_MODE=open
export SITE_URL=http://127.0.0.1:3100
export DATABASE_URL=postgresql+asyncpg://airalogy_e2e:airalogy_e2e@127.0.0.1:55432/airalogy_e2e
export REDIS_URL=redis://127.0.0.1:56379/0
export STORAGE_BACKEND=minio
export MINIO_ENDPOINT=127.0.0.1:59200
export MINIO_BUCKET=airalogy-e2e
export MINIO_ACCESS_KEY=airalogy_e2e
export MINIO_SECRET_KEY=airalogy-e2e-password
export SECRET_KEY=airalogy-e2e-secret-key
export AES_KEY=0000000000000000000000000000000000000000000000000000000000000000
export INNER_API_KEY=airalogy-e2e-inner-key
export AIRALOGY_ENDPOINT=http://127.0.0.1:4100
export PROTOCOL_DIR="$runtime_dir/protocols"
export LOG_FILE="$runtime_dir/api.log"
export LOG_REQUEST_BODIES=false

cd "$repository_root"
uv --directory apps/api run --no-sync python -m alembic upgrade head
exec uv --directory apps/api run --no-sync python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 4100
