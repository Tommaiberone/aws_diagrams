"""Flask server powering the web-based diagram editor."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

_HERE = Path(__file__).parent
_RESOURCES = Path(__file__).parent.parent.parent / "resources"
_DIAGRAMS_ROOT = Path(__file__).parent.parent.parent


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(_HERE / "templates"))

    # ------------------------------------------------------------------ UI
    @app.route("/")
    def index():
        return render_template("editor.html")

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

    # ------------------------------------------------------------------ Render preview
    @app.route("/api/render", methods=["POST"])
    def api_render():
        payload = request.get_json(force=True) or {}
        code: str = payload.get("code", "")
        fmt: str = payload.get("format", "png")

        if not code.strip():
            return jsonify({"error": "empty code"}), 400

        with tempfile.TemporaryDirectory() as tmpdir:
            # Monkey-patch Diagram so it writes to tmpdir with show=False
            wrapper = (
                f"import sys, os\n"
                f"sys.path.insert(0, {str(_DIAGRAMS_ROOT)!r})\n"
                f"os.chdir({tmpdir!r})\n"
                f"import diagrams as _d\n"
                f"_orig = _d.Diagram.__init__\n"
                f"def _patched(self, *a, **kw):\n"
                f"    kw['show'] = False\n"
                f"    kw['outformat'] = {fmt!r}\n"
                f"    _orig(self, *a, **kw)\n"
                f"_d.Diagram.__init__ = _patched\n"
                f"\n"
                f"{code}\n"
            )

            result = subprocess.run(
                [sys.executable, "-c", wrapper],
                capture_output=True,
                timeout=30,
                cwd=tmpdir,
            )

            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")[:3000]
                return jsonify({"error": err}), 400

            for fname in os.listdir(tmpdir):
                if fname.endswith(f".{fmt}"):
                    img_bytes = (Path(tmpdir) / fname).read_bytes()
                    mime = "image/png" if fmt == "png" else f"image/{fmt}"
                    return Response(img_bytes, mimetype=mime)

            return jsonify({"error": "diagram produced no output image"}), 500

    return app
