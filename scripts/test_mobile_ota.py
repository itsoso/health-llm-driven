from __future__ import annotations

import json
import os
import importlib.util
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_mobile_ota_artifact.py"
OTA = ROOT / "scripts" / "mobile-ota.sh"
ROLLBACK = ROOT / "scripts" / "mobile-ota-rollback.sh"

GROUP_ID = "11111111-1111-4111-8111-111111111111"
UPDATE_ID = "22222222-2222-4222-8222-222222222222"
ROLLBACK_GROUP_ID = "33333333-3333-4333-8333-333333333333"
ROLLBACK_UPDATE_ID = "44444444-4444-4444-8444-444444444444"
TRANSACTION_ID = "tx-test-1234"


@pytest.mark.parametrize(
    ("script", "args"),
    (
        (OTA, ("production", "test")),
        (OTA, ("rokid-production", "test")),
        (OTA, ("watch-production", "test")),
        (ROLLBACK, ("production", "--confirm")),
        (ROLLBACK, ("rokid-production", "--confirm")),
    ),
)
def test_production_ota_writers_are_frozen_even_with_a_caller_runner_override(
    script: Path,
    args: tuple[str, ...],
    tmp_path: Path,
) -> None:
    marker = tmp_path / "runner-invoked"
    fake_runner = tmp_path / "fake-eas"
    fake_runner.write_text(
        f"#!/bin/sh\nprintf invoked > {marker}\n",
        encoding="utf-8",
    )
    fake_runner.chmod(0o700)

    completed = subprocess.run(
        [str(script), *args],
        cwd=ROOT,
        env={**os.environ, "OTA_EAS_RUNNER": str(fake_runner)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "已冻结" in completed.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    ("script", "args"),
    (
        (OTA, ("production",)),
        (OTA, ("rokid-production",)),
        (ROLLBACK, ("production", "--confirm")),
        (ROLLBACK, ("rokid-production", "--confirm")),
    ),
)
def test_production_channel_family_freezes_before_git_paths_lock_or_state(
    script: Path,
    args: tuple[str, ...],
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ambient-command-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("git", "python3", "dirname"):
        executable = fake_bin / command
        executable.write_text(
            f"#!/bin/sh\nprintf invoked > {marker}\nexit 91\n",
            encoding="utf-8",
        )
        executable.chmod(0o700)

    state_path = tmp_path / "must-not-exist"
    completed = subprocess.run(
        [str(script), *args],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "REVA_RELEASE_LOCK_DIR": str(state_path / "lock"),
            "OTA_MANIFEST_FILE": str(state_path / "manifest.json"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "冻结" in completed.stderr
    assert not marker.exists()
    assert not state_path.exists()


@pytest.mark.parametrize(
    "channel",
    (
        "development",
        "preview",
        "rokid-preview",
        "production",
        "live",
        "prod",
        "foo",
        "watch-preview",
    ),
)
@pytest.mark.parametrize("script", (OTA, ROLLBACK))
def test_all_ota_channels_freeze_before_path_state_lock_or_runner(
    script: Path,
    channel: str,
    tmp_path: Path,
) -> None:
    external_marker = tmp_path / "ambient-command-invoked"
    runner_marker = tmp_path / "runner-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("git", "python3", "dirname"):
        executable = fake_bin / command
        executable.write_text(
            f"#!/bin/sh\nprintf invoked > {external_marker}\nexit 91\n",
            encoding="utf-8",
        )
        executable.chmod(0o700)
    fake_runner = tmp_path / "fake-eas"
    fake_runner.write_text(
        f"#!/bin/sh\nprintf invoked > {runner_marker}\nexit 92\n",
        encoding="utf-8",
    )
    fake_runner.chmod(0o700)
    state_path = tmp_path / "must-not-exist"
    arguments = (channel, "test") if script == OTA else (channel, "--confirm")

    result = subprocess.run(
        [str(script), *arguments],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "OTA_EAS_RUNNER": str(fake_runner),
            "REVA_RELEASE_LOCK_DIR": str(state_path / "lock"),
            "OTA_MANIFEST_FILE": str(state_path / "manifest.json"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78, result.stdout + result.stderr
    assert "冻结" in result.stderr
    assert not external_marker.exists()
    assert not runner_marker.exists()
    assert not state_path.exists()


@pytest.mark.parametrize(
    ("script", "args"),
    ((OTA, ("preview", "test")), (ROLLBACK, ("preview",))),
)
def test_ota_freeze_precedes_eas_cli_version_validation(
    script: Path,
    args: tuple[str, ...],
) -> None:
    env = os.environ.copy()
    env["OTA_EAS_CLI_VERSION"] = "latest"

    result = subprocess.run(
        [str(script), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "冻结" in result.stderr
    source = script.read_text(encoding="utf-8")
    assert 'EAS_CLI_VERSION="${OTA_EAS_CLI_VERSION:-21.8.0}"' in source
    assert '"eas-cli@${EAS_CLI_VERSION}"' in source


def test_per_channel_release_manifests_are_private_runtime_files() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ".mobile-release-manifest.preview.json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("script", "arguments"),
    (
        (OTA, ("production", "frozen")),
        (ROLLBACK, ("production", "--confirm")),
    ),
)
def test_production_ota_writers_are_frozen_before_any_runner_call(
    tmp_path: Path,
    script: Path,
    arguments: tuple[str, ...],
) -> None:
    marker = tmp_path / "runner-called"
    runner = tmp_path / "fake-eas"
    runner.write_text(
        f"#!/bin/sh\n: > {str(marker)!r}\nexit 0\n",
        encoding="utf-8",
    )
    runner.chmod(0o700)
    completed = subprocess.run(
        [str(script), *arguments],
        cwd=ROOT,
        env={**os.environ, "OTA_EAS_RUNNER": str(runner)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 78
    assert "冻结" in completed.stdout + completed.stderr
    assert not marker.exists()


def _write_export(root: Path, *, platforms: tuple[str, ...] = ("ios",)) -> None:
    root.mkdir(parents=True, exist_ok=True)
    file_metadata: dict[str, object] = {}
    for platform in platforms:
        bundle = f"bundles/{platform}-entry.js"
        asset = f"assets/{platform}-image.png"
        (root / bundle).parent.mkdir(parents=True, exist_ok=True)
        (root / asset).parent.mkdir(parents=True, exist_ok=True)
        (root / bundle).write_bytes(f"{platform}-bundle".encode())
        (root / asset).write_bytes(f"{platform}-asset".encode())
        file_metadata[platform] = {
            "bundle": bundle,
            "assets": [{"path": asset, "ext": "png"}],
        }
    (root / "metadata.json").write_text(
        json.dumps({"version": 0, "bundler": "metro", "fileMetadata": file_metadata}),
        encoding="utf-8",
    )


def _verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _artifact(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _verify("artifact", "--input-dir", str(root), "--platform", "ios", *args)


def _write_private_manifest(path: Path, payload: dict[str, object]) -> None:
    if payload.get("schema_version") == 2:
        payload.setdefault("channel", "production")
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def _load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_mobile_ota_artifact", VERIFY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_git_worktree_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "ota-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "OTA Test"], cwd=repository, check=True
    )
    subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "fixture"], cwd=repository, check=True
    )
    worktree_a = tmp_path / "worktree-a"
    worktree_b = tmp_path / "worktree-b"
    subprocess.run(
        ["git", "worktree", "add", "-qb", "fixture-a", str(worktree_a)],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-qb", "fixture-b", str(worktree_b)],
        cwd=repository,
        check=True,
    )
    return repository, worktree_a, worktree_b


def _published_manifest(
    *, group_id: str = GROUP_ID, update_id: str = UPDATE_ID
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "status": "published",
        "platform": "ios",
        "channel": "production",
        "environment": "production",
        "runtime_version": "1.3.3",
        "group_id": group_id,
        "update_id": update_id,
        "active_group_id": group_id,
        "active_update_id": update_id,
    }


def test_shared_ota_state_migrates_one_valid_legacy_receipt(tmp_path: Path) -> None:
    repository, worktree_a, _worktree_b = _make_git_worktree_pair(tmp_path)
    legacy = repository / ".mobile-release-manifest.json"
    legacy.write_text(json.dumps(_published_manifest()), encoding="utf-8")
    legacy.chmod(0o644)

    result = _verify(
        "state-paths",
        "--repo-root",
        str(worktree_a),
        "--channel",
        "production",
        "--scope",
        "mobile",
        "--migrate",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    shared = Path(payload["manifest_file"])
    assert shared == repository / ".git/reva-release-state/mobile-ota/manifest.production.json"
    assert json.loads(shared.read_text()) == _published_manifest()
    assert stat.S_IMODE(shared.stat().st_mode) == 0o600
    assert not legacy.exists()


def test_shared_ota_state_rejects_conflicting_legacy_receipts(tmp_path: Path) -> None:
    repository, worktree_a, _worktree_b = _make_git_worktree_pair(tmp_path)
    first = repository / ".mobile-release-manifest.json"
    second = worktree_a / ".mobile-release-manifest.json"
    first.write_text(json.dumps(_published_manifest()), encoding="utf-8")
    second.write_text(
        json.dumps(
            _published_manifest(
                group_id="55555555-5555-4555-8555-555555555555",
                update_id="66666666-6666-4666-8666-666666666666",
            )
        ),
        encoding="utf-8",
    )
    first.chmod(0o600)
    second.chmod(0o600)

    result = _verify(
        "state-paths",
        "--repo-root",
        str(worktree_a),
        "--channel",
        "production",
        "--scope",
        "mobile",
        "--migrate",
    )

    assert result.returncode != 0
    assert "conflicting" in result.stderr.lower()
    assert first.exists()
    assert second.exists()
    assert not (
        repository / ".git/reva-release-state/mobile-ota/manifest.production.json"
    ).exists()


def test_shared_ota_state_rejects_nonprivate_state_directory(tmp_path: Path) -> None:
    repository, worktree_a, _worktree_b = _make_git_worktree_pair(tmp_path)
    state_root = repository / ".git/reva-release-state"
    state_root.mkdir(mode=0o755)

    result = _verify(
        "state-paths",
        "--repo-root",
        str(worktree_a),
        "--channel",
        "production",
        "--scope",
        "mobile",
        "--migrate",
    )

    assert result.returncode != 0
    assert "0700" in result.stderr


def test_shared_ota_state_rejects_unsafe_channel_before_any_state_write(
    tmp_path: Path,
) -> None:
    repository, worktree_a, _worktree_b = _make_git_worktree_pair(tmp_path)
    state_root = repository / ".git/reva-release-state"

    result = _verify(
        "state-paths",
        "--repo-root",
        str(worktree_a),
        "--channel",
        "../escape",
        "--scope",
        "mobile",
        "--migrate",
    )

    assert result.returncode != 0
    assert "channel" in result.stderr.lower()
    assert not state_root.exists()



def test_artifact_accepts_one_complete_ios_export_and_digest_is_stable(
    tmp_path: Path,
) -> None:
    export = tmp_path / "export"
    _write_export(export)

    first = _artifact(export)
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(first.stdout)

    for path in export.rglob("*"):
        os.utime(path, (time.time() + 50, time.time() + 50), follow_symlinks=False)
    second = _artifact(export)
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(second.stdout)

    assert first_payload["platform"] == "ios"
    assert first_payload["artifact_digest"] == second_payload["artifact_digest"]
    assert len(first_payload["artifact_digest"]) == 64
    assert first_payload["file_count"] == 3


@pytest.mark.parametrize("bad_path", ["../escape.js", "/tmp/escape.js"])
def test_artifact_rejects_metadata_path_escape(tmp_path: Path, bad_path: str) -> None:
    export = tmp_path / "export"
    _write_export(export)
    metadata = json.loads((export / "metadata.json").read_text())
    metadata["fileMetadata"]["ios"]["bundle"] = bad_path
    (export / "metadata.json").write_text(json.dumps(metadata))

    result = _artifact(export)

    assert result.returncode != 0
    assert "path" in result.stderr.lower()


def test_artifact_rejects_any_symlink(tmp_path: Path) -> None:
    export = tmp_path / "export"
    _write_export(export)
    (export / "untrusted-link").symlink_to(export / "bundles" / "ios-entry.js")

    result = _artifact(export)

    assert result.returncode != 0
    assert "symlink" in result.stderr.lower()


def test_artifact_rejects_empty_files_even_when_unreferenced(tmp_path: Path) -> None:
    export = tmp_path / "export"
    _write_export(export)
    (export / "empty.map").write_bytes(b"")

    result = _artifact(export)

    assert result.returncode != 0
    assert "empty" in result.stderr.lower()


@pytest.mark.parametrize("platforms", [("android",), ("ios", "android")])
def test_artifact_rejects_non_ios_or_mixed_exports(
    tmp_path: Path, platforms: tuple[str, ...]
) -> None:
    export = tmp_path / "export"
    _write_export(export, platforms=platforms)

    result = _artifact(export)

    assert result.returncode != 0
    assert "ios" in result.stderr.lower()


def test_artifact_rejects_stale_and_mutated_bytes(tmp_path: Path) -> None:
    export = tmp_path / "export"
    _write_export(export)
    initial = _artifact(export)
    assert initial.returncode == 0, initial.stderr
    digest = json.loads(initial.stdout)["artifact_digest"]

    stale = _artifact(export, "--not-before-ns", str(time.time_ns() + 1_000_000))
    assert stale.returncode != 0
    assert "stale" in stale.stderr.lower()

    (export / "bundles" / "ios-entry.js").write_bytes(b"mutated")
    mutated = _artifact(export, "--expected-digest", digest)
    assert mutated.returncode != 0
    assert "digest" in mutated.stderr.lower()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "schema_version": 2,
            "group_id": GROUP_ID,
            "update_id": UPDATE_ID,
            "active_group_id": "55555555-5555-4555-8555-555555555555",
            "active_update_id": "66666666-6666-4666-8666-666666666666",
        },
        {
            "schema_version": 1,
            "status": "published",
            "group_id": GROUP_ID,
            "update_id": UPDATE_ID,
            "active_group_id": "55555555-5555-4555-8555-555555555555",
            "active_update_id": "66666666-6666-4666-8666-666666666666",
        },
    ],
)
def test_existing_manifest_requires_one_consistent_active_identity(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = _verify("manifest", "--manifest-file", str(manifest))

    assert result.returncode != 0
    assert "manifest" in result.stderr.lower()


def test_manifest_accepts_a_legacy_rolled_back_identity_shape(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
            "schema_version": 1,
            "status": "rolled_back",
            "group_id": GROUP_ID,
            "update_id": UPDATE_ID,
            "active_group_id": "55555555-5555-4555-8555-555555555555",
            "active_update_id": "66666666-6666-4666-8666-666666666666",
        },
    )

    result = _verify("manifest", "--manifest-file", str(manifest))

    assert result.returncode == 0, result.stderr


def test_manifest_rejects_group_or_world_permissions(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "published",
                "group_id": GROUP_ID,
                "update_id": UPDATE_ID,
                "active_group_id": GROUP_ID,
                "active_update_id": UPDATE_ID,
            }
        ),
        encoding="utf-8",
    )
    manifest.chmod(0o666)

    result = _verify("manifest", "--manifest-file", str(manifest))

    assert result.returncode != 0
    assert "permission" in result.stderr.lower() or "0600" in result.stderr


@pytest.mark.parametrize("unsafe_kind", ["owner_executable", "hardlink"])
def test_manifest_requires_exact_private_single_link(
    tmp_path: Path, unsafe_kind: str
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
            "schema_version": 2,
            "status": "published",
            "group_id": GROUP_ID,
            "update_id": UPDATE_ID,
            "active_group_id": GROUP_ID,
            "active_update_id": UPDATE_ID,
        },
    )
    if unsafe_kind == "owner_executable":
        manifest.chmod(0o700)
    else:
        os.link(manifest, tmp_path / "manifest-hardlink.json")

    result = _verify("manifest", "--manifest-file", str(manifest))

    assert result.returncode != 0
    assert "0600" in result.stderr or "link" in result.stderr.lower()


def test_manifest_rejects_a_symlinked_private_parent(tmp_path: Path) -> None:
    private_parent = tmp_path / "private"
    private_parent.mkdir(mode=0o700)
    manifest = private_parent / "manifest.json"
    _write_private_manifest(manifest, _published_manifest())
    symlinked_parent = tmp_path / "manifest-parent"
    symlinked_parent.symlink_to(private_parent, target_is_directory=True)

    result = _verify(
        "manifest",
        "--manifest-file",
        str(symlinked_parent / manifest.name),
        "--expected-channel",
        "production",
    )

    assert result.returncode != 0
    assert "directory" in result.stderr.lower() or "symlink" in result.stderr.lower()


def test_manifest_rejects_a_symlinked_final_file(tmp_path: Path) -> None:
    target = tmp_path / "manifest-target.json"
    _write_private_manifest(target, _published_manifest())
    manifest = tmp_path / "manifest.json"
    manifest.symlink_to(target)

    result = _verify(
        "manifest",
        "--manifest-file",
        str(manifest),
        "--expected-channel",
        "production",
    )

    assert result.returncode != 0
    assert "manifest" in result.stderr.lower()


def test_manifest_rejects_a_fifo_without_blocking(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    os.mkfifo(manifest, mode=0o600)

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "manifest",
            "--manifest-file",
            str(manifest),
            "--expected-channel",
            "production",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "regular" in result.stderr.lower()


def test_manifest_rejects_a_nonprivate_parent_directory(tmp_path: Path) -> None:
    private_parent = tmp_path / "manifest-parent"
    private_parent.mkdir(mode=0o755)
    manifest = private_parent / "manifest.json"
    _write_private_manifest(manifest, _published_manifest())

    result = _verify(
        "manifest",
        "--manifest-file",
        str(manifest),
        "--expected-channel",
        "production",
    )

    assert result.returncode != 0
    assert "0700" in result.stderr


def test_manifest_rejects_a_non_current_owner_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(manifest, _published_manifest())
    verifier = _load_verify_module()
    current_uid = os.getuid()
    monkeypatch.setattr(verifier.os, "getuid", lambda: current_uid + 1)

    with pytest.raises(verifier.VerificationError, match="owner"):
        verifier.validate_manifest(
            manifest,
            allow_missing=False,
            expected_channel="production",
        )


def test_manifest_rejects_oversized_json_before_parsing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    payload = json.dumps(_published_manifest()).encode("utf-8")
    manifest.write_bytes(payload + b" " * (1024 * 1024))
    manifest.chmod(0o600)

    result = _verify(
        "manifest",
        "--manifest-file",
        str(manifest),
        "--expected-channel",
        "production",
    )

    assert result.returncode != 0
    assert "large" in result.stderr.lower() or "size" in result.stderr.lower()


def test_manifest_rejects_inode_swap_during_single_fd_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(manifest, _published_manifest())
    replacement = tmp_path / "replacement.json"
    _write_private_manifest(
        replacement,
        _published_manifest(
            group_id="55555555-5555-4555-8555-555555555555",
            update_id="66666666-6666-4666-8666-666666666666",
        ),
    )
    verifier = _load_verify_module()
    real_read = verifier.os.read
    swapped = False

    def swap_after_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        data = real_read(descriptor, size)
        if not swapped:
            os.replace(replacement, manifest)
            swapped = True
        return data

    monkeypatch.setattr(verifier.os, "read", swap_after_read)

    with pytest.raises(verifier.VerificationError, match="changed"):
        verifier.validate_manifest(
            manifest,
            allow_missing=False,
            expected_channel="production",
        )


def test_manifest_rejects_parent_mode_drift_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(manifest, _published_manifest())
    verifier = _load_verify_module()
    real_read = verifier.os.read
    changed = False

    def make_parent_public(descriptor: int, size: int) -> bytes:
        nonlocal changed
        data = real_read(descriptor, size)
        if not changed:
            tmp_path.chmod(0o755)
            changed = True
        return data

    monkeypatch.setattr(verifier.os, "read", make_parent_public)
    try:
        with pytest.raises(verifier.VerificationError, match="directory"):
            verifier.validate_manifest(
                manifest,
                allow_missing=False,
                expected_channel="production",
            )
    finally:
        tmp_path.chmod(0o700)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "mode", "swap"])
