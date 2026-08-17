#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/../.." && pwd)"
ENV_FILE="${AIRALOGY_ENV_FILE:-$DEPLOY_DIR/.env}"

site_url="http://localhost:8080"
lab_name="Airalogy Lab"
lab_uid="main"
tls_email=""
force=false

usage() {
  cat <<'EOF'
Usage: generate-env.sh [options]

Options:
  --site-url URL    Public URL, for example https://lab.example.org
  --lab-name NAME   Display name of the single laboratory
  --lab-uid UID     Stable lowercase route identifier (default: main)
  --tls-email EMAIL ACME account email for automatic TLS
  --force           Replace an existing .env file
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site-url)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      site_url="$2"
      shift 2
      ;;
    --lab-name)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      lab_name="$2"
      shift 2
      ;;
    --lab-uid)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      lab_uid="$2"
      shift 2
      ;;
    --tls-email)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      tls_email="$2"
      shift 2
      ;;
    --force)
      force=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

command -v openssl >/dev/null 2>&1 || { echo "openssl is required" >&2; exit 1; }
[[ "$lab_uid" =~ ^[a-z][a-z0-9_]{2,31}$ ]] || { echo "invalid --lab-uid" >&2; exit 1; }
[[ "$site_url" =~ ^https?://[^/]+/?$ ]] || { echo "--site-url must be an HTTP(S) origin without a path" >&2; exit 1; }
[[ "$lab_name" != *$'\n'* && "$tls_email" != *$'\n'* ]] || { echo "values must not contain newlines" >&2; exit 1; }

if [[ -e "$ENV_FILE" && "$force" != true ]]; then
  echo "$ENV_FILE already exists; use --force to replace it" >&2
  exit 1
fi

if [[ "$site_url" == https://* ]]; then
  [[ -n "$tls_email" ]] || { echo "--tls-email is required for HTTPS deployments" >&2; exit 1; }
  site_address="${site_url#https://}"
  site_address="${site_address%/}"
  [[ "$site_address" != *:* ]] || { echo "HTTPS deployments require standard public ports 80/443" >&2; exit 1; }
  http_port=80
  https_port=443
else
  tls_email="${tls_email:-admin@localhost.invalid}"
  site_address=":80"
  authority="${site_url#http://}"
  authority="${authority%/}"
  if [[ "$authority" == *:* ]]; then
    http_port="${authority##*:}"
  else
    http_port=80
  fi
  https_port=8443
fi

secret_key="$(openssl rand -hex 48)"
aes_key="$(openssl rand -hex 32)"
inner_api_key="$(openssl rand -hex 32)"
initial_admin_token="$(openssl rand -hex 24)"
postgres_password="$(openssl rand -hex 24)"
minio_password="$(openssl rand -hex 24)"
platform_version="$(tr -d '\r\n' <"$REPO_ROOT/VERSION")"
deployment_id="dep_$(openssl rand -hex 16)"
git_commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')"
git_tag="$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || true)"
build_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null || true)" ]]; then
  build_dirty=true
else
  build_dirty=false
fi

umask 077
mkdir -p "$(dirname "$ENV_FILE")"
cat >"$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=airalogy-single-lab
PLATFORM_VERSION=$platform_version
AIRALOGY_DEPLOYMENT_ID=$deployment_id
GIT_TAG=$git_tag
GIT_COMMIT=$git_commit
BUILD_TIME=$build_time
BUILD_DIRTY=$build_dirty
AIRALOGY_RELEASE_MANIFEST_SHA256=
AIRALOGY_API_IMAGE=airalogy-platform-api:$platform_version
AIRALOGY_WEB_IMAGE=airalogy-platform-web:$platform_version
AIRALOGY_PROTOCOL_EXECUTOR_IMAGE=airalogy-platform-protocol-executor:$platform_version
AIRALOGY_POSTGRES_IMAGE=airalogy-platform-postgres:$platform_version
AIRALOGY_RELEASE_METADATA_REQUIRED=false
AIRALOGY_RELEASE_MANIFEST_FILE=./release-manifest.json
AIRALOGY_RELEASE_METADATA_FILE=./release-manifest.env
AIRALOGY_STATE_DIR=./state/$deployment_id
REDIS_IMAGE=redis:7-alpine
MINIO_IMAGE=quay.io/minio/minio:RELEASE.2024-03-26T22-10-45Z
MINIO_MC_IMAGE=quay.io/minio/mc:RELEASE.2024-03-25T16-41-14Z
COMPONENT_BUILD_MEMORY_MB=3072
WEB_BUILD_MEMORY_MB=6144

SITE_URL=$site_url
SITE_ADDRESS=$site_address
HTTP_BIND_ADDRESS=0.0.0.0
HTTP_PORT=$http_port
HTTPS_BIND_ADDRESS=0.0.0.0
HTTPS_PORT=$https_port
TLS_EMAIL=$tls_email

APP_ENV=production
DEPLOYMENT_MODE=single_lab
LAB_STRUCTURE_MODE=structured
API_ROOT_PATH=
SIGNUP_MODE=invite_only
DOCUMENTATION_PROFILE=customer_managed
DOCUMENTATION_URL=/docs/
SUPPORT_URL=
SINGLE_LAB_UID=$lab_uid
SINGLE_LAB_NAME=$lab_name
SINGLE_LAB_DESCRIPTION=
SINGLE_LAB_DEFAULT_PROJECT_UID=lab_protocols
SINGLE_LAB_DEFAULT_PROJECT_NAME=Lab Protocols
INVITATION_TTL_HOURS=168
PASSWORD_RESET_TTL_MINUTES=60

SECRET_KEY=$secret_key
AES_KEY=$aes_key
INNER_API_KEY=$inner_api_key
INITIAL_ADMIN_TOKEN=$initial_admin_token

POSTGRES_USER=airalogy
POSTGRES_PASSWORD=$postgres_password
POSTGRES_DB=airalogy

STORAGE_BACKEND=minio
MINIO_ROOT_USER=airalogy
MINIO_ROOT_PASSWORD=$minio_password
MINIO_BUCKET=airalogy
MINIO_CONSOLE_PORT=9201
REDIS_MAXMEMORY=256mb

LOG_REQUEST_BODIES=false
LOG_LEVEL=INFO
SQL_LOG_LEVEL=WARNING
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
RECORD_DELETE_GRACE_DAYS=7
MAX_LABS_PER_USER=1

VITE_APP_TITLE=$lab_name
VITE_APP_DESC=Private laboratory research workspace.
VITE_DOCS_URL=/docs/

APT_DEBIAN_MIRROR=http://deb.debian.org/debian
APT_DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
APT_POSTGRES_MIRROR=http://apt.postgresql.org/pub/repos/apt

AI_ENABLED=
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=
OPENAI_API_KEY=
OPENAI_BASE_URL=
ENABLE_GPT_MODEL=false
MASTERBRAIN_CALL_MODE=package
CHAT_API_ENDPOINT=
CHAT_MODEL_FAST=qwen3.5-flash
CHAT_MODEL_ACCURATE=qwen3.5-plus
CHAT_MODEL_DEEP=qwen-max

AIRALOGY_ENGINE_IMAGE=ghcr.io/airalogy/airalogy-engine:0.16.0@sha256:5d26af0a28fc42f042cf079ac6e00b1a4435ff2d1fd02631c5d356bfdd0e08b7
AIRALOGY_ENGINE_DEBUG=false
AIRALOGY_ENGINE_BOXLITE_HOME=

BACKUP_DIR=./backups
EOF
chmod 600 "$ENV_FILE"

printf 'Wrote %s with mode 600.\n' "$ENV_FILE"
printf 'Initial setup code: %s\n' "$initial_admin_token"
