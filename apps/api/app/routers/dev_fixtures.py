import json
import os
import tomllib
from pathlib import Path, PurePosixPath
from typing import TypedDict

from airalogy.markdown import generate_model
from airalogy.record.hash import get_data_sha1
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User

try:
    from airalogy.examples.protocols import get_protocol_example
except ImportError:
    get_protocol_example = None

router = APIRouter(prefix="/dev/fixtures", tags=["dev-fixtures"])

DEV_PASSWORD = "AiralogyDev123!"
DEV_LAB_UID = "dev_lab"
DEV_PROJECT_UID = "quickstart"


class DevAccount(TypedDict):
    key: str
    role: str
    username: str
    name: str
    email: str


class DefaultProtocolExample(TypedDict):
    protocol_id: str
    example_id: str
    locale: str


DEFAULT_PROTOCOL_EXAMPLES: list[DefaultProtocolExample] = [
    {
        "protocol_id": "meeting_notes_en",
        "example_id": "meeting-notes",
        "locale": "en-US",
    },
    {
        "protocol_id": "diary",
        "example_id": "diary",
        "locale": "en-US",
    },
    {
        "protocol_id": "drug_response_ic50_en",
        "example_id": "drug-response-ic50",
        "locale": "en-US",
    },
    {
        "protocol_id": "plasmid_resource_definition_en",
        "example_id": "plasmid-resource-definition",
        "locale": "en-US",
    },
]


DEV_ACCOUNTS: list[DevAccount] = [
    {
        "key": "owner",
        "role": "Project owner",
        "username": "dev_owner",
        "name": "Dev Owner",
        "email": "dev.owner@airalogy.dev",
    },
    {
        "key": "collaborator",
        "role": "Collaborator",
        "username": "dev_collaborator",
        "name": "Dev Collaborator",
        "email": "dev.collaborator@airalogy.dev",
    },
    {
        "key": "viewer",
        "role": "Viewer",
        "username": "dev_viewer",
        "name": "Dev Viewer",
        "email": "dev.viewer@airalogy.dev",
    },
]


def ensure_development_mode() -> None:
    if config.APP_ENV == "production":
        raise HTTPException(status_code=404, detail="Not found")


def find_airalogy_protocol_examples_dir() -> tuple[Path | None, list[str]]:
    configured_dir = os.getenv("AIRALOGY_PROTOCOL_EXAMPLES_DIR")
    if configured_dir:
        path = Path(configured_dir).expanduser().resolve()
        if path.is_dir() and (path / "index.json").is_file():
            return path, []
        return None, [
            f"AIRALOGY_PROTOCOL_EXAMPLES_DIR is not an Airalogy examples/protocols directory: {path}"
        ]

    cwd = Path.cwd().resolve()
    candidates: list[Path] = []
    for root in [cwd, *cwd.parents]:
        candidates.extend(
            [
                root / "examples" / "protocols",
                root / "airalogy" / "examples" / "protocols",
                root.parent / "airalogy" / "examples" / "protocols",
            ]
        )

    for candidate in candidates:
        if (candidate / "index.json").is_file():
            return candidate, []

    return None, [
        (
            "Airalogy protocol examples were not found. Set "
            "AIRALOGY_PROTOCOL_EXAMPLES_DIR to an Airalogy examples/protocols directory."
        )
    ]


def load_protocol_example(example_root: Path, relative_dir: str) -> dict:
    protocol_dir = example_root / relative_dir
    toml_path = protocol_dir / "protocol.toml"
    aimd_path = protocol_dir / "protocol.aimd"
    if not toml_path.is_file() or not aimd_path.is_file():
        raise ValueError(f"Invalid Airalogy protocol example directory: {protocol_dir}")

    with toml_path.open("rb") as file:
        metadata = tomllib.load(file).get("airalogy_protocol")
    if not metadata:
        raise ValueError(f"Missing [airalogy_protocol] metadata in {toml_path}")

    return {
        "metadata": metadata,
        "aimd": aimd_path.read_text(encoding="utf-8"),
        "source_dir": str(protocol_dir),
    }


