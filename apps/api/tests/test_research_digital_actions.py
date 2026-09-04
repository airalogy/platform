import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import (
    ResearchActionStatus,
    ResearchHumanWorkItem,
    ResearchRunStatus,
    ResearchTaskStatus,
)
from app.models.research_execution import (
    ResearchExecutorBinding,
    ResearchExecutorBindingAudit,
    ResearchHumanExecutorProfile,
    ResearchHumanExecutorProfileAudit,
    ResearchResourceConsumption,
    ResearchResourceReservation,
    ResearchToolJob,
    ResearchWaitEvent,
)
from app.routers import research_executor_bindings as executor_bindings_router
from app.routers.research_actions import WaitEventDraft
from app.routers.research_executor_bindings import (
    ExecutorBindingDraft,
    _validate_capability_and_executor,
    list_eligible_executor_users,
)
from app.routers.research_human_executors import (
    HumanExecutorProfileDraft,
    HumanExecutorSkill,
)
from app.routers.research_human_executors import (
    _command as human_executor_profile_command,
)
from app.routers.research_resources import (
    ResourceActionDraft,
    _pinned_requirement,
    _resource_command,
)
from app.services import (
    research_resources,
    research_runtime,
    research_tools,
    resource_job_worker,
)
from app.services.research_capabilities import (
    pinned_tool_definition,
    protocol_capability,
    tool_capability,
)
from app.services.research_executor_bindings import (
    derived_executor_binding,
    enforce_environment_binding_scope,
    environment_executor_binding,
    matching_profile_skills,
    profile_is_available,
    resolve_human_executor_ref,
    resolve_skill_pool_executor,
    validate_executor_binding_for_capability,
    validate_pinned_executor_target,
    validate_pinned_skill_pool_executor,
)
from app.services.research_resources import (
    ResearchResourceError,
    activate_aira_resource_action,
    resolve_aira_resource_request,
)
from app.services.research_runtime import (
    activate_protocol_action,
    activate_tool_action,
    activate_wait_event_action,
    canonical_digest,
)
from app.services.research_tools import (
    execute_research_tool,
    get_research_tool,
    research_tool_catalog,
    validate_tool_argument_template,
    validate_tool_arguments,
    validate_tool_output_path,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_tool_jobs_are_typed_one_to_one_action_executions():
    ddl = compile_table(ResearchToolJob)

    assert "UNIQUE (action_id)" in ddl
    assert "tool_key" in ddl
    assert "arguments" in ddl
    assert "timeout_seconds" in ddl


def test_wait_events_have_unique_keys_payload_contract_and_stale_guard():
    ddl = compile_table(ResearchWaitEvent)

    assert "UNIQUE (event_key)" in ddl
    assert "expected_event_type" in ddl
    assert "payload_schema" in ddl
    assert "revision" in ddl


def test_digital_action_migration_follows_scientific_assets():
    migration = import_module("migrations.versions.0015_research_digital_actions")

    assert migration.down_revision == "0014_research_assets"
    assert migration.TABLE_NAMES == ("research_tool_jobs", "research_wait_events")


def test_executor_bindings_are_revisioned_and_audited():
    binding_ddl = compile_table(ResearchExecutorBinding)
    audit_ddl = compile_table(ResearchExecutorBindingAudit)

    assert "uq_research_executor_bindings_identity" in binding_ddl
    assert "approval_policy" in binding_ddl
    assert "constraints" in binding_ddl
    assert "revision" in binding_ddl
    assert "uq_research_executor_binding_audits_revision" in audit_ddl
    assert "snapshot" in audit_ddl

    migration = import_module("migrations.versions.0016_research_executor_bindings")
    assert migration.down_revision == "0015_research_digital_actions"
    assert migration.TABLE_NAMES == (
        "research_executor_bindings",
        "research_executor_binding_audits",
    )


def test_human_executor_profiles_are_revisioned_and_audited():
    profile_ddl = compile_table(ResearchHumanExecutorProfile)
    audit_ddl = compile_table(ResearchHumanExecutorProfileAudit)

    assert "uq_research_human_executor_profile_user" in profile_ddl
    assert "max_concurrent_items BETWEEN 1 AND 100" in profile_ddl
    assert "skills JSON" in profile_ddl
    assert "uq_research_human_executor_profile_audit_revision" in audit_ddl

    migration = import_module(
        "migrations.versions.0024_research_human_executor_profiles"
    )
    assert migration.down_revision == "0023_research_review_recommendations"
    assert migration.TABLE_NAMES == (
        "research_human_executor_profiles",
        "research_human_executor_profile_audits",
    )


def test_executor_binding_contract_rejects_cross_type_dispatch():
    valid = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key="tool:knowledge.search",
        capability_version="1",
        executor_type="platform_tool",
        executor_ref_type="platform_worker",
        executor_ref_id="knowledge.search",
        mode="durable_job",
    )
    assert valid.approval_policy == "always_ask"

    skill_pool = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key=f"protocol:{uuid4()}",
        capability_version="1.0.0",
        executor_type="human",
        executor_ref_type="skill_pool",
        executor_ref_id="lab.skills",
        mode="protocol_record",
        constraints={
            "required_skill_keys": ["western_blot"],
            "minimum_skill_level": 3,
        },
    )
    assert skill_pool.constraints["required_skill_keys"] == ["western_blot"]

    instrument_gateway_id = uuid4()
    instrument = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key=f"instrument:{uuid4()}",
        capability_version="3",
        executor_type="instrument_gateway",
        executor_ref_type="instrument_gateway",
        executor_ref_id=str(instrument_gateway_id),
        mode="leased_command",
    )
    service = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key=f"service:{uuid4()}",
        capability_version="2026.1",
        executor_type="external_service",
        executor_ref_type="service_provider",
        executor_ref_id=str(uuid4()),
        mode="governed_order",
    )
    human_work = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key="human:structured-work",
        capability_version="1",
        executor_type="human",
        executor_ref_type="task_role",
        executor_ref_id="task.owner",
        mode="structured_submission",
    )
    assert instrument.executor_ref_id == str(instrument_gateway_id)
    assert service.approval_policy == "always_ask"
    assert human_work.mode == "structured_submission"

    with pytest.raises(ValidationError, match="approval-gated"):
        ExecutorBindingDraft(
            **{
                **instrument.model_dump(),
                "approval_policy": "allow_read_only",
            }
        )

    with pytest.raises(ValidationError, match="Platform Tool execution requires"):
        ExecutorBindingDraft(
            lab_id=uuid4(),
            capability_key="tool:knowledge.search",
            capability_version="1",
            executor_type="platform_tool",
            executor_ref_type="user",
            executor_ref_id=str(uuid4()),
            mode="durable_job",
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExecutorBindingDraft(
            lab_id=uuid4(),
            capability_key="tool:knowledge.search",
            capability_version="1",
            executor_type="platform_tool",
            executor_ref_type="platform_worker",
            executor_ref_id="knowledge.search",
            mode="durable_job",
            constraints={"pretend_budget_limit": 1},
        )
    with pytest.raises(ValidationError, match="at least one skill"):
        ExecutorBindingDraft(
            lab_id=uuid4(),
            capability_key=f"protocol:{uuid4()}",
            capability_version="1.0.0",
            executor_type="human",
            executor_ref_type="skill_pool",
            executor_ref_id="lab.skills",
            mode="protocol_record",
        )


def test_human_executor_bindings_pin_task_roles_and_specific_users():
    owner_user_id = uuid4()
    explicit_user_id = uuid4()
    task_role = {
        "executor_type": "human",
        "executor_ref": {"type": "task_role", "id": "task.owner"},
    }
    explicit = {
        "executor_type": "human",
        "executor_ref": {"type": "user", "id": str(explicit_user_id)},
    }

    assert resolve_human_executor_ref(task_role, owner_user_id=owner_user_id)[
        "resolved_executor_ref"
    ] == {"type": "user", "id": str(owner_user_id)}
    assert resolve_human_executor_ref(explicit, owner_user_id=owner_user_id)[
        "resolved_executor_ref"
    ] == {"type": "user", "id": str(explicit_user_id)}

    with pytest.raises(ValueError, match="Unsupported human executor task role"):
        resolve_human_executor_ref(
            {
                "executor_type": "human",
                "executor_ref": {"type": "task_role", "id": "project.manager"},
            },
            owner_user_id=owner_user_id,
        )


def test_structured_human_work_binding_is_accepted_by_capability_validation():
    draft = ExecutorBindingDraft(
        lab_id=uuid4(),
        capability_key="human:structured-work",
        capability_version="1",
        executor_type="human",
        executor_ref_type="task_role",
        executor_ref_id="task.owner",
        mode="structured_submission",
    )

    result = asyncio.run(
        _validate_capability_and_executor(
            SimpleNamespace(), draft, actor_user_id=uuid4()
        )
    )

    assert result == {
        "kind": "human",
        "name": "Structured human work",
        "risk": "human_execution",
    }


def test_human_executor_profile_contract_normalizes_skills_and_preview():
    lab_id = uuid4()
    user_id = uuid4()
    draft = HumanExecutorProfileDraft(
        lab_id=lab_id,
        user_id=user_id,
        max_concurrent_items=2,
        skills=[
            HumanExecutorSkill(
                key=" Western_Blot ",
                name=" Western blot ",
                level=3,
                verified=True,
            )
        ],
        notes="  Trained operator  ",
    )
    command = human_executor_profile_command(draft)

    assert draft.skills[0].key == "western_blot"
    assert draft.skills[0].name == "Western blot"
    assert command["expected_revision"] == 0
    assert command["skills"][0]["verified"] is True
    assert command["notes"] == "Trained operator"
    assert len(canonical_digest(command)) == 64

    with pytest.raises(ValidationError, match="duplicate keys"):
        HumanExecutorProfileDraft(
            lab_id=lab_id,
            user_id=user_id,
            skills=[
                {"key": "assay", "name": "Assay", "level": 1},
                {"key": "ASSAY", "name": "Assay", "level": 2},
            ],
        )


def test_skill_pool_resolution_uses_verified_availability_and_workload(monkeypatch):
    now = datetime.now(UTC)
    lab_id = uuid4()
    project = SimpleNamespace(id=uuid4(), lab_id=lab_id, deleted_at=None)
    busy_profile = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        user_id=uuid4(),
        availability="available",
        available_from=None,
        available_until=None,
        max_concurrent_items=2,
        revision=2,
        skills=[
            {
                "key": "western_blot",
                "name": "Western blot",
                "level": 4,
                "verified": True,
                "expires_at": None,
            }
        ],
    )
    free_profile = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        user_id=uuid4(),
        availability="available",
        available_from=now - timedelta(days=1),
        available_until=now + timedelta(days=1),
        max_concurrent_items=1,
        revision=3,
        skills=[
            {
                "key": "western_blot",
                "name": "Western blot",
                "level": 3,
                "verified": True,
                "expires_at": None,
            }
        ],
    )
    busy_user = SimpleNamespace(id=busy_profile.user_id)
    free_user = SimpleNamespace(id=free_profile.user_id)
    query_results = [
        SimpleNamespace(
            all=lambda: [(busy_profile, busy_user), (free_profile, free_user)]
        ),
        SimpleNamespace(all=lambda: [(busy_profile.user_id, 1)]),
    ]
    db_session = SimpleNamespace(
        get=AsyncMock(return_value=project),
        execute=AsyncMock(side_effect=query_results),
    )
    monkeypatch.setattr(
        research_runtime, "has_research_capability", AsyncMock(return_value=True)
    )
    binding = {
        "executor_type": "human",
        "executor_ref": {"type": "skill_pool", "id": "lab.skills"},
        "constraints": {
            "required_skill_keys": ["western_blot"],
            "minimum_skill_level": 3,
        },
    }

    resolved = asyncio.run(
        resolve_skill_pool_executor(
            db_session,
            binding=binding,
            lab_id=lab_id,
            project_id=project.id,
        )
    )

    assert resolved["resolved_executor_ref"] == {
        "type": "user",
        "id": str(free_profile.user_id),
    }
    assert resolved["executor_resolution"]["profile_revision"] == 3
    assert resolved["executor_resolution"]["matched_skills"][0]["level"] == 3
    assert len(resolved["executor_resolution"]["profile_digest"]) == 64

    free_profile.skills[0]["verified"] = False
    assert (
        matching_profile_skills(
            free_profile,
            required_skill_keys=["western_blot"],
            minimum_skill_level=3,
            now=now,
        )
        is None
    )
    free_profile.availability = "unavailable"
    assert profile_is_available(free_profile, now=now) is False