def test_manifest_writer_rejects_target_drift_after_snapshot(
    tmp_path: Path, unsafe_kind: str
) -> None:
    manifest = tmp_path / "manifest.json"
    original = _published_manifest()
    _write_private_manifest(manifest, original)
    verifier = _load_verify_module()
    snapshot = verifier.validate_manifest(
        manifest,
        allow_missing=False,
        expected_channel="production",
    )
    replacement = tmp_path / "replacement.json"
    _write_private_manifest(
        replacement,
        _published_manifest(
            group_id="55555555-5555-4555-8555-555555555555",
            update_id="66666666-6666-4666-8666-666666666666",
        ),
    )
    if unsafe_kind == "symlink":
        manifest.unlink()
        manifest.symlink_to(replacement)
    elif unsafe_kind == "hardlink":
        os.link(manifest, tmp_path / "manifest-hardlink.json")
    elif unsafe_kind == "mode":
        manifest.chmod(0o644)
    else:
        os.replace(replacement, manifest)

    with pytest.raises(verifier.VerificationError):
        verifier.replace_manifest_from_snapshot(
            manifest,
            snapshot=snapshot,
            payload=_published_manifest(),
            expected_channel="production",
        )

    if not manifest.is_symlink():
        assert json.loads(manifest.read_text(encoding="utf-8")) != original or (
            unsafe_kind in {"hardlink", "mode"}
        )


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "mode"])
def test_private_receipt_writer_rejects_unsafe_existing_anchor(
    tmp_path: Path, unsafe_kind: str
) -> None:
    anchor = tmp_path / "anchor.production"
    anchor.write_text("a" * 40 + "\n", encoding="utf-8")
    anchor.chmod(0o600)
    target = tmp_path / "anchor-target"
    if unsafe_kind == "symlink":
        target.write_text("owner data\n", encoding="utf-8")
        target.chmod(0o600)
        anchor.unlink()
        anchor.symlink_to(target)
    elif unsafe_kind == "hardlink":
        os.link(anchor, tmp_path / "anchor-hardlink")
    else:
        anchor.chmod(0o644)
    verifier = _load_verify_module()

    with pytest.raises(verifier.VerificationError):
        verifier.replace_private_text_receipt(
            anchor,
            "b" * 40 + "\n",
            label="OTA anchor",
        )


