#!/usr/bin/env bash
# Shared isolated runtime for browser and research API integration tests.
repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
runtime_dir="$repository_root/tests/e2e/.runtime"
mkdir -p "$runtime_dir/protocols"
export APP_ENV=development DEPLOYMENT_MODE=community LAB_STRUCTURE_MODE=structured SIGNUP_MODE=open
export SITE_URL=http://127.0.0.1:3100
export DATABASE_URL=postgresql+asyncpg://airalogy_e2e:airalogy_e2e@127.0.0.1:55432/airalogy_e2e
export REDIS_URL=redis://127.0.0.1:56379/0
export STORAGE_BACKEND=minio MINIO_ENDPOINT=127.0.0.1:59200 MINIO_BUCKET=airalogy-e2e
export MINIO_ACCESS_KEY=airalogy_e2e MINIO_SECRET_KEY=airalogy-e2e-password
export SECRET_KEY=airalogy-e2e-secret-key
export AES_KEY=0000000000000000000000000000000000000000000000000000000000000000
export INNER_API_KEY=airalogy-e2e-inner-key AIRALOGY_ENDPOINT=http://127.0.0.1:4100
export MASTERBRAIN_CALL_MODE=external CHAT_API_ENDPOINT=http://127.0.0.1:41999
export PROTOCOL_DIR="$runtime_dir/protocols" LOG_FILE="$runtime_dir/api.log" LOG_REQUEST_BODIES=false
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,::1"
export no_proxy="$NO_PROXY"
