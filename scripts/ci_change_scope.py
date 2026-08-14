#!/usr/bin/env python3
"""Classify repository changes into conservative CI/release scopes."""

from __future__ import annotations

import argparse
import json
import re
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

MAC_RELEASE_PATHS = {
    "apps/mac/scripts/package-app.sh",
    "apps/mac/scripts/release-dmg.sh",
    "apps/mac/scripts/mac_release_publish.py",
}

MOBILE_RELEASE_PATHS = {
    "mobile/app.json",
    "mobile/app.config.js",
    "mobile/app.config.ts",
    "mobile/eas.json",
    "mobile/package.json",
}
_NAME_STATUS_RE = re.compile(r"^[ACDMRTUXB][0-9]{0,3}$")


def parse_name_status_z(raw: bytes) -> tuple[str, ...]:
    """Return every path endpoint from ``git diff --name-status -z``."""

    if not raw:
        return ()
    fields = raw.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    paths: list[str] = []
    index = 0
    while index < len(fields):
        try:
            status = fields[index].decode("ascii", errors="strict")
        except UnicodeError as error:
            raise ValueError("non-ASCII Git status") from error
        index += 1
        if _NAME_STATUS_RE.fullmatch(status) is None:
            raise ValueError(f"unsupported Git status: {status!r}")
        path_count = 2 if status[0] in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise ValueError(f"incomplete Git status record: {status}")
        for raw_path in fields[index : index + path_count]:
            path = raw_path.decode("utf-8", errors="surrogateescape")
            if not path or "\n" in path or "\r" in path or "\0" in path:
                raise ValueError("unsafe Git path")
            paths.append(path)
        index += path_count
    return tuple(paths)


def _full_result() -> dict[str, bool]:
    return {
        "docs_only": False,
        "run_docs": True,
        **{key: True for key in RUNTIME_KEYS},
        "full": True,
    }


def _is_documentation(path: str) -> bool:
    colocated_client_docs = {
        "apps/mac/README.md",
        "apps/watch/README.md",
        "apps/rokid-pushup-glasses/README.md",
        "mobile/PRODUCT_MAP.md",
        "mobile/SENTRY_SETUP.md",
    }
    return (
        path.startswith("docs/")
        or path in DOC_ROOT_FILES
        or path in colocated_client_docs
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

    def normalize(path: str) -> str:
        value = path.strip()
        return value[2:] if value.startswith("./") else value

    normalized = sorted({normalize(path) for path in paths if path.strip()})
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
            result["run_release"] = True
            if path.startswith("backend/app/") or path == "backend/main.py":
                result["run_type_drift"] = True
        elif path.startswith("frontend/"):
            result["run_frontend"] = True
        elif path.startswith("mobile/"):
            result["run_mobile"] = True
            if path in MOBILE_RELEASE_PATHS:
                result["run_release"] = True
        elif path.startswith("apps/mac/"):
            result["run_mac"] = True
            if path in MAC_RELEASE_PATHS:
                result["run_release"] = True
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
    parser.add_argument(
        "--input-format",
        choices=("paths", "name-status-z"),
        default="paths",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.input_format == "name-status-z":
        try:
            paths = parse_name_status_z(sys.stdin.buffer.read())
        except ValueError as error:
            print(f"change classifier input error: {error}", file=sys.stderr)
            return 2
    else:
        paths = tuple(sys.stdin.read().splitlines())
    result = classify_changes(paths, event_name=args.event_name)
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
