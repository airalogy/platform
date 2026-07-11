#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 1 ]] || die "usage: operator-reset-link.sh MEMBER_EMAIL"
require_env_file
wait_for_service api-server 60
compose exec -T api-server python3 -m app.cli.create_password_reset "$1"