def test_skill_pool_dispatch_rechecks_current_capacity():
    lab_id = uuid4()
    user_id = uuid4()
    profile = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        user_id=user_id,
        availability="available",
        available_from=None,
        available_until=None,
        max_concurrent_items=1,
        skills=[
            {
                "key": "western_blot",
                "name": "Western blot",
                "level": 3,
                "verified": True,
                "expires_at": None,
            }
        ],
    )
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(first=lambda: profile)),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(user_id, 1)])),
    )
    binding = {
        "executor_ref": {"type": "skill_pool", "id": "lab.skills"},
        "executor_resolution": {
            "profile_id": str(profile.id),
            "required_skill_keys": ["western_blot"],
            "minimum_skill_level": 3,
        },
    }

    with pytest.raises(ValueError, match="reached current work capacity"):
        asyncio.run(
            validate_pinned_skill_pool_executor(
                db_session,
                binding=binding,
                lab_id=lab_id,
                assignee_user_id=user_id,
            )
        )


def test_eligible_executor_users_are_project_permission_filtered(monkeypatch):
    project = SimpleNamespace(id=uuid4(), lab_id=uuid4(), deleted_at=None)
    current_user = SimpleNamespace(id=uuid4())
    eligible_user = SimpleNamespace(id=uuid4(), username="runner", name="Runner")
    blocked_user = SimpleNamespace(id=uuid4(), username="viewer", name="Viewer")
    db_session = SimpleNamespace(
        get=AsyncMock(return_value=project),
        scalars=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [eligible_user, blocked_user])
        ),
    )
    require_access = AsyncMock()
    has_access = AsyncMock(
        side_effect=lambda _db_session, **kwargs: kwargs["user"].id == eligible_user.id
    )
    monkeypatch.setattr(
        executor_bindings_router, "require_research_capability", require_access
    )
    monkeypatch.setattr(executor_bindings_router, "has_research_capability", has_access)

    result = asyncio.run(
        list_eligible_executor_users(
            project_id=project.id,
            current_user=current_user,
            db_session=db_session,
        )
    )

    assert result == {
        "items": [{"id": str(eligible_user.id), "username": "runner", "name": "Runner"}]
    }
    require_access.assert_awaited_once_with(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    assert has_access.await_count == 2


def test_resource_reservations_are_typed_and_follow_executor_bindings():
    ddl = compile_table(ResearchResourceReservation)

    assert "UNIQUE (action_id)" in ddl
    assert "inventory_reservation_id" in ddl
    assert "equipment_booking_id" in ddl
    assert "resource_revision_id" in ddl
    assert "quantity" in ddl

    migration = import_module("migrations.versions.0017_research_resource_reservations")
    assert migration.down_revision == "0016_research_executor_bindings"
    assert migration.TABLE_NAMES == (
        "research_task_resource_requirements",
        "research_resource_reservations",
    )


def test_resource_consumptions_link_immutable_inventory_events_to_exact_records():
    ddl = compile_table(ResearchResourceConsumption)

    assert "uq_research_resource_consumption_inventory_event" in ddl
    assert "fk_research_resource_consumption_record" in ddl
    assert "FOREIGN KEY(record_id, record_version)" in ddl
    assert "REFERENCES records (id, version)" in ddl
    assert "remaining_quantity" in ddl

    migration = import_module("migrations.versions.0038_research_resource_consumptions")
    assert migration.down_revision == "0037_knowledge_ai_provenance"
    assert migration.TABLE_NAMES == ("research_resource_consumptions",)
    assert any(
        "prevent_research_resource_consumption_mutation" in value
        for value in migration.upgrade.__code__.co_consts
        if isinstance(value, str)
    )


def test_resource_action_contract_separates_inventory_and_equipment():
    inventory = ResourceActionDraft(
        kind="inventory",
        resource_id=uuid4(),
        container_id=uuid4(),
        quantity="2.5",
        unit="mg",
        purpose="Reserve reagent for assay",
        idempotency_key="resource-action-inventory",
    )
    assert str(inventory.quantity) == "2.5"

    equipment = ResourceActionDraft(
        kind="equipment",
        resource_id=uuid4(),
        starts_at=datetime.now(UTC) + timedelta(hours=1),
        ends_at=datetime.now(UTC) + timedelta(hours=2),
        purpose="Book the microscope",
        idempotency_key="resource-action-equipment",
    )
    assert equipment.container_id is None

    with pytest.raises(ValidationError, match="cannot include a booking window"):
        ResourceActionDraft(
            kind="inventory",
            resource_id=uuid4(),
            container_id=uuid4(),
            quantity="1",
            unit="mL",
            starts_at=datetime.now(UTC) + timedelta(hours=1),
            ends_at=datetime.now(UTC) + timedelta(hours=2),
            purpose="Invalid mixed reservation",
            idempotency_key="resource-action-invalid",
        )


def test_resource_action_preview_is_bound_to_inventory_and_environment_revisions():
    resource_type_id = uuid4()
    requirement = {
        "key": f"resource:{resource_type_id}",
        "version": "4",
        "source_id": str(resource_type_id),
        "source_revision_id": str(uuid4()),
    }
    run = SimpleNamespace(
        id=uuid4(),
        plan_version=2,
        environment_snapshot={"resources": [requirement]},
    )
    assert _pinned_requirement(run, resource_type_id) == requirement

    params = ResourceActionDraft(
        kind="inventory",
        resource_id=uuid4(),
        container_id=uuid4(),
        quantity="2.5",
        unit="mg",
        purpose="Reserve reagent for assay",
        idempotency_key="resource-action-revision",
    )
    task = SimpleNamespace(id=uuid4(), revision=3)
    context = {
        "resource": SimpleNamespace(
            id=params.resource_id, resource_type_id=resource_type_id
        ),
        "resource_revision": SimpleNamespace(id=uuid4(), revision=7),
        "requirement": requirement,
        "balance": SimpleNamespace(version=5, available=10, unit="mg"),
        "requested_in_balance_unit": params.quantity,
    }
    command = _resource_command(task=task, run=run, params=params, context=context)
    digest = canonical_digest(command)
    context["balance"] = SimpleNamespace(version=6, available=7.5, unit="mg")

    assert command["resource_revision"] == 7
    assert command["inventory"]["balance_version"] == 5
    assert digest != canonical_digest(
        _resource_command(task=task, run=run, params=params, context=context)
    )


def test_aira_resource_resolution_selects_a_permissioned_available_container(
    monkeypatch,
):
    resource_type_id = uuid4()
    type_revision_id = uuid4()
    resource = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        resource_type_id=resource_type_id,
        current_revision_id=uuid4(),
        name="Antibody A",
        code="AB-A",
        visibility="lab",
    )
    revision = SimpleNamespace(
        id=resource.current_revision_id,
        revision=5,
        resource_type_revision_id=type_revision_id,
    )
    container = SimpleNamespace(id=uuid4(), code="AB-A-01")
    balance = SimpleNamespace(version=3, available=10, unit="mg")
    scalars = SimpleNamespace(all=lambda: [resource])
    rows = SimpleNamespace(all=lambda: [(container, balance, None)])
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=scalars),
        execute=AsyncMock(return_value=rows),
        get=AsyncMock(return_value=revision),
    )
    access = SimpleNamespace(
        allows=lambda capability: capability == "inventory.operate"
    )
    access.sources = []
    monkeypatch.setattr(
        research_resources, "resolve_resource_access", AsyncMock(return_value=access)
    )
    task = SimpleNamespace(id=uuid4(), lab_id=resource.lab_id)
    run = SimpleNamespace(
        environment_snapshot={
            "resources": [
                {
                    "key": f"resource:{resource_type_id}",
                    "version": "2",
                    "source_id": str(resource_type_id),
                    "source_revision_id": str(type_revision_id),
                    "metadata": {"capabilities": {"inventory": True}},
                }
            ]
        }
    )

    resolved = asyncio.run(
        resolve_aira_resource_request(
            db_session,
            task=task,
            run=run,
            user_id=uuid4(),
            request={
                "resource_type_key": f"resource:{resource_type_id}",
                "kind": "inventory",
                "quantity": "2.5",
                "unit": "mg",
                "purpose": "Run assay",
            },
        )
    )

    assert resolved["resource_id"] == str(resource.id)
    assert resolved["inventory"]["container_id"] == str(container.id)
    assert resolved["inventory"]["balance_version"] == 3


