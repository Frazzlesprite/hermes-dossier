"""One live brief, end to end, against the real network.

No model, no search backend, no Hermes host — just the official-site and GitHub
adapters, the deterministic extractor, verification, composition, rendering and
a throwaway database. If this prints claims with dates, the pipeline works
outside the test fixtures.

    python scripts/live_check.py kalamari.club
    python scripts/live_check.py nousresearch.com --github NousResearch

Writes the brief to %TEMP%\\dossier-live.html and prints the card.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "dossier", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
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
    github = None
    if "--github" in argv:
        github = argv[argv.index("--github") + 1]

    load_plugin()
    from dossier import db, pipeline  # noqa: PLC0415 - after the package loads
    from dossier.pipeline import Config  # noqa: PLC0415

    workdir = Path(tempfile.mkdtemp(prefix="dossier-live-"))
    conn = db.connect(workdir / "live.db")
    try:
        result = pipeline.build(
            name,
            conn=conn,
            domain=name,
            github=github,
            config=Config(sources_per_brief=8),
            purpose="live smoke check",
        )
    finally:
        conn.close()

    print("status:", result.get("status"))
    if result.get("status") != "ok":
        print(result.get("error"))
        for candidate in result.get("candidates", []):
            print("  -", candidate["name"], candidate.get("disambiguator"))
        return 1

    print("entity:", result["entity"])
    print("counts:", result["counts"])
    print()
    print(result["card"])
    print()
    for claim in result["claims"]:
        quote = claim["evidence"][0]["quote"][:90]
        print(f"  [{claim['status']:<10}] {claim['predicate']:<10} {claim['value'][:60]}")
        print(f"               {claim['confidence']:.2f}  {quote}…")

    out = Path(tempfile.gettempdir()) / "dossier-live.html"
    out.write_text(result["html"], encoding="utf-8")
    print("\nbrief:", out)
    if result.get("notes"):
        print("\nnotes:")
        for note in result["notes"]:
            print("  -", note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
