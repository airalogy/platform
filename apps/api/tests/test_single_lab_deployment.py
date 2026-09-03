from importlib import import_module

from app.cli.validate_deployment import validate_single_lab_deployment
from app.config import config
from app.models.base import Base
from app.routers.projects import is_protected_default_project
from migrations.model_registry import import_models


def test_deployment_validator_reports_profile_mismatch(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "API_ROOT_PATH", "/api")

    errors = validate_single_lab_deployment()

    assert "APP_ENV must be production" in errors
    assert "DEPLOYMENT_MODE must be single_lab" in errors
    assert "LAB_STRUCTURE_MODE must be structured" in errors
    assert "API_ROOT_PATH must be empty because the bundled proxy strips /api" in errors


def test_initial_revision_excludes_tables_owned_by_later_revisions():
    initial_revision = import_module("migrations.versions.0001_initial_schema")
    resource_revision = import_module(
        "migrations.versions.0007_resources_and_schema_governance"
    )
    export_revision = import_module("migrations.versions.0008_record_exports")
    research_revision = import_module("migrations.versions.0009_research_tasks")
    knowledge_revision = import_module("migrations.versions.0011_knowledge_core")
    research_knowledge_revision = import_module(
        "migrations.versions.0012_research_environment_knowledge"
    )
    research_log_revision = import_module("migrations.versions.0013_research_log")
    research_asset_revision = import_module("migrations.versions.0014_research_assets")
    research_digital_revision = import_module(
        "migrations.versions.0015_research_digital_actions"
    )
    research_executor_revision = import_module(
        "migrations.versions.0016_research_executor_bindings"
    )
    research_resource_revision = import_module(
        "migrations.versions.0017_research_resource_reservations"
    )
    research_limits_revision = import_module(
        "migrations.versions.0018_research_operational_limits"
    )
    knowledge_protocol_revision = import_module(
        "migrations.versions.0019_knowledge_protocol_lineage"
    )
    knowledge_evidence_revision = import_module(
        "migrations.versions.0020_knowledge_evidence_lineage"
    )
    protocol_improvement_revision = import_module(
        "migrations.versions.0021_protocol_improvement_lineage"
    )
    protocol_improvement_ai_revision = import_module(
        "migrations.versions.0022_protocol_improvement_ai_provenance"
    )
    review_recommendation_revision = import_module(
        "migrations.versions.0023_research_review_recommendations"
    )
    human_executor_revision = import_module(
        "migrations.versions.0024_research_human_executor_profiles"
    )
    research_notification_revision = import_module(
        "migrations.versions.0025_research_notifications"
    )
    instrument_gateway_revision = import_module(
        "migrations.versions.0026_research_instrument_gateways"
    )
    instrument_job_revision = import_module(
        "migrations.versions.0027_research_instrument_jobs"
    )
    service_catalog_revision = import_module(
        "migrations.versions.0028_research_service_catalog"
    )
    service_job_revision = import_module(
        "migrations.versions.0029_research_service_jobs"
    )
    compute_environment_revision = import_module(
        "migrations.versions.0030_research_compute_environments"
    )
    compute_runner_revision = import_module(
        "migrations.versions.0031_research_compute_runners"
    )
    compute_job_revision = import_module(
        "migrations.versions.0032_research_compute_jobs"
    )
    compute_output_revision = import_module(
        "migrations.versions.0033_research_compute_outputs"
    )
    import_models()

    later_tables = {
        "account_security",
        "account_tokens",
        "access_grants",
        "access_grant_audits",
        "model_usage_events",
    }
    later_tables.update(resource_revision.RESOURCE_TABLE_NAMES)
    later_tables.update(export_revision.TABLE_NAMES)
    later_tables.update(research_revision.TABLE_NAMES)
    later_tables.update(knowledge_revision.TABLE_NAMES)
    later_tables.update(research_knowledge_revision.TABLE_NAMES)
    later_tables.update(research_log_revision.TABLE_NAMES)
    later_tables.update(research_asset_revision.TABLE_NAMES)
    later_tables.update(research_digital_revision.TABLE_NAMES)
    later_tables.update(research_executor_revision.TABLE_NAMES)
    later_tables.update(research_resource_revision.TABLE_NAMES)
    later_tables.update(research_limits_revision.TABLE_NAMES)
    later_tables.update(knowledge_protocol_revision.TABLE_NAMES)
    later_tables.update(knowledge_evidence_revision.TABLE_NAMES)
    later_tables.update(protocol_improvement_revision.TABLE_NAMES)
    assert protocol_improvement_ai_revision.down_revision == (
        "0021_protocol_improvement_lineage"
    )
    later_tables.update(review_recommendation_revision.TABLE_NAMES)
    later_tables.update(human_executor_revision.TABLE_NAMES)
    later_tables.update(research_notification_revision.TABLE_NAMES)
    later_tables.update(instrument_gateway_revision.TABLE_NAMES)
    later_tables.update(instrument_job_revision.TABLE_NAMES)
    later_tables.update(service_catalog_revision.TABLE_NAMES)
    later_tables.update(service_job_revision.TABLE_NAMES)
    later_tables.update(compute_environment_revision.TABLE_NAMES)
    later_tables.update(compute_runner_revision.TABLE_NAMES)
    later_tables.update(compute_job_revision.TABLE_NAMES)
    later_tables.update(compute_output_revision.TABLE_NAMES)
    expected_initial_tables = set(Base.metadata.tables) - later_tables

    assert set(initial_revision.INITIAL_TABLE_NAMES) == expected_initial_tables


def test_custom_single_lab_default_project_is_protected(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_lab")
    monkeypatch.setattr(config, "SINGLE_LAB_DEFAULT_PROJECT_UID", "research")

    assert is_protected_default_project("research")
    assert not is_protected_default_project("another_project")