def test_approved_aira_resource_action_rechecks_inventory_version(monkeypatch):
    resource_type_id = uuid4()
    type_revision_id = uuid4()
    resource_id = uuid4()
    revision_id = uuid4()
    container_id = uuid4()
    action_id = uuid4()
    requirement = {
        "key": f"resource:{resource_type_id}",
        "version": "2",
        "source_id": str(resource_type_id),
        "source_revision_id": str(type_revision_id),
    }
    reservation = SimpleNamespace(
        id=uuid4(),
        action_id=action_id,
        kind="inventory",
        resource_id=resource_id,
        resource_revision_id=revision_id,
        resource_revision=5,
        container_id=container_id,
        quantity="2.5",
        unit="mg",
        purpose="Run assay",
        status="proposed",
        revision=1,
        inventory_reservation_id=None,
    )
    resource = SimpleNamespace(
        id=resource_id,
        lab_id=uuid4(),
        resource_type_id=resource_type_id,
        current_revision_id=revision_id,
        status="active",
        archived_at=None,
        visibility="lab",
    )
    revision = SimpleNamespace(
        id=revision_id,
        revision=5,
        resource_type_revision_id=type_revision_id,
    )
    type_revision = SimpleNamespace(booking_policy="none")
    container = SimpleNamespace(
        id=container_id,
        resource_id=resource_id,
        status="active",
        archived_at=None,
    )
    balance = SimpleNamespace(version=4, available=10, unit="mg")

    async def get_model(model, key):
        name = model.__name__
        return {
            "Resource": resource,
            "ResourceRevision": revision,
            "ResourceTypeRevision": type_revision,
            "ResourceContainer": container,
        }.get(name)

    db_session = SimpleNamespace(
        get=AsyncMock(side_effect=get_model),
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: balance)
        ),
    )
    access = SimpleNamespace(
        allows=lambda capability: capability == "inventory.operate"
    )
    access.sources = []
    monkeypatch.setattr(
        ResearchResourceReservation, "find_by", AsyncMock(return_value=reservation)
    )
    monkeypatch.setattr(
        research_resources, "resolve_resource_access", AsyncMock(return_value=access)
    )
    reserve = AsyncMock()
    monkeypatch.setattr(research_resources, "reserve_inventory", reserve)
    task = SimpleNamespace(id=uuid4(), lab_id=resource.lab_id)
    run = SimpleNamespace(
        environment_snapshot={"resources": [requirement]},
        requested_by_user_id=uuid4(),
        status="waiting_for_approval",
    )
    action = SimpleNamespace(
        id=action_id,
        input_data={
            "resolved": {
                "resource_revision_id": str(revision_id),
                "resource_type_requirement": requirement,
                "inventory": {"balance_version": 3},
            }
        },
        revision=1,
    )

    with pytest.raises(ResearchResourceError, match="changed after Aira"):
        asyncio.run(
            activate_aira_resource_action(
                db_session,
                task=task,
                run=run,
                action=action,
                actor_user_id=run.requested_by_user_id,
            )
        )
    reserve.assert_not_awaited()

    balance.version = 3
    reserve.return_value = SimpleNamespace(
        id=uuid4(), status="active", quantity="2.5", unit="mg"
    )
    event_kind, event_payload = asyncio.run(
        activate_aira_resource_action(
            db_session,
            task=task,
            run=run,
            action=action,
            actor_user_id=run.requested_by_user_id,
        )
    )

    assert event_kind == "resource.inventory_reserved"
    assert event_payload["status"] == "active"
    assert reservation.status == "active"
    assert action.status == ResearchActionStatus.COMPLETED.value
    assert run.status == ResearchRunStatus.RUNNING.value
    reserve.assert_awaited_once()


