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
    import_models()

    later_tables = {
        "account_security",
        "account_tokens",
        "access_grants",
        "access_grant_audits",
    }
    expected_initial_tables = set(Base.metadata.tables) - later_tables

    assert set(initial_revision.INITIAL_TABLE_NAMES) == expected_initial_tables


def test_custom_single_lab_default_project_is_protected(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_lab")
    monkeypatch.setattr(config, "SINGLE_LAB_DEFAULT_PROJECT_UID", "research")

    assert is_protected_default_project("research")
    assert not is_protected_default_project("another_project")
