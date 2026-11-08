"""Load the plugin exactly the way Hermes does.

Hermes imports a directory plugin with `spec_from_file_location(...,
submodule_search_locations=[plugin_dir])`, so the plugin is a package and its
internal imports are relative. Loading it the same way here means the tests fail
for the same reasons the loader would, instead of passing under a plain
`sys.path` trick.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    if "dossier" in sys.modules:
        return sys.modules["dossier"]
    spec = importlib.util.spec_from_file_location(
        "dossier", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dossier"] = module
    spec.loader.exec_module(module)
    return module


load_plugin()