def test_executor_binding_scope_constraints_fail_closed():
    allowed_project = uuid4()
    binding = {
        "constraints": {
            "allowed_project_ids": [str(allowed_project)],
            "allowed_autonomy_levels": ["assisted"],
        }
    }

    enforce_environment_binding_scope(
        binding, project_id=allowed_project, autonomy_level="assisted"
    )
    with pytest.raises(ValueError, match="does not allow this Project"):
        enforce_environment_binding_scope(
            binding, project_id=uuid4(), autonomy_level="assisted"
        )
    with pytest.raises(ValueError, match="does not allow this autonomy"):
        enforce_environment_binding_scope(
            binding,
            project_id=allowed_project,
            autonomy_level="bounded_autopilot",
        )


def test_tool_catalog_is_allowlisted_versioned_and_schema_validated():
    catalog = research_tool_catalog()

    assert set(catalog) == {
        "knowledge.search",
        "literature.search",
        "literature.resolve_doi",
    }
    assert catalog["knowledge.search"].version == "1"
    assert catalog["knowledge.search"].available is True
    validate_tool_arguments(catalog["knowledge.search"], {"query": "RNA", "limit": 5})
    with pytest.raises(ValueError, match="Invalid Tool arguments"):
        validate_tool_arguments(catalog["knowledge.search"], {"query": ""})
    with pytest.raises(ValueError, match="Invalid Tool arguments"):
        validate_tool_arguments(
            catalog["knowledge.search"], {"query": "RNA", "unknown": True}
        )
    with pytest.raises(ValueError, match="Unknown Research Tool"):
        get_research_tool("shell.run")


