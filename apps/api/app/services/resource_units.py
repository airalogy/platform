"""Exact, dimension-safe conversions for the inventory UCUM subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class UnitDefinition:
    canonical: str
    dimension: str
    factor: Decimal


_UNITS = {
    "kg": UnitDefinition("kg", "mass", Decimal("1000")),
    "g": UnitDefinition("g", "mass", Decimal("1")),
    "mg": UnitDefinition("mg", "mass", Decimal("0.001")),
    "ug": UnitDefinition("ug", "mass", Decimal("0.000001")),
    "ng": UnitDefinition("ng", "mass", Decimal("0.000000001")),
    "pg": UnitDefinition("pg", "mass", Decimal("0.000000000001")),
    "L": UnitDefinition("L", "volume", Decimal("1")),
    "mL": UnitDefinition("mL", "volume", Decimal("0.001")),
    "uL": UnitDefinition("uL", "volume", Decimal("0.000001")),
    "nL": UnitDefinition("nL", "volume", Decimal("0.000000001")),
    "mol": UnitDefinition("mol", "amount", Decimal("1")),
    "mmol": UnitDefinition("mmol", "amount", Decimal("0.001")),
    "umol": UnitDefinition("umol", "amount", Decimal("0.000001")),
    "nmol": UnitDefinition("nmol", "amount", Decimal("0.000000001")),
    "s": UnitDefinition("s", "time", Decimal("1")),
    "min": UnitDefinition("min", "time", Decimal("60")),
    "h": UnitDefinition("h", "time", Decimal("3600")),
    "d": UnitDefinition("d", "time", Decimal("86400")),
    "1": UnitDefinition("1", "count", Decimal("1")),
    "{count}": UnitDefinition("{count}", "count", Decimal("1")),
    "{item}": UnitDefinition("{item}", "count", Decimal("1")),
}
_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9{}\[\]./%*^+-]+$")


def normalize_ucum_unit(unit: str) -> str:
    normalized = str(unit).strip().replace("µ", "u").replace("μ", "u")
    if not normalized or not _UNIT_PATTERN.fullmatch(normalized):
        raise UnitError("unit must be a non-empty UCUM-compatible expression")
    return normalized


def decimal_quantity(value: object) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise UnitError("quantity must be an exact decimal number") from error
    if not quantity.is_finite() or quantity < 0:
        raise UnitError("quantity must be finite and non-negative")
    return quantity


def convert_quantity(value: object, source_unit: str, target_unit: str) -> Decimal:
    quantity = decimal_quantity(value)
    source = normalize_ucum_unit(source_unit)
    target = normalize_ucum_unit(target_unit)
    if source == target:
        return quantity
    source_definition = _UNITS.get(source)
    target_definition = _UNITS.get(target)
    if source_definition is None or target_definition is None:
        raise UnitError(
            f'conversion between "{source}" and "{target}" is not supported; '
            "use identical UCUM units or a supported base dimension"
        )
    if source_definition.dimension != target_definition.dimension:
        raise UnitError(
            f'cannot convert {source_definition.dimension} unit "{source}" '
            f'to {target_definition.dimension} unit "{target}"'
        )
    return quantity * source_definition.factor / target_definition.factor
