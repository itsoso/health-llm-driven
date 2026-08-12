#!/usr/bin/env python3
"""Compute conservative content digests for repeatable release inputs."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


SYSTEM_KB_PATHS = (
    "backend/data/system_kb_v2_seed",
    "backend/data/food_nutrition_seed",
    "backend/knowledge",
    "backend/knowledge_base",
    "backend/migrations/managed",
    "backend/scripts/seed_food_nutrition.py",
    "backend/scripts/seed_system_kb_phase0.py",
    "backend/scripts/import_system_kb_v2_artifacts.py",
    "backend/app/models/system_knowledge.py",
    "backend/app/models/food_nutrition.py",
    "backend/app/services/system_knowledge_release_policy.py",
    "backend/app/services/system_knowledge_graph.py",
    "backend/app/services/system_knowledge_importer.py",
    "backend/app/services/system_knowledge_service.py",
    "backend/app/services/knowledge",
    "backend/app/tasks/system_knowledge_lifecycle.py",
)


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def compute_digest(repo: Path, commit: str, kind: str) -> str:
    resolved = _git(repo, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if kind == "requirements":
        material = _git(repo, "show", f"{resolved}:backend/requirements.lock")
    elif kind == "system-kb":
        material = _git(
            repo,
            "ls-tree",
            "-r",
            "--full-tree",
            resolved,
            "--",
            *SYSTEM_KB_PATHS,
        )
        if not material.strip():
            raise RuntimeError("no tracked System KB release inputs found")
    else:
        raise RuntimeError(f"unknown digest kind: {kind}")
    return hashlib.sha256(material).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--kind", choices=("requirements", "system-kb"), required=True)
    args = parser.parse_args()
    try:
        print(compute_digest(args.repo, args.commit, args.kind))
    except RuntimeError as exc:
        print(f"release input digest failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
