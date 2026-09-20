"""Live source authorization for Evidence and its derived read models.

Task membership never grants access to a Workflow's source Records or files.
Reviewed Knowledge has its own scope; its original source links still use these
checks. Unreviewed analysis-derived candidates also require their sources.
Checks are per artifact so independent readable branches stay usable.
"""

from contextvars import ContextVar
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeState,
    PaperLibraryEntry,
    ResearchFile,
)
from app.models.project import Project
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchProtocolRun,
    ResearchRun,
    ResearchTask,
)
from app.models.research_asset import (
    DataAsset,
    DataAssetVersion,
    EvidenceQuality,
    KnowledgeEvidenceLink,
    ProtocolImprovementProposal,
    ResearchActionOutputSnapshot,
    ResearchClaimEvidence,
    ResearchEvidence,
)

SOURCE_RESTRICTED = "Research Evidence source is unavailable or not readable"
HIDDEN_SOURCE_STATUSES = {400, 403, 404, 409, 422}
_knowledge_source_stack: ContextVar[frozenset] = ContextVar(
    "analysis_knowledge_source_stack", default=frozenset()
)


async def require_artifact_source_readable(
    db,
    *,
    task,
    user,
    artifact_type,
    artifact_id,
    artifact_version,
    action=None,
):
    """Authorize the exact original source, without publishing its content."""
    if user is None:
        raise HTTPException(403, SOURCE_RESTRICTED)
    if artifact_type == "external":
        return
    try:
        identity = UUID(str(artifact_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, SOURCE_RESTRICTED) from exc
    project = await db.get(Project, task.project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(403, SOURCE_RESTRICTED)

    if artifact_type == "analysis_publication":
        from app.services.analysis_publications import (
            require_analysis_publication_readable,
        )

        publication = await require_analysis_publication_readable(
            db, identity, user, task_id=task.id
        )
        if artifact_version != publication.digest:
            raise HTTPException(409, SOURCE_RESTRICTED)
        return

    if artifact_type == "action_output":
        from app.services.research_action_outputs import (
            ResearchActionOutputError,
            verify_action_output_snapshot,
        )
        from app.services.workflow_visibility import (
            require_workflow_action_data_readable,
        )

        action = action or await db.get(ResearchAction, identity)
        run = await db.get(ResearchRun, action.run_id) if action else None
        if (
            action is None
            or action.id != identity
            or run is None
            or run.task_id != task.id
        ):
            raise HTTPException(403, SOURCE_RESTRICTED)
        # A mutable Action must not authorize a different sealed historical output.
        # Ordinary Action snapshots retain their existing immutable-history contract.
        marker = (run.environment_snapshot or {}).get("manual_workflow") or {}
        is_workflow = marker.get("execution_contract_version") in {2, 3, 4, 5, 6, 7}
        # Ordinary Protocol Evidence uses its immutable historical output below.
        # The UI's live-output guard must not replace that exact source with a
        # later Action payload (or invalidate readable history after it changes).
        if is_workflow or action.kind != "protocol_run":
            await require_workflow_action_data_readable(
                db, run=run, action=action, current_user=user, project=project
            )
        if is_workflow or action.kind == "protocol_run":
            snapshot = await db.scalar(
                select(ResearchActionOutputSnapshot).where(
                    ResearchActionOutputSnapshot.action_id == action.id
                )
            )
            if snapshot is not None:
                try:
                    verify_action_output_snapshot(snapshot)
                except ResearchActionOutputError as exc:
                    raise HTTPException(409, SOURCE_RESTRICTED) from exc
                if (
                    snapshot.task_id != task.id
                    or snapshot.run_id != run.id
                    or snapshot.action_id != action.id
                    or snapshot.action_kind != action.kind
                    or (is_workflow and snapshot.output_data != action.output_data)
                    or (artifact_version and snapshot.digest != artifact_version)
                ):
                    raise HTTPException(409, SOURCE_RESTRICTED)
            if not is_workflow and action.kind == "protocol_run":
                await _require_protocol_output_readable(
                    db,
                    task=task,
                    action=action,
                    user=user,
                    output=snapshot.output_data if snapshot else action.output_data,
                )
        return

    if artifact_type == "record":
        from app.services.record_analyses import analysis_scope
        from app.services.workflow_files import authorize_record_files

        if not str(artifact_version).isdigit():
            raise HTTPException(409, SOURCE_RESTRICTED)
        record = await db.get(Record, (identity, int(artifact_version)))
        if record is None or record.deleted_at is not None:
            raise HTTPException(403, SOURCE_RESTRICTED)
        _, source_project, own_only = await analysis_scope(db, record.protocol_id, user)
        if source_project.id != project.id or (own_only and record.user_id != user.id):
            raise HTTPException(403, SOURCE_RESTRICTED)
        await authorize_record_files(db, record.data, user)
        return

    if artifact_type == "data_asset":
        from app.services.knowledge import authorize_research_file

        asset = await db.get(DataAsset, identity)
        if (
            asset is None
            or asset.archived_at is not None
            or asset.project_id != project.id
            or not str(artifact_version).isdigit()
        ):
            raise HTTPException(403, SOURCE_RESTRICTED)
        version = await db.scalar(
            select(DataAssetVersion).where(
                DataAssetVersion.data_asset_id == identity,
                DataAssetVersion.version == int(artifact_version),
            )
        )
        if version is None:
            raise HTTPException(403, SOURCE_RESTRICTED)
        if version.research_file_id is not None:
            file = await db.get(ResearchFile, version.research_file_id)
            if file is None or file.archived_at is not None:
                raise HTTPException(403, SOURCE_RESTRICTED)
            await authorize_research_file(db, user, file)
        return

    if artifact_type == "knowledge":
        from app.services.knowledge import authorize_knowledge_item

        item = await db.get(KnowledgeItem, identity)
        if item is None or item.state == KnowledgeState.ARCHIVED.value:
            raise HTTPException(403, SOURCE_RESTRICTED)
        await authorize_knowledge_item(db, user, item)
        return
    if artifact_type == "paper_library_entry":
        from app.services.knowledge import authorize_library_entry

        entry = await db.get(PaperLibraryEntry, identity)
        if entry is None or entry.archived_at is not None:
            raise HTTPException(403, SOURCE_RESTRICTED)
        await authorize_library_entry(db, user, entry)
        return
    raise HTTPException(409, SOURCE_RESTRICTED)


async def _require_protocol_output_readable(db, *, task, action, user, output):
    """A legacy Protocol Action snapshot still contains an exact private Record."""
    from app.services.research_runtime import canonical_digest

    try:
        record_payload = output["record"]
        record_id = UUID(str(record_payload["record_id"]))
        record_version = record_payload["record_version"]
        if type(record_version) is not int or record_version < 1:
            raise ValueError("An exact Record version is required")
        typed = await db.scalar(
            select(ResearchProtocolRun).where(
                ResearchProtocolRun.action_id == action.id
            )
        )
        record = await db.get(Record, (record_id, record_version))
        if (
            typed is None
            or record is None
            or typed.protocol_id != record.protocol_id
            or typed.protocol_version != record.protocol_version
            or typed.record_id != record_id
            or typed.record_version != record_version
            or record_payload["metadata"]["sha1"] != record.hash
            or canonical_digest(record_payload["data"]) != canonical_digest(record.data)
        ):
            raise ValueError("The sealed Record no longer matches its exact source")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(409, SOURCE_RESTRICTED) from exc
    await require_artifact_source_readable(
        db,
        task=task,
        user=user,
        artifact_type="record",
        artifact_id=str(record_id),
        artifact_version=str(record_version),
    )


async def require_evidence_source_readable(db, evidence, user):
    from app.services.research_runtime import require_research_capability

    task = await db.get(ResearchTask, evidence.task_id)
    project = await db.get(Project, task.project_id) if task else None
    if task is None or task.archived_at is not None or project is None:
        raise HTTPException(403, SOURCE_RESTRICTED)
    await require_research_capability(
        db, user=user, project=project, capability="research.read"
    )
    await require_artifact_source_readable(
        db,
        task=task,
        user=user,
        artifact_type=evidence.artifact_type,
        artifact_id=evidence.artifact_id,
        artifact_version=evidence.artifact_version,
    )


async def evidence_source_readable(db, evidence, user):
    try:
        await require_evidence_source_readable(db, evidence, user)
    except HTTPException as exc:
        if exc.status_code in HIDDEN_SOURCE_STATUSES:
            return False
        raise
    return True


async def require_claim_sources_readable(db, claim, user):
    ids = list(
        (
            await db.scalars(
                select(ResearchClaimEvidence.evidence_id).where(
                    ResearchClaimEvidence.claim_id == claim.id
                )
            )
        ).all()
    )
    for identity in ids:
        evidence = await db.get(ResearchEvidence, identity)
        if evidence is None or evidence.task_id != claim.task_id:
            raise HTTPException(403, SOURCE_RESTRICTED)
        await require_evidence_source_readable(db, evidence, user)


async def require_protocol_improvement_readable(db, proposal, user):
    from app.models.protocol import Protocol
    from app.services.workflow_definitions import require_protocol_read

    task = await db.get(ResearchTask, proposal.task_id)
    project = await db.get(Project, task.project_id) if task else None
    protocol = await db.get(Protocol, proposal.protocol_id)
    if (
        project is None
        or project.deleted_at is not None
        or protocol is None
        or protocol.deleted_at is not None
        or protocol.project_id != project.id
    ):
        raise HTTPException(403, SOURCE_RESTRICTED)
    await require_protocol_read(db, user, project, protocol)


async def visible_knowledge_evidence_links(db, links, user):
    """Keep published prose, but never disclose unauthorized original snapshots."""
    visible = []
    for link in links:
        evidence = await db.get(ResearchEvidence, link.evidence_id)
        source = link.source_snapshot
        if evidence is None or not isinstance(source, dict):
            continue
        if any(
            str(source.get(key)) != str(getattr(evidence, key))
            for key in (
                "id",
                "task_id",
                "artifact_type",
                "artifact_id",
                "artifact_version",
            )
        ):
            continue
        if await evidence_source_readable(db, evidence, user):
            visible.append(link)
    return visible


async def require_analysis_knowledge_evidence_readable(db, item, user):
    """Reauthorize sources when reading or promoting analysis candidates.

    Links survive ordinary text revisions. A new review or cross-scope copy
    must not silently drop an unreadable source, even if another link is still
    readable. Existing adopted prose keeps its own scope on ordinary reads.
    """
    checked = _knowledge_source_stack.get()
    if item.id in checked:
        raise HTTPException(409, "Knowledge source lineage is cyclic")
    token = _knowledge_source_stack.set(checked | {item.id})
    try:
        return await _analysis_knowledge_evidence_links(db, item, user)
    finally:
        _knowledge_source_stack.reset(token)


async def _analysis_knowledge_evidence_links(db, item, user):
    links = list(
        (
            await db.scalars(
                select(KnowledgeEvidenceLink)
                .where(KnowledgeEvidenceLink.knowledge_item_id == item.id)
                .order_by(
                    KnowledgeEvidenceLink.knowledge_revision,
                    KnowledgeEvidenceLink.created_at,
                    KnowledgeEvidenceLink.id,
                )
            )
        ).all()
    )
    # Preserve the existing contract for Knowledge not derived from a governed
    # analysis publication. Check both sides so a damaged link cannot hide its
    # provenance simply by changing the cached artifact type.
    evidence_by_id = {
        link.evidence_id: await db.get(ResearchEvidence, link.evidence_id)
        for link in links
    }
    if not any(
        (
            isinstance(link.source_snapshot, dict)
            and link.source_snapshot.get("artifact_type") == "analysis_publication"
        )
        or getattr(evidence_by_id[link.evidence_id], "artifact_type", None)
        == "analysis_publication"
        for link in links
    ):
        return []
    for link in links:
        evidence = evidence_by_id[link.evidence_id]
        source = link.source_snapshot
        if (
            evidence is None
            or not isinstance(source, dict)
            or link.knowledge_revision > item.revision
            or any(
                str(source.get(key)) != str(getattr(evidence, key))
                for key in (
                    "id", "task_id", "artifact_type", "artifact_id", "artifact_version"
                )
            )
        ):
            raise HTTPException(409, SOURCE_RESTRICTED)
        if evidence.quality_state != EvidenceQuality.VALIDATED.value:
            raise HTTPException(409, "Knowledge requires validated source Evidence")
        await require_evidence_source_readable(db, evidence, user)
    return links


async def require_task_asset_sources_readable(db, *, task_id, user):
    """Fail closed for indivisible review/result/AI contexts, never silently omit."""
    from app.services.research_assets import research_asset_bundle

    payload = await research_asset_bundle(db, task_id=task_id)
    await require_asset_snapshot_sources_readable(
        db, task_id=task_id, payload=payload, user=user
    )


async def require_asset_snapshot_sources_readable(db, *, task_id, payload, user):
    """Authorize only sources in this sealed package, not later unrelated assets."""
    task = await db.get(ResearchTask, task_id)
    if task is None or user is None or not isinstance(payload, dict):
        raise HTTPException(403, SOURCE_RESTRICTED)
    checked = set()

    async def source(item):
        if not isinstance(item, dict):
            raise HTTPException(409, SOURCE_RESTRICTED)
        try:
            identity = (
                item["artifact_type"],
                item["artifact_id"],
                item["artifact_version"],
            )
            if item.get("task_id") is not None and str(item["task_id"]) != str(task.id):
                raise ValueError("Source belongs to a different Task")
            if identity in checked:
                return
            await require_artifact_source_readable(
                db,
                task=task,
                user=user,
                artifact_type=identity[0],
                artifact_id=identity[1],
                artifact_version=identity[2],
            )
            checked.add(identity)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(409, SOURCE_RESTRICTED) from exc

    def entries(key):
        items = payload.get(key, [])
        if not isinstance(items, list):
            raise HTTPException(409, SOURCE_RESTRICTED)
        return items

    for item in entries("evidence"):
        await source(item)
    for asset in entries("data_assets"):
        if not isinstance(asset, dict) or not isinstance(asset.get("versions"), list):
            raise HTTPException(409, SOURCE_RESTRICTED)
        for version in asset["versions"]:
            if not isinstance(version, dict):
                raise HTTPException(409, SOURCE_RESTRICTED)
            await source(
                {
                    "artifact_type": "data_asset",
                    "artifact_id": asset.get("id"),
                    "artifact_version": str(version.get("version")),
                }
            )
    for key in ("claims", "knowledge_items", "protocol_improvements"):
        for item in entries(key):
            if not isinstance(item, dict) or not isinstance(
                item.get("evidence", []), list
            ):
                raise HTTPException(409, SOURCE_RESTRICTED)
            if key in {"knowledge_items", "protocol_improvements"}:
                try:
                    identity = UUID(str(item["id"]))
                except (KeyError, ValueError, TypeError) as exc:
                    raise HTTPException(409, SOURCE_RESTRICTED) from exc
                if key == "knowledge_items":
                    from app.services.knowledge import authorize_knowledge_item

                    knowledge = await db.get(KnowledgeItem, identity)
                    if (
                        knowledge is None
                        or knowledge.state == KnowledgeState.ARCHIVED.value
                    ):
                        raise HTTPException(403, SOURCE_RESTRICTED)
                    await authorize_knowledge_item(db, user, knowledge)
                else:
                    proposal = await db.get(ProtocolImprovementProposal, identity)
                    if (
                        proposal is None
                        or proposal.task_id != task.id
                        or str(proposal.protocol_id) != str(item.get("protocol_id"))
                    ):
                        raise HTTPException(403, SOURCE_RESTRICTED)
                    await require_protocol_improvement_readable(db, proposal, user)
            for link in item.get("evidence", []):
                if not isinstance(link, dict):
                    raise HTTPException(409, SOURCE_RESTRICTED)
                if isinstance(link.get("source_snapshot"), dict):
                    await source(link["source_snapshot"])
                else:
                    try:
                        identity = UUID(str(link["evidence_id"]))
                    except (KeyError, ValueError, TypeError) as exc:
                        raise HTTPException(409, SOURCE_RESTRICTED) from exc
                    evidence = await db.get(ResearchEvidence, identity)
                    if evidence is None or evidence.task_id != task.id:
                        raise HTTPException(403, SOURCE_RESTRICTED)
                    await source(
                        {
                            "artifact_type": evidence.artifact_type,
                            "artifact_id": evidence.artifact_id,
                            "artifact_version": evidence.artifact_version,
                        }
                    )