def test_tool_argument_templates_reserve_only_declared_bound_properties():
    definition = research_tool_catalog()["knowledge.search"]

    validate_tool_argument_template(
        definition,
        {"limit": 5},
        bound_argument_names={"query"},
    )
    with pytest.raises(ValueError, match="undeclared input property"):
        validate_tool_argument_template(
            definition,
            {},
            bound_argument_names={"command"},
        )
    with pytest.raises(ValueError, match="static value"):
        validate_tool_argument_template(
            definition,
            {"query": "RNA"},
            bound_argument_names={"query"},
        )


def test_tool_output_binding_paths_must_follow_the_declared_schema():
    definition = research_tool_catalog()["literature.search"]

    validate_tool_output_path(definition, ["result", "items", "0", "doi"])
    with pytest.raises(ValueError, match="outside the output Schema"):
        validate_tool_output_path(
            definition, ["result", "items", "0", "invented_field"]
        )
    with pytest.raises(ValueError, match="must use an index"):
        validate_tool_output_path(definition, ["result", "items", "first", "doi"])


def test_resolve_doi_tool_returns_a_candidate_without_importing_it(monkeypatch):
    class Provider:
        async def resolve_doi(self, doi: str):
            assert doi == "10.1000/test"
            return {"doi": doi, "title": "Test paper"}

    monkeypatch.setattr(research_tools, "get_literature_provider", lambda: Provider())
    definition = research_tool_catalog()["literature.resolve_doi"]

    result = asyncio.run(
        execute_research_tool(
            AsyncMock(),
            task=SimpleNamespace(),
            definition=definition,
            arguments={"doi": "10.1000/test"},
        )
    )

    assert result["found"] is True
    assert result["item"]["title"] == "Test paper"


