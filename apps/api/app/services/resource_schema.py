"""Helpers for validating resource data against an AIMD Protocol Schema."""

from typing import Any


def resource_data_schema(schema: dict[str, Any]) -> Any:
    """Return the discipline-field Schema from a full AIMD Protocol Schema."""
    if "vars" in schema:
        return schema["vars"]
    if "research_variable" in schema:
        return schema["research_variable"]
    return schema
