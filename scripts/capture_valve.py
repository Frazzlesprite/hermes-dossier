r"""Capture a deterministic source set for the Valve demo.

Runs the real pipeline against the real web_search backend, but wraps every
fetch so each successful page is written to a cache. The replay script then
serves those pages from disk, which is how the video gets the same brief on
every take without pretending the network is stable.

Cache lives in the temp directory, not the repo: these are third-party pages and
a public repository is not the place to redistribute them.

    set HERMES_HOME=%LOCALAPPDATA%\hermes
    cd %LOCALAPPDATA%\hermes\hermes-agent
    <hermes python> C:\Backpack\dossier-plugin\scripts\capture_valve.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("DOSSIER_PLUGIN_ROOT", r"C:\Backpack\dossier-plugin"))
CACHE = Path(tempfile.gettempdir()) / "dossier-valve-cache"

NAME = "Valve Corporation"
DOMAIN = "valvesoftware.com"


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "dossier", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dossier"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    from tools.web_tools import web_search_tool  # noqa: PLC0415

    load_plugin()
    from dossier import db, pipeline  # noqa: PLC0415
    from dossier.adapters import base, github, news, official, registry, search  # noqa: PLC0415
    from dossier.adapters import registry as registry_mod  # noqa: PLC0415
    from dossier.pipeline import Config  # noqa: PLC0415

    CACHE.mkdir(parents=True, exist_ok=True)
    for stale in CACHE.glob("*.html"):
        stale.unlink()
    for stale in CACHE.glob("*.json"):
        stale.unlink()

    real_fetch = base.fetch
    index: dict[str, dict[str, str]] = {}

    def capture_fetch(url, policy=None):
        result = real_fetch(url, policy)
        entry = {
            "status": result.status,
            "error": result.error,
            "content_type": result.content_type,
            "retrieved_at": result.retrieved_at,
            "final_url": result.final_url or url,
            "file": "",
        }
        if result.text:
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            (CACHE / f"{digest}.html").write_text(result.text, encoding="utf-8", errors="replace")
            entry["file"] = f"{digest}.html"
        index[url] = entry
        return result

    for module in (base, official, search, news, github, registry):
        if hasattr(module, "fetch"):
            module.fetch = capture_fetch

    queries: dict[str, list[dict[str, str]]] = {}

    def search_fn(query: str, limit: int):
        from dossier.adapters.search import normalise_results  # noqa: PLC0415

        raw = web_search_tool(query, limit)
        queries[query] = normalise_results(raw)
        return raw

    workdir = CACHE / "run"
    workdir.mkdir(exist_ok=True)
    conn = db.connect(workdir / "capture.db")
    try:
        result = pipeline.build(
            NAME,
            conn=conn,
            search_fn=search_fn,
            domain=DOMAIN,
            config=Config(registry_contact=os.environ.get("DOSSIER_REGISTRY_CONTACT", "")),
            purpose="demo capture",
        )
    finally:
        conn.close()

    (CACHE / "index.json").write_text(        json.dumps(
            {
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "name": NAME,
                "domain": DOMAIN,
                "pages": index,
                "queries": queries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("status   :", result.get("status"))
    print("counts   :", result.get("counts"))
    print("headline :", result.get("headline"))
    print("pages    :", len(index))
    print("queries  :", len(queries))
    print("cache    :", CACHE)
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