def test_legacy_manifest_validation_does_not_follow_a_scratch_symlink(
    tmp_path: Path,
) -> None:
    verifier = _load_verify_module()
    victim = tmp_path / "victim.txt"
    victim.write_text("owner data\n", encoding="utf-8")
    scratch = tmp_path / "scratch.json"
    scratch.symlink_to(victim)

    verifier._validate_receipt_payload(
        "manifest",
        json.dumps(_published_manifest()).encode("utf-8"),
        scratch,
        channel="production",
    )

    assert victim.read_text(encoding="utf-8") == "owner data\n"


@pytest.mark.parametrize("script", [OTA, ROLLBACK])
def test_ota_shells_consume_one_verified_manifest_snapshot(script: Path) -> None:
    source = script.read_text(encoding="utf-8")

    assert "MANIFEST_SNAPSHOT_JSON" in source
    assert "json.loads(manifest_path.read_text" not in source
    assert "manifest_path.read_bytes()" not in source


@pytest.mark.parametrize(
    "artifact_fields",
    [
        {
            "artifact_evidence": "verified_transaction_artifact",
            "artifact_digest": "not-a-sha256",
            "artifact_file_count": 4,
            "artifact_total_bytes": 999,
        },
        {
            "artifact_evidence": "verified_transaction_artifact",
            "artifact_digest": "d" * 64,
            "artifact_file_count": -1,
            "artifact_total_bytes": 999,
        },
        {
            "artifact_evidence": "verified_transaction_artifact",
            "artifact_digest": "d" * 64,
            "artifact_file_count": 4,
            "artifact_total_bytes": "bad",
        },
        {
            "artifact_evidence": "verified_transaction_artifact",
            "artifact_digest": "d" * 64,
            "artifact_file_count": 4,
            "artifact_total_bytes": 0,
        },
        {
            "artifact_evidence": "unavailable_after_remote_adoption",
            "artifact_digest": "d" * 64,
            "artifact_file_count": 4,
            "artifact_total_bytes": 999,
        },
    ],
)
def test_manifest_rejects_invalid_artifact_evidence_semantics(
    tmp_path: Path, artifact_fields: dict[str, object]
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
            "schema_version": 2,
            "status": "published",
            "group_id": GROUP_ID,
            "update_id": UPDATE_ID,
            "active_group_id": GROUP_ID,
            "active_update_id": UPDATE_ID,
            **artifact_fields,
        },
    )

    result = _verify("manifest", "--manifest-file", str(manifest))

    assert result.returncode != 0
    assert "artifact" in result.stderr.lower()


