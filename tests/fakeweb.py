"""A fake web: canned pages, no sockets, deterministic.

Adapters import `fetch` by name into their own module namespace, so the
monkeypatch has to reach each one. `install()` does that in one call and keeps
the tests honest about which URLs were actually requested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dossier.adapters import base as base_mod
from dossier.adapters import github as github_mod
from dossier.adapters import news as news_mod
from dossier.adapters import official as official_mod
from dossier.adapters import search as search_mod

ACME_ABOUT_V1 = """<html><head><title>Acme Robotics</title>
<meta name="description" content="Acme Robotics builds warehouse robots.">
</head><body>
<h1>Acme Robotics</h1>
<p>Acme Robotics builds autonomous warehouse robots for mid-sized logistics operators.</p>
<p>Founded in 2014 in Canberra, Acme employs 120 employees across three sites.</p>
<p>Headquartered in Canberra, Australia.</p>
<p>Our CEO is Dana Whitfield and she has led the company since 2019.</p>
</body></html>"""

ACME_ABOUT_V2 = ACME_ABOUT_V1.replace("120 employees", "160 employees")

NEWS_PAGE = """<html><head><title>Acme Robotics raises $40 million</title>
<meta property="article:published_time" content="2026-10-02T09:00:00Z">
</head><body><p>Acme Robotics raised $40 million in a Series B round led by Harbour Fund.</p>
<p>The company said the money would fund a second factory.</p></body></html>"""

AMBIGUOUS_A = """<html><head><title>Sarah Chen — Partner, Harbour Fund</title></head>
<body><p>Sarah Chen is a partner at Harbour Fund, based in Sydney.</p></body></html>"""

AMBIGUOUS_B = """<html><head><title>Sarah Chen — Engineer, Acme Robotics</title></head>
<body><p>Sarah Chen is a hardware engineer at Acme Robotics, based in Canberra.</p></body></html>"""


@dataclass
class FakeWeb:
    pages: dict[str, str] = field(default_factory=dict)
    requested: list[str] = field(default_factory=list)
    results: list[dict[str, str]] = field(default_factory=list)

    def fetch(self, url, policy=None):
        self.requested.append(url)
        html = self.pages.get(url)
        if html is None:
            for key, value in self.pages.items():
                if url.rstrip("/") == key.rstrip("/"):
                    html = value
                    break
        if html is None:
            return base_mod.Fetch(url=url, status=404, error="HTTP 404", retrieved_at="2026-11-08T00:00:00Z")
        return base_mod.Fetch(
            url=url,
            status=200,
            text=html,
            content_type="text/html",
            retrieved_at="2026-11-08T00:00:00Z",
            final_url=url,
        )

    def search(self, query, limit):
        return self.results[:limit]


def install(monkeypatch, web: FakeWeb) -> FakeWeb:
    for module in (base_mod, official_mod, search_mod, news_mod, github_mod):
        if hasattr(module, "fetch"):
            monkeypatch.setattr(module, "fetch", web.fetch)
    return web


def acme_web(version: int = 1) -> FakeWeb:
    about = ACME_ABOUT_V1 if version == 1 else ACME_ABOUT_V2
    return FakeWeb(
        pages={
            "https://acme.example/": about,
            "https://acme.example/about": about,
            "https://news.example/acme-series-b": NEWS_PAGE,
        },
        results=[
            {"url": "https://acme.example/", "title": "Acme Robotics"},
            {"url": "https://acme.example/about", "title": "Acme Robotics"},
        ],
    )
