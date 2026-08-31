#!/usr/bin/env python3
"""Compute conservative content digests for repeatable release inputs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import subprocess
import sys
from pathlib import Path


SYSTEM_KB_PATHS = (
    "backend/requirements.lock",
    "backend/data/system_kb_v2_seed",
    "backend/data/food_nutrition_seed",
    "backend/knowledge",
    "backend/knowledge_base",
    "backend/migrations/managed",
    "backend/scripts/seed_food_nutrition.py",
    "backend/scripts/seed_system_kb_phase0.py",
    "backend/scripts/import_system_kb_v2_artifacts.py",
    "backend/app/database.py",
    "backend/app/models/system_knowledge.py",
    "backend/app/models/food_nutrition.py",
    "backend/app/services/clinical_claim_release.py",
    "backend/app/services/kbase_review_workspace.py",
    "backend/app/services/retrieval_guard.py",
    "backend/app/services/system_knowledge_ingest.py",
    "backend/app/services/system_knowledge_release_policy.py",
    "backend/app/services/system_knowledge_graph.py",
    "backend/app/services/system_knowledge_importer.py",
    "backend/app/services/system_knowledge_service.py",
    "backend/app/services/knowledge",
    "backend/app/tasks/system_knowledge_lifecycle.py",
)

SYSTEM_KB_CONFIG_PREFIXES = ("dedao_kbase_", "system_kb_")
SYSTEM_KB_CONFIG_MEMBERS = {"model_config"}
LEGACY_SYSTEM_KB_PATHS = (*SYSTEM_KB_PATHS, "backend/app/config.py")


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def _system_kb_config_material(repo: Path, commit: str) -> bytes:
    raw_source = _git(repo, "show", f"{commit}:backend/app/config.py")
    source = raw_source.decode("utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeError(f"cannot parse System KB config projection: {exc}") from exc

    settings_class = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Settings"
        ),
        None,
    )
    if settings_class is None:
        raise RuntimeError("System KB config projection requires class Settings")

    projected: list[tuple[str, str]] = []
    for node in settings_class.body:
        target_name: str | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
        if target_name is None:
            continue
        if target_name in SYSTEM_KB_CONFIG_MEMBERS or target_name.startswith(
            SYSTEM_KB_CONFIG_PREFIXES
        ):
            projected.append(
                (target_name, ast.dump(node, annotate_fields=True, include_attributes=False))
            )

    if not any(name.startswith(SYSTEM_KB_CONFIG_PREFIXES) for name, _ in projected):
        raise RuntimeError("no System KB settings found in config projection")
    return "\n".join(
        f"{name}\0{node_dump}" for name, node_dump in sorted(projected)
    ).encode("utf-8")


def compute_digest(repo: Path, commit: str, kind: str) -> str:
    resolved = _git(repo, "rev-parse", f"{commit}^{{commit}}").decode().strip()
    if kind == "requirements":
        material = _git(repo, "show", f"{resolved}:backend/requirements.lock")
    elif kind in {"system-kb", "system-kb-legacy"}:
        paths = SYSTEM_KB_PATHS if kind == "system-kb" else LEGACY_SYSTEM_KB_PATHS
        tracked_material = _git(
            repo,
            "ls-tree",
            "-r",
            "--full-tree",
            resolved,
            "--",
            *paths,
        )
        if not tracked_material.strip():
            raise RuntimeError("no tracked System KB release inputs found")
        if kind == "system-kb":
            material = (
                tracked_material
                + b"\0backend/app/config.py:system-kb-projection\0"
                + _system_kb_config_material(repo, resolved)
            )
        else:
            material = tracked_material
    else:
        raise RuntimeError(f"unknown digest kind: {kind}")
    return hashlib.sha256(material).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--kind",
        choices=("requirements", "system-kb", "system-kb-legacy"),
        required=True,
    )
    args = parser.parse_args()
    try:
        print(compute_digest(args.repo, args.commit, args.kind))
    except RuntimeError as exc:
        print(f"release input digest failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
