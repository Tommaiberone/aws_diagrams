"""
Parse a Python diagrams source file into the editor's JSON state format.

Handles the most common patterns:
  - with Diagram("name", direction="LR", theme="neutral"):
  - with Cluster("label"): / with Group("label"):
  - var = SomeNode("label")
  - a >> b          (directed edge)
  - a << b          (reverse edge)
  - a - b           (undirected)
  - a >> b >> c     (chained)
  - [a, b] >> c     (fan-in)
  - a >> [b, c]     (fan-out)
  - a >> Edge(label="x") >> b
"""
import ast
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def parse_diagram_code(code: str) -> dict:
    """
    Parse Python diagrams code and return an editor state dict:
    {name, direction, theme, elements: [...cytoscape elements...]}
    Raises ValueError on syntax errors or if no Diagram block is found.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}") from exc

    class_types = _collect_imports(tree)
    visitor = _DiagramVisitor(class_types)
    visitor.visit(tree)

    if not visitor.found_diagram:
        raise ValueError("No 'with Diagram(...)' block found in the file.")

    _auto_layout(visitor.elements)

    return {
        "name":      visitor.diagram_name,
        "direction": visitor.diagram_direction,
        "theme":     visitor.diagram_theme,
        "elements":  visitor.elements,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Import collection
# ──────────────────────────────────────────────────────────────────────────────

def _collect_imports(tree: ast.AST) -> dict:
    """
    Return {ClassName: "provider.module.ClassName"} from
    'from diagrams.X.Y import A, B as C' statements.
    """
    result: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] == "diagrams" and len(parts) >= 3:
                provider, module = parts[1], parts[2]
                for alias in node.names:
                    # alias.name is the original class name; asname is the 'as X' rename
                    local_name = alias.asname or alias.name
                    result[local_name] = f"{provider}.{module}.{alias.name}"
    return result


# ──────────────────────────────────────────────────────────────────────────────
# AST visitor
# ──────────────────────────────────────────────────────────────────────────────

class _DiagramVisitor(ast.NodeVisitor):
    def __init__(self, class_types: dict):
        self._class_types = class_types
        self.found_diagram = False

        self.diagram_name      = "Imported Diagram"
        self.diagram_direction = "LR"
        self.diagram_theme     = "neutral"
        self.elements: list    = []

        self._var_map: dict = {}       # python var name → cytoscape node id
        self._cluster_stack: list = [] # stack of cluster node ids
        self._counter = 0

    # ── id generator ──────────────────────────────────────────────────────────
    def _uid(self) -> str:
        self._counter += 1
        return f"imp{self._counter}"

    # ── top-level visit: find 'with Diagram(...)' ─────────────────────────────
    def visit_With(self, node: ast.With):
        for item in node.items:
            if not isinstance(item.context_expr, ast.Call):
                continue
            name = _call_name(item.context_expr)

            if name == "Diagram":
                self.found_diagram = True
                self._parse_diagram_call(item.context_expr)
                self._visit_body(node.body)
                return  # process only first Diagram block

            if name in ("Cluster", "Group"):
                cl_id = self._uid()
                label = _str_arg(item.context_expr, 0) or "Cluster"
                self.elements.append({
                    "group":   "nodes",
                    "classes": "cluster",
                    "data":    {"id": cl_id, "label": label, "isCluster": True},
                    "position": {"x": 0, "y": 0},
                })
                self._cluster_stack.append(cl_id)
                self._visit_body(node.body)
                self._cluster_stack.pop()
                return

        # Not a Diagram/Cluster with — recurse into body looking for one
        self.generic_visit(node)

    # ── diagram metadata ──────────────────────────────────────────────────────
    def _parse_diagram_call(self, call: ast.Call):
        name = _str_arg(call, 0)
        if name:
            self.diagram_name = name
        for kw in call.keywords:
            try:
                val = ast.literal_eval(kw.value)
            except Exception:
                continue
            if kw.arg == "direction":
                self.diagram_direction = str(val)
            elif kw.arg == "theme":
                self.diagram_theme = str(val)

    # ── statement dispatcher ──────────────────────────────────────────────────
    def _visit_body(self, body: list):
        for stmt in body:
            self.visit(stmt)

    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) != 1:
            return
        target = node.targets[0]

        if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
            self._try_create_node(target.id, node.value)

        # Tuple assignment: a, b = NodeA("x"), NodeB("y")
        elif isinstance(target, ast.Tuple) and isinstance(node.value, (ast.Tuple, ast.List)):
            for t, v in zip(target.elts, node.value.elts):
                if isinstance(t, ast.Name) and isinstance(v, ast.Call):
                    self._try_create_node(t.id, v)

    def visit_Expr(self, node: ast.Expr):
        self._extract_connections(node.value)

    # ── node creation ─────────────────────────────────────────────────────────
    def _try_create_node(self, var_name: str, call: ast.Call):
        cls = _call_name(call)
        if cls not in self._class_types:
            return
        label = _str_arg(call, 0) or cls
        nid   = self._uid()

        data: dict = {
            "id":    nid,
            "label": label,
            "type":  self._class_types[cls],
            "icon":  "",  # filled in by the endpoint from the node catalog
        }
        if self._cluster_stack:
            data["parent"] = self._cluster_stack[-1]

        self.elements.append({
            "group":    "nodes",
            "data":     data,
            "position": {"x": 0, "y": 0},  # overwritten by _auto_layout
        })
        self._var_map[var_name] = nid

    # ── edge extraction ───────────────────────────────────────────────────────
    def _extract_connections(self, expr: ast.expr):
        if not isinstance(expr, ast.BinOp):
            return
        if not isinstance(expr.op, (ast.RShift, ast.LShift, ast.Sub)):
            return

        left, right = expr.left, expr.right

        # Pattern: (a >> Edge(label="x")) >> b
        if (isinstance(left, ast.BinOp)
                and isinstance(left.op, (ast.RShift,))
                and isinstance(left.right, ast.Call)
                and _call_name(left.right) == "Edge"):
            label = _kw_str(left.right, "label") or ""
            for s in self._resolve_ids(left.left):
                for t in self._resolve_ids(right):
                    self._add_edge(s, t, label)
            return

        # Recurse into left to handle chains (a >> b >> c creates a→b and b→c)
        src_ids = self._chain_ids(left)
        tgt_ids = self._resolve_ids(right)
        for s in src_ids:
            for t in tgt_ids:
                self._add_edge(s, t, "")

    def _chain_ids(self, expr: ast.expr) -> list:
        """
        Walk a chain expression, creating edges along the way, and return
        the terminal node IDs (used as source for the next step).
        """
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.RShift, ast.LShift, ast.Sub)):
            src_ids = self._chain_ids(expr.left)
            tgt_ids = self._resolve_ids(expr.right)
            for s in src_ids:
                for t in tgt_ids:
                    self._add_edge(s, t, "")
            return tgt_ids
        return self._resolve_ids(expr)

    def _resolve_ids(self, expr: ast.expr) -> list:
        """Resolve a Name or List[Name] to cytoscape node IDs."""
        if isinstance(expr, ast.Name):
            nid = self._var_map.get(expr.id)
            return [nid] if nid else []
        if isinstance(expr, (ast.List, ast.Tuple)):
            ids = []
            for elt in expr.elts:
                ids.extend(self._resolve_ids(elt))
            return ids
        return []

    def _add_edge(self, src: str, tgt: str, label: str):
        self.elements.append({
            "group": "edges",
            "data":  {"id": self._uid(), "source": src, "target": tgt, "label": label},
        })


# ──────────────────────────────────────────────────────────────────────────────
# Auto-layout: simple grid for imported nodes
# ──────────────────────────────────────────────────────────────────────────────

def _auto_layout(elements: list):
    """Assign grid positions to nodes that have position {x:0, y:0}."""
    reg_nodes = [
        e for e in elements
        if e.get("group") == "nodes"
        and not e.get("data", {}).get("isCluster")
        and not e.get("data", {}).get("parent")  # top-level only
    ]
    cols = max(1, min(5, len(reg_nodes)))
    for i, node in enumerate(reg_nodes):
        node["position"] = {
            "x": (i % cols) * 160 + 120,
            "y": (i // cols) * 160 + 120,
        }


# ──────────────────────────────────────────────────────────────────────────────
# AST helpers
# ──────────────────────────────────────────────────────────────────────────────

def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _str_arg(call: ast.Call, index: int) -> Optional[str]:
    """Return the string value of a positional argument, or None."""
    if len(call.args) > index:
        try:
            val = ast.literal_eval(call.args[index])
            return str(val) if isinstance(val, str) else None
        except Exception:
            pass
    return None


def _kw_str(call: ast.Call, key: str) -> Optional[str]:
    """Return the string value of a keyword argument, or None."""
    for kw in call.keywords:
        if kw.arg == key:
            try:
                val = ast.literal_eval(kw.value)
                return str(val) if isinstance(val, str) else None
            except Exception:
                pass
    return None
