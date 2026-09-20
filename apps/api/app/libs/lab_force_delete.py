import os
import shutil
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import sessionmanager
from app.libs.file_storage import delete_file
from app.libs.protocol_agent import prepare_protocol_package
from app.models.airalogy_file import AiralogyFile
from app.models.answer import Answer
from app.models.attachment import Attachment
from app.models.chat import Chat
from app.models.embedding import Embedding
from app.models.group import Group, GroupProject, GroupUser
from app.models.lab import Lab, LabUser
from app.models.lab_force_delete_job import LabForceDeleteJob
from app.models.pinned_item import PinnedItem, PinnedResourceType
from app.models.project import Project, ProjectUser
from app.models.project_group import (
    ProjectGroup,
    ProjectGroupProtocol,
    ProjectGroupUser,
    ProtocolUser,
)
from app.models.protocol import Protocol
from app.models.protocol_folder import ProtocolFolder, ProtocolFolderProtocol
from app.models.protocol_version import ProtocolVersion
from app.models.question import Question
from app.models.record import Record
from app.models.star import Star, StarResourceType
from app.models.upvote import Upvote, UpvoteResourceType

DEFAULT_PROJECT_UIDS = {"public_protocols", "lab_protocols"}

LAB_FORCE_DELETE_PENDING = "pending"
LAB_FORCE_DELETE_RUNNING = "running"
LAB_FORCE_DELETE_SUCCEEDED = "succeeded"
LAB_FORCE_DELETE_FAILED = "failed"


async def collect_lab_force_delete_manifest(
    db_session: AsyncSession,
    lab: Lab,
) -> dict[str, Any]:
    projects = (
        await db_session.execute(select(Project).where(Project.lab_id == lab.id))
    ).scalars().all()
    groups = (await db_session.execute(select(Group).where(Group.lab_id == lab.id))).scalars().all()

    project_ids = [project.id for project in projects]
    group_ids = [group.id for group in groups]

    project_groups: list[ProjectGroup] = []
    protocol_folders: list[ProtocolFolder] = []
    protocols: list[Protocol] = []
    if project_ids:
        project_groups = (
            await db_session.execute(
                select(ProjectGroup).where(ProjectGroup.project_id.in_(project_ids))
            )
        ).scalars().all()
        protocol_folders = (
            await db_session.execute(
                select(ProtocolFolder).where(ProtocolFolder.project_id.in_(project_ids))
            )
        ).scalars().all()
        protocols = (
            await db_session.execute(
                select(Protocol).where(Protocol.project_id.in_(project_ids))
            )
        ).scalars().all()

    protocol_ids = [protocol.id for protocol in protocols]
    project_group_ids = [project_group.id for project_group in project_groups]
    protocol_folder_ids = [protocol_folder.id for protocol_folder in protocol_folders]

    questions: list[Question] = []
    if protocol_ids:
        questions = (
            await db_session.execute(
                select(Question).where(Question.protocol_id.in_(protocol_ids))
            )
        ).scalars().all()
    question_ids = [question.id for question in questions]

    answers: list[Answer] = []
    if question_ids:
        answers = (
            await db_session.execute(
                select(Answer).where(Answer.question_id.in_(question_ids))
            )
        ).scalars().all()
    answer_ids = [answer.id for answer in answers]

    protocol_versions: list[ProtocolVersion] = []
    airalogy_files: list[AiralogyFile] = []
    records_total = 0
    records_active = 0
    if protocol_ids:
        protocol_versions = (
            await db_session.execute(
                select(ProtocolVersion).where(ProtocolVersion.protocol_id.in_(protocol_ids))
            )
        ).scalars().all()
        airalogy_files = (
            await db_session.execute(
                select(AiralogyFile).where(AiralogyFile.protocol_id.in_(protocol_ids))
            )
        ).scalars().all()
        records_total = await Record.count(
            db_session,
            [Record.protocol_id.in_(protocol_ids)],
        )
        records_active = await Record.count(
            db_session,
            [
                Record.protocol_id.in_(protocol_ids),
                Record.deleted_at.is_(None),
            ],
        )

    logo_attachment = None
    if lab.logo is not None:
        logo_attachment = await Attachment.find_by(db_session, [Attachment.id == lab.logo])

    members = await LabUser.count(db_session, [LabUser.lab_id == lab.id])
    projects_active = sum(project.deleted_at is None for project in projects)
    protocols_active = sum(protocol.deleted_at is None for protocol in protocols)
    projects_default = sum(project.uid in DEFAULT_PROJECT_UIDS for project in projects)

    preview = {
        "members": members,
        "groups": len(groups),
        "projects_total": len(projects),
        "projects_active": projects_active,
        "projects_deleted": len(projects) - projects_active,
        "projects_default": projects_default,
        "protocols_total": len(protocols),
        "protocols_active": protocols_active,
        "records_total": records_total,
        "records_active": records_active,
        "files_total": len(airalogy_files) + len(protocol_versions) + int(logo_attachment is not None),
    }

    return {
        "lab_id": lab.id,
        "lab_uid": lab.uid,
        "lab_name": lab.name,
        "preview": preview,
        "group_ids": group_ids,
        "project_ids": project_ids,
        "project_group_ids": project_group_ids,
        "protocol_folder_ids": protocol_folder_ids,
        "protocol_ids": protocol_ids,
        "question_ids": question_ids,
        "answer_ids": answer_ids,
        "airalogy_files": airalogy_files,
        "protocol_versions": protocol_versions,
        "logo_attachment": logo_attachment,
    }


