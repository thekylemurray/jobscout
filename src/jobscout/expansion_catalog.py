"""Conservative, curated public feeds for the personal JobScout expansion.

These are seed accounts verified through employer career-site pages, not a
promise that currently suitable positions are live. Scan state/history is kept.
"""
from __future__ import annotations

import json

EXPANSION_BOARDS: tuple[dict[str, object], ...] = (
    {"company": "Hugging Face", "source": "workable", "board": "huggingface", "enabled": True},
    {"company": "Huzzle", "source": "workable", "board": "huzzle", "enabled": True},
    {"company": "Dodge Construction Network", "source": "workable",
     "board": "dodge-construction-network", "enabled": True},
    {"company": "Zensai", "source": "recruitee", "board": "zensai", "enabled": True},
    {"company": "Braavo", "source": "recruitee", "board": "getbraavo", "enabled": True},
    {"company": "Better Collective", "source": "recruitee", "board": "bettercollective", "enabled": True},
    {"company": "HIKE2", "source": "recruitee", "board": "hike2", "enabled": True},
    {"company": "Startup Jobs (Remote)", "source": "startupjobs",
     "board": "https://startup.jobs/feeds/jobs?workplace=remote", "enabled": True},
    {"company": "Startup Jobs (Remote Marketing)", "source": "startupjobs",
     "board": "https://startup.jobs/feeds/jobs?workplace=remote&role=marketing", "enabled": True},
)


def planned_sources(config: dict) -> list[dict]:
    """Return unconfigured entries using (source, board) identity."""
    existing = {
        (str(entry.get("source", "")).lower(),
         str(entry.get("board", "")).rstrip("/").lower())
        for entry in config.get("boards", []) if isinstance(entry, dict)
    }
    return [dict(item) for item in EXPANSION_BOARDS
            if (str(item["source"]).lower(), str(item["board"]).rstrip("/").lower()) not in existing]


def add_sources(config: dict) -> tuple[dict, list[dict]]:
    """Return a merged config copy without mutating the caller."""
    copy = json.loads(json.dumps(config))
    added = planned_sources(copy)
    copy.setdefault("boards", []).extend(added)
    return copy, added
