from __future__ import annotations

from dataclasses import dataclass

@dataclass
class Job:
    uid: str
    company: str
    source: str
    title: str
    location: str
    workplace: str
    employment_type: str | list[str]
    description: str
    job_url: str
    apply_url: str
    published_at: str | int | float | None
    first_seen_at: str
    compensation: str
    updated_at: str | int | float | None = None
    fit_score: int = 0
    priority_score: int = 0
    age_hours: float | None = None
    reasons: list[str] | None = None
    risks: list[str] | None = None
    eligible: bool = True
    veto_reason: str = ""
    discovery_status: str = "published"  # published | new | baseline
    fresh: bool = False
    role_lane: str = ""
    lane_confidence: int = 0
    score_breakdown: list[str] | None = None
    priority_reasons: list[str] | None = None
    also_found_on: list[str] | None = None
    history_key: str = ""
    publication_basis: str = ""
    availability: str = "Unverified"
    availability_note: str = "Posting has not been checked."
    availability_checked_at: str = ""
