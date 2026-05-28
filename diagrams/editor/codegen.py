"""
Generate Python diagrams code from a JSON diagram state produced by the editor.

State format (mirrors Cytoscape.js .json()):
{
  "name": "My Diagram",
  "direction": "LR",
  "theme": "neutral",
  "elements": [
    {"group": "nodes", "data": {"id": "n1", "label": "Web", "type": "aws.compute.EC2"}},
    {"group": "nodes", "data": {"id": "cl1", "label": "VPC", "isCluster": true}},
    {"group": "nodes", "data": {"id": "n2", "label": "DB", "type": "aws.database.RDS", "parent": "cl1"}},
    {"group": "edges", "data": {"id": "e1", "source": "n1", "target": "n2", "label": ""}}
  ]
}
"""
from collections import defaultdict


def generate(state: dict) -> str:
    name = state.get("name", "My Diagram")
    direction = state.get("direction", "LR")
    theme = state.get("theme", "neutral")
    elements = state.get("elements", [])

    all_nodes = [e for e in elements if e.get("group") == "nodes"]
    edges = [e for e in elements if e.get("group") == "edges"]
    clusters = [n for n in all_nodes if n.get("data", {}).get("isCluster")]
    reg_nodes = [n for n in all_nodes if not n.get("data", {}).get("isCluster")]

    # --- Collect imports ---
    imports: dict[str, set[str]] = defaultdict(set)
    imports["diagrams"].add("Diagram")
    if clusters:
        imports["diagrams"].add("Cluster")

    has_edge_label = any(e.get("data", {}).get("label") for e in edges)
    if has_edge_label:
        imports["diagrams"].add("Edge")

    for node in reg_nodes:
        parts = node.get("data", {}).get("type", "").split(".")
        if len(parts) >= 3:
            module_path = f"diagrams.{parts[0]}.{parts[1]}"
            imports[module_path].add(parts[2])

    # --- Variable names ---
    var_names = _assign_var_names(reg_nodes)

    # --- Build output ---
    lines: list[str] = []

    for mod in sorted(imports):
        cls_list = ", ".join(sorted(imports[mod]))
        lines.append(f"from {mod} import {cls_list}")

    lines.append("")

    diag_args = [f'"{name}"']
    if direction != "LR":
        diag_args.append(f'direction="{direction}"')
    if theme != "neutral":
        diag_args.append(f'theme="{theme}"')
    lines.append(f"with Diagram({', '.join(diag_args)}):")

    INDENT = "    "

    # Cluster id → list of child node ids
    cluster_children: dict[str, list] = {
        cl["data"]["id"]: [] for cl in clusters
    }
    for node in reg_nodes:
        parent = node.get("data", {}).get("parent")
        if parent and parent in cluster_children:
            cluster_children[parent].append(node["data"]["id"])

    standalone = [
        n for n in reg_nodes if not n.get("data", {}).get("parent")
    ]

    for node in standalone:
        _write_node(lines, node["data"], var_names, INDENT)

    for cl in clusters:
        cl_data = cl["data"]
        lines.append(f'{INDENT}with Cluster("{cl_data.get("label", "Cluster")}"):')
        for nid in cluster_children.get(cl_data["id"], []):
            node = next(
                (n for n in reg_nodes if n["data"]["id"] == nid), None
            )
            if node:
                _write_node(lines, node["data"], var_names, INDENT * 2)

    if edges:
        lines.append("")

    for edge in edges:
        ed = edge.get("data", {})
        src = var_names.get(ed.get("source", ""))
        tgt = var_names.get(ed.get("target", ""))
        if not src or not tgt:
            continue
        label = ed.get("label", "")
        if label:
            lines.append(f'{INDENT}{src} >> Edge(label="{label}") >> {tgt}')
        else:
            lines.append(f"{INDENT}{src} >> {tgt}")

    return "\n".join(lines) + "\n"


def _write_node(lines: list, data: dict, var_names: dict, indent: str) -> None:
    parts = data.get("type", "").split(".")
    cls = parts[-1] if parts and parts[-1] else "Node"
    var = var_names.get(data["id"], data["id"])
    label = data.get("label", cls)
    lines.append(f'{indent}{var} = {cls}("{label}")')


def _assign_var_names(nodes: list) -> dict[str, str]:
    """Unique, readable Python variable name per node id."""
    import keyword

    def _safe(base: str) -> str:
        return f"{base}_svc" if keyword.iskeyword(base) else base

    total: dict[str, int] = defaultdict(int)
    for node in nodes:
        parts = node.get("data", {}).get("type", "").split(".")
        base = _safe(parts[-1].lower() if parts and parts[-1] else "node")
        total[base] += 1

    usage: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for node in nodes:
        nid = node["data"]["id"]
        parts = node.get("data", {}).get("type", "").split(".")
        base = _safe(parts[-1].lower() if parts and parts[-1] else "node")
        usage[base] += 1
        names[nid] = base if total[base] == 1 else f"{base}_{usage[base]}"
    return names
