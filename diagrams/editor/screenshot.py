"""
Headless PNG export for the Diagrams editor.

Spins up a temporary Flask server, loads the diagram in a headless Chromium
browser, and captures the Cytoscape canvas + edge-overlay composite — identical
to what the "Export PNG" button in the UI produces.

Requirements (optional extras):
    pip install "diagrams[screenshot]"
    playwright install chromium
"""
from __future__ import annotations

import base64
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise TimeoutError(f"Editor server did not respond on port {port} after {timeout}s")


# ── public API ────────────────────────────────────────────────────────────────

def export_png(
    py_code: str,
    output_path: str | Path,
    *,
    port: int = 0,
    viewport_width: int = 1600,
    viewport_height: int = 900,
    padding: int = 50,
    scale: int = 2,
) -> Path:
    """
    Render *py_code* to a PNG screenshot using a headless Chromium browser.

    The output is pixel-identical to clicking "Export PNG" in the browser UI:
    the Cytoscape canvas and edge-bridge overlay are composited at *scale* ×
    resolution before saving.

    Parameters
    ----------
    py_code:
        Content of a ``diagrams`` Python source file.
    output_path:
        Destination ``.png`` file.
    port:
        Port for the temporary Flask server. ``0`` picks a free port automatically.
    viewport_width / viewport_height:
        Headless browser window size. Larger values give more canvas space
        before fitting.
    padding:
        Canvas padding (px) passed to ``cy.fit()``.
    scale:
        Output resolution multiplier (default 2 = retina quality).

    Raises
    ------
    SystemExit
        If Playwright is not installed.
    ValueError
        If the Python code cannot be parsed as a diagrams diagram.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "PNG export requires Playwright.\n"
            "Install with:  pip install playwright && playwright install chromium"
        ) from None

    from .server import create_app

    # Start a temporary Flask server in a daemon thread
    port = port or _free_port()
    app = create_app()
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    ).start()
    _wait_for_server(port)

    output_path = Path(output_path)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

        # Import the diagram into the editor
        import_error = page.evaluate(
            """async (code) => {
                const r = await fetch('/api/import', {
                    method:  'POST',
                    headers: {'Content-Type': 'application/json'},
                    body:    JSON.stringify({code}),
                });
                if (!r.ok) {
                    const d = await r.json();
                    return d.error || 'import failed';
                }
                restoreState(await r.json());
                return null;
            }""",
            py_code,
        )
        if import_error:
            browser.close()
            raise ValueError(f"Diagram import failed: {import_error}")

        # Wait for the initial render + edge-bridge overlay to settle
        page.wait_for_timeout(500)

        # Composite cy canvas + overlay — mirrors exportPng() in editor.html
        data_url: str = page.evaluate(
            f"""() => new Promise(resolve => {{
                cy.fit(undefined, {padding});
                // Two rAF cycles: first triggers render+overlay, second captures it
                requestAnimationFrame(() => requestAnimationFrame(() => {{
                    const SCALE = {scale};
                    const cyUrl  = cy.png({{ output: 'base64uri', full: false, scale: SCALE, bg: '#fafbfc' }});
                    const overlay = document.getElementById('edge-overlay');
                    const img = new Image();
                    img.onload = () => {{
                        const c   = document.createElement('canvas');
                        c.width   = img.width;
                        c.height  = img.height;
                        const ctx = c.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        ctx.drawImage(overlay, 0, 0, c.width, c.height);
                        resolve(c.toDataURL('image/png'));
                    }};
                    img.src = cyUrl;
                }}));
            }})"""
        )
        browser.close()

    _, b64 = data_url.split(",", 1)
    output_path.write_bytes(base64.b64decode(b64))
    return output_path
