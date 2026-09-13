"""Reader-side protection for values derived by fixed Workflow v2 resolutions.

Research Task visibility does not grant access to its source Records. Keep the
workbench status visible, but never propagate resolved data to another reader.
"""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.research import ResearchAction, ResearchProtocolRun, ResearchTask
from app.models.workflow_definition import WorkflowNodeResolution
from app.routers.permission import check_user_permission

WORKFLOW_DATA_RESTRICTED = (
    "Workflow data is restricted because a source Record is not readable."
)


async def _readable_record(db, *, source, current_user, project):
    if source.get("kind") == "analysis":
        from app.models.research import ResearchRun
        from app.services.workflow_analysis_runtime import analysis_action_readable

        action = await db.get(ResearchAction, UUID(source["action_id"]))
        run = await db.get(ResearchRun, action.run_id) if action else None
        task = await db.get(ResearchTask, run.task_id) if run else None
        if (
            task is None
            or task.project_id != project.id
            or not await analysis_action_readable(
                db, task=task, run=run, action=action, user=current_user
            )
        ):
            raise HTTPException(403, WORKFLOW_DATA_RESTRICTED)
        output = (action.output_data or {}).get("analysis_result") or {}
        if (
            output.get("analysis_id") != source.get("analysis_id")
            or output.get("result_digest") != source.get("result_digest")
            or output.get("source_digest") != source.get("source_digest")
        ):
            raise ValueError("Workflow analysis source lineage changed")
        return None
    record_id = UUID(source["record_id"])
    version = source["record_version"]
    if type(version) is not int or version < 1:
        raise ValueError("Invalid source Record revision")
    record = await db.scalar(
        select(Record)
        .where(Record.id == record_id, Record.version == version)
        .execution_options(populate_existing=True)
    )
    protocol = await db.get(Protocol, record.protocol_id) if record else None
    if (
        record is None
        or record.deleted_at is not None
        or record.hash != source["record_hash"]
        or str(record.protocol_id) != source["protocol_id"]
        or protocol is None
        or protocol.deleted_at is not None
        or protocol.project_id != project.id
    ):
        raise ValueError("Workflow source Record is unavailable or changed")
    await check_user_permission(
        db,
        project=project,
        user=current_user,
        action="read_record",
        protocol=protocol,
        record=record,
    )
    from app.services.workflow_files import authorize_record_files

    await authorize_record_files(db, record.data, current_user)
    return record


