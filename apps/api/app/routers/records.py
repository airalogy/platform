import os
import tempfile
import uuid
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Literal

from airalogy.record.hash import get_data_sha1
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import cast, distinct, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.config import config
from app.database import DBSession
from app.libs.protocol_agent import prepare_protocol_package, protocol_exec
from app.libs.text_splitter import text_to_words
from app.models.lab import Lab
from app.models.project import Project, ProjectRole, ProjectType
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User
from app.routers.permission import check_user_permission
from app.routers.utils import UUID

from .depends import CurrentUser, OptionalCurrentUser

router = APIRouter(
    prefix="/protocols/{protocol_id}/records",
    tags=["records"],
)

SEARCH_CONFIG = literal_column("'english'")


def build_record_search_document():
    return func.record_search_document(
        cast(Record.data, JSONB),
        Record.report,
    )


def build_record_keyword_condition(q: str | None):
    if q is None:
        return None

    keyword = q.strip()
    if not keyword:
        return None

    qs = " & ".join(text_to_words(q.lower()))
    search_document = build_record_search_document()
    search_query = func.to_tsquery(SEARCH_CONFIG, qs)

    return func.to_tsvector(
        SEARCH_CONFIG,
        search_document,
    ).bool_op("@@")(
        search_query,
    )


class VarAssignParams(BaseModel):
    var_name: str
    dependent_data: dict[str, Any]


@router.post("/var_assign")
async def protocol_var_assign(
    protocol_id: UUID,
    data: VarAssignParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    protocol = await Protocol.find(db_session, id=protocol_id)

    project = await Project.find(db_session, id=protocol.project_id)
    lab = await Lab.find(db_session, id=project.lab_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="exec_assigner",
    )
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol package not found")

    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid

    env_vars = {}
    if protocol.env_vars is not None:
        env_vars = dotenv_values(stream=StringIO(protocol.env_vars))
    env_vars.update(
        {
            "AIRALOGY_ENDPOINT": config.AIRALOGY_ENDPOINT,
            "AIRALOGY_API_KEY": current_user.api_key,
            "AIRALOGY_PROTOCOL_ID": f"airalogy.id.protocol.{protocol.id}",
        }
    )

    assign_params = data.model_dump()
    assign_params.update({"env_vars": env_vars})
    await prepare_protocol_package(protocol_version)
    res = await protocol_exec(
        "var_assign", protocol_version.package_name, assign_params
    )
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])
    return res["data"]


class RecordValidateParams(BaseModel):
    var: Dict[str, Any] | None = None


@router.post("/validate")
async def protocol_record_validate(
    protocol_id: UUID,
    data: RecordValidateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
    )
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol package not found")
    await prepare_protocol_package(protocol_version)
    res = await protocol_exec("var_validate", protocol_version.package_name, data.var)
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])
    return res["data"]


class RecordQueryParams(BaseModel):
    user_id: UUID | None = None
    protocol_version: str | None = None
    number: int | None = None
    version: int | None = None
    q: str | None = None


