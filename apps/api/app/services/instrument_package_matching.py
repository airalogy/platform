"""Compare immutable package declarations, never infer device qualification."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.instrument_package_contract import SEMVER

# The query and comparison trim the same characters, including copied vendor
# metadata's nonbreaking/full-width spaces. Inner text and case stay literal.
MATCH_TRIM_CHARACTERS = (
    " \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)

COMBINATION_FIELDS = (
    "manufacturer",
    "model",
    "firmware",
    "application",
    "application_version",
    "os",
    "architecture",
)
RUNTIME_FIELDS = ("gateway_version", "python_version")
LiteralText = Annotated[str, Field(strict=True, min_length=1, max_length=256)]


def unresolved(value: str) -> bool:
    # These words are declarations, not supported wildcard/range syntax.
    return value.casefold() in {"*", "any", "all", "unknown", "unspecified"}


class AdapterTargetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: LiteralText
    model: LiteralText
    firmware: LiteralText | None = None
    application: LiteralText | None = None
    application_version: LiteralText | None = None
    os: LiteralText | None = None
    architecture: LiteralText | None = None
    gateway_version: LiteralText | None = None
    python_version: LiteralText | None = None

    @field_validator("*", mode="before")
    @classmethod
    def literal_text(cls, value):
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or len(value) > 256
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError(
                "Use bounded literal device metadata, not control characters"
            )
        normalized = value.strip(MATCH_TRIM_CHARACTERS)
        if not normalized or unresolved(normalized):
            raise ValueError(
                "Leave unknown optional fields empty; do not guess a wildcard"
            )
        return normalized

    @field_validator("gateway_version")
    @classmethod
    def exact_gateway(cls, value):
        if value is not None and not SEMVER.fullmatch(value):
            raise ValueError("Gateway version must be an exact SemVer")
        return value

    @field_validator("python_version")
    @classmethod
    def exact_python(cls, value):
        import re

        if value is not None and not re.fullmatch(r"3\.\d{1,2}", value):
            raise ValueError("Python version must be an exact major.minor version")
        return value


class AdapterMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: AdapterTargetProfile
    include_revoked: bool = Field(default=False, strict=True)


def compare_package(manifest: dict, profile: AdapterTargetProfile) -> dict:
    """Keep each declared combination intact; never mix fields across rows."""
    compatibility = manifest["compatibility"]
    target = profile.model_dump()
    combinations = []
    for index, combination in enumerate(compatibility["declared"]):
        if any(
            combination[field].strip(MATCH_TRIM_CHARACTERS) != target[field]
            for field in ("manufacturer", "model")
        ):
            continue
        checks = []
        for field in (*COMBINATION_FIELDS, *RUNTIME_FIELDS):
            declared = (
                compatibility[field + "s"]
                if field in RUNTIME_FIELDS
                else [combination[field]]
            )
            normalized = [item.strip(MATCH_TRIM_CHARACTERS) for item in declared]
            supplied = target[field]
            status = (
                "not_supplied"
                if supplied is None
                else "matches"
                if supplied in normalized and not unresolved(supplied)
                else "unresolved_declaration"
                if any(unresolved(item) for item in normalized)
                else "conflicts"
            )
            checks.append(
                {
                    "field": field,
                    "supplied": supplied,
                    "declared": declared,
                    "status": status,
                }
            )
        state = (
            "conflicts"
            if any(check["status"] == "conflicts" for check in checks)
            else "needs_information"
            if any(check["status"] != "matches" for check in checks)
            else "declaration_match"
        )
        combinations.append(
            {
                "combination_index": index,
                "status": state,
                "checks": checks,
                "test_declarations": [
                    item
                    for item in compatibility["tested"]
                    if item["combination_index"] == index
                ],
            }
        )
    best = next(
        (
            status
            for status in ("declaration_match", "needs_information", "conflicts")
            if any(item["status"] == status for item in combinations)
        ),
        "no_declared_model",
    )
    return {
        "status": best,
        "combinations": combinations,
        "hardware_authorized": False,
        "installation_authorized": False,
        "qualification_checked": False,
    }
