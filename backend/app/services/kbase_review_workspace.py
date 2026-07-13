"""Coordination and validation for the persistent dedao-kbase review workspace."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterator

from app.services.system_knowledge_ingest import ARTIFACT_FILES


def workspace_backup_path(artifact_dir: str | Path) -> Path:
    target = Path(artifact_dir)
    return target.with_name(f".{target.name}.backup")


@contextmanager
def review_workspace_lock(artifact_dir: str | Path) -> Iterator[None]:
    target = Path(artifact_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / f".{target.name}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            _recover_interrupted_replacement(target)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_workspace_metadata(artifact_dir: str | Path) -> dict[str, Any]:
    path = Path(artifact_dir) / "draft_manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def workspace_content_fingerprint(artifact_dir: str | Path) -> str:
    root = Path(artifact_dir)
    required = (*ARTIFACT_FILES, "manifest.json", "draft_manifest.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"review workspace is incomplete: missing {', '.join(missing)}")
    digest = hashlib.sha256()
    for name in required:
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update((root / name).read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def workspace_artifacts_valid(artifact_dir: str | Path) -> bool:
    root = Path(artifact_dir)
    required = (*ARTIFACT_FILES, "manifest.json", "draft_manifest.json")
    if not root.is_dir() or any(not (root / name).is_file() for name in required):
        return False
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        draft_manifest = json.loads((root / "draft_manifest.json").read_text(encoding="utf-8"))
        counts = manifest.get("counts") if isinstance(manifest, dict) else None
        if not isinstance(counts, dict) or not isinstance(draft_manifest, dict):
            return False
        actual_counts: dict[str, int] = {}
        for name in ARTIFACT_FILES:
            rows = [line for line in (root / name).read_text(encoding="utf-8").splitlines() if line.strip()]
            actual_counts[Path(name).stem] = len(rows)
            for line in rows:
                if not isinstance(json.loads(line), dict):
                    return False
        if sum(actual_counts.values()) == 0:
            return False
        if any(counts.get(name) != count for name, count in actual_counts.items()):
            return False
    except (OSError, json.JSONDecodeError):
        return False
    return True


def _recover_interrupted_replacement(target: Path) -> None:
    backup = workspace_backup_path(target)
    if not backup.exists():
        return
    if target.exists():
        shutil.rmtree(backup)
    else:
        os.replace(backup, target)
