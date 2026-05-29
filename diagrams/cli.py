import argparse
import sys


def run() -> int:
    """
    Run diagrams code files in a diagrams environment.
    Args:
        paths: A list of paths to Python files containing diagrams code.

    Returns:
        The exit code.
    """
    parser = argparse.ArgumentParser(
        description="Run diagrams code files in a diagrams environment.",
    )
    parser.add_argument(
        "paths",
        metavar="path",
        type=str,
        nargs="+",
        help="a Python file containing diagrams code",
    )
    args = parser.parse_args()

    for path in args.paths:
        with open(path, encoding='utf-8') as f:
            exec(f.read())

    return 0


def _run_files(paths: list) -> None:
    import diagrams as _d
    _orig = _d.Diagram.__init__
    def _patched(self, *a, **kw):
        kw["show"] = False
        _orig(self, *a, **kw)
    _d.Diagram.__init__ = _patched
    for path in paths:
        with open(path, encoding="utf-8") as f:
            exec(f.read())  # noqa: S102


def _run_editor(args) -> None:
    from diagrams.editor import launch
    launch(port=args.port, open_browser=not args.no_browser)


def _run_export(args) -> None:
    from pathlib import Path
    from diagrams.editor.screenshot import export_png

    input_path  = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".png")

    print(f"Exporting {input_path} → {output_path} …")
    export_png(
        input_path.read_text(encoding="utf-8"),
        output_path,
        port=args.port,
        viewport_width=args.width,
        viewport_height=args.height,
        scale=args.scale,
    )
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        prog="diagrams",
        description="diagrams – Diagram as Code toolkit",
    )
    sub = parser.add_subparsers(dest="command")

    # ── run (default) ──
    run_p = sub.add_parser("run", help="Execute Python files containing diagrams code")
    run_p.add_argument("paths", metavar="path", nargs="+",
                       help="Python file(s) containing diagrams code")

    # ── editor ──
    ed_p = sub.add_parser("editor", help="Launch the interactive web-based diagram editor")
    ed_p.add_argument("--port", type=int, default=8888, help="Port (default: 8888)")
    ed_p.add_argument("--no-browser", action="store_true",
                      help="Don't open the browser automatically")

    # ── export ──
    ex_p = sub.add_parser("export", help="Export a .py diagram to PNG (headless browser)")
    ex_p.add_argument("input",  help="Python diagrams source file (.py)")
    ex_p.add_argument("output", nargs="?", help="Output PNG path (default: <input>.png)")
    ex_p.add_argument("--port",   type=int, default=0,    help="Internal server port (0 = auto)")
    ex_p.add_argument("--width",  type=int, default=1600, help="Browser viewport width (default: 1600)")
    ex_p.add_argument("--height", type=int, default=900,  help="Browser viewport height (default: 900)")
    ex_p.add_argument("--scale",  type=int, default=2,    help="Output resolution multiplier (default: 2)")

    args = parser.parse_args()

    if args.command == "editor":
        _run_editor(args)
    elif args.command == "export":
        _run_export(args)
    elif args.command == "run":
        _run_files(args.paths)
    else:
        # Backwards-compatible: bare `diagrams file.py` still works
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            _run_files(sys.argv[1:])
        else:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
