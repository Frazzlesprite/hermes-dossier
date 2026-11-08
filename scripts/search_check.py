r"""Prove the search and news adapters against a real backend response.

The adapters only ever see what `web_search` hands them, so the risk is a shape
mismatch that fails silently. This runs the real Hermes search tool, prints the
envelope it returns, then builds a brief through the normal adapters using that
output, which is the same path a session takes through `ctx.dispatch_tool`.

Run it inside the Hermes environment:

    set HERMES_HOME=%LOCALAPPDATA%\hermes
    cd %LOCALAPPDATA%\hermes\hermes-agent
    <hermes venv python> C:\Backpack\dossier-plugin\scripts\search_check.py "Kalamari" kalamari.club
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("DOSSIER_PLUGIN_ROOT", r"C:\Backpack\dossier-plugin"))


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "dossier", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dossier"] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    name = argv[0]
    domain = argv[1] if len(argv) > 1 else None

    from tools.web_tools import web_search_tool  # noqa: PLC0415 - Hermes' own tool

    query = f'"{name}"'
    raw = web_search_tool(query, 5)
    print("=" * 68)
    print("RAW web_search RESPONSE")
    print("=" * 68)
    try:
        payload = json.loads(raw)
    except Exception:
        print(raw[:800])
        payload = None
    if isinstance(payload, dict):
        print("keys:", list(payload.keys()))
        print(json.dumps(payload, indent=2)[:900])
    if not payload or payload.get("success") is False:
        print("\nsearch backend unavailable:", (payload or {}).get("error", "unparseable response"))
        return 1

    load_plugin()
    from dossier import db, pipeline  # noqa: PLC0415
    from dossier.adapters.search import normalise_results  # noqa: PLC0415
    from dossier.pipeline import Config  # noqa: PLC0415

    results = normalise_results(raw)
    print("\nnormalised:", len(results), "result(s)")
    for item in results[:5]:
        print("  -", item["url"])

    def search_fn(q: str, limit: int):
        return web_search_tool(q, limit)

    workdir = Path(tempfile.mkdtemp(prefix="dossier-search-"))
    conn = db.connect(workdir / "search.db")
    try:
        result = pipeline.build(
            name,
            conn=conn,
            search_fn=search_fn,
            domain=domain,
            config=Config(registry_contact=os.environ.get("DOSSIER_REGISTRY_CONTACT", "")),
            purpose="search check")

        second = None
        if "--second-run" in argv:
            second = pipeline.build(
                name,
                conn=conn,
                search_fn=search_fn,
                domain=domain,
                config=Config(registry_contact=os.environ.get("DOSSIER_REGISTRY_CONTACT", "")),
                purpose="search check")
    finally:
        conn.close()

    print("\nstatus:", result.get("status"), result.get("error") or "")
    if result.get("status") != "ok":
        return 1
    print("counts:", result["counts"])
    by_type: dict[str, int] = {}
    for claim in result["claims"]:
        for item in claim["evidence"]:
            by_type[item["source_type"]] = by_type.get(item["source_type"], 0) + 1
    print("evidence by source type:", by_type)
    print("\nheadline:", result["headline"])
    print("questions:")
    for question in result["questions"]:
        print("  -", question)
    print("\nnotes:")
    for note in result["notes"]:
        print("  -", note)

    if "--claims" in argv:
        print("\nclaims:")
        for claim in result["claims"]:
            first = claim["evidence"][0]
            print(f"  [{claim['status']:<9}] {claim['predicate']:<10} {claim['value'][:52]!r}")
            print(f"              {first['source_type']}: {first['source_url']}")
            print(f"              \"{first['quote'][:120]}\"")

    if second is not None:
        diff = second.get("diff") or {}
        print("\nsecond run:")
        print("  counts:", second.get("counts"))
        print("  diff  :", diff.get("changed_count", 0), "change(s) since", diff.get("from"))
        for item in diff.get("added", [])[:5]:
            print("    +", item["predicate"], item["value"])
        for item in diff.get("removed", [])[:5]:
            print("    -", item["predicate"], item["value"])
        for item in diff.get("changed", [])[:5]:
            print("    ~", item["predicate"], item["value"], item["from"], "->", item["to"])

    out_dir = Path(tempfile.gettempdir())
    html_path = out_dir / "dossier-search.html"
    html_path.write_text(result["html"], encoding="utf-8")
    pdf_path = out_dir / "dossier-search.pdf"
    pdf_path.write_bytes(result["pdf"])
    print("\nhtml:", html_path)
    print("pdf :", pdf_path, f"({len(result['pdf'])} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