async def run_lab_force_delete_job(job_id: int):
    await _mark_job_running(job_id)

    manifest: dict[str, Any] | None = None
    try:
        async with sessionmanager.session() as db_session:
            job = await LabForceDeleteJob.find_by(db_session, [LabForceDeleteJob.id == job_id])
            if job is None:
                return

            lab = await Lab.find_by(db_session, [Lab.id == job.lab_id], with_for_update=True)
            if lab is None:
                raise ValueError("Lab not found")
            if lab.create_user_id != job.requested_by_user_id:
                raise ValueError("Lab deletion requester is no longer the Lab creator")

            manifest = await collect_lab_force_delete_manifest(db_session, lab)
            await _delete_lab_from_database(db_session, lab, manifest)
            await db_session.commit()
    except Exception as exc:
        await _finish_job(
            job_id,
            status=LAB_FORCE_DELETE_FAILED,
            failure_reason=str(exc),
        )
        return

    storage_failures = await _cleanup_storage_objects(manifest)
    if storage_failures:
        await _finish_job(
            job_id,
            status=LAB_FORCE_DELETE_FAILED,
            failure_reason=_format_storage_failures(storage_failures),
        )
        return

    await _finish_job(job_id, status=LAB_FORCE_DELETE_SUCCEEDED)


