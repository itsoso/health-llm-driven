#!/usr/bin/env python3
"""Load System Map modules only from this repository's scripts directory."""

from __future__ import annotations

import importlib._bootstrap
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType


class SystemMapImportError(ImportError):
    """Raised when a System Map module does not have canonical file identity."""


def _require_module_file(
    module: ModuleType,
    *,
    module_name: str,
    expected_path: Path,
) -> ModuleType:
    actual_path = getattr(module, "__file__", None)
    try:
        matches = actual_path is not None and os.path.samefile(
            actual_path,
            expected_path,
        )
    except (OSError, TypeError, ValueError):
        matches = False
    if not matches:
        raise SystemMapImportError(
            f"{module_name} loaded from unexpected path: "
            f"{actual_path!r}; expected {str(expected_path)!r}"
        )
    return module


def load_repo_module(module_name: str, scripts_dir: Path) -> ModuleType:
    """Return one canonical module, rejecting cached modules from elsewhere."""
    expected_path = scripts_dir / f"{module_name}.py"
    with importlib._bootstrap._ModuleLockManager(module_name):
        cached = sys.modules.get(module_name)
        if cached is not None:
            return _require_module_file(
                cached,
                module_name=module_name,
                expected_path=expected_path,
            )

        spec = importlib.util.spec_from_file_location(module_name, expected_path)
        if spec is None or spec.loader is None:
            raise SystemMapImportError(
                f"cannot load canonical System Map module: {expected_path}"
            )
        module = importlib.util.module_from_spec(spec)
        spec._initializing = True
        try:
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
                return _require_module_file(
                    module,
                    module_name=module_name,
                    expected_path=expected_path,
                )
            except BaseException:
                if sys.modules.get(module_name) is module:
                    sys.modules.pop(module_name, None)
                raise
        finally:
            spec._initializing = False