@router.get("")
async def get_protocol_records(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    params=Depends(RecordQueryParams),
    page: int = 1,
    page_size: int = 10,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    user_role = await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_record",
        protocol=protocol,
    )
    lab: Lab = await Lab.find(db_session, id=project.lab_id)
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid

    # some roles can only read their own records
    if (
        current_user is not None
        and project.type == ProjectType.PRIVATE
        and user_role == ProjectRole.RECORDER
    ):
        params.user_id = current_user.id
    if (
        current_user is not None
        and project.type == ProjectType.PUBLIC
        and user_role
        in [
            ProjectRole.RECORDER_SELF_ONLY,
            ProjectRole.EXPLORER_SELF_ONLY,
        ]
    ):
        params.user_id = current_user.id

    payload = params.model_dump(exclude_none=True, exclude={"q"})
    conditions = Record.conditions_from_dict(payload)
    conditions.append(Record.protocol_id == protocol_id)
    conditions.append(Record.deleted_at.is_(None))
    keyword_condition = build_record_keyword_condition(params.q)
    if keyword_condition is not None:
        conditions.append(keyword_condition)
    count_query = (
        select(func.count(distinct(Record.id))).select_from(Record).where(*conditions)
    )
    total_count = await db_session.scalar(count_query)

    sub_query = (
        select(
            Record,
            func.row_number()
            .over(
                partition_by=Record.id,
                order_by=Record.version.desc(),
            )
            .label("row_number"),
        )
        .where(*conditions)
        .subquery()
    )

    query = (
        select(
            sub_query,
            User.username.label("username"),
        )
        .join(User, User.id == sub_query.c.user_id)
        .where(sub_query.c.row_number == 1)
        .order_by(sub_query.c.number.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = (await db_session.execute(query)).all()
    records = []

    for row in result:
        row_dict = row._asdict()
        row_dict.pop("row_number")
        username = row_dict.pop("username")
        record = Record(**row_dict)
        if record.version > 1:
            init_record = await Record.find_by(
                db_session,
                [
                    Record.id == record.id,
                    Record.version == 1,
                ],
            )
        else:
            init_record = record
        records.append(
            {
                "airalogy_record_id": record.airalogy_id,
                "record_id": record.id,
                "record_version": record.version,
                "metadata": {
                    "airalogy_protocol_id": protocol.airalogy_id,
                    "protocol_id": protocol.uid,
                    "protocol_uuid": record.protocol_id,
                    "protocol_version": record.protocol_version,
                    "record_current_version_submission_time": record.created_at,
                    "record_current_version_submission_user_id": username,
                    "record_initial_version_submission_time": init_record.created_at,
                    "record_initial_version_submission_user_id": username,
                    "lab_id": lab.uid,
                    "project_id": project.uid,
                    "record_num": record.number,
                    "sha1": record.hash,
                },
                "data": record.data,
            }
        )

    return {
        "records": records,
        "total_count": total_count,
    }


class RecordCreateParams(BaseModel):
    step: Dict[str, Any]
    var: Dict[str, Any]
    check: Dict[str, Any]
    report: str


def _serialize_import_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "row_number": error.get("row_number"),
            "column": error.get("column"),
            "message": error.get("message") or "Invalid row data",
        }
        for error in errors
    ]


def _raise_import_errors(errors: list[dict[str, Any]]):
    raise HTTPException(
        status_code=400,
        detail={
            "message": "Record import failed",
            "errors": _serialize_import_errors(errors),
        },
    )


def _record_data_from_imported_record(
    imported_record: dict[str, Any],
    protocol_version: ProtocolVersion,
) -> dict[str, Any]:
    data = imported_record.get("data")
    if not isinstance(data, dict):
        data = {}

    data.setdefault("step", {})
    data.setdefault("var", {})
    data.setdefault("check", {})

    for key, schema in protocol_version.json_schema["vars"]["properties"].items():
        if schema.get("airalogy_type") == "IgnoreStr":
            data["var"][key] = ""

    return data


