"""Read and export finalized or legacy Research Result Packages."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.database import DBSession
from app.models.project import Project
from app.models.research import (
    ResearchResultPackageSnapshot,
    ResearchRun,
    ResearchTask,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.research_result_packages import (
    ResearchResultPackageError,
    render_result_package_markdown,
    result_package_digest,
    verify_result_package_digest,
)
from app.services.research_runtime import require_research_capability

router = APIRouter(prefix="/research-tasks", tags=["research-result-packages"])


async def _authorized_task(
    db_session: DBSession,
    *,
    task_id: UUID,
    current_user: User,
) -> ResearchTask:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await Project.find_by(
        db_session,
        [Project.id == task.project_id, Project.deleted_at.is_(None)],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    return task


async def _result_package_envelope(
    db_session: DBSession,
    *,
    task_id: UUID,
    current_user: User,
    run_id: UUID | None,
) -> tuple[dict, ResearchTask, ResearchRun]:
    task = await _authorized_task(
        db_session, task_id=task_id, current_user=current_user
    )
    statement = select(ResearchRun).where(ResearchRun.task_id == task.id)
    if run_id is not None:
        statement = statement.where(ResearchRun.id == run_id)
    statement = statement.order_by(ResearchRun.run_number.desc()).limit(1)
    run = (await db_session.scalars(statement)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Research Run not found")
    snapshot = await ResearchResultPackageSnapshot.find_by(
        db_session,
        [ResearchResultPackageSnapshot.run_id == run.id],
    )
    package = snapshot.package if snapshot is not None else run.result_package
    if not package:
        raise HTTPException(
            status_code=409,
            detail="Research Run does not have a Result Package yet",
        )
    if snapshot is not None:
        try:
            verify_result_package_digest(snapshot.package, snapshot.digest)
        except ResearchResultPackageError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        digest = snapshot.digest
    else:
        digest = result_package_digest(package)
    finalized_at = snapshot.finalized_at.isoformat() if snapshot is not None else None
    envelope = {
        "snapshot": {
            "id": str(snapshot.id) if snapshot is not None else None,
            "sealed": snapshot is not None,
            "task_id": str(task.id),
            "run_id": str(run.id),
            "run_number": run.run_number,
            "task_revision": snapshot.task_revision if snapshot is not None else None,
            "schema_version": (
                snapshot.schema_version
                if snapshot is not None
                else package.get("schema") or "legacy"
            ),
            "digest": digest,
            "finalized_by_user_id": (
                str(snapshot.finalized_by_user_id)
                if snapshot is not None and snapshot.finalized_by_user_id
                else package.get("reviewed_by_user_id")
            ),
            "finalized_at": finalized_at,
        },
        "package": package,
    }
    return jsonable_encoder(envelope), task, run


@router.get("/{task_id}/result-package")
async def get_research_result_package(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    run_id: UUID | None = None,
):
    envelope, _task, _run = await _result_package_envelope(
        db_session,
        task_id=task_id,
        current_user=current_user,
        run_id=run_id,
    )
    return envelope


@router.get("/{task_id}/result-package/export", response_class=PlainTextResponse)
async def export_research_result_package(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    run_id: UUID | None = None,
    format: Literal["json", "markdown"] = "json",
    language: Literal["en", "zh"] = "en",
):
    envelope, task, run = await _result_package_envelope(
        db_session,
        task_id=task_id,
        current_user=current_user,
        run_id=run_id,
    )
    snapshot = envelope["snapshot"]
    if format == "markdown":
        content = render_result_package_markdown(
            task_title=task.title,
            run_number=run.run_number,
            package=envelope["package"],
            digest=snapshot["digest"],
            sealed=snapshot["sealed"],
            finalized_at=snapshot["finalized_at"],
            language=language,
        )
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    else:
        content = json.dumps(
            envelope,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        media_type = "application/json; charset=utf-8"
        extension = "json"
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="research-task-{task.id}-run-{run.run_number}.{extension}"'
            ),
            "Cache-Control": "private, no-store",
            "X-Airalogy-Result-Digest": snapshot["digest"],
        },
    )
