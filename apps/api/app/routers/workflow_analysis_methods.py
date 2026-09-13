"""Explicitly shared Project method snapshots; no Record sharing or execution."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.database import DBSession
from app.routers.depends import CurrentUser
from app.services.workflow_analysis_methods import (
    MethodPublicationConfirm,
    MethodPublicationDraft,
    confirm_publication,
    get_method,
    list_methods,
    preview_publication,
    publication_payload,
)
from app.services.workflow_contracts import (
    MAX_ANALYSIS_OUTPUTS,
    WorkflowComputeFileOutput,
)
from app.services.workflow_definitions import scope

router = APIRouter(
    prefix="/workflow-analysis-methods", tags=["workflow-analysis-methods"]
)


@router.get("")
async def get_methods(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await scope(db_session, current_user, project_id)
    unavailable = []
    items = await list_methods(
        db_session, current_user, project, unavailable=unavailable
    )
    return {"items": items, "unavailable": unavailable}


@router.post("/preview")
async def preview_method(
    params: MethodPublicationDraft,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await preview_publication(db_session, current_user, params)


@router.post("/confirm")
async def confirm_method(
    params: MethodPublicationConfirm, current_user: CurrentUser, db_session: DBSession
):
    method = await confirm_publication(db_session, current_user, params)
    await db_session.commit()
    return publication_payload(method)


class OutputPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outputs: list[dict] = Field(default_factory=list, max_length=MAX_ANALYSIS_OUTPUTS)
    file_outputs: list[WorkflowComputeFileOutput] = Field(
        default_factory=list, max_length=16
    )


@router.post("/{publication_id}/outputs/preview")
async def preview_outputs(
    publication_id: UUID,
    params: OutputPreview,
    current_user: CurrentUser,
    db_session: DBSession,
):
    from app.services.workflow_analysis_contracts import analysis_output_catalog

    method = await get_method(db_session, current_user, publication_id)
    try:
        if method.compute_contract:
            from app.services.workflow_compute_contracts import compute_output_catalog

            catalog = compute_output_catalog(
                method.compute_contract["result_schema"], params.outputs
            )
            from app.services.workflow_file_contracts import compute_file_output_catalog

            file_catalog = compute_file_output_catalog(
                method.recipe, params.file_outputs
            )
            if catalog.keys() & file_catalog.keys():
                raise ValueError("Scalar and file output IDs must be unique")
            catalog.update(file_catalog)
        else:
            if params.file_outputs:
                raise ValueError("Builtin analysis methods do not produce file ports")
            catalog = analysis_output_catalog(
                method.recipe, method.input_fields, params.outputs
            )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "fields": [
            {"path": list(path), "title": path[-1], **spec.model_dump(mode="json")}
            for path, spec in catalog.items()
        ]
    }


@router.get("/{publication_id}/outputs/catalog")
async def output_catalog(
    publication_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    method = await get_method(db_session, current_user, publication_id)
    if not method.compute_contract:
        return {"kind": "builtin", "fields": []}
    from app.services.workflow_compute_contracts import compute_result_fields
    from app.services.workflow_file_contracts import compute_file_output_catalog

    file_fields = []
    for item in method.recipe.get("output_files", []):
        try:
            port = WorkflowComputeFileOutput(
                output_id="file", mount_name=item["mount_name"]
            )
            spec = compute_file_output_catalog(method.recipe, [port])[
                ("analysis", "file")
            ]
        except (ValueError, KeyError):
            # An output without a supported extension remains downloadable, but
            # cannot be represented by a downstream Protocol FileId port.
            continue
        file_fields.append(
            {
                "mount_name": item["mount_name"],
                "title": item["asset_name"],
                "media_type": item["media_type"],
                "max_bytes": item["max_bytes"],
                "required": item.get("required", True),
                **spec.model_dump(mode="json"),
            }
        )

    return {
        "kind": "compute",
        "fields": compute_result_fields(method.compute_contract["result_schema"]),
        "file_fields": file_fields,
    }
