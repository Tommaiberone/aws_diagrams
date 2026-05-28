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


def _run_editor(args) -> None:
    from diagrams.editor import launch
    launch(port=args.port, open_browser=not args.no_browser)


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

    args = parser.parse_args()

    if args.command == "editor":
        _run_editor(args)
    elif args.command == "run":
        for path in args.paths:
            with open(path, encoding="utf-8") as f:
                exec(f.read())  # noqa: S102
    else:
        # Backwards-compatible: bare `diagrams file.py` still works
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            for path in sys.argv[1:]:
                with open(path, encoding="utf-8") as f:
                    exec(f.read())  # noqa: S102
        else:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
