"""Bounded independent acceptance and current-state validation, without execution."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)

from app.models.instrument_package import InstrumentAdapterRelease
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.research_execution import ResearchInstrumentGateway
from app.models.resource import Resource


class QualificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal[
        "identity",
        "output",
        "completion",
        "parameter_readback",
        "safe_stop",
        "manual_takeover",
        "interlocks",
    ]
    method: str = Field(min_length=1, max_length=1000)
    expected: str = Field(min_length=1, max_length=1000)
    observed: str = Field(min_length=1, max_length=1000)
    passed: StrictBool


class CommandAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    key: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    checks: list[QualificationCheck] = Field(min_length=3, max_length=7)

    @model_validator(mode="after")
    def unique_checks(self):
        kinds = [check.kind for check in self.checks]
        if len(kinds) != len(set(kinds)) or not {
            "identity",
            "output",
            "completion",
        } <= set(kinds):
            raise ValueError(
                "Each command needs unique identity, output and completion checks"
            )
        return self


class QualificationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    identity_reference: str = Field(min_length=1, max_length=255)
    firmware: str = Field(min_length=1, max_length=255)
    application: str = Field(min_length=1, max_length=255)
    application_version: str = Field(min_length=1, max_length=255)
    driver_version: str = Field(min_length=1, max_length=255)
    os_version: str = Field(min_length=1, max_length=255)


class QualificationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    scope: Literal["simulation", "read_only", "controlled"]
    evidence_origin: Literal[
        "manual_observation", "independent_test", "package_self_test"
    ]
    target: QualificationTarget
    commands: list[CommandAssessment] = Field(min_length=1, max_length=10)
    evidence_file_ids: list[UUID] = Field(default_factory=list, max_length=8)
    assessed_at: AwareDatetime
    expires_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=2000)
    independent_review_confirmed: StrictBool = False
    physical_tests_authorized: StrictBool = False

    @model_validator(mode="after")
    def valid_assessment(self):
        commands = [(item.key, item.version) for item in self.commands]
        if len(commands) != len(set(commands)):
            raise ValueError("Qualification command versions must be unique")
        if len(self.evidence_file_ids) != len(set(self.evidence_file_ids)):
            raise ValueError("Qualification evidence files must be unique")
        if (
            not self.assessed_at
            < self.expires_at
            <= self.assessed_at + timedelta(days=365)
        ):
            raise ValueError(
                "Qualification expiry must follow assessment within 365 days"
            )
        if self.scope != "simulation":
            if self.evidence_origin == "package_self_test":
                raise ValueError("Package self-tests cannot qualify real equipment")
            if (
                not self.independent_review_confirmed
                or not self.physical_tests_authorized
            ):
                raise ValueError(
                    "Real equipment needs authorized tests and independent human review"
                )
        return self


def command_simulation_only(command):
    field = command["output_schema"].get("properties", {}).get("simulation_only")
    return isinstance(field, dict) and field.get("const") is True


def validate_command_assessments(draft, manifest):
    declared = {(item["key"], item["version"]): item for item in manifest["commands"]}
    selected = []
    for assessment in draft.commands:
        command = declared.get((assessment.key, assessment.version))
        if command is None:
            raise ValueError("Qualification must select exact package command versions")
        if draft.scope != "simulation" and command_simulation_only(command):
            raise ValueError("A simulation-only command cannot qualify real equipment")
        if draft.scope == "read_only" and command["risk"] != "read_only":
            raise ValueError(
                "Read-only qualification cannot include a state-changing command"
            )
        if draft.scope == "controlled" and command["risk"] != "read_only":
            kinds = {check.kind for check in assessment.checks}
            if (
                not {"parameter_readback", "safe_stop", "manual_takeover", "interlocks"}
                <= kinds
            ):
                raise ValueError(
                    "Controlled equipment needs readback, safe-stop, takeover and interlock checks"
                )
        selected.append(command)
    return selected


async def binding_invalid_reason(db, binding):
    if binding.state != "installed" or not binding.receipt:
        return "installation_not_current"
    gateway = await db.get(ResearchInstrumentGateway, binding.gateway_id)
    if (
        gateway is None
        or gateway.lab_id != binding.lab_id
        or gateway.revoked_at
        or gateway.token_digest != binding.gateway_credential_pin
    ):
        return "gateway_identity_changed"
    resource = await db.get(Resource, binding.resource_id)
    if (
        resource is None
        or resource.lab_id != binding.lab_id
        or resource.archived_at
        or resource.status != "active"
        or resource.current_revision_id != binding.resource_revision_id
    ):
        return "equipment_changed"
    release = await db.get(InstrumentAdapterRelease, binding.release_id)
    if (
        release is None
        or release.lab_id != binding.lab_id
        or release.state != "approved"
        or release.revision != binding.release_revision
        or release.archive_digest != binding.descriptor["archive_digest"]
        or release.manifest_digest != binding.descriptor["manifest_digest"]
    ):
        return "source_changed"
    file = await db.get(ResearchFile, release.research_file_id)
    if (
        file is None
        or file.archived_at
        or file.lab_id != binding.lab_id
        or file.scope_type != "lab"
    ):
        return "source_unavailable"
    return None


async def qualification_state(db, row, binding):
    if row.revoked_at:
        return "revoked"
    if row.outcome == "failed":
        return "failed"
    if row.expires_at <= datetime.now(UTC):
        return "expired"
    reason = await binding_invalid_reason(db, binding)
    if reason:
        return reason
    if (
        row.pins["descriptor"] != binding.descriptor
        or row.pins["receipt"] != binding.receipt
    ):
        return "installation_changed"
    for pin in row.evidence_files:
        file = await db.get(ResearchFile, UUID(pin["id"]))
        blob = await db.get(ResearchFileBlob, file.blob_id) if file else None
        if (
            file is None
            or file.archived_at
            or file.lab_id != binding.lab_id
            or file.scope_type != "lab"
            or blob is None
            or blob.checksum_sha256 != pin["sha256"]
        ):
            return "evidence_unavailable"
    return "simulation_only" if row.scope == "simulation" else "qualified"
