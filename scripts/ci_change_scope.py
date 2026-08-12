#!/usr/bin/env python3
"""Classify repository changes into conservative CI/release scopes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable


RUNTIME_KEYS = (
    "run_backend",
    "run_frontend",
    "run_mobile",
    "run_mac",
    "run_type_drift",
    "run_release",
)

DOC_ROOT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "MEMORY.md",
    "README.md",
    "SECURITY.md",
}


def _full_result() -> dict[str, bool]:
    return {
        "docs_only": False,
        "run_docs": True,
        **{key: True for key in RUNTIME_KEYS},
        "full": True,
    }


def _is_documentation(path: str) -> bool:
    return (
        path.startswith("docs/")
        or path in DOC_ROOT_FILES
        or ("/" not in path and path.endswith((".md", ".mdx", ".rst")))
    )


def _requires_full(path: str) -> bool:
    return (
        path.startswith(".github/")
        or path.startswith("scripts/")
        or path.startswith("packages/shared/")
        or path in {"deploy.sh", "docker-compose.yml", "docker-compose.prod.yml"}
        or path.endswith(
            (
                "/requirements.lock",
                "/requirements.txt",
                "/requirements-dev.txt",
                "/package-lock.json",
                "/pnpm-lock.yaml",
                "/yarn.lock",
            )
        )
        or path in {"package.json", "pyproject.toml", "uv.lock"}
    )


def classify_changes(
    paths: Iterable[str], *, event_name: str = "push"
) -> dict[str, bool]:
    """Return fail-closed CI scopes for a normalized changed-file list."""

    normalized = sorted({path.strip().lstrip("./") for path in paths if path.strip()})
    if event_name == "workflow_dispatch" or not normalized:
        return _full_result()
    if any(_requires_full(path) for path in normalized):
        return _full_result()

    result = {
        "docs_only": True,
        "run_docs": True,
        **{key: False for key in RUNTIME_KEYS},
        "full": False,
    }
    for path in normalized:
        if _is_documentation(path):
            continue
        result["docs_only"] = False
        if path.startswith("backend/"):
            result["run_backend"] = True
            if path.startswith("backend/app/") or path == "backend/main.py":
                result["run_type_drift"] = True
        elif path.startswith("frontend/"):
            result["run_frontend"] = True
        elif path.startswith("mobile/"):
            result["run_mobile"] = True
        elif path.startswith("apps/mac/"):
            result["run_mac"] = True
        elif path.startswith(("mcp-server/", "infra/")):
            return _full_result()
        else:
            return _full_result()

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "github", "shell"),
        default="json",
    )
    parser.add_argument("--event-name", default="push")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = classify_changes(sys.stdin.read().splitlines(), event_name=args.event_name)
    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        for key, value in result.items():
            rendered = "true" if value else "false"
            if args.format == "shell":
                rendered = "1" if value else "0"
                print(f"{key.upper()}={rendered}")
            else:
                print(f"{key}={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
