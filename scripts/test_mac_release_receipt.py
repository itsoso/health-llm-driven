from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "apps/mac/scripts/mac_release_publish.py"
RELEASE_DMG = ROOT / "apps/mac/scripts/release-dmg.sh"
PACKAGE_APP = ROOT / "apps/mac/scripts/package-app.sh"
RELEASE_LOCK = ROOT / "scripts/release_lock.py"
MAC_LEGACY_SOURCE = (
    "unset APP_STORE_CONNECT_API_KEY APP_STORE_CONNECT_ISSUER_ID EXPO_TOKEN; "
    f"eval \"$(/usr/bin/sed -n "
    f"'/^# BEGIN UNREACHABLE LEGACY MAC RELEASE IMPLEMENTATION$/,/^# END UNREACHABLE LEGACY MAC RELEASE IMPLEMENTATION$/p' "
    f"{RELEASE_DMG!s} | /usr/bin/sed "
    f"-e 's|${{BASH_SOURCE\\[0\\]}}|{RELEASE_DMG!s}|g' "
    "-e 's|^acquire_release_lock \"mac-dmg-release\"$|: # isolated fixture bypasses external guardian|')\""
)

SOURCE_SHA = "1" * 40
SOURCE_TREE = "2" * 40
NOTARY_ID = "11111111-1111-4111-8111-111111111111"
PUBLIC_FIELDS = {
    "schema_version",
    "source_sha",
    "source_tree",
    "artifact_sha256",
    "artifact_size",
    "bundle_id",
    "version",
    "build",
    "architectures",
    "min_os",
    "artifact_url",
    "published_at",
}


def _publisher_test_runner(helper_path: Path = PUBLISHER) -> list[str]:
    """Return an import-only runner for the isolated non-production protocol."""

    return [
        sys.executable,
        "-c",
        (
            "import importlib.util,sys;"
            "path=sys.argv.pop(1);"
            "spec=importlib.util.spec_from_file_location('reva_mac_publish_test',path);"
            "module=importlib.util.module_from_spec(spec);"
            "sys.modules[spec.name]=module;"
            "spec.loader.exec_module(module);"
            "raise SystemExit(module.main())"
        ),
        str(helper_path),
    ]


def _load_publisher_module():
    name = "reva_mac_publish_direct_boundary_test"
    spec = importlib.util.spec_from_file_location(name, PUBLISHER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _direct_writer_argv(command: str, root: Path) -> list[str]:
    token = "mac-1111111111111111-11111111-1111-4111-8111-111111111111"
    digest = "3" * 64
    shared = [
        "--allow-non-root-for-tests",
    ]
    if command == "publish":
        return [
            command,
            "--artifact",
            str(root / "upload.dmg"),
            "--candidate",
            str(root / "candidate.json"),
            "--asset-root",
            str(root / "assets"),
            "--state-root",
            str(root / "state"),
            *shared,
        ]
    if command in {"recover", "rollback", "verify"}:
        return [
            command,
            "--asset-root",
            str(root / "assets"),
            "--state-root",
            str(root / "state"),
            *shared,
        ]
    if command == "create-candidate":
        return [
            command,
            "--output",
            str(root / "candidate.json"),
            "--source-sha",
            SOURCE_SHA,
            "--source-tree",
            SOURCE_TREE,
            "--artifact-sha256",
            digest,
            "--artifact-size",
            "1",
            "--artifact-path",
            str(root / f"assets/mac/releases/{SOURCE_SHA}/{digest}.dmg"),
            "--artifact-url",
            f"https://health.executor.life/mac/releases/{SOURCE_SHA}/{digest}.dmg",
            "--bundle-id",
            "life.executor.health.mac",
            "--version",
            "1.2.3",
            "--build",
            "42",
            "--team-id",
            "QA2U724DAN",
            "--cdhash",
            "4" * 40,
            "--architecture",
            "arm64",
            "--min-os",
            "14.0",
            "--notary-submission-id",
            NOTARY_ID,
            "--notary-status",
            "Accepted",
            "--stapled",
            "--published-at",
            "2026-08-13T00:00:00Z",
            *shared,
        ]
    if command == "handoff-clear":
        return [
            command,
            "--bundle",
            str(root / "reva-mac-release-recovery"),
            "--token",
            token,
            *shared,
        ]
    result = [
        command,
        "--lock-dir",
        str(root / "state/deploy.lock"),
        "--token",
        token,
        "--operation",
        "publish",
        "--stage-kind",
        "publish",
        "--stage",
        str(root / f"assets/mac/.staging/{token}"),
        "--asset-root",
        str(root / "assets"),
        "--state-root",
        str(root / "state"),
        "--source-sha",
        SOURCE_SHA,
        "--source-tree",
        SOURCE_TREE,
        "--helper-sha256",
        "5" * 64,
        "--artifact-sha256",
        digest,
        "--artifact-size",
        "1",
        "--candidate-sha256",
        "6" * 64,
        *shared,
    ]
    if command == "lease-acquire":
        result.extend(("--requested-action", "publish"))
    elif command == "lease-assert":
        result.extend(("--phase", "staging"))
    elif command == "lease-transition":
        result.extend(("--old-phase", "staging", "--new-phase", "sealed"))
    elif command == "lease-release":
        result.extend(("--phase", "staging"))
    return result


def _invoke_direct_writer(module, args):
    if args.command == "publish":
        return module.publish(args)
    if args.command == "recover":
        return module.recover_or_rollback(args, rollback=False)
    if args.command == "rollback":
        return module.recover_or_rollback(args, rollback=True)
    if args.command == "verify":
        return module.verify_release_state(args)
    if args.command == "create-candidate":
        return module.create_candidate(args)
    return {
        "lease-acquire": module.lease_acquire,
        "lease-assert": module.lease_assert,
        "lease-transition": module.lease_transition,
        "lease-release": module.lease_release,
        "stage-reset": module.stage_reset,
        "stage-bind-helper": module.stage_bind_helper,
        "stage-bind-payload": module.stage_bind_payload,
        "stage-cleanup": module.stage_cleanup,
        "handoff-clear": module.handoff_clear,
    }[args.command](args)


@pytest.mark.parametrize(
    "command",
    (
        "publish",
        "recover",
        "rollback",
        "verify",
        "create-candidate",
        "lease-acquire",
        "lease-assert",
        "lease-transition",
        "lease-release",
        "stage-reset",
        "stage-bind-helper",
        "stage-bind-payload",
        "stage-cleanup",
        "handoff-clear",
    ),
)
def test_imported_root_writer_api_fails_before_paths_locks_or_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    module = _load_publisher_module()
    args = module.parser().parse_args(_direct_writer_argv(command, tmp_path))
    touched: list[str] = []

    def forbidden_path(*_args, **_kwargs):
        touched.append("path")
        raise AssertionError("writer reached path handling")

    monkeypatch.setenv("MAC_RELEASE_TEST_MODE", "1")
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "getegid", lambda: 0)
    monkeypatch.setattr(module, "Path", forbidden_path)

    with pytest.raises(module.PublishError, match="non-root"):
        _invoke_direct_writer(module, args)

    assert touched == []


