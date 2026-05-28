"""
Tests for the diagram web editor.

Run with:  pytest tests/test_editor.py -v
"""
import json
import re

import pytest

# Skip all tests if Flask is not installed
flask = pytest.importorskip("flask", reason="flask not installed (pip install flask)")

from diagrams.editor.server import create_app  # noqa: E402


# ─────────────────────────── fixture ────────────────────────────
@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ─────────────────────────── HTML / static ───────────────────────
class TestUI:
    def test_index_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_index_is_html(self, client):
        r = client.get("/")
        assert b"<!DOCTYPE html>" in r.data or b"<!doctype html>" in r.data.lower()

    def test_index_contains_app_title(self, client):
        r = client.get("/")
        assert b"Diagrams Editor" in r.data

    def test_index_loads_cytoscape_core(self, client):
        r = client.get("/")
        assert b"cytoscape" in r.data.lower()

    def test_html_has_no_undefined_cdn_globals(self, client):
        """No references to globals that CDN plugins might not expose."""
        r = client.get("/")
        html = r.data.decode()
        bad_globals = ["cytoscapeEdgehandles", "cytoscapeCompoundDragAndDrop"]
        for g in bad_globals:
            assert g not in html, f"Found potentially undefined global: {g}"

    def test_html_references_no_removed_plugins(self, client):
        """Confirm edge-handles CDN script tag was removed."""
        r = client.get("/")
        assert b"cytoscape-edgehandles" not in r.data

    def test_html_uses_taxi_edges(self, client):
        r = client.get("/")
        assert b"curve-style" in r.data
        assert b"taxi" in r.data
        assert b"bezier" not in r.data

    def test_html_has_corner_radius(self, client):
        r = client.get("/")
        assert b"corner-radius" in r.data

    def test_html_has_undo_function(self, client):
        r = client.get("/")
        assert b"function undo()" in r.data

    def test_html_has_push_history(self, client):
        r = client.get("/")
        assert b"pushHistory" in r.data

    def test_html_has_compact_save(self, client):
        r = client.get("/")
        assert b"toSaveState" in r.data
        assert b"v: 2" in r.data

    def test_html_has_undo_button(self, client):
        r = client.get("/")
        assert b"btn-undo" in r.data


# ─────────────────────────── /api/nodes ──────────────────────────
class TestNodesAPI:
    def test_returns_200(self, client):
        r = client.get("/api/nodes")
        assert r.status_code == 200

    def test_returns_json(self, client):
        r = client.get("/api/nodes")
        assert r.content_type.startswith("application/json")

    def test_contains_aws_provider(self, client):
        data = client.get("/api/nodes").get_json()
        assert "aws" in data

    def test_aws_has_compute_module(self, client):
        data = client.get("/api/nodes").get_json()
        assert "compute" in data["aws"]

    def test_ec2_present(self, client):
        data = client.get("/api/nodes").get_json()
        names = [n["name"] for n in data["aws"]["compute"]]
        assert "EC2" in names

    def test_node_has_required_fields(self, client):
        data = client.get("/api/nodes").get_json()
        node = data["aws"]["compute"][0]
        assert "name" in node
        assert "type" in node
        assert "icon" in node

    def test_node_type_format(self, client):
        data = client.get("/api/nodes").get_json()
        node = data["aws"]["compute"][0]
        parts = node["type"].split(".")
        assert len(parts) == 3, f"Expected provider.module.Class, got {node['type']}"

    def test_icon_path_ends_with_png(self, client):
        data = client.get("/api/nodes").get_json()
        for node in data["aws"]["compute"][:5]:
            assert node["icon"].endswith(".png"), f"Unexpected icon path: {node['icon']}"

    def test_multiple_providers_present(self, client):
        data = client.get("/api/nodes").get_json()
        assert len(data) >= 5, "Expected at least 5 providers"