def load_protocol_examples_from_index(
    example_root: Path,
) -> tuple[list[dict], list[str]]:
    index_path = example_root / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"Invalid Airalogy protocol example index: {index_path}: {exc}"]

    examples = []
    warnings = []
    for entry in index.get("examples", []):
        for locale, aimd_path in entry.get("entry", {}).items():
            relative_dir = entry.get("protocol_dir", {}).get(locale)
            if relative_dir is None:
                relative_dir = str(PurePosixPath(aimd_path).parent)
            try:
                examples.append(load_protocol_example(example_root, relative_dir))
            except ValueError as exc:
                warnings.append(str(exc))

    if not examples:
        warnings.append(f"No protocol examples were loaded from {index_path}")

    return examples, warnings


def load_packaged_protocol_examples() -> tuple[list[dict], list[str]]:
    if get_protocol_example is None:
        return [], []

    examples = []
    warnings = []
    for protocol_example in DEFAULT_PROTOCOL_EXAMPLES:
        try:
            example = get_protocol_example(protocol_example["protocol_id"])
            examples.append(
                {
                    "metadata": example.load_metadata(),
                    "aimd": example.read_aimd(),
                    "source_dir": f"airalogy.examples.protocols:{example.directory}",
                }
            )
        except Exception as exc:
            warnings.append(
                "Could not load packaged Airalogy protocol example "
                f"{protocol_example['protocol_id']}: {exc}"
            )

    return examples, warnings


def load_default_protocol_examples() -> tuple[list[dict], list[str]]:
    if os.getenv("AIRALOGY_PROTOCOL_EXAMPLES_DIR"):
        example_root, warnings = find_airalogy_protocol_examples_dir()
        if example_root is None:
            return [], warnings
        examples, load_warnings = load_protocol_examples_from_index(example_root)
        return examples, [*warnings, *load_warnings]

    packaged_examples, packaged_warnings = load_packaged_protocol_examples()
    if packaged_examples:
        return packaged_examples, packaged_warnings

    example_root, warnings = find_airalogy_protocol_examples_dir()
    warnings.extend(packaged_warnings)
    if example_root is None:
        return [], warnings

    examples = []
    for protocol_example in DEFAULT_PROTOCOL_EXAMPLES:
        relative_dir = f"{protocol_example['example_id']}/{protocol_example['locale']}"
        try:
            examples.append(load_protocol_example(example_root, relative_dir))
        except ValueError as exc:
            warnings.append(str(exc))

    return examples, warnings


async def get_or_create_user(
    db_session: AsyncSession,
    account: DevAccount,
) -> User:
    user = await User.find_by(db_session, [User.email == account["email"]])
    if user is None:
        user = await User.find_by(db_session, [User.username == account["username"]])

    if user is None:
        user = User(
            username=account["username"],
            name=account["name"],
            email=account["email"],
            country_code="",
            phone="",
            password=DEV_PASSWORD,
            api_key_iv=os.urandom(16).hex(),
        )
        db_session.add(user)
        await db_session.flush()
    else:
        user.name = account["name"]
        user.email = account["email"]
        user.password = DEV_PASSWORD

    return user


async def ensure_lab_members(
    db_session: AsyncSession,
    lab: Lab,
    owner: User,
    users: list[tuple[DevAccount, User]],
) -> None:
    for account, user in users:
        role = LabRole.OWNER if user.id == owner.id else LabRole.MEMBER
        lab_user = await LabUser.find_by(
            db_session,
            [LabUser.lab_id == lab.id, LabUser.user_id == user.id],
        )
        if lab_user is None:
            lab_user = LabUser(
                lab_id=lab.id,
                user_id=user.id,
                role=role,
                create_user_id=owner.id,
            )
            db_session.add(lab_user)
        else:
            lab_user.role = role
            lab_user.create_user_id = owner.id

    lab.users_count = await LabUser.count(db_session, [LabUser.lab_id == lab.id])


