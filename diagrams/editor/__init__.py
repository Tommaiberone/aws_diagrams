"""
Interactive web-based diagram editor.

Usage:
    diagrams editor [file.py] [--port 8888]

Or programmatically:
    from diagrams.editor import launch
    launch(port=8888)
"""
import threading
import time
import webbrowser
from typing import Optional


def launch(port: int = 8888, open_browser: bool = True, initial_file: Optional[str] = None) -> None:
    """Start the editor server and (optionally) open the browser."""
    try:
        from flask import Flask  # noqa: F401
    except ImportError:
        raise SystemExit(
            "The diagram editor requires Flask.\n"
            "Install it with:  pip install flask"
        )

    from .server import create_app

    app = create_app(initial_file=initial_file)

    if open_browser:

        def _open() -> None:
            time.sleep(0.9)
            webbrowser.open(f"http://127.0.0.1:{port}")

        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  Diagrams Editor  →  http://127.0.0.1:{port}\n  Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
