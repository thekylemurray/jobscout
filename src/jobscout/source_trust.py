"""Source ownership policy: an ATS board can belong to a recruiting intermediary.

An ATS-hosted listing is not always proof the company displayed is the final
hiring employer. Huzzle is a known recruiting intermediary that places talent
with clients. Keep these jobs discoverable without direct-employer boosts.
"""
from __future__ import annotations


def is_intermediary(job) -> bool:
    if getattr(job, "intermediary", False):
        return True
    uid = str(getattr(job, "uid", "")).lower()
    return (getattr(job, "source", "") == "workable"
            and (uid.startswith("workable:huzzle:")
                 or str(getattr(job, "company", "")).strip().lower() == "huzzle"))


def source_class(job) -> str:
    if is_intermediary(job):
        return "Recruiting intermediary"
    from .rules import DIRECT_SOURCES, AGGREGATOR_SOURCES
    if job.source in DIRECT_SOURCES:
        return "Employer ATS"
    if job.source in AGGREGATOR_SOURCES:
        return "Aggregator"
    return "Other"