def test_tool_execution_is_limited_to_the_pinned_environment():
    environment = {
        "schema": "airalogy.research-environment.v2",
        "tools": [research_tool_catalog()["knowledge.search"].payload()],
    }

    assert pinned_tool_definition(environment, "knowledge.search").version == "1"
    with pytest.raises(ValueError, match="not pinned"):
        pinned_tool_definition(environment, "literature.search")


def test_capability_registry_is_derived_and_executor_bindings_are_explicit():
    protocol_id = uuid4()
    version_id = uuid4()
    protocol = SimpleNamespace(
        id=protocol_id,
        uid="rna_assay",
        name="RNA assay",
        description="Measure RNA",
    )
    version = SimpleNamespace(
        id=version_id,
        version="1.2.0",
        json_schema={"type": "object"},
    )
    protocol_item = protocol_capability(protocol, version).payload()
    tool_item = tool_capability(research_tool_catalog()["knowledge.search"]).payload()
    owner_user_id = uuid4()
    bindings = [
        derived_executor_binding(capability=protocol_item, owner_user_id=owner_user_id),
        derived_executor_binding(capability=tool_item, owner_user_id=owner_user_id),
    ]

    assert protocol_item["key"] == f"protocol:{protocol_id}"
    assert protocol_item["source_revision_id"] == str(version_id)
    assert tool_item["key"] == "tool:knowledge.search"
    assert bindings[0]["mode"] == "protocol_record"
    assert bindings[1]["mode"] == "durable_job"
    assert all(item["approval_policy"] == "always_ask" for item in bindings)
    assert (
        environment_executor_binding(
            {"executor_bindings": bindings},
            tool_item["key"],
            tool_item["version"],
        )["mode"]
        == "durable_job"
    )
    legacy = environment_executor_binding(
        {"schema": "airalogy.research-environment.v1"},
        protocol_item["key"],
        protocol_item["version"],
        legacy_capability=protocol_item,
        owner_user_id=owner_user_id,
    )
    assert legacy["source"] == "platform_default"
    assert legacy["resolved_executor_ref"]["id"] == str(owner_user_id)


