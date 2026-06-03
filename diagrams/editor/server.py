"""Flask server powering the web-based diagram editor."""
import sys
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request, send_file

_HERE = Path(__file__).parent
_RESOURCES = Path(__file__).parent.parent.parent / "resources"


def create_app(initial_file: Optional[str] = None) -> Flask:
    app = Flask(__name__, template_folder=str(_HERE / "templates"))

    _initial_code: Optional[str] = None
    if initial_file:
        p = Path(initial_file)
        if p.exists():
            _initial_code = p.read_text(encoding="utf-8")
        else:
            print(f"Warning: file not found: {initial_file}", file=sys.stderr)

    # ------------------------------------------------------------------ UI
    @app.route("/")
    def index():
        return render_template("editor.html")

    # ------------------------------------------------------------------ Initial file
    @app.route("/api/initial")
    def api_initial():
        return jsonify({"code": _initial_code})

    # ------------------------------------------------------------------ Nodes
    @app.route("/api/nodes")
    def api_nodes():
        from .nodes import get_node_catalog

        return jsonify(get_node_catalog())

    # ------------------------------------------------------------------ Icons
    @app.route("/api/icons/<path:icon_path>")
    def api_icon(icon_path: str):
        full = _RESOURCES / icon_path
        if full.exists() and full.suffix in (".png", ".svg"):
            return send_file(str(full))
        return "not found", 404

    # ------------------------------------------------------------------ Code generation
    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        from .codegen import generate

        state = request.get_json(force=True) or {}
        try:
            code = generate(state)
            return jsonify({"code": code})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400

    # ------------------------------------------------------------------ Import .py
    @app.route("/api/import", methods=["POST"])
    def api_import():
        from .parser import parse_diagram_code

        payload = request.get_json(force=True) or {}
        code: str = payload.get("code", "")

        if not code.strip():
            return jsonify({"error": "empty code"}), 400

        try:
            state = parse_diagram_code(code)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        # Convert to compact v:2 format — client re-derives icon/borderColor
        nodes, edges = [], []
        for el in state.get("elements", []):
            d   = el.get("data", {})
            pos = el.get("position", {})
            if el.get("group") == "nodes":
                n = {"id": d["id"], "label": d.get("label", "")}
                if d.get("isCluster"):
                    n["cluster"] = True
                else:
                    n["type"] = d.get("type", "")
                if d.get("parent"):
                    n["parent"] = d["parent"]
                n["x"] = round(pos.get("x", 0))
                n["y"] = round(pos.get("y", 0))
                nodes.append(n)
            else:
                e = {"id": d["id"], "src": d["source"], "tgt": d["target"]}
                if d.get("label"):
                    e["label"] = d["label"]
                edges.append(e)

        result: dict = {
            "v":     2,
            "name":  state.get("name", "Imported Diagram"),
            "dir":   state.get("direction", "LR"),
            "nodes": nodes,
            "edges": edges,
        }
        theme = state.get("theme", "neutral")
        if theme and theme != "neutral":
            result["theme"] = theme

        return jsonify(result)

    return app
