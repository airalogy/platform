"""Pure transport/data-disclosure guard regressions, no live infrastructure."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from app.libs.external_request_boundary import (
    MAX_EXTERNAL_BODY,
    ExternalRequestBoundary,
)
from app.routers.external_access import parse_args, safe_error, tool_schema
from app.services.external_access import (
    primitive_schema,
    record_view,
    scalar_field,
    validation_errors,
)
from fastapi import FastAPI, HTTPException
from jsonschema import Draft202012Validator


@pytest.mark.parametrize(
    "schema,allowed",
    [
        ({"type": "string"}, True),
        ({"type": "number"}, True),
        ({"anyOf": [{"type": "number", "minimum": 0}, {"type": "null"}]}, True),
        ({"anyOf": [{"type": "string", "format": "binary"}, {"type": "null"}]}, False),
        ({"type": []}, False),
        ({"type": [{}]}, False),
        ({"type": "string", "format": "date-time"}, True),
        ({"type": "string", "format": "binary"}, False),
        ({"type": "string", "airalogy_type": "FileId"}, False),
        ({"$ref": "#/$defs/Attachment"}, False),
        ({"type": "array"}, False),
        ({"anyOf": [{"type": "object"}, {"type": "null"}]}, False),
    ],
)
def test_primitive_schema_never_opens_complex_files(schema, allowed):
    assert scalar_field(schema) is allowed


@pytest.mark.parametrize("constraint", [{"enum": ["A", "B"]}, {"const": "A"}])
def test_nullable_choices_keep_null_in_advertised_constraints(constraint):
    schema = {"anyOf": [{"type": "string", **constraint}, {"type": "null"}]}
    flattened = primitive_schema(schema)
    for value in [None, "A", "B", "other", 1]:
        assert Draft202012Validator(flattened).is_valid(value) == Draft202012Validator(
            schema
        ).is_valid(value)


def test_omitted_private_values_are_not_fabricated_nulls():
    access = SimpleNamespace(policy=SimpleNamespace(blocked_fields=["secret"]))
    version = SimpleNamespace(
        json_schema={
            "vars": {
                "properties": {
                    key: {"type": "string"}
                    for key in ["secret", "public", "url", "empty"]
                }
            }
        }
    )
    record = SimpleNamespace(
        id="one",
        version=1,
        protocol_version="1.0.0",
        data={
            "var": {
                "secret": "hidden",
                "public": "safe",
                "url": "https://private.invalid/signed",
                "empty": None,
                "unknown": "not in schema",
            }
        },
    )
    result = record_view(access, version, record)
    assert result["var"] == {"public": "safe", "empty": None}
    assert result["withheld_fields"] == ["url"]


def test_custom_validation_messages_cannot_echo_inputs_or_secrets():
    errors = validation_errors(
        [
            {
                "column": "var.score",
                "row_number": 3,
                "line_number": 4,
                "code": "range",
                "message": "private-token: abc",
                "input": "secret",
            },
            {
                "column": "secret-encoded-as-column",
                "code": "secret",
                "row_number": "secret",
            },
        ],
        {"score"},
    )
    assert errors[0]["column"] == "score" and errors[0]["code"] == "range"
    assert errors[0]["line_number"] == 4
    assert "secret" not in str(errors) and "abc" not in str(errors)
    assert safe_error(HTTPException(400, "private secret")) == {
        "code": "request_failed_use_platform"
    }


@pytest.mark.parametrize(
    "name,args",
    [
        (None, {}),
        ([], {}),
        ("get_protocol", {}),
        ("access_context", {"project_id": "other"}),
        ("execute_operation", {"operation_id": "one", "csv": "different"}),
    ],
)
def test_tool_schema_rejects_unknown_targets_and_extra_mutation_inputs(name, args):
    with pytest.raises(HTTPException):
        parse_args(name, args)
    assert tool_schema("execute_operation")["inputSchema"]["required"] == [
        "operation_id"
    ]


def test_streaming_body_limit_does_not_trust_content_length():
    async def scenario():
        app = FastAPI()
        app.add_middleware(ExternalRequestBoundary)

        @app.post("/mcp")
        async def endpoint():
            pytest.fail("Oversized input reached the application")

        async def chunks():
            for _ in range(3):
                yield b"x" * (MAX_EXTERNAL_BODY // 2)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post("/mcp", content=chunks())
            assert response.status_code == 413

    asyncio.run(scenario())
