from __future__ import annotations

from copy import deepcopy
from typing import Any

from .sources import SOURCE_FUNCS

DEFAULT_CONFIG: dict[str, Any] = {
    "alert_threshold": 82,
    "dashboard_threshold": 52,
    "max_alert_age_hours": 24,
    "dashboard_age_hours": 168,
    "watch_interval_minutes": 15,
    "salary_floor": 75000,
    "salary_target": 100000,
    "contract_priority_bonus": 1,
    "local_regions": ["your city", "your state"],
    "boards": [
        {"company": "Pendo", "source": "greenhouse", "board": "pendo", "enabled": True},
        {"company": "Webflow", "source": "greenhouse", "board": "webflow", "enabled": True},
        {"company": "GitLab", "source": "greenhouse", "board": "gitlab", "enabled": True},
        {"company": "Contentstack", "source": "greenhouse", "board": "contentstack", "enabled": True},
        {"company": "ServiceNow", "source": "smartrecruiters", "board": "ServiceNow", "enabled": True},
        {"company": "Stripe", "source": "stripe_careers", "board": "https://stripe.com/careers/search", "enabled": True},
        {"company": "Remote OK", "source": "remoteok", "board": "https://remoteok.com/api", "enabled": True},
        {"company": "Jobicy US Remote", "source": "jobicy", "board": "https://jobicy.com/api/v2/remote-jobs", "enabled": True},
        {"company": "Himalayas US Remote", "source": "himalayas", "board": "https://himalayas.app/jobs/api/search", "enabled": True},
        {"company": "We Work Remotely", "source": "wwr", "board": "https://weworkremotely.com/remote-jobs.rss", "enabled": True},
    ],
}


def default_config() -> dict[str, Any]:
    """Return a mutable copy of the bundled starter configuration."""
    return deepcopy(DEFAULT_CONFIG)


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors for a runtime configuration."""
    errors: list[str] = []
    required = {
        "alert_threshold",
        "dashboard_threshold",
        "max_alert_age_hours",
        "dashboard_age_hours",
        "watch_interval_minutes",
        "local_regions",
        "boards",
    }
    missing = sorted(required - set(config))
    if missing:
        errors.append("missing config keys: " + ", ".join(missing))

    if not isinstance(config.get("boards"), list):
        errors.append("config.boards must be a list")
        return errors

    if not isinstance(config.get("local_regions"), list):
        errors.append("config.local_regions must be a list")

    numeric_keys = [
        "alert_threshold",
        "dashboard_threshold",
        "max_alert_age_hours",
        "dashboard_age_hours",
        "watch_interval_minutes",
    ]
    for key in numeric_keys:
        if key in config and not isinstance(config[key], (int, float)):
            errors.append(f"config.{key} must be numeric")

    for idx, board in enumerate(config.get("boards", [])):
        if not isinstance(board, dict):
            errors.append(f"boards[{idx}] must be an object")
            continue
        for key in ("company", "source", "board"):
            if not board.get(key):
                errors.append(f"boards[{idx}].{key} is required")
        source = board.get("source")
        if source and source not in SOURCE_FUNCS:
            errors.append(f"boards[{idx}].source is unknown: {source}")

    return errors
