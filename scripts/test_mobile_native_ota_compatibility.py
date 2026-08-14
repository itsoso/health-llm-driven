from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_mobile_native_ota_compatibility.py"
NOW = "2026-08-12T12:00:00Z"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return _git(repo, "rev-parse", "HEAD")


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "native-gate@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Native Gate"], cwd=repo, check=True
    )
    (repo / "mobile").mkdir()
    (repo / "mobile/app.json").write_text(
        json.dumps({"expo": {"version": "1.3.3", "runtimeVersion": "1.3.3"}}),
        encoding="utf-8",
    )
    (repo / "mobile/package.json").write_text(
        json.dumps({"name": "fixture", "scripts": {"test": "true"}}),
        encoding="utf-8",
    )
    (repo / "mobile/app.tsx").write_text("export const version = 1;\n")
    return repo, _commit(repo, "native build source")


def _build(
    sha: str,
    *,
    build_id: str = "11111111-1111-4111-8111-111111111111",
    fingerprint: str = "a" * 40,
    expiration: str = "2026-09-12T12:00:00Z",
) -> dict[str, object]:
    return {
        "id": build_id,
        "status": "FINISHED",
        "platform": "IOS",
        "distribution": "STORE",
        "buildProfile": "production",
        "channel": "production",
        "runtimeVersion": "1.3.3",
        "gitCommitHash": sha,
        "fingerprint": {"hash": fingerprint},
        "expirationDate": expiration,
        "isForIosSimulator": False,
    }


def _verify(
    repo: Path,
    target: str,
    builds: list[dict[str, object]],
) -> subprocess.CompletedProcess[str]:
    builds_path = repo.parent / "builds.json"
    builds_path.write_text(json.dumps(builds), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "verify",
            "--repo-root",
            str(repo),
            "--target-sha",
            target,
            "--runtime-version",
            "1.3.3",
            "--channel",
            "production",
            "--builds-json",
            str(builds_path),
            "--now",
            NOW,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_hidden_native_change_since_an_eligible_build_blocks_ota(tmp_path: Path) -> None:
    repo, build_sha = _repository(tmp_path)
    plugin = repo / "mobile/plugins/native-config.js"
    plugin.parent.mkdir()
    plugin.write_text("module.exports = {};\n", encoding="utf-8")
    target = _commit(repo, "native plugin change")

    result = _verify(repo, target, [_build(build_sha)])

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "mobile/plugins/native-config.js" in combined
    assert "new runtime" in combined.lower() or "native build" in combined.lower()


def test_pure_js_change_is_compatible_with_one_native_cohort(tmp_path: Path) -> None:
    repo, build_sha = _repository(tmp_path)
    (repo / "mobile/app.tsx").write_text("export const version = 2;\n")
    target = _commit(repo, "pure js change")

    result = _verify(repo, target, [_build(build_sha)])

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["eligible_build_count"] == 1
    assert payload["expired_artifact_count"] == 0
    assert payload["cohort"][0]["git_commit_hash"] == build_sha
    assert payload["target_sha"] == target


def test_expired_eas_artifact_does_not_exclude_an_installed_store_build(
    tmp_path: Path,
) -> None:
    repo, expired_sha = _repository(tmp_path)
    plugin = repo / "mobile/plugins/native-config.js"
    plugin.parent.mkdir()
    plugin.write_text("module.exports = {};\n", encoding="utf-8")
    eligible_sha = _commit(repo, "new native binary")
    (repo / "mobile/app.tsx").write_text("export const version = 2;\n")
    target = _commit(repo, "pure js after native binary")

    result = _verify(
        repo,
        target,
        [
            _build(
                expired_sha,
                build_id="22222222-2222-4222-8222-222222222222",
                fingerprint="b" * 40,
                expiration="2026-08-11T12:00:00Z",
            ),
            _build(eligible_sha),
        ],
    )

    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert "native-sensitive" in output
    assert expired_sha[:12] in output


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo", "oversized"])
def test_native_cohort_reader_rejects_unsafe_or_unbounded_input_without_blocking(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    repo, build_sha = _repository(tmp_path)
    target = repo.parent / "unsafe-builds.json"
    if unsafe_kind == "symlink":
        source = repo.parent / "real-builds.json"
        source.write_text(json.dumps([_build(build_sha)]), encoding="utf-8")
        target.symlink_to(source)
    elif unsafe_kind == "fifo":
        os.mkfifo(target, mode=0o600)
    else:
        target.write_bytes(b"[" + b" " * (16 * 1024 * 1024) + b"]")

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "verify",
            "--repo-root",
            str(repo),
            "--target-sha",
            build_sha,
            "--runtime-version",
            "1.3.3",
            "--channel",
            "production",
            "--builds-json",
            str(target),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=3,
    )

    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert "bounded regular file" in output or "symbolic link" in output


@pytest.mark.parametrize(
    "missing_field",
    ["gitCommitHash", "runtimeVersion", "fingerprint"],
)
def test_active_build_missing_required_native_identity_is_rejected(
    tmp_path: Path, missing_field: str
) -> None:
    repo, build_sha = _repository(tmp_path)
    build = _build(build_sha)
    build.pop(missing_field)

    result = _verify(repo, build_sha, [build])

    assert result.returncode != 0
    assert missing_field.lower() in (result.stdout + result.stderr).lower()


def test_mixed_fingerprints_in_one_runtime_are_ambiguous(tmp_path: Path) -> None:
    repo, build_sha = _repository(tmp_path)
    result = _verify(
        repo,
        build_sha,
        [
            _build(build_sha),
            _build(
                build_sha,
                build_id="22222222-2222-4222-8222-222222222222",
                fingerprint="b" * 40,
            ),
        ],
    )

    assert result.returncode != 0
    assert "fingerprint" in (result.stdout + result.stderr).lower()
    assert "ambiguous" in (result.stdout + result.stderr).lower()


def test_append_page_rejects_duplicate_build_identity_across_pages(
    tmp_path: Path,
) -> None:
    repo, build_sha = _repository(tmp_path)
    aggregate = tmp_path / "aggregate.json"
    aggregate.write_text("[]\n", encoding="utf-8")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps([_build(build_sha)]), encoding="utf-8")
    second.write_text(json.dumps([_build(build_sha)]), encoding="utf-8")

    command = [
        sys.executable,
        str(VERIFY),
        "append-page",
        "--aggregate-json",
        str(aggregate),
        "--runtime-version",
        "1.3.3",
        "--channel",
        "production",
    ]
    first_result = subprocess.run(
        [*command, "--page-json", str(first)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    second_result = subprocess.run(
        [*command, "--page-json", str(second)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first_result.returncode == 0, first_result.stderr
    assert first_result.stdout.strip() == "1"
    assert second_result.returncode != 0
    assert "duplicate" in (second_result.stdout + second_result.stderr).lower()
