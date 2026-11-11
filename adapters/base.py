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

import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

DEFAULT_UA = "Dossier/0.1 (+https://github.com/Frazzlesprite/hermes-dossier)"
MAX_BYTES = 2_000_000
MIN_HOST_INTERVAL = 1.0
_TIMEOUT = 15.0

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


def _address_is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Is this a routable public address? Anything else is refused.

    v4-mapped IPv6 (`::ffff:127.0.0.1`) is judged as the IPv4 address it
    really is, or the loopback check would be one spelling away from useless.
    """
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if (
        address.is_private          # RFC 1918 and IPv6 ULA fc00::/7
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        return False
    # CGNAT (100.64/10) is not flagged as private by every Python version, and
    # `is_global` is the honest question: is this address routable on the
    # public internet at all?
    return address.is_global


def _resolve(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every address the host resolves to, or refuse if we cannot tell.

    Fail closed: a name we cannot resolve is not a name we will hand to
    `urlopen`, because the resolution there is the same one an attacker would
    be controlling.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise FetchRefused(f"refusing to fetch {host!r}: it does not resolve ({exc})") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]  # drop an IPv6 zone id
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError as exc:
            raise FetchRefused(f"refusing to fetch {host!r}: unreadable address {raw!r}") from exc
    if not addresses:
        raise FetchRefused(f"refusing to fetch {host!r}: no addresses returned")
    return addresses


def _validate(url: str) -> None:
    """Refuse a URL unless every address its host resolves to is public.

    Model-chosen domains, search results and links scraped out of fetched pages
    all reach this function, so a literal-only check is not enough: `lvh.me`
    resolves to 127.0.0.1, and `2130706433` is 127.0.0.1 on platforms that
    accept the legacy numeric form.

    Residual window: name resolution happens here and again inside `urlopen`, so
    a DNS server that answers differently the second time could still point at a
    private address. Closing that needs a connection pinned to the address we
    checked; it is a rewrite of the fetch stack, and this check is what makes
    the common cases impossible rather than unlikely.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchRefused(f"unsupported scheme {parsed.scheme!r}")
    host = (parsed.hostname or "").strip().rstrip(".")
    if not host:
        raise FetchRefused("no host")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchRefused(f"invalid port in {url!r}") from exc
    for address in _resolve(host, port):
        if not _address_is_public(address):
            raise FetchRefused(
                f"refusing to fetch {host!r}: it resolves to the non-public address {address}")


_robots_cache: dict[str, Optional[object]] = {}


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """The same host check on every hop, plus the same rate limit.

    `urlopen` follows a 302 to any host it is given, so a public page could
    bounce the fetch to 169.254.169.254 or the LAN and hand the response back as
    evidence. The redirect target is only fetched if it passes `_validate`, and
    the new host is throttled, because the limit is keyed on the original host.
    """

    def __init__(self, policy: "Policy") -> None:
        super().__init__()
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if request is None:
            return None
        _validate(request.full_url)
        _throttle(urllib.parse.urlparse(request.full_url).netloc, self.policy.min_interval)
        return request


def _opener(policy: "Policy") -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_GuardedRedirectHandler(policy))


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
    try:
        _validate(url)
    except FetchRefused as exc:
        # A scraped link to localhost is a note, not a crashed build.
        return Fetch(url=url, status=0, error=str(exc), retrieved_at=now_iso())
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
        with _opener(policy).open(request, timeout=policy.timeout) as response:
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
                error="truncated to size cap" if truncated else None)
    except FetchRefused as exc:
        return Fetch(url=url, status=0, error=f"redirect refused: {exc}", retrieved_at=now_iso())
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
    """Return (title, text, meta, time values) for an HTML document.

    Block-level lines are joined with sentence punctuation. Without that, an
    `<h1>` sitting above the first paragraph fuses into it and the extractor
    sees one long sentence: "Acme Robotics Acme Robotics builds robots".
    """
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass

    lines: list[str] = []
    description = (parser.meta.get("description") or parser.meta.get("og:description") or "").strip()
    if description:
        # The meta description is the page describing itself in one sentence, 
        # the best one-line claim available, and it is part of the document.
        lines.append(description.rstrip(".") + ".")
    for raw in parser.text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if lines and not lines[-1].endswith((".", "!", "?", ":", ";")):
            # Inline markup splits a sentence across lines: "We created" /
            # "Steam" / "in 2003". A full stop there turned one sentence into
            # three fragments, and fragments make poor evidence. A line that
            # starts lower-case, or a one or two word line with no terminal
            # punctuation, is the tail of the sentence above rather than a new
            # one.
            tail = line.split()
            if line[0].islower() or (len(tail) <= 2 and not line.endswith((".", "!", "?", ":", ";"))):
                lines[-1] += " " + line
                continue
            lines[-1] += "."
        lines.append(line)
    text = "\n".join(lines)
    return parser.title.strip(), text[:limit], parser.meta, parser.times


_DATE_PATTERNS = (
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"dateModified"\s*:\s*"([^"]+)"'),
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)'))


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
    """The best publication date we can honestly claim, or None.

    Only signals that actually mean "published": an article meta tag, a JSON-LD
    datePublished, or a `<time>` element on a page that declares itself an
    article. A bare `<time>` or `date` meta key is usually a copyright line or a
    navigation timestamp, and a wrong date is worse than no date.
    """
    for key in ("article:published_time", "article:published", "og:published_time", "datepublished", "publish-date"):
        if key in meta:
            got = _normalise_date(meta[key])
            if got:
                return got
    declares_article = (
        (meta.get("og:type") or "").casefold() == "article"
        or (meta.get("og:type") or "").casefold() == "newsarticle"
    )
    has_article_meta = "article:published_time" in meta or "article:published" in meta
    news_jsonld = re.search(
        r'"@type"\s*:\s*"(?:NewsArticle|BlogPosting|ReportageNewsArticle)"', html or "", re.I
    )
    if declares_article or has_article_meta or news_jsonld:
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
    # A wiki declaring "datePublished: 2001" is describing when the page was
    # first created, not when the sentence we quote was written. No date is
    # more honest than a 25-year-old one.
    return None


def json_load(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None