async def _delete_lab_from_database(
    db_session: AsyncSession,
    lab: Lab,
    manifest: dict[str, Any],
):
    if manifest.get("lab_id") != lab.id:
        raise ValueError("Lab deletion manifest does not match the confirmed Lab")
    # This is deliberately in the same transaction as the existing Lab delete.
    # A later protected research FK failure rolls back these lineage deletions.
    await _delete_lab_analysis_publications(db_session, lab.id)
    await _delete_lab_analysis_input_file_references(db_session, lab.id)
    await _delete_lab_workflow_file_references(db_session, lab.id)
    await _delete_lab_workflow_asset_inputs(db_session, lab.id)
    project_ids = manifest["project_ids"]
    project_group_ids = manifest["project_group_ids"]
    protocol_folder_ids = manifest["protocol_folder_ids"]
    protocol_ids = manifest["protocol_ids"]
    question_ids = manifest["question_ids"]
    answer_ids = manifest["answer_ids"]
    group_ids = manifest["group_ids"]
    logo_attachment = manifest["logo_attachment"]

    if protocol_ids:
        await db_session.execute(
            update(Protocol)
            .where(Protocol.parent_protocol_id.in_(protocol_ids))
            .values(parent_protocol_id=None, parent_protocol_version=None)
        )

    if project_ids:
        await db_session.execute(
            update(Project)
            .where(Project.parent_project_id.in_(project_ids))
            .values(parent_project_id=None)
        )

    if answer_ids:
        await db_session.execute(
            delete(Star).where(
                Star.resource_type == StarResourceType.ANSWER,
                Star.resource_id.in_(answer_ids),
            )
        )
        await db_session.execute(
            delete(Upvote).where(
                Upvote.resource_type == UpvoteResourceType.ANSWER,
                Upvote.resource_id.in_(answer_ids),
            )
        )

    if question_ids:
        await db_session.execute(
            delete(Star).where(
                Star.resource_type == StarResourceType.QUESTION,
                Star.resource_id.in_(question_ids),
            )
        )
        await db_session.execute(
            delete(Upvote).where(
                Upvote.resource_type == UpvoteResourceType.QUESTION,
                Upvote.resource_id.in_(question_ids),
            )
        )
        await db_session.execute(delete(Answer).where(Answer.question_id.in_(question_ids)))
        await db_session.execute(delete(Question).where(Question.id.in_(question_ids)))

    if protocol_ids:
        await db_session.execute(delete(Record).where(Record.protocol_id.in_(protocol_ids)))
        await db_session.execute(delete(Chat).where(Chat.protocol_id.in_(protocol_ids)))
        await db_session.execute(
            delete(ProtocolUser).where(ProtocolUser.protocol_id.in_(protocol_ids))
        )
        await db_session.execute(
            delete(ProjectGroupProtocol).where(
                or_(
                    ProjectGroupProtocol.project_group_id.in_(project_group_ids),
                    ProjectGroupProtocol.protocol_id.in_(protocol_ids),
                )
            )
        )
        await db_session.execute(
            delete(ProtocolFolderProtocol).where(
                or_(
                    ProtocolFolderProtocol.protocol_folder_id.in_(protocol_folder_ids),
                    ProtocolFolderProtocol.protocol_id.in_(protocol_ids),
                )
            )
        )
        await db_session.execute(delete(Embedding).where(Embedding.protocol_id.in_(protocol_ids)))
        await db_session.execute(
            delete(PinnedItem).where(
                PinnedItem.resource_type == PinnedResourceType.PROTOCOL,
                PinnedItem.resource_id.in_(protocol_ids),
            )
        )
        await db_session.execute(
            delete(Star).where(
                Star.resource_type == StarResourceType.PROTOCOL,
                Star.resource_id.in_(protocol_ids),
            )
        )
        await db_session.execute(
            delete(AiralogyFile).where(AiralogyFile.protocol_id.in_(protocol_ids))
        )
        await db_session.execute(
            delete(ProtocolVersion).where(ProtocolVersion.protocol_id.in_(protocol_ids))
        )
        await db_session.execute(delete(Protocol).where(Protocol.id.in_(protocol_ids)))

    if project_group_ids:
        await db_session.execute(
            delete(ProjectGroupUser).where(
                ProjectGroupUser.project_group_id.in_(project_group_ids)
            )
        )
        await db_session.execute(
            delete(ProjectGroup).where(ProjectGroup.id.in_(project_group_ids))
        )

    if project_ids or group_ids:
        await db_session.execute(
            delete(GroupProject).where(
                or_(
                    GroupProject.group_id.in_(group_ids),
                    GroupProject.project_id.in_(project_ids),
                )
            )
        )

    if project_ids:
        await db_session.execute(delete(ProjectUser).where(ProjectUser.project_id.in_(project_ids)))
        await db_session.execute(
            delete(ProtocolFolder).where(ProtocolFolder.id.in_(protocol_folder_ids))
        )
        await db_session.execute(
            delete(PinnedItem).where(
                PinnedItem.resource_type == PinnedResourceType.PROJECT,
                PinnedItem.resource_id.in_(project_ids),
            )
        )
        await db_session.execute(delete(Project).where(Project.id.in_(project_ids)))

    if group_ids:
        await db_session.execute(delete(GroupUser).where(GroupUser.group_id.in_(group_ids)))
        await db_session.execute(delete(Group).where(Group.id.in_(group_ids)))

    await db_session.execute(
        delete(PinnedItem).where(
            PinnedItem.resource_type == PinnedResourceType.LAB,
            PinnedItem.resource_id == lab.id,
        )
    )
    await db_session.execute(delete(LabUser).where(LabUser.lab_id == lab.id))
    await db_session.delete(lab)
    await db_session.flush()

    if logo_attachment is not None:
        await db_session.execute(
            delete(Attachment).where(Attachment.id == logo_attachment.id)
        )


