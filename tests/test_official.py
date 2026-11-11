"""The official site: the front page, the about pages it links, and the usual paths."""

from __future__ import annotations

import fakeweb

from dossier.adapters.official import collect_official

BARE = (
    "<html><head><title>Acme Robotics</title></head>"
    "<body><p>We build warehouse robots for logistics operators.</p></body></html>"
)

ABOUT = (
    "<html><head><title>About Acme</title></head>"
    "<body><p>Acme was founded in 2014 and employs 120 people across three sites.</p></body></html>"
)


def test_it_tries_the_usual_about_paths(monkeypatch):
    """A homepage with no about link still leads to the about page."""
    fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(
            pages={
                "https://acme.example/": BARE,
                "https://acme.example/about-us": ABOUT,
            }
        ),
    )
    result = collect_official("acme.example")
    urls = [doc.url for doc in result["documents"]]
    assert "https://acme.example/about-us" in urls


def test_a_missing_path_is_silent(monkeypatch):
    """Guessing a path is a probe, not a failure to report."""
    fakeweb.install(monkeypatch, fakeweb.FakeWeb(pages={"https://acme.example/": BARE}))
    result = collect_official("acme.example")
    assert [doc.url for doc in result["documents"]] == ["https://acme.example/"]
    assert result["notes"] == []


def test_linked_pages_come_first_and_are_not_fetched_twice(monkeypatch):
    page = (
        "<html><head><title>Acme Robotics</title></head><body>"
        "<p>We build warehouse robots.</p><a href=\"/about\">About</a>"
        "</body></html>"
    )
    web = fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(pages={"https://acme.example/": page, "https://acme.example/about": ABOUT}),
    )
    result = collect_official("acme.example")
    urls = [doc.url for doc in result["documents"]]
    assert urls == ["https://acme.example/", "https://acme.example/about"]
    assert web.requested.count("https://acme.example/about") == 1


def test_a_lookalike_domain_is_not_same_site(monkeypatch):
    """`evilacme.com` ends with `acme.com` and used to pass the same-site test."""
    page = (
        "<html><head><title>Acme Robotics</title></head><body>"
        "<p>We build warehouse robots.</p>"
        "<a href=\"https://evilacme.com/about\">About</a>"
        "</body></html>"
    )
    web = fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(pages={"https://acme.example/": page}),
    )
    result = collect_official("acme.example")
    assert all("evilacme.com" not in doc.url for doc in result["documents"])
    assert not any("evilacme.com" in url for url in web.requested)


def test_a_real_subdomain_is_same_site(monkeypatch):
    page = (
        "<html><head><title>Acme Robotics</title></head><body>"
        "<p>We build warehouse robots.</p>"
        "<a href=\"https://blog.acme.example/about\">About</a>"
        "</body></html>"
    )
    fakeweb.install(
        monkeypatch,
        fakeweb.FakeWeb(
            pages={"https://acme.example/": page, "https://blog.acme.example/about": ABOUT}
        ),
    )
    urls = [doc.url for doc in collect_official("acme.example")["documents"]]
    assert "https://blog.acme.example/about" in urls
