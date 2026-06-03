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

    _auto_layout(visitor.elements, visitor.diagram_direction)

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
                cl_data: dict = {"id": cl_id, "label": label, "isCluster": True}
                if self._cluster_stack:
                    cl_data["parent"] = self._cluster_stack[-1]
                self.elements.append({
                    "group":   "nodes",
                    "classes": "cluster",
                    "data":    cl_data,
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
# Auto-layout: cluster-aware layered layout (no overlaps guaranteed)
# ──────────────────────────────────────────────────────────────────────────────

def _auto_layout(elements: list, direction: str = "LR"):
    """
    Hierarchical cluster-aware layered layout.

    - Only *leaf* clusters (no nested cluster children) snap their members to
      one column; outer clusters let each direct child keep its natural layer.
      This preserves the topological flow direction even inside deep nesting
      (e.g. IGW stays near Internet, TGW Attachment stays near TGW).
    - Direct children of non-leaf clusters are placed as standalone nodes.
    - After column packing, a family-alignment pass ensures every node that
      belongs to the same root cluster shares the same cross-axis centre
      across all layers, so the outer cluster box is symmetric and compact.
    """
    from collections import defaultdict, deque

    # ── Index ──────────────────────────────────────────────────────────────────
    all_nodes: dict  = {}
    reg_ids:   set   = set()
    cluster_ids: set = set()

    for el in elements:
        if el.get("group") == "nodes":
            nid = el["data"]["id"]
            all_nodes[nid] = el
            if el["data"].get("isCluster"):
                cluster_ids.add(nid)
            else:
                reg_ids.add(nid)

    if not reg_ids:
        return

    # ── Directed graph on regular nodes ───────────────────────────────────────
    adj_out = defaultdict(list)
    in_deg  = defaultdict(int)
    for el in elements:
        if el.get("group") == "edges":
            s, t = el["data"]["source"], el["data"]["target"]
            if s in reg_ids and t in reg_ids:
                adj_out[s].append(t)
                in_deg[t] += 1

    # Keep a copy of original in-degrees (BFS zeroes them out)
    in_deg_orig: dict = dict(in_deg)

    # ── Topological BFS: longest-path layering ────────────────────────────────
    layer_of: dict = {nid: 0 for nid in reg_ids}
    queue = deque(nid for nid in reg_ids if in_deg[nid] == 0)
    while queue:
        nid = queue.popleft()
        for tgt in adj_out[nid]:
            in_deg[tgt] -= 1
            layer_of[tgt] = max(layer_of[tgt], layer_of[nid] + 1)
            if in_deg[tgt] == 0:
                queue.append(tgt)

    # ── Pull "source-only" nodes toward their targets ─────────────────────────
    # Nodes with no incoming edges default to layer 0 from BFS.  When their
    # outgoing targets are much later (e.g. a monitoring node that observes
    # services deep in the graph), layer 0 causes the node to extend its
    # parent cluster's bounding box far to the left/top, overlapping unrelated
    # elements.  Move such nodes to a layer near the average of their targets.
    for nid in reg_ids:
        if in_deg_orig.get(nid, 0) == 0 and adj_out[nid]:
            tgt_layers = [layer_of[t] for t in adj_out[nid] if t in layer_of]
            if tgt_layers:
                avg = sum(tgt_layers) / len(tgt_layers)
                if avg > layer_of[nid] + 2:
                    layer_of[nid] = round(avg)

    # ── Identify leaf clusters (no nested cluster children) ────────────────────
    leaf_clusters: set = {
        cl_id for cl_id in cluster_ids
        if not any(all_nodes[cid]["data"].get("parent") == cl_id for cid in cluster_ids)
    }

    # ── Snap children of LEAF clusters (spread-limited) ───────────────────────
    # A leaf cluster is snapped only when all *connected* members span ≤ 4
    # layers.  Wide-spread clusters (e.g. a "services" cluster where one member
    # is also a late-stage processor after an async pipeline) are left
    # unsnapped so they don't create backwards edges.
    _SNAP_SPREAD = 4

    cluster_children: dict = {}
    snappable_leaf: set = set()

    for cl_id in cluster_ids:
        ch = [nid for nid in reg_ids if all_nodes[nid]["data"].get("parent") == cl_id]
        cluster_children[cl_id] = sorted(ch)
        if not ch or cl_id not in leaf_clusters:
            continue
        connected = [c for c in ch if in_deg_orig.get(c, 0) > 0 or adj_out[c]]
        isolated  = [c for c in ch if c not in connected]
        if connected:
            max_l = max(layer_of[c] for c in connected)
            min_l = min(layer_of[c] for c in connected)
            spread = max_l - min_l
        else:
            max_l  = max(layer_of[c] for c in ch)
            spread = 0
        if spread <= _SNAP_SPREAD:
            for c in ch:
                layer_of[c] = max_l
            snappable_leaf.add(cl_id)
        else:
            # Snap isolated (edge-free) nodes to the median layer of connected ones
            if isolated and connected:
                mid = sorted(layer_of[c] for c in connected)[len(connected) // 2]
                for c in isolated:
                    layer_of[c] = mid

    # ── Post-snap propagation ─────────────────────────────────────────────────
    # Snap moves cluster members to later layers.  Non-cluster nodes that
    # receive edges from snapped members (e.g. S3 receiving from a CDN that
    # was snapped forward) must be updated so they don't end up in the same
    # column as the cluster they are NOT part of.
    snapped_members: set = {
        nid for cl_id in snappable_leaf for nid in cluster_children.get(cl_id, [])
    }
    adj_in: dict = defaultdict(list)
    for s, targets in adj_out.items():
        for t in targets:
            adj_in[t].append(s)

    relaxed = True
    while relaxed:
        relaxed = False
        for nid in reg_ids:
            if nid in snapped_members:
                continue
            for pred in adj_in.get(nid, []):
                new_l = layer_of.get(pred, 0) + 1
                if new_l > layer_of[nid]:
                    layer_of[nid] = new_l
                    relaxed = True

    # ── Compact layer indices ─────────────────────────────────────────────────
    used   = sorted(set(layer_of.values()))
    remap  = {v: i for i, v in enumerate(used)}
    for nid in reg_ids:
        layer_of[nid] = remap[layer_of[nid]]
    n_layers = len(used)

    # ── Build column → units ──────────────────────────────────────────────────
    col_units: list = [[] for _ in range(n_layers)]
    placed_cl: set  = set()

    for cl_id, ch in cluster_children.items():
        if ch and cl_id in snappable_leaf:
            col = layer_of[ch[0]]
            col_units[col].append(("cluster", cl_id, ch))
            placed_cl.add(cl_id)

    for nid in reg_ids:
        parent = all_nodes[nid]["data"].get("parent")
        # Place as standalone when: no parent, parent is non-leaf cluster,
        # or parent is a leaf cluster that was NOT snapped.
        if (not parent
                or (parent in cluster_ids and parent not in leaf_clusters)
                or (parent in leaf_clusters and parent not in snappable_leaf)):
            col_units[layer_of[nid]].append(("node", nid, []))

    # ── Geometry constants ─────────────────────────────────────────────────────
    NODE_SZ    = 56    # node width/height — matches Cytoscape stylesheet `width: 56`
    CHILD_GAP  = 120   # gap between siblings within a leaf cluster
    CL_PAD     = 30    # cluster padding — matches Cytoscape stylesheet `padding: 30`
    RENDER_PAD = 30    # extra padding per nesting level for cross_size computation
    LAYER_GAP  = 250   # distance between layers
    UNIT_GAP   = 70    # gap between sibling units in the same column
    MARGIN     = 130   # canvas margin
    CROSS_CTR  = 500   # cross-axis centre of the whole diagram

    vertical = direction in ("TB", "BT")
    reverse  = direction in ("RL", "BT")

    def cluster_depth(cl_id: str) -> int:
        p = all_nodes[cl_id]["data"].get("parent")
        return 1 + cluster_depth(p) if p and p in cluster_ids else 0

    def node_depth(nid: str) -> int:
        parent = all_nodes[nid]["data"].get("parent")
        return 1 + cluster_depth(parent) if parent and parent in cluster_ids else 0

    def cross_size(kind: str, uid: str, ch: list) -> float:
        """Effective cross size including space reserved for each ancestor cluster box."""
        if kind == "node":
            return NODE_SZ + 2 * node_depth(uid) * RENDER_PAD
        n = len(ch)
        base = max(n - 1, 0) * CHILD_GAP + NODE_SZ + 2 * CL_PAD
        return base + 2 * cluster_depth(uid) * RENDER_PAD

    def set_pos(nid: str, lc: float, cc: float) -> None:
        if vertical:
            all_nodes[nid]["position"] = {"x": round(cc), "y": round(lc)}
        else:
            all_nodes[nid]["position"] = {"x": round(lc), "y": round(cc)}

    # ── Assign positions, column by column ────────────────────────────────────
    for col_idx, units in enumerate(col_units):
        if not units:
            continue

        col_val = (n_layers - 1 - col_idx) if reverse else col_idx
        lc = MARGIN + col_val * LAYER_GAP

        units.sort(key=lambda u: (0 if u[0] == "cluster" else 1, u[1]))

        total  = (sum(cross_size(k, uid, ch) for k, uid, ch in units)
                  + UNIT_GAP * max(0, len(units) - 1))
        cursor = CROSS_CTR - total / 2.0

        for kind, uid, ch in units:
            cs     = cross_size(kind, uid, ch)
            center = cursor + cs / 2.0
            cursor += cs + UNIT_GAP

            if kind == "node":
                set_pos(uid, lc, center)
            else:
                n = len(ch)
                for i, child_id in enumerate(ch):
                    cc = center - (n - 1) * CHILD_GAP / 2.0 + i * CHILD_GAP
                    set_pos(child_id, lc, cc)
                set_pos(uid, lc, center)

    # ── Family alignment ──────────────────────────────────────────────────────
    # After independent column packing, nodes in the same root cluster may land
    # at different cross positions across layers.  Shift each layer so that the
    # family's cross centre is consistent (derived from its widest layer).

    def root_family(nid: str):
        cur, root = all_nodes[nid]["data"].get("parent"), None
        while cur and cur in cluster_ids:
            root = cur
            cur  = all_nodes[cur]["data"].get("parent")
        return root

    def get_cc(nid: str) -> float:
        p = all_nodes[nid]["position"]
        return p["x"] if vertical else p["y"]

    def set_cc(nid: str, val: float) -> None:
        if vertical:
            all_nodes[nid]["position"]["x"] = round(val)
        else:
            all_nodes[nid]["position"]["y"] = round(val)

    family_layers: dict = defaultdict(lambda: defaultdict(list))
    for nid in reg_ids:
        fam = root_family(nid)
        if fam:
            family_layers[fam][layer_of[nid]].append(nid)

    for fam_id, by_layer in family_layers.items():
        # Reference = layer with the largest cross span (widest content)
        ref_layer = max(
            by_layer,
            key=lambda l: (
                max(get_cc(n) for n in by_layer[l]) - min(get_cc(n) for n in by_layer[l])
                if len(by_layer[l]) > 1 else 0
            ),
        )
        ref_center = sum(get_cc(n) for n in by_layer[ref_layer]) / len(by_layer[ref_layer])

        for layer, nodes in by_layer.items():
            if layer == ref_layer:
                continue
            cur_center = sum(get_cc(n) for n in nodes) / len(nodes)
            offset = ref_center - cur_center
            if abs(offset) < 0.5:
                continue
            for nid in nodes:
                set_cc(nid, get_cc(nid) + offset)
            # Also shift the leaf-cluster node that owns these reg nodes
            shifted: set = set()
            for nid in nodes:
                parent = all_nodes[nid]["data"].get("parent")
                if parent and parent in leaf_clusters and parent not in shifted:
                    shifted.add(parent)
                    set_cc(parent, get_cc(parent) + offset)

    # ── Position outer clusters at centroid of descendants ────────────────────
    def _desc_reg(cl_id: str) -> list:
        result = [nid for nid in reg_ids if all_nodes[nid]["data"].get("parent") == cl_id]
        for cid in cluster_ids:
            if all_nodes[cid]["data"].get("parent") == cl_id:
                result.extend(_desc_reg(cid))
        return result

    for cl_id in cluster_ids:
        if cl_id not in placed_cl:
            desc = _desc_reg(cl_id)
            if desc:
                xs_d = [all_nodes[d]["position"]["x"] for d in desc]
                ys_d = [all_nodes[d]["position"]["y"] for d in desc]
                all_nodes[cl_id]["position"] = {
                    "x": round(sum(xs_d) / len(xs_d)),
                    "y": round(sum(ys_d) / len(ys_d)),
                }
            else:
                all_nodes[cl_id]["position"] = {
                    "x": round(MARGIN),
                    "y": round(CROSS_CTR) if not vertical else round(MARGIN),
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
