"""Headless PNG export — delegates to the pure-Python renderer."""
from __future__ import annotations

from pathlib import Path


def export_png(
    py_code: str,
    output_path: str | Path,
    *,
    scale: int = 2,
    **_kwargs,          # absorb legacy port/viewport args silently
) -> Path:
    """
    Render *py_code* to PNG using the built-in Pillow renderer.

    No browser or Graphviz required — only Pillow.
    """
    from .renderer import render_to_png
    return render_to_png(py_code, output_path, scale=scale)
