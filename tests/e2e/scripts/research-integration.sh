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
export PYTHONPATH="$repository_root/apps/compute-runner/src${PYTHONPATH:+:$PYTHONPATH}"
test_files=(
  tests/test_research_integration.py
  tests/test_resource_postgres.py
  tests/test_record_analysis_postgres.py
  tests/test_project_analyses_postgres.py
  tests/test_project_analysis_migrations_postgres.py
  tests/test_analysis_publication_postgres.py
  tests/test_analysis_publication_knowledge_postgres.py
  tests/test_analysis_evidence_review_postgres.py
  tests/test_record_analysis_ai_postgres.py
  tests/test_record_analysis_compute_postgres.py
  tests/test_analysis_compute_files_postgres.py
  tests/test_analysis_compute_attachments_postgres.py
  tests/test_analysis_compute_runtime_postgres.py
  tests/test_record_analysis_compute_ai_postgres.py
  tests/test_analysis_compute_ai_runner_postgres.py
  tests/test_workflow_definitions_postgres.py
  tests/test_workflow_binding_postgres.py
  tests/test_workflow_condition_postgres.py
  tests/test_workflow_visibility_postgres.py
  tests/test_workflow_analysis_methods_postgres.py
  tests/test_workflow_analysis_runtime_postgres.py
  tests/test_workflow_analysis_lifecycle_postgres.py
  tests/test_workflow_project_methods_postgres.py
  tests/test_workflow_project_runtime_postgres.py
  tests/test_analysis_protocol_drafts_postgres.py
  tests/test_workflow_compute_methods_postgres.py
  tests/test_workflow_compute_runtime_postgres.py
  tests/test_workflow_compute_r_postgres.py
  tests/test_workflow_compute_locks_postgres.py
  tests/test_workflow_conversions_postgres.py
  tests/test_lab_workflow_file_cleanup_postgres.py
  tests/test_workflow_files_postgres.py
  tests/test_workflow_asset_migrations_postgres.py
  tests/test_workflow_asset_runtime_postgres.py
  tests/test_research_asset_visibility_postgres.py
  tests/test_research_context_visibility_postgres.py
)
uv --directory apps/api run --with pytest python -m pytest "${test_files[@]}" "$@"