async def _delete_lab_analysis_publications(db_session: AsyncSession, lab_id):
    """Release only this confirmed Lab's publication FKs before its sources.

    Publications never own the source analyses, Records, or files. An unexpected
    cross-Lab reference blocks the entire deletion, rather than deleting foreign
    lineage or bypassing the source RESTRICT constraints.
    """
    from app.models.analysis import AnalysisInterpretationRevision, AnalysisRun
    from app.models.analysis_publication import AnalysisEvidencePublication
    from app.models.research import ResearchTask
    from app.models.research_asset import ResearchEvidence

    project_ids = select(Project.id).where(Project.lab_id == lab_id)
    analysis_ids = select(AnalysisRun.id).where(AnalysisRun.project_id.in_(project_ids))
    task_ids = select(ResearchTask.id).where(ResearchTask.lab_id == lab_id)
    evidence_ids = select(ResearchEvidence.id).where(ResearchEvidence.task_id.in_(task_ids))
    foreign = await db_session.scalar(
        select(AnalysisEvidencePublication.id).where(
            or_(
                AnalysisEvidencePublication.analysis_run_id.in_(analysis_ids),
                AnalysisEvidencePublication.task_id.in_(task_ids),
                AnalysisEvidencePublication.evidence_id.in_(evidence_ids),
            ),
            AnalysisEvidencePublication.project_id.not_in(project_ids),
        ).limit(1)
    )
    if foreign is not None:
        raise ValueError("Another Lab references these analysis publications; deletion is blocked")
    publications = list((await db_session.scalars(
        select(AnalysisEvidencePublication).where(
            AnalysisEvidencePublication.project_id.in_(project_ids),
        ).with_for_update()
    )).all())
    for publication in publications:
        project = await db_session.get(Project, publication.project_id)
        analysis = await db_session.get(AnalysisRun, publication.analysis_run_id)
        task = await db_session.get(ResearchTask, publication.task_id)
        evidence = await db_session.get(ResearchEvidence, publication.evidence_id)
        interpretation = (
            await db_session.get(AnalysisInterpretationRevision, publication.interpretation_revision_id)
            if publication.interpretation_revision_id is not None else None
        )
        if (
            project is None or project.lab_id != lab_id
            or analysis is None or analysis.project_id != project.id
            or task is None or task.lab_id != lab_id or task.project_id != project.id
            or evidence is None or evidence.task_id != task.id
            or evidence.artifact_type != "analysis_publication"
            or evidence.artifact_id != str(publication.id)
            or evidence.artifact_version != publication.digest
            or (publication.interpretation_revision_id is not None and (
                interpretation is None or interpretation.analysis_run_id != analysis.id
            ))
        ):
            raise ValueError("Analysis publication does not belong to the confirmed Lab")
    if publications:
        await db_session.execute(delete(AnalysisEvidencePublication).where(
            AnalysisEvidencePublication.id.in_([row.id for row in publications]),
            AnalysisEvidencePublication.project_id.in_(project_ids),
        ))


async def _delete_lab_analysis_input_file_references(db_session: AsyncSession, lab_id):
    """Drop only confirmed Lab attachment receipts before deleting their sources.

    No storage object, original file, shared blob or foreign Lab receipt is
    removed here. Any later research lifecycle failure rolls this back too.
    """
    from app.models.analysis import AnalysisRun
    from app.models.analysis_compute import AnalysisComputeInputFile

    analysis_ids = select(AnalysisRun.id).join(
        Project, Project.id == AnalysisRun.project_id
    ).where(Project.lab_id == lab_id)
    source_ids = select(AiralogyFile.id).join(
        Protocol, Protocol.id == AiralogyFile.protocol_id
    ).join(Project, Project.id == Protocol.project_id).where(Project.lab_id == lab_id)
    foreign = await db_session.scalar(select(AnalysisComputeInputFile.input_row_id).where(
        AnalysisComputeInputFile.source_file_id.in_(source_ids),
        AnalysisComputeInputFile.analysis_run_id.not_in(analysis_ids),
    ).limit(1))
    if foreign is not None:
        raise ValueError("Another Lab still references these analysis attachment files; deletion is blocked")
    await db_session.execute(delete(AnalysisComputeInputFile).where(
        AnalysisComputeInputFile.analysis_run_id.in_(analysis_ids)
    ))


