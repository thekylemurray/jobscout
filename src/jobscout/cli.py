from __future__ import annotations

import argparse
import json
import webbrowser

from . import __version__
from .app import render_html, run_once, watch
from .config import default_config, validate_config
from .demo import demo_jobs
from .paths import RuntimePaths
from .utils import load_json


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobscout", description="Explainable job discovery and ranking.")
    p.add_argument("--version", action="version", version=f"JobScout {__version__}")
    p.add_argument(
        "--home",
        default=".",
        help="runtime directory containing config.json (default: current directory)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a starter config.json")
    init.add_argument("--force", action="store_true", help="overwrite an existing config.json")

    scan = sub.add_parser("scan", help="scan configured sources once")
    scan.add_argument("--open", action="store_true", help="open the generated dashboard")
    scan.add_argument("--quiet", action="store_true", help="minimal console output")

    sub.add_parser("watch", help="scan repeatedly using watch_interval_minutes")

    demo = sub.add_parser("demo", help="generate an offline demo dashboard")
    demo.add_argument("--open", action="store_true")

    sub.add_parser("doctor", help="validate local configuration without network access")
    return p


def _doctor(paths: RuntimePaths) -> int:
    if not paths.config.exists():
        print(f"FAIL missing config: {paths.config}")
        print("Run `jobscout init` to create one.")
        return 1

    try:
        config = load_json(paths.config, {})
    except Exception as exc:
        print(f"FAIL config parse failed: {exc}")
        return 1

    errors = validate_config(config)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1

    enabled = sum(1 for board in config["boards"] if board.get("enabled", True))
    print(f"PASS config: {paths.config}")
    print(f"PASS configured sources: {enabled}")
    print(f"PASS output directory: {paths.output_dir}")
    print("PASS runtime dependency check: standard library only")
    return 0


def _init(paths: RuntimePaths, force: bool) -> int:
    paths.home.mkdir(parents=True, exist_ok=True)
    if paths.config.exists() and not force:
        print(f"Refusing to overwrite existing {paths.config}")
        print("Use `jobscout init --force` if you really want to replace it.")
        return 1
    paths.config.write_text(json.dumps(default_config(), indent=2) + "\n", encoding="utf-8")
    print(f"Created {paths.config}")
    print("Edit local_regions and source boards before your first live scan.")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    paths = RuntimePaths.from_home(args.home)

    if args.command == "init":
        raise SystemExit(_init(paths, args.force))
    if args.command == "scan":
        run_once(paths, open_dashboard=args.open, quiet=args.quiet)
        return
    if args.command == "watch":
        watch(paths)
        return
    if args.command == "doctor":
        raise SystemExit(_doctor(paths))
    if args.command == "demo":
        config = load_json(paths.config, default_config()) if paths.config.exists() else default_config()
        jobs = demo_jobs(config)
        paths.ensure()
        paths.dashboard.write_text(render_html(jobs), encoding="utf-8")
        print(f"Demo dashboard: {paths.dashboard}")
        if args.open:
            webbrowser.open(paths.dashboard.resolve().as_uri())
        return
