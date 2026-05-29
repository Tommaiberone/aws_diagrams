"""
Server-side PNG renderer — matches the editor canvas exactly.

Mirrors the Cytoscape.js stylesheet in editor.html:
  - Cluster: rounded-rect, #f0f7ff fill, #4f9cf9 dashed border, label top-center bold
  - Node:    round-rectangle 56×56, white fill, provider-colored border, label below
  - Edge:    taxi orthogonal, corner-radius 8, grey #718096, triangle arrowhead
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

_RESOURCES = Path(__file__).parent.parent.parent / "resources"

# ── palette — exact values from editor's PROVIDER_COLORS / CSS ───────────────
_BG           = (250, 251, 252)   # #fafbfc
_WHITE        = (255, 255, 255)
_CLUSTER_FILL = (240, 247, 255)   # #f0f7ff  (background-opacity 0.94 → baked)
_CLUSTER_BDR  = ( 79, 156, 249)   # #4f9cf9
_CLUSTER_TEXT = ( 37,  99, 235)   # #2563eb
_EDGE         = (113, 128, 150)   # #718096
_TEXT         = ( 45,  55,  72)   # #2d3748
_DEFAULT_BDR  = (113, 128, 150)   # fallback border

_PROVIDER_COLOR: dict[str, tuple] = {
    "aws":          (255, 153,   0),   # #FF9900
    "azure":        (  0, 137, 214),   # #0089D6
    "gcp":          ( 66, 133, 244),   # #4285F4
    "k8s":          ( 50, 108, 229),   # #326CE5
    "alibabacloud": (255, 106,   0),   # #FF6A00
    "digitalocean": (  0, 128, 255),   # #0080FF
    "elastic":      (  0,  85, 113),   # #005571
    "firebase":     (255, 202,  40),   # #FFCA28
    "generic":      (113, 128, 150),   # #718096
    "ibm":          ( 18,  97, 254),   # #1261FE
    "oci":          (199,  70,  52),   # #C74634
    "onprem":       (113, 128, 150),   # #718096
    "openstack":    (237,  25,  68),   # #ED1944
    "outscale":     ( 91,  79, 191),   # #5B4FBF
    "programming":  ( 45, 154, 103),   # #2d9a67
    "saas":         (  0, 180, 228),   # #00b4e4
    "c4":           (136, 136, 136),   # #888888
}

# ── node geometry constants (match Cytoscape stylesheet) ──────────────────────
_NODE_W  = 56    # width / height in model px
_NODE_H  = 56
_CL_PAD  = 30    # cluster padding (matches parser.CL_PAD)
_LBL_GAP = 4     # text-margin-y for nodes
_CORNER_R = 8    # edge corner-radius


# ── public API ────────────────────────────────────────────────────────────────

def render_to_png(
    py_code: str,
    output_path: str | Path,
    *,
    scale: int = 2,
    margin: int = 80,
) -> Path:
    """
    Parse *py_code* and render to PNG using Pillow.

    Visually matches the editor canvas: same layout, same icons, same
    colour scheme, rounded-corner edges, dashed cluster borders.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise SystemExit(
            "PNG rendering requires Pillow.\n"
            "Install with:  pip install pillow"
        ) from None

    from .parser import parse_diagram_code

    state    = parse_diagram_code(py_code)
    elements = state["elements"]

    node_els = {e["data"]["id"]: e for e in elements if e["group"] == "nodes"}
    edge_els = [e for e in elements if e["group"] == "edges"]
    reg      = {nid: el for nid, el in node_els.items() if not el["data"].get("isCluster")}
    clusters = {nid: el for nid, el in node_els.items() if el["data"].get("isCluster")}

    if not reg:
        img = Image.new("RGBA", (400 * scale, 300 * scale), _BG)
        return _save(img, output_path)

    # ── coordinate transform: model px → canvas px ───────────────────────────
    pos = {nid: (el["position"]["x"], el["position"]["y"]) for nid, el in reg.items()}
    xs  = [p[0] for p in pos.values()]
    ys  = [p[1] for p in pos.values()]
    ox  = min(xs) - margin
    oy  = min(ys) - margin
    cw  = int((max(xs) - min(xs) + 2 * margin + _NODE_W)                      * scale)
    ch  = int((max(ys) - min(ys) + 2 * margin + _NODE_H + _LBL_GAP + 14)     * scale)

    def sx(x: float) -> float: return (x - ox) * scale
    def sy(y: float) -> float: return (y - oy) * scale

    img  = Image.new("RGBA", (cw, ch), _BG)
    draw = ImageDraw.Draw(img)
    fsm, fmd = _fonts(scale)

    # ── 1. cluster fills + dashed borders + labels ────────────────────────────
    for cl_id, cl_el in clusters.items():
        children = [nid for nid in reg if reg[nid]["data"].get("parent") == cl_id]
        if children:
            cxs = [pos[c][0] for c in children]
            cys = [pos[c][1] for c in children]
            pad = _CL_PAD * scale
            x0 = sx(min(cxs)) - _NODE_W / 2 * scale - pad
            y0 = sy(min(cys)) - _NODE_H / 2 * scale - pad
            x1 = sx(max(cxs)) + _NODE_W / 2 * scale + pad
            y1 = sy(max(cys)) + _NODE_H / 2 * scale + pad
        else:
            px, py = cl_el["position"]["x"], cl_el["position"]["y"]
            x0, y0 = sx(px) - 60 * scale, sy(py) - 40 * scale
            x1, y1 = sx(px) + 60 * scale, sy(py) + 40 * scale

        r = max(4, 8 * scale // 2)
        # Fill
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=_CLUSTER_FILL)
        # Dashed border
        _dashed_rounded_rect(draw, x0, y0, x1, y1, r, _CLUSTER_BDR,
                              width=max(1, scale), dash=int(7 * scale * 0.6), gap=int(4 * scale * 0.6))
        # Label — centered at top (text-valign: top)
        lbl = cl_el["data"].get("label", "Cluster")
        tw  = _text_width(fmd, lbl)
        lx  = (x0 + x1) / 2 - tw / 2
        ly  = y0 + max(2, 4 * scale // 2)
        draw.text((lx, ly), lbl, fill=_CLUSTER_TEXT, font=fmd)

    # ── 2. edges ─────────────────────────────────────────────────────────────
    nw, nh   = int(_NODE_W * scale), int(_NODE_H * scale)
    half_nw  = nw / 2
    half_nh  = nh / 2
    lw       = max(1, scale)
    arrow_sz = max(7, int(9 * scale * 0.6))
    cr       = _CORNER_R * scale // 2   # corner radius in canvas px

    for edge in edge_els:
        d   = edge["data"]
        sid, tid = d.get("source"), d.get("target")
        if sid not in pos or tid not in pos:
            continue
        s = (sx(pos[sid][0]), sy(pos[sid][1]))
        t = (sx(pos[tid][0]), sy(pos[tid][1]))
        pts = _taxi(s, t)

        # Trim source to boundary
        dx0, dy0 = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        if abs(dx0) >= abs(dy0):
            sign = 1 if dx0 > 0 else -1
            pts[0] = (pts[0][0] + sign * half_nw, pts[0][1])
        else:
            sign = 1 if dy0 > 0 else -1
            pts[0] = (pts[0][0], pts[0][1] + sign * half_nh)

        # Trim target to boundary
        dx1, dy1 = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        if abs(dx1) >= abs(dy1):
            sign = -1 if dx1 > 0 else 1
            pts[-1] = (pts[-1][0] + sign * half_nw, pts[-1][1])
        else:
            sign = -1 if dy1 > 0 else 1
            pts[-1] = (pts[-1][0], pts[-1][1] + sign * half_nh)

        _draw_rounded_polyline(draw, pts, _EDGE, lw, cr)
        _arrowhead(draw, pts[-2], pts[-1], _EDGE, size=arrow_sz)

        lbl = d.get("label", "")
        if lbl:
            mid = pts[len(pts) // 2]
            tw  = _text_width(fsm, lbl)
            # White pill background like editor (text-background-opacity: 1)
            lx, ly = mid[0] - tw / 2, mid[1] - 7 * scale // 2
            pad2 = max(1, 2 * scale // 2)
            draw.rectangle([lx - pad2, ly - pad2, lx + tw + pad2, ly + 12 * scale // 2 + pad2],
                           fill=_BG)
            draw.text((lx, ly), lbl, fill=_EDGE, font=fsm)

    # ── 3. nodes ─────────────────────────────────────────────────────────────
    for nid, el in reg.items():
        cx, cy = sx(pos[nid][0]), sy(pos[nid][1])
        x0, y0 = cx - nw / 2, cy - nh / 2
        x1, y1 = x0 + nw,     y0 + nh
        provider = el["data"].get("type", "").split(".")[0]
        border   = _PROVIDER_COLOR.get(provider, _DEFAULT_BDR)
        r = max(4, 8 * scale // 2)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r,
                                fill=_WHITE, outline=border, width=max(1, scale))
        icon = _icon_path(el["data"].get("type", ""))
        if icon:
            _paste_icon(img, icon, x0, y0, nw, nh)
        lbl = el["data"].get("label", "")
        if lbl:
            tw = _text_width(fsm, lbl)
            draw.text((cx - tw / 2, y1 + _LBL_GAP * scale // 2),
                      lbl, fill=_TEXT, font=fsm)

    return _save(img, output_path)


# ── drawing helpers ───────────────────────────────────────────────────────────

def _draw_rounded_polyline(draw, pts: list, color: tuple, width: int, radius: float) -> None:
    """Draw an orthogonal polyline with Bézier-rounded corners (mirrors corner-radius: 8)."""
    r = radius
    lens = [math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1)]

    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        ln = lens[i]
        if ln < 0.01:
            continue
        ux, uy = (p2[0] - p1[0]) / ln, (p2[1] - p1[1]) / ln

        # Only trim toward a corner when the adjacent segment is non-degenerate;
        # a zero-length neighbour means the corner doesn't exist and trimming
        # would leave a visible gap ("saltello").
        trim_start = i > 0             and ln > r and lens[i - 1] > 0.01
        trim_end   = i < len(pts) - 2 and ln > r and lens[i + 1] > 0.01

        seg_start = (p1[0] + ux * r, p1[1] + uy * r) if trim_start else p1
        seg_end   = (p2[0] - ux * r, p2[1] - uy * r) if trim_end   else p2

        if math.hypot(seg_end[0] - seg_start[0], seg_end[1] - seg_start[1]) > 0.5:
            draw.line([seg_start, seg_end], fill=color, width=width)

    # Bézier arcs at each inner corner
    for i in range(1, len(pts) - 1):
        p_prev, corner, p_next = pts[i - 1], pts[i], pts[i + 1]
        d1x, d1y = corner[0] - p_prev[0], corner[1] - p_prev[1]
        d2x, d2y = p_next[0] - corner[0],  p_next[1] - corner[1]
        l1 = math.hypot(d1x, d1y)
        l2 = math.hypot(d2x, d2y)
        if l1 < 0.01 or l2 < 0.01:
            continue
        A = (corner[0] - d1x / l1 * r, corner[1] - d1y / l1 * r)
        B = (corner[0] + d2x / l2 * r, corner[1] + d2y / l2 * r)
        # Quadratic Bézier with the corner as control point
        bezier = [(
            (1 - t) ** 2 * A[0] + 2 * (1 - t) * t * corner[0] + t ** 2 * B[0],
            (1 - t) ** 2 * A[1] + 2 * (1 - t) * t * corner[1] + t ** 2 * B[1],
        ) for t in (j / 8 for j in range(9))]
        for j in range(len(bezier) - 1):
            draw.line([bezier[j], bezier[j + 1]], fill=color, width=width)


def _dashed_rounded_rect(draw, x0, y0, x1, y1, radius, color, width, dash, gap) -> None:
    """Draw a dashed rounded-rectangle border."""
    r = radius
    # Four straight sides, clipped by radius at corners
    sides = [
        ((x0 + r, y0), (x1 - r, y0)),   # top
        ((x1, y0 + r), (x1, y1 - r)),   # right
        ((x1 - r, y1), (x0 + r, y1)),   # bottom (RTL)
        ((x0, y1 - r), (x0, y0 + r)),   # left (BTT)
    ]
    for p1, p2 in sides:
        _dashed_line(draw, p1, p2, color, width, dash, gap)
    # Solid corner arcs (close enough to dashed visually)
    corners = [
        ((x0, y0), (x0 + 2*r, y0 + 2*r), 180, 270),
        ((x1 - 2*r, y0), (x1, y0 + 2*r), 270, 360),
        ((x1 - 2*r, y1 - 2*r), (x1, y1), 0, 90),
        ((x0, y1 - 2*r), (x0 + 2*r, y1), 90, 180),
    ]
    for bbox, sa, ea in [(c[0:2], c[2], c[3]) for c in corners]:
        draw.arc(list(bbox[0]) + list(bbox[1]), start=sa, end=ea, fill=color, width=width)


def _dashed_line(draw, p1, p2, color, width, dash, gap) -> None:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ln = math.hypot(dx, dy)
    if ln < 0.01:
        return
    ux, uy = dx / ln, dy / ln
    pos = 0
    while pos < ln:
        e = min(pos + dash, ln)
        draw.line([(p1[0] + ux * pos, p1[1] + uy * pos),
                   (p1[0] + ux * e,   p1[1] + uy * e)],
                  fill=color, width=width)
        pos += dash + gap


def _arrowhead(draw, p1: tuple, p2: tuple, color: tuple, size: int) -> None:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ln = math.hypot(dx, dy)
    if ln < 1:
        return
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    half   = size * 0.45
    b1 = (p2[0] - ux * size + px * half, p2[1] - uy * size + py * half)
    b2 = (p2[0] - ux * size - px * half, p2[1] - uy * size - py * half)
    draw.polygon([p2, b1, b2], fill=color)


# ── geometry helpers ──────────────────────────────────────────────────────────

def _taxi(s: tuple, t: tuple) -> list[tuple]:
    """Orthogonal two-turn path (mirrors taxiPath() in editor.html)."""
    sx, sy = s
    tx, ty = t
    mx, my = (sx + tx) / 2, (sy + ty) / 2
    if abs(sx - tx) >= abs(sy - ty):
        p1, p2 = (mx, sy), (mx, ty)
    else:
        p1, p2 = (sx, my), (tx, my)
    # Coincident intermediates mean source and target share a row/column →
    # the path is a straight line; no turns needed.
    if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 0.5:
        return [list(s), list(t)]
    return [list(s), list(p1), list(p2), list(t)]


# ── icon resolution ───────────────────────────────────────────────────────────

def _icon_path(type_str: str) -> Optional[Path]:
    if not type_str:
        return None
    parts = type_str.split(".")
    if len(parts) < 3:
        return None
    provider, module, cls_name = parts[0], parts[1], parts[2]
    try:
        import importlib
        mod = importlib.import_module(f"diagrams.{provider}.{module}")
        cls = getattr(mod, cls_name, None)
        if cls and hasattr(cls, "_icon"):
            path = _RESOURCES / provider / module / cls._icon
            if path.exists():
                return path
    except Exception:
        pass
    path = _RESOURCES / provider / module / f"{cls_name.lower()}.png"
    return path if path.exists() else None


def _paste_icon(img, icon_path: Path, x0: float, y0: float, w: int, h: int) -> None:
    try:
        from PIL import Image
        icon = Image.open(icon_path).convert("RGBA")
        pad  = int(w * 0.15)
        icon = icon.resize((w - 2 * pad, h - 2 * pad), Image.LANCZOS)
        img.paste(icon, (int(x0) + pad, int(y0) + pad), icon)
    except Exception:
        pass


# ── font & text helpers ───────────────────────────────────────────────────────

def _fonts(scale: int):
    from PIL import ImageFont
    size_sm = max(9,  10 * scale // 2)   # node labels (font-size: 10)
    size_md = max(10, 12 * scale // 2)   # cluster labels (font-size: 12)
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return (ImageFont.truetype(p, size_sm),
                        ImageFont.truetype(p, size_md))
            except Exception:
                pass
    default = ImageFont.load_default()
    return default, default


def _text_width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return font.getlength(text)
    if hasattr(font, "getsize"):
        return font.getsize(text)[0]
    return len(text) * 6


def _save(img, path) -> Path:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path = Path(path)
    path.write_bytes(buf.getvalue())
    return path
