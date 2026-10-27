"""Carefully scoped migrations for employer boards that changed recruiting ATS.

Only exact old employer/source pairs are modified; other configurations and
user-disabled entries are preserved. Calls are pure; CLI handles backups.
"""
from __future__ import annotations

import json

REPLACEMENTS = {
    ("amplitude", "greenhouse"): ("ashby", "amplitude"),
    ("postman", "greenhouse"): (
        "workday", "https://postman.wd108.myworkdayjobs.com/careers"),
}


def repair_sources(config: dict) -> tuple[dict, list[dict]]:
    result = json.loads(json.dumps(config))
    changes: list[dict] = []
    for entry in result.get("boards", []):
        if not isinstance(entry, dict):
            continue
        company = str(entry.get("company", "")).strip().lower()
        source = str(entry.get("source", "")).strip().lower()
        replacement = REPLACEMENTS.get((company, source))
        if replacement is None:
            continue
        old_source = entry["source"]
        old_board = entry.get("board")
        entry["source"], entry["board"] = replacement
        changes.append({
            "company": entry["company"],
            "old_source": old_source,
            "old_board": old_board,
            "new_source": entry["source"],
            "new_board": entry["board"],
            "enabled": entry.get("enabled", True),
        })
    return result, changes
