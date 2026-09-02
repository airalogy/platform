from importlib import import_module
from uuid import uuid4

import pytest
from app.main import app
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    ResearchInstrumentGatewayAudit,
)
from app.routers.research_instrument_gateways import InstrumentCommandDraft
from app.services.research_instruments import (
    gateway_snapshot,
    gateway_token_digest,
    generate_gateway_token,
    validate_bounded_schema,
)
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def object_schema() -> dict:
    return {
        "type": "object",
        "properties": {"temperature": {"type": "number"}},
        "required": ["temperature"],
        "additionalProperties": False,
    }


def test_instrument_gateway_tables_keep_credentials_out_of_public_models():
    gateway_ddl = compile_table(ResearchInstrumentGateway)
    command_ddl = compile_table(ResearchInstrumentCommand)
    audit_ddl = compile_table(ResearchInstrumentGatewayAudit)

    assert "token_digest VARCHAR(64) NOT NULL" in gateway_ddl
    assert "UNIQUE (token_digest)" in gateway_ddl
    assert "uq_research_instrument_command_identity" in command_ddl
    assert "device_confirmation_required" in command_ddl
    assert "resource_revision_id" in command_ddl
    assert "snapshot JSON" in audit_ddl

    gateway = ResearchInstrumentGateway(
        id=uuid4(),
        lab_id=uuid4(),
        name="Microscope room gateway",
        description="Local adapter",
        token_digest="a" * 64,
        token_hint="12345678",
        enabled=True,
        revision=1,
        created_by_user_id=uuid4(),
        updated_by_user_id=uuid4(),
    )
    assert "token_digest" not in gateway.as_dict()
    assert "token_digest" not in gateway_snapshot(gateway)


def test_instrument_gateway_migration_follows_notifications():
    migration = import_module("migrations.versions.0026_research_instrument_gateways")

    assert migration.down_revision == "0025_research_notifications"
    assert migration.TABLE_NAMES == (
        "research_instrument_gateways",
        "research_instrument_commands",
        "research_instrument_gateway_audits",
    )


def test_gateway_credentials_are_high_entropy_and_only_stored_as_digest():
    first = generate_gateway_token()
    second = generate_gateway_token()

    assert first.startswith("aigw_")
    assert len(first) > 40
    assert first != second
    assert len(gateway_token_digest(first)) == 64
    assert first not in gateway_token_digest(first)


def test_instrument_command_contract_is_schema_bounded_and_fail_closed():
    command = InstrumentCommandDraft(
        gateway_id=uuid4(),
        resource_id=uuid4(),
        command_key="incubator.set-temperature",
        command_version="1",
        name="Set incubator temperature",
        input_schema=object_schema(),
        output_schema={
            "type": "object",
            "properties": {"accepted": {"type": "boolean"}},
            "required": ["accepted"],
            "additionalProperties": False,
        },
        risk="high",
        device_confirmation_required=True,
    )
    assert command.command_key == "incubator.set-temperature"

    with pytest.raises(ValidationError, match="device-side confirmation"):
        InstrumentCommandDraft(
            gateway_id=uuid4(),
            resource_id=uuid4(),
            command_key="incubator.set-temperature",
            command_version="1",
            name="Set incubator temperature",
            input_schema=object_schema(),
            output_schema=object_schema(),
            risk="high",
            device_confirmation_required=False,
        )

    with pytest.raises(ValueError, match="remote references"):
        validate_bounded_schema(
            {
                "type": "object",
                "properties": {
                    "payload": {"$ref": "https://example.org/unsafe-schema.json"}
                },
            },
            "input",
        )

    with pytest.raises(ValueError, match="must describe an object"):
        validate_bounded_schema({"type": "string"}, "input")


def test_instrument_gateway_management_routes_are_registered():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if route.path.startswith("/research-instrument-gateways")
    }

    assert ("/research-instrument-gateways", ("GET",)) in routes
    assert ("/research-instrument-gateways", ("POST",)) in routes
    assert ("/research-instrument-gateways/commands", ("POST",)) in routes
    assert (
        "/research-instrument-gateways/{gateway_id}/rotate",
        ("POST",),
    ) in routes
