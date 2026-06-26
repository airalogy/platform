import json
import os
import tomllib
from pathlib import Path
from pathlib import PurePosixPath
from typing import TypedDict

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
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


def load_protocol_examples_from_index(example_root: Path) -> tuple[list[dict], list[str]]:
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
            "json_schema": empty_protocol_json_schema(),
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
        project.description = "Development-only project with Airalogy example protocols."
        project.type = ProjectType.PUBLIC
        project.public_access_role = ProjectRole.EXPLORER
        project.create_user_id = owner.id

    await ensure_project_members(db_session, project, owner, users)

    protocols, warnings = await ensure_protocols(db_session, project, owner)
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
                "latest_version": protocol.latest_version,
            }
            for protocol in protocols
        ],
        "warnings": warnings,
    }