def test_transaction_lookup_requires_one_unique_matching_group(tmp_path: Path) -> None:
    updates = tmp_path / "updates.json"
    item = {
        "branch": "production",
        "group": GROUP_ID,
        "message": f"[tx:{TRANSACTION_ID}] publish",
        "runtimeVersion": "1.3.3",
    }
    updates.write_text(json.dumps({"currentPage": [item]}), encoding="utf-8")

    unique = _verify(
        "find-transaction",
        "--updates-json",
        str(updates),
        "--transaction-id",
        TRANSACTION_ID,
        "--branch",
        "production",
        "--runtime-version",
        "1.3.3",
    )
    assert unique.returncode == 0, unique.stderr
    assert json.loads(unique.stdout) == {"found": True, "group_id": GROUP_ID}

    duplicate = dict(item, group="55555555-5555-4555-8555-555555555555")
    updates.write_text(json.dumps({"currentPage": [item, duplicate]}), encoding="utf-8")
    ambiguous = _verify(
        "find-transaction",
        "--updates-json",
        str(updates),
        "--transaction-id",
        TRANSACTION_ID,
        "--branch",
        "production",
        "--runtime-version",
        "1.3.3",
    )
    assert ambiguous.returncode != 0
    assert "ambiguous" in ambiguous.stderr.lower()

    malformed = dict(item)
    malformed.pop("group")
    updates.write_text(json.dumps({"currentPage": [malformed]}), encoding="utf-8")
    incomplete = _verify(
        "find-transaction",
        "--updates-json",
        str(updates),
        "--transaction-id",
        TRANSACTION_ID,
        "--runtime-version",
        "1.3.3",
    )
    assert incomplete.returncode != 0
    assert "incomplete" in incomplete.stderr.lower()


