from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import webbrowser
from datetime import datetime, timezone

from . import __version__
from .app import render_html, run_once, watch
from .config import default_config, validate_config
from .demo import demo_jobs
from .expansion_catalog import add_sources, planned_sources
from .paths import RuntimePaths
from .requirements import validate_candidate_evidence
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
    expand = sub.add_parser("add-sources", help="append curated new job boards to local config")
    expand.add_argument("--dry-run", action="store_true",
                        help="show proposed boards without editing config.json")
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

    evidence_path = paths.home / "candidate_evidence.json"
    if evidence_path.exists():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"FAIL local candidate evidence: {exc}")
            return 1
        problems = validate_candidate_evidence(evidence)
        if problems:
            for problem in problems:
                print(f"FAIL candidate evidence: {problem}")
            return 1
        print(f"PASS local candidate evidence: {evidence_path}")
    else:
        print("NOTE: No local candidate evidence; skills will remain unassessed.")

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


def _add_sources(paths: RuntimePaths, dry_run: bool = False) -> int:
    """Update the user's local config, preserving all existing preferences."""
    if not paths.config.exists():
        print(f"FAIL config missing: {paths.config}. Run 'jobscout init' first.")
        return 1
    try:
        config = json.loads(paths.config.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        print(f"FAIL cannot parse config: {exc}")
        return 1
    if not isinstance(config, dict):
        print("FAIL config must be a JSON object")
        return 1
    original_errors = validate_config(config)
    if original_errors:
        print("FAIL fix existing config first: " + "; ".join(original_errors))
        return 1
    updated, added = add_sources(config)
    if not added:
        print("No additions needed: all expansion sources already configured.")
        return 0
    for item in added:
        print(f"  + {item['company']} ({item['source']} / {item['board']})")
    if dry_run:
        print(f"Dry run only: {len(added)} boards would be added.")
        return 0
    problems = validate_config(updated)
    if problems:
        print("FAIL merged config invalid: " + "; ".join(problems))
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = paths.config.with_name(f"config.backup-{stamp}.json")
    shutil.copy2(paths.config, backup)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=paths.config.parent,
                prefix="config.new-", suffix=".json", delete=False) as handle:
            temp_name = handle.name
            json.dump(updated, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_name, paths.config)
    except OSError as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        print(f"FAIL could not update config: {exc}; original backup: {backup}")
        return 1
    print(f"Added {len(added)} job sources to {paths.config}")
    print(f"Original configuration backed up at {backup}")
    print("Existing preferences, candidate evidence and search history were not changed.")
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
    if args.command == "add-sources":
        raise SystemExit(_add_sources(paths, dry_run=args.dry_run))
    if args.command == "demo":
        config = load_json(paths.config, default_config()) if paths.config.exists() else default_config()
        jobs = demo_jobs(config)
        paths.ensure()
        paths.dashboard.write_text(render_html(jobs), encoding="utf-8")
        print(f"Demo dashboard: {paths.dashboard}")
        if args.open:
            webbrowser.open(paths.dashboard.resolve().as_uri())
        return