def test_physical_and_external_executor_defaults_bind_exact_targets():
    gateway_id = uuid4()
    provider_id = uuid4()
    instrument_capability = {
        "key": f"instrument:{uuid4()}",
        "version": "4",
        "kind": "instrument",
        "metadata": {"gateway_id": str(gateway_id)},
    }
    service_capability = {
        "key": f"service:{uuid4()}",
        "version": "2026.1",
        "kind": "service",
        "metadata": {"provider": {"id": str(provider_id)}},
    }

    instrument = derived_executor_binding(
        capability=instrument_capability, owner_user_id=uuid4()
    )
    service = derived_executor_binding(
        capability=service_capability, owner_user_id=uuid4()
    )

    assert instrument["mode"] == "leased_command"
    assert service["mode"] == "governed_order"
    validate_pinned_executor_target(
        instrument,
        executor_type="instrument_gateway",
        executor_ref_type="instrument_gateway",
        executor_ref_id=gateway_id,
        mode="leased_command",
    )
    validate_pinned_executor_target(
        service,
        executor_type="external_service",
        executor_ref_type="service_provider",
        executor_ref_id=provider_id,
        mode="governed_order",
    )
    with pytest.raises(ValueError, match="does not match"):
        validate_pinned_executor_target(
            instrument,
            executor_type="instrument_gateway",
            executor_ref_type="instrument_gateway",
            executor_ref_id=uuid4(),
            mode="leased_command",
        )
    with pytest.raises(ValueError, match="approval-gated"):
        validate_executor_binding_for_capability(
            {**instrument, "approval_policy": "allow_read_only"},
            instrument_capability,
        )


def test_wait_event_draft_validates_contract_and_normalizes_naive_deadline():
    deadline = datetime.now() + timedelta(hours=1)  # noqa: DTZ005
    draft = WaitEventDraft(
        title="Wait for instrument upload",
        event_key="instrument.run-42.completed",
        expected_event_type="instrument.completed",
        payload_schema={
            "type": "object",
            "required": ["file_id"],
            "properties": {"file_id": {"type": "string"}},
        },
        due_at=deadline,
        idempotency_key="wait-instrument-run-42",
    )

    assert draft.due_at == deadline.replace(tzinfo=UTC)
    with pytest.raises(ValidationError, match="Invalid event payload Schema"):
        WaitEventDraft(
            title="Broken contract",
            event_key="broken.contract",
            expected_event_type="broken",
            payload_schema={"type": "not-a-json-schema-type"},
            idempotency_key="broken-contract-key",
        )


def test_wait_event_has_a_distinct_run_boundary():
    assert ResearchRunStatus.WAITING_FOR_TOOL.value == "waiting_for_tool"
    assert ResearchRunStatus.WAITING_FOR_EVENT.value == "waiting_for_event"
    with pytest.raises(ValidationError, match="must be in the future"):
        WaitEventDraft(
            title="Expired event",
            event_key="expired.event",
            expected_event_type="expired",
            due_at=datetime.now(UTC) - timedelta(seconds=1),
            idempotency_key="expired-event-key",
        )


def test_persistent_worker_dispatches_research_tool_job(monkeypatch):
    tool_job_id = uuid4()
    process = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(resource_job_worker, "process_research_tool_job", process)

    result = asyncio.run(
        resource_job_worker.process_persistent_job(
            SimpleNamespace(),
            SimpleNamespace(
                kind="research_tool_job",
                payload={"tool_job_id": str(tool_job_id)},
            ),
        )
    )

    assert result == {"items": []}
    process.assert_awaited_once_with(ANY, tool_job_id=tool_job_id)