async def ensure_project_members(
    db_session: AsyncSession,
    project: Project,
    owner: User,
    users: list[tuple[DevAccount, User]],
) -> None:
    role_by_key = {
        "owner": ProjectRole.OWNER,
        "collaborator": ProjectRole.COLLABORATOR,
        "viewer": ProjectRole.VIEWER,
    }
    for account, user in users:
        project_user = await ProjectUser.find_by(
            db_session,
            [ProjectUser.project_id == project.id, ProjectUser.user_id == user.id],
        )
        role = role_by_key[account["key"]]
        if project_user is None:
            project_user = ProjectUser(
                project_id=project.id,
                user_id=user.id,
                role=role,
                create_user_id=owner.id,
            )
            db_session.add(project_user)
        else:
            project_user.role = role
            project_user.create_user_id = owner.id


def protocol_schema(title: str, description: str) -> dict:
    return {
        "title": title,
        "description": description,
        "type": "object",
        "properties": {},
        "required": [],
    }


def empty_protocol_json_schema() -> dict:
    return {
        "research_variable": protocol_schema("Variables", "Protocol inputs"),
        "research_step": protocol_schema("Steps", "Protocol steps"),
        "research_check": protocol_schema("Checks", "Protocol checks"),
        "research_result": protocol_schema("Results", "Protocol results"),
    }


def empty_protocol_fields() -> dict:
    return {
        "research_variable": [],
        "research_step": [],
        "research_check": [],
        "research_result": [],
    }


def resource_definition_json_schema(aimd: str) -> dict:
    """Build the variable Schema shape produced by the Protocol executor."""
    namespace: dict = {}
    exec(
        compile(generate_model(aimd), "<development resource fixture>", "exec"),
        namespace,
    )
    return {
        "steps": {},
        "vars": namespace["VarModel"].model_json_schema(),
        "checks": {},
    }


async def ensure_protocols(
    db_session: AsyncSession,
    project: Project,
    owner: User,
) -> tuple[list[Protocol], list[str]]:
    protocols: list[Protocol] = []
    protocol_examples, warnings = load_default_protocol_examples()
    for protocol_data in protocol_examples:
        metadata = protocol_data["metadata"]
        uid = metadata["id"]
        version = metadata["version"]
        protocol = await Protocol.find_by(
            db_session,
            [
                Protocol.project_id == project.id,
                Protocol.uid == uid,
                Protocol.deleted_at.is_(None),
            ],
        )
        if protocol is None:
            protocol = Protocol(
                project_id=project.id,
                user_id=owner.id,
                uid=uid,
                name=metadata.get("name") or uid,
                kind=metadata.get("kind", "experiment"),
                latest_version=version,
                description=metadata.get("description"),
                disciplines=metadata.get("disciplines") or [],
                keywords=metadata.get("keywords") or [],
            )
            db_session.add(protocol)
            await db_session.flush()
        else:
            protocol.user_id = owner.id
            protocol.name = metadata.get("name") or uid
            protocol.kind = metadata.get("kind", "experiment")
            protocol.latest_version = version
            protocol.description = metadata.get("description")
            protocol.disciplines = metadata.get("disciplines") or []
            protocol.keywords = metadata.get("keywords") or []

        protocol_version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == version,
            ],
        )
        version_payload = {
            "json_schema": (
                resource_definition_json_schema(protocol_data["aimd"])
                if protocol.kind == "resource_definition"
                else empty_protocol_json_schema()
            ),
            "fields": empty_protocol_fields(),
            "assigners": {},
            "assigner_graph": {},
            "aimd": protocol_data["aimd"],
            "meta_data": metadata,
        }
        if protocol_version is None:
            protocol_version = ProtocolVersion(
                protocol_id=protocol.id,
                version=version,
                **version_payload,
            )
            db_session.add(protocol_version)
        else:
            for key, value in version_payload.items():
                setattr(protocol_version, key, value)

        protocols.append(protocol)

    return protocols, warnings