async def _delete_lab_workflow_asset_inputs(db_session: AsyncSession, lab_id):
    """Delete only confirmed Lab input receipts, after their dependent aliases."""
    from app.models.knowledge import ResearchFile
    from app.models.research import ResearchTask
    from app.models.research_asset import DataAsset, DataAssetVersion
    from app.models.workflow_asset import WorkflowRunAssetInput
    from app.models.workflow_file import WorkflowFileBinding

    task_ids = select(ResearchTask.id).where(ResearchTask.lab_id == lab_id)
    sources = select(DataAssetVersion.id).join(DataAsset).where(DataAsset.lab_id == lab_id)
    files = select(ResearchFile.id).where(ResearchFile.lab_id == lab_id)
    foreign = await db_session.scalar(select(WorkflowRunAssetInput.id).where(
        or_(WorkflowRunAssetInput.data_asset_version_id.in_(sources), WorkflowRunAssetInput.research_file_id.in_(files)),
        WorkflowRunAssetInput.task_id.not_in(task_ids),
    ).limit(1))
    if foreign is not None:
        raise ValueError("Another Lab references these Workflow DataAsset inputs; deletion is blocked")
    rows = list((await db_session.scalars(select(WorkflowRunAssetInput).where(
        WorkflowRunAssetInput.task_id.in_(task_ids),
    ).with_for_update())).all())
    if not rows:
        return
    for row in rows:
        task = await db_session.get(ResearchTask, row.task_id)
        project = await db_session.get(Project, task.project_id)
        version = await db_session.get(DataAssetVersion, row.data_asset_version_id)
        asset = await db_session.get(DataAsset, version.data_asset_id) if version else None
        file = await db_session.get(ResearchFile, row.research_file_id)
        if (
            project is None or project.lab_id != lab_id or asset is None
            or asset.project_id != project.id or asset.lab_id != lab_id
            or file is None or file.lab_id != lab_id or file.project_id not in {None, project.id}
            or version.research_file_id != file.id or file.blob_id != row.blob_id
        ):
            raise ValueError("Workflow DataAsset input does not belong to the confirmed Lab")
    ids = [row.id for row in rows]
    if await db_session.scalar(select(WorkflowFileBinding.file_id).where(
        WorkflowFileBinding.asset_input_id.in_(ids),
    ).limit(1)) is not None:
        raise ValueError("Workflow DataAsset file aliases must be removed before input receipts")
    await db_session.execute(delete(WorkflowRunAssetInput).where(
        WorkflowRunAssetInput.id.in_(ids), WorkflowRunAssetInput.task_id.in_(task_ids),
    ))


async def _delete_lab_workflow_file_references(db_session: AsyncSession, lab_id):
    """Remove only this Lab's logical file lifecycle, never its shared blobs.

    Do not reuse this helper for local Protocol/file deletes: their source and
    execution references must remain protected. Unexpected cross-Lab references
    stop the entire transaction rather than deleting another Lab's lineage.
    """
    from app.models.record_export import RecordExport
    from app.models.research import ResearchTask
    from app.models.workflow_file import (
        WorkflowFileBinding,
        WorkflowFileExportReference,
    )

    tasks = list(
        (
            await db_session.scalars(
                select(ResearchTask)
                .where(ResearchTask.lab_id == lab_id)
                .order_by(ResearchTask.id)
                .with_for_update()
            )
        ).all()
    )
    if not tasks:
        return
    project_ids = set(
        (
            await db_session.scalars(select(Project.id).where(Project.lab_id == lab_id))
        ).all()
    )
    if any(task.project_id not in project_ids for task in tasks):
        raise ValueError(
            "Workflow Task does not belong to the confirmed Lab's Projects"
        )
    task_ids = [task.id for task in tasks]
    bindings = list(
        (
            await db_session.scalars(
                select(WorkflowFileBinding)
                .where(WorkflowFileBinding.task_id.in_(task_ids))
                .order_by(WorkflowFileBinding.file_id)
                .with_for_update()
            )
        ).all()
    )
    if not bindings:
        return
    file_ids = [binding.file_id for binding in bindings]
    files = list(
        (
            await db_session.scalars(
                select(AiralogyFile)
                .where(AiralogyFile.id.in_(file_ids))
                .order_by(AiralogyFile.id)
                .with_for_update()
            )
        ).all()
    )
    protocol_ids = set(
        (
            await db_session.scalars(
                select(Protocol.id).where(Protocol.project_id.in_(project_ids))
            )
        ).all()
    )
    tasks_by_id = {task.id: task for task in tasks}
    bindings_by_id = {binding.file_id: binding for binding in bindings}
    if len(files) != len(bindings) or any(
        file.storage_backend != "workflow_reference"
        or file.protocol_id not in protocol_ids
        or file.project_id != tasks_by_id[bindings_by_id[file.id].task_id].project_id
        for file in files
    ):
        raise ValueError("Workflow logical file scope does not match the confirmed Lab")
    foreign_binding = await db_session.scalar(
        select(WorkflowFileBinding.file_id)
        .where(
            WorkflowFileBinding.source_file_id.in_(file_ids),
            WorkflowFileBinding.task_id.not_in(task_ids),
        )
        .limit(1)
    )
    foreign_export = await db_session.scalar(
        select(WorkflowFileExportReference.file_id)
        .join(RecordExport, RecordExport.id == WorkflowFileExportReference.export_id)
        .where(
            WorkflowFileExportReference.file_id.in_(file_ids),
            RecordExport.lab_id != lab_id,
        )
        .limit(1)
    )
    if foreign_binding is not None or foreign_export is not None:
        raise ValueError(
            "Another Lab still references these Workflow files; deletion is blocked"
        )
    await db_session.execute(
        delete(WorkflowFileExportReference).where(
            WorkflowFileExportReference.file_id.in_(file_ids),
            WorkflowFileExportReference.export_id.in_(
                select(RecordExport.id).where(RecordExport.lab_id == lab_id)
            ),
        )
    )
    await db_session.execute(
        delete(WorkflowFileBinding).where(
            WorkflowFileBinding.file_id.in_(file_ids),
            WorkflowFileBinding.task_id.in_(task_ids),
        )
    )
    await db_session.execute(
        delete(AiralogyFile).where(
            AiralogyFile.id.in_(file_ids),
            AiralogyFile.storage_backend == "workflow_reference",
        )
    )


