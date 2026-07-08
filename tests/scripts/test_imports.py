from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_imports_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "imports.py"
    module_name = "imports_script_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_import_check_current_tree_passes() -> None:
    imports = _load_imports_module()

    assert imports.main() == 0