async def ensure_schema_governance_fixture(
    db_session: AsyncSession,
    project: Project,
    owner: User,
) -> tuple[Protocol, Record]:
    """Create an old Record plus a newer Protocol version for browser testing."""
    uid = "schema_governance_e2e"
    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.project_id == project.id,
            Protocol.uid == uid,
            Protocol.deleted_at.is_(None),
        ],
    )
    if protocol is None:
        protocol = Protocol(
            project_id=project.id,
            user_id=owner.id,
            uid=uid,
            name="Schema Governance E2E",
            kind="experiment",
            latest_version="2.0.0",
            description="Development fixture for cross-version Record governance.",
        )
        db_session.add(protocol)
        await db_session.flush()
    else:
        protocol.user_id = owner.id
        protocol.name = "Schema Governance E2E"
        protocol.kind = "experiment"
        protocol.latest_version = "2.0.0"

    source_schema = {
        "type": "object",
        "properties": {
            "var": {
                "type": "object",
                "properties": {"old_name": {"type": "string"}},
            }
        },
    }
    target_schema = {
        "type": "object",
        "properties": {
            "var": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "new_measurement": {"type": ["number", "null"]},
                },
            }
        },
    }
    manifest = {
        "version": "airalogy.migration.v1",
        "from": "1.0.0",
        "to": "2.0.0",
        "operations": [{"op": "rename", "from": "var.old_name", "to": "var.name"}],
    }
    version_payloads = {
        "1.0.0": {
            "json_schema": source_schema,
            "aimd": "# Schema Governance E2E\n\nLegacy sample record.",
            "migration_manifest": None,
        },
        "2.0.0": {
            "json_schema": target_schema,
            "aimd": "# Schema Governance E2E\n\nCurrent sample record.",
            "migration_manifest": manifest,
        },
    }
    for version, payload in version_payloads.items():
        protocol_version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == version,
            ],
        )
        values = {
            "meta_data": {
                "id": uid,
                "version": version,
                "kind": "experiment",
                "name": protocol.name,
            },
            "json_schema": payload["json_schema"],
            "fields": empty_protocol_fields(),
            "assigners": {},
            "assigner_graph": {},
            "aimd": payload["aimd"],
            "migration_manifest": payload["migration_manifest"],
        }
        if protocol_version is None:
            db_session.add(
                ProtocolVersion(
                    protocol_id=protocol.id,
                    version=version,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(protocol_version, key, value)

    record = await Record.find_by(
        db_session,
        [
            Record.protocol_id == protocol.id,
            Record.version == 1,
            Record.deleted_at.is_(None),
        ],
    )
    data = {"var": {"old_name": "Legacy E2E sample"}, "step": {}, "check": {}}
    if record is None:
        record = Record(
            protocol_id=protocol.id,
            protocol_version="1.0.0",
            user_id=owner.id,
            data=data,
            report="# Legacy E2E sample",
            number=1,
            version=1,
            hash=get_data_sha1({"data": data}),
            revision_kind="initial",
            revision_reason="",
        )
        db_session.add(record)
        await db_session.flush()
    return protocol, record


async def ensure_analysis_fixture(
    db_session: DBSession, project: Project, owner: User
) -> Protocol:
    """Known numerical inputs for real browser analysis; no model or instruments."""
    uid = "record_analysis_e2e"
    protocol = await Protocol.find_by(
        db_session, [Protocol.project_id == project.id, Protocol.uid == uid]
    )
    if protocol is not None:
        return protocol
    protocol = Protocol(
        project_id=project.id,
        user_id=owner.id,
        uid=uid,
        name="Synthetic Record Analysis",
        latest_version="1.0.0",
        description="Development-only known-value analysis fixture.",
    )
    db_session.add(protocol)
    await db_session.flush()
    db_session.add(
        ProtocolVersion(
            protocol_id=protocol.id,
            version="1.0.0",
            meta_data={"id": uid, "version": "1.0.0", "name": protocol.name},
            json_schema={
                "vars": {
                    "type": "object",
                    "properties": {
                        "measurement": {
                            "type": "number",
                            "title": "Measurement",
                            "unit": "mg/L",
                        },
                        "group": {"type": "string", "title": "Group"},
                    },
                }
            },
            fields={"vars": ["measurement", "group"]},
            assigners={},
            assigner_graph={},
            aimd="# Synthetic measurement\n\n{{var|measurement: float}}\n\n{{var|group: str}}",
        )
    )
    for number in range(1, 13):
        data = {
            "var": {
                "measurement": number * 2,
                "group": "control" if number <= 6 else "treatment",
            },
            "step": {},
            "check": {},
        }
        db_session.add(
            Record(
                protocol_id=protocol.id,
                protocol_version="1.0.0",
                user_id=owner.id,
                number=number,
                version=1,
                data=data,
                report=f"Synthetic sample {number}",
                hash=get_data_sha1({"data": data}),
            )
        )
    await db_session.flush()
    return protocol


async def ensure_workflow_compute_fixture(db, project, owner, protocol):
    """Synthetic UI fixtures only: no successful run, device or runnable token."""
    from decimal import Decimal
    from secrets import token_hex

    from sqlalchemy import select

    from app.models.analysis import AnalysisPipeline, AnalysisPipelineRevision
    from app.models.research_execution import (
        ResearchComputeEnvironment,
        ResearchComputeEnvironmentRevision,
        ResearchComputeRunner,
        ResearchComputeRunnerEnvironment,
    )
    from app.services.analysis_compute_contracts import (
        ANALYSIS_JOB_SCHEMA,
        COMPUTE_ENGINE_VERSION,
        AnalysisComputeRecipe,
    )
    from app.services.analysis_engine import canonical_digest
    from app.services.record_analyses import AnalysisSelection, method_revision_digest

    environment = await db.scalar(
        select(ResearchComputeEnvironment).where(
            ResearchComputeEnvironment.lab_id == project.lab_id,
            ResearchComputeEnvironment.environment_key == "workflow-compute-e2e",
        )
    )
    if environment is None:
        environment = ResearchComputeEnvironment(
            lab_id=project.lab_id,
            environment_key="workflow-compute-e2e",
            created_by_user_id=owner.id,
        )
        db.add(environment)
        await db.flush()
        for number in (1, 2):
            db.add(
                ResearchComputeEnvironmentRevision(
                    compute_environment_id=environment.id,
                    revision=number,
                    name="Synthetic Workflow Python",
                    enabled=True,
                    description="UI fixture only; not an executable research environment.",
                    image_ref="synthetic.example.test/python@sha256:"
                    + str(number) * 64,
                    runtime_version="synthetic-python-3.13",
                    allowed_languages=["python"],
                    resource_limits={
                        "cpu_millis": 1000,
                        "gpu_count": 0,
                        "memory_mb": 256,
                        "timeout_seconds": 60,
                        "max_output_bytes": 65536,
                    },
                    network_policy="none",
                    allowed_egress_hosts=[],
                    software_manifest={},
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    result_schema={
                        "type": "object",
                        "properties": {"mean": {"type": "number", "unit": "mg/L"}},
                        "required": ["mean"],
                        "additionalProperties": False,
                    },
                    estimated_cost_per_hour=Decimal("6"),
                    currency="USD",
                    created_by_user_id=owner.id,
                )
            )
        await db.flush()
        revision = await db.scalar(
            select(ResearchComputeEnvironmentRevision).where(
                ResearchComputeEnvironmentRevision.compute_environment_id
                == environment.id,
                ResearchComputeEnvironmentRevision.revision == 1,
            )
        )
        runner = ResearchComputeRunner(
            lab_id=project.lab_id,
            name="Synthetic offline UI fixture — no execution",
            token_digest=token_hex(32),
            token_hint="synthetic",
            last_report={
                "protocol_version": "airalogy.compute-runner.v1",
                "job_schemas": [ANALYSIS_JOB_SCHEMA],
            },
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        )
        db.add(runner)
        await db.flush()
        db.add(
            ResearchComputeRunnerEnvironment(
                runner_id=runner.id,
                lab_id=project.lab_id,
                compute_environment_id=environment.id,
                compute_environment_revision_id=revision.id,
                created_by_user_id=owner.id,
            )
        )
    revision = await db.scalar(
        select(ResearchComputeEnvironmentRevision).where(
            ResearchComputeEnvironmentRevision.compute_environment_id == environment.id,
            ResearchComputeEnvironmentRevision.revision == 1,
        )
    )
    title = "Synthetic Workflow Python method (not executed)"
    pipeline = await db.scalar(
        select(AnalysisPipeline).where(
            AnalysisPipeline.protocol_id == protocol.id,
            AnalysisPipeline.created_by_user_id == owner.id,
            AnalysisPipeline.title == title,
        )
    )
    if pipeline is None:
        pipeline = AnalysisPipeline(
            project_id=project.id,
            protocol_id=protocol.id,
            created_by_user_id=owner.id,
            title=title,
            current_revision=1,
        )
        db.add(pipeline)
        await db.flush()
        recipe = AnalysisComputeRecipe(
            kind="compute",
            environment_revision_id=revision.id,
            language="python",
            source_code="import json, os, statistics\nfrom pathlib import Path\nsource = json.loads((Path(os.environ['AIRALOGY_INPUT_DIR']) / 'records.json').read_text())\nvalues = [row['data']['var']['measurement'] for row in source['records']]\nmean = statistics.mean(values)\nPath(os.environ['AIRALOGY_RESULT_JSON']).write_text(json.dumps({'mean': mean}))\n(Path(os.environ['AIRALOGY_RESULT_JSON']).parent / 'files' / 'summary.csv').write_text('mean\\n' + str(mean) + '\\n')\n",
            parameters={},
            output_files=[
                {
                    "mount_name": "summary.csv",
                    "asset_name": "Synthetic summary CSV",
                    "media_type": "text/csv",
                    "max_bytes": 4096,
                    "required": True,
                }
            ],
        ).model_dump(mode="json")
        selection = AnalysisSelection().model_dump(mode="json", exclude_none=True)
        provenance = {
            "engine_version": COMPUTE_ENGINE_VERSION,
            "synthetic_ui_fixture": True,
        }
        provenance["method_digest"] = method_revision_digest(
            recipe, selection, provenance
        )
        db.add(
            AnalysisPipelineRevision(
                pipeline_id=pipeline.id,
                revision=1,
                recipe=recipe,
                recipe_digest=canonical_digest(recipe),
                source_selection=selection,
                provenance=provenance,
                created_by_user_id=owner.id,
            )
        )
    version = await db.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == "1.0.0",
        )
    )
    await db.flush()
    return {
        "pipeline_id": str(pipeline.id),
        "pipeline_title": title,
        "environment_id": str(environment.id),
        "environment_revision_id": str(revision.id),
        "environment_name": revision.name,
        "protocol_id": str(protocol.id),
        "protocol_version_id": str(version.id),
    }


