"""AI-independent, bounded contracts for versioned manual Workflows.

This module validates structure, not authorization or asset existence. Callers
must load the exact Protocol/AnalysisPipeline revisions and build field catalogs
from those revisions before accepting conditions. It never invokes a model,
executes a Protocol, or reads a database.

The whole graph, including presentation, belongs to an immutable WorkflowRevision.
``workflow_revision_digest`` seals it; ``workflow_execution_digest`` omits titles
and positions and sorts stable IDs. Moving/reordering cards therefore does not
alter node identity or the execution contract. Neither digest grants permission.

Data bindings describe bounded, one-to-one Protocol values, separate from
control edges. Version 4 file references require an independently authorized and
sealed runtime receipt. A caller must resolve exact source Records and validate
the target Schema before dispatch. Accepting a valid graph is not a
promise that every node kind/condition is supported by an execution adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_serializer,
    model_validator,
)

MAX_WORKFLOW_NODES = 64
MAX_WORKFLOW_EDGES = 256
MAX_WORKFLOW_BINDINGS = 128
MAX_ANALYSIS_OUTPUTS = 128
MAX_INITIAL_VALUE_BYTES = 128 * 1024
MAX_GRAPH_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_ITEMS = 20_000

WorkflowIdentifier = Annotated[StrictStr, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
WorkflowScalarType = Literal["string", "number", "integer", "boolean"]
WorkflowValueType = Literal["string", "number", "integer", "boolean", "file"]
WorkflowScalar = (
    Annotated[StrictStr, Field(max_length=2_000)]
    | StrictBool
    | StrictInt
    | Annotated[float, Field(strict=True, allow_inf_nan=False)]
)


class WorkflowContractError(ValueError):
    """A graph or a resolved value cannot safely satisfy the contract."""


def _bounded_json(value: Any, byte_limit: int) -> bytes:
    remaining = MAX_JSON_ITEMS

    def visit(item: Any, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_JSON_DEPTH:
            raise WorkflowContractError("Workflow JSON exceeds the structural limit")
        if item is None or type(item) in {str, bool, int}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise WorkflowContractError("Workflow JSON numbers must be finite")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise WorkflowContractError("Workflow JSON keys must be strings")
                visit(child, depth + 1)
            return
        raise WorkflowContractError("Workflow values must be ordinary JSON values")

    visit(value, 0)
    try:
        result = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise WorkflowContractError("Workflow values must be valid JSON") from exc
    if len(result) > byte_limit:
        raise WorkflowContractError("Workflow JSON exceeds the byte limit")
    return result


class _WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkflowPosition(_WorkflowModel):
    x: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e6, le=1e6)]
    y: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e6, le=1e6)]


class WorkflowAnalysisRecordSource(_WorkflowModel):
    source_node_id: WorkflowIdentifier
    cardinality: Literal["one"] = "one"


class WorkflowAnalysisOutput(_WorkflowModel):
    """One named statistic, with an exact group key rather than a row index."""

    output_id: WorkflowIdentifier
    field: StrictStr = Field(min_length=1, max_length=255)
    statistic: Literal[
        "count",
        "missing",
        "invalid",
        "mean",
        "median",
        "min",
        "max",
        "sum",
        "sample_stddev",
    ]
    group: dict[
        Annotated[StrictStr, Field(min_length=1, max_length=255)], WorkflowScalar | None
    ] = Field(default_factory=dict, max_length=3)

    @field_validator("group", mode="before")
    @classmethod
    def validate_group(cls, value: Any):
        if type(value) is not dict:
            raise WorkflowContractError(
                "Analysis output groups must be explicit JSON objects"
            )
        return value

    @model_validator(mode="after")
    def validate_output(self):
        if not self.field.strip() or any(not key.strip() for key in self.group):
            raise WorkflowContractError("Analysis output fields must not be blank")
        _bounded_json(self.model_dump(mode="json"), 16 * 1024)
        return self


class WorkflowComputeOutput(_WorkflowModel):
    """One explicitly typed object path inside a Compute structured result."""

    output_id: WorkflowIdentifier
    path: list[Annotated[StrictStr, Field(min_length=1, max_length=255)]] = Field(
        min_length=1, max_length=16
    )
    value_type: WorkflowScalarType
    unit: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    nullable: StrictBool

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: Any):
        if type(value) is not list:
            raise WorkflowContractError("Compute output paths must be JSON key arrays")
        return value

    @model_validator(mode="after")
    def validate_output(self):
        if any(not key.strip() for key in self.path):
            raise WorkflowContractError("Compute output path keys must not be blank")
        if self.unit is not None and (
            not self.unit.strip()
            or self.unit != self.unit.strip()
            or self.value_type not in {"number", "integer"}
        ):
            raise WorkflowContractError(
                "Only numeric Compute outputs may declare a unit"
            )
        _bounded_json(self.model_dump(mode="json"), 16 * 1024)
        return self


class WorkflowComputeFileOutput(_WorkflowModel):
    """An explicit manifest file, never a path supplied by computed JSON."""

    output_id: WorkflowIdentifier
    mount_name: StrictStr = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$"
    )


class WorkflowNode(_WorkflowModel):
    node_id: WorkflowIdentifier
    kind: Literal["protocol", "analysis"]
    title: StrictStr = Field(default="", max_length=255)
    position: WorkflowPosition | None = None
    protocol_id: UUID | None = None
    protocol_version_id: UUID | None = None
    initial_values: dict[str, Any] = Field(default_factory=dict)
    pipeline_revision_id: UUID | None = None
    method_publication_id: UUID | None = None
    record_sources: list[WorkflowAnalysisRecordSource] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_NODES
    )
    input_policy: Literal["all_declared"] | None = None
    analysis_outputs: list[WorkflowAnalysisOutput] = Field(
        default_factory=list, max_length=MAX_ANALYSIS_OUTPUTS
    )
    analysis_kind: Literal["compute"] | None = None
    compute_outputs: list[WorkflowComputeOutput] = Field(
        default_factory=list, max_length=MAX_ANALYSIS_OUTPUTS
    )
    compute_file_outputs: list[WorkflowComputeFileOutput] = Field(
        default_factory=list, max_length=16
    )

    @model_serializer(mode="wrap")
    def preserve_legacy_node_json(self, handler):
        result = handler(self)
        if not self.compute_file_outputs:
            # Additive v4 fields cannot alter sealed v1/v2/v3 graphs.
            result.pop("compute_file_outputs", None)
        if self.analysis_kind is None and not self.compute_outputs:
            # v3 defaults must not change either v1 or builtin v2 digests.
            result.pop("analysis_kind", None)
            result.pop("compute_outputs", None)
        if (
            self.method_publication_id is None
            and not self.record_sources
            and self.input_policy is None
            and not self.analysis_outputs
        ):
            # Adding v2 defaults must never change a sealed v1 revision/run.
            for key in (
                "method_publication_id",
                "record_sources",
                "input_policy",
                "analysis_outputs",
            ):
                result.pop(key, None)
        return result

    @field_validator(
        "record_sources",
        "analysis_outputs",
        "compute_outputs",
        "compute_file_outputs",
        mode="before",
    )
    @classmethod
    def validate_analysis_lists(cls, value: Any):
        if type(value) is not list:
            raise WorkflowContractError("Analysis node collections must be JSON arrays")
        return value

    @field_validator("initial_values", mode="before")
    @classmethod
    def validate_initial_values(cls, value: Any) -> dict[str, Any]:
        if type(value) is not dict:
            raise WorkflowContractError("Workflow initial values must be a JSON object")
        _bounded_json(value, MAX_INITIAL_VALUE_BYTES)
        return value

    @model_validator(mode="after")
    def validate_node_kind(self):
        if self.kind == "protocol":
            if self.protocol_id is None or self.protocol_version_id is None:
                raise WorkflowContractError(
                    "Protocol nodes require exact protocol_id and protocol_version_id"
                )
            if (
                self.pipeline_revision_id is not None
                or self.method_publication_id is not None
                or self.record_sources
                or self.input_policy is not None
                or self.analysis_outputs
                or self.analysis_kind is not None
                or self.compute_outputs
                or self.compute_file_outputs
            ):
                raise WorkflowContractError(
                    "Protocol nodes cannot contain an analysis pipeline revision"
                )
        elif (
            self.protocol_id is not None
            or self.protocol_version_id is not None
            or self.initial_values
        ):
            raise WorkflowContractError("Analysis nodes cannot contain Protocol inputs")
        elif self.method_publication_id is not None:
            if self.analysis_kind == "compute" and self.analysis_outputs:
                raise WorkflowContractError(
                    "Compute nodes cannot contain builtin statistic outputs"
                )
            if self.analysis_kind is None and (
                self.compute_outputs or self.compute_file_outputs
            ):
                raise WorkflowContractError(
                    "Compute outputs require an explicit compute analysis kind"
                )
            if (
                self.pipeline_revision_id is not None
                or not self.record_sources
                or self.input_policy != "all_declared"
            ):
                raise WorkflowContractError(
                    "Published analysis nodes require explicit all_declared Record sources and no private revision"
                )
            source_ids = [item.source_node_id for item in self.record_sources]
            if len(source_ids) != len(set(source_ids)):
                raise WorkflowContractError("Analysis Record sources must be unique")
            output_ids = [
                item.output_id
                for item in (
                    *self.analysis_outputs,
                    *self.compute_outputs,
                    *self.compute_file_outputs,
                )
            ]
            if len(output_ids) != len(set(output_ids)):
                raise WorkflowContractError("Analysis output IDs must be unique")
        elif (
            self.pipeline_revision_id is None
            or self.record_sources
            or self.input_policy is not None
            or self.analysis_outputs
            or self.analysis_kind is not None
            or self.compute_outputs
            or self.compute_file_outputs
        ):
            raise WorkflowContractError(
                "Legacy analysis nodes require an exact pipeline_revision_id"
            )
        return self


def _matches_scalar_type(value: Any, value_type: WorkflowScalarType) -> bool:
    if value_type == "string":
        return type(value) is str
    if value_type == "boolean":
        return type(value) is bool
    if value_type == "integer":
        return type(value) is int
    # bool is an int subclass in Python, but never a scientific numeric value.
    return type(value) is int or (type(value) is float and math.isfinite(value))


class WorkflowCondition(_WorkflowModel):
    """One scalar comparison against the source node's authoritative output.

    Path segments are literal object keys, not JSONPath, dotted expressions,
    Python attributes, wildcards or list indices. Missing/null is an error even
    for ``ne``; it must never silently select another branch.
    """

    path: list[Annotated[StrictStr, Field(min_length=1, max_length=255)]] = Field(
        min_length=1, max_length=8
    )
    value_type: WorkflowScalarType
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: WorkflowScalar
    unit: StrictStr | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_comparison(self):
        if not _matches_scalar_type(self.value, self.value_type):
            raise WorkflowContractError(
                "Workflow condition value does not match its declared scalar type"
            )
        if self.operator not in {"eq", "ne"} and self.value_type not in {
            "number",
            "integer",
        }:
            raise WorkflowContractError("Ordering conditions require a numeric field")
        if self.unit is not None and self.value_type not in {"number", "integer"}:
            raise WorkflowContractError("Only numeric conditions may declare a unit")
        _bounded_json(self.model_dump(mode="json"), 8 * 1024)
        return self


class WorkflowEdge(_WorkflowModel):
    edge_id: WorkflowIdentifier
    source_node_id: WorkflowIdentifier
    target_node_id: WorkflowIdentifier
    condition: WorkflowCondition | None = None

    @model_validator(mode="after")
    def validate_not_self(self):
        if self.source_node_id == self.target_node_id:
            raise WorkflowContractError("Workflow nodes cannot depend on themselves")
        return self


class WorkflowBinding(_WorkflowModel):
    """One value from a direct Protocol/Analysis predecessor into a Protocol.

    Both paths address ``Record.data`` as ``['var', literal_field_key]``.
    File bindings require schema v4 and a separately authorized, immutable file
    receipt. Arrays, nested values, coercion and unit conversion remain excluded.
    """

    binding_id: WorkflowIdentifier
    source_node_id: WorkflowIdentifier
    source_path: list[Annotated[StrictStr, Field(min_length=1, max_length=255)]] = (
        Field(min_length=2, max_length=2)
    )
    target_node_id: WorkflowIdentifier
    target_path: list[Annotated[StrictStr, Field(min_length=1, max_length=255)]] = (
        Field(min_length=2, max_length=2)
    )
    value_type: WorkflowValueType
    unit: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    cardinality: Literal["one"] = "one"

    @field_validator("source_path", mode="before")
    @classmethod
    def validate_source_path(cls, value: Any) -> list[str]:
        if (
            type(value) is not list
            or len(value) != 2
            or value[0] not in ("var", "analysis")
        ):
            raise WorkflowContractError(
                "Workflow source binding paths require ['var', key] or ['analysis', output_id]"
            )
        return value

    @field_validator("target_path", mode="before")
    @classmethod
    def validate_variable_path(cls, value: Any) -> list[str]:
        if type(value) is not list or len(value) != 2 or value[0] != "var":
            raise WorkflowContractError(
                "Workflow binding paths require ['var', literal_field_key]"
            )
        return value

    @model_validator(mode="after")
    def validate_scalar_binding(self):
        if self.source_node_id == self.target_node_id:
            raise WorkflowContractError("Workflow bindings cannot read their own node")
        if self.unit is not None and self.value_type not in {"number", "integer"}:
            raise WorkflowContractError("Only numeric bindings may declare a unit")
        return self


def _topological_nodes(
    nodes: list[WorkflowNode], edges: list[WorkflowEdge]
) -> list[str]:
    node_ids = [node.node_id for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowContractError("Workflow node IDs must be unique")
    edge_ids = [edge.edge_id for edge in edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise WorkflowContractError("Workflow edge IDs must be unique")
    pairs = [(edge.source_node_id, edge.target_node_id) for edge in edges]
    if len(pairs) != len(set(pairs)):
        raise WorkflowContractError("Workflow control dependencies must be unique")

    dependencies = {node_id: set() for node_id in node_ids}
    for edge in edges:
        if (
            edge.source_node_id not in dependencies
            or edge.target_node_id not in dependencies
        ):
            raise WorkflowContractError("Workflow edge references an unknown node")
        dependencies[edge.target_node_id].add(edge.source_node_id)
    result: list[str] = []
    while dependencies:
        released = sorted(
            node_id for node_id, parents in dependencies.items() if not parents
        )
        if not released:
            raise WorkflowContractError("Workflow control dependencies contain a cycle")
        result.extend(released)
        for node_id in released:
            del dependencies[node_id]
        for parents in dependencies.values():
            parents.difference_update(released)
    return result


class WorkflowGraph(_WorkflowModel):
    schema_version: Literal[1, 2, 3, 4] = 1
    nodes: list[WorkflowNode] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    edges: list[WorkflowEdge] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_EDGES
    )
    bindings: list[WorkflowBinding] = Field(
        default_factory=list, max_length=MAX_WORKFLOW_BINDINGS
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        if type(value) is not int or value not in {1, 2, 3, 4}:
            raise WorkflowContractError(
                "Workflow schema_version must be integer 1, 2, 3 or 4"
            )
        return value

    @field_validator("nodes", "edges", "bindings", mode="before")
    @classmethod
    def validate_lists(cls, value: Any) -> list[Any]:
        if type(value) is not list:
            raise WorkflowContractError("Workflow collections must be JSON arrays")
        return value

    @model_validator(mode="after")
    def validate_graph(self):
        _topological_nodes(self.nodes, self.edges)
        by_node = {node.node_id: node for node in self.nodes}
        direct_edges = {
            (edge.source_node_id, edge.target_node_id) for edge in self.edges
        }
        for node in self.nodes:
            if self.schema_version < 4 and (
                node.compute_file_outputs
                or "compute_file_outputs" in node.model_fields_set
            ):
                raise WorkflowContractError(
                    "Compute file ports require Workflow schema_version 4"
                )
            if self.schema_version < 3 and (
                node.analysis_kind is not None
                or node.compute_outputs
                or {"analysis_kind", "compute_outputs"} & node.model_fields_set
            ):
                raise WorkflowContractError(
                    "Compute node fields require Workflow schema_version 3"
                )
            if node.method_publication_id is not None and self.schema_version < 2:
                raise WorkflowContractError(
                    "Published analysis nodes require Workflow schema_version 2 or 3"
                )
            if node.kind == "analysis" and self.schema_version >= 2:
                if node.method_publication_id is None:
                    raise WorkflowContractError(
                        "Workflow analysis requires a Project method publication"
                    )
                for reference in node.record_sources:
                    source = by_node.get(reference.source_node_id)
                    if source is None or source.kind != "protocol":
                        raise WorkflowContractError(
                            "Analysis Record sources must reference Protocol nodes"
                        )
                    if (source.node_id, node.node_id) not in direct_edges:
                        raise WorkflowContractError(
                            "Analysis Record sources require direct control dependencies"
                        )
        binding_ids = [binding.binding_id for binding in self.bindings]
        if len(set(binding_ids)) != len(binding_ids):
            raise WorkflowContractError("Workflow binding IDs must be unique")
        targets: set[tuple[str, tuple[str, ...]]] = set()
        for binding in self.bindings:
            if binding.value_type == "file" and self.schema_version < 4:
                raise WorkflowContractError(
                    "File bindings require Workflow schema_version 4"
                )
            source = by_node.get(binding.source_node_id)
            target = by_node.get(binding.target_node_id)
            if source is None or target is None:
                raise WorkflowContractError(
                    "Workflow binding references an unknown node"
                )
            if (
                target.kind != "protocol"
                or source.kind == "analysis"
                and self.schema_version < 2
            ):
                raise WorkflowContractError(
                    "Workflow bindings require a supported source and Protocol target"
                )
            expected_prefix = "var" if source.kind == "protocol" else "analysis"
            if binding.source_path[0] != expected_prefix:
                raise WorkflowContractError(
                    "Workflow binding path does not match its source kind"
                )
            if source.kind == "analysis" and binding.source_path[1] not in {
                item.output_id
                for item in (
                    *source.analysis_outputs,
                    *source.compute_outputs,
                    *source.compute_file_outputs,
                )
            }:
                raise WorkflowContractError(
                    "Workflow binding references an undeclared analysis output"
                )
            if (binding.source_node_id, binding.target_node_id) not in direct_edges:
                raise WorkflowContractError(
                    "Workflow bindings require a direct control dependency"
                )
            target_identity = (binding.target_node_id, tuple(binding.target_path))
            if target_identity in targets:
                raise WorkflowContractError(
                    "Workflow binding target fields must be unique"
                )
            targets.add(target_identity)
            if binding.target_path[1] in target.initial_values:
                raise WorkflowContractError(
                    "Workflow bindings cannot overwrite explicit initial values"
                )
        _bounded_json(self.model_dump(mode="json"), MAX_GRAPH_BYTES)
        return self


def validate_workflow_graph(payload: Any) -> WorkflowGraph:
    """Parse/revalidate a graph, including a previously constructed model.

    Frozen models still contain mutable JSON containers. Revalidation at each
    trust boundary avoids relying on a caller not having changed such a list.
    """
    if isinstance(payload, WorkflowGraph):
        payload = payload.model_dump(mode="json")
    return WorkflowGraph.model_validate(payload)


def topological_node_ids(graph: WorkflowGraph) -> list[str]:
    """Return a deterministic order based on IDs, never canvas/list positions."""
    validated = validate_workflow_graph(graph)
    return _topological_nodes(validated.nodes, validated.edges)


def workflow_revision_digest(graph: WorkflowGraph) -> str:
    validated = validate_workflow_graph(graph)
    return hashlib.sha256(
        _bounded_json(validated.model_dump(mode="json"), MAX_GRAPH_BYTES)
    ).hexdigest()


def workflow_execution_digest(graph: WorkflowGraph) -> str:
    validated = validate_workflow_graph(graph)
    payload = validated.model_dump(mode="json")
    payload["nodes"] = sorted(
        [
            {
                key: value
                for key, value in node.items()
                if key not in {"title", "position"}
            }
            for node in payload["nodes"]
        ],
        key=lambda item: item["node_id"],
    )
    payload["edges"] = sorted(payload["edges"], key=lambda item: item["edge_id"])
    payload["bindings"] = sorted(
        payload["bindings"], key=lambda item: item["binding_id"]
    )
    return hashlib.sha256(_bounded_json(payload, MAX_GRAPH_BYTES)).hexdigest()


class WorkflowFieldSpec(_WorkflowModel):
    """Trusted value specification extracted from an exact asset revision."""

    value_type: WorkflowValueType
    nullable: StrictBool = False
    unit: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    file_extensions: (
        list[Annotated[StrictStr, Field(pattern=r"^[a-z0-9]{1,32}$")]] | None
    ) = Field(default=None, min_length=1, max_length=32)

    @model_serializer(mode="wrap")
    def preserve_scalar_json(self, handler):
        result = handler(self)
        if self.value_type != "file":
            result.pop("file_extensions", None)
        return result

    @model_validator(mode="after")
    def validate_file_spec(self):
        if self.value_type == "file" and self.unit is not None:
            raise WorkflowContractError("File ports cannot declare numeric units")
        if self.value_type != "file" and self.file_extensions is not None:
            raise WorkflowContractError("Only file ports may declare extensions")
        if self.file_extensions is not None and self.file_extensions != sorted(
            set(self.file_extensions)
        ):
            raise WorkflowContractError("File extensions must be sorted and unique")
        return self


WorkflowFieldCatalog = Mapping[tuple[str, ...], WorkflowFieldSpec]


def _validate_condition_catalog(
    condition: WorkflowCondition, catalog: WorkflowFieldCatalog
) -> None:
    spec = catalog.get(tuple(condition.path))
    if not isinstance(spec, WorkflowFieldSpec):
        raise WorkflowContractError("Workflow condition references an unknown field")
    if condition.value_type != spec.value_type:
        raise WorkflowContractError(
            "Workflow condition conflicts with the pinned field type"
        )
    if condition.unit != spec.unit:
        raise WorkflowContractError(
            "Workflow condition conflicts with the pinned field unit"
        )


def validate_workflow_conditions(
    graph: WorkflowGraph,
    field_catalog_by_node: Mapping[str, WorkflowFieldCatalog],
) -> None:
    """Require exact, authoritative source-node fields before saving/publishing."""
    for edge in validate_workflow_graph(graph).edges:
        if edge.condition is not None:
            _validate_condition_catalog(
                edge.condition, field_catalog_by_node.get(edge.source_node_id, {})
            )


def evaluate_workflow_condition(
    condition: WorkflowCondition,
    output: Any,
    field_catalog: WorkflowFieldCatalog,
) -> bool:
    """Compare one authorized, persisted source output; do not infer missing data."""
    condition = WorkflowCondition.model_validate(condition.model_dump(mode="json"))
    _validate_condition_catalog(condition, field_catalog)
    value = output
    for segment in condition.path:
        if type(value) is not dict or segment not in value:
            raise WorkflowContractError("Workflow condition output field is missing")
        value = value[segment]
    if not _matches_scalar_type(value, condition.value_type):
        raise WorkflowContractError(
            "Workflow condition output has a missing or conflicting type"
        )
    if condition.operator == "eq":
        return value == condition.value
    if condition.operator == "ne":
        return value != condition.value
    if condition.operator == "gt":
        return value > condition.value
    if condition.operator == "gte":
        return value >= condition.value
    if condition.operator == "lt":
        return value < condition.value
    return value <= condition.value


class WorkflowEdgeOutcome(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowJoinDecision(_WorkflowModel):
    state: Literal["waiting", "ready", "branch_not_selected", "blocked"]
    active_count: int
    inactive_count: int
    pending_count: int
    failed_count: int
    cancelled_count: int


def evaluate_all_active_join(
    outcomes: Iterable[WorkflowEdgeOutcome | str],
) -> WorkflowJoinDecision:
    """Wait for all incoming edges; only selected, successful edges release work.

    ``active`` means the parent completed successfully and its edge condition is
    true (or absent). ``inactive`` means false or an upstream branch was not
    selected. Parent failure/rejection, cancellation, and predicate errors must
    never be mapped to ``inactive``. The runtime records those as failed or
    cancelled, and keeps this decision separate from Action execution status.
    """
    counts: Counter[WorkflowEdgeOutcome] = Counter()
    total = 0
    for value in outcomes:
        total += 1
        if total > MAX_WORKFLOW_EDGES:
            raise WorkflowContractError("Workflow join exceeds the incoming edge limit")
        try:
            counts[WorkflowEdgeOutcome(value)] += 1
        except (ValueError, TypeError) as exc:
            raise WorkflowContractError(
                "Unknown Workflow incoming edge outcome"
            ) from exc
    if counts[WorkflowEdgeOutcome.PENDING]:
        state = "waiting"
    elif counts[WorkflowEdgeOutcome.FAILED] or counts[WorkflowEdgeOutcome.CANCELLED]:
        state = "blocked"
    elif total == 0 or counts[WorkflowEdgeOutcome.ACTIVE]:
        state = "ready"
    else:
        state = "branch_not_selected"
    return WorkflowJoinDecision(
        state=state,
        active_count=counts[WorkflowEdgeOutcome.ACTIVE],
        inactive_count=counts[WorkflowEdgeOutcome.INACTIVE],
        pending_count=counts[WorkflowEdgeOutcome.PENDING],
        failed_count=counts[WorkflowEdgeOutcome.FAILED],
        cancelled_count=counts[WorkflowEdgeOutcome.CANCELLED],
    )
