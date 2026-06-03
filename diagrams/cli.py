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
    launch(
        port=args.port,
        open_browser=not args.no_browser,
        initial_file=getattr(args, "file", None),
    )


def _run_skill_install(args) -> None:
    from pathlib import Path

    skill_src = Path(__file__).parent / "editor" / "SKILL.md"
    if not skill_src.exists():
        print("Error: SKILL.md not found in package.", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "global_install", False):
        dest_dir = Path.home() / ".claude" / "skills"
    else:
        dest_dir = Path.cwd() / ".claude" / "skills"

    dest_dir = dest_dir / "python-diagrams"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"
    dest.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")

    scope = "globally (~/.claude/skills/python-diagrams/)" if getattr(args, "global_install", False) else f"in this project ({dest})"
    print(f"Skill installed {scope}")
    print("Restart Claude Code to activate it.")


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
    ed_p.add_argument("file", nargs="?", default=None,
                      help="Optional .py diagram file to auto-import on startup")
    ed_p.add_argument("--port", type=int, default=8888, help="Port (default: 8888)")
    ed_p.add_argument("--no-browser", action="store_true",
                      help="Don't open the browser automatically")

    # ── skill-install ──
    si_p = sub.add_parser("skill-install",
                           help="Install the Claude Code skill into the current project")
    si_p.add_argument("--global", action="store_true", dest="global_install",
                      help="Install to ~/.claude/skills/ instead of ./.claude/skills/")

    args = parser.parse_args()

    if args.command == "editor":
        _run_editor(args)
    elif args.command == "skill-install":
        _run_skill_install(args)
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