@router.post("/import")
async def import_protocol_records(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    input_format: Literal["auto", "csv", "tsv", "json", "jsonl"] = Form("auto"),
    allow_extra_var_fields: bool = Form(False),
    require_complete_quiz: bool = Form(False),
    include_template_defaults: bool = Form(True),
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")

    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
        protocol=protocol,
    )

    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol package not found")

    await prepare_protocol_package(protocol_version)

    package_dir = Path(config.PROTOCOL_DIR) / protocol_version.package_name
    if not package_dir.is_dir():
        raise HTTPException(status_code=400, detail="Protocol package not found")

    env_vars = {}
    if protocol.env_vars is not None:
        env_vars = dotenv_values(stream=StringIO(protocol.env_vars))
    env_vars.update(
        {
            "AIRALOGY_ENDPOINT": config.AIRALOGY_ENDPOINT,
            "AIRALOGY_API_KEY": current_user.api_key,
            "AIRALOGY_PROTOCOL_ID": f"airalogy.id.protocol.{protocol.id}",
        }
    )

    suffix = Path(file.filename or "").suffix.lower()
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=package_dir,
            prefix="record_import_",
            suffix=suffix,
            delete=False,
        ) as tmp_file:
            tmp_path = tmp_file.name
            while chunk := await file.read(1024 * 1024):
                tmp_file.write(chunk)

        input_filename = os.path.basename(tmp_path)
        res = await protocol_exec(
            "import_records",
            protocol_version.package_name,
            {
                "input_filename": input_filename,
                "input_format": input_format,
                "allow_extra_var_fields": allow_extra_var_fields,
                "require_complete_quiz": require_complete_quiz,
                "include_template_defaults": include_template_defaults,
                "env_vars": env_vars,
            },
        )
    finally:
        await file.close()
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])

    import_data = res["data"]
    import_errors = import_data.get("errors") or []
    if import_errors:
        _raise_import_errors(import_errors)

    imported_records = import_data.get("records") or []
    if not imported_records:
        raise HTTPException(status_code=400, detail="No records found in import file")

    normalized_record_ids: list[uuid.UUID] = []
    validation_errors: list[dict[str, Any]] = []
    seen_record_ids: dict[uuid.UUID, int] = {}

    for row_number, imported_record in enumerate(imported_records, start=1):
        record_version = imported_record.get("record_version", 1)
        if record_version != 1:
            validation_errors.append(
                {
                    "row_number": row_number,
                    "column": "record_version",
                    "message": "Bulk upload only supports new records with record_version 1.",
                }
            )

        try:
            record_id = uuid.UUID(str(imported_record.get("record_id")))
        except (TypeError, ValueError):
            validation_errors.append(
                {
                    "row_number": row_number,
                    "column": "record_id",
                    "message": "record_id must be a valid UUID.",
                }
            )
            continue

        if record_id in seen_record_ids:
            validation_errors.append(
                {
                    "row_number": row_number,
                    "column": "record_id",
                    "message": f"Duplicate record_id also appears in row {seen_record_ids[record_id]}.",
                }
            )
            continue

        seen_record_ids[record_id] = row_number
        normalized_record_ids.append(record_id)

    if normalized_record_ids:
        existing_record_ids = (
            await db_session.scalars(
                select(Record.id).where(Record.id.in_(normalized_record_ids))
            )
        ).all()
        for existing_id in existing_record_ids:
            validation_errors.append(
                {
                    "row_number": seen_record_ids.get(existing_id),
                    "column": "record_id",
                    "message": "record_id already exists.",
                }
            )

    if validation_errors:
        _raise_import_errors(validation_errors)

    latest_number = await db_session.scalar(
        select(func.max(Record.number)).where(Record.protocol_id == protocol_id)
    )
    next_number = (latest_number or 0) + 1

    created_records: list[Record] = []
    for offset, imported_record in enumerate(imported_records):
        data = _record_data_from_imported_record(imported_record, protocol_version)
        record = Record(
            id=normalized_record_ids[offset],
            protocol_id=protocol_id,
            protocol_version=protocol_version.version,
            user_id=current_user.id,
            data=data,
            report="",
            number=next_number + offset,
            version=1,
            hash=get_data_sha1({"data": data}),
        )
        db_session.add(record)
        created_records.append(record)

    await db_session.commit()
    return {
        "imported_count": len(created_records),
        "record_ids": [str(record.id) for record in created_records],
    }


@router.post("")
async def create_protocol_record(
    protocol_id: UUID,
    params: RecordCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
        protocol=protocol,
    )

    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol package not found")
    await prepare_protocol_package(protocol_version)
    res = await protocol_exec("var_validate", protocol_version.package_name, params.var)
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])
    data = res["data"]
    if data.get("errors") is not None:
        raise HTTPException(
            status_code=400,
            detail={"message": "validate error", "errors": data["errors"]},
        )
    last_records = await Record.all(
        db_session,
        [Record.protocol_id == protocol_id],
        page=1,
        page_size=1,
        order_by=Record.created_at.desc(),
    )

    number = last_records[0].number + 1 if len(last_records) > 0 else 1
    data = {
        "step": params.step,
        "var": params.var,
        "check": params.check,
    }
    # set ignore str to empty string
    for k, v in protocol_version.json_schema["vars"]["properties"].items():
        if v.get("airalogy_type") == "IgnoreStr":
            data["var"][k] = ""

    record = Record(
        protocol_id=protocol_id,
        protocol_version=protocol_version.version,
        user_id=current_user.id,
        data=data,
        report=params.report,
        number=number,
        version=1,
        hash=get_data_sha1({"data": data}),
    )
    db_session.add(record)
    await db_session.commit()
    return record


