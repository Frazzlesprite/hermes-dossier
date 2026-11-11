"""The fetcher refuses anything that is not a public address, on every hop.

Model-chosen domains, search results and links scraped out of fetched pages all
reach `_validate`, so the cases here are the ones an attacker can arrange: a name
that resolves to loopback, a legacy numeric spelling of 127.0.0.1, and a public
page that bounces the fetch somewhere private.

The resolver is always faked, so these tests never touch DNS.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

from dossier.adapters import base
from dossier.adapters.base import FetchRefused, Policy, _validate, fetch


def _resolves(monkeypatch, mapping: dict[str, str]) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        value = mapping.get(host)
        if value is None:
            raise socket.gaierror(f"no address for {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, port or 80))]

    monkeypatch.setattr(base.socket, "getaddrinfo", fake_getaddrinfo)


def test_a_public_address_is_allowed(monkeypatch):
    _resolves(monkeypatch, {"example.com": "93.184.216.34"})
    _validate("https://example.com/about")


def test_a_name_that_resolves_to_loopback_is_refused(monkeypatch):
    """lvh.me is a public DNS name pointing at 127.0.0.1, the original report."""
    _resolves(monkeypatch, {"lvh.me": "127.0.0.1"})
    with pytest.raises(FetchRefused, match="non-public address"):
        _validate("http://lvh.me:8080/")


def test_the_legacy_numeric_form_is_refused(monkeypatch):
    """2130706433 is 127.0.0.1 on platforms that accept the legacy form."""
    _resolves(monkeypatch, {"2130706433": "127.0.0.1"})
    with pytest.raises(FetchRefused, match="non-public address"):
        _validate("http://2130706433:8080/")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",        # loopback
        "10.1.2.3",         # RFC 1918
        "172.16.0.9",       # RFC 1918
        "192.168.1.10",     # RFC 1918
        "169.254.169.254",  # link-local, the cloud metadata address
        "100.64.0.1",       # CGNAT
        "0.0.0.0",          # unspecified
        "224.0.0.1",        # multicast
        "255.255.255.255",  # reserved
        "::1",              # IPv6 loopback
        "fd00::1",          # IPv6 ULA
        "fe80::1",          # IPv6 link-local
        "::ffff:127.0.0.1", # v4-mapped loopback
        "::ffff:10.0.0.1",  # v4-mapped private
    ],
)
def test_every_non_public_range_is_refused(monkeypatch, address):
    _resolves(monkeypatch, {"elsewhere.example": address})
    with pytest.raises(FetchRefused, match="non-public address"):
        _validate("http://elsewhere.example/")


def test_an_unresolvable_host_is_refused(monkeypatch):
    """Fail closed: if we cannot tell where it points, we do not fetch it."""
    _resolves(monkeypatch, {})
    with pytest.raises(FetchRefused, match="does not resolve"):
        _validate("https://nowhere.example/")


def test_a_redirect_to_loopback_is_refused(monkeypatch):
    _resolves(monkeypatch, {"127.0.0.1": "127.0.0.1"})
    handler = base._GuardedRedirectHandler(Policy(min_interval=0))
    request = urllib.request.Request("https://example.com/")
    with pytest.raises(FetchRefused, match="non-public address"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/admin")


def test_a_redirect_to_a_public_host_is_allowed(monkeypatch):
    _resolves(monkeypatch, {"cdn.example": "93.184.216.34"})
    handler = base._GuardedRedirectHandler(Policy(min_interval=0))
    request = urllib.request.Request("https://example.com/")
    follow = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example/file")
    assert follow is not None
    assert follow.full_url == "https://cdn.example/file"


def test_a_refused_url_is_a_note_not_a_crash(monkeypatch):
    """A scraped link to localhost must degrade to a recorded failure."""
    _resolves(monkeypatch, {"lvh.me": "127.0.0.1"})
    result = fetch("http://lvh.me/", Policy(respect_robots=False))
    assert result.status == 0
    assert "non-public address" in (result.error or "")


def test_a_bad_scheme_is_refused():
    with pytest.raises(FetchRefused, match="unsupported scheme"):
        _validate("file:///etc/passwd")


def test_the_opener_actually_installs_the_guard():
    """`build_opener` skips a default handler only when a subclass is passed."""
    opener = base._opener(Policy())
    assert any(isinstance(handler, base._GuardedRedirectHandler) for handler in opener.handlers)
