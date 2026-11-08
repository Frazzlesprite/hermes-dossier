"""Shared fetching for every adapter: polite, bounded, and honest about failure.

Rules baked in here rather than left to each adapter:

* one request per host per second, enforced with a lock so parallel adapters
  cannot quietly double the rate;
* a descriptive User-Agent;
* `robots.txt` respected, cached per host;
* a hard response size cap;
* no request to loopback, link-local or private addresses;
* every failure becomes a note, never a silent drop.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

DEFAULT_UA = "Dossier/0.1 (+https://github.com/Frazzlesprite/dossier-plugin)"
MAX_BYTES = 2_000_000
MIN_HOST_INTERVAL = 1.0
_TIMEOUT = 15.0

_PRIVATE_HOST = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.|\[?::1\]?$)"
)

_rate_lock = threading.Lock()
_last_hit: dict[str, float] = {}


class FetchRefused(Exception):
    """The URL is not something we will fetch at all (bad scheme, private host)."""


@dataclass(frozen=True)
class Fetch:
    url: str
    status: int = 0
    text: str = ""
    content_type: str = ""
    error: Optional[str] = None
    retrieved_at: str = ""
    final_url: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error


@dataclass
class Policy:
    user_agent: str = DEFAULT_UA
    timeout: float = _TIMEOUT
    max_bytes: int = MAX_BYTES
    respect_robots: bool = True
    min_interval: float = MIN_HOST_INTERVAL
    extra_headers: dict[str, str] = field(default_factory=dict)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _throttle(host: str, interval: float) -> None:
    if interval <= 0:
        return
    with _rate_lock:
        last = _last_hit.get(host)
        now = time.monotonic()
        if last is not None:
            wait = interval - (now - last)
            if wait > 0:
                time.sleep(wait)
        _last_hit[host] = time.monotonic()


def _validate(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchRefused(f"unsupported scheme {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise FetchRefused("no host")
    if _PRIVATE_HOST.match(host):
        raise FetchRefused(f"refusing to fetch a private/loopback host: {host}")


_robots_cache: dict[str, Optional[object]] = {}


def _robots_for(url: str, policy: Policy):
    """Cached robots.txt parser for the URL's scheme+host, or None if unusable."""
    parsed = urllib.parse.urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root in _robots_cache:
        return _robots_cache[root]
    parser = urllib.robotparser.RobotFileParser()
    try:
        resp = _raw_get(root + "/robots.txt", policy, allow_robots_file=True)
        if resp.ok and resp.text:
            parser.parse(resp.text.splitlines())
        else:
            parser.parse([])
    except Exception:
        parser.parse([])
    _robots_cache[root] = parser
    return parser


def _raw_get(url: str, policy: Policy, *, allow_robots_file: bool = False) -> Fetch:
    _validate(url)
    parsed = urllib.parse.urlparse(url)
    if policy.respect_robots and not allow_robots_file:
        parser = _robots_for(url, policy)
        try:
            if parser is not None and not parser.can_fetch(policy.user_agent, url):
                return Fetch(url=url, status=0, error="blocked by robots.txt", retrieved_at=now_iso())
        except Exception:
            pass

    _throttle(parsed.netloc, policy.min_interval)
    headers = {"User-Agent": policy.user_agent, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"}
    headers.update(policy.extra_headers)
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=policy.timeout) as response:
            raw = response.read(policy.max_bytes + 1)
            truncated = len(raw) > policy.max_bytes
            raw = raw[: policy.max_bytes]
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                body = raw.decode(charset, errors="replace")
            except LookupError:
                body = raw.decode("utf-8", errors="replace")
            return Fetch(
                url=url,
                status=response.status,
                text=body,
                content_type=response.headers.get("Content-Type", ""),
                retrieved_at=now_iso(),
                final_url=response.geturl(),
                error="truncated to size cap" if truncated else None,
            )
    except urllib.error.HTTPError as exc:
        return Fetch(url=url, status=exc.code, error=f"HTTP {exc.code}", retrieved_at=now_iso())
    except urllib.error.URLError as exc:
        return Fetch(url=url, status=0, error=f"network error: {exc.reason}", retrieved_at=now_iso())
    except Exception as exc:  # pragma: no cover - defensive
        return Fetch(url=url, status=0, error=f"{type(exc).__name__}: {exc}", retrieved_at=now_iso())


def fetch(url: str, policy: Optional[Policy] = None) -> Fetch:
    return _raw_get(url, policy or Policy())


class _TextExtractor(HTMLParser):
    """Collect visible text plus the handful of metadata fields we trust."""

    _SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "nav", "footer", "aside"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.times: list[str] = []
        self._depth_skip = 0
        self._in_title = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self._SKIP:
            self._depth_skip += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content") or ""
            if key and content:
                self.meta.setdefault(key, content)
        elif tag == "time" and attrs.get("datetime"):
            self.times.append(attrs["datetime"])
        elif tag in ("p", "div", "li", "br", "h1", "h2", "h3", "tr", "section", "article"):
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth_skip:
            self._depth_skip -= 1
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._depth_skip:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        return re.sub(r"[ \t\r\f\v]+", " ", "\n".join(self._chunks))


def html_to_text(html: str, limit: int = 40_000) -> tuple[str, str, dict[str, str], list[str]]:
    """Return (title, text, meta, time values) for an HTML document."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    text = "\n".join(line.strip() for line in parser.text().splitlines() if line.strip())
    return parser.title.strip(), text[:limit], parser.meta, parser.times


_DATE_PATTERNS = (
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"dateModified"\s*:\s*"([^"]+)"'),
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)'),
)


def _normalise_date(value: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return time.strftime("%Y-%m-%d", time.strptime(value[:32], fmt))
        except ValueError:
            continue
    return None


def published_at(html: str, times: list[str], meta: dict[str, str]) -> Optional[str]:
    """The best publication date we can honestly claim, or None."""
    for key in ("article:published_time", "datepublished", "publish-date", "date"):
        if key in meta:
            got = _normalise_date(meta[key])
            if got:
                return got
    for match in _DATE_PATTERNS:
        found = match.search(html or "")
        if found:
            got = _normalise_date(found.group(1))
            if got:
                return got
    for value in times:
        got = _normalise_date(value)
        if got:
            return got
    return None


def json_load(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None