@router.put("/{id}")
async def update_protocol_record(
    protocol_id: UUID,
    id: UUID,
    params: RecordCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _stmt = (
        select(Record)
        .where(Record.id == id, Record.protocol_id == protocol_id)
        .order_by(Record.version.desc())
        .with_for_update()
        .limit(1)
    )
    record = (await db_session.execute(_stmt)).scalar()
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
        protocol=protocol,
        record=record,
    )

    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol package not found")
    await prepare_protocol_package(protocol_version)
    res = await protocol_exec("var_validate", protocol_version.package_name, params.var)
    if res["success"] is False:
        raise HTTPException(status_code=400, detail=res["message"])
    data = res["data"]
    if data.get("errors") is not None:
        raise HTTPException(
            status_code=400,
            detail={"message": "validate error", "errors": data["errors"]},
        )

    data = {
        "step": params.step,
        "var": params.var,
        "check": params.check,
    }
    # set ignore str to empty string
    for k, v in protocol_version.json_schema["vars"]["properties"].items():
        if v.get("airalogy_type") == "IgnoreStr":
            data["var"][k] = ""

    new_record = Record(
        id=record.id,
        protocol_id=protocol_id,
        protocol_version=protocol_version.version,
        user_id=current_user.id,
        data=data,
        report=params.report,
        number=record.number,
        version=record.version + 1,
        hash=get_data_sha1({"data": data}),
    )
    db_session.add(new_record)
    await db_session.commit()
    return new_record


@router.get("/{id}")
async def get_record(
    protocol_id: UUID,
    id: UUID,
    version: int,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
):
    record = await Record.find_by(
        db_session,
        [
            Record.id == id,
            Record.protocol_id == protocol_id,
            Record.version == version,
        ],
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    protocol = await Protocol.find(db_session, id=record.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_record",
        protocol=protocol,
        record=record,
    )

    if record.version > 1:
        init_record = await Record.find_by(
            db_session,
            [
                Record.id == record.id,
                Record.version == 1,
            ],
        )
    else:
        init_record = record
    user = await User.find(db_session, id=record.user_id)
    project: Project = await Project.find(db_session, id=protocol.project_id)
    lab: Lab = await Lab.find(db_session, id=project.lab_id)
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid
    return {
        "airalogy_record_id": record.airalogy_id,
        "record_id": record.id,
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": protocol.airalogy_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": record.protocol_id,
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at,
            "record_current_version_submission_user_id": user.username,
            "record_initial_version_submission_time": init_record.created_at,
            "record_initial_version_submission_user_id": user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
        },
        "data": record.data,
    }


@router.delete("/{id}")
async def delete_protocol_record(
    protocol_id: UUID,
    id: UUID,
    version: int,
    db_session: DBSession,
    current_user: CurrentUser,
):
    # 查找要删除的记录
    record = await Record.find_by(
        db_session,
        [
            Record.id == id,
            Record.protocol_id == protocol_id,
            Record.version == version,
        ],
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    # 获取协议和项目信息进行权限检查
    protocol = await Protocol.find(db_session, id=record.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)

    # 检查删除记录的权限
    user_role = await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="delete_record",
        protocol=protocol,
        record=record,
    )

    # 不允许删除存在更新记录之前的记录（必须先删最新的）
    latest_number = await db_session.scalar(
        select(func.max(Record.number)).where(
            Record.protocol_id == protocol_id,
            Record.deleted_at.is_(None),
        )
    )
    if (
        latest_number is not None
        and record.number is not None
        and record.number < latest_number
    ):
        raise HTTPException(
            status_code=400,
            detail="存在更新的记录，请先删除最新记录。",
        )

    # 非管理员受安全缓冲期限制
    grace_days = config.RECORD_DELETE_GRACE_DAYS
    if grace_days and grace_days > 0 and user_role > ProjectRole.MANAGER:
        if record.created_at and datetime.now() - record.created_at > timedelta(
            days=grace_days
        ):
            raise HTTPException(
                status_code=400,
                detail=f"记录已超过 {grace_days} 天，无法删除。",
            )

    # 执行删除操作
    update_stmt = (
        update(Record)
        .where(
            Record.id == id,
            Record.protocol_id == protocol_id,
            Record.version == version,
        )
        .values(deleted_at=datetime.now())
    )
    await db_session.execute(update_stmt)
    await db_session.commit()

    return {"message": "success"}
