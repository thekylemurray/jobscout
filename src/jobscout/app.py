from __future__ import annotations

import csv
import html
import os
import time
import urllib.error
import webbrowser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from typing import Any

from . import __version__
from .models import Job
from .paths import RuntimePaths
from .scoring import application_tier, apply_freshness, dedupe_jobs, freshness_label, score_job
from .sources import SOURCE_FUNCS
from .utils import as_text, has_any, iso_now, load_json, now_utc, save_json

def fetch_all(config: dict[str, Any], state: dict[str, Any], cache: dict[str, Any], log: list[str], progress=None) -> tuple[list[Job], list[Job]]:
    jobs: list[Job] = []
    rejected: list[Job] = []
    seen = state.setdefault("jobs", {})
    board_state = state.setdefault("boards", {})

    boards = [b for b in config.get("boards", []) if b.get("enabled", True)]

    def fetch_board(b):
        company, source, board = b["company"], b["source"], b["board"]
        messages = []
        if progress:
            progress(f"Searching {company} ({source})…")
        def source_progress(message):
            if message.startswith(("COVERAGE ", "WARNING ")):
                messages.append(message)
            if progress:
                progress(message)
        try:
            func = SOURCE_FUNCS[source]
            if source == "workday" and config.get("profile"):
                raw = func(company, board, iso_now(), cache,
                           title_terms=config["profile"]["title_terms"],
                           search_text=b.get("search_text", ""), progress=source_progress,
                           seniority_terms=config["profile"]["seniority_terms"])
            else:
                raw = func(company, board, iso_now(), cache)
            messages.append(f"OK {company} ({source}): {len(raw)} jobs")
            return b, raw, messages, True
        except Exception as exc:
            messages.append(f"FAIL {company} ({source}): {type(exc).__name__}: {exc}")
            return b, [], messages, False

    # Network retrieval is bounded to three employer boards; scoring and state
    # updates remain sequential. Each board's cache entries use distinct URLs.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch_board, b) for b in boards]
        fetched = [future.result() for future in as_completed(futures)]
    for b, raw, messages, ok in fetched:
        log.extend(messages)
        if not ok:
            continue
        board_key = f"{b['source']}:{b['board']}"
        initialized = bool((board_state.get(board_key) or {}).get("initialized"))
        for job in raw:
            prev = seen.get(job.uid)
            is_new = prev is None
            if prev and prev.get("first_seen_at"):
                job.first_seen_at = prev["first_seen_at"]
            else:
                seen[job.uid] = {"first_seen_at": job.first_seen_at, "alerted": False}

            job = score_job(job, config)
            job = apply_freshness(job, config, board_initialized=initialized, is_new=is_new)
            if job.eligible:
                jobs.append(job)
            else:
                rejected.append(job)

        board_state[board_key] = {"initialized": True, "last_checked_at": iso_now()}

    return dedupe_jobs(jobs, config), rejected