async def ensure_workflow_file_fixture(db, project, owner):
    """Real small managed file and submitted Record; no execution is fabricated."""
    import hashlib
    from io import BytesIO

    from sqlalchemy import select

    from app.models.airalogy_file import AiralogyFile

    uid = "workflow_files_e2e"
    protocol = await Protocol.find_by(
        db, [Protocol.project_id == project.id, Protocol.uid == uid]
    )
    if protocol is None:
        protocol = Protocol(
            project_id=project.id,
            user_id=owner.id,
            uid=uid,
            name="Synthetic Workflow Files",
            latest_version="1.0.0",
            description="Development-only managed file binding fixture.",
        )
        db.add(protocol)
        await db.flush()
        db.add(
            ProtocolVersion(
                protocol_id=protocol.id,
                version="1.0.0",
                meta_data={"id": uid, "version": "1.0.0", "name": protocol.name},
                json_schema={
                    "vars": {
                        "type": "object",
                        "properties": {
                            "attachment": {
                                "type": "string",
                                "airalogy_type": "FileId",
                                "file_extension": "csv",
                                "title": "CSV attachment",
                            },
                        },
                        "required": ["attachment"],
                    }
                },
                fields={"vars": ["attachment"]},
                assigners={},
                assigner_graph={},
                aimd="# Synthetic Workflow Files\n\n{{var|attachment: FileIdCSV}}",
            )
        )
        content = b"sample,measurement\nsynthetic-a,2\nsynthetic-b,4\n"
        file = AiralogyFile(
            filename="synthetic-measurements.csv",
            content_type="text/csv",
            protocol_id=protocol.id,
            project_id=project.id,
            user_id=owner.id,
        )
        db.add(file)
        await db.flush()
        await file.save_file(
            BytesIO(content),
            content_type="text/csv",
            length=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )
        data = {"var": {"attachment": file.airalogy_id}, "step": {}, "check": {}}
        db.add(
            Record(
                protocol_id=protocol.id,
                protocol_version="1.0.0",
                user_id=owner.id,
                number=1,
                version=1,
                data=data,
                hash=get_data_sha1({"data": data}),
                report="Synthetic managed CSV, not a Workflow execution.",
            )
        )
        await db.flush()
    version = await db.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == "1.0.0",
        )
    )
    record = await db.scalar(
        select(Record).where(
            Record.protocol_id == protocol.id, Record.number == 1, Record.version == 1
        )
    )
    return {
        "protocol_id": str(protocol.id),
        "protocol_uid": protocol.uid,
        "protocol_version_id": str(version.id),
        "record_id": str(record.id),
        "record_version": record.version,
        "file_ref": record.data["var"]["attachment"],
        "field": "attachment",
    }