def test_transaction_lookup_without_branch_is_global_and_fail_closed(
    tmp_path: Path,
) -> None:
    updates = tmp_path / "updates.json"
    first = {
        "branch": "release-production",
        "group": GROUP_ID,
        "message": f"[tx:{TRANSACTION_ID}] publish",
        "runtimeVersion": "1.3.3",
    }
    updates.write_text(json.dumps({"currentPage": [first]}), encoding="utf-8")

    unique = _verify(
        "find-transaction",
        "--updates-json",
        str(updates),
        "--transaction-id",
        TRANSACTION_ID,
        "--runtime-version",
        "1.3.3",
    )
    assert unique.returncode == 0, unique.stderr
    assert json.loads(unique.stdout) == {"found": True, "group_id": GROUP_ID}

    second = dict(
        first,
        branch="another-release-branch",
        group="55555555-5555-4555-8555-555555555555",
    )
    updates.write_text(json.dumps({"currentPage": [first, second]}), encoding="utf-8")
    ambiguous = _verify(
        "find-transaction",
        "--updates-json",
        str(updates),
        "--transaction-id",
        TRANSACTION_ID,
        "--runtime-version",
        "1.3.3",
    )
    assert ambiguous.returncode != 0
    assert "ambiguous" in ambiguous.stderr.lower()