async def workflow_data_readable(db, *, run, current_user, project=None):
    marker = (getattr(run, "environment_snapshot", None) or {}).get(
        "manual_workflow"
    ) or {}
    if marker.get("execution_contract_version") not in {2, 3, 4, 5}:
        return True
    if current_user is None:
        return False
    if project is None:
        task = await db.get(ResearchTask, run.task_id)
        project = await db.get(Project, task.project_id) if task else None
    if project is None or project.deleted_at is not None:
        return False
    from app.services.workflow_resolutions import verify_resolution_seal

    rows = list(
        (
            await db.scalars(
                select(WorkflowNodeResolution)
                .where(WorkflowNodeResolution.run_id == run.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    checked = set()
    for row in rows:
        try:
            verify_resolution_seal(row)
            if (
                row.task_id != run.task_id
                or row.run_id != run.id
                or str(row.workflow_revision_id) != marker.get("revision_id")
            ):
                return False
            sources = row.receipt.get("sources")
            if not isinstance(sources, dict):
                return False
            for source in sources.values():
                key = (
                    source.get("record_id", source.get("analysis_id")),
                    source.get("record_version", source.get("result_digest")),
                    source.get("record_hash", source.get("source_digest")),
                )
                if key in checked:
                    continue
                await _readable_record(
                    db, source=source, current_user=current_user, project=project
                )
                checked.add(key)
        except (KeyError, TypeError, ValueError):
            return False
        except HTTPException as error:
            if error.status_code in {400, 403, 404, 409}:
                return False
            raise
    # Whole-Run views also contain independent root outputs, including Records
    # that never became a condition/binding source. They retain their own ACL.
    actions = list(
        (
            await db.scalars(
                select(ResearchAction).where(ResearchAction.run_id == run.id)
            )
        ).all()
    )
    for action in actions:
        if not await workflow_action_data_readable(
            db, run=run, action=action, current_user=current_user, project=project
        ):
            return False
    return True


async def workflow_action_data_readable(db, *, run, action, current_user, project):
    """Check only data this card carries, never unrelated parallel branches."""
    marker = (getattr(run, "environment_snapshot", None) or {}).get(
        "manual_workflow"
    ) or {}
    if marker.get("execution_contract_version") not in {2, 3, 4, 5}:
        # Ordinary Protocol cards also expose a complete Record in output_data.
        # Check the exact *displayed* payload, not a possibly older Evidence
        # snapshot. Cards that have not produced a Record keep their prior path.
        if action.kind == "protocol_run" and (
            "record" in (action.output_data or {}) or action.status == "completed"
        ):
            from app.services.research_asset_visibility import (
                HIDDEN_SOURCE_STATUSES,
                _require_protocol_output_readable,
            )

            if (
                current_user is None
                or project is None
                or project.deleted_at is not None
                or action.run_id != run.id
            ):
                return False
            task = await db.get(ResearchTask, run.task_id)
            if task is None or task.project_id != project.id:
                return False
            try:
                await _require_protocol_output_readable(
                    db,
                    task=task,
                    action=action,
                    user=current_user,
                    output=action.output_data,
                )
            except HTTPException as error:
                if error.status_code in HIDDEN_SOURCE_STATUSES:
                    return False
                raise
        return True
    if current_user is None or project is None or project.deleted_at is not None:
        return False
    from app.services.research_runtime import canonical_digest
    from app.services.workflow_resolutions import verify_resolution_seal

    try:
        if action.run_id == run.id and action.kind == "analysis_run":
            from app.services.workflow_analysis_runtime import analysis_action_readable

            task = await db.get(ResearchTask, run.task_id)
            return task is not None and await analysis_action_readable(
                db, task=task, run=run, action=action, user=current_user
            )
        if action.run_id != run.id or action.kind != "protocol_run":
            return False
        data = action.input_data or {}
        typed = await db.scalar(
            select(ResearchProtocolRun)
            .where(ResearchProtocolRun.action_id == action.id)
            .execution_options(populate_existing=True)
        )
        if typed is None or canonical_digest(typed.initial_values) != canonical_digest(
            data.get("initial_values")
        ):
            return False
        row = await db.scalar(
            select(WorkflowNodeResolution)
            .where(WorkflowNodeResolution.action_id == action.id)
            .execution_options(populate_existing=True)
        )
        if row is not None:
            verify_resolution_seal(row)
            if marker.get("execution_contract_version") == 5:
                from app.services.workflow_files import verify_resolution_files

                task = await db.get(ResearchTask, run.task_id)
                await verify_resolution_files(
                    db,
                    task=task,
                    run=run,
                    action=action,
                    resolution=row,
                    user=current_user,
                )
            reference = {
                "id": str(row.id),
                "digest": row.digest,
                "state": row.state,
                "receipt": row.receipt,
            }
            if (
                row.task_id != run.task_id
                or row.run_id != run.id
                or row.action_id != action.id
                or row.node_id != (data.get("action_graph") or {}).get("node_id")
                or str(row.workflow_revision_id) != marker.get("revision_id")
                or canonical_digest(reference)
                != canonical_digest(data.get("workflow_resolution"))
                or canonical_digest(row.initial_values)
                != canonical_digest(typed.initial_values)
            ):
                return False
            sources = row.receipt.get("sources")
            if not isinstance(sources, dict):
                return False
            for source in sources.values():
                await _readable_record(
                    db, source=source, current_user=current_user, project=project
                )
        elif data.get("workflow_resolution") is not None:
            return False
        # A root has no resolution, but its completed output is still a private
        # Record. Do not disclose it merely because it has no incoming edges.
        output = action.output_data or {}
        if "record" in output:
            payload = output["record"]
            source = {
                "record_id": payload["record_id"],
                "record_version": payload["record_version"],
                "record_hash": payload["metadata"]["sha1"],
                "protocol_id": str(typed.protocol_id),
            }
            record = await _readable_record(
                db, source=source, current_user=current_user, project=project
            )
            if (
                typed.record_id != record.id
                or typed.record_version != record.version
                or canonical_digest(payload["data"]) != canonical_digest(record.data)
            ):
                return False
        elif typed.record_id is not None:
            return False
        if output.get("workflow_resolution") is not None and (
            row is None
            or canonical_digest(output["workflow_resolution"])
            != canonical_digest(reference)
        ):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    except HTTPException as error:
        if error.status_code in {400, 403, 404, 409}:
            return False
        raise
    return True


async def require_workflow_action_data_readable(
    db, *, run, action, current_user, project
):
    if not await workflow_action_data_readable(
        db, run=run, action=action, current_user=current_user, project=project
    ):
        raise HTTPException(status_code=403, detail=WORKFLOW_DATA_RESTRICTED)


async def require_workflow_data_readable(db, *, run, current_user, project=None):
    if not await workflow_data_readable(
        db, run=run, current_user=current_user, project=project
    ):
        raise HTTPException(status_code=403, detail=WORKFLOW_DATA_RESTRICTED)


def restricted_workflow_payload(payload, *, kind):
    """Return an explicit status-only view, without modifying stored evidence."""
    result = deepcopy(payload)
    result["workflow_data_restricted"] = True
    result["workflow_data_restriction_reason"] = WORKFLOW_DATA_RESTRICTED
    if kind in {"run", "task"}:
        result["result_package"] = {}
        if kind == "run":
            result["aira_state"] = {}
            result["last_error"] = None
        else:
            result["conclusion"] = ""
    if kind == "action":
        result["input_data"] = {
            key: value
            for key, value in (result.get("input_data") or {}).items()
            if key not in {"initial_values", "workflow_resolution", "analysis_input"}
        }
        result["output_data"] = {}
        result["error"] = None
        result["preview_digest"] = ""
        if result.get("analysis_run"):
            result["analysis_run"] = {
                "status": result["analysis_run"].get("status"),
                "can_open_private_report": False,
            }
        if result.get("protocol_run"):
            result["protocol_run"].update(
                initial_values={},
                validation_report={},
                record_id=None,
                record_version=None,
            )
        if result.get("work_item"):
            result["work_item"] = restricted_workflow_payload(
                result["work_item"], kind="work_item"
            )
        if result.get("approval"):
            result["approval"] = restricted_workflow_payload(
                result["approval"], kind="approval"
            )
    if kind == "work_item":
        result.update(
            instructions="",
            submission_contract={},
            submission={},
            validation_issues=[],
            record_id=None,
            record_version=None,
        )
    if kind == "approval":
        result.update(preview_digest="", reason="", decision_reason="")
    return result
