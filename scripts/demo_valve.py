r"""Replay the captured Valve source set through the real pipeline.

No network, no model. Every page comes from the capture made by
`capture_valve.py`, including the failures, so the notes in the brief are the
ones the live run produced. Two builds, so the diff has something to compare.

    python scripts/demo_valve.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(tempfile.gettempdir()) / "dossier-valve-cache"
LAST: dict[str, object] = {}


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "dossier", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dossier"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    index = json.loads((CACHE / "index.json").read_text(encoding="utf-8"))
    pages = index["pages"]
    queries = index["queries"]

    load_plugin()
    from dossier import db, pipeline  # noqa: PLC0415
    from dossier.adapters import base, github, news, official, registry, search  # noqa: PLC0415
    from dossier.pipeline import Config  # noqa: PLC0415

    served: list[str] = []
    missing: list[str] = []

    def replay_fetch(url, policy=None):
        entry = pages.get(url)
        if entry is None:
            for key, value in pages.items():
                if key.rstrip("/") == url.rstrip("/"):
                    entry, url = value, key
                    break
        if entry is None:
            missing.append(url)
            return base.Fetch(url=url, status=0, error="not in the captured set", retrieved_at=index["captured_at"])
        served.append(url)
        text = ""
        if entry.get("file"):
            text = (CACHE / entry["file"]).read_text(encoding="utf-8", errors="replace")
        return base.Fetch(
            url=url,
            status=int(entry.get("status") or 0),
            text=text,
            content_type=entry.get("content_type") or "",
            error=entry.get("error"),
            retrieved_at=entry.get("retrieved_at") or index["captured_at"],
            final_url=entry.get("final_url") or url,
        )

    for module in (base, official, search, news, github, registry):
        if hasattr(module, "fetch"):
            module.fetch = replay_fetch

    # The SEC ticker list is cached on disk by the registry adapter, so the live
    # run never fetched it. Seed the same cache here to get the same note.
    tickers = CACHE / "edgar_tickers.json"
    if tickers.exists():
        payload = json.loads(tickers.read_text(encoding="utf-8"))
        registry._ticker_cache.update({"at": float(payload.get("at", 0)), "entries": payload.get("entries", {})})
        registry._ticker_cache_path = lambda: tickers

    fallback = next(iter(queries.values()), [])

    def search_fn(query: str, limit: int):
        results = queries.get(query)
        if results is None:
            for key, value in queries.items():
                if key.casefold() == query.casefold():
                    results = value
                    break
        return (results if results is not None else fallback)[:limit]

    purpose = os.environ.get("DOSSIER_PURPOSE", "demo")
    context = os.environ.get("DOSSIER_CONTEXT") or None
    workdir = Path(tempfile.mkdtemp(prefix="dossier-valve-"))
    conn = db.connect(workdir / "valve.db")
    config = Config(registry_contact="demo@example.invalid")
    try:
        first = pipeline.build(
            index["name"], conn=conn, search_fn=search_fn, domain=index["domain"],
            config=config, purpose=purpose, context=context)
        second = pipeline.build(
            index["name"], conn=conn, search_fn=search_fn, domain=index["domain"],
            config=config, purpose=purpose, context=context)
    finally:
        conn.close()

    if first.get("status") != "ok":
        print("build failed:", first.get("error"))
        return 1

    out = Path(tempfile.gettempdir())
    html_path = out / "valve-brief.html"
    html_path.write_text(first["html"], encoding="utf-8")
    pdf_path = out / "valve-brief.pdf"
    pdf_path.write_bytes(first["pdf"])

    print("captured at :", index["captured_at"])
    print("pages served:", len(served), "| missing:", len(missing))
    for url in missing:
        print("   missing:", url)
    print("counts      :", first["counts"])
    print("headline    :", first["headline"])
    print("questions   :", first["questions"])
    print("diff        :", (second.get("diff") or {}).get("changed_count"), "change(s)")
    print("notes:")
    for note in first["notes"]:
        print("   -", note)
    print("claims:")
    for claim in first["claims"]:
        first_ev = claim["evidence"][0]
        print(f"   [{claim['status']:<11}] {claim['predicate']:<9} {claim['value'][:46]!r}")
        print(f"                 {first_ev['source_url']}")
    print("html        :", html_path)
    print("pdf         :", pdf_path)

    LAST.update({"first": first, "second": second, "index": index, "html": html_path, "pdf": pdf_path, "served": served})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