def test_publish_verification_allows_channel_to_map_to_a_different_branch(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish.json"
    view = tmp_path / "view.json"
    channel = tmp_path / "channel.json"
    update = {
        "id": UPDATE_ID,
        "group": GROUP_ID,
        "branch": "release-production",
        "runtimeVersion": "1.3.3",
        "platform": "ios",
    }
    publish.write_text(json.dumps([update]), encoding="utf-8")
    view.write_text(json.dumps([update]), encoding="utf-8")
    channel.write_text(
        json.dumps(
            {
                "currentPage": {
                    "name": "production",
                    "isPaused": False,
                    "updateBranches": [
                        {
                            "name": "release-production",
                            "updateGroups": [{"id": GROUP_ID}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = _verify(
        "publish",
        "--publish-json",
        str(publish),
        "--view-json",
        str(view),
        "--channel-json",
        str(channel),
        "--channel",
        "production",
        "--runtime-version",
        "1.3.3",
    )

    assert result.returncode == 0, result.stderr

    channel_payload = json.loads(channel.read_text())
    channel_payload["currentPage"]["isPaused"] = True
    channel.write_text(json.dumps(channel_payload), encoding="utf-8")
    paused = _verify(
        "publish",
        "--publish-json",
        str(publish),
        "--view-json",
        str(view),
        "--channel-json",
        str(channel),
        "--channel",
        "production",
        "--runtime-version",
        "1.3.3",
    )
    assert paused.returncode != 0
    assert "channel" in paused.stderr.lower()


def test_publish_verification_rejects_a_multi_branch_rollout_as_singular_active(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish.json"
    view = tmp_path / "view.json"
    channel = tmp_path / "channel.json"
    update = {
        "id": UPDATE_ID,
        "group": GROUP_ID,
        "branch": "release-production",
        "runtimeVersion": "1.3.3",
        "platform": "ios",
    }
    publish.write_text(json.dumps([update]), encoding="utf-8")
    view.write_text(json.dumps([update]), encoding="utf-8")
    channel.write_text(
        json.dumps(
            {
                "currentPage": {
                    "name": "production",
                    "isPaused": False,
                    "updateBranches": [
                        {
                            "name": "release-production",
                            "updateGroups": [{"id": GROUP_ID}],
                        },
                        {
                            "name": "rollout-control",
                            "updateGroups": [
                                {"id": "77777777-7777-4777-8777-777777777777"}
                            ],
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = _verify(
        "publish",
        "--publish-json",
        str(publish),
        "--view-json",
        str(view),
        "--channel-json",
        str(channel),
        "--channel",
        "production",
        "--runtime-version",
        "1.3.3",
    )

    assert result.returncode != 0
    assert "channel" in result.stderr.lower()


def test_rollback_source_pair_is_verified_within_a_mixed_platform_group(
    tmp_path: Path,
) -> None:
    view = tmp_path / "view.json"
    ios = {
        "id": UPDATE_ID,
        "group": GROUP_ID,
        "branch": "production",
        "runtimeVersion": "1.3.3",
        "platform": "ios",
    }
    android = dict(
        ios,
        id="66666666-6666-4666-8666-666666666666",
        platform="android",
    )
    view.write_text(json.dumps([ios, android]), encoding="utf-8")

    valid = _verify(
        "source",
        "--view-json",
        str(view),
        "--group-id",
        GROUP_ID,
        "--update-id",
        UPDATE_ID,
        "--runtime-version",
        "1.3.3",
    )
    assert valid.returncode == 0, valid.stderr

    mismatch = _verify(
        "source",
        "--view-json",
        str(view),
        "--group-id",
        GROUP_ID,
        "--update-id",
        "99999999-9999-4999-8999-999999999999",
        "--runtime-version",
        "1.3.3",
    )
    assert mismatch.returncode != 0
    assert "mismatch" in mismatch.stderr.lower()