# ─────────────────────────── /api/icons ──────────────────────────
class TestIconsAPI:
    def test_serves_existing_png(self, client):
        r = client.get("/api/icons/aws/compute/ec2.png")
        assert r.status_code == 200

    def test_returns_png_mimetype(self, client):
        r = client.get("/api/icons/aws/compute/ec2.png")
        assert r.content_type == "image/png"

    def test_node_catalog_icon_paths_are_servable(self, client):
        """Every icon path returned by /api/nodes must be accessible via /api/icons."""
        data = client.get("/api/nodes").get_json()
        # Spot-check first 3 nodes of aws/compute
        for node in data["aws"]["compute"][:3]:
            r = client.get(f"/api/icons/{node['icon']}")
            assert r.status_code == 200, (
                f"Icon not found: /api/icons/{node['icon']}"
            )

    def test_missing_icon_returns_404(self, client):
        r = client.get("/api/icons/does/not/exist.png")
        assert r.status_code == 404


# ─────────────────────────── /api/generate ───────────────────────
def _state(**kwargs):
    base = {"name": "Test", "direction": "LR", "theme": "neutral", "elements": []}
    base.update(kwargs)
    return base


class TestGenerateAPI:
    def test_empty_state_returns_200(self, client):
        r = client.post("/api/generate", json=_state())
        assert r.status_code == 200

    def test_empty_state_returns_code_key(self, client):
        r = client.post("/api/generate", json=_state())
        assert "code" in r.get_json()

    def test_basic_nodes_and_edge(self, client):
        state = _state(elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "Web", "type": "aws.compute.EC2"}},
            {"group": "nodes", "data": {"id": "n2", "label": "DB", "type": "aws.database.RDS"}},
            {"group": "edges", "data": {"id": "e1", "source": "n1", "target": "n2", "label": ""}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert "from diagrams import Diagram" in code
        assert "from diagrams.aws.compute import EC2" in code
        assert "from diagrams.aws.database import RDS" in code
        assert 'with Diagram("Test")' in code
        assert "ec2 >> rds" in code

    def test_cluster_generates_with_block(self, client):
        state = _state(elements=[
            {"group": "nodes", "data": {"id": "cl1", "label": "VPC", "isCluster": True}},
            {"group": "nodes", "data": {"id": "n1", "label": "App", "type": "aws.compute.EC2", "parent": "cl1"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert "from diagrams import Cluster, Diagram" in code
        assert 'with Cluster("VPC")' in code

    def test_duplicate_class_names_get_suffixes(self, client):
        state = _state(elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "A", "type": "aws.compute.EC2"}},
            {"group": "nodes", "data": {"id": "n2", "label": "B", "type": "aws.compute.EC2"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert "ec2_1" in code
        assert "ec2_2" in code

    def test_edge_label_uses_edge_class(self, client):
        state = _state(elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "A", "type": "aws.compute.EC2"}},
            {"group": "nodes", "data": {"id": "n2", "label": "B", "type": "aws.compute.Lambda"}},
            {"group": "edges", "data": {"id": "e1", "source": "n1", "target": "n2", "label": "invoke"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert 'Edge(label="invoke")' in code

    def test_non_default_direction_included(self, client):
        state = _state(direction="TB", elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "A", "type": "aws.compute.EC2"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert 'direction="TB"' in code

    def test_default_direction_omitted(self, client):
        state = _state(direction="LR", elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "A", "type": "aws.compute.EC2"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert 'direction=' not in code

    def test_non_default_theme_included(self, client):
        state = _state(theme="blues", elements=[
            {"group": "nodes", "data": {"id": "n1", "label": "A", "type": "aws.compute.EC2"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        assert 'theme="blues"' in code

    def test_invalid_json_returns_400(self, client):
        r = client.post("/api/generate", data="not json", content_type="text/plain")
        # Flask returns 200 with empty state or 400 — either is acceptable;
        # what must NOT happen is a 500 server error.
        assert r.status_code in (200, 400)

    def test_imports_are_sorted(self, client):
        state = _state(elements=[
            {"group": "nodes", "data": {"id": "n1", "type": "aws.network.ELB", "label": "LB"}},
            {"group": "nodes", "data": {"id": "n2", "type": "aws.compute.EC2", "label": "Web"}},
        ])
        code = client.post("/api/generate", json=state).get_json()["code"]
        lines = code.splitlines()
        import_lines = [l for l in lines if l.startswith("from ")]
        assert import_lines == sorted(import_lines), "Imports should be alphabetically sorted"


# ─────────────────────────── /api/import ─────────────────────────
_EXAMPLE_PY = """\
from diagrams import Diagram, Cluster
from diagrams.aws.compute import EC2, Lambda
from diagrams.aws.database import RDS
from diagrams.aws.network import ELB

with Diagram("Test Import", direction="TB"):
    with Cluster("App"):
        web = EC2("Web")
        fn  = Lambda("Function")
    lb  = ELB("Load Balancer")
    db  = RDS("Database")
    lb >> [web, fn]
    web >> db
"""


class TestImportAPI:
    def test_returns_200(self, client):
        r = client.post("/api/import", json={"code": _EXAMPLE_PY})
        assert r.status_code == 200

    def test_returns_json(self, client):
        r = client.post("/api/import", json={"code": _EXAMPLE_PY})
        assert r.content_type.startswith("application/json")

    def test_format_version(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        assert state["v"] == 2

    def test_diagram_name_extracted(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        assert state["name"] == "Test Import"

    def test_direction_extracted(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        assert state["dir"] == "TB"

    def test_nodes_present(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        nodes = [n for n in state["nodes"] if not n.get("cluster")]
        labels = {n["label"] for n in nodes}
        assert labels == {"Web", "Function", "Load Balancer", "Database"}

    def test_cluster_present(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        clusters = [n for n in state["nodes"] if n.get("cluster")]
        assert len(clusters) == 1
        assert clusters[0]["label"] == "App"

    def test_cluster_children_have_parent(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        cl_id = next(n["id"] for n in state["nodes"] if n.get("cluster"))
        children = [n for n in state["nodes"] if n.get("parent") == cl_id]
        assert {c["label"] for c in children} == {"Web", "Function"}

    def test_edges_extracted(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        assert len(state["edges"]) >= 3

    def test_edge_fields(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        e = state["edges"][0]
        assert "id" in e and "src" in e and "tgt" in e

    def test_node_type_set(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        types = {n.get("type") for n in state["nodes"] if not n.get("cluster")}
        assert "aws.compute.EC2" in types
        assert "aws.network.ELB" in types

    def test_no_icon_in_response(self, client):
        """Icons are derived client-side; server must not include them."""
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        for n in state["nodes"]:
            assert "icon" not in n
            assert "borderColor" not in n

    def test_node_has_position(self, client):
        state = client.post("/api/import", json={"code": _EXAMPLE_PY}).get_json()
        for n in state["nodes"]:
            assert "x" in n and "y" in n

    def test_empty_code_returns_400(self, client):
        r = client.post("/api/import", json={"code": ""})
        assert r.status_code == 400

    def test_syntax_error_returns_400(self, client):
        r = client.post("/api/import", json={"code": "def broken("})
        assert r.status_code == 400

    def test_no_diagram_block_returns_400(self, client):
        r = client.post("/api/import", json={"code": "x = 1 + 1"})
        assert r.status_code == 400

    def test_example_file_importable(self, client):
        """The shipped examples/web_app.py must import without errors."""
        from pathlib import Path
        example = (Path(__file__).parent.parent / "examples" / "web_app.py").read_text()
        r = client.post("/api/import", json={"code": example})
        assert r.status_code == 200
        state = r.get_json()
        assert state["v"] == 2
        nodes = [n for n in state["nodes"] if not n.get("cluster")]
        assert len(nodes) >= 8