@router.post("/quickstart")
async def ensure_quickstart_fixtures(db_session: DBSession):
    ensure_development_mode()

    users = [
        (account, await get_or_create_user(db_session, account))
        for account in DEV_ACCOUNTS
    ]
    owner = users[0][1]

    lab = await Lab.find_by(db_session, [Lab.uid == DEV_LAB_UID])
    if lab is None:
        lab = Lab(
            uid=DEV_LAB_UID,
            name="Dev Demo Lab",
            create_user_id=owner.id,
            description="Development-only lab for quick local testing.",
        )
        db_session.add(lab)
        await db_session.flush()
    else:
        lab.name = "Dev Demo Lab"
        lab.create_user_id = owner.id
        lab.description = "Development-only lab for quick local testing."

    await ensure_lab_members(db_session, lab, owner, users)

    project = await Project.find_by(
        db_session,
        [
            Project.lab_id == lab.id,
            Project.uid == DEV_PROJECT_UID,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        project = Project(
            lab_id=lab.id,
            uid=DEV_PROJECT_UID,
            name="Quickstart Protocol Testing",
            description="Development-only project with Airalogy example protocols.",
            type=ProjectType.PUBLIC,
            public_access_role=ProjectRole.EXPLORER,
            create_user_id=owner.id,
        )
        db_session.add(project)
        await db_session.flush()
    else:
        project.name = "Quickstart Protocol Testing"
        project.description = (
            "Development-only project with Airalogy example protocols."
        )
        project.type = ProjectType.PUBLIC
        project.public_access_role = ProjectRole.EXPLORER
        project.create_user_id = owner.id

    await ensure_project_members(db_session, project, owner, users)

    protocols, warnings = await ensure_protocols(db_session, project, owner)
    governance_protocol, governance_record = await ensure_schema_governance_fixture(
        db_session,
        project,
        owner,
    )
    analysis_protocol = await ensure_analysis_fixture(db_session, project, owner)
    workflow_compute = await ensure_workflow_compute_fixture(
        db_session, project, owner, analysis_protocol
    )
    workflow_files = await ensure_workflow_file_fixture(db_session, project, owner)
    lab.projects_count = await Project.count(
        db_session,
        [Project.lab_id == lab.id, Project.deleted_at.is_(None)],
    )

    await db_session.commit()

    return {
        "accounts": [
            {
                "key": account["key"],
                "role": account["role"],
                "name": account["name"],
                "email": account["email"],
                "password": DEV_PASSWORD,
            }
            for account, _user in users
        ],
        "lab": {
            "id": str(lab.id),
            "uid": lab.uid,
            "name": lab.name,
        },
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
            "lab_uid": lab.uid,
        },
        "protocols": [
            {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "kind": protocol.kind,
                "latest_version": protocol.latest_version,
            }
            for protocol in protocols
        ],
        "schema_governance": {
            "protocol_id": str(governance_protocol.id),
            "protocol_uid": governance_protocol.uid,
            "source_version": governance_record.protocol_version,
            "target_version": governance_protocol.latest_version,
            "record_id": str(governance_record.id),
            "record_version": governance_record.version,
        },
        "analysis": {
            "protocol_id": str(analysis_protocol.id),
            "protocol_uid": analysis_protocol.uid,
        },
        "workflow_compute": workflow_compute,
        "workflow_files": workflow_files,
        "warnings": warnings,
    }
