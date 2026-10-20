"""Conservative HTTP checks of the exact employer application for CLI searches."""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .http import UA
from .utils import iso_now, strip_html

CLOSED = re.compile(
    r"(?:this\s+(?:job(?:\s+post(?:ing)?)?|position|posting)\s+"
    r"(?:is\s+)?(?:no\s+longer\s+(?:available|exists|accepting\s+applications)|"
    r"has\s+been\s+(?:filled|closed))|"
    r"(?:job|position|posting)\s+(?:not\s+found|does\s+not\s+exist)|"
    r"(?:this\s+)?(?:job|position|posting)\s+has\s+expired|"
    r"no\s+longer\s+accepting\s+applications)", re.I
)
APPLY = re.compile(r"(?:apply\s+(?:now|for\s+this\s+(?:job|position)|for|to)|submit\s+application|job_application)", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _safe_public_url(url: str) -> bool:
    try:
        uri = urllib.parse.urlsplit(url)
        host = (uri.hostname or "").lower()
        if uri.scheme not in ("http", "https") or not host:
            return False
        if host == "localhost" or host.endswith((".local", ".internal")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def _same_posting(start: str, final: str) -> bool:
    a, b = urllib.parse.urlsplit(start), urllib.parse.urlsplit(final)
    if a.hostname == b.hostname and a.path.rstrip("/") == b.path.rstrip("/"):
        return True
    ma, mb = re.search(r"/jobs/(\d+)", a.path), re.search(r"/jobs/(\d+)", b.path)
    return bool(ma and mb and ma.group(1) == mb.group(1))


def _workday_endpoint(url: str) -> str | None:
    uri = urllib.parse.urlsplit(url)
    if not (uri.hostname or "").endswith(".myworkdayjobs.com"):
        return None
    parts = [urllib.parse.unquote(p) for p in uri.path.split("/") if p]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts.pop(0)
    if len(parts) < 3 or parts[1] != "job":
        return None
    site = parts[0]
    tail = "/".join(parts[1:])
    tenant = uri.hostname.split(".")[0]
    return f"{uri.scheme}://{uri.netloc}/wday/cxs/{tenant}/{site}/{tail}"
