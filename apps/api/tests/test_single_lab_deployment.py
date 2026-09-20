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
    claim_ai_revision = import_module(
        "migrations.versions.0034_research_claim_ai_provenance"
    )
    result_package_revision = import_module(
        "migrations.versions.0035_research_result_package_snapshots"
    )
    action_output_revision = import_module(
        "migrations.versions.0036_research_action_output_snapshots"
    )
    resource_consumption_revision = import_module(
        "migrations.versions.0038_research_resource_consumptions"
    )
    action_dependency_guard_revision = import_module(
        "migrations.versions.0039_research_action_dependency_guard"
    )
    autonomy_policy_revision = import_module(
        "migrations.versions.0040_research_autonomy_policy"
    )
    autonomy_grant_revision = import_module(
        "migrations.versions.0043_research_autonomy_grants"
    )
    sample_lineage_revision = import_module(
        "migrations.versions.0044_sample_lineage_semantics"
    )
    instrument_control_revision = import_module(
        "migrations.versions.0047_instrument_control_sessions"
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
    assert claim_ai_revision.down_revision == "0033_research_compute_outputs"
    later_tables.update(result_package_revision.TABLE_NAMES)
    assert result_package_revision.down_revision == (
        "0034_research_claim_ai_provenance"
    )
    later_tables.update(action_output_revision.TABLE_NAMES)
    assert action_output_revision.down_revision == (
        "0035_research_result_package_snapshots"
    )
    later_tables.update(resource_consumption_revision.TABLE_NAMES)
    assert resource_consumption_revision.down_revision == (
        "0037_knowledge_ai_provenance"
    )
    assert action_dependency_guard_revision.down_revision == (
        "0038_research_resource_consumptions"
    )
    later_tables.update(autonomy_policy_revision.TABLE_NAMES)
    assert autonomy_policy_revision.down_revision == (
        "0039_research_action_dependency_guard"
    )
    later_tables.update(autonomy_grant_revision.TABLE_NAMES)
    assert autonomy_grant_revision.down_revision == (
        "0042_human_work_review_notifications"
    )
    assert sample_lineage_revision.down_revision == ("0043_research_autonomy_grants")
    assert instrument_control_revision.down_revision == (
        "0046_research_reproduction_assessments"
    )
    later_tables.update(instrument_control_revision.TABLE_NAMES)
    integration_revision = import_module(
        "migrations.versions.0048_instrument_integration_drafts"
    )
    assert integration_revision.down_revision == "0047_instrument_control_sessions"
    later_tables.update(integration_revision.TABLE_NAMES)
    pairing_revision = import_module("migrations.versions.0049_instrument_pairings")
    assert pairing_revision.down_revision == "0048_instrument_integration_drafts"
    later_tables.update(pairing_revision.TABLE_NAMES)
    package_revision = import_module(
        "migrations.versions.0050_instrument_adapter_packages"
    )
    assert package_revision.down_revision == "0049_instrument_pairings"
    later_tables.update(package_revision.TABLE_NAMES)
    installation_revision = import_module(
        "migrations.versions.0051_instrument_device_bindings"
    )
    assert installation_revision.down_revision == "0050_instrument_adapter_packages"
    later_tables.update(installation_revision.TABLE_NAMES)
    qualification_revision = import_module(
        "migrations.versions.0052_instrument_qualifications"
    )
    assert qualification_revision.down_revision == "0051_instrument_device_bindings"
    later_tables.update(qualification_revision.TABLE_NAMES)
    activation_revision = import_module(
        "migrations.versions.0053_instrument_activations"
    )
    assert activation_revision.down_revision == "0052_instrument_qualifications"
    later_tables.update(activation_revision.TABLE_NAMES)
    output_revision = import_module("migrations.versions.0054_instrument_outputs")
    assert output_revision.down_revision == "0053_instrument_activations"
    later_tables.update(output_revision.TABLE_NAMES)
    authoring_revision = import_module("migrations.versions.0055_instrument_authoring")
    assert authoring_revision.down_revision == "0054_instrument_outputs"
    later_tables.update(authoring_revision.TABLE_NAMES)
    analysis_revision = import_module("migrations.versions.0059_analysis")
    assert analysis_revision.down_revision == "0058_optional_embeddings"
    later_tables.update(analysis_revision.TABLE_NAMES)
    analysis_ai_revision = import_module("migrations.versions.0060_analysis_ai")
    assert analysis_ai_revision.down_revision == "0059_analysis"
    later_tables.update(analysis_ai_revision.TABLE_NAMES)
    analysis_compute_revision = import_module(
        "migrations.versions.0061_analysis_compute"
    )
    assert analysis_compute_revision.down_revision == "0060_analysis_ai"
    later_tables.update(analysis_compute_revision.TABLE_NAMES)
    workflow_revision = import_module("migrations.versions.0063_workflow_definitions")
    assert workflow_revision.down_revision == "0062_analysis_compute_ai"
    later_tables.update(workflow_revision.TABLE_NAMES)
    workflow_resolution_revision = import_module("migrations.versions.0064_workflow_node_resolutions")
    assert workflow_resolution_revision.down_revision == "0063_workflow_definitions"
    later_tables.update(workflow_resolution_revision.TABLE_NAMES)
    workflow_analysis_revision = import_module("migrations.versions.0065_workflow_analysis")
    assert workflow_analysis_revision.down_revision == "0064_workflow_node_resolutions"
    later_tables.update(workflow_analysis_revision.TABLE_NAMES)
    workflow_compute_revision = import_module("migrations.versions.0066_workflow_compute_methods")
    assert workflow_compute_revision.down_revision == "0065_workflow_analysis"
    workflow_conversion_revision = import_module("migrations.versions.0067_workflow_legacy_conversions")
    assert workflow_conversion_revision.down_revision == "0066_workflow_compute_methods"
    later_tables.update(workflow_conversion_revision.TABLE_NAMES)
    workflow_file_revision = import_module("migrations.versions.0068_workflow_file_bindings")
    assert workflow_file_revision.down_revision == workflow_conversion_revision.revision
    later_tables.update(workflow_file_revision.TABLE_NAMES)
    analysis_input_file_revision = import_module("migrations.versions.0069_analysis_compute_input_files")
    assert analysis_input_file_revision.down_revision == workflow_file_revision.revision
    later_tables.update(analysis_input_file_revision.TABLE_NAMES)
    project_analysis_revision = import_module("migrations.versions.0070_project_analysis")
    assert project_analysis_revision.down_revision == analysis_input_file_revision.revision
    later_tables.update(project_analysis_revision.TABLE_NAMES)
    workflow_asset_revision = import_module("migrations.versions.0071_workflow_asset_inputs")
    assert workflow_asset_revision.down_revision == "0070_project_analysis"
    later_tables.update(workflow_asset_revision.TABLE_NAMES)
    analysis_publication_revision = import_module("migrations.versions.0072_analysis_publications")
    assert analysis_publication_revision.down_revision == workflow_asset_revision.revision
    later_tables.update(analysis_publication_revision.TABLE_NAMES)
    workflow_project_revision = import_module("migrations.versions.0073_workflow_project_analysis")
    assert workflow_project_revision.down_revision == analysis_publication_revision.revision
    later_tables.update(workflow_project_revision.TABLE_NAMES)
    analysis_protocol_revision = import_module("migrations.versions.0074_analysis_protocol_drafts")
    assert analysis_protocol_revision.down_revision == workflow_project_revision.revision
    later_tables.update(analysis_protocol_revision.TABLE_NAMES)
    expected_initial_tables = set(Base.metadata.tables) - later_tables

    assert set(initial_revision.INITIAL_TABLE_NAMES) == expected_initial_tables


def test_custom_single_lab_default_project_is_protected(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_lab")
    monkeypatch.setattr(config, "SINGLE_LAB_DEFAULT_PROJECT_UID", "research")

    assert is_protected_default_project("research")
    assert not is_protected_default_project("another_project")
