#!/usr/bin/env python3
"""Validate the pinned Chinese-CLIP manifest and local artifact hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import urlparse


COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EXPECTED_MODEL_ID = "OFA-Sys/chinese-clip-rn50"
EXPECTED_ARTIFACT_ROOT = PurePosixPath(".build/models/chinese-clip-rn50")
EXPECTED_COMPONENTS = {
    "shipped": ["image_encoder"],
    "buildTimeOnly": ["text_encoder", "tokenizer"],
}


class ManifestError(ValueError):
    """Raised when the provenance manifest is incomplete or inconsistent."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ManifestError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"cannot load manifest {path}: {error}") from error
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    return data


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{field} must be a non-empty string")
    return value


def _require_commit(value: Any, field: str) -> str:
    revision = _require_string(value, field)
    if not COMMIT_PATTERN.fullmatch(revision):
        raise ManifestError(f"{field} must be a full lowercase 40-character Git commit")
    return revision


def _require_sha256(value: Any, field: str) -> str:
    digest = _require_string(value, field)
    if not SHA256_PATTERN.fullmatch(digest):
        raise ManifestError(f"{field} must be a lowercase SHA-256")
    return digest


def _require_https(value: Any, field: str) -> str:
    url = _require_string(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManifestError(f"{field} must be an HTTPS URL")
    return url


def _require_safe_relative_path(value: Any, field: str) -> PurePosixPath:
    raw = _require_string(value, field)
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or raw != path.as_posix():
        raise ManifestError(f"{field} must be a normalized repository-relative path")
    return path


def _require_exact_keys(value: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ManifestError(f"{field} keys mismatch; missing={missing}, extra={extra}")


def validate_manifest(manifest: dict[str, Any]) -> None:
    _require_exact_keys(
        manifest,
        {
            "schemaVersion",
            "modelId",
            "modelRevision",
            "checkpoint",
            "sourceCode",
            "modelLicense",
            "components",
            "artifactRoot",
        },
        "manifest",
    )
    if manifest["schemaVersion"] != 1:
        raise ManifestError("schemaVersion must equal 1")
    if manifest["modelId"] != EXPECTED_MODEL_ID:
        raise ManifestError(f"modelId must equal {EXPECTED_MODEL_ID}")

    model_revision = _require_commit(manifest["modelRevision"], "modelRevision")
    artifact_root = _require_safe_relative_path(manifest["artifactRoot"], "artifactRoot")
    if artifact_root != EXPECTED_ARTIFACT_ROOT:
        raise ManifestError(f"artifactRoot must equal {EXPECTED_ARTIFACT_ROOT}")

    checkpoint = _require_object(manifest["checkpoint"], "checkpoint")
    _require_exact_keys(checkpoint, {"path", "url", "sha256"}, "checkpoint")
    checkpoint_path = _require_safe_relative_path(checkpoint["path"], "checkpoint.path")
    if checkpoint_path.parts[: len(artifact_root.parts)] != artifact_root.parts:
        raise ManifestError("checkpoint.path must remain under artifactRoot")
    checkpoint_url = _require_https(checkpoint["url"], "checkpoint.url")
    if f"/resolve/{model_revision}/" not in checkpoint_url:
        raise ManifestError("checkpoint.url must contain the exact modelRevision")
    if not checkpoint_url.endswith("/clip_cn_rn50.pt"):
        raise ManifestError("checkpoint.url must identify clip_cn_rn50.pt")
    _require_sha256(checkpoint["sha256"], "checkpoint.sha256")

    source_code = _require_object(manifest["sourceCode"], "sourceCode")
    _require_exact_keys(
        source_code,
        {"repository", "revision", "license", "licensePath", "licenseSha256"},
        "sourceCode",
    )
    repository = _require_https(source_code["repository"], "sourceCode.repository")
    if repository.rstrip("/") != "https://github.com/OFA-Sys/Chinese-CLIP":
        raise ManifestError("sourceCode.repository must be the official Chinese-CLIP repository")
    _require_commit(source_code["revision"], "sourceCode.revision")
    if source_code["license"] != "MIT":
        raise ManifestError("sourceCode.license must equal MIT")
    _require_safe_relative_path(source_code["licensePath"], "sourceCode.licensePath")
    _require_sha256(source_code["licenseSha256"], "sourceCode.licenseSha256")

    model_license = _require_object(manifest["modelLicense"], "modelLicense")
    _require_exact_keys(
        model_license,
        {"spdx", "declarationUrl", "licensePath", "licenseSha256"},
        "modelLicense",
    )
    if model_license["spdx"] != "Apache-2.0":
        raise ManifestError("modelLicense.spdx must equal Apache-2.0")
    declaration_url = _require_https(model_license["declarationUrl"], "modelLicense.declarationUrl")
    if model_revision not in declaration_url:
        raise ManifestError("modelLicense.declarationUrl must contain the exact modelRevision")
    _require_safe_relative_path(model_license["licensePath"], "modelLicense.licensePath")
    _require_sha256(model_license["licenseSha256"], "modelLicense.licenseSha256")

    components = _require_object(manifest["components"], "components")
    if components != EXPECTED_COMPONENTS:
        raise ManifestError("only the image encoder may ship; text encoder and tokenizer are build-time only")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ManifestError(f"cannot read artifact {path}: {error}") from error
    return digest.hexdigest()


def _resolve_repository_path(root: Path, value: Any, field: str) -> Path:
    relative = _require_safe_relative_path(value, field)
    root = root.resolve()
    resolved = (root / Path(relative.as_posix())).resolve()
    if resolved != root and root not in resolved.parents:
        raise ManifestError(f"{field} escapes repository root")
    return resolved


def verify_files(manifest: dict[str, Any], root: Path) -> None:
    validate_manifest(manifest)
    checks = (
        (
            "checkpoint",
            manifest["checkpoint"]["path"],
            manifest["checkpoint"]["sha256"],
        ),
        (
            "source code license",
            manifest["sourceCode"]["licensePath"],
            manifest["sourceCode"]["licenseSha256"],
        ),
        (
            "model license",
            manifest["modelLicense"]["licensePath"],
            manifest["modelLicense"]["licenseSha256"],
        ),
    )
    for label, relative_path, expected_digest in checks:
        path = _resolve_repository_path(root, relative_path, f"{label}.path")
        actual_digest = _sha256(path)
        if actual_digest != expected_digest:
            raise ManifestError(
                f"{label} SHA-256 mismatch: expected {expected_digest}, got {actual_digest}"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Local Health Kernel module root (defaults to the script parent module)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = Path.cwd() / manifest_path
    manifest = load_manifest(manifest_path)
    validate_manifest(manifest)
    if args.verify_files:
        verify_files(manifest, args.root)
    summary = {
        "artifactRoot": manifest["artifactRoot"],
        "filesVerified": bool(args.verify_files),
        "modelId": manifest["modelId"],
        "modelRevision": manifest["modelRevision"],
        "sourceRevision": manifest["sourceCode"]["revision"],
    }
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as error:
        raise SystemExit(f"manifest verification failed: {error}") from error
