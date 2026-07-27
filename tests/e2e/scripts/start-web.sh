#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

export CI=1
export VITE_SERVICE_ENV=dev
export VITE_HTTP_PROXY=Y
export VITE_API_BASE_URL=http://127.0.0.1:4100
export VITE_GA_ID=

cd "$repository_root"
exec corepack pnpm --filter @airalogy/web exec vite \
  --host 127.0.0.1 \
  --port 3100 \
  --strictPort
