r"""Exercise the installed plugin through Hermes' own storage, without a model.

The harness routes: load the plugin from the installed location, call the tool
handlers exactly as the dispatcher would, and let `plugin_db` /
`plugin_data_dir` resolve to the real Hermes home. This is the check that
proves storage and the handler contract in the host environment, everything the
model would do, minus the model.

    set HERMES_HOME=%LOCALAPPDATA%\hermes
    python scripts/harness_check.py kalamari.club https://kalamari.club
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

PLUGIN_ID = "dossier"


def installed_plugin_dir() -> Path:
    home = os.environ.get("HERMES_HOME")
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "plugins" / PLUGIN_ID


def load_plugin(root: Path):
    if "dossier" in sys.modules:
        return sys.modules["dossier"]
    spec = importlib.util.spec_from_file_location(
        "dossier", root / "__init__.py", submodule_search_locations=[str(root)]
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

    root = installed_plugin_dir()
    if not root.is_dir():
        print(f"not installed at {root}")
        return 1

    print("HERMES_HOME:", os.environ.get("HERMES_HOME") or "(unset, default)")
    print("plugin dir :", root)
    load_plugin(root)

    from plugins.plugin_storage import plugin_data_dir, plugin_db  # noqa: PLC0415

    print("data dir   :", plugin_data_dir(PLUGIN_ID))
    plugin_db(PLUGIN_ID).close()

    from dossier import tools  # noqa: PLC0415

    built = json.loads(tools.build({"name": name, "domain": domain, "purpose": "harness check"}))
    print("\nbuild      :", built.get("status"), built.get("counts") or built.get("error"))
    if built.get("status") != "ok":
        return 1
    print("headline   :", built.get("headline"))
    print("questions  :", built.get("questions"))
    print("brief      :", built.get("brief_path"))

    shown = json.loads(tools.show({"name": built["entity"]["name"]}))
    print("\nshow       :", shown.get("status"), shown.get("claims"), "claim(s),", shown.get("taken_at"))

    diff = json.loads(tools.diff({"name": built["entity"]["name"]}))
    print("diff       :", diff.get("status"), diff.get("error") or f"{diff.get('changed_count')} change(s)")

    refreshed = json.loads(tools.refresh({"name": built["entity"]["name"]}))
    print("refresh    :", refreshed.get("status"), refreshed.get("counts") or refreshed.get("error"))
    if refreshed.get("diff"):
        print("after      :", refreshed["diff"]["changed_count"], "change(s) since the last snapshot")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