def test_openapi_exposes_digital_action_preview_confirm_contracts():
    paths = app.openapi()["paths"]

    assert "/research-tools" in paths
    assert "/research-tasks/{task_id}/tool-actions/preview" in paths
    assert "/research-tasks/{task_id}/tool-actions" in paths
    assert "/research-tasks/{task_id}/wait-actions/preview" in paths
    assert "/research-tasks/{task_id}/wait-actions" in paths
    assert "/research-wait-events/{wait_event_id}/signal/preview" in paths
    assert "/research-wait-events/{wait_event_id}/signal" in paths
    assert "/research-executor-bindings" in paths
    assert "/research-executor-bindings/eligible-users" in paths
    assert "/research-executor-bindings/preview" in paths
    assert "/research-executor-bindings/{binding_id}/preview" in paths
    assert "/research-human-executors" in paths
    assert "/research-human-executors/preview" in paths
    assert "/research-human-executors/{user_id}" in paths
    assert "/research-tasks/{task_id}/resource-actions/preview" in paths
    assert "/research-tasks/{task_id}/resource-actions" in paths
    assert "/research-resource-reservations/{reservation_id}/sync" in paths
    assert "/research-resource-reservations/{reservation_id}/release/preview" in paths
    assert "/research-resource-reservations/{reservation_id}/release" in paths


def test_protocol_action_activation_rechecks_pinned_executor_access(monkeypatch):
    assignee = SimpleNamespace(id=uuid4())
    project = SimpleNamespace(id=uuid4(), lab_id=uuid4())

    async def get_model(model, key):
        if model.__name__ == "Project":
            return project
        if model.__name__ == "User" and key == assignee.id:
            return assignee
        return None

    db_session = SimpleNamespace(get=AsyncMock(side_effect=get_model), add=Mock())
    monkeypatch.setattr(ResearchHumanWorkItem, "find_by", AsyncMock(return_value=None))
    access = AsyncMock(return_value=False)
    monkeypatch.setattr(research_runtime, "has_research_capability", access)

    with pytest.raises(ValueError, match="no longer eligible"):
        asyncio.run(
            activate_protocol_action(
                db_session,
                task=SimpleNamespace(
                    id=uuid4(),
                    project_id=project.id,
                    owner_user_id=uuid4(),
                ),
                run=SimpleNamespace(id=uuid4()),
                action=SimpleNamespace(
                    id=uuid4(),
                    policy_decision="ask",
                    assignee_user_id=assignee.id,
                ),
                protocol=SimpleNamespace(id=uuid4(), name="Assay"),
                version=SimpleNamespace(version="1.0.0"),
                instructions="Run the assay",
                actor_user_id=uuid4(),
            )
        )

    access.assert_awaited_once_with(
        db_session,
        user=assignee,
        project=project,
        capability="research.run",
    )
    db_session.add.assert_not_called()


def test_approved_tool_action_is_queued_at_a_durable_boundary(monkeypatch):
    job = SimpleNamespace(
        id=uuid4(),
        tool_key="knowledge.search",
        tool_version="1",
        status="queued",
    )
    action = SimpleNamespace(
        id=uuid4(),
        policy_decision="allow",
        status=ResearchActionStatus.PROPOSED.value,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_approval", last_error="old")
    task = SimpleNamespace(
        id=uuid4(), lab_id=uuid4(), status=ResearchTaskStatus.ACTIVE.value
    )
    monkeypatch.setattr(ResearchToolJob, "find_by", AsyncMock(return_value=job))
    enqueue = AsyncMock()
    emit = AsyncMock()
    monkeypatch.setattr(research_runtime, "enqueue_job", enqueue)
    monkeypatch.setattr(research_runtime, "emit_research_event", emit)

    result = asyncio.run(
        activate_tool_action(
            SimpleNamespace(),
            task=task,
            run=run,
            action=action,
            actor_user_id=uuid4(),
        )
    )

    assert result is job
    assert action.status == ResearchActionStatus.QUEUED.value
    assert run.status == ResearchRunStatus.WAITING_FOR_TOOL.value
    assert run.last_error is None
    enqueue.assert_awaited_once()
    emit.assert_awaited_once()


def test_approved_wait_action_opens_only_the_pinned_event(monkeypatch):
    event = SimpleNamespace(
        id=uuid4(),
        event_key="aira.run.step.data_asset.ready",
        expected_event_type="data_asset.ready",
        status="waiting",
    )
    action = SimpleNamespace(
        id=uuid4(),
        policy_decision="allow",
        status=ResearchActionStatus.PROPOSED.value,
        revision=1,
    )
    run = SimpleNamespace(id=uuid4(), status="waiting_for_approval", last_error="old")
    task = SimpleNamespace(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    monkeypatch.setattr(ResearchWaitEvent, "find_by", AsyncMock(return_value=event))
    emit = AsyncMock()
    monkeypatch.setattr(research_runtime, "emit_research_event", emit)

    result = asyncio.run(
        activate_wait_event_action(
            SimpleNamespace(),
            task=task,
            run=run,
            action=action,
            actor_user_id=uuid4(),
        )
    )

    assert result is event
    assert action.status == ResearchActionStatus.WAITING.value
    assert run.status == ResearchRunStatus.WAITING_FOR_EVENT.value
    assert run.last_error is None
    emit.assert_awaited_once()
