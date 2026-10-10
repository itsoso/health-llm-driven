#!/usr/bin/env python3
"""Read-only local tool discovery. Does not install, authenticate or certify a release."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from itertools import islice
from pathlib import Path

PROFILES = {
    "base": ("git",),
    "ci": ("git", "node", "npm", "gh"),
    "ota": ("git", "node", "npm", "gh", "eas"),
    "testflight": ("git", "node", "npm", "gh", "eas", "xcodebuild"),
}


def _python_version(path: Path) -> str | None:
    # Fixed arguments only; isolated Python avoids startup hooks and inherited
    # credential/environment values. Never include raw output in the report.
    try:
        proc = subprocess.run([str(path), "-I", "--version"], capture_output=True,
                              text=True, timeout=5, env={"PYTHONNOUSERSITE": "1"}, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.fullmatch(r"Python (\d+\.\d+\.\d+)\s*", proc.stdout)
    return match.group(1) if proc.returncode == 0 and match else None


def inspect_environment(root: Path, profile: str, uv_cache: Path | None = None) -> dict:
    on_path = shutil.which("python3.12")
    candidates = [("path", Path(on_path))] if on_path else []
    candidates += [("project_venv", root / folder / "bin" / name)
                   for folder in (".venv", "backend/.venv") for name in ("python3.12", "python3")]
    cache = uv_cache if uv_cache is not None else Path.home() / ".local/share/uv/python"
    # Only inspect already-installed interpreters; no uv install/find network fallback.
    candidates += [("uv_cache", path) for path in islice(cache.glob("cpython-3.12.*/bin/python3.12"), 8)]
    python = {"usable": False, "on_path": False, "source": None, "version": None}
    seen = set()
    for source, candidate in candidates[:8]:
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        version = _python_version(candidate)
        if version and version.startswith("3.12."):
            python = {"usable": True, "on_path": source == "path", "source": source, "version": version}
            break
    tools = {name: {"available": shutil.which(name) is not None} for name in PROFILES[profile]}
    return {"scope": "local_tool_availability_only", "profile": profile, "python": python,
            "tools": tools, "ready": python["usable"] and all(item["available"] for item in tools.values()),
            "next_action": "use_detected_python_explicitly" if python["usable"] and not python["on_path"] else "review_local_tool_availability",
            "unverified": ["dependencies", "authentication", "network", "signing", "release_gates"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="base")
    args = parser.parse_args(argv)
    report = inspect_environment(Path(__file__).resolve().parents[1], args.profile)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
