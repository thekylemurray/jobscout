from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import __version__

UA = f"JobScout/{__version__} (+https://github.com/your-username/jobscout)"

def _urlopen_with_retry(req: urllib.request.Request, timeout: int, attempts: int = 3):
    """Open a URL with bounded exponential backoff for transient failures."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
        except urllib.error.URLError as e:
            last_exc = e
            if attempt == attempts - 1:
                raise
        time.sleep(1.0 * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("request failed without an exception")

def request_json(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with _urlopen_with_retry(req, timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def request_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with _urlopen_with_retry(req, timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")

def request_json_post(url: str, payload: dict[str, Any], timeout: int = 30, referer: str | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with _urlopen_with_retry(req, timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def request_xml(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