def test_sourcing_mac_release_driver_is_inert_before_caller_paths_or_tools(
    tmp_path: Path,
) -> None:
    after = tmp_path / "after"
    marker = tmp_path / "external-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "git", "python3", "ssh", "curl"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)

    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"set -- --preflight-only; source {RELEASE_DMG!s}; printf AFTER > {after!s}",
        ],
        cwd=tmp_path,
        env={"PATH": str(fake_bin), "MAC_RELEASE_TOKEN": "must-not-leak"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert "must-not-leak" not in completed.stdout + completed.stderr
    assert after.read_text(encoding="utf-8") == "AFTER"
    assert not marker.exists()


def test_hostile_source_cannot_reach_mac_release_legacy_when_builtins_are_shadowed(
    tmp_path: Path,
) -> None:
    tool_marker = tmp_path / "external-called"
    function_marker = tmp_path / "legacy-function-loaded"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "git", "python3", "ssh", "curl"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {tool_marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    harness = f"""
set -- --preflight-only
exit() {{ return 0; }}
builtin() {{ return 0; }}
printf() {{ return 0; }}
set() {{ return 0; }}
source {RELEASE_DMG!s}
if declare -F finalize_remote_release >/dev/null; then
  : > {function_marker!s}
fi
"""

    completed = subprocess.run(
        ["/bin/bash", "-c", harness],
        cwd=tmp_path,
        env={"PATH": str(fake_bin), "MAC_RELEASE_TOKEN": "must-not-read"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert not tool_marker.exists()
    assert not function_marker.exists()


def _receipt(artifact: Path, asset_root: Path) -> dict[str, object]:
    content = artifact.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    artifact_path = asset_root / "mac/releases" / SOURCE_SHA / f"{digest}.dmg"
    return {
        "schema_version": 1,
        "source_sha": SOURCE_SHA,
        "source_tree": SOURCE_TREE,
        "artifact_sha256": digest,
        "artifact_size": len(content),
        "artifact_path": str(artifact_path),
        "artifact_url": (
            "https://health.executor.life/mac/releases/"
            f"{SOURCE_SHA}/{digest}.dmg"
        ),
        "bundle_id": "life.executor.health.mac",
        "version": "1.2.3",
        "build": "42",
        "team_id": "QA2U724DAN",
        "cdhash": "a" * 40,
        "architectures": ["arm64", "x86_64"],
        "min_os": "14.0",
        "notary_submission_id": NOTARY_ID,
        "notary_status": "Accepted",
        "stapled": True,
        "published_at": "2026-08-12T12:34:56Z",
    }


@pytest.mark.parametrize(
    "arguments",
    (
        ("publish", "--version", "1.2.3", "--build", "42"),
        ("recover",),
        ("rollback",),
    ),
)
def test_mac_driver_blocks_production_mutation_before_network(
    arguments: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        [str(RELEASE_DMG), *arguments],
        cwd=ROOT,
        env={**os.environ, "REVA_MAC_RELEASE_VIA_DEPLOY": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 78
    assert "manual release Gate" in completed.stderr


def test_mac_skip_upload_build_path_is_also_frozen_before_external_tools() -> None:
    completed = subprocess.run(
        [
            str(RELEASE_DMG),
            "publish",
            "--version",
            "1.2.3",
            "--build",
            "42",
            "--skip-upload",
        ],
        cwd=ROOT,
        env={**os.environ, "REVA_MAC_RELEASE_VIA_DEPLOY": "1"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "manual release Gate" in completed.stderr


def test_mac_driver_freezes_before_loading_or_acquiring_the_local_release_lock() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    freeze = source.index("Mac production release entrypoint is frozen")
    load_lock = source.index('source "${DEFAULT_REPO_ROOT}/scripts/release_lock.sh"')
    acquire_lock = source.index('acquire_release_lock "mac-dmg-release"')

    assert freeze < load_lock < acquire_lock


def test_mac_driver_freezes_writer_before_path_resolution_or_path_tools(
    tmp_path: Path,
) -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")
    freeze = source.index("Mac production release entrypoint is frozen")
    assert freeze < source.index('SCRIPT_DIR="')

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "path-tool-called"
    for name in ("dirname", "git", "python3", "ssh"):
        fake = fake_bin / name
        fake.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "{name}" >> "{marker}"\nexit 91\n',
            encoding="utf-8",
        )
        fake.chmod(0o755)

    completed = subprocess.run(
        [str(RELEASE_DMG), "publish", "--version", "1.2.3", "--build", "42"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "REVA_MAC_RELEASE_VIA_DEPLOY": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "manual release Gate" in completed.stderr
    assert not marker.exists()


def test_mac_publisher_production_cli_freezes_before_imports_paths_tools_or_tokens(
    tmp_path: Path,
) -> None:
    isolated = tmp_path / "publisher"
    isolated.mkdir()
    script = isolated / PUBLISHER.name
    shutil.copyfile(PUBLISHER, script)
    marker = tmp_path / "import-or-tool-called"
    (isolated / "argparse.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "git", "nginx", "ssh", "systemctl"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    secret = "mac-release-token-must-not-leak"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "publish",
            "--asset-root",
            "/must-not-resolve",
            "--allow-non-root-for-tests",
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(fake_bin),
            "HOME": str(tmp_path / "poison-home"),
            "MAC_RELEASE_REMOTE_LOCK_TOKEN": secret,
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "MAC_RELEASE_PUBLISH_FROZEN" in completed.stderr
    assert secret not in completed.stdout + completed.stderr
    assert "/must-not-resolve" not in completed.stdout + completed.stderr
    assert not marker.exists()


def test_mac_publisher_executable_ignores_hostile_path_before_freeze(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    marker = tmp_path / "fake-python-called"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        f"#!/bin/sh\nprintf called > {marker!s}\nexit 91\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    completed = subprocess.run(
        [
            str(PUBLISHER),
            "publish",
            "--allow-non-root-for-tests",
        ],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "MAC_RELEASE_PUBLISH_FROZEN" in completed.stderr
    assert not marker.exists()


def _write_candidate(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _public(payload: dict[str, object]) -> dict[str, object]:
    return {key: payload[key] for key in PUBLIC_FIELDS}


def _publish(
    artifact: Path,
    candidate: Path,
    asset_root: Path,
    state_root: Path,
    *,
    fail_at: str | None = None,
    crash_at: str | None = None,
    release_lock: tuple[Path, str] | None = None,
    drop_lock_at: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MAC_RELEASE_TEST_MODE"] = "1"
    if fail_at:
        env["MAC_RELEASE_FAIL_AT_FOR_TESTS"] = fail_at
    if crash_at:
        env["MAC_RELEASE_CRASH_AT_FOR_TESTS"] = crash_at
    if drop_lock_at:
        env["MAC_RELEASE_DROP_LOCK_AT_FOR_TESTS"] = drop_lock_at
    command = [
        *_publisher_test_runner(),
        "publish",
        "--artifact",
        str(artifact),
        "--candidate",
        str(candidate),
        "--asset-root",
        str(asset_root),
        "--state-root",
        str(state_root),
        "--allow-non-root-for-tests",
    ]
    if release_lock:
        command.extend(
            (
                "--release-lock-dir",
                str(release_lock[0]),
                "--release-lock-token",
                release_lock[1],
            )
        )
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _publisher_maintenance(
    command: str,
    asset_root: Path,
    state_root: Path,
    *,
    release_lock: tuple[Path, str] | None = None,
    drop_lock_at: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MAC_RELEASE_TEST_MODE"] = "1"
    if drop_lock_at:
        env["MAC_RELEASE_DROP_LOCK_AT_FOR_TESTS"] = drop_lock_at
    invocation = [
        *_publisher_test_runner(),
        command,
        "--asset-root",
        str(asset_root),
        "--state-root",
        str(state_root),
        "--allow-non-root-for-tests",
    ]
    if release_lock:
        invocation.extend(
            (
                "--release-lock-dir",
                str(release_lock[0]),
                "--release-lock-token",
                release_lock[1],
            )
        )
    return subprocess.run(
        invocation,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _remote_release_lock(tmp_path: Path) -> tuple[Path, str]:
    lock_dir = tmp_path / "health-app-release"
    lock_dir.mkdir(mode=0o700)
    token = "mac-release-test-token"
    token_file = lock_dir / "token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    return lock_dir, token


def _second_release(
    tmp_path: Path,
    asset_root: Path,
    *,
    content: bytes = b"candidate-two",
) -> tuple[Path, Path, dict[str, object]]:
    artifact = tmp_path / f"upload-{hashlib.sha256(content).hexdigest()[:8]}.dmg"
    artifact.write_bytes(content)
    artifact.chmod(0o600)
    payload = _receipt(artifact, asset_root)
    payload["source_sha"] = "3" * 40
    payload["source_tree"] = "4" * 40
    digest = str(payload["artifact_sha256"])
    payload["artifact_path"] = str(
        asset_root / "mac/releases" / payload["source_sha"] / f"{digest}.dmg"
    )
    payload["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{payload['source_sha']}/{digest}.dmg"
    )
    payload["build"] = "43"
    candidate = tmp_path / f"candidate-{digest[:8]}.json"
    _write_candidate(candidate, payload)
    return artifact, candidate, payload


def _prepare(tmp_path: Path, content: bytes = b"signed-notarized-dmg"):
    artifact = tmp_path / "upload.dmg"
    artifact.write_bytes(content)
    artifact.chmod(0o600)
    asset_root = tmp_path / "assets"
    asset_root.mkdir(mode=0o755)
    state_root = tmp_path / "release-state"
    state_root.mkdir(mode=0o700)
    candidate = tmp_path / "candidate.json"
    payload = _receipt(artifact, asset_root)
    _write_candidate(candidate, payload)
    return artifact, candidate, asset_root, state_root, payload


def _release_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "release-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "mac-release@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Mac Release Test"], cwd=repo, check=True
    )
    (repo / "tracked.txt").write_text("trusted\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "trusted"], cwd=repo, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", sha],
        cwd=repo,
        check=True,
    )
    return repo, sha


def _release_preflight(
    repo: Path,
    sha: str,
    *arguments: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "MAC_RELEASE_TEST_MODE": "1",
            "MAC_RELEASE_REPO_ROOT_FOR_TESTS": str(repo),
            "MAC_RELEASE_REMOTE_MAIN_SHA_FOR_TESTS": sha,
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["/bin/bash", "-c", f'set -- "$@"; {MAC_LEGACY_SOURCE}', "fixture", *arguments],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _protocol_context(
    tmp_path: Path,
    *,
    token: str = "mac-1111111111111111-11111111-1111-4111-8111-111111111111",
    operation: str = "publish",
    stage_kind: str = "publish",
    helper_path: Path = PUBLISHER,
    artifact_content: bytes = b"protocol-artifact",
    candidate_content: bytes = b'{"candidate":"protocol"}\n',
) -> dict[str, object]:
    protocol_root = tmp_path / "remote state root"
    protocol_root.mkdir(mode=0o700, exist_ok=True)
    asset_root = tmp_path / "remote assets"
    asset_root.mkdir(mode=0o755, exist_ok=True)
    state_root = protocol_root
    lock_dir = state_root / "deploy.lock"
    stage = asset_root / "mac/.staging" / token
    helper = helper_path.read_bytes()
    artifact_sha256 = hashlib.sha256(artifact_content).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_content).hexdigest()
    command = [
        *_publisher_test_runner(helper_path),
        "lease-acquire",
        "--lock-dir",
        str(lock_dir),
        "--token",
        token,
        "--operation",
        operation,
        "--stage-kind",
        stage_kind,
        "--stage",
        str(stage),
        "--asset-root",
        str(asset_root),
        "--state-root",
        str(state_root),
        "--source-sha",
        SOURCE_SHA,
        "--source-tree",
        SOURCE_TREE,
        "--helper-sha256",
        hashlib.sha256(helper).hexdigest(),
        "--artifact-sha256",
        artifact_sha256 if stage_kind == "publish" else "-",
        "--artifact-size",
        str(len(artifact_content)) if stage_kind == "publish" else "0",
        "--candidate-sha256",
        candidate_sha256 if stage_kind == "publish" else "-",
        "--allow-non-root-for-tests",
    ]
    return {
        "command": command,
        "lock_dir": lock_dir,
        "asset_root": asset_root,
        "state_root": state_root,
        "stage": stage,
        "token": token,
        "helper": helper,
        "artifact": artifact_content,
        "candidate": candidate_content,
    }


def _protocol_run(
    context: dict[str, object],
    command: str,
    *extra: str,
    crash_at: str | None = None,
    helper_path: Path = PUBLISHER,
) -> subprocess.CompletedProcess[str]:
    invocation = list(context["command"])
    invocation[3] = str(helper_path)
    invocation[4] = command
    invocation.extend(extra)
    env = os.environ.copy()
    env["MAC_RELEASE_TEST_MODE"] = "1"
    if crash_at:
        env["MAC_RELEASE_PROTOCOL_CRASH_AT_FOR_TESTS"] = crash_at
    return subprocess.run(
        invocation,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _protocol_tree_snapshot(*roots: Path) -> tuple[tuple[object, ...], ...]:
    """Capture durable state so a rejected protocol call can prove zero writes."""

    rows: list[tuple[object, ...]] = []
    for root_index, root in enumerate(roots):
        paths = [root, *sorted(root.rglob("*"), key=lambda item: str(item))]
        for path in paths:
            metadata = path.lstat()
            payload: object = None
            if stat.S_ISREG(metadata.st_mode):
                payload = hashlib.sha256(path.read_bytes()).hexdigest()
            elif stat.S_ISLNK(metadata.st_mode):
                payload = os.readlink(path)
            rows.append(
                (
                    root_index,
                    str(path.relative_to(root)),
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_nlink,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    payload,
                )
            )
    return tuple(rows)


def _bind_protocol_stage(context: dict[str, object]) -> None:
    reset = _protocol_run(context, "stage-reset")
    assert reset.returncode == 0, reset.stderr
    stage = context["stage"]
    assert isinstance(stage, Path)
    (stage / ".mac_release_publish.py.upload").write_bytes(context["helper"])
    (stage / ".mac_release_publish.py.upload").chmod(0o600)
    bound = _protocol_run(context, "stage-bind-helper")
    assert bound.returncode == 0, bound.stderr
    command = context["command"]
    assert isinstance(command, list)
    stage_kind = command[command.index("--stage-kind") + 1]
    if stage_kind == "publish":
        (stage / ".upload.dmg.upload").write_bytes(context["artifact"])
        (stage / ".upload.dmg.upload").chmod(0o600)
        (stage / ".candidate.json.upload").write_bytes(context["candidate"])
        (stage / ".candidate.json.upload").chmod(0o600)
        payload = _protocol_run(context, "stage-bind-payload")
        assert payload.returncode == 0, payload.stderr


def _lease_file_order() -> tuple[str, ...]:
    return (
        "artifact_sha256",
        "artifact_size",
        "candidate_sha256",
        "helper_sha256",
        "label",
        "operation",
        "phase",
        "source_sha",
        "source_tree",
        "stage",
        "stage_kind",
        "started_at",
        "token",
    )


def _write_protocol_handoff(context: dict[str, object], root: Path) -> Path:
    bundle = root / "git common dir with spaces/reva-mac-release-recovery"
    bundle.mkdir(parents=True, mode=0o700)
    helper = bundle / "mac_release_publish.py"
    helper.write_bytes(context["helper"])
    helper.chmod(0o600)
    command = context["command"]
    assert isinstance(command, list)

    def value(flag: str) -> str:
        return str(command[command.index(flag) + 1])

    fields = {
        "schema": "1",
        "server": "protocol-test@localhost",
        "lock_dir": value("--lock-dir"),
        "token": value("--token"),
        "operation": value("--operation"),
        "stage_kind": value("--stage-kind"),
        "stage": value("--stage"),
        "source_sha": value("--source-sha"),
        "source_tree": value("--source-tree"),
        "helper_sha256": value("--helper-sha256"),
        "artifact_sha256": value("--artifact-sha256"),
        "artifact_size": value("--artifact-size"),
        "candidate_sha256": value("--candidate-sha256"),
    }
    handoff = bundle / "handoff"
    handoff.write_text(
        "".join(f"{key}={value}\n" for key, value in fields.items()),
        encoding="utf-8",
    )
    handoff.chmod(0o600)
    return bundle


def _shell_protocol_recover(
    context: dict[str, object],
    root: Path,
    repo: Path,
    sha: str,
    bundle: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "MAC_RELEASE_TEST_MODE": "1",
            "MAC_RELEASE_REPO_ROOT_FOR_TESTS": str(repo),
            "MAC_RELEASE_REMOTE_MAIN_SHA_FOR_TESTS": sha,
            "MAC_RELEASE_PROTOCOL_TEST_ROOT": str(root),
            "MAC_RELEASE_PROTOCOL_ASSET_ROOT_FOR_TESTS": str(context["asset_root"]),
            "MAC_RELEASE_PROTOCOL_STATE_ROOT_FOR_TESTS": str(context["state_root"]),
            "MAC_RELEASE_PROTOCOL_HANDOFF_FOR_TESTS": str(bundle),
            "MAC_RELEASE_PROTOCOL_PYTHON_FOR_TESTS": str(Path(sys.executable).resolve()),
        }
    )
    return subprocess.run(
        ["/bin/bash", "-c", f'set -- "$@"; {MAC_LEGACY_SOURCE}', "fixture", "--protocol-recovery-test"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _fake_route_curl(
    path: Path,
    *,
    immutable_marker: bool,
    redirect_route: str | None = None,
) -> Path:
    immutable_header = (
        "marker='mac-immutable-dmg'" if immutable_marker else "marker=''"
    )
    path.write_text(
        "\n".join(
            (
                "#!/bin/sh",
                "headers=''",
                "url=''",
                'while [ "$#" -gt 0 ]; do',
                '  case "$1" in',
                '    -D|--dump-header) headers="$2"; shift 2 ;;',
                '    -o|-w|--output|--write-out|--max-time|--max-redirs|--proto) shift 2 ;;',
                '    -*) shift ;;',
                '    *) url="$1"; shift ;;',
                "  esac",
                "done",
                'case "$url" in',
                f"  */xiaoba-mac.dmg) status=$([ '{redirect_route}' = legacy ] && printf 302 || printf 200); marker='' ;;",
                f"  */mac/current.json) status=$([ '{redirect_route}' = current ] && printf 302 || printf 404); marker='mac-current-manifest' ;;",
                f"  */mac/releases/0000000000000000000000000000000000000000/*) status=$([ '{redirect_route}' = immutable ] && printf 302 || printf 404); {immutable_header} ;;",
                "  *) status=500; marker='' ;;",
                "esac",
                "{",
                "  printf 'HTTP/2 %s\\r\\n' \"$status\"",
                "  if [ -n \"$marker\" ]; then printf 'X-Reva-Artifact: %s\\r\\n' \"$marker\"; fi",
                "  printf '\\r\\n'",
                '} > "$headers"',
                "printf '%s' \"$status\"",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def _fake_proof_curl(path: Path) -> Path:
    path.write_text(
        "\n".join(
            (
                f"#!{Path(sys.executable).resolve()}",
                "import json, os, pathlib, sys",
                "args = sys.argv[1:]",
                "if args == ['--version']:",
                "    print('curl 8.7.1 (test)')",
                "    raise SystemExit(0)",
                "def option(name):",
                "    index = args.index(name)",
                "    return args[index + 1]",
                "required_flags = {'--tlsv1.2', '--fail', '--silent', '--show-error'}",
                "if not required_flags.issubset(args):",
                "    raise SystemExit(91)",
                "if option('--proto') != '=https' or option('--max-redirs') != '0':",
                "    raise SystemExit(92)",
                "limit = int(option('--max-filesize'))",
                "output = pathlib.Path(option('--output'))",
                "log = pathlib.Path(os.environ['FAKE_CURL_LOG'])",
                "log.write_text(json.dumps(args), encoding='utf-8')",
                "mode = os.environ['FAKE_CURL_MODE']",
                "if mode == 'redirect':",
                "    output.write_bytes(b'redirect-body')",
                "    print('302', end='')",
                "elif mode == 'oversized':",
                "    output.write_bytes(b'x' * (limit + 1))",
                "    print('200', end='')",
                "    raise SystemExit(63)",
                "elif mode == 'success':",
                "    output.write_bytes(os.environ.get('FAKE_CURL_BODY', 'ok').encode())",
                "    print('200', end='')",
                "else:",
                "    raise SystemExit(93)",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def _run_http_proof_test(
    tmp_path: Path,
    *,
    mode: str,
    maximum: int,
    body: str = "ok",
) -> tuple[subprocess.CompletedProcess[str], Path, list[str]]:
    repo, sha = _release_repo(tmp_path)
    fake_curl = _fake_proof_curl(tmp_path / "proof-curl")
    proof_root = tmp_path / "http proof root"
    proof_root.mkdir(mode=0o700)
    log = tmp_path / "curl-arguments.json"
    env = os.environ.copy()
    env.update(
        {
            "MAC_RELEASE_TEST_MODE": "1",
            "MAC_RELEASE_REPO_ROOT_FOR_TESTS": str(repo),
            "MAC_RELEASE_REMOTE_MAIN_SHA_FOR_TESTS": sha,
            "MAC_RELEASE_CURL_FOR_TESTS": str(fake_curl),
            "MAC_RELEASE_HTTP_TEST_ROOT": str(proof_root),
            "FAKE_CURL_LOG": str(log),
            "FAKE_CURL_MODE": mode,
            "FAKE_CURL_BODY": body,
        }
    )
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f'set -- "$@"; {MAC_LEGACY_SOURCE}',
            "fixture",
            "--http-proof-test",
            "https://health.executor.life/test-proof",
            str(maximum),
            "30",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    arguments = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    return result, proof_root, arguments


def test_public_proof_download_rejects_redirect_and_removes_partial(
    tmp_path: Path,
) -> None:
    result, proof_root, arguments = _run_http_proof_test(
        tmp_path, mode="redirect", maximum=16 * 1024
    )

    assert result.returncode != 0
    assert "http 200" in result.stderr.lower()
    assert list(proof_root.iterdir()) == []
    assert arguments[arguments.index("--proto") + 1] == "=https"
    assert arguments[arguments.index("--max-redirs") + 1] == "0"
    assert "--tlsv1.2" in arguments


def test_public_proof_download_enforces_streaming_limit_and_removes_partial(
    tmp_path: Path,
) -> None:
    result, proof_root, arguments = _run_http_proof_test(
        tmp_path, mode="oversized", maximum=8
    )

    assert result.returncode != 0
    assert "bounded public proof download failed" in result.stderr.lower()
    assert list(proof_root.iterdir()) == []
    assert arguments[arguments.index("--max-filesize") + 1] == "8"


def test_public_proof_download_accepts_direct_bounded_http_200(tmp_path: Path) -> None:
    result, proof_root, arguments = _run_http_proof_test(
        tmp_path, mode="success", maximum=8, body="bounded"
    )

    assert result.returncode == 0, result.stderr
    assert (proof_root / "proof").read_bytes() == b"bounded"
    assert arguments[arguments.index("--max-filesize") + 1] == "8"


def test_every_slow_public_release_proof_uses_the_bounded_fetch_choke_point() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    for destination in (
        '"${current_json}" 16384 30',
        '"${immutable_proof}" "${size}" 300',
        '"${stable_proof}" "${size}" 300',
        '"${HTTP_PROOF}" "${ARTIFACT_SIZE}" 300',
        '"${CURRENT_JSON}" 16384 30',
        '"${STABLE_PROOF}" "${ARTIFACT_SIZE}" 300',
        '"${IMMUTABLE_FINAL_PROOF}" "${ARTIFACT_SIZE}" 300',
    ):
        assert f"fetch_public_proof " in source
        assert destination in source
    assert "--proto '=https'" in source
    assert "--tlsv1.2" in source
    assert "--max-redirs 0" in source
    assert "--max-filesize" in source
    assert "curl 8.4.0 or newer is required" in source


def test_release_script_requires_clean_exact_remote_main_before_build() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    assert "--porcelain=v1" in source
    assert "--untracked-files=all" in source
    assert "refs/heads/main" in source
    assert "origin/main" in source
    assert "SOURCE_TREE" in source
    assert source.index("verify_release_source") < source.index("package-app.sh")


def test_release_test_mode_cannot_reach_build_notary_or_upload(tmp_path: Path) -> None:
    repo, sha = _release_repo(tmp_path)

    result = _release_preflight(repo, sha, "--version", "1.2.3", "--build", "42")

    # This helper extracts only the syntactically unreachable legacy body for
    # protocol regression tests.  The real script's unconditional rc78 freeze
    # is covered separately above; inside the isolated fixture, test mode must
    # still reject every build/notary/upload path before the first build step.
    assert result.returncode == 2
    assert "test mode is read-only" in result.stderr.lower()
    assert "[1/7]" not in result.stdout


def test_isolated_preflight_fixture_does_not_claim_the_shared_release_lock(
    tmp_path: Path,
) -> None:
    repo, sha = _release_repo(tmp_path)
    holder = subprocess.Popen(
        [
            sys.executable,
            str(RELEASE_LOCK),
            "run",
            "--repo-root",
            str(repo),
            "--label",
            "test-holder",
            "--",
            "/bin/sh",
            "-c",
            "echo READY; sleep 30",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "READY"
        result = _release_preflight(repo, sha, "--preflight-only")
    finally:
        holder.terminate()
        holder.wait(timeout=10)

    # MAC_LEGACY_SOURCE deliberately replaces acquire_release_lock so these
    # read-only protocol fixtures cannot claim real release authority.  The
    # production driver itself exits 78 before loading the lock helper.
    assert result.returncode == 0, result.stderr
    assert "Source verified:" in result.stdout


def test_release_builds_from_an_exact_git_archive_and_reprobes_before_upload() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    assert "scripts/release_lock.sh" in source
    assert 'acquire_release_lock "mac-dmg-release"' in source
    assert "git_release archive" in source
    assert 'SNAPSHOT_DIR="${WORK_DIR}/source"' in source
    assert '"${SNAPSHOT_DIR}/apps/mac/scripts/package-app.sh"' in source
    assert source.count("verify_release_source") >= 4
    assert source.rindex("verify_release_source") < source.index(
        'echo "[7/7] Upload immutable artifact'
    )


def test_release_uses_only_pinned_ssh_and_scp_wrappers() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    for token in (
        "-F",
        '"/dev/null"',
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=/dev/null",
        "GlobalKnownHostsFile=/dev/null",
        "KnownHostsCommand=",
        "39.98.206.178",
        "ssh_release",
        "scp_release",
    ):
        assert token in source
    assert "HEALTH_MAC_RELEASE_SERVER" not in source


def test_formal_release_holds_the_unified_remote_release_lease() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")
    publisher = PUBLISHER.read_text(encoding="utf-8")

    assert (
        'REMOTE_RELEASE_LOCK_DIR="/var/lib/health-app/release-state/deploy.lock"'
        in source
    )
    for token in (
        "acquire_remote_release_lock",
        "assert_remote_release_lock",
        "release_remote_release_lock",
        "--release-lock-dir",
        "--release-lock-token",
    ):
        assert token in source
    assert (
        'EXPECTED_RELEASE_LOCK_DIR = Path("/var/lib/health-app/release-state/deploy.lock")'
        in publisher
    )
    assert "_assert_release_authority" in publisher


def test_release_route_contract_is_checked_before_any_remote_write() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    call = source.index("preflight_public_routes\n")
    first_upload = source.index('echo "[7/7] Upload immutable artifact')
    assert call < first_upload
    assert "mac-current-manifest" in source
    assert "mac-immutable-dmg" in source
    assert "xiaoba-mac.dmg" in source


def test_route_preflight_accepts_only_the_marked_route_contract(tmp_path: Path) -> None:
    repo, sha = _release_repo(tmp_path)
    fake_curl = _fake_route_curl(tmp_path / "curl", immutable_marker=True)

    result = _release_preflight(
        repo,
        sha,
        "--route-preflight-only",
        extra_env={"MAC_RELEASE_CURL_FOR_TESTS": str(fake_curl)},
    )

    assert result.returncode == 0, result.stderr
    assert "public route preflight passed" in result.stdout.lower()


def test_route_preflight_rejects_a_missing_immutable_marker(tmp_path: Path) -> None:
    repo, sha = _release_repo(tmp_path)
    fake_curl = _fake_route_curl(tmp_path / "curl", immutable_marker=False)

    result = _release_preflight(
        repo,
        sha,
        "--route-preflight-only",
        extra_env={"MAC_RELEASE_CURL_FOR_TESTS": str(fake_curl)},
    )

    assert result.returncode != 0
    assert "mac-immutable-dmg" in result.stderr


@pytest.mark.parametrize("route", ("legacy", "current", "immutable"))
def test_route_preflight_rejects_redirects(tmp_path: Path, route: str) -> None:
    repo, sha = _release_repo(tmp_path)
    fake_curl = _fake_route_curl(
        tmp_path / "curl", immutable_marker=True, redirect_route=route
    )

    result = _release_preflight(
        repo,
        sha,
        "--route-preflight-only",
        extra_env={"MAC_RELEASE_CURL_FOR_TESTS": str(fake_curl)},
    )

    assert result.returncode != 0
    assert "must return" in result.stderr.lower()


def test_package_embeds_release_identity_and_version_in_plist_and_manifest() -> None:
    source = PACKAGE_APP.read_text(encoding="utf-8")

    for value in (
        "MAC_APP_VERSION",
        "MAC_APP_BUILD",
        "MAC_SOURCE_SHA",
        "MAC_SOURCE_TREE",
        "RevaSourceSHA",
        "RevaSourceTree",
        "release-manifest.json",
    ):
        assert value in source


def test_release_script_verifies_signature_notarization_staple_and_mounted_app() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    assert "--output-format json" in source
    assert "stapler validate" in source
    assert "spctl --assess" in source
    assert "hdiutil attach" in source
    assert "codesign --verify" in source
    assert "RevaSourceSHA" in source
    assert "RevaSourceTree" in source


def test_release_pins_the_expected_bundle_and_developer_team() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")
    publisher = PUBLISHER.read_text(encoding="utf-8")

    assert 'EXPECTED_BUNDLE_ID="life.executor.health.mac"' in source
    assert 'EXPECTED_TEAM_ID="QA2U724DAN"' in source
    assert '"${BUNDLE_ID}" == "${EXPECTED_BUNDLE_ID}"' in source
    assert '"${TEAM_ID}" == "${EXPECTED_TEAM_ID}"' in source
    assert 'EXPECTED_BUNDLE_ID = "life.executor.health.mac"' in publisher
    assert 'EXPECTED_TEAM_ID = "QA2U724DAN"' in publisher


def test_release_accepts_only_stable_numeric_versions() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")
    publisher = PUBLISHER.read_text(encoding="utf-8")

    assert "([-+]" not in source
    assert "[-+]" not in publisher[publisher.index("VERSION_RE") : publisher.index("BUILD_RE")]


def test_formal_release_pins_production_paths_and_public_origin() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    assert 'ASSET_ROOT="/opt/health-app-shared/assets"' in source
    assert 'STATE_ROOT="/var/lib/health-app/release-state"' in source
    assert 'PUBLIC_BASE_URL="https://health.executor.life"' in source
    assert 'ASSET_ROOT="${HEALTH_MAC_ASSET_ROOT:-/opt' not in source
    assert 'STATE_ROOT="${HEALTH_MAC_STATE_ROOT:-/var' not in source
    assert 'PUBLIC_BASE_URL="${HEALTH_MAC_PUBLIC_BASE_URL:-https' not in source


def test_release_requires_a_private_single_link_notary_key() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    for token in ("stat -f '%HT'", "stat -f '%Su'", "stat -f '%Lp'", "stat -f '%l'"):
        assert token in source
    assert "Notarization credential file is unsafe" in source


def test_post_switch_http_failure_requires_reconciliation() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")
    publish_block = source[source.index('REMOTE_PUBLISH=('):]

    assert "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED" in publish_block
    assert "reconciliation" in publish_block.lower()
    assert publish_block.index("remote publish outcome is ambiguous") > publish_block.index(
        'remote_publisher "${REMOTE_PUBLISH[@]}"'
    )
    for marker in (
        "current manifest verification failed after switch",
        "current manifest does not match the candidate after switch",
        "stable download verification failed after switch",
        "stable download did not match after switch",
        "immutable download verification failed after switch",
        "immutable download did not match after switch",
    ):
        offset = publish_block.index(marker)
        branch = publish_block[offset : offset + 400]
        assert "REMOTE_RELEASE_LOCK_HELD=0" in branch
        assert "exit 75" in branch


@pytest.mark.parametrize(
    "crash_at",
    ("acquire-after-mkdir",)
    + tuple(f"acquire-after-write-{name}" for name in _lease_file_order()),
)
def test_partial_creating_lease_is_resumed_without_looking_free(
    tmp_path: Path,
    crash_at: str,
) -> None:
    context = _protocol_context(tmp_path)

    crashed = _protocol_run(context, "lease-acquire", "--requested-action", "publish", crash_at=crash_at)

    assert crashed.returncode == 87
    lock_dir = context["lock_dir"]
    token = context["token"]
    assert isinstance(lock_dir, Path) and isinstance(token, str)
    creating = lock_dir.parent / f".{lock_dir.name}.mac-creating-{token}"
    assert creating.exists()
    assert not lock_dir.exists()

    resumed = _protocol_run(context, "lease-acquire", "--requested-action", "recover")

    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["status"] == "created"
    assert lock_dir.exists()
    assert not creating.exists()


@pytest.mark.parametrize(
    "crash_at",
    ("release-after-rename",)
    + tuple(f"release-after-remove-{name}" for name in _lease_file_order()),
)
def test_partial_releasing_lease_is_resumed_for_every_remaining_field(
    tmp_path: Path,
    crash_at: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0

    crashed = _protocol_run(
        context,
        "lease-release",
        "--phase",
        "staging",
        crash_at=crash_at,
    )

    assert crashed.returncode == 87
    lock_dir = context["lock_dir"]
    token = context["token"]
    assert isinstance(lock_dir, Path) and isinstance(token, str)
    tombstone = lock_dir.parent / f".{lock_dir.name}.mac-releasing-{token}"
    assert tombstone.exists()
    assert not lock_dir.exists()

    resumed = _protocol_run(context, "lease-release", "--phase", "staging")

    assert resumed.returncode == 0, resumed.stderr
    assert not tombstone.exists()
    assert not lock_dir.exists()


def test_empty_release_tombstone_is_idempotently_removed(tmp_path: Path) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    crashed = _protocol_run(
        context,
        "lease-release",
        "--phase",
        "staging",
        crash_at="release-after-remove-token",
    )
    assert crashed.returncode == 87
    lock_dir = context["lock_dir"]
    token = context["token"]
    assert isinstance(lock_dir, Path) and isinstance(token, str)
    tombstone = lock_dir.parent / f".{lock_dir.name}.mac-releasing-{token}"
    assert tombstone.exists() and not any(tombstone.iterdir())

    resumed = _protocol_run(context, "lease-release", "--phase", "staging")

    assert resumed.returncode == 0, resumed.stderr
    assert not tombstone.exists()


@pytest.mark.parametrize(
    "residue_name,is_directory",
    (
        (".deploy.lock.alloc-generic-token", True),
        (".deploy.lock.state-generic-token", False),
        (".deploy.lock.released-generic-token", True),
        (".deploy.lock.mac-creating-mac-2222222222222222-22222222-2222-4222-8222-222222222222", True),
        (".deploy.lock.mac-releasing-mac-2222222222222222-22222222-2222-4222-8222-222222222222", True),
        (".deploy.lock.mac-phase-mac-2222222222222222-22222222-2222-4222-8222-222222222222", False),
    ),
)
def test_foreign_generic_or_mac_residue_blocks_fresh_mac_acquire(
    tmp_path: Path,
    residue_name: str,
    is_directory: bool,
) -> None:
    context = _protocol_context(tmp_path)
    lock_dir = context["lock_dir"]
    assert isinstance(lock_dir, Path)
    residue = lock_dir.parent / residue_name
    if is_directory:
        residue.mkdir(mode=0o700)
    else:
        residue.write_text("foreign\n", encoding="utf-8")
        residue.chmod(0o600)

    result = _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    )

    assert result.returncode != 0
    assert "foreign" in result.stderr.lower()
    assert not lock_dir.exists()


@pytest.mark.parametrize(
    "old_phase,new_phase,crash_at",
    (
        ("staging", "sealed", "transition-after-write"),
        ("staging", "sealed", "transition-after-replace"),
        ("sealed", "mutating", "transition-after-write"),
        ("sealed", "mutating", "transition-after-replace"),
    ),
)
def test_phase_transition_response_loss_is_adoptable(
    tmp_path: Path,
    old_phase: str,
    new_phase: str,
    crash_at: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    if old_phase == "sealed":
        assert _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            "staging",
            "--new-phase",
            "sealed",
        ).returncode == 0

    lost_response = _protocol_run(
        context,
        "lease-transition",
        "--old-phase",
        old_phase,
        "--new-phase",
        new_phase,
        crash_at=crash_at,
    )

    assert lost_response.returncode == 87
    adopted = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )
    assert adopted.returncode == 0, adopted.stderr
    assert json.loads(adopted.stdout) == {
        "phase": new_phase,
        "status": "adopted",
    }
    lock_dir = context["lock_dir"]
    token = context["token"]
    assert isinstance(lock_dir, Path) and isinstance(token, str)
    assert not (lock_dir.parent / f".{lock_dir.name}.mac-phase-{token}").exists()


@pytest.mark.parametrize(
    "field,value",
    (
        ("label", "generic-deploy"),
        ("token", "mac-2222222222222222-22222222-2222-4222-8222-222222222222"),
        ("stage", "/tmp/foreign-stage"),
    ),
)
def test_tampered_lease_identity_is_rejected_without_further_writes(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    assert _protocol_run(
        context,
        "lease-transition",
        "--old-phase",
        "staging",
        "--new-phase",
        "sealed",
    ).returncode == 0
    lock_dir = context["lock_dir"]
    asset_root = context["asset_root"]
    state_root = context["state_root"]
    assert isinstance(lock_dir, Path)
    assert isinstance(asset_root, Path)
    assert isinstance(state_root, Path)
    (lock_dir / field).write_text(value + "\n", encoding="utf-8")
    before = _protocol_tree_snapshot(asset_root, state_root)

    rejected = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )

    assert rejected.returncode != 0
    assert _protocol_tree_snapshot(asset_root, state_root) == before


def test_extra_lease_entry_is_rejected_without_further_writes(tmp_path: Path) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    lock_dir = context["lock_dir"]
    asset_root = context["asset_root"]
    state_root = context["state_root"]
    assert isinstance(lock_dir, Path)
    assert isinstance(asset_root, Path)
    assert isinstance(state_root, Path)
    unexpected = lock_dir / "unexpected"
    unexpected.write_text("foreign\n", encoding="utf-8")
    unexpected.chmod(0o600)
    before = _protocol_tree_snapshot(asset_root, state_root)

    rejected = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )

    assert rejected.returncode != 0
    assert _protocol_tree_snapshot(asset_root, state_root) == before


@pytest.mark.parametrize(
    "entry",
    ("mac_release_publish.py", "candidate.json", "upload.dmg", "unexpected"),
)
def test_tampered_or_extra_sealed_stage_is_rejected_without_further_writes(
    tmp_path: Path,
    entry: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    assert _protocol_run(
        context,
        "lease-transition",
        "--old-phase",
        "staging",
        "--new-phase",
        "sealed",
    ).returncode == 0
    stage = context["stage"]
    asset_root = context["asset_root"]
    state_root = context["state_root"]
    assert isinstance(stage, Path)
    assert isinstance(asset_root, Path)
    assert isinstance(state_root, Path)
    target = stage / entry
    target.write_bytes(b"tampered-or-extra")
    target.chmod(0o600 if entry != "mac_release_publish.py" else 0o700)
    before = _protocol_tree_snapshot(asset_root, state_root)

    rejected = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )

    assert rejected.returncode != 0
    assert _protocol_tree_snapshot(asset_root, state_root) == before


def test_active_release_cannot_be_stolen_and_exact_original_helper_still_operates(
    tmp_path: Path,
) -> None:
    helper_a = tmp_path / "helper-a.py"
    helper_a.write_bytes(PUBLISHER.read_bytes())
    helper_a.chmod(0o600)
    context_a = _protocol_context(tmp_path, helper_path=helper_a)
    assert _protocol_run(
        context_a,
        "lease-acquire",
        "--requested-action",
        "publish",
        helper_path=helper_a,
    ).returncode == 0

    helper_b = tmp_path / "helper-b.py"
    helper_b.write_bytes(PUBLISHER.read_bytes() + b"\n# distinct helper B\n")
    helper_b.chmod(0o600)
    token_b = "mac-2222222222222222-22222222-2222-4222-8222-222222222222"
    context_b = _protocol_context(
        tmp_path,
        token=token_b,
        helper_path=helper_b,
    )
    # Reuse the same remote authority roots while retaining B's distinct exact
    # helper identity and token-specific stage.
    command_b = context_b["command"]
    command_a = context_a["command"]
    assert isinstance(command_b, list) and isinstance(command_a, list)
    for field in ("--lock-dir", "--asset-root", "--state-root"):
        command_b[command_b.index(field) + 1] = command_a[command_a.index(field) + 1]
    stage_b = Path(command_a[command_a.index("--asset-root") + 1]) / "mac/.staging" / token_b
    command_b[command_b.index("--stage") + 1] = str(stage_b)
    context_b["lock_dir"] = context_a["lock_dir"]
    context_b["asset_root"] = context_a["asset_root"]
    context_b["state_root"] = context_a["state_root"]
    context_b["stage"] = stage_b

    blocked = _protocol_run(
        context_b,
        "lease-acquire",
        "--requested-action",
        "publish",
        helper_path=helper_b,
    )
    assert blocked.returncode != 0

    still_a = _protocol_run(
        context_a,
        "lease-assert",
        "--phase",
        "staging",
        helper_path=helper_a,
    )
    assert still_a.returncode == 0, still_a.stderr
    released = _protocol_run(
        context_a,
        "lease-release",
        "--phase",
        "staging",
        helper_path=helper_a,
    )
    assert released.returncode == 0, released.stderr


def test_fresh_acquire_writes_no_stage_or_remote_helper_before_lease(
    tmp_path: Path,
) -> None:
    context = _protocol_context(tmp_path)
    stage = context["stage"]
    state_root = context["state_root"]
    assert isinstance(stage, Path) and isinstance(state_root, Path)

    acquired = _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    )

    assert acquired.returncode == 0, acquired.stderr
    assert not stage.exists()
    assert set(path.name for path in state_root.iterdir()) == {"deploy.lock"}


@pytest.mark.parametrize(
    "crash_at",
    (
        "stage-cleanup-after-rename",
        "stage-cleanup-after-remove-candidate.json",
        "stage-cleanup-after-remove-mac_release_publish.py",
        "stage-cleanup-after-remove-upload.dmg",
        "stage-cleanup-after-complete",
    ),
)
def test_mutating_stage_cleanup_is_lease_bound_and_crash_resumable(
    tmp_path: Path,
    crash_at: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    for old, new in (("staging", "sealed"), ("sealed", "mutating")):
        transitioned = _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            old,
            "--new-phase",
            new,
        )
        assert transitioned.returncode == 0, transitioned.stderr

    crashed = _protocol_run(
        context, "stage-cleanup", crash_at=crash_at
    )

    assert crashed.returncode == 87
    adopted = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )
    assert adopted.returncode == 0, adopted.stderr
    assert json.loads(adopted.stdout)["phase"] == "mutating"
    resumed = _protocol_run(context, "stage-cleanup")
    assert resumed.returncode == 0, resumed.stderr
    stage = context["stage"]
    asset_root = context["asset_root"]
    token = context["token"]
    assert isinstance(stage, Path) and isinstance(asset_root, Path) and isinstance(token, str)
    assert not stage.exists()
    cleanup = asset_root / "mac/.staging" / f".cleanup-{token}"
    assert cleanup.is_dir() and not any(cleanup.iterdir())
    released = _protocol_run(context, "lease-release", "--phase", "mutating")
    assert released.returncode == 0, released.stderr
    assert not cleanup.exists()


def test_stage_cleanup_without_exact_lease_cannot_delete_stage(tmp_path: Path) -> None:
    context = _protocol_context(tmp_path)
    stage = context["stage"]
    assert isinstance(stage, Path)
    stage.mkdir(parents=True, mode=0o700)
    sentinel = stage / "sentinel"
    sentinel.write_bytes(b"must survive")
    sentinel.chmod(0o600)

    result = _protocol_run(context, "stage-cleanup")

    assert result.returncode != 0
    assert sentinel.read_bytes() == b"must survive"


def test_unlock_response_loss_after_stage_proof_is_finished_by_recover_acquire(
    tmp_path: Path,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    for old, new in (("staging", "sealed"), ("sealed", "mutating")):
        assert _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            old,
            "--new-phase",
            new,
        ).returncode == 0
    assert _protocol_run(context, "stage-cleanup").returncode == 0

    crashed = _protocol_run(
        context,
        "lease-release",
        "--phase",
        "mutating",
        crash_at="release-after-stage-proof",
    )

    assert crashed.returncode == 87
    lock_dir = context["lock_dir"]
    assert isinstance(lock_dir, Path) and not lock_dir.exists()
    recovered = _protocol_run(
        context, "lease-acquire", "--requested-action", "recover"
    )
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout) == {
        "phase": "released",
        "status": "completed",
    }
    token = context["token"]
    assert isinstance(token, str)
    assert not (
        lock_dir.parent / f".{lock_dir.name}.mac-releasing-{token}"
    ).exists()


@pytest.mark.parametrize(
    "crash_at",
    (
        "stage-cleanup-after-rename",
        "stage-cleanup-after-remove-candidate.json",
        "stage-cleanup-after-remove-mac_release_publish.py",
        "stage-cleanup-after-remove-upload.dmg",
        "stage-cleanup-after-complete",
    ),
)
def test_real_release_shell_recovers_every_mutating_stage_cleanup_crash(
    tmp_path: Path,
    crash_at: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    for old, new in (("staging", "sealed"), ("sealed", "mutating")):
        assert _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            old,
            "--new-phase",
            new,
        ).returncode == 0
    assert _protocol_run(
        context, "stage-cleanup", crash_at=crash_at
    ).returncode == 87
    bundle = _write_protocol_handoff(context, tmp_path)
    repo, sha = _release_repo(tmp_path)

    recovered = _shell_protocol_recover(context, tmp_path, repo, sha, bundle)

    assert recovered.returncode == 0, recovered.stderr
    assert "protocol recovery harness completed" in recovered.stdout.lower()
    assert not bundle.exists()
    lock_dir = context["lock_dir"]
    assert isinstance(lock_dir, Path) and not lock_dir.exists()


@pytest.mark.parametrize("phase", ("staging", "sealed"))
def test_real_release_shell_recovers_pre_mutation_cleanup_response_loss(
    tmp_path: Path,
    phase: str,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    if phase == "sealed":
        assert _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            "staging",
            "--new-phase",
            "sealed",
        ).returncode == 0
    assert _protocol_run(
        context,
        "stage-cleanup",
        "--allow-partial-stage",
        crash_at="stage-cleanup-after-complete",
    ).returncode == 87
    stage = context["stage"]
    asset_root = context["asset_root"]
    token = context["token"]
    assert isinstance(stage, Path)
    assert isinstance(asset_root, Path)
    assert isinstance(token, str)
    cleanup = asset_root / "mac/.staging" / f".cleanup-{token}"
    assert not stage.exists()
    assert cleanup.is_dir() and not any(cleanup.iterdir())
    bundle = _write_protocol_handoff(context, tmp_path)
    repo, sha = _release_repo(tmp_path)

    recovered = _shell_protocol_recover(context, tmp_path, repo, sha, bundle)

    assert recovered.returncode == 0, recovered.stderr
    assert "pre-mutation mac release attempt" in recovered.stdout.lower()
    lock_dir = context["lock_dir"]
    assert isinstance(lock_dir, Path)
    assert not lock_dir.exists()
    assert not cleanup.exists()
    assert not bundle.exists()


def test_real_release_shell_finishes_unlock_after_stage_proof_response_loss(
    tmp_path: Path,
) -> None:
    context = _protocol_context(tmp_path)
    assert _protocol_run(
        context, "lease-acquire", "--requested-action", "publish"
    ).returncode == 0
    _bind_protocol_stage(context)
    for old, new in (("staging", "sealed"), ("sealed", "mutating")):
        assert _protocol_run(
            context,
            "lease-transition",
            "--old-phase",
            old,
            "--new-phase",
            new,
        ).returncode == 0
    assert _protocol_run(context, "stage-cleanup").returncode == 0
    assert _protocol_run(
        context,
        "lease-release",
        "--phase",
        "mutating",
        crash_at="release-after-stage-proof",
    ).returncode == 87
    bundle = _write_protocol_handoff(context, tmp_path)
    repo, sha = _release_repo(tmp_path)

    recovered = _shell_protocol_recover(context, tmp_path, repo, sha, bundle)

    assert recovered.returncode == 0, recovered.stderr
    assert "already completed stage cleanup and unlock" in recovered.stdout.lower()
    assert not bundle.exists()


@pytest.mark.parametrize(
    "crash_at",
    (
        "handoff-clear-after-rename",
        "handoff-clear-after-remove-handoff",
        "handoff-clear-after-remove-mac_release_publish.py",
        "handoff-clear-after-rmdir",
    ),
)
def test_local_handoff_clear_is_crash_resumable_with_space_in_path(
    tmp_path: Path,
    crash_at: str,
) -> None:
    parent = tmp_path / "git common dir with spaces"
    parent.mkdir(mode=0o700)
    bundle = parent / "reva-mac-release-recovery"
    bundle.mkdir(mode=0o700)
    (bundle / "handoff").write_text("schema=1\n", encoding="utf-8")
    (bundle / "handoff").chmod(0o600)
    (bundle / "mac_release_publish.py").write_bytes(PUBLISHER.read_bytes())
    (bundle / "mac_release_publish.py").chmod(0o600)
    token = "mac-1111111111111111-11111111-1111-4111-8111-111111111111"
    env = os.environ.copy()
    env.update(
        {
            "MAC_RELEASE_TEST_MODE": "1",
            "MAC_RELEASE_PROTOCOL_CRASH_AT_FOR_TESTS": crash_at,
        }
    )
    command = [
        *_publisher_test_runner(),
        "handoff-clear",
        "--bundle",
        str(bundle),
        "--token",
        token,
        "--allow-non-root-for-tests",
    ]

    crashed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)

    assert crashed.returncode == 87
    env.pop("MAC_RELEASE_PROTOCOL_CRASH_AT_FOR_TESTS")
    resumed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    assert resumed.returncode == 0, resumed.stderr
    assert not bundle.exists()
    assert not (parent / f"{bundle.name}.clearing-{token}").exists()


def test_publish_creates_immutable_artifact_and_atomic_receipts(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode == 0, result.stderr
    immutable = Path(str(payload["artifact_path"]))
    receipt = state_root / "mac-runtime.json"
    current = asset_root / "mac/current.json"
    stable = asset_root / "xiaoba-mac.dmg"
    assert immutable.read_bytes() == artifact.read_bytes()
    assert stable.read_bytes() == artifact.read_bytes()
    assert json.loads(receipt.read_text(encoding="utf-8")) == payload
    public = json.loads(current.read_text(encoding="utf-8"))
    assert public == _public(payload)
    assert set(public) == PUBLIC_FIELDS
    assert "team_id" not in public
    assert "cdhash" not in public
    assert "artifact_path" not in public
    assert "notary_submission_id" not in public
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert stat.S_IMODE(current.stat().st_mode) == 0o644
    assert stat.S_IMODE(immutable.stat().st_mode) == 0o644
    assert stat.S_IMODE(stable.stat().st_mode) == 0o644
    assert receipt.stat().st_nlink == 1
    assert current.stat().st_nlink == 1


def test_second_publish_preserves_previous_receipt(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact = tmp_path / "upload-2.dmg"
    second_artifact.write_bytes(b"second-signed-notarized-dmg")
    second_artifact.chmod(0o600)
    second_candidate = tmp_path / "candidate-2.json"
    second = _receipt(second_artifact, asset_root)
    second["source_sha"] = "3" * 40
    second["source_tree"] = "4" * 40
    digest = str(second["artifact_sha256"])
    second["artifact_path"] = str(
        asset_root / "mac/releases" / second["source_sha"] / f"{digest}.dmg"
    )
    second["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{second['source_sha']}/{digest}.dmg"
    )
    second["build"] = "43"
    _write_candidate(second_candidate, second)

    result = _publish(
        second_artifact, second_candidate, asset_root, state_root
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((state_root / "mac-runtime.previous.json").read_text()) == first
    assert json.loads((state_root / "mac-runtime.json").read_text()) == second
    assert json.loads((asset_root / "mac/current.json").read_text()) == _public(second)
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == second_artifact.read_bytes()


def test_first_formal_publish_migrates_an_existing_legacy_stable_dmg(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)
    stable = asset_root / "xiaoba-mac.dmg"
    stable.write_bytes(b"legacy-public-dmg")
    stable.chmod(0o644)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode == 0, result.stderr
    assert stable.read_bytes() == artifact.read_bytes()
    assert json.loads((state_root / "mac-runtime.json").read_text()) == payload
    assert not (asset_root / ".xiaoba-mac.dmg.rollback").exists()


def test_failed_first_formal_publish_restores_legacy_stable_bytes(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    stable = asset_root / "xiaoba-mac.dmg"
    legacy = b"legacy-public-dmg-must-survive"
    stable.write_bytes(legacy)
    stable.chmod(0o644)

    result = _publish(
        artifact,
        candidate,
        asset_root,
        state_root,
        fail_at="before-current",
    )

    assert result.returncode != 0
    assert stable.read_bytes() == legacy
    assert not (state_root / "mac-runtime.json").exists()
    assert not (asset_root / "mac/current.json").exists()
    assert not (asset_root / ".xiaoba-mac.dmg.rollback").exists()


def test_failure_before_current_restores_all_pointers(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    previous_before = (state_root / "mac-runtime.previous.json")
    assert not previous_before.exists()
    receipt_before = (state_root / "mac-runtime.json").read_bytes()
    current_before = (asset_root / "mac/current.json").read_bytes()
    stable_before = (asset_root / "xiaoba-mac.dmg").read_bytes()

    second_artifact = tmp_path / "upload-2.dmg"
    second_artifact.write_bytes(b"candidate-two")
    second_artifact.chmod(0o600)
    second_payload = _receipt(second_artifact, asset_root)
    second_payload["source_sha"] = "3" * 40
    digest = str(second_payload["artifact_sha256"])
    second_payload["artifact_path"] = str(
        asset_root / "mac/releases" / second_payload["source_sha"] / f"{digest}.dmg"
    )
    second_payload["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{second_payload['source_sha']}/{digest}.dmg"
    )
    second_candidate = tmp_path / "candidate-2.json"
    _write_candidate(second_candidate, second_payload)

    result = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
        fail_at="before-current",
    )

    assert result.returncode != 0
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before
    assert (asset_root / "mac/current.json").read_bytes() == current_before
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == stable_before
    assert not (state_root / "mac-runtime.previous.json").exists()
    assert json.loads(receipt_before) == first


def test_failure_after_current_restores_old_current(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    receipt_before = (state_root / "mac-runtime.json").read_bytes()
    current_before = (asset_root / "mac/current.json").read_bytes()
    stable_before = (asset_root / "xiaoba-mac.dmg").read_bytes()

    second_artifact = tmp_path / "upload-2.dmg"
    second_artifact.write_bytes(b"candidate-after-current")
    second_artifact.chmod(0o600)
    second_payload = _receipt(second_artifact, asset_root)
    second_payload["source_sha"] = "3" * 40
    digest = str(second_payload["artifact_sha256"])
    second_payload["artifact_path"] = str(
        asset_root / "mac/releases" / second_payload["source_sha"] / f"{digest}.dmg"
    )
    second_payload["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{second_payload['source_sha']}/{digest}.dmg"
    )
    second_candidate = tmp_path / "candidate-2.json"
    _write_candidate(second_candidate, second_payload)

    result = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
        fail_at="after-current",
    )

    assert result.returncode != 0
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before
    assert (asset_root / "mac/current.json").read_bytes() == current_before
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == stable_before
    assert not (state_root / "mac-runtime.previous.json").exists()


@pytest.mark.parametrize(
    "crash_at",
    (
        "after-journal",
        "after-previous",
        "after-receipt",
        "after-stable",
        "after-current",
    ),
)
def test_hard_crash_at_each_pointer_stage_recovers_the_old_release(
    tmp_path: Path,
    crash_at: str,
) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    receipt_before = (state_root / "mac-runtime.json").read_bytes()
    current_before = (asset_root / "mac/current.json").read_bytes()
    stable_before = (asset_root / "xiaoba-mac.dmg").read_bytes()
    second_artifact, second_candidate, _second = _second_release(tmp_path, asset_root)

    crashed = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
        crash_at=crash_at,
    )

    assert crashed.returncode == 86
    journal = state_root / "mac-release.transaction.json"
    assert journal.exists()
    metadata = journal.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert metadata.st_nlink == 1
    assert metadata.st_size <= 64 * 1024

    recovered = _publisher_maintenance("recover", asset_root, state_root)

    assert recovered.returncode == 0, recovered.stderr
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before
    assert (asset_root / "mac/current.json").read_bytes() == current_before
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == stable_before
    assert not (state_root / "mac-runtime.previous.json").exists()
    assert not journal.exists()
    assert json.loads(receipt_before) == first


def test_hard_crash_after_committed_finalizes_the_new_release(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)

    crashed = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
        crash_at="after-committed",
    )

    assert crashed.returncode == 86
    assert (state_root / "mac-release.transaction.json").exists()
    recovered = _publisher_maintenance("recover", asset_root, state_root)
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads((state_root / "mac-runtime.json").read_text()) == second
    assert json.loads((asset_root / "mac/current.json").read_text()) == _public(second)
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == second_artifact.read_bytes()
    assert not (state_root / "mac-release.transaction.json").exists()


def test_publish_auto_recovers_a_hard_crash_before_starting_the_next_publish(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)
    assert (
        _publish(
            second_artifact,
            second_candidate,
            asset_root,
            state_root,
            crash_at="after-stable",
        ).returncode
        == 86
    )

    retried = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
    )

    assert retried.returncode == 0, retried.stderr
    assert json.loads((state_root / "mac-runtime.json").read_text()) == second
    assert json.loads((asset_root / "mac/current.json").read_text()) == _public(second)
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == second_artifact.read_bytes()
    assert not (state_root / "mac-release.transaction.json").exists()


def test_explicit_rollback_atomically_returns_to_the_previous_release(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)
    assert (
        _publish(second_artifact, second_candidate, asset_root, state_root).returncode
        == 0
    )

    rolled_back = _publisher_maintenance("rollback", asset_root, state_root)

    assert rolled_back.returncode == 0, rolled_back.stderr
    assert json.loads((state_root / "mac-runtime.json").read_text()) == first
    assert json.loads((asset_root / "mac/current.json").read_text()) == _public(first)
    assert Path(str(first["artifact_path"])).read_bytes() == (
        asset_root / "xiaoba-mac.dmg"
    ).read_bytes()
    assert json.loads((state_root / "mac-runtime.previous.json").read_text()) == second
    assert not (state_root / "mac-release.transaction.json").exists()


@pytest.mark.parametrize("damage", ("missing", "tampered"))
def test_rollback_refuses_an_unverifiable_current_immutable_without_pointer_write(
    tmp_path: Path,
    damage: str,
) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)
    assert (
        _publish(second_artifact, second_candidate, asset_root, state_root).returncode
        == 0
    )
    current_immutable = Path(str(second["artifact_path"]))
    if damage == "missing":
        current_immutable.unlink()
    else:
        current_immutable.write_bytes(b"tampered-current-immutable")
        current_immutable.chmod(0o644)
    watched = (
        state_root / "mac-runtime.json",
        state_root / "mac-runtime.previous.json",
        asset_root / "mac/current.json",
        asset_root / "xiaoba-mac.dmg",
    )
    before = {path: path.read_bytes() for path in watched}

    rolled_back = _publisher_maintenance("rollback", asset_root, state_root)

    assert rolled_back.returncode != 0
    assert "dmg" in rolled_back.stderr.lower() or "artifact" in rolled_back.stderr.lower()
    assert {path: path.read_bytes() for path in watched} == before
    assert not (state_root / "mac-release.transaction.json").exists()


def test_publish_high_water_survives_rollback(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)
    assert (
        _publish(second_artifact, second_candidate, asset_root, state_root).returncode
        == 0
    )
    assert _publisher_maintenance("rollback", asset_root, state_root).returncode == 0
    before = {
        "receipt": (state_root / "mac-runtime.json").read_bytes(),
        "previous": (state_root / "mac-runtime.previous.json").read_bytes(),
        "current": (asset_root / "mac/current.json").read_bytes(),
        "stable": (asset_root / "xiaoba-mac.dmg").read_bytes(),
    }
    assert json.loads(before["receipt"]) == first
    assert json.loads(before["previous"]) == second

    reused_artifact, reused_candidate, reused = _second_release(
        tmp_path, asset_root, content=b"different-bytes-for-reused-high-water"
    )
    reused["version"] = str(second["version"])
    reused["build"] = str(second["build"])
    _write_candidate(reused_candidate, reused)
    rejected = _publish(
        reused_artifact, reused_candidate, asset_root, state_root
    )

    assert rejected.returncode != 0
    assert "version" in rejected.stderr.lower() or "build" in rejected.stderr.lower()
    assert (state_root / "mac-runtime.json").read_bytes() == before["receipt"]
    assert (state_root / "mac-runtime.previous.json").read_bytes() == before["previous"]
    assert (asset_root / "mac/current.json").read_bytes() == before["current"]
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == before["stable"]
    assert not (state_root / "mac-release.transaction.json").exists()
    assert not Path(str(reused["artifact_path"])).exists()

    third_artifact, third_candidate, third = _second_release(
        tmp_path, asset_root, content=b"strictly-newer-third-release"
    )
    third["source_sha"] = "5" * 40
    third["source_tree"] = "6" * 40
    third["build"] = "44"
    digest = str(third["artifact_sha256"])
    third["artifact_path"] = str(
        asset_root / "mac/releases" / third["source_sha"] / f"{digest}.dmg"
    )
    third["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{third['source_sha']}/{digest}.dmg"
    )
    _write_candidate(third_candidate, third)

    accepted = _publish(third_artifact, third_candidate, asset_root, state_root)

    assert accepted.returncode == 0, accepted.stderr
    assert json.loads((state_root / "mac-runtime.json").read_text()) == third


@pytest.mark.parametrize(
    "drop_lock_at",
    (
        "rollback-journal",
        "rollback-previous",
        "rollback-receipt",
        "rollback-stable",
        "rollback-current",
    ),
)
def test_rollback_lock_loss_is_resumable_and_restores_pre_rollback_state(
    tmp_path: Path,
    drop_lock_at: str,
) -> None:
    lock_dir, token = _remote_release_lock(tmp_path)
    authority = (lock_dir, token)
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert (
        _publish(
            artifact,
            candidate,
            asset_root,
            state_root,
            release_lock=authority,
        ).returncode
        == 0
    )
    second_artifact, second_candidate, _second = _second_release(tmp_path, asset_root)
    assert (
        _publish(
            second_artifact,
            second_candidate,
            asset_root,
            state_root,
            release_lock=authority,
        ).returncode
        == 0
    )
    watched = (
        state_root / "mac-runtime.json",
        state_root / "mac-runtime.previous.json",
        asset_root / "mac/current.json",
        asset_root / "xiaoba-mac.dmg",
    )
    before = {path: path.read_bytes() for path in watched}

    interrupted = _publisher_maintenance(
        "rollback",
        asset_root,
        state_root,
        release_lock=authority,
        drop_lock_at=drop_lock_at,
    )

    assert interrupted.returncode != 0
    token_file = lock_dir / "token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    recovered = _publisher_maintenance(
        "recover", asset_root, state_root, release_lock=authority
    )
    assert recovered.returncode == 0, recovered.stderr
    assert {path: path.read_bytes() for path in watched} == before
    assert not (state_root / "mac-release.transaction.json").exists()


def test_first_release_hard_crash_restores_a_legacy_stable_download(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    stable = asset_root / "xiaoba-mac.dmg"
    legacy = b"legacy-public-dmg-must-survive-hard-crash"
    stable.write_bytes(legacy)
    stable.chmod(0o644)

    crashed = _publish(
        artifact,
        candidate,
        asset_root,
        state_root,
        crash_at="after-stable",
    )
    assert crashed.returncode == 86

    recovered = _publisher_maintenance("recover", asset_root, state_root)

    assert recovered.returncode == 0, recovered.stderr
    assert stable.read_bytes() == legacy
    assert not (state_root / "mac-runtime.json").exists()
    assert not (asset_root / "mac/current.json").exists()
    assert not (state_root / "mac-release.transaction.json").exists()
    assert not (asset_root / ".xiaoba-mac.dmg.rollback").exists()


def test_unsafe_transaction_journal_blocks_recovery_without_following_symlink(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, _second = _second_release(tmp_path, asset_root)
    assert (
        _publish(
            second_artifact,
            second_candidate,
            asset_root,
            state_root,
            crash_at="after-receipt",
        ).returncode
        == 86
    )
    journal = state_root / "mac-release.transaction.json"
    outside = tmp_path / "outside-journal.json"
    journal.rename(outside)
    journal.symlink_to(outside)

    recovered = _publisher_maintenance("recover", asset_root, state_root)

    assert recovered.returncode != 0
    assert "journal" in recovered.stderr.lower() or "release file" in recovered.stderr.lower()
    assert outside.exists()


def test_wrong_unified_release_token_blocks_before_any_publish_write(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    lock_dir, _token = _remote_release_lock(tmp_path)

    result = _publish(
        artifact,
        candidate,
        asset_root,
        state_root,
        release_lock=(lock_dir, "wrong-token"),
    )

    assert result.returncode != 0
    assert "release lock" in result.stderr.lower()
    assert not (state_root / "mac-release.lock").exists()
    assert not (state_root / "mac-release.transaction.json").exists()
    assert not (state_root / "mac-runtime.json").exists()
    assert not (asset_root / "mac/current.json").exists()


def test_lost_unified_release_lock_stops_writes_and_can_be_recovered(
    tmp_path: Path,
) -> None:
    lock_dir, token = _remote_release_lock(tmp_path)
    authority = (lock_dir, token)
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert (
        _publish(
            artifact,
            candidate,
            asset_root,
            state_root,
            release_lock=authority,
        ).returncode
        == 0
    )
    before_receipt = (state_root / "mac-runtime.json").read_bytes()
    before_current = (asset_root / "mac/current.json").read_bytes()
    before_stable = (asset_root / "xiaoba-mac.dmg").read_bytes()
    second_artifact, second_candidate, _second = _second_release(tmp_path, asset_root)

    lost = _publish(
        second_artifact,
        second_candidate,
        asset_root,
        state_root,
        release_lock=authority,
        drop_lock_at="receipt",
    )

    assert lost.returncode != 0
    assert "release lock" in lost.stderr.lower() or "authority" in lost.stderr.lower()
    journal = state_root / "mac-release.transaction.json"
    assert journal.exists()
    mixed = {
        "receipt": (state_root / "mac-runtime.json").read_bytes(),
        "current": (asset_root / "mac/current.json").read_bytes(),
        "stable": (asset_root / "xiaoba-mac.dmg").read_bytes(),
        "journal": journal.read_bytes(),
    }
    assert mixed["receipt"] == before_receipt
    assert mixed["current"] == before_current
    assert mixed["stable"] == before_stable

    token_file = lock_dir / "token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    recovered = _publisher_maintenance(
        "recover", asset_root, state_root, release_lock=authority
    )

    assert recovered.returncode == 0, recovered.stderr
    assert (state_root / "mac-runtime.json").read_bytes() == before_receipt
    assert (asset_root / "mac/current.json").read_bytes() == before_current
    assert (asset_root / "xiaoba-mac.dmg").read_bytes() == before_stable
    assert not journal.exists()


@pytest.mark.parametrize("tampered", ("receipt", "previous", "current", "stable"))
def test_recovery_refuses_unknown_pointer_state_without_any_write(
    tmp_path: Path,
    tampered: str,
) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, _second = _second_release(tmp_path, asset_root)
    assert (
        _publish(
            second_artifact,
            second_candidate,
            asset_root,
            state_root,
            crash_at="after-stable",
        ).returncode
        == 86
    )
    target = {
        "receipt": state_root / "mac-runtime.json",
        "previous": state_root / "mac-runtime.previous.json",
        "current": asset_root / "mac/current.json",
        "stable": asset_root / "xiaoba-mac.dmg",
    }[tampered]
    target.write_bytes(b"unknown-concurrent-state")
    target.chmod(0o600 if tampered in {"receipt", "previous"} else 0o644)
    watched = (
        state_root / "mac-release.transaction.json",
        state_root / "mac-runtime.json",
        state_root / "mac-runtime.previous.json",
        asset_root / "mac/current.json",
        asset_root / "xiaoba-mac.dmg",
    )
    before = {path: path.read_bytes() if path.exists() else None for path in watched}

    recovered = _publisher_maintenance("recover", asset_root, state_root)

    assert recovered.returncode != 0
    assert "unknown" in recovered.stderr.lower() or "reconcile" in recovered.stderr.lower()
    after = {path: path.read_bytes() if path.exists() else None for path in watched}
    assert after == before


def test_tampered_existing_immutable_artifact_blocks_without_pointer_change(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)
    immutable = Path(str(payload["artifact_path"]))
    immutable.parent.mkdir(parents=True)
    immutable.write_bytes(b"tampered")
    immutable.chmod(0o644)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert not (state_root / "mac-runtime.json").exists()
    assert not (asset_root / "mac/current.json").exists()
    assert immutable.read_bytes() == b"tampered"


def test_new_publish_refuses_to_preserve_a_tampered_previous_release(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    old_immutable = Path(str(first["artifact_path"]))
    old_immutable.chmod(0o600)
    old_immutable.write_bytes(b"tampered-old-release")
    old_immutable.chmod(0o644)
    receipt_before = (state_root / "mac-runtime.json").read_bytes()
    current_before = (asset_root / "mac/current.json").read_bytes()

    second_artifact = tmp_path / "upload-2.dmg"
    second_artifact.write_bytes(b"new-candidate")
    second_artifact.chmod(0o600)
    second = _receipt(second_artifact, asset_root)
    second["source_sha"] = "3" * 40
    second["build"] = "43"
    digest = str(second["artifact_sha256"])
    second["artifact_path"] = str(
        asset_root / "mac/releases" / second["source_sha"] / f"{digest}.dmg"
    )
    second["artifact_url"] = (
        "https://health.executor.life/mac/releases/"
        f"{second['source_sha']}/{digest}.dmg"
    )
    second_candidate = tmp_path / "candidate-2.json"
    _write_candidate(second_candidate, second)

    result = _publish(
        second_artifact, second_candidate, asset_root, state_root
    )

    assert result.returncode != 0
    assert "previous" in result.stderr.lower() or "immutable" in result.stderr.lower()
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before
    assert (asset_root / "mac/current.json").read_bytes() == current_before
    assert not (state_root / "mac-runtime.previous.json").exists()


def test_public_current_with_extra_field_blocks_next_publish(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    current = asset_root / "mac/current.json"
    malformed = _public(first)
    malformed["team_id"] = first["team_id"]
    current.write_text(json.dumps(malformed), encoding="utf-8")
    current.chmod(0o644)
    receipt_before = (state_root / "mac-runtime.json").read_bytes()

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "public" in result.stderr.lower()
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before


def test_public_current_with_missing_field_blocks_next_publish(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    current = asset_root / "mac/current.json"
    malformed = _public(first)
    del malformed["published_at"]
    current.write_text(json.dumps(malformed), encoding="utf-8")
    current.chmod(0o644)
    receipt_before = (state_root / "mac-runtime.json").read_bytes()

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "public" in result.stderr.lower()
    assert (state_root / "mac-runtime.json").read_bytes() == receipt_before


def test_publisher_and_probe_share_one_gibibyte_artifact_limit() -> None:
    producer = PUBLISHER.read_text(encoding="utf-8")
    probe = (ROOT / "scripts/release_production_state.py").read_text(
        encoding="utf-8"
    )

    assert "MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024" in producer
    assert "MAC_MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024" in probe


def test_malformed_or_unverified_receipt_is_rejected(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)
    payload["notary_status"] = "Invalid"
    _write_candidate(candidate, payload)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "notary" in result.stderr.lower()
    assert not (state_root / "mac-runtime.json").exists()


def test_candidate_rejects_a_non_production_artifact_origin(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)
    payload["artifact_url"] = payload["artifact_url"].replace(
        "https://health.executor.life", "https://evil.example"
    )
    _write_candidate(candidate, payload)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "artifact_url" in result.stderr


@pytest.mark.parametrize(
    ("bad_root", "expected_rc", "expected_error"),
    (
        ("/", 78, "frozen"),
        ("/tmp//assets", 1, "canonical non-root absolute path"),
        ("/tmp/./assets", 1, "canonical non-root absolute path"),
        ("/tmp/x/../assets", 1, "canonical non-root absolute path"),
    ),
)
def test_publisher_rejects_noncanonical_release_roots(
    tmp_path: Path,
    bad_root: str,
    expected_rc: int,
    expected_error: str,
) -> None:
    artifact, candidate, _asset_root, state_root, _payload = _prepare(tmp_path)
    env = os.environ.copy()
    env["MAC_RELEASE_TEST_MODE"] = "1"

    result = subprocess.run(
        [
            *_publisher_test_runner(),
            "publish",
            "--artifact",
            str(artifact),
            "--candidate",
            str(candidate),
            "--asset-root",
            bad_root,
            "--state-root",
            str(state_root),
            "--allow-non-root-for-tests",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == expected_rc
    assert expected_error in result.stderr.lower()


@pytest.mark.parametrize(
    ("version", "build"),
    (("1.2.2", "101"), ("1.2.3", "41"), ("1.2.3", "42")),
)
def test_distinct_release_cannot_regress_or_reuse_version_identity(
    tmp_path: Path,
    version: str,
    build: str,
) -> None:
    artifact, candidate, asset_root, state_root, _first = _prepare(tmp_path)
    assert _publish(artifact, candidate, asset_root, state_root).returncode == 0
    second_artifact, second_candidate, second = _second_release(tmp_path, asset_root)
    second["version"] = version
    second["build"] = build
    _write_candidate(second_candidate, second)

    result = _publish(second_artifact, second_candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "version" in result.stderr.lower() or "build" in result.stderr.lower()


def test_symlink_pointer_is_rejected_without_following_it(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("do-not-touch", encoding="utf-8")
    mac_root = asset_root / "mac"
    mac_root.mkdir(mode=0o755)
    (mac_root / "current.json").symlink_to(outside)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert outside.read_text(encoding="utf-8") == "do-not-touch"
    assert not (state_root / "mac-runtime.json").exists()


def test_symlink_staged_artifact_is_rejected(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    real_artifact = tmp_path / "real.dmg"
    artifact.rename(real_artifact)
    artifact.symlink_to(real_artifact)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "staged" in result.stderr.lower() or "symlink" in result.stderr.lower()
    assert not (state_root / "mac-runtime.json").exists()


def test_symlink_release_root_is_rejected(tmp_path: Path) -> None:
    artifact, candidate, asset_root, state_root, payload = _prepare(tmp_path)
    real_asset_root = tmp_path / "real-assets"
    asset_root.rename(real_asset_root)
    asset_root.symlink_to(real_asset_root, target_is_directory=True)
    payload["artifact_path"] = str(
        real_asset_root
        / "mac/releases"
        / payload["source_sha"]
        / f"{payload['artifact_sha256']}.dmg"
    )
    _write_candidate(candidate, payload)

    result = _publish(artifact, candidate, asset_root, state_root)

    assert result.returncode != 0
    assert "directory" in result.stderr.lower() or "symlink" in result.stderr.lower()
    assert not (state_root / "mac-runtime.json").exists()


def test_publisher_rejects_non_root_bypass_without_explicit_test_mode(
    tmp_path: Path,
) -> None:
    artifact, candidate, asset_root, state_root, _payload = _prepare(tmp_path)
    env = os.environ.copy()
    env.pop("MAC_RELEASE_TEST_MODE", None)

    result = subprocess.run(
        [
            *_publisher_test_runner(),
            "publish",
            "--artifact",
            str(artifact),
            "--candidate",
            str(candidate),
            "--asset-root",
            str(asset_root),
            "--state-root",
            str(state_root),
            "--allow-non-root-for-tests",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "frozen" in result.stderr.lower()


def test_publisher_test_flags_cannot_mutate_fixed_production_roots() -> None:
    env = {**os.environ, "MAC_RELEASE_TEST_MODE": "1"}
    result = subprocess.run(
        [
            *_publisher_test_runner(),
            "recover",
            "--asset-root",
            "/opt/health-app-shared/assets",
            "--state-root",
            "/var/lib/health-app/release-state",
            "--allow-non-root-for-tests",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "frozen" in result.stderr.lower()


def test_publisher_ignores_poisoned_tmpdir_when_classifying_test_roots() -> None:
    before = (ROOT / "package.json").read_bytes()
    env = {
        **os.environ,
        "MAC_RELEASE_TEST_MODE": "1",
        "TMPDIR": str(ROOT),
    }
    result = subprocess.run(
        [
            *_publisher_test_runner(),
            "recover",
            "--asset-root",
            str(ROOT),
            "--state-root",
            str(ROOT),
            "--allow-non-root-for-tests",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "frozen" in result.stderr.lower()
    assert (ROOT / "package.json").read_bytes() == before


def test_release_upload_uses_immutable_path_and_remote_transaction_helper() -> None:
    source = RELEASE_DMG.read_text(encoding="utf-8")

    assert "mac/releases/${SOURCE_SHA}/${ARTIFACT_SHA256}.dmg" in source
    assert "mac_release_publish.py" in source
    assert "mac-runtime.json" in (
        PUBLISHER.read_text(encoding="utf-8") if PUBLISHER.exists() else ""
    )
    assert "${PUBLIC_BASE_URL}/xiaoba-mac.dmg" in source
    assert "scp -q \"${DMG_PATH}\" \"${SERVER}:${ASSET_ROOT}/xiaoba-mac.dmg\"" not in source