def write_outputs(jobs: list[Job], rejected: list[Job], config: dict[str, Any], state: dict[str, Any], paths: RuntimePaths) -> list[Job]:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    dash_hours = config.get("dashboard_age_hours", 168)
    dash_min = config.get("dashboard_threshold", 64)

    # Always keep a complete eligible-candidate file for tuning. The dashboard is
    # intentionally broader than alerts: missing a plausible role is worse than
    # spending 30 seconds reviewing one extra candidate.
    all_eligible = sorted(jobs, key=lambda j: (j.fit_score, j.priority_score), reverse=True)

    visible = [
        j for j in jobs
        if j.fit_score >= dash_min and (j.age_hours is None or j.age_hours <= dash_hours)
    ]
    visible.sort(key=lambda j: (j.priority_score, j.fit_score), reverse=True)

    # Never produce a blank dashboard when the matcher found plausible roles.
    # If every candidate falls just below the review threshold, show the best ten.
    if not visible and all_eligible:
        visible = all_eligible[:10]

    with paths.eligible_csv.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "priority_score", "fit_score", "company", "title", "location", "workplace",
            "employment_type", "freshness", "age_hours", "published_at", "updated_at",
            "compensation", "role_lane", "lane_confidence", "apply_url", "reasons", "risks", "priority_reasons", "also_found_on"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for j in all_eligible:
            w.writerow({
                "priority_score": j.priority_score,
                "fit_score": j.fit_score,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "workplace": j.workplace,
                "employment_type": j.employment_type,
                "freshness": freshness_label(j),
                "age_hours": "" if j.age_hours is None else round(j.age_hours, 1),
                "published_at": j.published_at or "",
                "updated_at": j.updated_at or "",
                "compensation": j.compensation,
                "role_lane": j.role_lane,
                "lane_confidence": j.lane_confidence,
                "apply_url": j.apply_url,
                "reasons": "; ".join(j.reasons or []),
                "risks": "; ".join(j.risks or []),
                "priority_reasons": "; ".join(j.priority_reasons or []),
                "also_found_on": "; ".join(j.also_found_on or []),
            })

    with paths.jobs_csv.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "priority_score", "fit_score", "company", "title", "location", "workplace",
            "employment_type", "freshness", "age_hours", "published_at", "updated_at",
            "compensation", "role_lane", "lane_confidence", "apply_url", "reasons", "risks", "priority_reasons", "also_found_on"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for j in visible:
            w.writerow({
                "priority_score": j.priority_score,
                "fit_score": j.fit_score,
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "workplace": j.workplace,
                "employment_type": j.employment_type,
                "freshness": freshness_label(j),
                "age_hours": "" if j.age_hours is None else round(j.age_hours, 1),
                "published_at": j.published_at or "",
                "updated_at": j.updated_at or "",
                "compensation": j.compensation,
                "role_lane": j.role_lane,
                "lane_confidence": j.lane_confidence,
                "apply_url": j.apply_url,
                "reasons": "; ".join(j.reasons or []),
                "risks": "; ".join(j.risks or []),
                "priority_reasons": "; ".join(j.priority_reasons or []),
                "also_found_on": "; ".join(j.also_found_on or []),
            })

    # Near misses: rejected jobs whose titles still contain one of the broad lane
    # words. This is an audit file, not an application list.
    near_terms = [
        "web", "website", "content", "seo", "aeo", "geo", "search", "digital",
        "communications", "editorial", "brand", "campaign", "cms", "experience"
    ]
    if config.get("profile"):
        near_terms = config["profile"]["title_terms"]
    near_misses = [
        j for j in rejected
        if has_any(j.title or "", near_terms)
    ]
    with paths.near_miss_csv.open("w", newline="", encoding="utf-8") as f:
        fields = ["company", "title", "location", "source", "veto_reason", "apply_url"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for j in near_misses:
            w.writerow({
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "source": j.source,
                "veto_reason": j.veto_reason,
                "apply_url": j.apply_url,
            })

    with paths.rejected_csv.open("w", newline="", encoding="utf-8") as f:
        fields = ["company", "title", "location", "source", "veto_reason", "apply_url"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for j in rejected:
            w.writerow({
                "company": j.company,
                "title": j.title,
                "location": j.location,
                "source": j.source,
                "veto_reason": j.veto_reason,
                "apply_url": j.apply_url,
            })

    seen = state.setdefault("jobs", {})
    alert_threshold = config.get("alert_threshold", 78)
    max_age = config.get("max_alert_age_hours", 24)
    alerts: list[Job] = []
    for j in jobs:
        rec = seen.setdefault(j.uid, {"first_seen_at": j.first_seen_at, "alerted": False})
        if j.discovery_status == "baseline":
            continue
        is_new_enough = j.age_hours is not None and j.age_hours <= max_age
        if j.priority_score >= alert_threshold and is_new_enough and not rec.get("alerted", False):
            alerts.append(j)
            rec["alerted"] = True
            rec["alerted_at"] = iso_now()

    save_json(paths.alerts, [asdict(j) for j in alerts])
    paths.dashboard.write_text(render_html(visible), encoding="utf-8")
    return alerts

def render_html(jobs: list[Job]) -> str:
    tier_order = ["🔥 Apply now", "🟢 Strong matches", "🟡 Worth reviewing", "🔵 Discovery"]
    buckets: dict[str, list[Job]] = {t: [] for t in tier_order}
    for j in jobs:
        buckets[application_tier(j)].append(j)

    sections: list[str] = []
    for tier in tier_order:
        tier_jobs = buckets[tier]
        if not tier_jobs:
            continue
        cards = []
        for j in tier_jobs:
            age = "unknown" if j.age_hours is None else (f"{j.age_hours:.1f}h" if j.age_hours < 48 else f"{j.age_hours/24:.1f}d")
            reasons = "".join(f"<li>{html.escape(x)}</li>" for x in (j.reasons or []))
            risks = "".join(f"<li>{html.escape(x)}</li>" for x in (j.risks or []))
            breakdown = "".join(f"<li>{html.escape(x)}</li>" for x in (j.score_breakdown or []))
            pri = "".join(f"<li>{html.escape(x)}</li>" for x in (j.priority_reasons or []))
            risk_block = f"<div class='risks'><strong>Watch:</strong><ul>{risks}</ul></div>" if risks else ""
            comp = f"<span>{html.escape(j.compensation)}</span>" if j.compensation else ""
            duplicate = f"<span>also: {html.escape(', '.join(j.also_found_on or []))}</span>" if j.also_found_on else ""
            lane_label = f'{j.lane_confidence}% lane confidence' if j.lane_confidence else 'profile rules; review required'
            fit_label = f'{j.fit_score}% fit' if j.lane_confidence else f'{j.fit_score}/100 fit score'
            cards.append(f"""
            <article class='card'>
              <div class='scores'><div class='priority'>{j.priority_score}</div><small>priority</small><div class='fit'>{fit_label}</div></div>
              <div class='body'>
                <div class='topline'><span class='fresh'>{freshness_label(j)}</span><span class='age'>{age}</span><span class='source'>{html.escape(j.source)}</span></div>
                <h2>{html.escape(j.title)}</h2>
                <h3>{html.escape(j.company)}</h3>
                <div class='lane'>{html.escape(j.role_lane)} <span>{lane_label}</span></div>
                <div class='meta'><span>{html.escape(j.location or 'Location not listed')}</span><span>{html.escape(j.workplace or '')}</span><span>{html.escape(as_text(j.employment_type) or '')}</span>{comp}{duplicate}</div>
                <div class='grid'><div><strong>Why it matches</strong><ul>{reasons}</ul></div>{risk_block}</div>
                <details><summary>Why these scores?</summary><div class='details-grid'><div><strong>Fit evidence</strong><ul>{breakdown}</ul></div><div><strong>Priority evidence</strong><ul>{pri}</ul></div></div></details>
                <a class='apply' href='{html.escape(j.apply_url or j.job_url)}' target='_blank' rel='noopener'>Open application →</a>
              </div>
            </article>""")
        sections.append(f"<section><div class='section-head'><h2>{tier}</h2><span>{len(tier_jobs)} roles</span></div>{''.join(cards)}</section>")

    if not sections:
        sections.append("<div class='empty'>No credible matches above the dashboard threshold right now.</div>")
    stamp = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    counts = " · ".join(f"{t.replace('🔥 ', '').replace('🟢 ', '').replace('🟡 ', '').replace('🔵 ', '')}: {len(buckets[t])}" for t in tier_order if buckets[t])
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>JobScout</title><style>
:root{{--bg:#0f172a;--panel:#111827;--soft:#1f2937;--text:#e5e7eb;--muted:#94a3b8;--green:#22c55e;--cyan:#22d3ee;--amber:#f59e0b;--red:#f87171}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(135deg,#07111f,#111827);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:28px 18px 60px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:8px}}h1{{font-size:34px;margin:0}}.subtitle{{color:var(--muted);margin-top:6px}}.stamp{{color:var(--muted);font-size:13px}}.summary{{color:#cbd5e1;font-size:13px;margin:8px 0 24px}}.section-head{{display:flex;justify-content:space-between;align-items:center;margin-top:28px;border-bottom:1px solid #263244;padding-bottom:7px}}.section-head h2{{font-size:20px;margin:0}}.section-head span{{color:var(--muted);font-size:13px}}
.card{{display:grid;grid-template-columns:92px 1fr;background:rgba(17,24,39,.94);border:1px solid #263244;border-radius:16px;margin:14px 0;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.18)}}
.scores{{padding:20px 14px;text-align:center;background:#0b1220;border-right:1px solid #263244}}.priority{{font-size:34px;font-weight:800;color:var(--cyan)}}.scores small{{color:var(--muted)}}.fit{{margin-top:12px;font-size:14px;color:#bbf7d0}}.body{{padding:19px 22px}}.topline{{display:flex;gap:10px;align-items:center;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}.fresh{{font-weight:800;color:var(--green)}}.age,.source{{color:var(--muted)}}.body h2{{margin:8px 0 2px;font-size:23px}}h3{{margin:0 0 8px;color:#cbd5e1;font-weight:600}}.lane{{display:inline-block;background:#172033;border:1px solid #2b3b52;border-radius:999px;padding:5px 9px;font-size:12px;margin:2px 0 9px}}.lane span{{color:var(--muted);margin-left:6px}}.meta{{display:flex;flex-wrap:wrap;gap:7px 14px;color:var(--muted);font-size:14px}}.grid,.details-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}ul{{margin:6px 0 0;padding-left:18px;color:#cbd5e1}}li{{margin:3px 0}}.risks strong{{color:var(--amber)}}details{{margin-top:13px;border-top:1px solid #263244;padding-top:10px}}summary{{cursor:pointer;color:#93c5fd;font-size:13px}}.apply{{display:inline-block;margin-top:16px;padding:9px 14px;background:#0e7490;color:white;border-radius:9px;text-decoration:none;font-weight:700}}.apply:hover{{background:#0891b2}}.empty{{padding:40px;background:var(--panel);border-radius:14px;color:var(--muted)}}@media(max-width:700px){{.card{{grid-template-columns:70px 1fr}}.grid,.details-grid{{grid-template-columns:1fr}}header{{display:block}}.stamp{{margin-top:8px}}}}
</style></head><body><main><header><div><h1>JobScout <small style='font-size:14px;color:#94a3b8'>v{__version__}</small></h1><div class='subtitle'>Explainable job discovery based on your search preferences.</div></div><div class='stamp'>Updated {stamp}</div></header><div class='summary'>{html.escape(counts)}</div>{''.join(sections)}</main></body></html>"""

def notify(alerts: list[Job], paths: RuntimePaths, open_dashboard: bool = True) -> None:
    if not alerts:
        return
    print("\n" + "=" * 72)
    print(f"NEW STRONG MATCHES: {len(alerts)}")
    print("=" * 72)
    for j in alerts:
        age = "?" if j.age_hours is None else f"{j.age_hours:.1f}h"
        print(f"[{j.fit_score}% fit / {age}] {j.title} — {j.company}")
        print(f"  {j.apply_url}")
    if os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            time.sleep(0.15)
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
    if open_dashboard:
        try:
            webbrowser.open(paths.dashboard.resolve().as_uri())
        except Exception:
            pass

def run_once(paths: RuntimePaths, *, open_dashboard: bool = False, quiet: bool = False, progress=None) -> int:
    paths.ensure()
    if not paths.config.exists():
        raise FileNotFoundError(f"Missing {paths.config}. Copy config.example.json to config.json first.")
    config = load_json(paths.config, {})
    from .config import validate_config
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    state = load_json(paths.state, {"version": __version__, "jobs": {}, "boards": {}})
    cache = load_json(paths.cache, {})
    state["version"] = __version__
    log: list[str] = [f"JobScout v{__version__} run {iso_now()}"]
    jobs, rejected = fetch_all(config, state, cache, log, progress=progress)
    alerts = write_outputs(jobs, rejected, config, state, paths)
    save_json(paths.state, state)
    save_json(paths.cache, cache)
    try:
        with paths.jobs_csv.open("r", encoding="utf-8", newline="") as f:
            dashboard_count = max(0, sum(1 for _ in f) - 1)
    except OSError:
        dashboard_count = 0
    log.append(f"ELIGIBLE {len(jobs)} / DASHBOARD {dashboard_count} / REJECTED {len(rejected)}")
    ok_sources = sum(1 for line in log if line.startswith("OK "))
    failed_sources = sum(1 for line in log if line.startswith("FAIL "))
    log.append(f"SOURCE_HEALTH OK {ok_sources} / FAIL {failed_sources}")
    reason_counts = Counter(j.veto_reason for j in rejected if j.veto_reason)
    for reason, count in reason_counts.most_common(8):
        log.append(f"REJECT {count}: {reason}")
    paths.log.write_text("\n".join(log), encoding="utf-8")
    rows = ''.join('<tr>' + ''.join('<td>' + html.escape(as_text(x)) + '</td>' for x in
        (j.company, j.title, j.location, j.workplace, j.veto_reason)) + '</tr>' for j in rejected)
    audit = '<!doctype html><meta charset="utf-8"><title>JobScout scan report</title><style>body{font:16px system-ui;margin:32px}td,th{padding:12px;text-align:left;border-bottom:1px solid #ccc}pre{white-space:pre-wrap}</style><h1>Scan coverage and exclusions</h1>'
    audit += '<p>These are filtering decisions, not a claim that no suitable jobs exist. Inspect source failures and incomplete coverage below.</p>'
    audit += '<pre>' + html.escape('\n'.join(log)) + '</pre><table><tr><th>Employer</th><th>Title</th><th>Location</th><th>Arrangement</th><th>Reason</th></tr>' + rows + '</table>'
    (paths.output_dir / 'scan-report.html').write_text(audit, encoding='utf-8')
    if not quiet:
        enabled = sum(1 for b in config.get("boards", []) if b.get("enabled", True))
        print(f"Scanned {enabled} configured sources.")
        print(f"Credible lane matches: {len(jobs)} | filtered out: {len(rejected)}")
        print(f"Dashboard: {paths.dashboard}")
        if alerts:
            notify(alerts, paths, open_dashboard=True)
        elif open_dashboard:
            webbrowser.open(paths.dashboard.resolve().as_uri())
            print("No new strong matches this run.")
    elif alerts:
        notify(alerts, paths, open_dashboard=False)
    return len(alerts)


def watch(paths: RuntimePaths) -> None:
    config = load_json(paths.config, {})
    minutes = int(config.get("watch_interval_minutes", 15))
    print(f"JobScout v{__version__} watch mode. Checking every {minutes} minutes. Press Ctrl+C to stop.")
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] checking...")
            run_once(paths, open_dashboard=False, quiet=False)
        except KeyboardInterrupt:
            print("Stopped.")
            return
        except Exception as exc:
            print(f"Run error: {type(exc).__name__}: {exc}")
        time.sleep(minutes * 60)
