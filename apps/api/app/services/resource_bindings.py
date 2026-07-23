"""Extract and validate ResourceRef values from a Protocol Record."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .resource_units import UnitError, decimal_quantity, normalize_ucum_unit


class ResourceBindingError(ValueError):
    pass


@dataclass(frozen=True)
class ResourceFieldSpec:
    path: str
    role: str
    quantity_field: str | None
    container_required: bool
    booking_required: bool


@dataclass(frozen=True)
class ResourceBinding:
    field_path: str
    role: str
    value: dict[str, Any]
    quantity: Decimal | None
    unit: str | None
    container_required: bool
    booking_required: bool


def _item_value(item: object, key: str, default=None):
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _resource_specs(fields: Mapping[str, Any]) -> list[ResourceFieldSpec]:
    templates = fields.get("templates")
    source = templates if isinstance(templates, Mapping) else fields
    items = (
        source.get("var_definitions")
        or source.get("vars")
        or source.get("var")
        or []
    )
    specs: list[ResourceFieldSpec] = []

    def add(item: object, path: str) -> None:
        type_name = str(
            _item_value(item, "type", _item_value(item, "type_annotation", ""))
        )
        if "ResourceRef" not in type_name:
            return
        kwargs = _item_value(item, "kwargs", {})
        kwargs = kwargs if isinstance(kwargs, Mapping) else {}
        specs.append(
            ResourceFieldSpec(
                path=path,
                role=str(kwargs.get("resource_role") or "reference"),
                quantity_field=(
                    str(kwargs["quantity_field"])
                    if kwargs.get("quantity_field")
                    else None
                ),
                container_required=kwargs.get("container_required") is True,
                booking_required=kwargs.get("booking_required") is True,
            )
        )

    for item in items:
        field_id = _item_value(item, "id", _item_value(item, "name"))
        if isinstance(field_id, str):
            subvars = _item_value(item, "subvars", []) or []
            if subvars:
                for subvar in subvars:
                    subvar_id = _item_value(
                        subvar, "id", _item_value(subvar, "name")
                    )
                    if isinstance(subvar_id, str):
                        add(subvar, f"var.{field_id}.{subvar_id}")
            else:
                add(item, f"var.{field_id}")
    for table in source.get("var_table", []) or []:
        table_id = _item_value(table, "id", _item_value(table, "name"))
        if not isinstance(table_id, str):
            continue
        for item in _item_value(table, "subvars", []) or []:
            field_id = _item_value(item, "id", _item_value(item, "name"))
            if isinstance(field_id, str):
                add(item, f"var.{table_id}.{field_id}")
    return specs


def _read_path(data: Mapping[str, Any], path: str) -> Any:
    value: Any = data
    for segment in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(segment)
    return value


def _table_values(
    data: Mapping[str, Any], path: str
) -> Iterable[tuple[str, Any, Mapping[str, Any] | None]]:
    segments = path.split(".")
    if len(segments) != 3:
        yield path, _read_path(data, path), None
        return
    table = _read_path(data, ".".join(segments[:2]))
    if not isinstance(table, list):
        return
    for index, row in enumerate(table):
        if isinstance(row, Mapping):
            yield (
                f"{'.'.join(segments[:2])}.{index}.{segments[2]}",
                row.get(segments[2]),
                row,
            )


def extract_resource_bindings(
    fields: Mapping[str, Any],
    record_data: Mapping[str, Any],
) -> list[ResourceBinding]:
    bindings: list[ResourceBinding] = []
    for spec in _resource_specs(fields):
        for field_path, raw_value, table_row in _table_values(record_data, spec.path):
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for raw in values:
                if raw is None:
                    continue
                if not isinstance(raw, dict) or not str(raw.get("id") or "").strip():
                    raise ResourceBindingError(
                        f"{field_path} must contain a valid ResourceRef"
                    )
                if spec.container_required and not raw.get("container_id"):
                    raise ResourceBindingError(
                        f"{field_path} requires an inventory container"
                    )
                if spec.booking_required and not raw.get("booking_id"):
                    raise ResourceBindingError(
                        f"{field_path} requires an equipment booking"
                    )
                quantity_value = raw.get("quantity")
                if spec.quantity_field:
                    if table_row is not None:
                        local_name = spec.quantity_field.rsplit(".", 1)[-1]
                        quantity_value = table_row.get(local_name)
                    else:
                        quantity_path = spec.quantity_field
                        if not quantity_path.startswith("var."):
                            quantity_path = f"var.{quantity_path}"
                        quantity_value = _read_path(record_data, quantity_path)
                try:
                    quantity = (
                        decimal_quantity(quantity_value)
                        if quantity_value is not None
                        else None
                    )
                    unit = (
                        normalize_ucum_unit(str(raw["unit"]))
                        if raw.get("unit")
                        else None
                    )
                except UnitError as error:
                    raise ResourceBindingError(
                        f"{field_path}: {error}"
                    ) from error
                if quantity is not None and not unit:
                    raise ResourceBindingError(
                        f"{field_path} must declare a UCUM unit with quantity"
                    )
                bindings.append(
                    ResourceBinding(
                        field_path=field_path,
                        role=spec.role,
                        value=raw,
                        quantity=quantity,
                        unit=unit,
                        container_required=spec.container_required,
                        booking_required=spec.booking_required,
                    )
                )
    return bindings
