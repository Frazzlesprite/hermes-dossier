"""The demo case, offline: a contradiction, then a leadership change.

Two sources disagree about headcount, so the brief prints both and refuses to
pick. Then a second run changes the CEO, so the diff reports one change and
stays quiet about everything else. No network, no model, no timing luck, the
same run every time, which is the point when a 90-second video only gets one
take.

    python scripts/demo_contradiction.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ABOUT_V1 = """<html><head><title>Acme Robotics</title>
<meta name="description" content="Acme Robotics builds warehouse robots."></head><body>
<h1>Acme Robotics</h1>
<p>Acme Robotics builds autonomous warehouse robots for mid-sized logistics operators.</p>
<p>Founded in 2014, the company employs 120 employees across three sites.</p>
<p>Headquartered in Canberra, Australia.</p>
<p>Our CEO is Dana Whitfield and she has led the company since 2019.</p>
</body></html>"""

ABOUT_V2 = ABOUT_V1.replace(
    "Our CEO is Dana Whitfield and she has led the company since 2019.",
    "Our CEO is Priya Raman, appointed in October 2026.")

NEWS = """<html><head><title>Acme Robotics says headcount has grown to 160 employees</title>
<meta property="article:published_time" content="2026-10-02T09:00:00Z"></head><body>
<p>Acme Robotics says the company now employs 160 employees, up from 120 last year.</p>
<p>The company said the growth followed a Series B round led by Harbour Fund.</p>
</body></html>"""

# A saved registry response set, so the demo does not depend on network timing.
REG_TICKERS = """{"0":{"cik_str":1234567,"ticker":"ACME","title":"Acme Robotics, Inc."}}"""
REG_SUBMISSIONS = """{"name":"Acme Robotics, Inc.","sicDescription":"Industrial Robots",
"addresses":{"business":{"city":"CANBERRA","stateOrCountry":"ACT"}},
"filings":{"recent":{"form":["10-Q","10-K"],"filingDate":["2026-09-30","2026-03-14"]}}}"""

GITHUB_ORG = """{"login":"acme","name":"Acme Robotics","description":"autonomous warehouse robots",
"location":"Canberra, Australia","blog":"https://acme.example","public_repos":12}"""
GITHUB_REPOS = """[{"name":"fleet-os","pushed_at":"2026-10-28T00:00:00Z"},
{"name":"sim-warehouse","pushed_at":"2026-09-14T00:00:00Z"}]"""


LAST: dict[str, object] = {}


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "dossier", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dossier"] = module
    spec.loader.exec_module(module)
    return module


def install_web(pages: dict[str, str], results: list[dict[str, str]]):
    """Point every adapter at a saved source set."""
    from dossier.adapters import base, github, news, official, registry, search

    class Web:
        def fetch(self, url, policy=None):
            html = pages.get(url)
            if html is None:
                for key, value in pages.items():
                    if key in url:
                        html = value
                        break
            if html is None:
                return base.Fetch(url=url, status=404, error="HTTP 404", retrieved_at="2026-11-09T00:00:00Z")
            return base.Fetch(
                url=url, status=200, text=html, content_type="text/html",
                retrieved_at="2026-11-09T00:00:00Z", final_url=url)

        def search(self, query, limit):
            return results[:limit]

    web = Web()
    for module in (base, official, search, news, github, registry):
        if hasattr(module, "fetch"):
            module.fetch = web.fetch
    return web


def main() -> int:
    load_plugin()
    from dossier import db, pipeline  # noqa: PLC0415
    from dossier.pipeline import Config  # noqa: PLC0415

    pages = {
        "https://acme.example/": ABOUT_V1,
        "https://acme.example/about": ABOUT_V1,
        "https://news.example/acme-headcount": NEWS,
        "company_tickers": REG_TICKERS,
        "data.sec.gov/submissions": REG_SUBMISSIONS,
        "api.github.com/orgs/acme/repos": GITHUB_REPOS,
        "api.github.com/orgs/acme": GITHUB_ORG,
    }
    results = [
        {"url": "https://acme.example/", "title": "Acme Robotics"},
        {"url": "https://acme.example/about", "title": "Acme Robotics"},
        {"url": "https://news.example/acme-headcount", "title": "Acme Robotics says headcount has grown to 160 employees"},
    ]
    web = install_web(pages, results)
    from dossier.adapters import registry as registry_mod  # noqa: PLC0415

    registry_mod._ticker_cache.update({"at": 0.0, "entries": {}})
    registry_mod._ticker_cache_path = lambda: None

    workdir = Path(tempfile.mkdtemp(prefix="dossier-demo-"))
    conn = db.connect(workdir / "demo.db")
    config = Config(registry_contact="demo@example.invalid", country="US")
    try:
        first = pipeline.build("Acme Robotics", conn=conn, search_fn=web.search, config=config)
        print("=" * 68)
        print("FIRST LOOK")
        print("=" * 68)
        print(first["card"])
        print()
        types: dict[str, int] = {}
        for claim in first["claims"]:
            for item in claim["evidence"]:
                types[item["source_type"]] = types.get(item["source_type"], 0) + 1
        print("  sources fetched by type:", types, "| claims:", len(first["claims"]))
        for note in first.get("notes", []):
            print("  note:", note)
        print()
        for section in _sections(first):
            print(section)
        print()

        print("=" * 68)
        print("CONTESTED: printed as two sides, not a winner")
        print("=" * 68)
        for claim in first["claims"]:
            if claim["status"] == "contested":
                print(f"  {claim['predicate']}: {claim['value']}  (confidence {claim['confidence']})")
                for item in claim["evidence"]:
                    print(f"    - {item['published_at'] or item['retrieved_at'][:10]}  {item['source_url']}")
                    print(f"      \"{item['quote'][:110]}\"")
        print()

        # Second run: the CEO changed, nothing else did.
        pages["https://acme.example/"] = ABOUT_V2
        pages["https://acme.example/about"] = ABOUT_V2
        second = pipeline.build("Acme Robotics", conn=conn, search_fn=web.search, config=config)
        diff = second.get("diff") or {}
        print("=" * 68)
        print(f"REFRESH: {diff.get('changed_count', 0)} change(s) since {diff.get('from')}")
        print("=" * 68)
        for item in diff.get("added", []):
            print(f"  + {item['predicate']}: {item['value']}")
        for item in diff.get("removed", []):
            print(f"  - {item['predicate']}: {item['value']}")
        for item in diff.get("changed", []):
            print(f"  ~ {item['predicate']}: {item['value']} ({item['from']['status']} -> {item['to']['status']})")

        out = Path(tempfile.gettempdir()) / "dossier-demo.html"
        out.write_text(second["html"], encoding="utf-8")
        pdf_out = Path(tempfile.gettempdir()) / "dossier-demo.pdf"
        pdf_out.write_bytes(second["pdf"])
        LAST.update({"first": first, "second": second, "diff": diff, "html": out, "pdf": pdf_out})
        print(f"\nbrief: {out}")
        print(f"pdf  : {pdf_out}")
    finally:
        conn.close()
    return 0


def _sections(result: dict) -> list[str]:
    lines = []
    for claim in result["claims"]:
        if claim["predicate"] in ("product", "hq", "founded", "employees", "ceo"):
            quote = claim["evidence"][0]["quote"][:80]
            lines.append(f"  [{claim['status']:<10}] {claim['predicate']:<10} {claim['value'][:58]}")
            lines.append(f"               \"{quote}…\"")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
