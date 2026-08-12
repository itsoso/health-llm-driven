from __future__ import annotations

import json
import os
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
    ((OTA, ("production", "test")), (ROLLBACK, ("production",))),
)
def test_ota_commands_require_an_exact_eas_cli_version(
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

    assert result.returncode == 2
    assert "exact" in (result.stdout + result.stderr).lower() or "精确" in (
        result.stdout + result.stderr
    )
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


def _write_private_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def _artifact(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _verify("artifact", "--input-dir", str(root), "--platform", "ios", *args)


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


def _fake_eas_runner(tmp_path: Path) -> Path:
    runner = tmp_path / "fake-eas"
    runner.write_text(
        """#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["OTA_TEST_CALLS"])
calls = json.loads(log.read_text()) if log.exists() else []
calls.append(args)
log.write_text(json.dumps(calls))
mode = os.environ.get("OTA_TEST_MODE", "transient")
state = Path(os.environ["OTA_TEST_STATE"])
group = "11111111-1111-4111-8111-111111111111"
update = "22222222-2222-4222-8222-222222222222"
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
runtime = json.loads(Path("app.json").read_text())["expo"]["version"]

def value(flag):
    return args[args.index(flag) + 1]

def write_export(path):
    root = Path(path)
    (root / "bundles").mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "bundles/ios-entry.js").write_bytes(b"bundle")
    (root / "assets/image.png").write_bytes(b"asset")
    (root / "metadata.json").write_text(json.dumps({
        "version": 0,
        "bundler": "metro",
        "fileMetadata": {"ios": {
            "bundle": "bundles/ios-entry.js",
            "assets": [{"path": "assets/image.png", "ext": "png"}],
        }},
    }))

if args[0] == "--version":
    print("eas-cli/21.8.0")
elif args[0] == "update":
    attempts = sum(1 for call in calls if call and call[0] == "update")
    input_dir = value("--input-dir")
    message = value("--message")
    payload = [{
        "id": update,
        "group": group,
        "branch": "production",
        "message": message,
        "runtimeVersion": runtime,
        "platform": "ios",
        "gitCommitHash": head,
    }]
    if attempts == 1:
        write_export(input_dir)
        if mode == "ambiguous-network":
            print("ECONNRESET while waiting for publish response", file=sys.stderr)
            raise SystemExit(1)
        if mode in {"first-ambiguous", "eventual-first"}:
            state.write_text(json.dumps(payload))
            print("Asset processing timed out after upload", file=sys.stderr)
            raise SystemExit(1)
        if mode in {"transient", "mutate", "second-ambiguous"}:
            print("Asset processing timed out", file=sys.stderr)
            raise SystemExit(1)
    state.write_text(json.dumps(payload))
    if mode == "second-ambiguous":
        print("Asset processing timed out after upload", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(payload))
elif args[0] == "update:list":
    page = json.loads(state.read_text()) if state.exists() else []
    list_attempts = sum(1 for call in calls if call and call[0] == "update:list")
    print(json.dumps({
        "currentPage": []
        if mode == "ambiguous-network"
        or (mode == "eventual-first" and list_attempts < 2)
        else page
    }))
elif args[0] == "update:view":
    payload = json.loads(state.read_text())
    if mode == "view-mismatch":
        payload[0]["id"] = "99999999-9999-4999-8999-999999999999"
    print(json.dumps(payload))
elif args[0] == "channel:view":
    payload = json.loads(state.read_text())[0]
    print(json.dumps({"currentPage": {
        "name": "production",
        "isPaused": False,
        "updateBranches": [{
            "name": "production",
            "updateGroups": [{"id": payload["group"], "group": payload["group"]}],
        }],
    }}))
else:
    raise SystemExit("unexpected command: " + repr(args))
""",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def _run_ota(
    tmp_path: Path,
    mode: str,
    *,
    existing_manifest: str | None = None,
    audit_log: Path | None = None,
    preexisting_updates: list[dict[str, object]] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    runner = _fake_eas_runner(tmp_path)
    manifest = tmp_path / "manifest.json"
    if existing_manifest is not None:
        manifest.write_text(existing_manifest, encoding="utf-8")
        manifest.chmod(0o600)
    anchor = tmp_path / "anchor"
    calls = tmp_path / "calls.json"
    if preexisting_updates is not None:
        (tmp_path / "state.json").write_text(json.dumps(preexisting_updates))
    env = os.environ.copy()
    env.update(
        {
            "OTA_ALLOW_DIRTY": "1",
            "OTA_EAS_RUNNER": str(runner),
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_ANCHOR_FILE": str(anchor),
            "OTA_TEST_CALLS": str(calls),
            "OTA_TEST_STATE": str(tmp_path / "state.json"),
            "OTA_TEST_MODE": mode,
            "OTA_TRANSACTION_ID": TRANSACTION_ID,
            "OTA_AUDIT_LOG": str(audit_log or (tmp_path / "ota-audit.jsonl")),
            "OTA_RETRY_DELAY_SECONDS": "0.3" if mode == "mutate" else "0",
            "OTA_LOOKUP_ATTEMPTS": "3",
            "OTA_LOOKUP_DELAY_SECONDS": "0",
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
        }
    )
    if mode == "mutate":
        mutator = tmp_path / "mutate-artifact"
        mutator.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib,sys\n"
            "(pathlib.Path(sys.argv[1]) / 'bundles/ios-entry.js').write_bytes(b'mutated')\n",
            encoding="utf-8",
        )
        mutator.chmod(0o755)
        env["OTA_TEST_AFTER_ARTIFACT_VERIFIED"] = str(mutator)
    result = subprocess.run(
        [str(OTA), "production", "transaction test"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, calls, manifest, anchor


def test_ota_exports_once_and_retries_same_verified_directory(tmp_path: Path) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "transient")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(calls_path.read_text())
    updates = [call for call in calls if call[0] == "update"]
    assert len(updates) == 2
    assert "--skip-bundler" not in updates[0]
    assert "--skip-bundler" in updates[1]
    assert updates[0][updates[0].index("--input-dir") + 1] == updates[1][
        updates[1].index("--input-dir") + 1
    ]
    assert "--emit-metadata" not in updates[0]
    assert any(call[0] == "update:list" for call in calls)
    assert any(call[0] == "update:view" for call in calls)
    assert any(call[0] == "channel:view" for call in calls)
    payload = json.loads(manifest.read_text())
    assert payload["schema_version"] == 2
    assert payload["transaction_id"] == TRANSACTION_ID
    assert len(payload["artifact_digest"]) == 64
    assert len(payload["source_tree"]) == 40
    assert payload["active_group_id"] == GROUP_ID
    assert payload["active_update_id"] == UPDATE_ID
    assert anchor.read_text().strip() == payload["commit_sha"]


def test_ota_cross_invocation_retry_adopts_postcommit_publish_without_republishing(
    tmp_path: Path,
) -> None:
    audit_log = tmp_path / "ota-audit.jsonl"
    audit_log.mkdir()

    first, calls_path, manifest, anchor = _run_ota(
        tmp_path,
        "success",
        audit_log=audit_log,
    )

    assert first.returncode != 0
    assert manifest.exists()
    assert anchor.exists()
    first_manifest = json.loads(manifest.read_text())
    assert len(
        [call for call in json.loads(calls_path.read_text()) if call[0] == "update"]
    ) == 1

    audit_log.rmdir()
    second, calls_path, retried_manifest, retried_anchor = _run_ota(
        tmp_path,
        "success",
        audit_log=audit_log,
    )

    assert second.returncode == 0, second.stdout + second.stderr
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 1
    assert len([call for call in calls if call[0] == "update:list"]) >= 1
    retried_payload = json.loads(retried_manifest.read_text())
    assert retried_payload["transaction_id"] == TRANSACTION_ID
    assert retried_payload["artifact_digest"] == first_manifest["artifact_digest"]
    assert retried_payload["published_at"] == first_manifest["published_at"]
    assert retried_anchor.exists()
    audit_events = [
        json.loads(line) for line in audit_log.read_text().splitlines() if line.strip()
    ]
    assert audit_events[-1]["result"] == "published"
    assert audit_events[-1]["transaction_id"] == TRANSACTION_ID


def _preexisting_transaction_update(
    *,
    group_id: str = GROUP_ID,
    update_id: str = UPDATE_ID,
) -> dict[str, object]:
    return {
        "id": update_id,
        "group": group_id,
        "branch": "production",
        "message": f"[tx:{TRANSACTION_ID}] transaction test",
        "runtimeVersion": "1.3.3",
        "platform": "ios",
        "gitCommitHash": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }


def test_ota_preflight_adopts_one_remote_transaction_and_rebuilds_local_receipt(
    tmp_path: Path,
) -> None:
    result, calls_path, manifest, anchor = _run_ota(
        tmp_path,
        "preexisting",
        preexisting_updates=[_preexisting_transaction_update()],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(calls_path.read_text())
    assert not [call for call in calls if call[0] == "update"]
    assert any(call[0] == "update:list" for call in calls)
    assert any(call[0] == "update:view" for call in calls)
    assert any(call[0] == "channel:view" for call in calls)
    payload = json.loads(manifest.read_text())
    assert payload["transaction_id"] == TRANSACTION_ID
    assert payload["active_group_id"] == GROUP_ID
    assert payload["active_update_id"] == UPDATE_ID
    assert payload["artifact_digest"] is None
    assert payload["artifact_evidence"] == "unavailable_after_remote_adoption"
    assert anchor.exists()
    assert manifest.stat().st_mode & 0o777 == 0o600


def test_ota_preflight_fails_closed_on_multiple_remote_transaction_groups(
    tmp_path: Path,
) -> None:
    result, calls_path, manifest, anchor = _run_ota(
        tmp_path,
        "preexisting",
        preexisting_updates=[
            _preexisting_transaction_update(),
            _preexisting_transaction_update(
                group_id="33333333-3333-4333-8333-333333333333",
                update_id="44444444-4444-4444-8444-444444444444",
            ),
        ],
    )

    assert result.returncode != 0
    calls = json.loads(calls_path.read_text())
    assert not [call for call in calls if call[0] == "update"]
    assert "ambiguous" in (result.stdout + result.stderr).lower()
    assert not manifest.exists()
    assert not anchor.exists()


def test_ota_preflight_refuses_same_transaction_manifest_identity_conflict(
    tmp_path: Path,
) -> None:
    original = {
        "schema_version": 2,
        "status": "published",
        "transaction_id": TRANSACTION_ID,
        "group_id": GROUP_ID,
        "update_id": UPDATE_ID,
        "active_group_id": GROUP_ID,
        "active_update_id": UPDATE_ID,
    }
    result, calls_path, manifest, anchor = _run_ota(
        tmp_path,
        "preexisting",
        existing_manifest=json.dumps(original),
        preexisting_updates=[
            _preexisting_transaction_update(
                group_id="33333333-3333-4333-8333-333333333333",
                update_id="44444444-4444-4444-8444-444444444444",
            )
        ],
    )

    assert result.returncode != 0
    calls = json.loads(calls_path.read_text())
    assert not [call for call in calls if call[0] == "update"]
    assert "conflict" in (result.stdout + result.stderr).lower()
    assert json.loads(manifest.read_text()) == original
    assert not anchor.exists()


def test_ota_resolves_a_lost_second_publish_response_without_a_third_publish(
    tmp_path: Path,
) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "second-ambiguous")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 2
    assert len([call for call in calls if call[0] == "update:list"]) == 5
    assert json.loads(manifest.read_text())["active_group_id"] == GROUP_ID
    assert anchor.exists()


def test_ota_adopts_a_unique_first_publish_when_the_response_is_lost(
    tmp_path: Path,
) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "first-ambiguous")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 1
    assert len([call for call in calls if call[0] == "update:list"]) == 2
    assert json.loads(manifest.read_text())["active_group_id"] == GROUP_ID
    assert anchor.exists()


def test_ota_polls_until_a_first_publish_becomes_visible(tmp_path: Path) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "eventual-first")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 1
    assert len([call for call in calls if call[0] == "update:list"]) == 2
    assert json.loads(manifest.read_text())["active_group_id"] == GROUP_ID
    assert anchor.exists()


def test_ota_does_not_republish_an_unresolved_ambiguous_network_failure(
    tmp_path: Path,
) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "ambiguous-network")

    assert result.returncode != 0
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 1
    assert len([call for call in calls if call[0] == "update:list"]) == 4
    assert "ambiguous" in (result.stdout + result.stderr).lower()
    assert not manifest.exists()
    assert not anchor.exists()


def test_ota_refuses_artifact_mutation_before_retry(tmp_path: Path) -> None:
    result, calls_path, manifest, anchor = _run_ota(tmp_path, "mutate")

    assert result.returncode != 0
    calls = json.loads(calls_path.read_text())
    assert len([call for call in calls if call[0] == "update"]) == 1
    assert "digest" in (result.stdout + result.stderr).lower()
    assert not manifest.exists()
    assert not anchor.exists()


def test_ota_refuses_structured_view_mismatch_before_manifest(tmp_path: Path) -> None:
    result, _calls, manifest, anchor = _run_ota(tmp_path, "view-mismatch")

    assert result.returncode != 0
    assert "mismatch" in (result.stdout + result.stderr).lower()
    assert not manifest.exists()
    assert not anchor.exists()


def test_ota_refuses_corrupt_existing_manifest_before_eas(tmp_path: Path) -> None:
    result, calls, manifest, anchor = _run_ota(
        tmp_path,
        "transient",
        existing_manifest="{corrupt",
    )

    assert result.returncode != 0
    assert "manifest" in (result.stdout + result.stderr).lower()
    assert not calls.exists()
    assert manifest.read_text() == "{corrupt"
    assert not anchor.exists()


def test_ota_refuses_incomplete_legacy_manifest_pair_before_eas(tmp_path: Path) -> None:
    result, calls, manifest, anchor = _run_ota(
        tmp_path,
        "transient",
        existing_manifest=json.dumps(
            {"schema_version": 1, "group_id": GROUP_ID, "update_id": None}
        ),
    )

    assert result.returncode != 0
    assert "manifest" in (result.stdout + result.stderr).lower()
    assert not calls.exists()
    assert json.loads(manifest.read_text())["group_id"] == GROUP_ID
    assert not anchor.exists()


def _fake_rollback_runner(tmp_path: Path) -> Path:
    runner = tmp_path / "fake-rollback-eas"
    runner.write_text(
        f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
calls_path = os.environ.get("OTA_ROLLBACK_TEST_CALLS")
if calls_path:
    calls = json.loads(open(calls_path).read()) if os.path.exists(calls_path) else []
    calls.append(args)
    open(calls_path, "w").write(json.dumps(calls))
source = [{{
  "id": "{UPDATE_ID}",
  "group": "{GROUP_ID}",
  "branch": "production",
  "message": "known good",
  "runtimeVersion": "1.3.3",
  "platform": "ios",
  "gitCommitHash": "0000000000000000000000000000000000000000"
}}]
new = [{{
  "id": "{ROLLBACK_UPDATE_ID}",
  "group": "{ROLLBACK_GROUP_ID}",
  "branch": {{"name": "production"}},
  "message": "[tx:" + os.environ["OTA_ROLLBACK_TRANSACTION_ID"] + "] rollback",
  "runtimeVersion": "1.3.3",
  "platform": "ios",
  "gitCommitHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}}]
if args[0] == "update:republish":
    if os.environ.get("OTA_ROLLBACK_TEST_AMBIGUOUS") == "1":
        print("ECONNRESET after republish", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(new))
elif args[0] == "update:list":
    print(json.dumps({{"currentPage": [{{
      "group": "{ROLLBACK_GROUP_ID}",
      "branch": "production",
      "message": new[0]["message"],
      "runtimeVersion": "1.3.3"
    }}]}}))
elif args[0] == "update:view":
    if args[1] == "{GROUP_ID}":
        if os.environ.get("OTA_ROLLBACK_TEST_SOURCE_MISMATCH") == "1":
            source[0]["id"] = "99999999-9999-4999-8999-999999999999"
        print(json.dumps(source))
    else:
        print(json.dumps(new))
elif args[0] == "channel:view":
    print(json.dumps({{"currentPage": {{
      "name": "production",
      "isPaused": False,
      "updateBranches": [{{"name": "production", "updateGroups": [{{
        "id": "{ROLLBACK_GROUP_ID}", "group": "{ROLLBACK_GROUP_ID}"
      }}]}}]
    }}}}))
else:
    raise SystemExit("unexpected command")
""",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def test_rollback_records_new_republish_ids_and_separate_source_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
                "schema_version": 2,
                "status": "published",
                "platform": "ios",
                "channel": "production",
                "environment": "production",
                "runtime_version": "1.3.3",
                "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "previous_known_good_group_id": GROUP_ID,
                "previous_known_good_update_id": UPDATE_ID,
                "transaction_id": "old-bad-transaction",
                "commit_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "source_tree": "cccccccccccccccccccccccccccccccccccccccc",
                "artifact_digest": "d" * 64,
                "artifact_file_count": 4,
                "artifact_total_bytes": 999,
                "published_at": "2026-08-01T00:00:00+00:00",
        },
    )
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_EAS_RUNNER": str(_fake_rollback_runner(tmp_path)),
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
            "OTA_ROLLBACK_TEST_CALLS": str(tmp_path / "rollback-calls.json"),
        }
    )

    result = subprocess.run(
        [str(ROLLBACK), "production", "--confirm"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(manifest.read_text())
    calls = json.loads((tmp_path / "rollback-calls.json").read_text())
    assert calls[0][:2] == ["update:view", GROUP_ID]
    assert calls[1][0] == "update:republish"
    assert "--message" in calls[1]
    assert calls[1][calls[1].index("--message") + 1].startswith("[tx:rollback-")
    assert payload["schema_version"] == 2
    assert payload["status"] == "rolled_back"
    assert payload["rollback_source_group_id"] == GROUP_ID
    assert payload["rollback_source_update_id"] == UPDATE_ID
    assert payload["rollback_transaction_id"].startswith("rollback-")
    assert payload["active_group_id"] == ROLLBACK_GROUP_ID
    assert payload["active_update_id"] == ROLLBACK_UPDATE_ID
    assert payload["rollback_from_group_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert payload["rollback_from_update_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assert payload["previous_known_good_group_id"] == GROUP_ID
    assert payload["previous_known_good_update_id"] == UPDATE_ID
    assert payload["commit_sha"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert "source_tree" not in payload
    assert "artifact_digest" not in payload
    assert "transaction_id" not in payload
    assert "published_at" not in payload
    assert payload["rollback_from_evidence"]["transaction_id"] == (
        "old-bad-transaction"
    )


def test_rollback_rejects_a_partial_explicit_source_pair(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
                "schema_version": 1,
                "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "previous_known_good_group_id": GROUP_ID,
                "previous_known_good_update_id": UPDATE_ID,
        },
    )
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_ROLLBACK_GROUP_ID": GROUP_ID,
            "OTA_ROLLBACK_UPDATE_ID": "",
        }
    )

    result = subprocess.run(
        [str(ROLLBACK), "production"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "pair" in (result.stdout + result.stderr).lower() or "成对" in (
        result.stdout + result.stderr
    )


def test_rollback_rejects_source_pair_mismatch_before_republish(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    original = {
        "schema_version": 2,
        "status": "published",
        "runtime_version": "1.3.3",
        "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "previous_known_good_group_id": GROUP_ID,
        "previous_known_good_update_id": UPDATE_ID,
    }
    _write_private_manifest(manifest, original)
    calls = tmp_path / "rollback-calls.json"
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_EAS_RUNNER": str(_fake_rollback_runner(tmp_path)),
            "OTA_ROLLBACK_TEST_CALLS": str(calls),
            "OTA_ROLLBACK_TEST_SOURCE_MISMATCH": "1",
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
        }
    )

    result = subprocess.run(
        [str(ROLLBACK), "production", "--confirm"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "source" in (result.stdout + result.stderr).lower()
    assert all(call[0] != "update:republish" for call in json.loads(calls.read_text()))
    assert json.loads(manifest.read_text()) == original


def test_rollback_adopts_a_unique_republish_when_response_is_lost(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_private_manifest(
        manifest,
        {
                "schema_version": 2,
                "runtime_version": "1.3.3",
                "group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "previous_known_good_group_id": GROUP_ID,
                "previous_known_good_update_id": UPDATE_ID,
        },
    )
    calls = tmp_path / "rollback-calls.json"
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_EAS_RUNNER": str(_fake_rollback_runner(tmp_path)),
            "OTA_ROLLBACK_TEST_CALLS": str(calls),
            "OTA_ROLLBACK_TEST_AMBIGUOUS": "1",
            "OTA_LOOKUP_DELAY_SECONDS": "0",
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
        }
    )

    result = subprocess.run(
        [str(ROLLBACK), "production", "--confirm"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    logged = json.loads(calls.read_text())
    assert len([call for call in logged if call[0] == "update:republish"]) == 1
    assert len([call for call in logged if call[0] == "update:list"]) == 1
    assert json.loads(manifest.read_text())["active_group_id"] == ROLLBACK_GROUP_ID


def test_rollback_refuses_an_incomplete_active_pair_before_eas(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    original = {
        "schema_version": 2,
        "runtime_version": "1.3.3",
        "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "active_update_id": None,
        "previous_known_good_group_id": GROUP_ID,
        "previous_known_good_update_id": UPDATE_ID,
    }
    _write_private_manifest(manifest, original)
    calls = tmp_path / "rollback-calls.json"
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_EAS_RUNNER": str(_fake_rollback_runner(tmp_path)),
            "OTA_ROLLBACK_TEST_CALLS": str(calls),
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
        }
    )

    result = subprocess.run(
        [str(ROLLBACK), "production", "--confirm"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest" in (result.stdout + result.stderr).lower()
    assert not calls.exists()
    assert json.loads(manifest.read_text()) == original


def test_explicit_rollback_pair_can_create_a_missing_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    env = os.environ.copy()
    env.update(
        {
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_EAS_RUNNER": str(_fake_rollback_runner(tmp_path)),
            "OTA_ROLLBACK_RUNTIME_VERSION": "1.3.3",
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
        }
    )

    result = subprocess.run(
        [
            str(ROLLBACK),
            "production",
            "--group",
            GROUP_ID,
            "--update-id",
            UPDATE_ID,
            "--confirm",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(manifest.read_text())
    assert payload["active_group_id"] == ROLLBACK_GROUP_ID
    assert payload["active_update_id"] == ROLLBACK_UPDATE_ID
    assert payload["platform"] == "ios"
    assert payload["runtime_version"] == "1.3.3"
    assert payload["rollback_source_verification"] == {
        "group_update_runtime": True,
        "update_view": True,
    }
