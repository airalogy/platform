"""Static client/server contract shared by the host and isolated executor."""

from pathlib import Path
from airalogy.assigner.graph import (
    extract_assigner_graph_nodes_from_aimd,
    extract_server_assigner_graph_nodes_from_file,
    validate_assigner_graph,
)


def add_client_assigners(aimd, assigner_path, assigners, schema):
    """Use the pinned core graph validator; never execute JS in the Python host."""
    inline = extract_assigner_graph_nodes_from_aimd(aimd)
    clients = [node for node in inline if node.runtime == "client"]
    if not clients:
        return assigners, None
    servers = (
        extract_server_assigner_graph_nodes_from_file(assigner_path)
        if Path(assigner_path).is_file()
        else [node for node in inline if node.runtime == "server"]
    )
    nodes = [*servers, *clients]
    validate_assigner_graph(nodes)
    properties = schema.get("properties", {})
    for node in clients:
        if set(node.assigned_fields) & set(node.dependent_fields):
            raise ValueError("Client assigner cannot depend on its own output")
        for field in [*node.dependent_fields, *node.assigned_fields]:
            parts = field.split(".")
            spec = properties.get(parts[0])
            if len(parts) == 2 and spec:
                item = spec.get("items", {})
                if "$ref" in item:
                    item = schema.get("$defs", {}).get(item["$ref"].split("/")[-1], {})
                spec = item.get("properties", {}).get(parts[1])
            if spec is None or len(parts) > 2:
                raise ValueError(
                    f"Client assigner field {field} not defined in Protocol"
                )
        for field in node.assigned_fields:
            if field in assigners:
                raise ValueError(f"Client and server assigners both write {field}")
            assigners[field] = dict(
                id=node.id,
                runtime="client",
                mode=node.mode,
                dependent_fields=node.dependent_fields,
                assigned_fields=node.assigned_fields,
            )
    # Preserve both runtimes in the visual dependency graph.
    graph_nodes, edges = {}, []
    outputs = {field for node in nodes for field in node.assigned_fields}
    for node in nodes:
        name = f"{node.runtime}:{node.id}"
        graph_nodes[name] = {"name": name, "type": "assigner"}
        for field in [*node.dependent_fields, *node.assigned_fields]:
            graph_nodes[field] = {
                "name": field,
                "type": "assigned_field" if field in outputs else "dependent_field",
            }
        edges.extend((field, name) for field in node.dependent_fields)
        edges.extend((name, field) for field in node.assigned_fields)
    return assigners, {"nodes": list(graph_nodes.values()), "edges": edges}