async def _cleanup_storage_objects(manifest: dict[str, Any] | None) -> list[str]:
    if manifest is None:
        return []

    failures: list[str] = []

    logo_attachment: Attachment | None = manifest["logo_attachment"]
    if logo_attachment is not None:
        await _delete_storage_key(logo_attachment.object_key, failures)

    for airalogy_file in manifest["airalogy_files"]:
        if airalogy_file.storage_backend == "workflow_reference":
            continue
        await _delete_storage_key(airalogy_file.object_key, failures)

    for protocol_version in manifest["protocol_versions"]:
        package_dir = os.path.join(config.PROTOCOL_DIR, protocol_version.package_name)
        package_dir_keys: list[str] = []
        try:
            await prepare_protocol_package(protocol_version)
            if os.path.isdir(package_dir):
                for root, _, files in os.walk(package_dir):
                    for filename in files:
                        local_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(local_path, package_dir).replace("\\", "/")
                        package_dir_keys.append(
                            f"{protocol_version.package_dir_object_key}/{relative_path}"
                        )
        except Exception as exc:
            failures.append(
                f"{protocol_version.package_dir_object_key}: failed to enumerate package files ({exc})"
            )
        finally:
            if os.path.isdir(package_dir):
                shutil.rmtree(package_dir, ignore_errors=True)

        for object_key in package_dir_keys:
            await _delete_storage_key(object_key, failures)

        await _delete_storage_key(protocol_version.package_object_key, failures)

    return failures


async def _delete_storage_key(object_key: str, failures: list[str]):
    try:
        await delete_file(object_key)
    except Exception as exc:
        failures.append(f"{object_key}: {exc}")


async def _mark_job_running(job_id: int):
    async with sessionmanager.session() as db_session:
        job = await LabForceDeleteJob.find_by(db_session, [LabForceDeleteJob.id == job_id])
        if job is None:
            return

        job.status = LAB_FORCE_DELETE_RUNNING
        job.started_at = datetime.now()
        job.failure_reason = None
        await db_session.commit()


async def _finish_job(
    job_id: int,
    status: str,
    failure_reason: str | None = None,
):
    async with sessionmanager.session() as db_session:
        job = await LabForceDeleteJob.find_by(db_session, [LabForceDeleteJob.id == job_id])
        if job is None:
            return

        job.status = status
        job.failure_reason = failure_reason
        job.finished_at = datetime.now()
        await db_session.commit()


def _format_storage_failures(failures: list[str]) -> str:
    max_items = 20
    message_lines = [
        "Lab database records were deleted, but some file objects could not be removed:"
    ]
    message_lines.extend(failures[:max_items])
    remaining = len(failures) - max_items
    if remaining > 0:
        message_lines.append(f"... and {remaining} more")
    return "\n".join(message_lines)
