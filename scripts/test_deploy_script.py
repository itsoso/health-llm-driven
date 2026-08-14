import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy.sh"
# Production argv are intentionally frozen before deploy.sh can be sourced.
# Legacy function-level fault-injection tests extract only the unreachable
# implementation; this test-only extraction creates no runtime bypass.
DEPLOY_SOURCE_FOR_TESTS = (
    "set -e\n"
    ': "${DEPLOY_ENV_FILE:?tests must provide an isolated DEPLOY_ENV_FILE}"\n'
    f"test \"$DEPLOY_ENV_FILE\" != {str(ROOT / '.env')!r}\n"
    "set -- --status\n"
    f"eval \"$(/usr/bin/sed -n '/^# BEGIN UNREACHABLE LEGACY DEPLOY IMPLEMENTATION$/,/^# END UNREACHABLE LEGACY DEPLOY IMPLEMENTATION$/p' "
    f"{DEPLOY_SCRIPT!s} | /usr/bin/sed "
    f"'s|${{BASH_SOURCE\\[0\\]}}|{DEPLOY_SCRIPT!s}|g')\"\n"
    "SERVER=fake-server.invalid\n"
    "ssh() { return 97; }\nscp() { return 97; }\nrsync() { return 97; }\n"
    "set --"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o100)


def _write_root_owned_stat_shim(path: Path) -> None:
    """Write the GNU-stat subset used by remote release-state harnesses."""
    _write_executable(
        path,
        """#!/usr/bin/env python3
import os
import sys

if len(sys.argv) != 4 or sys.argv[1] != "-c":
    raise SystemExit(64)

metadata = os.stat(sys.argv[3])
if sys.argv[2] == "%h":
    print(metadata.st_nlink)
elif sys.argv[2] == "%U:%G:%a":
    print(f"root:root:{metadata.st_mode & 0o7777:o}")
else:
    raise SystemExit(64)
""",
    )


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--status",),
        ("--logs",),
        ("--inspect-release-lock",),
        ("--backend",),
        ("--help", "--status"),
    ),
)
def test_sourcing_deploy_cli_is_inert_and_caller_continues(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    after = tmp_path / "after"
    marker = tmp_path / "external-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "grep", "git", "python3", "ssh"):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
        )
    quoted = " ".join(subprocess.list2cmdline([part]) for part in arguments)
    harness = (
        f"set -- {quoted}\n" if quoted else "set --\n"
    ) + f"source {DEPLOY_SCRIPT!s}\nprintf AFTER > {after!s}\n"

    completed = subprocess.run(
        ["/bin/bash", "-c", harness],
        cwd=tmp_path,
        env={
            "PATH": str(fake_bin),
            "DEPLOY_ENV_FILE": str(tmp_path / "must-not-read.env"),
            "BASH_FUNC_ssh%%": f"() {{ printf called >> {marker!s}; }}",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert after.read_text(encoding="utf-8") == "AFTER"
    assert not marker.exists()


@pytest.mark.parametrize("help_flag", ("-h", "--help"))
def test_sourcing_deploy_exact_help_is_inert_and_returns_to_caller(
    tmp_path: Path,
    help_flag: str,
) -> None:
    after = tmp_path / "after"
    completed = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"set -- {help_flag}; source {DEPLOY_SCRIPT!s}; printf AFTER > {after!s}",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert after.read_text(encoding="utf-8") == "AFTER"


def test_hostile_source_cannot_reach_deploy_legacy_even_if_builtins_are_shadowed(
    tmp_path: Path,
) -> None:
    tool_marker = tmp_path / "external-called"
    function_marker = tmp_path / "legacy-function-loaded"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("dirname", "grep", "cut", "git", "python3", "ssh"):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\nprintf called >> {tool_marker!s}\nexit 91\n",
        )
    harness = f"""
set -- --status
exit() {{ return 0; }}
builtin() {{ return 0; }}
printf() {{ return 0; }}
set() {{ return 0; }}
source {DEPLOY_SCRIPT!s}
if declare -F deploy_backend >/dev/null; then
  : > {function_marker!s}
fi
"""
    completed = subprocess.run(
        ["/bin/bash", "-c", harness],
        cwd=tmp_path,
        env={
            "PATH": str(fake_bin),
            "DEPLOY_ENV_FILE": str(tmp_path / "must-not-read.env"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert not tool_marker.exists()
    assert not function_marker.exists()


def test_release_step_proofs_default_to_shadow_in_private_server_cache():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'RELEASE_STEP_PROOF_MODE="${RELEASE_STEP_PROOF_MODE:-shadow}"' in script
    assert (
        'REMOTE_RELEASE_PROOF_ROOT="${REMOTE_RELEASE_PROOF_ROOT:-'
        '/var/cache/health-app/release-proofs}"'
    ) in script
    assert 'off|shadow|on' in script


def test_production_remote_release_lock_path_cannot_be_overridden_by_ambient_env():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert (
        'REMOTE_RELEASE_LOCK_DIR="/var/lib/health-app/release-state/deploy.lock"'
        in script
    )
    assert 'REMOTE_RELEASE_LOCK_DIR="${REMOTE_RELEASE_LOCK_DIR:-' not in script


def test_remote_release_lock_uses_a_256_bit_csprng_token() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    acquire = script[
        script.index("acquire_remote_release_lock() {") : script.index(
            "remote_release_lock_command() {"
        )
    ]

    assert "secrets.token_hex(32)" in acquire
    assert '${RANDOM:-0}' not in acquire
    assert '$$-' not in acquire


def test_remote_release_coordinator_contract_has_explicit_v2_identity() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    contract = script[
        script.index("remote_release_lock_command() {") : script.index(
            "show_remote_release_lock_handoff() {"
        )
    ]

    assert '"surface"' in contract
    assert '"operation"' in contract
    assert '"channel"' in contract
    assert '"transaction_id"' in contract
    assert '"baseline_digest"' in contract
    assert '"request_digest"' in contract
    assert '"schema": "2"' in contract
    assert 'value == "production"' in contract
    assert 'operation == "bind"' in contract


def test_deploy_help_does_not_expose_release_coordinator_authority(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, result.stderr
    assert "Production repository entrypoints are frozen" in result.stdout
    assert "--release-coordinator" not in result.stdout


def test_remote_release_coordinator_rejects_nonproduction_channel_before_ssh(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    ssh_log = tmp_path / "ssh.log"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={tmp_path / 'deploy.lock'!s}
ssh() {{ printf 'called\n' >> {ssh_log!s}; return 99; }}
REVA_RELEASE_COORDINATOR_SURFACE=mobile
REVA_RELEASE_COORDINATOR_OPERATION=forward
REVA_RELEASE_COORDINATOR_CHANNEL=preview
REVA_RELEASE_COORDINATOR_TRANSACTION={'b' * 32}
REVA_RELEASE_COORDINATOR_REQUEST_DIGEST={'c' * 64}
declare -F begin_remote_release_coordinator >/dev/null
set +e
begin_remote_release_coordinator
rc=$?
set -e
test "$rc" -eq 70
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not ssh_log.exists()
    assert "command not found" not in result.stderr
    assert "固定 production 契约" in result.stdout


@pytest.mark.parametrize("poison", ("wrong-origin", "url-rewrite", "replace-ref"))
def test_release_coordinator_rejects_noncanonical_origin_before_network(
    tmp_path: Path,
    poison: str,
) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repository,
        check=True,
    )
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
    origin = (
        "https://example.invalid/poisoned.git"
        if poison == "wrong-origin"
        else "https://github.com/itsoso/health-llm-driven.git"
    )
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=repository, check=True)
    if poison == "url-rewrite":
        subprocess.run(
            [
                "git",
                "config",
                "url.https://example.invalid/.insteadOf",
                "https://github.com/itsoso/",
            ],
            cwd=repository,
            check=True,
        )
    if poison == "replace-ref":
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "rev-parse", f"{head}^{{tree}}"], cwd=repository, text=True
        ).strip()
        replacement = subprocess.check_output(
            ["git", "commit-tree", tree, "-m", "replacement"],
            cwd=repository,
            text=True,
        ).strip()
        subprocess.run(
            ["git", "replace", head, replacement], cwd=repository, check=True
        )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    network_log = tmp_path / "network.log"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
trusted_release_network_git() {{
    printf 'network\n' >> {network_log!s}
    return 99
}}
set +e
verify_release_coordinator_source
rc=$?
set -e
test "$rc" -eq 70
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not network_log.exists()


def test_remote_release_coordinator_begin_bind_mutate_finish_exact_v2_lifecycle(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    lock_dir = tmp_path / "deploy.lock"
    transaction = "a" * 32
    request_digest = "b" * 64
    baseline_digest = "c" * 64
    terminal_digest = "d" * 64

    common = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
ssh() {{ shift; "$@"; }}
REVA_RELEASE_COORDINATOR_SURFACE=mobile
REVA_RELEASE_COORDINATOR_OPERATION=forward
REVA_RELEASE_COORDINATOR_CHANNEL=production
REVA_RELEASE_COORDINATOR_TRANSACTION={transaction}
REVA_RELEASE_COORDINATOR_REQUEST_DIGEST={request_digest}
"""
    clean_env = {
        key: value
        for key, value in {**os.environ, "DEPLOY_ENV_FILE": str(env_file)}.items()
        if not key.startswith("REVA_RELEASE_COORDINATOR_")
        and key
        not in {
            "REVA_REMOTE_RELEASE_LOCK_ADOPT",
            "REVA_REMOTE_RELEASE_LOCK_ALLOW_ALLOCATING_ADOPT",
            "REVA_REMOTE_RELEASE_LOCK_TOKEN",
        }
    }
    begun = subprocess.run(
        [
            "bash",
            "-c",
            common
            + "\nverify_release_coordinator_source() {\n"
            + "  REVA_RELEASE_COORDINATOR_SOURCE_SHA=$(git -C \"$SCRIPT_DIR\" rev-parse HEAD)\n"
            + "  REVA_RELEASE_COORDINATOR_SOURCE_TREE=$(git -C \"$SCRIPT_DIR\" rev-parse HEAD^{tree})\n"
            + "  export REVA_RELEASE_COORDINATOR_SOURCE_SHA REVA_RELEASE_COORDINATOR_SOURCE_TREE\n"
            + "}\nbegin_remote_release_coordinator\n",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=clean_env,
    )
    assert begun.returncode == 0, (begun.stdout, begun.stderr)
    proof = re.search(
        r"REVA_RELEASE_COORDINATOR_BEGIN token=([0-9a-f]{64}) "
        r"stage=(/tmp/health-app-backup-preflight-[0-9a-f]{64}) "
        r"source_sha=([0-9a-f]{40}) source_tree=([0-9a-f]{40}) "
        r"surface=mobile operation=forward channel=production "
        rf"transaction_id=({transaction}) request_digest=({request_digest})",
        begun.stdout,
    )
    assert proof is not None, begun.stdout
    token, stage, source_sha, source_tree, _, _ = proof.groups()
    expected = {
        "schema": "2",
        "token": token,
        "label": "coordinator:mobile:forward",
        "stage": stage,
        "source_sha": source_sha,
        "source_tree": source_tree,
        "state": "allocating",
        "surface": "mobile",
        "operation": "forward",
        "channel": "production",
        "transaction_id": transaction,
        "baseline_digest": "-",
        "request_digest": request_digest,
        "terminal_digest": "-",
    }
    assert set(path.name for path in lock_dir.iterdir()) == {
        *expected,
        "started_at",
    }
    assert lock_dir.stat().st_mode & 0o7777 == 0o700
    for name, value in expected.items():
        path = lock_dir / name
        assert path.read_text(encoding="ascii") == value + "\n"
        assert path.stat().st_mode & 0o7777 == 0o600

    continuation = common + f"""
REVA_REMOTE_RELEASE_LOCK_TOKEN={token}
REVA_RELEASE_COORDINATOR_STAGE={stage}
REVA_RELEASE_COORDINATOR_SOURCE_SHA={source_sha}
REVA_RELEASE_COORDINATOR_SOURCE_TREE={source_tree}
REVA_RELEASE_COORDINATOR_BASELINE_DIGEST={baseline_digest}
"""
    bound = subprocess.run(
        ["bash", "-c", continuation + "\nbind_remote_release_coordinator\n"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=clean_env,
    )
    assert bound.returncode == 0, (bound.stdout, bound.stderr)
    assert "REMOTE_RELEASE_LOCK_BOUND state=sealed" in bound.stdout
    assert (lock_dir / "baseline_digest").read_text(encoding="ascii") == (
        baseline_digest + "\n"
    )
    assert (lock_dir / "state").read_text(encoding="ascii") == "sealed\n"

    mutated = subprocess.run(
        ["bash", "-c", continuation + "\nmutate_remote_release_coordinator\n"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=clean_env,
    )
    assert mutated.returncode == 0, (mutated.stdout, mutated.stderr)
    assert (lock_dir / "state").read_text(encoding="ascii") == "mutating\n"

    premature = subprocess.run(
        ["bash", "-c", continuation + "\nfinish_remote_release_coordinator\n"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=clean_env,
    )
    assert premature.returncode == 70, (premature.stdout, premature.stderr)
    assert lock_dir.exists()

    finished = subprocess.run(
        [
            "bash",
            "-c",
            continuation
            + f"\nREVA_RELEASE_COORDINATOR_TERMINAL_DIGEST={terminal_digest}"
            + "\nfinish_remote_release_coordinator\n",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=clean_env,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "REVA_RELEASE_COORDINATOR_FINISHED" in finished.stdout
    assert not lock_dir.exists()


def test_deploy_help_does_not_expose_release_lock_handoff_entrypoint(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, result.stderr
    assert "release-lock inspection" in result.stdout
    assert "--inspect-release-lock" not in result.stdout


def test_expected_server_surface_cas_runs_inside_remote_lease_before_other_work():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    acquired = main_body.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    asserted = main_body.index("assert_remote_release_lock", acquired)
    cas = main_body.index("verify_expected_server_surfaces_under_lock", asserted)
    ota_drift = main_body.index("confirm_ota_drift", cas)
    execute = main_body.index("# 执行对应操作", ota_drift)

    assert acquired < asserted < cas < ota_drift < execute


def test_mac_route_bootstrap_is_an_explicit_non_daily_deploy_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "--bootstrap-mac-routes" in script
    assert 'MAC_ROUTE_ACTION="apply"' in script
    assert 'MAC_ROUTE_ACTION="rollback"' in script
    assert 'scripts/mac-release-nginx-bootstrap.sh" "${MAC_ROUTE_ACTION}"' in script
    all_mode = script[script.index('"all")') : script.index('"frontend")')]
    assert "bootstrap_mac_release_routes" not in all_mode


def test_mac_route_bootstrap_rechecks_exact_remote_main_under_server_lease():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    body = script[
        script.index("bootstrap_mac_release_routes() {") : script.index(
            "\n}\n\nverify_mac_route_release_source()",
            script.index("bootstrap_mac_release_routes() {"),
        )
    ]

    lease_assert = body.index("assert_remote_release_lock")
    source_recheck = body.index("verify_mac_route_release_source", lease_assert)
    snapshot = body.index("stage_mac_route_release_artifacts", source_recheck)
    mutation = body.index("REVA_MAC_BOOTSTRAP_ENTRYPOINT=deploy.sh", snapshot)

    assert lease_assert < source_recheck < snapshot < mutation


def test_mac_route_wrapper_treats_nonterminal_output_as_ambiguous_and_retains_lease():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    body = script[
        script.index("bootstrap_mac_release_routes() {") : script.index(
            "\n}\n\nverify_mac_route_release_source()",
            script.index("bootstrap_mac_release_routes() {"),
        )
    ]

    assert "_REMOTE_RELEASE_LOCK_DELEGATED=1" in body
    assert "MAC_NGINX_BOOTSTRAP_OK outcome=" in body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body
    assert "Mac nginx route outcome is ambiguous" in body
    terminal = body.index("MAC_NGINX_BOOTSTRAP_OK outcome=")
    assert body.index("assert_remote_release_lock", terminal) < body.index(
        "_REMOTE_RELEASE_LOCK_DELEGATED=0", terminal
    )


def test_mac_route_bootstrap_help_documents_apply_and_explicit_rollback(tmp_path: Path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@39.98.206.178\n"
        "DEPLOY_PATH=/opt/health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, result.stderr
    assert "Production repository entrypoints are frozen" in result.stdout
    assert "--bootstrap-mac-routes" not in result.stdout


def test_mac_release_mutations_have_supported_deploy_entrypoints(tmp_path: Path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@39.98.206.178\n"
        "DEPLOY_PATH=/opt/health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, result.stderr
    assert "Production repository entrypoints are frozen" in result.stdout
    assert "--publish-mac" not in result.stdout
    assert "--recover-mac-release" not in result.stdout
    assert "--rollback-mac-release" not in result.stdout


def test_deploy_hard_blocks_mac_mutations_before_the_release_driver():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "Mac 自动发布已冻结" in script
    assert "Mac 自动恢复已冻结" in script
    assert "Mac 自动回滚已冻结" in script
    assert 'apps/mac/scripts/release-dmg.sh" publish' not in script
    assert "acquire_release_lock \"deploy:mac-publish\"" not in script
    assert "acquire_remote_release_lock \"deploy:mac-publish\"" not in script


def test_deploy_hard_blocks_mac_route_bootstrap_before_lock_or_network():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    parse_end = script.index('if [[ "$DEPLOY_MODE" == "release-lock-inspect" ]]')
    route_gate = script.index("Mac 下载路由变更已冻结")

    assert route_gate < parse_end


@pytest.mark.parametrize(
    "arguments",
    (
        ("--publish-mac", "--version", "1.2.3", "--build", "42"),
        ("--recover-mac-release",),
        ("--rollback-mac-release",),
    ),
)
def test_mac_deploy_modes_exit_at_manual_gate_before_external_action(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@39.98.206.178\nDEPLOY_PATH=/opt/health-app\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), *arguments],
        cwd=ROOT,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 78
    assert "Gate" in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--all",),
        ("--frontend",),
        ("--backend",),
        ("--env",),
        ("--activate-health-evidence",),
        ("--reset-app-store-review",),
        ("--restart",),
        ("--push",),
        ("--publish-mac", "--version", "1.2.3", "--build", "42"),
        ("--recover-mac-release",),
        ("--rollback-mac-release",),
        ("--bootstrap-mac-routes",),
        ("--release-coordinator-begin",),
        ("--release-coordinator-bind",),
        ("--release-coordinator-mutate",),
        ("--release-coordinator-finish",),
        ("--release-coordinator-abort",),
        ("--release-coordinator-recover",),
        ("--status",),
        ("--logs",),
        ("--inspect-release-lock",),
        ("--help", "--status"),
    ),
)
def test_production_deploy_freeze_precedes_top_level_tools_and_env_read(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-called"
    for name in ("dirname", "grep", "cut", "date", "pwd", "python3", "git", "ssh"):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\nprintf '%s' {name!r} >> {marker!s}\nexit 97\n",
        )
    completed = subprocess.run(
        ["/bin/bash", str(DEPLOY_SCRIPT), *arguments],
        cwd=tmp_path,
        env={
            "PATH": str(fake_bin),
            "DEPLOY_ENV_FILE": str(tmp_path / "must-not-be-read.env"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78, completed.stdout + completed.stderr
    assert "Gate" in completed.stdout + completed.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "relative_path",
    (
        "deploy-remote.sh",
        "deploy_to_server.sh",
        "packages/mini-program/build-on-server.sh",
        "deploy_production.sh",
        "scripts/mobile-local-archive.sh",
        ".claude/skills/mobile-testflight-release/scripts/native-archive-asc.sh",
    ),
)
def test_legacy_direct_production_writers_are_frozen_before_tools(
    tmp_path: Path,
    relative_path: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-called"
    for name in (
        "git",
        "ssh",
        "scp",
        "rsync",
        "dirname",
        "rm",
        "npm",
        "python3",
        "xcodebuild",
        "xcrun",
        "cat",
    ):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 97\n",
        )
    result = subprocess.run(
        ["/bin/bash", str(ROOT / relative_path)],
        cwd=tmp_path,
        env={"PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78, result.stdout + result.stderr
    assert "manual Gate" in result.stderr
    assert not marker.exists()


def test_deploy_exact_help_is_static_before_env_paths_functions_or_tools(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-called"
    for name in ("dirname", "grep", "cut", "date", "pwd", "python3", "git", "ssh"):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 97\n",
        )

    result = subprocess.run(
        ["/bin/bash", str(DEPLOY_SCRIPT), "--help"],
        cwd=tmp_path,
        env={
            "PATH": str(fake_bin),
            "DEPLOY_ENV_FILE": str(env_file),
            "BASH_FUNC_ssh%%": f"() {{ printf called >> {marker!s}; }}",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        "Usage: ./deploy.sh -h|--help\n\n"
        "Production repository entrypoints are frozen (exit 78).\n"
        "Status, logs, release-lock inspection, deploy, restart, rollback, and publish "
        "require an external trusted Gate.\n"
    )
    assert result.stderr == ""
    assert "fake-server" not in result.stdout
    assert str(env_file) not in result.stdout
    assert not marker.exists()


def _make_mac_route_source_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "route-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Route Test"], cwd=repository, check=True
    )
    for relative, content in (
        ("scripts/mac-release-nginx-bootstrap.sh", "#!/bin/sh\n"),
        ("scripts/mac_release_nginx_bootstrap.py", "# helper\n"),
        ("infra/nginx/mac-release-routes.conf", "# snippet\n"),
    ):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "route source"], cwd=repository, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repository, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=repository, check=True)
    return repository, remote


def _run_mac_route_source_check(repository: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "route-deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@39.98.206.178\n"
        "DEPLOY_PATH=/opt/health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
verify_mac_route_release_source
"""
    return subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )


@pytest.mark.parametrize(
    "dirty_path",
    [
        "scripts/mac-release-nginx-bootstrap.sh",
        "scripts/mac_release_nginx_bootstrap.py",
        "infra/nginx/mac-release-routes.conf",
    ],
)
def test_mac_route_source_rejects_dirty_operator_bytes(
    tmp_path: Path, dirty_path: str
) -> None:
    repository, _ = _make_mac_route_source_repo(tmp_path)
    with (repository / dirty_path).open("a", encoding="utf-8") as handle:
        handle.write("dirty\n")

    result = _run_mac_route_source_check(repository, tmp_path)

    assert result.returncode != 0
    assert "完全干净" in result.stdout


def test_mac_route_source_rejects_remote_main_drift(tmp_path: Path) -> None:
    repository, remote = _make_mac_route_source_repo(tmp_path)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=other, check=True)
    subprocess.run(
        ["git", "config", "user.email", "route-test@example.invalid"],
        cwd=other,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Route Test"], cwd=other, check=True)
    (other / "remote-change").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "remote-change"], cwd=other, check=True)
    subprocess.run(["git", "commit", "-qm", "advance remote"], cwd=other, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=other, check=True)

    result = _run_mac_route_source_check(repository, tmp_path)

    assert result.returncode != 0
    assert "exact remote main" in result.stdout


def test_mac_route_recovery_on_main_b_executes_exact_sealed_source_a(
    tmp_path: Path,
) -> None:
    repository, _ = _make_mac_route_source_repo(tmp_path)
    wrapper = repository / "scripts/mac-release-nginx-bootstrap.sh"
    wrapper.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "printf 'A\\n' >> \"$MAC_ROUTE_VERSION_LOG\"\n"
        "printf 'MAC_NGINX_BOOTSTRAP_OK outcome=recovered-applied\\n'\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "source A"], cwd=repository, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repository, check=True)
    source_a = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    tree_a = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True
    ).strip()

    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    for relative in (
        "scripts/mac-release-nginx-bootstrap.sh",
        "scripts/mac_release_nginx_bootstrap.py",
        "infra/nginx/mac-release-routes.conf",
    ):
        target = stage / Path(relative).name
        target.write_bytes(
            subprocess.check_output(
                ["git", "show", f"{source_a}:{relative}"], cwd=repository
            )
        )
        target.chmod(0o700 if relative.endswith(".sh") else 0o600)
    token = "mac-route-owner"
    source_receipt = stage / "mac-routes.source"
    source_receipt.write_text(
        f"schema=1\ntoken={token}\nsource_sha={source_a}\nsource_tree={tree_a}\n",
        encoding="ascii",
    )
    source_receipt.chmod(0o400)
    manifest = stage / "mac-routes.sha256"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256((stage / name).read_bytes()).hexdigest()}  {name}\n"
            for name in (
                "mac-release-nginx-bootstrap.sh",
                "mac_release_nginx_bootstrap.py",
                "mac-release-routes.conf",
                "mac-routes.source",
            )
        ),
        encoding="ascii",
    )
    manifest.chmod(0o400)

    # main advances to B after A has crossed the mutation boundary.
    wrapper.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "printf 'B\\n' >> \"$MAC_ROUTE_VERSION_LOG\"\n"
        "printf 'MAC_NGINX_BOOTSTRAP_OK outcome=applied\\n'\n",
        encoding="utf-8",
    )
    (repository / "scripts/mac_release_nginx_bootstrap.py").write_text(
        "# helper B\n", encoding="utf-8"
    )
    (repository / "infra/nginx/mac-release-routes.conf").write_text(
        "# snippet B\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "source B"], cwd=repository, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repository, check=True)

    remote_lock = tmp_path / "deploy.lock"
    _write_remote_release_lock(
        remote_lock,
        token=token,
        label="deploy:mac-routes",
        stage=stage,
        source_sha=source_a,
        source_tree=tree_a,
        state="mutating",
    )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    version_log = tmp_path / "executed-version.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "stat",
        """#!/usr/bin/env python3
import os
import stat
import sys
metadata = os.stat(sys.argv[-1])
mode = stat.S_IMODE(metadata.st_mode)
formats = {
    '%U:%G:%a': f'root:root:{mode:o}',
    '%U:%G:%h': f'root:root:{metadata.st_nlink}',
    '%a': f'{mode:o}',
    '%h': f'{metadata.st_nlink}',
}
print(formats[sys.argv[2]])
""",
        )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
REMOTE_RELEASE_LOCK_DIR={remote_lock!s}
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN={token}
REVA_RELEASE_COORDINATOR_SOURCE_SHA={source_a}
REVA_RELEASE_COORDINATOR_SOURCE_TREE={tree_a}
REVA_RELEASE_COORDINATOR_SURFACE=server
REVA_RELEASE_COORDINATOR_OPERATION=mac-routes
REVA_RELEASE_COORDINATOR_CHANNEL=production
REVA_RELEASE_COORDINATOR_TRANSACTION={'c' * 32}
REVA_RELEASE_COORDINATOR_BASELINE_DIGEST={'d' * 64}
REVA_RELEASE_COORDINATOR_REQUEST_DIGEST={'e' * 64}
set_remote_backup_preflight_dir {stage!s}
MAC_ROUTE_ACTION=apply
ssh() {{ shift; "$@"; }}
scp() {{
    test "$#" -eq 2
    source_path="$1"
    target_path="$2"
    case "$source_path" in
      fake-server.invalid:*)
        cp "${{source_path#fake-server.invalid:}}" "$target_path"
        ;;
      *) return 99 ;;
    esac
}}
acquire_remote_release_lock deploy:mac-routes
test "$DEPLOY_EXPECTED_SHA" = {source_a}
bootstrap_mac_release_routes
test "$DEPLOY_EXPECTED_SHA" = {source_a}
test "$(cat "$MAC_ROUTE_VERSION_LOG")" = A
release_remote_release_lock
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DEPLOY_ENV_FILE": str(env_file),
                "MAC_ROUTE_VERSION_LOG": str(version_log),
            },
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert version_log.read_text(encoding="utf-8") == "A\n"


def _make_ota_drift_fixture(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "mobile").mkdir()
    (repository / "mobile/app.ts").write_text("export const value = 1;\n")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "deploy-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Deploy Test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "add", "mobile/app.ts"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "mobile baseline"], cwd=repository, check=True)
    anchor = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    (repository / "mobile/app.ts").write_text("export const value = 2;\n")
    subprocess.run(["git", "add", "mobile/app.ts"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "mobile pending"], cwd=repository, check=True)
    return repository, anchor


def test_ota_drift_reads_private_shared_anchor_from_git_common_dir(
    tmp_path: Path,
) -> None:
    repository, anchor = _make_ota_drift_fixture(tmp_path)
    state_root = repository / ".git/reva-release-state"
    state_dir = state_root / "mobile-ota"
    state_root.mkdir(mode=0o700)
    state_dir.mkdir(mode=0o700)
    anchor_file = state_dir / "anchor.production"
    anchor_file.write_text(anchor + "\n", encoding="utf-8")
    anchor_file.chmod(0o600)
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
AUTO_YES=1
confirm_ota_drift
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "mobile pending" in result.stdout
    body = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    body = body[body.index("confirm_ota_drift() {") : body.index("\n}\n", body.index("confirm_ota_drift() {"))]
    assert ".last-ota-commit" not in body
    assert "anchor.production" in body


def test_ota_drift_rejects_unsafe_shared_anchor_before_deploy(tmp_path: Path) -> None:
    repository, anchor = _make_ota_drift_fixture(tmp_path)
    state_root = repository / ".git/reva-release-state"
    state_dir = state_root / "mobile-ota"
    state_root.mkdir(mode=0o700)
    state_dir.mkdir(mode=0o700)
    target = tmp_path / "anchor-target"
    target.write_text(anchor + "\n", encoding="utf-8")
    (state_dir / "anchor.production").symlink_to(target)
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
AUTO_YES=1
confirm_ota_drift
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode != 0
    assert "anchor" in (result.stdout + result.stderr).lower()


def test_backend_dependency_proof_wraps_only_pip_and_records_after_postcondition():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("deploy_backend() {")
    end = script.index("CODE_EXIT=$?", start)
    guard = script[start:end]

    check = guard.index("check --mode '$RELEASE_STEP_PROOF_MODE'")
    locked_verify_on_hit = guard.index(
        "python scripts/verify_locked_requirements.py requirements.lock",
        check,
    )
    lease_after_hit_verify = guard.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        locked_verify_on_hit,
    )
    invalidate = guard.index("invalidate --profile python-dependencies", check)
    clean_venv = guard.index("python -m venv --clear venv", invalidate)
    install = guard.index("pip install --require-hashes", invalidate)
    lease_after_install = guard.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        install,
    )
    locked_verify_after_install = guard.index(
        "python scripts/verify_locked_requirements.py requirements.lock",
        lease_after_install,
    )
    pip_check = guard.index("python -m pip check", install)
    lease_before_record = guard.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'", pip_check
    )
    record = guard.index("record --mode '$RELEASE_STEP_PROOF_MODE'", pip_check)
    migration = guard.index("python scripts/apply_managed_migrations.py", record)

    assert (
        check
        < locked_verify_on_hit
        < lease_after_hit_verify
        < invalidate
        < clean_venv
        < install
        < lease_after_install
        < locked_verify_after_install
        < pip_check
        < lease_before_record
        < record
        < migration
    )


def test_frontend_dependency_and_build_proofs_preserve_service_postconditions():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("deploy_frontend() {")
    end = script.index("validate_runtime_only_kb_staging() {", start)
    frontend = script[start:end]

    dependency_check = frontend.index(
        "check --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-dependencies"
    )
    npm_ci = frontend.index("npm ci", dependency_check)
    dependency_record = frontend.index(
        "record --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-dependencies",
        npm_ci,
    )
    build_check = frontend.index(
        "check --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-build",
        dependency_record,
    )
    build = frontend.index("npm run build", build_check)
    restart = frontend.index("pm2 restart health-frontend", build)
    http_proof = frontend.index(
        "curl -fsS --max-time 10 http://127.0.0.1:3000/", restart
    )
    build_record = frontend.index(
        "record --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-build",
        http_proof,
    )

    assert (
        dependency_check < npm_ci < dependency_record < build_check < build
        < restart < http_proof < build_record
    )


def test_frontend_runtime_receipt_is_root_owned_atomic_and_written_after_health():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    helper_start = script.index("write_frontend_runtime_receipt() {")
    helper_end = script.index("\n}\n", helper_start)
    helper = script[helper_start:helper_end]
    deploy_start = script.index("deploy_frontend() {")
    deploy_end = script.index("validate_runtime_only_kb_staging() {", deploy_start)
    frontend = script[deploy_start:deploy_end]

    assert "/var/lib/health-app/release-state/frontend-runtime.json" in helper
    assert "os.O_NOFOLLOW" in helper
    assert "stat.S_ISREG" in helper
    assert "st_nlink" in helper
    assert "st_uid" in helper
    assert "0o600" in helper
    assert "0o700" in helper
    assert "pm2" in helper and "jlist" in helper
    assert "pm_uptime" in helper
    assert '"PM2_HOME": "/root/.pm2"' in helper
    assert ".next/BUILD_ID" in helper
    assert "os.replace" in helper
    assert "os.fsync" in helper
    assert "DEPLOY_EXPECTED_SHA" in helper
    assert "REMOTE_RELEASE_LOCK_TOKEN" in helper

    restart = frontend.index("pm2 restart health-frontend")
    http_proof = frontend.index(
        "curl -fsS --max-time 10 http://127.0.0.1:3000/", restart
    )
    build_record = frontend.index(
        "record --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-build",
        http_proof,
    )
    runtime_receipt = frontend.index("write_frontend_runtime_receipt", build_record)
    final_revision = frontend.index("verify_deployed_revision", runtime_receipt)
    assert restart < http_proof < build_record < runtime_receipt < final_revision


def test_release_proof_reuse_never_wraps_unconditional_server_gates():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    backend = script[script.index("deploy_backend() {"):]

    assert backend.index("backup_database") < backend.index(
        "check --mode '$RELEASE_STEP_PROOF_MODE'"
    )
    for gate in (
        "python scripts/apply_managed_migrations.py",
        "verify_runtime_schema_compatibility.py",
        "systemctl restart health-backend.socket",
        "verify_deployed_revision",
        "verify_deployment",
        "rollback_deploy",
    ):
        assert gate in backend


def test_backend_deploy_checks_health_before_skills_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    health_check = script.index("if ! verify_deployment; then")
    manifest_check = script.index("wait_for_agent_skills_manifest", health_check)

    assert health_check < manifest_check


def test_backend_dependency_proof_replaces_legacy_digest_marker():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("deploy_backend() {")
    end = script.index("CODE_EXIT=$?", start)
    guard = script[start:end]

    assert "requirements-lock.sha256" not in script
    assert "REQUIREMENTS_LOCK_SHA" not in script
    assert "remote_dependency_sync_command" not in script
    assert guard.count(
        "python scripts/verify_locked_requirements.py requirements.lock"
    ) == 2
    assert "pip install --require-hashes -r requirements.lock" in guard
    assert "python -m pip check" in guard


def test_system_kb_incremental_import_is_never_bypassed_by_external_digest_marker():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "determine_system_kb_activation_need" not in script
    assert "record_system_kb_input_digest" not in script
    assert "SYSTEM_KB_ACTIVATION_REQUIRED" not in script
    assert "system-kb-input.sha256" not in script


def test_system_kb_incremental_import_always_runs_inside_release_mutation_phase():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_end = script.index("render_backend_env_file() {", deploy_start)
    deploy_body = script[deploy_start:deploy_end]

    backup = deploy_body.index("backup_database")
    release_lock = deploy_body.index("assert_remote_release_lock", backup)
    mutation = deploy_body.index("python scripts/seed_food_nutrition.py")
    incremental_import = deploy_body.index(
        "python scripts/import_system_kb_v2_artifacts.py",
        mutation,
    )
    final_contract = deploy_body.rindex('verify_runtime_only_kb_contract "staged"')
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates", final_contract
    )

    assert backup < release_lock < mutation < incremental_import < final_contract < finalize
    assert "SYSTEM_KB_IMPORT_PROOF_MODE" in deploy_body
    assert "System KB inputs unchanged; mutation skipped" not in deploy_body
    assert "verify_deployment" in deploy_body
    assert "verify_deployed_revision" in deploy_body


def test_skills_manifest_check_uses_condition_wait_not_fixed_three_retries():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "wait_for_agent_skills_manifest" in script
    assert "for attempt in $(seq 1 12)" in script


def test_skills_manifest_check_does_not_embed_auth_token():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "Authorization: Bearer" not in script


def test_remote_sync_does_not_stash_untracked_runtime_files():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "git stash push -u" not in script
    assert "git stash push -m auto-deploy-stash" in script
    assert "auto-deploy-stash >/dev/null 2>&1 || true" not in script


def test_remote_sync_normalizes_only_git_metadata_and_tracked_paths():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("remote_repository_trust_normalization_command() {")
    end = script.index("remote_git_sync_command() {", start)
    body = script[start:end]

    assert "chown root:root ." in body
    assert "chown -R root:root .git" in body
    assert "chmod -R go-w .git" in body
    assert "git ls-files --stage -z" in body
    assert 'chown -h root:root -- "$tracked_path"' in body
    assert 'chmod 0644 -- "$tracked_path"' in body
    assert 'chmod 0755 -- "$tracked_path"' in body
    assert "chown -R root:root .\n" not in body


def test_repository_trust_normalization_never_targets_ignored_runtime_data(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "backend/.env\nuploads/\ntmp/\nnode_modules/\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    for ignored in (
        repo / "backend/.env",
        repo / "uploads/private.bin",
        repo / "tmp/runtime.sock",
        repo / "node_modules/pkg/index.js",
    ):
        ignored.parent.mkdir(parents=True, exist_ok=True)
        ignored.write_text("runtime\n", encoding="utf-8")

    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@example.test\n"
        f"DEPLOY_PATH={repo!s}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = (
        f"{DEPLOY_SOURCE_FOR_TESTS}\n"
        "remote_repository_trust_normalization_command\n"
    )
    generated = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )
    assert generated.returncode == 0, generated.stderr

    event_log = tmp_path / "ownership-targets.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("chown", "chmod"):
        _write_executable(
            fake_bin / command,
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            f"printf '{command}' >> \"$TARGET_EVENT_LOG\"\n"
            "for arg in \"$@\"; do "
            "printf '|%s' \"$arg\" >> \"$TARGET_EVENT_LOG\"; done\n"
            "printf '\\n' >> \"$TARGET_EVENT_LOG\"\n",
        )
    _write_executable(
        fake_bin / "stat",
        "#!/bin/sh\nprintf 'root:root\\n'\n",
    )
    result = subprocess.run(
        ["bash", "-c", generated.stdout],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TARGET_EVENT_LOG": str(event_log),
        },
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    targets = event_log.read_text(encoding="utf-8")
    assert "|.git\n" in targets
    assert "|src/app.py\n" in targets
    assert "|src\n" in targets
    for ignored in (
        "backend/.env",
        "uploads",
        "tmp",
        "node_modules",
    ):
        assert ignored not in targets


def test_repository_trust_normalization_makes_tracked_seeds_readable_not_writable(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    data_dir = repo / "backend/data"
    data_dir.mkdir(parents=True)
    seed = data_dir / "gene_knowledge.json"
    seed.write_text("{}\n", encoding="utf-8")
    executable = repo / "backend/scripts/probe.sh"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    (repo / ".gitignore").write_text(
        "*.db\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    schedule = data_dir / "celerybeat-schedule.db"
    schedule.write_text("runtime\n", encoding="utf-8")
    data_dir.chmod(0o700)
    seed.chmod(0o600)
    executable.chmod(0o700)
    schedule.chmod(0o600)

    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@example.test\n"
        f"DEPLOY_PATH={repo!s}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = (
        f"{DEPLOY_SOURCE_FOR_TESTS}\n"
        "remote_repository_trust_normalization_command\n"
    )
    generated = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )
    assert generated.returncode == 0, generated.stderr

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ownership_log = tmp_path / "ownership.log"
    _write_executable(
        fake_bin / "chown",
        """#!/bin/sh
set -eu
printf 'chown' >> "$OWNERSHIP_LOG"
for argument in "$@"; do
  printf '|%s' "$argument" >> "$OWNERSHIP_LOG"
done
printf '\n' >> "$OWNERSHIP_LOG"
""",
    )
    _write_executable(fake_bin / "stat", "#!/bin/sh\nprintf 'root:root\\n'\n")
    _write_executable(
        fake_bin / "chmod",
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "args=()\n"
        "for arg in \"$@\"; do\n"
        "  [ \"$arg\" = \"--\" ] || args+=(\"$arg\")\n"
        "done\n"
        "exec /bin/chmod \"${args[@]}\"\n",
    )
    result = subprocess.run(
        ["bash", "-c", generated.stdout],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "OWNERSHIP_LOG": str(ownership_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    ownership_calls = ownership_log.read_text(encoding="utf-8").splitlines()
    for tracked_path in (
        ".gitignore",
        "backend/data/gene_knowledge.json",
        "backend/scripts/probe.sh",
    ):
        assert f"chown|root:root|--|{tracked_path}" in ownership_calls
    for tracked_parent in (
        "backend",
        "backend/data",
        "backend/scripts",
    ):
        assert f"chown|root:root|--|{tracked_parent}" in ownership_calls
    assert all("celerybeat-schedule.db" not in call for call in ownership_calls)
    assert data_dir.stat().st_mode & 0o777 == 0o755
    assert seed.stat().st_mode & 0o777 == 0o644
    assert executable.stat().st_mode & 0o777 == 0o755
    assert schedule.stat().st_mode & 0o777 == 0o600


def test_backend_wraps_runtime_state_in_verified_release_transaction():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index(
        "remote_repository_trust_normalization_command() {", stage_start
    )
    stage_body = script[stage_start:stage_end]
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    assert "backend/scripts/runtime_state_release_transaction.py" in stage_body
    for name in (
        "health-backend-runtime-state.conf",
        "celery-worker-runtime-state.conf",
        "celery-beat-runtime-state.conf",
    ):
        assert name in stage_body
    assert "remote_celery_beat_state_migration_command" not in script
    assert "cleanup_legacy_celery_beat_state" not in script

    status = deploy_body.index(
        "inspect_runtime_state_transaction_before_deploy"
    )
    preflight = deploy_body.index(
        "run_runtime_state_transaction \\\n            preflight"
    )
    stop = deploy_body.index("systemctl stop health-backend.socket")
    prepare = deploy_body.index(
        "prepare '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA'"
    )
    checkout = deploy_body.index("$remote_git_sync")
    install = deploy_body.index(
        "install '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA'"
    )
    restart = deploy_body.index("systemctl restart celery-worker celery-beat")
    stable_proof = deploy_body.index(
        "prove_health_evidence_runtime_process_flag false", restart
    )
    guard_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "guard"',
        stable_proof,
    )
    commit = deploy_body.index(
        "commit_runtime_state_transaction_after_guard",
        guard_contract,
    )
    floor = deploy_body.index(
        'ROLLBACK_COMMIT="$DEPLOY_EXPECTED_SHA"',
        commit,
    )
    skills = deploy_body.index("wait_for_agent_skills_manifest", floor)
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates",
        skills,
    )
    assert (
        status
        < preflight
        < stop
        < prepare
        < checkout
        < install
        < restart
        < stable_proof
        < guard_contract
        < commit
        < floor
        < skills
        < finalize
    )


def test_backend_reprobes_stability_process_revision_and_kb_after_skills():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {") :]
    skills = deploy_body.rindex("wait_for_agent_skills_manifest")
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates",
        skills,
    )
    terminal_gate_body = deploy_body[skills:finalize]

    for probe in (
        "prove_health_evidence_runtime_process_flag false",
        "verify_deployment",
        "verify_deployed_revision",
        'verify_runtime_only_kb_contract "staged"',
    ):
        assert probe in terminal_gate_body


def test_deactivation_proof_requires_services_stable_across_restart_window():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_deactivated_state() {")
    end = script.index(
        "prove_health_evidence_runtime_process_flag() {", start
    )
    body = script[start:end]

    assert "SERVICE_STABILITY_SECONDS=7" in body
    assert "--property=SubState" in body
    assert "--property=Result" in body
    assert "--property=NRestarts" in body
    assert 'sleep "$SERVICE_STABILITY_SECONDS"' in body
    assert (
        'test "$main_pid" = "${stable_main_pid[$process_index]}"'
        in body
    )
    assert (
        '"${stable_restart_count[$process_index]}"'
        in body
    )
    assert body.count("verify_process_environment_false") >= 2


@pytest.mark.parametrize(
    "failure_mode",
    ("beat-restart", "socket-substate-flip"),
)
def test_deactivation_proof_rejects_restart_of_only_celery_beat(
    tmp_path: Path,
    failure_mode: str,
):
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    proof = script.split(
        "<<'REMOTE_DEACTIVATION_PROOF'\n", 1
    )[1].split("\nREMOTE_DEACTIVATION_PROOF", 1)[0]
    proof_script = tmp_path / "deactivation-proof.sh"
    proof_script.write_text(proof, encoding="utf-8")

    repo = tmp_path / "release"
    (repo / "backend").mkdir(parents=True)
    (repo / "backend" / ".env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    (release_lock / "token").write_text("proof-owner\n", encoding="utf-8")
    runtime_state = tmp_path / "runtime-state"
    systemd_runtime = tmp_path / "systemd-runtime"
    systemd_runtime.mkdir()
    durable_state = tmp_path / "durable-state"
    cgroup_root = tmp_path / "cgroup"
    proc_root = tmp_path / "proc"
    cgroup_root.mkdir()
    proc_root.mkdir()
    unit_pids = {
        "health-backend": 4101,
        "celery-worker": 4201,
        "celery-beat": 4301,
    }
    for unit, pid in unit_pids.items():
        cgroup = cgroup_root / "system.slice" / f"{unit}.service"
        cgroup.mkdir(parents=True)
        (cgroup / "cgroup.procs").write_text(f"{pid}\n", encoding="utf-8")
        process = proc_root / str(pid)
        process.mkdir()
        (process / "environ").write_bytes(
            b"PATH=/usr/bin\0"
            b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0"
        )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    restart_marker = tmp_path / "restart-window.elapsed"
    _write_executable(
        fake_bin / "sleep",
        """#!/bin/sh
set -eu
: > "$FAKE_RESTART_MARKER"
""",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/bin/bash
set -euo pipefail
test "$1" = "show"
unit="$2"
name="${unit%.service}"
case "$name" in
  health-backend) pid=4101 ;;
  celery-worker) pid=4201 ;;
  celery-beat) pid=4301 ;;
  health-backend.socket) pid=0 ;;
  *) exit 91 ;;
esac
case "$*" in
  *--property=ActiveState*) printf 'active\n' ;;
  *--property=SubState*)
    if [ "$name" = "health-backend.socket" ]; then
      if [ "${FAKE_SOCKET_FLIP_AFTER_SLEEP:-0}" = "1" ] &&
         [ -e "$FAKE_RESTART_MARKER" ]; then
        printf 'listening\n'
      else
        printf 'running\n'
      fi
    else
      printf 'running\n'
    fi
    ;;
  *--property=Result*) printf 'success\n' ;;
  *--property=MainPID*) printf '%s\n' "$pid" ;;
  *--property=NRestarts*)
    if [ "${FAKE_BEAT_RESTART_AFTER_SLEEP:-0}" = "1" ] &&
       [ "$name" = "celery-beat" ] &&
       [ -e "$FAKE_RESTART_MARKER" ]; then
      printf '1\n'
    else
      printf '0\n'
    fi
    ;;
  *--property=ActiveEnterTimestampMonotonic*)
    if [ "${FAKE_BEAT_RESTART_AFTER_SLEEP:-0}" = "1" ] &&
       [ "$name" = "celery-beat" ] &&
       [ -e "$FAKE_RESTART_MARKER" ]; then
      printf '200\n'
    else
      printf '100\n'
    fi
    ;;
  *--property=ControlGroup*)
    printf '/system.slice/%s.service\n' "$name"
    ;;
  *) exit 92 ;;
esac
""",
    )
    result = subprocess.run(
        [
            "bash",
            str(proof_script),
            str(repo),
            str(durable_state),
            str(release_lock),
            "proof-owner",
            "-",
            str(runtime_state),
            str(systemd_runtime),
            str(cgroup_root),
            str(proc_root),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_RESTART_MARKER": str(restart_marker),
            "FAKE_BEAT_RESTART_AFTER_SLEEP": (
                "1" if failure_mode == "beat-restart" else "0"
            ),
            "FAKE_SOCKET_FLIP_AFTER_SLEEP": (
                "1" if failure_mode == "socket-substate-flip" else "0"
            ),
        },
    )

    assert result.returncode != 0, (result.stdout, result.stderr)
    assert restart_marker.exists()


def test_socket_ready_state_is_portable_but_stable_across_proofs():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = deploy.index("prove_health_evidence_deactivated_state() {")
    deploy_end = deploy.index(
        "prove_health_evidence_runtime_process_flag() {", deploy_start
    )
    activation = (
        ROOT
        / "backend"
        / "scripts"
        / "activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    rollback = (
        ROOT / "backend" / "scripts" / "rollback_release.sh"
    ).read_text(encoding="utf-8")

    for body in (deploy[deploy_start:deploy_end], activation, rollback):
        assert "listening|running" in body
        assert 'stable_socket_sub_state="$sub_state"' in body
        assert '"$sub_state" = "$stable_socket_sub_state"' in body
        assert "*) return 1 ;;" in body


def test_activation_and_rollback_proofs_reject_restart_windows():
    activation = (
        ROOT
        / "backend"
        / "scripts"
        / "activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    rollback = (
        ROOT / "backend" / "scripts" / "rollback_release.sh"
    ).read_text(encoding="utf-8")

    for body in (activation, rollback):
        assert "SERVICE_STABILITY_SECONDS=7" in body
        assert "--property=NRestarts" in body
        assert "--property=SubState" in body
        assert "--property=Result" in body
        assert 'sleep "$SERVICE_STABILITY_SECONDS"' in body


def test_backup_and_health_score_failures_block_deploy():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    backup_start = script.index("backup_database() {")
    backup_end = script.index("# 记录当前 commit", backup_start)
    backup_body = script[backup_start:backup_end]
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "print_warning \"数据库备份失败" not in backup_body
    assert "return 1" in backup_body
    assert "健康度检查跳过" not in verify_body
    assert "健康度脚本无有效输出" in verify_body


def test_health_score_failure_reports_critical_gate_detail():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "critical_failures" in verify_body
    assert "agent_runtime_circuit" in verify_body
    assert "健康度硬闸" in verify_body


def test_deploy_health_gate_proves_garmin_worker_affinity():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "systemctl show health-backend --property=ExecStart --value" in verify_body
    assert '[[ "$BACKEND_EXEC_START" != *"--workers 1"* ]]' in verify_body
    assert "Garmin MFA 单 worker 约束未生效" in verify_body


def test_backend_proves_rollback_schema_before_live_env_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    backup = deploy_body.index("backup_database")
    rollback_point = deploy_body.index("save_rollback_point")
    rollback_probe = deploy_body.index(
        "verify_rollback_point_schema_compatibility"
    )
    sync_env = deploy_body.index("sync_env")

    assert backup < rollback_point < rollback_probe < sync_env


def test_backend_runs_bundle_and_runtime_preflight_before_live_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    rollback_probe = deploy_body.index(
        "verify_rollback_point_schema_compatibility"
    )
    bundle = deploy_body.index("upload_deploy_bundle", rollback_probe)
    preflight = deploy_body.index(
        "run_runtime_state_transaction \\\n            preflight",
        bundle,
    )
    sync_env = deploy_body.index("sync_env", preflight)
    preserve = deploy_body.index(
        "_REMOTE_RELEASE_LOCK_ABANDONED=1",
        sync_env,
    )
    deactivate = deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation",
        preserve,
    )

    assert (
        rollback_probe
        < bundle
        < preflight
        < sync_env
        < preserve
        < deactivate
    )


def test_adopted_release_lock_is_preserved_before_transaction_inspection(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "ssh.events"
    adopted_stage = (
        f"/tmp/health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    token = "a" * 64
    transaction_id = "c" * 32
    baseline_digest = "d" * 64
    request_digest = "e" * 64
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN={token}
ssh() {{
        printf 'ssh\\n' >> "$ADOPT_EVENT_LOG"
        printf '%s\\n' \
          'REMOTE_RELEASE_LOCK_ADOPTED state=sealed stage={adopted_stage} source_sha={source_sha} source_tree={source_tree} surface=server operation=backend channel=production transaction_id={transaction_id} baseline_digest={baseline_digest} request_digest={request_digest} terminal_digest=-'
}}
acquire_remote_release_lock deploy:backend
test "$_REMOTE_RELEASE_LOCK_ADOPTED" -eq 1
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
cleanup_remote_release_artifacts
test "$(wc -l < "$ADOPT_EVENT_LOG")" -eq 2
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "ADOPT_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_rollback_sha_is_recorded_only_after_schema_probe_success():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    save_start = script.index("save_rollback_point() {")
    save_end = script.index(
        "verify_rollback_point_schema_compatibility() {",
        save_start,
    )
    save_body = script[save_start:save_end]
    verify_start = save_end
    verify_end = script.index("# 回滚到上一个版本", verify_start)
    verify_body = script[verify_start:verify_end]

    assert 'ROLLBACK_CANDIDATE_COMMIT="$rollback_commit"' in save_body
    assert 'ROLLBACK_COMMIT="$rollback_commit"' not in save_body
    assert "sha256sum --strict -c staged.sha256" in verify_body
    assert "source .env" not in verify_body
    assert "env -u MIGRATION_DATABASE_URL" in verify_body
    assert "ROLLBACK_POINT_SCHEMA_OK commit=" in verify_body
    probe_success = verify_body.index(
        'if [[ "$probe_output" != *"ROLLBACK_SCHEMA_PROBE_OK tables="* ||'
    )
    record = verify_body.index(
        'ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"'
    )
    assert probe_success < record


def test_guard_probes_full_schema_before_starting_any_backend_writer():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]
    guard_end = deploy_body.index("CODE_EXIT=$?")
    guard_body = deploy_body[:guard_end]

    stop_socket = guard_body.index("systemctl stop health-backend.socket")
    stop_backend = guard_body.index("systemctl stop health-backend &&")
    stop_celery = guard_body.index(
        "systemctl stop celery-worker celery-beat"
    )
    checkout = guard_body.index("$remote_git_sync")
    dependency_sync = guard_body.index(
        "check --mode '$RELEASE_STEP_PROOF_MODE' --profile python-dependencies"
    )
    migration = guard_body.index("python scripts/apply_managed_migrations.py")
    lease_before_migration = guard_body.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        dependency_sync,
    )
    stage_recheck = guard_body.index(
        "sha256sum --strict -c staged.sha256",
        migration,
    )
    schema_probe = guard_body.index(
        "verify_runtime_schema_compatibility.py"
    )
    lease_after_probe = guard_body.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        schema_probe,
    )
    restart_socket = guard_body.index(
        "systemctl restart health-backend.socket"
    )
    restart_backend = guard_body.index("systemctl restart health-backend &&")
    restart_celery = guard_body.index(
        "systemctl restart celery-worker celery-beat"
    )

    assert (
        stop_socket
        < stop_backend
        < stop_celery
        < checkout
        < dependency_sync
        < lease_before_migration
        < migration
        < stage_recheck
        < schema_probe
        < lease_after_probe
        < restart_socket
        < restart_backend
        < restart_celery
    )


def test_guard_lost_lease_after_pip_never_runs_migration_or_restarts_writers(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    remote_repo = tmp_path / "remote"
    backend = remote_repo / "backend"
    fake_bin = tmp_path / "bin"
    lease_dir = tmp_path / "release-lock"
    stage_dir = tmp_path / "stage"
    event_log = tmp_path / "events"
    migration_marker = tmp_path / "migration-ran"
    fake_migration_env = tmp_path / "migration.env"
    backend.mkdir(parents=True)
    fake_bin.mkdir()
    lease_dir.mkdir()
    stage_dir.mkdir()
    (backend / "venv" / "bin").mkdir(parents=True)
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={remote_repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    (backend / ".env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    (backend / "venv" / "bin" / "activate").write_text(
        ":\n",
        encoding="utf-8",
    )
    fake_migration_env.write_text(
        "MIGRATION_DATABASE_URL=postgresql://migration-role@example/health\n",
        encoding="utf-8",
    )
    (lease_dir / "token").write_text("lease-token\n", encoding="utf-8")
    (stage_dir / "staged.sha256").write_text(
        "stage evidence remains\n",
        encoding="utf-8",
    )
    runtime_helper = stage_dir / "runtime_state_release_transaction.py"
    runtime_helper.write_text(
        "import sys\n"
        "print('RUNTIME_STATE_TRANSACTION_OK command=' + sys.argv[1])\n",
        encoding="utf-8",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
printf 'systemctl:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
if [ "$1" = "show" ]; then
    printf 'inactive\\n'
fi
""",
    )
    _write_executable(
        fake_bin / "pip",
        """#!/usr/bin/env bash
printf 'pip:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
rm -f "$FAKE_LEASE_DIR/token"
""",
    )
    _write_executable(
        fake_bin / "python",
        """#!/usr/bin/env bash
printf 'python:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
if [ "$1" = "../scripts/release_step_proof.py" ] && [ "$2" = "check" ]; then
    exit 3
fi
if [ "$1" = "scripts/apply_managed_migrations.py" ]; then
    : > "$FAKE_MIGRATION_MARKER"
fi
""",
    )
    _write_root_owned_stat_shim(fake_bin / "stat")
    _write_executable(fake_bin / "sync", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "mv",
        """#!/bin/sh
set -eu
test "$1" = "-fT"
test "$2" = "--"
/bin/mv -f "$3" "$4"
""",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA={'2' * 40}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_DIR={lease_dir!s}
REMOTE_RELEASE_STATE_DIR={(tmp_path / 'release-state')!s}
REMOTE_RELEASE_LOCK_TOKEN=lease-token
REMOTE_BACKUP_PREFLIGHT_DIR={stage_dir!s}
REMOTE_RUNTIME_STATE_RUNNER={runtime_helper!s}
validate_runtime_only_kb_staging() {{ :; }}
assert_remote_release_lock_if_acquired() {{ :; }}
assert_remote_release_lock() {{ :; }}
backup_database() {{ :; }}
save_rollback_point() {{ ROLLBACK_CANDIDATE_COMMIT={'1' * 40}; }}
verify_rollback_point_schema_compatibility() {{
    ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"
}}
sync_env() {{ :; }}
    deactivate_health_evidence_runtime_before_mutation() {{ :; }}
    upload_deploy_bundle() {{ :; }}
    run_runtime_state_transaction() {{ :; }}
    remote_git_sync_command() {{ printf ':'; }}
    ssh() {{
    shift
    local command="$*"
    command="${{command//\\/etc\\/health-app\\/migration.env/$FAKE_MIGRATION_ENV}}"
    PATH="$FAKE_BIN:$PATH" bash -c "$command"
}}
if (deploy_backend); then exit 91; fi
test -d "$REMOTE_RELEASE_LOCK_DIR"
test -d "$REMOTE_BACKUP_PREFLIGHT_DIR"
test -f "$REMOTE_BACKUP_PREFLIGHT_DIR/staged.sha256"
test ! -e "$FAKE_MIGRATION_MARKER"
test ! -e "$REMOTE_RELEASE_LOCK_DIR/token"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_BIN": str(fake_bin),
            "FAKE_EVENT_LOG": str(event_log),
            "FAKE_LEASE_DIR": str(lease_dir),
            "FAKE_MIGRATION_ENV": str(fake_migration_env),
            "FAKE_MIGRATION_MARKER": str(migration_marker),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not migration_marker.exists()
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert any(event.startswith("pip:") for event in events)
    assert not any(
        event.startswith("python:")
        and (
            "scripts/apply_managed_migrations.py" in event
            or "verify_runtime_schema_compatibility.py" in event
        )
        for event in events
    )
    assert not any("restart" in event for event in events)
    assert {
        event.removeprefix("systemctl:")
        for event in events
        if event.startswith("systemctl:stop ")
    } >= {
        "stop health-backend.socket",
        "stop health-backend",
        "stop celery-worker celery-beat",
    }


def test_unknown_guard_transaction_failure_never_starts_concurrent_rollback():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]
    failure_start = deploy_body.index("if [ $CODE_EXIT -ne 0 ]; then")
    failure_end = deploy_body.index(
        "if ! prove_health_evidence_runtime_process_flag false",
        failure_start,
    )
    failure_body = deploy_body[failure_start:failure_end]

    assert "rollback_deploy" not in failure_body
    assert "_REMOTE_RELEASE_LOCK_DELEGATED=0" not in failure_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in failure_body
    assert "transaction terminal" in failure_body


def test_runtime_state_commit_disconnect_preserves_lease_without_rollback(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
DEPLOY_EXPECTED_SHA={'a' * 40}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf 'commit-rpc\\n' >> "$COMMIT_EVENT_LOG"
    return 255
}}
rollback_deploy() {{
    printf 'rollback\\n' >> "$COMMIT_EVENT_LOG"
}}
commit_runtime_state_transaction_after_guard
commit_rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$commit_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$COMMIT_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "COMMIT_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "commit-rpc",
        "rc=1 delegated=1 abandoned=1",
    ]


def test_runtime_state_finalize_disconnect_preserves_lease_without_rollback(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
DEPLOY_EXPECTED_SHA={'a' * 40}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf 'finalize-rpc\\n' >> "$FINALIZE_EVENT_LOG"
    return 255
}}
rollback_deploy() {{
    printf 'rollback\\n' >> "$FINALIZE_EVENT_LOG"
}}
finalize_runtime_state_transaction_after_all_gates
finalize_rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$finalize_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$FINALIZE_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FINALIZE_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "finalize-rpc",
        "rc=1 delegated=1 abandoned=1",
    ]


def test_runtime_state_status_adopts_journal_authoritative_release(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA={candidate_sha}
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=PREPARED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=true gate_released=false release_target=none next_action=install state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{old_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_RESUME_PHASE" = PREPARED
test "$RUNTIME_STATE_RESUME_TARGET" = none
test "$ROLLBACK_CANDIDATE_COMMIT" = {old_sha}
test "$ROLLBACK_COMMIT" = {old_sha}
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_runtime_state_status_rejects_other_candidate_and_preserves_lease(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA={'b' * 40}
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=INSTALLED old_sha={'a' * 40} candidate_sha={'c' * 40} gate_armed=true gate_released=false release_target=none next_action=candidate-guard state_source=journal'
}}
set +e
inspect_runtime_state_transaction_before_deploy
inspect_rc=$?
test "$inspect_rc" -ne 0
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize(
    ("phase", "remote_head", "env_proof_ok"),
    (
        ("INSTALLED", "c" * 40, True),
        ("PREPARED", "a" * 40, False),
    ),
)
def test_runtime_state_resume_proof_failure_preserves_stage_and_lease(
    tmp_path: Path,
    phase: str,
    remote_head: str,
    env_proof_ok: bool,
):
    env_file = tmp_path / "deploy.env"
    stage = tmp_path / "release-stage"
    lock_dir = tmp_path / "release-lock"
    stage.mkdir()
    lock_dir.mkdir()
    (stage / "backend.env.rollback").write_text("rollback")
    (lock_dir / "token").write_text("owner")
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
DEPLOY_EXPECTED_SHA={candidate_sha}
REMOTE_BACKUP_PREFLIGHT_DIR={stage!s}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase={phase} old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=true gate_released=false release_target=none next_action=install state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{remote_head}' ;;
      *) [ '{1 if env_proof_ok else 0}' = 1 ] ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
inspect_rc=$?
set -e
test "$inspect_rc" -ne 0
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
cleanup_remote_release_artifacts
test -d "$REMOTE_BACKUP_PREFLIGHT_DIR"
test -f "$REMOTE_BACKUP_PREFLIGHT_DIR/backend.env.rollback"
test -d "$REMOTE_RELEASE_LOCK_DIR"
test -f "$REMOTE_RELEASE_LOCK_DIR/token"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_committed_journal_resumes_post_commit_gates_before_finalize(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA={candidate_sha}
run_runtime_state_transaction() {{
    printf '%s\\n' "$1" >> "$STATUS_EVENT_LOG"
    test "$1" = status
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=false gate_released=true release_target=candidate next_action=finalize state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{candidate_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_RESUME_PHASE" = COMMITTED
test "$RUNTIME_STATE_ALREADY_FINALIZED" -eq 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "STATUS_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == ["status"]


def test_terminal_marker_cleanup_is_idempotent_before_read_only_post_gates(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA={candidate_sha}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf '%s\\n' "$1" >> "$STATUS_EVENT_LOG"
    if [ "$1" = status ]; then
        printf '%s\\n' \
          'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=false gate_released=true release_target=candidate next_action=finalize state_source=terminal'
    else
        test "$1" = finalize
        test "$2" = {candidate_sha}
        printf '%s\\n' \
          'RUNTIME_STATE_TRANSACTION_OK command=finalize result=finalized'
    fi
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{candidate_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_ALREADY_FINALIZED" -eq 1
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "STATUS_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "status",
        "finalize",
    ]


def test_remote_release_lock_rejects_shell_metacharacters_before_ssh(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    ssh_marker = tmp_path / "ssh-called"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR="/tmp/release-lock';touch /tmp/injected"
ssh() {{ : > "$SSH_MARKER"; }}
set +e
acquire_remote_release_lock test
lock_rc=$?
test "$lock_rc" -eq 70
test ! -e "$SSH_MARKER"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "SSH_MARKER": str(ssh_marker),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not ssh_marker.exists()


@pytest.mark.parametrize(
    (
        "runtime_dir",
        "upload_dir",
        "skills_cache_dir",
        "dedao_dir",
        "legacy_enabled",
        "allowed",
    ),
    (
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            True,
        ),
        (
            "/opt/health-app/backend/data",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/opt/health-app/backend/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/opt/health-app/.health-skills-cache",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase-review",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "true",
            False,
        ),
    ),
)
def test_env_guard_requires_canonical_external_runtime_paths(
    tmp_path: Path,
    runtime_dir: str,
    upload_dir: str,
    skills_cache_dir: str,
    dedao_dir: str,
    legacy_enabled: str,
    allowed: bool,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "APP_ENV=production\n"
        "DEBUG=False\n"
        f"HEALTH_RUNTIME_DATA_DIR={runtime_dir}\n"
        f"HEALTH_UPLOAD_DIR={upload_dir}\n"
        f"HEALTH_SKILLS_CACHE_DIR={skills_cache_dir}\n"
        f"DEDAO_KBASE_REVIEW_ARTIFACT_DIR={dedao_dir}\n"
        f"LEGACY_KNOWLEDGE_RUNTIME_ENABLED={legacy_enabled}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
scp() {{ return 1; }}
validate_env_sync_safety
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert (result.returncode == 0) is allowed, (
        result.stdout,
        result.stderr,
    )


def test_plain_ssh_write_failures_preserve_server_lease_for_reconciliation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    for function_name, next_marker in (
        ("backup_database() {", "# 记录当前 commit"),
        ("backup_remote_env() {", "upload_backend_env_file() {"),
        ("restart_frontend_service() {", "# 推送代码到 GitHub"),
        ("deploy_frontend() {", "validate_runtime_only_kb_staging() {"),
    ):
        start = script.index(function_name)
        end = script.index(next_marker, start)
        body = script[start:end]
        assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_release_cleanup_abandons_server_lease_on_hup_int_and_term():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("install_release_cleanup_traps() {")
    end = script.index("acquire_remote_release_lock() {", start)
    body = script[start:end]

    assert "abandon_remote_release_lock 129" in body
    assert "abandon_remote_release_lock 130" in body
    assert "abandon_remote_release_lock 143" in body


def test_env_sync_uses_external_backup_root_and_mode_0600():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'REMOTE_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in script
    assert 'ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"' in script
    assert 'cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"' in script
    assert 'install -o root -g health-app -m 0640' in script


def test_env_sync_stages_candidate_and_only_deactivation_atomically_installs_live_env():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    upload_start = script.index("upload_backend_env_file() {")
    upload_end = script.index("validate_env_sync_safety() {", upload_start)
    upload_body = script[upload_start:upload_end]
    transaction_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    transaction_end = script.index(
        "prove_health_evidence_deactivated_state() {",
        transaction_start,
    )
    transaction_body = script[transaction_start:transaction_end]
    execution_body = transaction_body[
        transaction_body.index("mutation_started=1") :
    ]

    assert "REMOTE_BACKEND_ENV_CANDIDATE" in upload_body
    assert "sha256sum -c" in upload_body
    assert 'scp "$temp_env" "$SERVER:$REMOTE_PATH/backend/.env"' not in upload_body
    assert 'mv -fT "$candidate_install_tmp" "$target_env"' in transaction_body
    helper_start = transaction_body.index("install_candidate_env() {")
    helper_end = transaction_body.index(
        "remove_runtime_authorization() {", helper_start
    )
    helper_body = transaction_body[helper_start:helper_end]
    install = helper_body.index(
        'install -o root -g health-app -m 0640'
    )
    sync_tmp = helper_body.index('sync -f "$candidate_install_tmp"')
    rename = helper_body.index(
        'mv -fT "$candidate_install_tmp" "$target_env"'
    )
    sync_parent = helper_body.index('sync -f "$target_env_dir"')
    assert install < sync_tmp < rename < sync_parent
    assert "install_candidate_env" in execution_body


def test_deploy_accepts_main_or_detached_exact_origin_main_only():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'CURRENT_BRANCH="$(trusted_release_git branch --show-current)"' in script
    assert '[[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "main" ]]' in script
    assert "git push origin HEAD:main" not in script
    assert "git ls-remote origin refs/heads/main" not in script
    assert "git push kuaishou HEAD:main" not in script
    assert 'trusted_release_git fetch --quiet --no-tags "$CANONICAL_RELEASE_ORIGIN_URL"' in script
    assert 'trusted_release_network_git ls-remote --exit-code' in script


def test_direct_server_release_proves_canonical_source_before_any_lock_or_network_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_start = script.index("main() {")
    main_body = script[main_start:]

    source_proof = main_body.index("verify_release_coordinator_source")
    local_lock = main_body.index('acquire_release_lock "deploy:${DEPLOY_MODE}"')
    remote_lock = main_body.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    push = main_body.index("push_code", remote_lock)

    assert source_proof < local_lock < remote_lock < push


def test_direct_server_release_rejects_noncanonical_origin_before_lock(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repository,
        check=True,
    )
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repository, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://attacker.invalid/repo.git"],
        cwd=repository,
        check=True,
    )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    lock_marker = tmp_path / "lock-called"
    network_marker = tmp_path / "network-called"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR={repository!s}
acquire_release_lock() {{ printf called > {lock_marker!s}; return 99; }}
trusted_release_network_git() {{ printf called > {network_marker!s}; return 99; }}
main --backend --yes
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert not lock_marker.exists()
    assert not network_marker.exists()


def test_remote_checkout_and_post_deploy_revision_match_expected_sha():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "DEPLOY_EXPECTED_SHA" in script
    assert "verify_deployed_revision" in script
    assert "git rev-parse HEAD" in script
    assert "远端部署版本不匹配" in script


def test_automatic_rollback_uses_verified_release_runner_and_propagates_failure():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]

    assert "if ! rollback_output=$(ssh" in rollback_body
    assert "return 1" in rollback_body
    assert "git checkout $ROLLBACK_COMMIT -- ." not in rollback_body
    assert "kb_quarantine=passed" in rollback_body
    assert "REMOTE_ROLLBACK_RUNNER" in rollback_body
    assert "$REMOTE_PATH/backend/scripts/rollback_release.sh" not in rollback_body
    assert "rollback_output=" in rollback_body
    assert "ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed" in rollback_body


@pytest.mark.parametrize(
    ("runtime_state_marker", "accepted"),
    (
        ("runtime_state=restored", True),
        ("runtime_state=candidate-retained", True),
        ("", False),
        ("runtime_state=unknown", False),
        ("runtime_state=restored-extra", False),
    ),
)
def test_automatic_rollback_accepts_only_terminal_runtime_state_values(
    tmp_path: Path,
    runtime_state_marker: str,
    accepted: bool,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    rollback_commit = "a" * 40
    marker = (
        f"ROLLBACK_OK commit={rollback_commit} "
        "kb_quarantine=passed schema_probe=passed auth_probe=passed "
        "services=active process_flag=false"
    )
    if runtime_state_marker:
        marker += f" {runtime_state_marker}"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
ROLLBACK_COMMIT={rollback_commit}
ssh() {{ printf '%s\\n' "$FAKE_ROLLBACK_OUTPUT"; }}
rollback_deploy
rollback_rc=$?
printf 'ROLLBACK_RESULT rc=%s delegated=%s abandoned=%s\\n' \
    "$rollback_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
exit 0
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_ROLLBACK_OUTPUT": marker,
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    expected = (
        "ROLLBACK_RESULT rc=0 delegated=0 abandoned=0"
        if accepted
        else "ROLLBACK_RESULT rc=1 delegated=1 abandoned=1"
    )
    assert expected in result.stdout


def test_release_preflight_stages_rollback_code_and_failed_release_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]

    assert "rollback_release.sh" in stage_body
    assert "verify_locked_requirements.py" in stage_body
    assert "verify_runtime_schema_compatibility.py" in stage_body
    assert "quarantine_runtime_only_kb.py" in stage_body
    assert "review_manifest.json" in stage_body
    assert "shasum -a 256" in stage_body
    assert "sha256sum" in stage_body
    assert "git cat-file -e" in stage_body
    assert "git show" in stage_body
    assert "staged.sha256" in stage_body


def test_release_env_snapshots_are_sealed_into_verified_stage_before_deactivation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    seal_start = script.index("seal_release_env_snapshots() {")
    seal_end = script.index("require_canonical_env_assignment() {", seal_start)
    seal_body = script[seal_start:seal_end]
    sync_start = script.index("sync_env() {")
    sync_end = script.index("# 去激活事务", sync_start)
    sync_body = script[sync_start:sync_end]
    deploy_body = script[script.index("deploy_backend() {") :]

    for snapshot in ("backend.env.rollback", "backend.env.candidate"):
        assert snapshot in seal_body
    assert "sha256sum --strict -c staged.sha256" in seal_body
    assert '" = "15"' in seal_body
    assert sync_body.index("upload_backend_env_file") < sync_body.index(
        "seal_release_env_snapshots"
    )
    assert deploy_body.index("sync_env") < deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )


def test_deploy_does_not_claim_services_are_blocked_when_rollback_fails():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "服务保持阻断状态" not in script
    assert "无法证明服务已停止" in script


def test_all_mode_captures_old_backend_sha_before_frontend_checkout(tmp_path):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "deploy.events"
    old_sha = "1" * 40
    new_sha = "2" * 40
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_HEAD={old_sha}
verify_release_coordinator_source() {{ :; }}
acquire_release_lock() {{ :; }}
capture_expected_server_surfaces_before_lock() {{ :; }}
acquire_remote_release_lock() {{
    _REMOTE_RELEASE_LOCK_ACQUIRED=1
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
}}
install_release_cleanup_traps() {{ :; }}
capture_expected_server_surfaces_under_lock() {{
    ROLLBACK_CANDIDATE_COMMIT="$REMOTE_HEAD"
}}
bind_expected_server_surfaces_under_lock() {{ :; }}
assert_remote_release_lock() {{ :; }}
verify_expected_server_surfaces_under_lock() {{ :; }}
confirm_ota_drift() {{ :; }}
push_code() {{
    DEPLOY_EXPECTED_SHA={new_sha}
    printf 'push\\n' >> "$DEPLOY_EVENT_LOG"
}}
ssh() {{ printf '%s\\n' "$REMOTE_HEAD"; }}
deploy_frontend() {{
    REMOTE_HEAD={new_sha}
    printf 'frontend-checkout:%s\\n' "$REMOTE_HEAD" >> "$DEPLOY_EVENT_LOG"
}}
deploy_backend() {{
    save_rollback_point
    verify_rollback_point_schema_compatibility
    printf 'backend-floor:%s\\n' "$ROLLBACK_COMMIT" >> "$DEPLOY_EVENT_LOG"
    REMOTE_HEAD={new_sha}
}}
verify_rollback_point_schema_compatibility() {{
    ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"
}}
check_status() {{ printf 'status\\n' >> "$DEPLOY_EVENT_LOG"; }}
main --all --yes
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEPLOY_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "push",
        f"backend-floor:{old_sha}",
        f"frontend-checkout:{new_sha}",
        "status",
    ]


def test_frontend_build_refuses_revision_mismatch_before_npm_or_pm2(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
assert_remote_release_lock_if_acquired() {{ :; }}
verify_deployed_revision() {{ return 1; }}
ssh() {{ printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"; }}
if deploy_frontend; then exit 91; fi
test ! -e "$FRONTEND_EVENT_LOG"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not event_log.exists()


def test_frontend_build_same_sha_does_not_mutate_runtime_or_backend_services(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    durable = tmp_path / "enabled.env"
    durable_bytes = (
        b"# commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        b"# guard_sha256=" + b"b" * 64 + b"\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    durable.write_bytes(durable_bytes)
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    assert_remote_release_lock_if_acquired() {{ :; }}
    mark_remote_release_mutation_started() {{ :; }}
verify_deployed_revision() {{
    printf 'revision\\n' >> "$FRONTEND_EVENT_LOG"
}}
ssh() {{
    printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"
    case "$*" in
      *systemctl*|*health-backend*|*celery*) return 92 ;;
    esac
}}
deploy_frontend
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert durable.read_bytes() == durable_bytes
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events[0] == "revision"
    assert events[-1] == "revision"
    ssh_events = [event for event in events if event.startswith("ssh:")]
    assert len(ssh_events) == 2
    assert "/usr/bin/python3 -" in ssh_events[1]
    assert "frontend-runtime" not in ssh_events[0]
    assert all("systemctl" not in event for event in events)
    assert all("health-backend" not in event for event in events)
    assert all("celery" not in event for event in events)


def test_env_candidate_upload_interruption_never_touches_live_env(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    live_env = backend / ".env"
    live_bytes = (
        b"SECRET_VALUE=production-secret\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    live_env.write_bytes(live_bytes)
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700)
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "env-stage-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "SECRET_VALUE=new-secret\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "scp",
        """#!/bin/bash
set -euo pipefail
source="$1"
destination="${2#*:}"
if [ "${FAKE_SCP_INTERRUPT:-0}" = "1" ]; then
  /usr/bin/head -c 8 "$source" > "$destination"
  exit 74
fi
/bin/cp "$source" "$destination"
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
/bin/cp "$source" "$target"
chmod 0400 "$target"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
if [ -d "$target" ]; then
  printf 'root:root:700\n'
else
  printf 'root:root:400\n'
fi
""",
    )
    _write_executable(
        bin_dir / "sync",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -f\ntest -e \"$2\"\n",
    )
    _write_executable(
        bin_dir / "mv",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -fT\n/bin/mv \"$2\" \"$3\"\n",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_BACKUP_PREFLIGHT_DIR={stage}
REMOTE_BACKEND_ENV_CANDIDATE={stage / "backend.env.candidate"}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
ssh() {{ shift; "$@"; }}
upload_backend_env_file "$ENV_FILE"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_SCP_INTERRUPT": "1",
        },
    )

    assert result.returncode != 0
    assert live_env.read_bytes() == live_bytes
    assert not (stage / "backend.env.candidate").exists()


def test_backend_deploy_establishes_guard_floor_before_system_kb_activation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    restart = deploy_body.index("systemctl restart health-backend")
    first_health = deploy_body.index("if ! verify_deployment; then")
    first_revision = deploy_body.index("verify_deployed_revision", first_health)
    guard_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "guard"',
        first_health,
    )
    guard_floor = deploy_body.index("ROLLBACK_COMMIT=\"$DEPLOY_EXPECTED_SHA\"")
    phase0_seed = deploy_body.index("python scripts/seed_system_kb_phase0.py")
    v2_import = deploy_body.index("python scripts/import_system_kb_v2_artifacts.py")
    second_health = deploy_body.index(
        "if ! verify_deployment; then",
        first_health + 1,
    )

    staged_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"',
        second_health,
    )

    assert (
        restart
        < first_health
        < first_revision
        < guard_contract
        < guard_floor
        < phase0_seed
        < v2_import
        < second_health
        < staged_contract
    )


def test_backend_deploy_requires_runtime_only_feature_flag_off_during_guard_rollout():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    validator_start = script.index("validate_runtime_only_kb_staging() {")
    validator_end = script.index("deploy_backend() {", validator_start)
    validator_body = script[validator_start:validator_end]
    deploy_body = script[validator_end:]

    assert "review_manifest.json" in validator_body
    assert "generic_serving_allowed" in validator_body
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED" in validator_body
    assert "false" in validator_body
    assert 'pack.get("serving_allowed") is True' not in validator_body
    assert deploy_body.index("validate_runtime_only_kb_staging") < deploy_body.index(
        "sync_env"
    )


def test_backend_revokes_durable_runtime_before_checkout_or_kb_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    sync_guard = deploy_body.index("sync_env")
    revoke = deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    checkout = deploy_body.index("$remote_git_sync")
    migration = deploy_body.index("python scripts/apply_managed_migrations.py")
    kb_import = deploy_body.index(
        "python scripts/import_system_kb_v2_artifacts.py"
    )

    assert sync_guard < revoke < checkout < migration < kb_import

    deactivation_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    deactivation_end = script.index(
        "prove_health_evidence_deactivated_state() {", deactivation_start
    )
    deactivation = script[deactivation_start:deactivation_end]
    execution = deactivation[deactivation.index("mutation_started=1") :]
    assert "enabled.env" in deactivation
    assert "sync -f" in deactivation
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" in deactivation
    assert "cgroup.procs" in deactivation
    assert "health-backend.socket" in deactivation
    assert 'systemctl stop "$unit"' in deactivation
    assert 'systemctl start "$unit"' in deactivation
    assert (
        "stop_and_prove_services_inactive() {"
        in deactivation
    )
    assert "verify_services_inactive" in deactivation
    stop = execution.index("stop_and_prove_services_inactive")
    branch_start = execution.index(
        'if [ "$legacy_flag_bootstrap" -eq 1 ]; then'
    )
    branch_else = execution.index("\nelse\n", branch_start)
    branch_end = execution.index(
        "\nfi\nverify_flag_file_false", branch_else
    )
    bootstrap_branch = execution[branch_start:branch_else]
    standard_branch = execution[branch_else:branch_end]
    start = execution.index('systemctl start "$unit"')
    process_false = execution.index("verify_process_environment_false")
    assert stop < branch_start < branch_end < start < process_false
    assert bootstrap_branch.index(
        "install_candidate_env"
    ) < bootstrap_branch.index("remove_runtime_authorization")
    assert standard_branch.index(
        "remove_runtime_authorization"
    ) < standard_branch.index("install_candidate_env")


def test_deactivation_delegates_before_remote_stage_or_live_mutation_and_proves_last_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    sync_start = script.index("sync_env() {")
    sync_end = script.index("# 去激活事务", sync_start)
    sync_body = script[sync_start:sync_end]
    orchestration_start = script.index(
        "deactivate_health_evidence_runtime_before_mutation() {"
    )
    orchestration_end = script.index("# 部署后端", orchestration_start)
    orchestration = script[orchestration_start:orchestration_end]
    deploy_body = script[script.index("deploy_backend() {") :]

    assert sync_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < sync_body.index(
        "upload_backend_env_file"
    )
    assert orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        orchestration.index("run_health_evidence_deactivation_transaction")
    )
    assert orchestration.index(
        "run_health_evidence_deactivation_transaction"
    ) < orchestration.index("prove_health_evidence_deactivated_state")
    assert orchestration.index("prove_health_evidence_deactivated_state") < (
        orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=0")
    )
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in orchestration

    last_backend_restart = deploy_body.index(
        "systemctl restart health-backend"
    )
    assert last_backend_restart < deploy_body.index(
        "prove_health_evidence_runtime_process_flag false",
        last_backend_restart,
    )


def test_guard_kb_and_rollback_never_overlap_unknown_remote_transactions():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {") :]
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]
    guard_start = deploy_body.index("# 3. Guard phase")
    kb_start = deploy_body.index("# 5. KB activation phase")
    guard_body = deploy_body[guard_start:kb_start]
    kb_body = deploy_body[kb_start:]

    assert guard_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        guard_body.index("ssh $SERVER")
    )
    assert "远端事务结果不明确" in guard_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in guard_body
    assert kb_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        kb_body.index("ssh $SERVER")
    )
    assert "不与可能仍运行的 importer 并发回滚" in kb_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in kb_body
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        rollback_body.index("ssh")
    )
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0") > (
        rollback_body.index("ROLLBACK_OK")
    )


def test_generic_env_and_restart_revoke_durable_runtime_before_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    env_body = main_body[env_start:env_end]
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    restart_body = main_body[restart_start:restart_end]

    assert env_body.index("sync_env") < env_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    assert "restart_services" not in env_body
    assert restart_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    ) < restart_body.index("restart_frontend_service")


def test_frontend_only_never_mutates_backend_checkout_or_runtime_authorization():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    frontend_start = main_body.index('"frontend")')
    frontend_end = main_body.index('"backend")', frontend_start)
    frontend_body = main_body[frontend_start:frontend_end]
    deploy_start = script.index("deploy_frontend() {")
    deploy_end = script.index("validate_runtime_only_kb_staging() {", deploy_start)
    deploy_body = script[deploy_start:deploy_end]

    assert "deactivate_health_evidence_runtime_before_mutation" not in frontend_body
    assert deploy_body.count("verify_deployed_revision") == 2
    assert deploy_body.index("verify_deployed_revision") < deploy_body.index(
        "npm ci"
    )
    assert deploy_body.count(
        "git status --porcelain --untracked-files=all"
    ) == 2
    assert "remote_git_sync" not in deploy_body
    assert "git checkout" not in deploy_body


def test_post_import_staged_contract_failure_uses_quarantine_rollback():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {"):]
    contract_call = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"'
    )
    rollback_call = deploy_body.index("rollback_deploy", contract_call)
    exit_call = deploy_body.index("exit 1", rollback_call)

    assert contract_call < rollback_call < exit_call


def test_health_evidence_activation_is_delegated_to_persistent_systemd_transaction():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("activate_health_evidence_runtime() {")
    end = script.index("# 查看服务状态", start)
    body = script[start:end]
    runner_start = script.index("run_health_evidence_activation_unit() {")
    runner_end = script.index(
        "prove_health_evidence_activation_state() {", runner_start
    )
    runner_body = script[runner_start:runner_end]
    proof_start = runner_end
    proof_end = script.index(
        "prove_health_evidence_activation_not_launched() {", proof_start
    )
    proof_body = script[proof_start:proof_end]

    adopted_branch = body.index('if [[ "$adopted" = "1" ]]')
    adopted_stage = body.index(
        "stage_health_evidence_activation_artifacts",
        adopted_branch,
    )
    adopted_enabled_proof = body.index(
        "prove_health_evidence_activation_state",
        adopted_stage,
    )
    adopted_not_launched = body.index(
        "prove_health_evidence_activation_not_launched",
        adopted_enabled_proof,
    )
    precheck = body.index(
        'verify_runtime_only_kb_contract "staged"',
        adopted_not_launched,
    )
    stage_delegated = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1", precheck)
    capability = body.index(
        "verify_systemd_activation_capability",
        stage_delegated,
    )
    fresh_branch = body.index('if [[ "$adopted" != "1" ]]', capability)
    stage = body.index(
        "stage_health_evidence_activation_artifacts",
        fresh_branch,
    )
    stage_clear = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0", stage)
    launch_delegated = body.index(
        "_REMOTE_RELEASE_LOCK_DELEGATED=1", stage_clear
    )
    launch = body.index("run_health_evidence_activation_unit")
    deadman = runner_body.index("ExecStopPost")
    recover_mode = runner_body.index("--recover-if-unverified")

    assert (
        adopted_branch
        < adopted_stage
        < adopted_enabled_proof
        < adopted_not_launched
        < precheck
        < stage_delegated
        < capability
        < fresh_branch
        < stage
        < stage_clear
        < launch_delegated
        < launch
    )
    assert deadman >= 0
    assert recover_mode >= 0
    assert "systemd-run" in runner_body
    assert "require_health_evidence_flag_value true" in body
    assert "sync_env" not in body
    assert "upload_backend_env_file" not in body
    assert "restart_health_runtime_services" not in body
    assert 'HEALTH_EVIDENCE_ACTIVATION_OK commit=$expected_sha' in proof_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_activation_stage_hashes_runner_candidate_guard_and_keeps_marker_outside():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("stage_health_evidence_activation_artifacts() (")
    end = script.index("activate_health_evidence_runtime() {", start)
    body = script[start:end]

    assert "activate_health_evidence_runtime.sh" in body
    assert "candidate.env" in body
    assert "guard.env" in body
    assert "staged.sha256" in body
    assert "sha256sum" in body
    assert "require_health_evidence_flag_value false" in body
    assert "require_health_evidence_flag_value true" in body
    assert "REMOTE_ACTIVATION_SUCCESS_MARKER" in body
    assert "dirname" not in body or "REMOTE_BACKUP_PREFLIGHT_DIR" in body


def test_activation_proof_uses_durable_authorization_and_real_process_flags():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_services_inactive() {", start
    )
    proof = script[start:end]

    assert "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" in proof
    assert "guard_sha256" in proof
    assert "cgroup.procs" in proof
    assert "verify_process_environment" in proof
    assert 'HEALTH_EVIDENCE_RUNTIME_ENABLED=true' in proof
    assert 'flag_is_exact "$repo/backend/.env" false' in proof
    assert 'cmp -s "$guard_env" "$repo/backend/.env"' in proof
    assert 'cmp -s "$candidate_env" "$repo/backend/.env"' not in proof
    assert "verify_git_metadata_trust" in proof
    assert "verify_tracked_worktree_trust" in proof
    assert "verify_repo_revision" in proof
    assert "GIT_CONFIG_NOSYSTEM=1" in proof
    assert 'GIT_CONFIG_GLOBAL="$protected_config"' in proof
    assert 'GIT_OBJECT_DIRECTORY="$git_dir/objects"' in proof
    assert "GIT_OPTIONAL_LOCKS=0" in proof
    assert "/usr/bin/git --no-optional-locks --no-replace-objects" in proof
    assert '--git-dir="$proof_git"' in proof
    assert '--work-tree="$repo"' in proof
    assert '-c "safe.directory=$repo"' not in proof
    assert "-c core.fsmonitor=false" in proof
    assert "-c core.hooksPath=/dev/null" in proof


def test_activation_proof_derives_space_bearing_markers_on_remote_side():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_activation_not_launched() {", start
    )
    proof = script[start:end]
    ssh_prefix = 'ssh "$SERVER" bash -s -- \\'
    remote_start = proof.index(ssh_prefix)
    heredoc_start = proof.index("<<'REMOTE_ACTIVATION_PROOF'", remote_start)
    ssh_argv = proof[remote_start + len(ssh_prefix) : heredoc_start]
    argv = [
        line.strip().removesuffix("\\").strip()
        for line in ssh_argv.splitlines()
        if line.strip()
    ]
    remote = proof[heredoc_start:]

    # OpenSSH joins command arguments into one remote shell command. Marker
    # strings contain spaces, so sending them as argv silently shifts every
    # following positional parameter. Pin the exact ordered argv contract,
    # and independently make the remote reject any future extra argument.
    assert argv == [
        '"$phase"',
        '"$unit_name"',
        '"$REMOTE_PATH"',
        '"$DEPLOY_EXPECTED_SHA"',
        '"$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env"',
        '"$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env"',
        '"$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR"',
        '"$REMOTE_ACTIVATION_SUCCESS_MARKER"',
        '"${REMOTE_ACTIVATION_SUCCESS_MARKER}.outcome"',
        '"$REMOTE_RELEASE_LOCK_DIR"',
        '"$REMOTE_RELEASE_LOCK_TOKEN"',
    ]
    argc_check = remote.index('test "$#" -eq 11')
    first_assignment = remote.index('phase="$1"')
    assert argc_check < first_assignment
    assert 'expected_outcome="${10}"' not in remote
    assert 'expected_success="${11}"' not in remote
    assert 'release_lock="${10}"' in remote
    assert 'release_token="${11}"' in remote
    runner = (
        ROOT / "backend/scripts/activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    expected_markers = (
        "HEALTH_EVIDENCE_ACTIVATION_OK commit=$expected_sha flag=true "
        "health=passed auth_probe=passed score=passed contract=enabled "
        "services=active",
        "HEALTH_EVIDENCE_DEADMAN_NOOP commit=$expected_sha "
        "authorization=verified",
        "HEALTH_EVIDENCE_DEADMAN_RECOVERED commit=$expected_sha flag=false "
        "health=passed contract=staged services=active",
    )
    marker_pattern = re.compile(
        r'"(HEALTH_EVIDENCE_(?:ACTIVATION_OK|DEADMAN_'
        r'(?:NOOP|RECOVERED))[^"\n]*)"'
    )
    remote_markers = tuple(marker_pattern.findall(remote))
    runner_markers = tuple(
        marker.replace("$EXPECTED_SHA", "$expected_sha")
        for marker in marker_pattern.findall(runner)
    )
    assert sorted(remote_markers) == sorted(expected_markers)
    assert sorted(runner_markers) == sorted(expected_markers)
    assert sorted(remote_markers) == sorted(runner_markers)

    phase_case = remote[remote.index('case "$phase" in') :]
    enabled_start = phase_case.index("enabled)")
    staged_start = phase_case.index("staged)", enabled_start)
    invalid_start = phase_case.index("*)", staged_start)
    case_end = phase_case.index("esac", invalid_start)
    enabled_body = phase_case[enabled_start:staged_start]
    staged_body = phase_case[staged_start:invalid_start]
    invalid_body = phase_case[invalid_start:case_end]
    assert enabled_body.count("expected_outcome=") == 1
    assert "HEALTH_EVIDENCE_DEADMAN_NOOP" in enabled_body
    assert "HEALTH_EVIDENCE_DEADMAN_RECOVERED" not in enabled_body
    assert staged_body.count("expected_outcome=") == 1
    assert "HEALTH_EVIDENCE_DEADMAN_RECOVERED" in staged_body
    assert "HEALTH_EVIDENCE_DEADMAN_NOOP" not in staged_body
    assert "expected_outcome=" not in invalid_body
    assert "exit 2" in invalid_body


def test_activation_process_flag_awk_executes_on_posix_awk():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    proof_start = script.index("prove_health_evidence_activation_state() {")
    proof_end = script.index(
        "prove_health_evidence_activation_not_launched() {", proof_start
    )
    proof = script[proof_start:proof_end]
    process_start = proof.index("verify_process_environment() {")
    process_end = proof.index("\nverify_repo_revision\n", process_start)
    process_proof = proof[process_start:process_end]
    awk_program_match = re.search(
        r'awk -v expected="\$expected" \'(?P<program>.*?)\n\s*\'',
        process_proof,
        re.DOTALL,
    )

    assert awk_program_match is not None
    result = subprocess.run(
        ["awk", "-v", "expected=true", awk_program_match.group("program")],
        input="HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_activation_proof_marker_checks_are_byte_exact(tmp_path: Path):
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_activation_not_launched() {", start
    )
    proof = script[start:end]
    outcome_check = (
        'cmp -s "$outcome_file" '
        '<(printf \'%s\\n\' "$expected_outcome")'
    )
    success_check = (
        'cmp -s "$success_marker" '
        '<(printf \'%s\\n\' "$expected_success")'
    )

    assert outcome_check in proof
    assert success_check in proof
    assert 'test "$(cat "$outcome_file")" = "$expected_outcome"' not in proof
    assert 'test "$(cat "$success_marker")" = "$expected_success"' not in proof

    harness = (
        "set -euo pipefail\n"
        'outcome_file="$1"\n'
        'success_marker="$2"\n'
        'expected_outcome="$3"\n'
        'expected_success="$4"\n'
        f"{outcome_check}\n"
        f"{success_check}\n"
    )
    expected_outcome = "known outcome"
    expected_success = "known success"
    cases = (
        ("exact", b"known outcome\n", b"known success\n", True),
        ("outcome-missing-lf", b"known outcome", b"known success\n", False),
        ("outcome-extra-lf", b"known outcome\n\n", b"known success\n", False),
        ("success-missing-lf", b"known outcome\n", b"known success", False),
        ("success-extra-lf", b"known outcome\n", b"known success\n\n", False),
    )
    for label, outcome_bytes, success_bytes, should_pass in cases:
        outcome_file = tmp_path / f"{label}.outcome"
        success_file = tmp_path / f"{label}.success"
        outcome_file.write_bytes(outcome_bytes)
        success_file.write_bytes(success_bytes)
        result = subprocess.run(
            [
                "bash",
                "-c",
                harness,
                "--",
                str(outcome_file),
                str(success_file),
                expected_outcome,
                expected_success,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert (result.returncode == 0) is should_pass, (
            label,
            result.stdout,
            result.stderr,
        )


def test_release_preflight_hashes_activation_runner_for_rollback_floor():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]
    rollback = (
        ROOT / "backend/scripts/rollback_release.sh"
    ).read_text(encoding="utf-8")

    assert "activate_health_evidence_runtime.sh" in stage_body
    assert "activate_health_evidence_runtime.sh" in rollback


def test_cli_has_dedicated_health_evidence_activation_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "--activate-health-evidence" in script
    assert 'DEPLOY_MODE="health-evidence"' in script
    assert "activate_health_evidence_runtime" in script


def test_cli_has_secret_free_app_store_review_reset_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("reset_app_store_review_demo() {")
    end = script.index("\n# 查看服务状态", start)
    body = script[start:end]

    assert "--reset-app-store-review" in script
    assert 'DEPLOY_MODE="app-store-review-reset"' in script
    assert "verify_deployed_revision" in body
    assert "APP_STORE_REVIEW_DEMO_ACCOUNT" in body
    assert "APP_STORE_REVIEW_DEMO_PASSWORD" in body
    assert "--secret-free" in body
    assert "APP_STORE_REVIEW_RESET_OK" in body
    assert "--rotate-password" not in body
    mutation = body.index("mark_remote_release_mutation_started")
    delegated = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1", mutation)
    remote = body.index('reset_output=$(ssh "$SERVER"', delegated)
    assert mutation < delegated < remote
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body[remote:]
    assert body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0", remote) > body.index(
        '[[ "$reset_output" != "APP_STORE_REVIEW_RESET_OK" ]]', remote
    )


@pytest.mark.parametrize(
    ("ssh_result", "expected_rc", "delegated", "abandoned"),
    (("transport-failure", 1, "1", "1"), ("success", 0, "0", "0")),
)
def test_app_store_review_reset_retains_lease_until_exact_terminal_proof(
    tmp_path: Path,
    ssh_result: str,
    expected_rc: int,
    delegated: str,
    abandoned: str,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
assert_remote_release_lock() {{ :; }}
verify_deployed_revision() {{ :; }}
mark_remote_release_mutation_started() {{ REMOTE_RELEASE_LOCK_STATE=mutating; }}
ssh() {{
    test "$_REMOTE_RELEASE_LOCK_DELEGATED" = 1
    if test "$SSH_RESULT" = transport-failure; then
        return 255
    fi
    cat >/dev/null
    printf '%s\\n' APP_STORE_REVIEW_RESET_OK
}}
set +e
reset_app_store_review_demo
rc=$?
set -e
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$rc" "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
test "$rc" = "$EXPECTED_RC"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "SSH_RESULT": ssh_result,
            "EXPECTED_RC": str(expected_rc),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert f"rc={expected_rc} delegated={delegated} abandoned={abandoned}" in result.stdout


def test_health_evidence_flag_parser_only_accepts_one_canonical_assignment(
    tmp_path,
):
    cases = (
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=false", "false", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "true", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=1", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=yes", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=on", "false", False),
        ('HEALTH_EVIDENCE_RUNTIME_ENABLED="true"', "false", False),
        ("export HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "false", False),
        (
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
            "false",
            False,
        ),
    )
    for index, (assignments, expected, allowed) in enumerate(cases):
        env_file = tmp_path / f"deploy-{index}.env"
        env_file.write_text(
            "\n".join(
                (
                    "DEPLOY_SERVER=fake-server",
                    "DEPLOY_PATH=/tmp/fake-health-app",
                    assignments,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
require_health_evidence_flag_value {expected}
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
        assert (result.returncode == 0) is allowed, (
            assignments,
            result.stdout,
            result.stderr,
        )


def test_generic_env_and_restart_paths_require_canonical_false():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_start = script.index("main() {")
    main_body = script[main_start:]

    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    assert "require_health_evidence_flag_value false" in main_body[env_start:env_end]
    assert (
        "require_health_evidence_flag_value false"
        in main_body[restart_start:restart_end]
    )


def test_mutating_deploy_modes_acquire_server_release_lease():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    acquire = main_body.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    execute = main_body.index("# 执行对应操作")

    assert acquire < execute
    assert (
        '"all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"'
        in main_body
    )
    assert "assert_remote_release_lock" in main_body[acquire:execute]
    assert "push" not in main_body[acquire - 100 : acquire]


def test_server_release_lease_rejects_second_owner_and_only_owner_can_release(
    tmp_path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    remote_lock = tmp_path / "remote-release.lock"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={remote_lock!s}
ssh() {{ shift; "$@"; }}
REVA_REMOTE_RELEASE_LOCK_TOKEN=owner-one
acquire_remote_release_lock first
first_token="$REMOTE_RELEASE_LOCK_TOKEN"
first_label="$REMOTE_RELEASE_LOCK_LABEL"
first_stage="$REMOTE_BACKUP_PREFLIGHT_DIR"
first_state="$REMOTE_RELEASE_LOCK_STATE"
first_source_sha="$REMOTE_RELEASE_SOURCE_SHA"
first_source_tree="$REMOTE_RELEASE_SOURCE_TREE"
first_surface="$REMOTE_RELEASE_SURFACE"
first_operation="$REMOTE_RELEASE_OPERATION"
first_channel="$REMOTE_RELEASE_CHANNEL"
first_transaction="$REMOTE_RELEASE_TRANSACTION_ID"
first_baseline="$REMOTE_RELEASE_BASELINE_DIGEST"
first_request="$REMOTE_RELEASE_REQUEST_DIGEST"
first_terminal="$REMOTE_RELEASE_TERMINAL_DIGEST"
_REMOTE_RELEASE_LOCK_ACQUIRED=0
REMOTE_RELEASE_LOCK_TOKEN=
REVA_REMOTE_RELEASE_LOCK_TOKEN=owner-two
if acquire_remote_release_lock second; then
    exit 91
fi
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=wrong-owner
if release_remote_release_lock; then
    exit 92
fi
test -d "$REMOTE_RELEASE_LOCK_DIR"
REMOTE_RELEASE_LOCK_TOKEN="$first_token"
REMOTE_RELEASE_LOCK_LABEL="$first_label"
set_remote_backup_preflight_dir "$first_stage"
REMOTE_RELEASE_LOCK_STATE="$first_state"
REMOTE_RELEASE_SOURCE_SHA="$first_source_sha"
REMOTE_RELEASE_SOURCE_TREE="$first_source_tree"
REMOTE_RELEASE_SURFACE="$first_surface"
REMOTE_RELEASE_OPERATION="$first_operation"
REMOTE_RELEASE_CHANNEL="$first_channel"
REMOTE_RELEASE_TRANSACTION_ID="$first_transaction"
REMOTE_RELEASE_BASELINE_DIGEST="$first_baseline"
REMOTE_RELEASE_REQUEST_DIGEST="$first_request"
REMOTE_RELEASE_TERMINAL_DIGEST="$first_terminal"
release_remote_release_lock
test ! -e "$REMOTE_RELEASE_LOCK_DIR"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize("unsafe_parent", ("world-writable", "symlink"))
def test_remote_release_lock_rejects_unsafe_parent_without_creating_lock(
    tmp_path: Path, unsafe_parent: str
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    if unsafe_parent == "world-writable":
        real_parent.chmod(0o777)
        parent = real_parent
    else:
        parent = tmp_path / "linked-parent"
        parent.symlink_to(real_parent, target_is_directory=True)
    lock_dir = parent / "deploy.lock"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
REVA_REMOTE_RELEASE_LOCK_TOKEN=test-owner
ssh() {{ shift; "$@"; }}
if acquire_remote_release_lock deploy:backend; then
    exit 91
fi
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not (real_parent / "deploy.lock").exists()


def test_deploy_bundle_is_inside_root_only_stage_not_predictable_tmp_target():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert 'REMOTE_DEPLOY_BUNDLE="$REMOTE_BACKUP_PREFLIGHT_DIR/deploy.bundle"' in script
    assert 'REMOTE_DEPLOY_BUNDLE="/tmp/health-app-deploy-' not in script
    stage = script[
        script.index("stage_backup_preflight_scripts() {") : script.index(
            "\n}\n\nrun_runtime_state_transaction()",
            script.index("stage_backup_preflight_scripts() {"),
        )
    ]
    assert "mkdir '$REMOTE_BACKUP_PREFLIGHT_DIR'" in stage
    assert "test ! -e '$REMOTE_DEPLOY_BUNDLE'" in stage
    assert "test ! -L '$REMOTE_DEPLOY_BUNDLE'" in stage
    assert "root:root:600:1" in stage
    assert "sync -f '$REMOTE_DEPLOY_BUNDLE'" in stage


@pytest.mark.parametrize("preexisting", ("regular", "symlink", "hardlink"))
def test_preexisting_bundle_stage_is_not_overwritten(
    tmp_path: Path, preexisting: str
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    victim = tmp_path / "victim"
    victim.write_bytes(b"must remain byte-for-byte\n")
    bundle = stage / "deploy.bundle"
    if preexisting == "regular":
        bundle.write_bytes(b"preexisting partial bundle\n")
    elif preexisting == "symlink":
        bundle.symlink_to(victim)
    else:
        os.link(victim, bundle)
    before_victim = victim.read_bytes()
    before_bundle = bundle.read_bytes()
    scp_log = tmp_path / "scp.log"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set_remote_backup_preflight_dir {stage!s}
DEPLOY_EXPECTED_SHA=$(git -C "$SCRIPT_DIR" rev-parse HEAD)
assert_remote_release_lock_if_acquired() {{ :; }}
ssh() {{ shift; bash -c "$1"; }}
scp() {{ printf '%s\\n' "$*" >> "$SCP_LOG"; return 99; }}
if stage_backup_preflight_scripts; then
    exit 91
fi
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "DEPLOY_ENV_FILE": str(env_file),
                "SCP_LOG": str(scp_log),
            },
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert victim.read_bytes() == before_victim
        assert bundle.read_bytes() == before_bundle
        assert not scp_log.exists()
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_remote_release_lock(
    lock_dir: Path,
    *,
    token: str,
    label: str,
    stage: Path,
    source_sha: str = "a" * 40,
    source_tree: str = "b" * 40,
    state: str = "sealed",
    surface: str = "server",
    operation: str | None = None,
    channel: str = "production",
    transaction_id: str = "c" * 32,
    baseline_digest: str = "d" * 64,
    request_digest: str = "e" * 64,
    terminal_digest: str = "-",
) -> None:
    if operation is None:
        operation = label.removeprefix("deploy:")
    lock_dir.mkdir(mode=0o700)
    for name, value in (
        ("schema", "2"),
        ("token", token),
        ("label", label),
        ("stage", str(stage)),
        ("started_at", "2026-08-12T00:00:00Z"),
        ("source_sha", source_sha),
        ("source_tree", source_tree),
        ("state", state),
        ("surface", surface),
        ("operation", operation),
        ("channel", channel),
        ("transaction_id", transaction_id),
        ("baseline_digest", baseline_digest),
        ("request_digest", request_digest),
        ("terminal_digest", terminal_digest),
    ):
        path = lock_dir / name
        path.write_text(value + "\n", encoding="ascii")
        path.chmod(0o600)


def _remote_release_context_shell(
    *,
    token: str,
    label: str,
    stage: Path,
    source_sha: str = "a" * 40,
    source_tree: str = "b" * 40,
    state: str = "sealed",
    surface: str = "server",
    operation: str | None = None,
    channel: str = "production",
    transaction_id: str = "c" * 32,
    baseline_digest: str = "d" * 64,
    request_digest: str = "e" * 64,
    terminal_digest: str = "-",
) -> str:
    if operation is None:
        operation = label.removeprefix("deploy:")
    return f"""
set_remote_backup_preflight_dir {stage!s}
REMOTE_RELEASE_LOCK_TOKEN={token}
REMOTE_RELEASE_LOCK_LABEL={label}
REMOTE_RELEASE_LOCK_STATE={state}
REMOTE_RELEASE_SOURCE_SHA={source_sha}
REMOTE_RELEASE_SOURCE_TREE={source_tree}
REMOTE_RELEASE_SURFACE={surface}
REMOTE_RELEASE_OPERATION={operation}
REMOTE_RELEASE_CHANNEL={channel}
REMOTE_RELEASE_TRANSACTION_ID={transaction_id}
REMOTE_RELEASE_BASELINE_DIGEST={baseline_digest}
REMOTE_RELEASE_REQUEST_DIGEST={request_digest}
REMOTE_RELEASE_TERMINAL_DIGEST={terminal_digest}
"""


def _release_lock_tree_bytes(parent: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(parent)): (path.stat().st_mode & 0o7777, path.read_bytes())
        for path in sorted(parent.rglob("*"))
        if path.is_file()
    }


def test_remote_release_handoff_discovers_exact_active_owner_without_writes(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    lock_dir = tmp_path / "remote-release.lock"
    _write_remote_release_lock(
        lock_dir,
        token="durable-owner-token",
        label="deploy:backend",
        stage=stage,
        state="sealed",
    )
    before = _release_lock_tree_bytes(tmp_path)
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
ssh() {{ shift; "$@"; }}
show_remote_release_lock_handoff
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 78, (result.stdout, result.stderr)
    assert "检查已冻结" in result.stderr
    assert "durable-owner-token" not in result.stdout + result.stderr
    assert "REVA_REMOTE_RELEASE_LOCK" not in result.stdout
    assert "export " not in result.stdout
    assert str(stage) not in result.stdout
    assert "重新执行原部署命令" not in result.stdout
    assert _release_lock_tree_bytes(tmp_path) == before


@pytest.mark.parametrize("kind", ("alloc", "state", "released"))
def test_remote_release_handoff_discovers_interrupted_owner_residue_without_writes(
    tmp_path: Path,
    kind: str,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    lock_path = tmp_path / "remote-release.lock"
    residue = tmp_path / f".remote-release.lock.{kind}-orphan-owner-token"
    if kind == "state":
        residue.write_text("sealed\n", encoding="ascii")
        residue.chmod(0o600)
    else:
        residue.mkdir(mode=0o700)
        token_file = residue / "token"
        token_file.write_text("orphan-owner-token\n", encoding="ascii")
        token_file.chmod(0o600)
    before = _release_lock_tree_bytes(tmp_path)
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_path!s}
ssh() {{ shift; "$@"; }}
show_remote_release_lock_handoff
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 78, (result.stdout, result.stderr)
    assert "检查已冻结" in result.stderr
    assert "orphan-owner-token" not in result.stdout + result.stderr
    assert "REVA_REMOTE_RELEASE_LOCK" not in result.stdout
    assert "export " not in result.stdout
    assert _release_lock_tree_bytes(tmp_path) == before


@pytest.mark.parametrize(
    "raw",
    (
        "REMOTE_RELEASE_HANDOFF status=recovery kind=terminal token=secret-token label=deploy:backend",
        "REMOTE_RELEASE_HANDOFF status=mac-recovery kind=phase token=secret-token",
    ),
)
def test_remote_release_inspection_never_prints_reusable_recovery_authority(
    tmp_path: Path,
    raw: str,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
remote_release_lock_command() {{ builtin printf '%s\\n' {raw!r}; }}
show_remote_release_lock_handoff
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 78, (result.stdout, result.stderr)
    assert "检查已冻结" in result.stderr
    assert "secret-token" not in result.stdout + result.stderr
    assert "export " not in result.stdout
    assert "REVA_REMOTE_RELEASE_LOCK" not in result.stdout
    assert "--recover-mac-release" not in result.stdout
    assert "重新执行" not in result.stdout


def test_deploy_direct_inspect_freezes_before_env_paths_or_remote_tools(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-tool-called"
    for name in ("dirname", "git", "python3", "ssh"):
        tool = fake_bin / name
        tool.write_text(
            f'#!/bin/sh\nprintf called >> "{marker}"\nexit 91\n',
            encoding="utf-8",
        )
        tool.chmod(0o755)
    secret = "do-not-print-inspection-token"
    result = subprocess.run(
        ["/bin/bash", str(DEPLOY_SCRIPT), "--inspect-release-lock"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SHELLOPTS": "xtrace",
            "REVA_REMOTE_RELEASE_LOCK_TOKEN": secret,
            "DEPLOY_ENV_FILE": str(tmp_path / "must-not-be-read.env"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "repository entrypoints are frozen" in result.stderr
    assert secret not in result.stdout + result.stderr
    assert not marker.exists()


def test_remote_release_handoff_rejects_unknown_residue_without_writes(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    lock_path = tmp_path / "remote-release.lock"
    residue = tmp_path / ".remote-release.lock.unrecognized-owner"
    residue.write_bytes(b"preserve exactly\n")
    residue.chmod(0o600)
    before = _release_lock_tree_bytes(tmp_path)
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_path!s}
ssh() {{ shift; "$@"; }}
if show_remote_release_lock_handoff; then
    exit 91
fi
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _release_lock_tree_bytes(tmp_path) == before


@pytest.mark.parametrize(
    "actual",
    (
        ["9" * 40, "b" * 64, "c" * 40, "d" * 64, "e" * 40, "f" * 64, "1" * 64],
        ["a" * 40, "b" * 64, "c" * 40, "d" * 64, "9" * 40, "f" * 64, "1" * 64],
    ),
    ids=("same-surface-published", "different-surface-published"),
)
def test_server_surface_cas_blocks_intervening_publish_before_any_mutation(
    tmp_path: Path,
    actual: list[str],
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    expected = [
        "a" * 40,
        "b" * 64,
        "c" * 40,
        "d" * 64,
        "e" * 40,
        "f" * 64,
        "1" * 64,
    ]
    mutation_log = tmp_path / "mutation.log"
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_TOKEN=cas-owner
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REVA_EXPECTED_SERVER_SURFACES='{json.dumps(expected, separators=(",", ":"))}'
python3() {{
    if [[ "$1" == *release_production_state.py ]]; then
        printf '%s\\n' '{json.dumps(actual, separators=(",", ":"))}'
        return 0
    fi
    command python3 "$@"
}}
mark_remote_release_mutation_started() {{ printf 'mutated\\n' > "$MUTATION_LOG"; }}
if verify_expected_server_surfaces_under_lock; then
    mark_remote_release_mutation_started
    exit 91
fi
test ! -e "$MUTATION_LOG"
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "MUTATION_LOG": str(mutation_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "服务器发布代际已变化" in result.stdout
    assert not mutation_log.exists()


def test_server_surface_cas_accepts_exact_generation_and_proof_identity(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    expected = [
        "a" * 40,
        "b" * 64,
        None,
        None,
        "e" * 40,
        "f" * 64,
        "1" * 64,
    ]
    payload = json.dumps(expected, separators=(",", ":"))
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_TOKEN=cas-owner
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REVA_EXPECTED_SERVER_SURFACES='{payload}'
python3() {{
    if [[ "$1" == *release_production_state.py ]]; then
        printf '%s\\n' '{payload}'
        return 0
    fi
    command python3 "$@"
}}
verify_expected_server_surfaces_under_lock
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_direct_server_deploy_binds_baseline_only_after_remote_lock() -> None:
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main = script[script.index("main() {") :]

    acquire = main.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    capture = main.index("capture_expected_server_surfaces_under_lock", acquire)
    bind = main.index("bind_expected_server_surfaces_under_lock", capture)
    compare = main.index("verify_expected_server_surfaces_under_lock")
    first_mutation = min(
        main.index("push_code", compare),
        main.index("sync_env", compare),
        main.index("reset_app_store_review_demo", compare),
    )

    assert 'REVA_RELEASE_COORDINATOR_BASELINE_DIGEST="-"' in main[:acquire]
    assert acquire < capture < bind < compare < first_mutation


def test_direct_server_deploy_captures_quiescent_baseline_when_not_supplied(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    expected = [
        "a" * 40,
        "b" * 64,
        None,
        None,
        "e" * 40,
        "f" * 64,
        "1" * 64,
    ]
    payload = json.dumps(expected, separators=(",", ":"))
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
unset REVA_EXPECTED_SERVER_SURFACES
REMOTE_RELEASE_LOCK_TOKEN=exact-owner
_REMOTE_RELEASE_LOCK_ACQUIRED=1
python3() {{
    if [[ "$1" = "$SCRIPT_DIR/scripts/release_production_state.py" ]]; then
        test "$2" = server-under-lock
        test "$3" = exact-owner
        printf '%s\\n' '{payload}'
        return
    fi
    command python3 "$@"
}}
capture_expected_server_surfaces_under_lock
test "$REVA_EXPECTED_SERVER_SURFACES" = '{payload}'
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_adopted_server_deploy_captures_baseline_with_exact_lock_token(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    expected = [
        "a" * 40,
        "b" * 64,
        "c" * 40,
        "d" * 64,
        None,
        None,
        None,
    ]
    payload = json.dumps(expected, separators=(",", ":"))
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
unset REVA_EXPECTED_SERVER_SURFACES
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN=handoff-token
REMOTE_RELEASE_LOCK_TOKEN=handoff-token
_REMOTE_RELEASE_LOCK_ACQUIRED=1
python3() {{
    if [[ "$1" = "$SCRIPT_DIR/scripts/release_production_state.py" ]]; then
        test "$2" = server-under-lock
        test "$3" = handoff-token
        printf '%s\\n' '{payload}'
        return
    fi
    command python3 "$@"
}}
capture_expected_server_surfaces_under_lock
test "$REVA_EXPECTED_SERVER_SURFACES" = '{payload}'
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_remote_unlock_rejects_unknown_entry_without_deleting_any_metadata(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    lock_dir = tmp_path / "remote-release.lock"
    _write_remote_release_lock(
        lock_dir,
        token="exact-owner",
        label="deploy:backend",
        stage=stage,
    )
    (lock_dir / "unexpected").write_text("do-not-delete\n", encoding="ascii")
    before = {
        path.name: path.read_bytes()
        for path in lock_dir.iterdir()
        if path.is_file()
    }
    context = _remote_release_context_shell(
        token="exact-owner",
        label="deploy:backend",
        stage=stage,
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
{context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
ssh() {{ shift; "$@"; }}
if release_remote_release_lock; then
    exit 91
fi
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert lock_dir.is_dir()
    assert {
        path.name: path.read_bytes()
        for path in lock_dir.iterdir()
        if path.is_file()
    } == before


def test_remote_unlock_atomically_detaches_exact_token_bound_lock(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    lock_dir = tmp_path / "remote-release.lock"
    _write_remote_release_lock(
        lock_dir,
        token="exact-owner",
        label="deploy:backend",
        stage=stage,
    )
    context = _remote_release_context_shell(
        token="exact-owner",
        label="deploy:backend",
        stage=stage,
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
{context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
ssh() {{ shift; "$@"; }}
release_remote_release_lock
test ! -e {lock_dir!s}
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not lock_dir.exists()


@pytest.mark.parametrize("failure_point", ("acquire", "mkdir", "scp", "chmod", "manifest"))
def test_abandoned_allocating_stage_is_safely_reaped_instead_of_wedging(
    tmp_path: Path, failure_point: str,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    if failure_point != "acquire":
        stage.mkdir(mode=0o700)
    if failure_point in {"scp", "chmod", "manifest"}:
        partial = stage / "backup_db.sh"
        partial.write_text("partial upload\n", encoding="utf-8")
        partial.chmod(0o700 if failure_point != "scp" else 0o600)
    if failure_point == "manifest":
        partial_manifest = stage / "staged.sha256"
        partial_manifest.write_text("partial manifest\n", encoding="utf-8")
        partial_manifest.chmod(0o600)
    lock_dir = tmp_path / "remote-release.lock"
    _write_remote_release_lock(
        lock_dir,
        token="partial-owner",
        label="deploy:backend",
        stage=stage,
        state="allocating",
    )
    context = _remote_release_context_shell(
        token="partial-owner",
        label="deploy:backend",
        stage=stage,
        state="allocating",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
{context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=1
ssh() {{ shift; "$@"; }}
cleanup_remote_release_artifacts
test ! -e {lock_dir!s}
test ! -e {stage!s}
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not lock_dir.exists()


def test_allocating_stage_with_unknown_entry_is_retained_byte_for_byte(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    unknown = stage / "attacker-file"
    unknown.write_bytes(b"retain exactly\n")
    unknown.chmod(0o600)
    lock_dir = tmp_path / "remote-release.lock"
    _write_remote_release_lock(
        lock_dir,
        token="partial-owner",
        label="deploy:backend",
        stage=stage,
        state="allocating",
    )
    lock_before = {
        path.name: path.read_bytes() for path in lock_dir.iterdir()
    }
    context = _remote_release_context_shell(
        token="partial-owner",
        label="deploy:backend",
        stage=stage,
        state="allocating",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
{context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=1
ssh() {{ shift; "$@"; }}
cleanup_remote_release_artifacts
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert unknown.read_bytes() == b"retain exactly\n"
        assert {
            path.name: path.read_bytes() for path in lock_dir.iterdir()
        } == lock_before
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def test_remote_lock_contract_pins_source_sha_and_lifecycle_state():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    acquire = script[
        script.index("acquire_remote_release_lock() {") : script.index(
            "assert_remote_release_lock() {"
        )
    ]

    assert '"source_sha"' in acquire
    assert '"source_tree"' in acquire
    assert '"state"' in acquire
    assert "REMOTE_RELEASE_LOCK_ADOPTED state=" in acquire
    assert "git merge-base --is-ancestor" in script


def test_mac_route_recovery_uses_a_sealed_token_bound_source_stage():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    bootstrap = script[
        script.index("bootstrap_mac_release_routes() {") : script.index(
            "\n}\n\nverify_mac_route_release_source()",
            script.index("bootstrap_mac_release_routes() {"),
        )
    ]

    assert "stage_mac_route_release_artifacts" in bootstrap
    assert "mark_remote_release_mutation_started" in bootstrap
    assert "mac-routes.source" in script
    assert "mac-routes.sha256" in script
    assert "REMOTE_RELEASE_SOURCE_TREE" in script
    assert bootstrap.index("stage_mac_route_release_artifacts") < bootstrap.index(
        "mark_remote_release_mutation_started"
    )
    assert bootstrap.index("mark_remote_release_mutation_started") < bootstrap.index(
        'REVA_MAC_BOOTSTRAP_ENTRYPOINT=deploy.sh'
    )


def test_remote_lock_recovery_protocol_accounts_for_orphan_siblings():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    contract = script[
        script.index("remote_release_lock_command() {") : script.index(
            "\n}\n\nassert_remote_release_lock()",
            script.index("remote_release_lock_command() {"),
        )
    ]

    assert 'f".{lock_name}.released-{token}"' in contract
    assert 'f".{lock_name}.alloc-{token}"' in contract
    assert "inspect_orphan_siblings" in contract
    assert "recover_orphan_for_explicit_owner" in contract


def test_release_tombstone_blocks_new_owner_and_original_owner_recovers(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    payload = stage / "mac-routes.source"
    payload.write_text("partial cleanup remains discoverable\n", encoding="ascii")
    payload.chmod(0o600)
    lock_dir = tmp_path / "remote-release.lock"
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    _write_remote_release_lock(
        lock_dir,
        token="original-owner",
        label="deploy:backend",
        stage=stage,
        source_sha=source_sha,
        source_tree=source_tree,
        state="mutating",
    )
    tombstone = lock_dir.with_name(
        f".{lock_dir.name}.released-original-owner"
    )
    lock_dir.rename(tombstone)
    before_lock = {
        path.name: path.read_bytes() for path in tombstone.iterdir()
    }
    before_stage = payload.read_bytes()
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
ssh() {{ shift; "$@"; }}
REVA_REMOTE_RELEASE_LOCK_TOKEN=new-owner
if acquire_remote_release_lock deploy:backend; then
    exit 91
fi
test -d {tombstone!s}
test -d {stage!s}
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN=original-owner
acquire_remote_release_lock deploy:backend
test "$_REMOTE_RELEASE_LOCK_ALREADY_RELEASED" = 1
test ! -e {lock_dir!s}
test ! -e {tombstone!s}
test ! -e {stage!s}
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert before_lock
    assert before_stage == b"partial cleanup remains discoverable\n"
    assert not lock_dir.exists()


@pytest.mark.parametrize("kind", ("creating", "phase", "releasing"))
def test_foreign_mac_lease_residue_blocks_generic_acquire_without_writes(
    tmp_path: Path, kind: str
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    lock_dir = tmp_path / "deploy.lock"
    residue = lock_dir.with_name(f".{lock_dir.name}.mac-{kind}-mac-owner")
    if kind == "phase":
        residue.write_bytes(b"mac phase remains exactly\n")
        residue.chmod(0o600)
    else:
        residue.mkdir(mode=0o700)
        marker = residue / "marker"
        marker.write_bytes(b"mac residue remains exactly\n")
        marker.chmod(0o600)
    before = (
        residue.read_bytes()
        if residue.is_file()
        else {path.name: path.read_bytes() for path in residue.iterdir()}
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
REVA_REMOTE_RELEASE_LOCK_TOKEN=generic-owner
ssh() {{ shift; "$@"; }}
if acquire_remote_release_lock deploy:backend; then
    exit 91
fi
test ! -e {lock_dir!s}
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    after = (
        residue.read_bytes()
        if residue.is_file()
        else {path.name: path.read_bytes() for path in residue.iterdir()}
    )
    assert after == before


@pytest.mark.parametrize("remaining_field_count", (0, 1, 4, 7))
def test_partial_release_tombstone_is_idempotently_reaped_by_original_owner(
    tmp_path: Path, remaining_field_count: int
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-app\n",
        encoding="utf-8",
    )
    lock_dir = tmp_path / "deploy.lock"
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    _write_remote_release_lock(
        lock_dir,
        token="partial-owner",
        label="deploy:backend",
        stage=stage,
        source_sha=source_sha,
        source_tree=source_tree,
        state="mutating",
    )
    tombstone = lock_dir.with_name(f".{lock_dir.name}.released-partial-owner")
    lock_dir.rename(tombstone)
    ordered = sorted(path.name for path in tombstone.iterdir())
    for name in ordered[remaining_field_count:]:
        (tombstone / name).unlink()
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN=partial-owner
ssh() {{ shift; "$@"; }}
acquire_remote_release_lock deploy:backend
test "$_REMOTE_RELEASE_LOCK_ALREADY_RELEASED" = 1
test ! -e {lock_dir!s}
test ! -e {tombstone!s}
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not tombstone.exists()
    assert not lock_dir.exists()


@pytest.mark.parametrize(
    "mode",
    (
        "all",
        "frontend",
        "backend",
        "env",
        "health-evidence",
        "app-store-review-reset",
        "restart",
    ),
)
def test_each_terminal_release_mode_arms_adopted_stage_cleanup(
    tmp_path: Path,
    mode: str,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=0
arm_remote_release_cleanup_after_terminal_mode_success {mode}
printf 'delegated=%s abandoned=%s\\n' \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "delegated=0 abandoned=0"


def test_terminal_release_mode_preserves_adopted_stage_while_delegated(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=1
arm_remote_release_cleanup_after_terminal_mode_success backend
rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "rc=73 delegated=1 abandoned=1" in result.stdout


def test_adopted_terminal_activation_proof_removes_stage_state_and_lease(
    tmp_path: Path,
):
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    state_dir = Path(f"{stage}.activation-state")
    for path in (stage, state_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(mode=0o700)
    (stage / "backup_db.sh").write_text("immutable\n", encoding="utf-8")
    (stage / "backup_db.sh").chmod(0o600)
    (state_dir / "success").write_text("terminal\n", encoding="utf-8")
    (state_dir / "success").chmod(0o600)
    remote_lock = tmp_path / "release.lock"
    token = "activation-owner"
    _write_remote_release_lock(
        remote_lock,
        token=token,
        label="deploy:health-evidence",
        stage=stage,
        state="mutating",
    )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={tmp_path / 'remote-app'}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    release_context = _remote_release_context_shell(
        token=token,
        label="deploy:health-evidence",
        stage=stage,
        state="mutating",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_RELEASE_LOCK_DIR={remote_lock}
{release_context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
ssh() {{
    shift
    "$@"
}}
require_health_evidence_flag_value() {{ return 0; }}
verify_deployed_revision() {{ return 0; }}
stage_health_evidence_activation_artifacts() {{ return 0; }}
prove_health_evidence_activation_state() {{ test "$1" = enabled; }}
verify_runtime_only_kb_contract() {{ exit 91; }}
verify_systemd_activation_capability() {{ exit 92; }}
run_health_evidence_activation_unit() {{ exit 93; }}
prove_health_evidence_activation_not_launched() {{ exit 94; }}
activate_health_evidence_runtime
test "$_REMOTE_RELEASE_LOCK_ABANDONED" = 0
test "$_REMOTE_RELEASE_LOCK_DELEGATED" = 0
cleanup_remote_release_artifacts
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )

        assert result.returncode == 0, (result.stdout, result.stderr)
        assert not stage.exists()
        assert not state_dir.exists()
        assert not remote_lock.exists()
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)


_ADOPTED_STAGE_ARTIFACTS = (
    ("backup_db.sh", "backend/scripts/backup_db.sh"),
    ("verify_backup_restore.sh", "backend/scripts/verify_backup_restore.sh"),
    ("archive_backup_offsite.sh", "backend/scripts/archive_backup_offsite.sh"),
    ("rollback_release.sh", "backend/scripts/rollback_release.sh"),
    (
        "verify_locked_requirements.py",
        "backend/scripts/verify_locked_requirements.py",
    ),
    (
        "activate_health_evidence_runtime.sh",
        "backend/scripts/activate_health_evidence_runtime.sh",
    ),
    (
        "verify_runtime_schema_compatibility.py",
        "backend/scripts/verify_runtime_schema_compatibility.py",
    ),
    (
        "quarantine_runtime_only_kb.py",
        "backend/scripts/quarantine_runtime_only_kb.py",
    ),
    (
        "runtime_state_release_transaction.py",
        "backend/scripts/runtime_state_release_transaction.py",
    ),
    (
        "review_manifest.json",
        "backend/data/system_kb_v2_seed/review_manifest.json",
    ),
    (
        "health-backend-runtime-state.conf",
        "infra/systemd/dropins/health-backend-runtime-state.conf",
    ),
    (
        "celery-worker-runtime-state.conf",
        "infra/systemd/dropins/celery-worker-runtime-state.conf",
    ),
    (
        "celery-beat-runtime-state.conf",
        "infra/systemd/dropins/celery-beat-runtime-state.conf",
    ),
)


def _write_immutable_adopted_stage(
    stage: Path,
    *,
    source_repo: Path,
    release_sha: str,
    candidate_env: bytes,
) -> None:
    stage.mkdir(mode=0o700)
    for staged_name, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        payload = subprocess.check_output(
            ["git", "show", f"{release_sha}:{repository_path}"],
            cwd=source_repo,
        )
        target = stage / staged_name
        target.write_bytes(payload)
        target.chmod(0o400)
    for name, payload in (
        ("backend.env.rollback", candidate_env),
        ("backend.env.candidate", candidate_env),
    ):
        target = stage / name
        target.write_bytes(payload)
        target.chmod(0o400)
    subprocess.run(
        ["git", "bundle", "create", str(stage / "deploy.bundle"), "main"],
        cwd=source_repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (stage / "deploy.bundle").chmod(0o600)

    manifest_lines = []
    for path in sorted(stage.iterdir(), key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.name}")
    manifest = stage / "staged.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    manifest.chmod(0o400)


def _immutable_stage_snapshot(
    stage: Path,
) -> tuple[int, int, dict[str, tuple[int, str, bytes]]]:
    files = {}
    for path in sorted(stage.iterdir(), key=lambda item: item.name):
        payload = path.read_bytes()
        files[path.name] = (
            path.stat().st_ino,
            hashlib.sha256(payload).hexdigest(),
            payload,
        )
    metadata = stage.stat()
    return metadata.st_ino, metadata.st_mtime_ns, files


def _run_adopted_release_stage_harness(
    tmp_path: Path,
    *,
    scenario: str,
) -> dict[str, object]:
    source_repo = tmp_path / "release-source"
    source_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=source_repo,
        check=True,
    )
    for _, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        target = source_repo / repository_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repository_path).read_bytes())
    subprocess.run(["git", "add", "."], cwd=source_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "release fixture"],
        cwd=source_repo,
        check=True,
    )
    release_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        text=True,
    ).strip()
    old_sha = "1" * 40
    status_candidate_sha = (
        "f" * 40 if scenario == "wrong-sha" else release_sha
    )
    if status_candidate_sha == old_sha:
        old_sha = "2" * 40

    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    candidate_env = (
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        b"HEALTH_RUNTIME_DATA_DIR=/var/lib/health-app/runtime\n"
        b"HEALTH_UPLOAD_DIR=/var/lib/health-app/uploads\n"
        b"HEALTH_SKILLS_CACHE_DIR=/var/cache/health-app/skills-hub\n"
        b"DEDAO_KBASE_REVIEW_ARTIFACT_DIR="
        b"/var/lib/health-app/dedao-kbase/workspace\n"
        b"LEGACY_KNOWLEDGE_RUNTIME_ENABLED=false\n"
    )
    _write_immutable_adopted_stage(
        stage,
        source_repo=source_repo,
        release_sha=release_sha,
        candidate_env=candidate_env,
    )
    if scenario == "unsealed-allowed-name":
        unsealed = stage / "candidate.env"
        unsealed.write_bytes(candidate_env)
        unsealed.chmod(0o400)
    stage_before = _immutable_stage_snapshot(stage)

    remote_path = tmp_path / "remote-app"
    (remote_path / "backend").mkdir(parents=True)
    (remote_path / "backend/.env").write_bytes(candidate_env)
    remote_lock = tmp_path / "remote-release.lock"
    token = "resume-owner"
    label = "deploy:backend"
    release_tree = subprocess.check_output(
        ["git", "rev-parse", f"{release_sha}^{{tree}}"],
        cwd=source_repo,
        text=True,
    ).strip()
    _write_remote_release_lock(
        remote_lock,
        token=token,
        label=label,
        stage=stage,
        source_sha=release_sha,
        source_tree=release_tree,
        state="sealed",
    )

    attempted_token = "wrong-owner" if scenario == "wrong-token" else token
    attempted_label = (
        "deploy:frontend" if scenario == "wrong-label" else label
    )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={remote_path}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    event_log = tmp_path / "adoption.events"
    proof_file = tmp_path / "adoption.proof"
    mkdir_log = tmp_path / "mkdir.events"
    scp_log = tmp_path / "scp.events"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
case "$target" in
  "$FAKE_ADOPTED_STAGE") printf 'root:root:700\n' ;;
  "$FAKE_ADOPTED_STAGE/staged.sha256"|\
"$FAKE_ADOPTED_STAGE/backend.env.candidate"|\
staged.sha256|backend.env.candidate)
    printf 'root:root:400\n'
    ;;
  *) exit 97 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "mkdir",
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_MKDIR_LOG"
exec /bin/mkdir "$@"
""",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
SCRIPT_DIR="$FAKE_SOURCE_REPO"
REMOTE_RELEASE_LOCK_DIR="$FAKE_REMOTE_LOCK"
REVA_REMOTE_RELEASE_LOCK_ADOPT=1
REVA_REMOTE_RELEASE_LOCK_TOKEN="$ATTEMPTED_TOKEN"
set_remote_backup_preflight_dir "$FAKE_ADOPTED_STAGE"
REVA_RELEASE_COORDINATOR_SOURCE_SHA="$EXPECTED_RELEASE_SHA"
REVA_RELEASE_COORDINATOR_SOURCE_TREE="$EXPECTED_RELEASE_TREE"
REVA_RELEASE_COORDINATOR_SURFACE=server
REVA_RELEASE_COORDINATOR_OPERATION=backend
REVA_RELEASE_COORDINATOR_CHANNEL=production
REVA_RELEASE_COORDINATOR_TRANSACTION={'c' * 32}
REVA_RELEASE_COORDINATOR_BASELINE_DIGEST={'d' * 64}
REVA_RELEASE_COORDINATOR_REQUEST_DIGEST={'e' * 64}
DEPLOY_EXPECTED_SHA="$EXPECTED_RELEASE_SHA"
ssh() {{
    shift
    if [ "${{1:-}}" = /usr/bin/python3 ]; then
        "$@"
        return
    fi
    if [ "${{1:-}}" = bash ] && [ "${{2:-}}" = -s ]; then
        "$@"
        return
    fi
    if [ "$#" -eq 1 ]; then
        case "$1" in
          *"rev-parse HEAD"*) printf '%s\\n' "$FAKE_REMOTE_HEAD" ;;
          *) bash -c "$1" ;;
        esac
        return
    fi
    "$@"
}}
scp() {{
    printf '%s\\n' "$*" >> "$FAKE_SCP_LOG"
    return 99
}}
run_runtime_state_transaction() {{
    test "$1" = status
    printf '%s\\n' \
      "RUNTIME_STATE_TRANSACTION_OK command=status result=phase=PREPARED old_sha=$STATUS_OLD_SHA candidate_sha=$STATUS_CANDIDATE_SHA gate_armed=true gate_released=false release_target=none next_action=install state_source=journal"
}}

printf 'acquire\\n' >> "$ADOPTION_EVENT_LOG"
if acquire_remote_release_lock "$ATTEMPTED_LABEL"; then
    :
else
    acquire_rc=$?
    printf 'acquire-failed:%s\\n' "$acquire_rc" >> "$ADOPTION_EVENT_LOG"
    exit 81
fi
test "$REMOTE_BACKUP_PREFLIGHT_DIR" = "$FAKE_ADOPTED_STAGE"
test "$REMOTE_RUNTIME_STATE_RUNNER" = \
    "$FAKE_ADOPTED_STAGE/runtime_state_release_transaction.py"
printf 'stage\\n' >> "$ADOPTION_EVENT_LOG"
if stage_backup_preflight_scripts; then
    :
else
    stage_rc=$?
    printf 'stage-failed:%s\\n' "$stage_rc" >> "$ADOPTION_EVENT_LOG"
    exit 82
fi
printf 'inspect\\n' >> "$ADOPTION_EVENT_LOG"
if inspect_runtime_state_transaction_before_deploy; then
    :
else
    inspect_rc=$?
    printf 'inspect-failed:%s\\n' "$inspect_rc" >> "$ADOPTION_EVENT_LOG"
    exit 83
fi
printf 'stage=%s adopted=%s phase=%s candidate=%s\\n' \
    "$REMOTE_BACKUP_PREFLIGHT_DIR" \
    "$_REMOTE_RELEASE_LOCK_ADOPTED" \
    "$RUNTIME_STATE_RESUME_PHASE" \
    "$STATUS_CANDIDATE_SHA" \
    > "$ADOPTION_PROOF_FILE"
printf 'complete\\n' >> "$ADOPTION_EVENT_LOG"
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=source_repo,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DEPLOY_ENV_FILE": str(env_file),
                "FAKE_REMOTE_LOCK": str(remote_lock),
                "FAKE_SOURCE_REPO": str(source_repo),
                "FAKE_ADOPTED_STAGE": str(stage),
                "FAKE_REMOTE_HEAD": old_sha,
                "FAKE_MKDIR_LOG": str(mkdir_log),
                "FAKE_SCP_LOG": str(scp_log),
                "ADOPTION_EVENT_LOG": str(event_log),
                "ADOPTION_PROOF_FILE": str(proof_file),
                "ATTEMPTED_TOKEN": attempted_token,
                "ATTEMPTED_LABEL": attempted_label,
                "EXPECTED_RELEASE_SHA": release_sha,
                "EXPECTED_RELEASE_TREE": release_tree,
                "STATUS_OLD_SHA": old_sha,
                "STATUS_CANDIDATE_SHA": status_candidate_sha,
            },
        )
        stage_after = _immutable_stage_snapshot(stage)
        return {
            "result": result,
            "stage": str(stage),
            "stage_before": stage_before,
            "stage_after": stage_after,
            "events": (
                event_log.read_text(encoding="utf-8").splitlines()
                if event_log.exists()
                else []
            ),
            "proof": (
                proof_file.read_text(encoding="utf-8")
                if proof_file.exists()
                else ""
            ),
            "mkdir_calls": (
                mkdir_log.read_text(encoding="utf-8").splitlines()
                if mkdir_log.exists()
                else []
            ),
            "scp_calls": (
                scp_log.read_text(encoding="utf-8").splitlines()
                if scp_log.exists()
                else []
            ),
        }
    finally:
        shutil.rmtree(stage)


def test_remote_adoption_namespace_survives_the_real_local_lock_guardian(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-{tmp_path.stat().st_ino}"
    )
    lock_dir = tmp_path / "remote-release.lock"
    token = "retained-owner-token"
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    _write_remote_release_lock(
        lock_dir,
        token=token,
        label="deploy:backend",
        stage=stage,
        source_sha=source_sha,
        source_tree=source_tree,
        state="sealed",
    )
    harness = tmp_path / "guardian-entrypoint.sh"
    _write_executable(
        harness,
        f"""#!/usr/bin/env bash
set -euo pipefail
{DEPLOY_SOURCE_FOR_TESTS}
_REVA_RELEASE_CALLER="$0"
_REVA_RELEASE_CALLER_ARGS=(resume)
acquire_release_lock remote-adoption-entrypoint
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
set_remote_backup_preflight_dir {stage!s}
REVA_RELEASE_COORDINATOR_SOURCE_SHA={source_sha}
REVA_RELEASE_COORDINATOR_SOURCE_TREE={source_tree}
REVA_RELEASE_COORDINATOR_SURFACE=server
REVA_RELEASE_COORDINATOR_OPERATION=backend
REVA_RELEASE_COORDINATOR_CHANNEL=production
REVA_RELEASE_COORDINATOR_TRANSACTION={'c' * 32}
REVA_RELEASE_COORDINATOR_BASELINE_DIGEST={'d' * 64}
REVA_RELEASE_COORDINATOR_REQUEST_DIGEST={'e' * 64}
ssh() {{ shift; "$@"; }}
acquire_remote_release_lock deploy:backend
test "$_REMOTE_RELEASE_LOCK_ADOPTED" = 1
test "$REMOTE_RELEASE_LOCK_TOKEN" = {token}
test "$REMOTE_BACKUP_PREFLIGHT_DIR" = {stage!s}
_REMOTE_RELEASE_LOCK_ABANDONED=0
release_remote_release_lock
""",
    )

    result = subprocess.run(
        [str(harness)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "REVA_REMOTE_RELEASE_LOCK_ADOPT": "1",
            "REVA_REMOTE_RELEASE_LOCK_TOKEN": token,
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not lock_dir.exists()


def test_successful_entrypoint_reports_remote_unlock_failure(tmp_path: Path) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ABANDONED=0
_REMOTE_RELEASE_LOCK_DELEGATED=0
ssh() {{ return 0; }}
release_remote_release_lock() {{ return 73; }}
install_release_cleanup_traps
exit 0
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 73, (result.stdout, result.stderr)


def test_existing_remote_release_is_adopted_without_mutating_immutable_stage(
    tmp_path: Path,
):
    outcome = _run_adopted_release_stage_harness(
        tmp_path,
        scenario="valid",
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert outcome["events"] == ["acquire", "stage", "inspect", "complete"]
    assert (
        f"stage={outcome['stage']} adopted=1 phase=PREPARED"
        in outcome["proof"]
    )
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["scp_calls"] == []
    assert all(outcome["stage"] not in call for call in outcome["mkdir_calls"])


@pytest.mark.parametrize(
    ("scenario", "expected_returncode", "expected_events"),
    (
        ("wrong-token", 81, ("acquire", "acquire-failed:73")),
        ("wrong-label", 81, ("acquire", "acquire-failed:73")),
        (
            "wrong-sha",
            83,
            ("acquire", "stage", "inspect", "inspect-failed:1"),
        ),
        (
            "unsealed-allowed-name",
            82,
            ("acquire", "stage", "stage-failed:1"),
        ),
    ),
)
def test_existing_remote_release_adoption_fails_closed_on_identity_mismatch(
    tmp_path: Path,
    scenario: str,
    expected_returncode: int,
    expected_events: tuple[str, ...],
):
    outcome = _run_adopted_release_stage_harness(
        tmp_path,
        scenario=scenario,
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == expected_returncode, (
        result.stdout,
        result.stderr,
    )
    assert outcome["events"] == list(expected_events)
    assert outcome["proof"] == ""
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["scp_calls"] == []
    assert all(outcome["stage"] not in call for call in outcome["mkdir_calls"])


def _run_adopted_activation_stage_harness(
    tmp_path: Path,
    *,
    terminal: bool,
) -> dict[str, object]:
    source_repo = tmp_path / "activation-release-source"
    source_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=source_repo,
        check=True,
    )
    for _, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        target = source_repo / repository_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repository_path).read_bytes())
    subprocess.run(["git", "add", "."], cwd=source_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "activation release fixture"],
        cwd=source_repo,
        check=True,
    )
    release_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        text=True,
    ).strip()

    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    for staged_name, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        payload = subprocess.check_output(
            ["git", "show", f"{release_sha}:{repository_path}"],
            cwd=source_repo,
        )
        target = stage / staged_name
        target.write_bytes(payload)
        target.chmod(0o400)

    candidate = (
        b"APP_ENV=production\n"
        b"DEBUG=False\n"
        b"HEALTH_RUNTIME_DATA_DIR=/var/lib/health-app/runtime\n"
        b"HEALTH_UPLOAD_DIR=/var/lib/health-app/uploads\n"
        b"HEALTH_SKILLS_CACHE_DIR=/var/cache/health-app/skills-hub\n"
        b"DEDAO_KBASE_REVIEW_ARTIFACT_DIR="
        b"/var/lib/health-app/dedao-kbase/workspace\n"
        b"LEGACY_KNOWLEDGE_RUNTIME_ENABLED=false\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    guard = candidate.replace(
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false",
    )
    for name, payload in (("candidate.env", candidate), ("guard.env", guard)):
        target = stage / name
        target.write_bytes(payload)
        target.chmod(0o400)
    subprocess.run(
        ["git", "bundle", "create", str(stage / "deploy.bundle"), "main"],
        cwd=source_repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (stage / "deploy.bundle").chmod(0o600)
    manifest_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(stage.iterdir(), key=lambda item: item.name)
    ]
    manifest = stage / "staged.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    manifest.chmod(0o400)

    state_dir = Path(f"{stage}.activation-state")
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(mode=0o700)
    if terminal:
        terminal_payloads = {
            "launch-intent": (
                f"commit={release_sha}\n"
                "unit=health-evidence-activation-"
                f"{release_sha[:12]}-4242.service\n"
                "lease_sha256="
                f"{hashlib.sha256(b'activation-owner').hexdigest()}\n"
            ),
            "success": "terminal-success\n",
            "success.outcome": "terminal-outcome\n",
        }
        for name, payload in terminal_payloads.items():
            target = state_dir / name
            target.write_text(payload, encoding="utf-8")
            target.chmod(0o400)

    remote_path = tmp_path / "remote-app"
    (remote_path / "backend").mkdir(parents=True)
    (remote_path / "backend/.env").write_bytes(guard)
    remote_lock = tmp_path / "activation-release.lock"
    release_tree = subprocess.check_output(
        ["git", "rev-parse", f"{release_sha}^{{tree}}"],
        cwd=source_repo,
        text=True,
    ).strip()
    _write_remote_release_lock(
        remote_lock,
        token="activation-owner",
        label="deploy:health-evidence",
        stage=stage,
        source_sha=release_sha,
        source_tree=release_tree,
        state="sealed",
    )
    env_file = tmp_path / "activation.env"
    env_file.write_bytes(
        b"DEPLOY_SERVER=fake-server\n"
        + f"DEPLOY_PATH={remote_path}\n".encode()
        + candidate
    )
    scp_log = tmp_path / "activation.scp"
    mkdir_log = tmp_path / "activation.mkdir"
    fake_bin = tmp_path / "activation-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "stat",
        """#!/bin/bash
set -euo pipefail
format="$2"
target="${@: -1}"
case "$format" in
  %U:%G:%a)
    if [ -d "$target" ]; then
      printf 'root:root:700\n'
    else
      printf 'root:root:400\n'
    fi
    ;;
  %h) printf '1\n' ;;
  *) exit 97 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "mkdir",
        """#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_ACTIVATION_MKDIR_LOG"
exec /bin/mkdir "$@"
""",
    )
    stage_before = _immutable_stage_snapshot(stage)
    state_before = _immutable_stage_snapshot(state_dir)
    release_context = _remote_release_context_shell(
        token="activation-owner",
        label="deploy:health-evidence",
        stage=stage,
        source_sha=release_sha,
        source_tree=release_tree,
        state="sealed",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
DEPLOY_EXPECTED_SHA="$FAKE_ACTIVATION_SHA"
REMOTE_RELEASE_LOCK_DIR="$FAKE_ACTIVATION_LOCK"
{release_context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
validate_env_sync_safety() {{ return 0; }}
validate_langbridge_env() {{ return 0; }}
ssh() {{
    shift
    if [ "${{1:-}}" = /usr/bin/python3 ]; then
        "$@"
        return
    fi
    if [ "${{1:-}}" = bash ] && [ "${{2:-}}" = -s ]; then
        "$@"
        return
    fi
    test "$#" -eq 1
    bash -c "$1"
}}
scp() {{
    if [ "${{1:-}}" = -q ]; then shift; fi
    test "$#" -eq 2
    source_path="$1"
    target_path="$2"
    case "$source_path" in
      fake-server.invalid:*)
        printf 'download:%s\\n' "${{source_path#fake-server.invalid:}}" \
            >> "$FAKE_ACTIVATION_SCP_LOG"
        cp "${{source_path#fake-server.invalid:}}" "$target_path"
        ;;
      *)
        printf 'upload:%s\\n' "$source_path" \
            >> "$FAKE_ACTIVATION_SCP_LOG"
        return 99
        ;;
    esac
}}
stage_health_evidence_activation_artifacts
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=source_repo,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DEPLOY_ENV_FILE": str(env_file),
                "FAKE_ACTIVATION_STAGE": str(stage),
                "FAKE_ACTIVATION_SHA": release_sha,
                "FAKE_ACTIVATION_TREE": release_tree,
                "FAKE_ACTIVATION_LOCK": str(remote_lock),
                "FAKE_ACTIVATION_SCP_LOG": str(scp_log),
                "FAKE_ACTIVATION_MKDIR_LOG": str(mkdir_log),
            },
        )
        return {
            "result": result,
            "stage_before": stage_before,
            "stage_after": _immutable_stage_snapshot(stage),
            "state_before": state_before,
            "state_after": _immutable_stage_snapshot(state_dir),
            "scp": (
                scp_log.read_text(encoding="utf-8").splitlines()
                if scp_log.exists()
                else []
            ),
            "mkdir": (
                mkdir_log.read_text(encoding="utf-8").splitlines()
                if mkdir_log.exists()
                else []
            ),
        }
    finally:
        shutil.rmtree(stage)
        shutil.rmtree(state_dir)


@pytest.mark.parametrize("terminal", (False, True))
def test_adopted_activation_stage_is_read_only_for_empty_and_terminal_state(
    tmp_path: Path,
    terminal: bool,
):
    outcome = _run_adopted_activation_stage_harness(
        tmp_path,
        terminal=terminal,
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["state_after"] == outcome["state_before"]
    assert outcome["mkdir"] == []
    assert len(outcome["scp"]) == 2
    assert all(call.startswith("download:") for call in outcome["scp"])


def _run_deactivation_orchestrator_harness(
    tmp_path: Path,
    *,
    transaction_ok: bool,
    proof_ok: bool,
    inactive_ok: bool,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "deploy-deactivation.env"
    event_log = tmp_path / "deactivation.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=test-owner
assert_remote_release_lock() {{ :; }}
run_health_evidence_deactivation_transaction() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_TRANSACTION_OK" = "1" ]
}}
prove_health_evidence_deactivated_state() {{
    printf 'prove\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_PROOF_OK" = "1" ]
}}
prove_health_evidence_services_inactive() {{
    printf 'inactive-proof\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_INACTIVE_OK" = "1" ]
}}
deactivate_health_evidence_runtime_before_mutation
deactivation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$deactivation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$DEACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEACTIVATION_EVENT_LOG": str(event_log),
            "DEACTIVATION_TRANSACTION_OK": "1" if transaction_ok else "0",
            "DEACTIVATION_PROOF_OK": "1" if proof_ok else "0",
            "DEACTIVATION_INACTIVE_OK": "1" if inactive_ok else "0",
        },
    )
    return result, event_log.read_text(encoding="utf-8").splitlines()


def test_deactivation_orchestrator_clears_delegation_only_after_exact_proof(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=True,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_deactivation_orchestrator_rejects_lost_ssh_even_if_state_proof_passes(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_deactivation_orchestrator_preserves_lease_and_stage_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=False,
        inactive_ok=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def _run_deactivation_transaction_fixture(
    tmp_path: Path,
    *,
    fail_candidate_sync: bool,
    live_flag: str | None = "false",
    authorization_enabled: bool = True,
    process_flag: str | None = "true",
    dirty_auth_artifact: str | None = None,
    dirty_process_unit: str | None = None,
    dirty_process_flag: str = "true",
    dirty_process_child_unit: str | None = None,
    drop_lease_after_candidate_sync: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    old_env = backend / ".env"
    old_env_text = "CONFIG_REVISION=old\n"
    if live_flag is not None:
        old_env_text += f"HEALTH_EVIDENCE_RUNTIME_ENABLED={live_flag}\n"
    old_env.write_text(old_env_text, encoding="utf-8")
    stage = tmp_path / "stage"
    stage.mkdir()
    candidate = stage / "backend.env.candidate"
    candidate.write_text(
        "CONFIG_REVISION=new\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    candidate.chmod(0o400)
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    durable = tmp_path / "durable"
    runtime_state = tmp_path / "runtime-state"
    systemd_runtime = tmp_path / "systemd-runtime"
    systemd_runtime.mkdir()
    dirty_auth_artifacts = (
        {
            "durable",
            "runtime_state",
            "backend_dropin",
            "worker_dropin",
            "beat_dropin",
        }
        if authorization_enabled
        else ({dirty_auth_artifact} if dirty_auth_artifact else set())
    )
    if "durable" in dirty_auth_artifacts:
        durable.mkdir()
        (durable / "enabled.env").write_text(
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
            encoding="utf-8",
        )
    elif "durable_symlink" in dirty_auth_artifacts:
        durable.mkdir()
        (durable / "enabled.env").symlink_to(
            tmp_path / "missing-durable-authorization"
        )
    if "runtime_state" in dirty_auth_artifacts:
        runtime_state.mkdir()
        (runtime_state / "enabled.env").write_text(
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
            encoding="utf-8",
        )
    elif "runtime_state_symlink" in dirty_auth_artifacts:
        runtime_state.symlink_to(
            tmp_path / "missing-runtime-state",
            target_is_directory=True,
        )
    dirty_dropins = {
        "backend_dropin": "health-backend.service",
        "worker_dropin": "celery-worker.service",
        "beat_dropin": "celery-beat.service",
        "backend_dropin_symlink": "health-backend.service",
        "backend_dropin_dir_symlink": "health-backend.service",
    }
    for artifact, unit in dirty_dropins.items():
        if artifact in dirty_auth_artifacts:
            unit_dir = systemd_runtime / f"{unit}.d"
            if artifact.endswith("_dir_symlink"):
                unit_dir.symlink_to(
                    tmp_path / "missing-runtime-override-dir",
                    target_is_directory=True,
                )
                continue
            unit_dir.mkdir()
            override = (
                unit_dir / "90-reva-health-evidence-activation.conf"
            )
            if artifact.endswith("_symlink"):
                override.symlink_to(tmp_path / "missing-runtime-override")
            else:
                override.write_text(
                    "[Service]\nEnvironmentFile=/tmp/runtime-enabled.env\n",
                    encoding="utf-8",
                )
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "deactivation-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    service_state = tmp_path / "service-state"
    service_state.mkdir()
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    unit_pids = {
        "health-backend": 3101,
        "celery-worker": 3201,
        "celery-beat": 3301,
    }
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        (service_state / f"{unit}.state").write_text(
            "active\n", encoding="utf-8"
        )
    for unit, pid in unit_pids.items():
        group = cgroup_root / "system.slice" / f"{unit}.service"
        group.mkdir(parents=True)
        cgroup_pids = [pid]
        if dirty_process_child_unit == unit:
            cgroup_pids.append(pid + 50)
        (group / "cgroup.procs").write_text(
            "".join(f"{process_pid}\n" for process_pid in cgroup_pids),
            encoding="utf-8",
        )
        process = proc_root / str(pid)
        process.mkdir()
        process_env = b"PATH=/usr/bin\0"
        unit_process_flag = process_flag
        if dirty_process_unit == unit:
            unit_process_flag = dirty_process_flag
        if unit_process_flag is not None:
            process_env += (
                "HEALTH_EVIDENCE_RUNTIME_ENABLED="
                f"{unit_process_flag}\0"
            ).encode()
        (process / "environ").write_bytes(process_env)
        if dirty_process_child_unit == unit:
            child_process = proc_root / str(pid + 50)
            child_process.mkdir()
            child_process_env = (
                b"PATH=/usr/bin\0"
                b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0"
            )
            (child_process / "environ").write_bytes(child_process_env)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    event_log = tmp_path / "deactivation-transaction.events"
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/bash
set -euo pipefail
normalize() { printf '%s' "${1%.service}"; }
state_file() { printf '%s/%s.state' "$FAKE_STATE_DIR" "$(normalize "$1")"; }
pid_for() {
  case "$(normalize "$1")" in
    health-backend) printf '3101' ;;
    celery-worker) printf '3201' ;;
    celery-beat) printf '3301' ;;
    *) printf '0' ;;
  esac
}
case "$1" in
  stop)
    unit="$2"
    printf 'stop:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  start)
    unit="$2"
    printf 'start:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'active\n' > "$(state_file "$unit")"
    pid="$(pid_for "$unit")"
    if [ "$pid" != "0" ]; then
      printf 'PATH=/usr/bin\\0HEALTH_EVIDENCE_RUNTIME_ENABLED=false\\0' \
        > "$FAKE_PROC_ROOT/$pid/environ"
    fi
    ;;
  show)
    unit="$2"
    case "$*" in
      *--property=ActiveState*) cat "$(state_file "$unit")" ;;
      *--property=MainPID*) pid_for "$unit"; printf '\n' ;;
      *--property=ControlGroup*)
        printf '/system.slice/%s.service\n' "$(normalize "$unit")"
        ;;
      *) exit 93 ;;
    esac
    ;;
  kill)
    unit="${@: -1}"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  daemon-reload) exit 0 ;;
  *) exit 92 ;;
esac
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
cp "$source" "$target"
chmod 0640 "$target"
printf 'install:%s\n' "$target" >> "$FAKE_EVENT_LOG"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
case "$target" in
  *backend.env.candidate) printf 'root:root:400\n' ;;
  */backend/.env|*/backend/.env.reva-release.tmp)
    printf 'root:health-app:640\n'
    ;;
  *) printf 'root:root:700\n' ;;
esac
""",
    )
    _write_executable(
        bin_dir / "sync",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-f"
if [ "${FAKE_FAIL_CANDIDATE_SYNC:-0}" = "1" ] &&
   [[ "$2" == *".env.reva-release.tmp" ]]; then
  exit 88
fi
test -e "$2"
printf 'sync:%s\n' "$2" >> "$FAKE_EVENT_LOG"
if [ "${FAKE_DROP_LEASE_AFTER_CANDIDATE_SYNC:-0}" = "1" ] &&
   [[ "$2" == *".env.reva-release.tmp" ]]; then
  rm -f "$FAKE_RELEASE_TOKEN_FILE"
fi
""",
    )
    _write_executable(
        bin_dir / "mv",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-fT"
/bin/mv "$2" "$3"
""",
    )
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
REMOTE_BACKEND_ENV_CANDIDATE={candidate}
REMOTE_BACKEND_ENV_CANDIDATE_SHA={candidate_hash}
REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR={durable}
REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR={runtime_state}
REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR={systemd_runtime}
REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT={cgroup_root}
REMOTE_HEALTH_EVIDENCE_PROC_ROOT={proc_root}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
ssh() {{ shift; "$@"; }}
run_health_evidence_deactivation_transaction
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_STATE_DIR": str(service_state),
            "FAKE_PROC_ROOT": str(proc_root),
            "FAKE_EVENT_LOG": str(event_log),
            "FAKE_FAIL_CANDIDATE_SYNC": (
                "1" if fail_candidate_sync else "0"
            ),
            "FAKE_DROP_LEASE_AFTER_CANDIDATE_SYNC": (
                "1" if drop_lease_after_candidate_sync else "0"
            ),
            "FAKE_RELEASE_TOKEN_FILE": str(release_lock / "token"),
        },
    )
    return result, {
        "old_env": old_env,
        "candidate": candidate,
        "durable": durable,
        "runtime_state": runtime_state,
        "service_state": service_state,
        "proc_root": proc_root,
        "event_log": event_log,
    }


def test_deactivation_transaction_atomically_installs_then_proves_false(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert paths["old_env"].read_bytes() == paths["candidate"].read_bytes()
    assert not (paths["durable"] / "enabled.env").exists()
    assert not paths["runtime_state"].exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "active"
    for pid in (3101, 3201, 3301):
        assert b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0" in (
            paths["proc_root"] / str(pid) / "environ"
        ).read_bytes()


def test_deactivation_sync_failure_keeps_old_env_and_contains_services(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=True,
    )

    assert result.returncode != 0
    assert paths["old_env"].read_text(encoding="utf-8").startswith(
        "CONFIG_REVISION=old\n"
    )
    assert not (paths["durable"] / "enabled.env").exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"
    assert "start:" not in paths["event_log"].read_text(encoding="utf-8")


def test_deactivation_bootstraps_missing_legacy_flag_only_when_unset_everywhere(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert paths["old_env"].read_bytes() == paths["candidate"].read_bytes()
    events = paths["event_log"].read_text(encoding="utf-8").splitlines()
    install_index = next(
        index for index, event in enumerate(events) if event.startswith("install:")
    )
    assert all(
        events.index(f"stop:{unit}") < install_index
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    )
    assert all(
        events.index(f"start:{unit}") > install_index
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    )


def test_deactivation_bootstrap_sync_failure_contains_legacy_services(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=True,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    events = paths["event_log"].read_text(encoding="utf-8")
    assert "start:" not in events
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"


def test_deactivation_bootstrap_lost_lease_before_rename_keeps_legacy_env(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        drop_lease_after_candidate_sync=True,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    events = paths["event_log"].read_text(encoding="utf-8")
    assert "start:" not in events
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"


@pytest.mark.parametrize(
    "dirty_auth_artifact",
    (
        "durable",
        "runtime_state",
        "backend_dropin",
        "worker_dropin",
        "beat_dropin",
        "durable_symlink",
        "runtime_state_symlink",
        "backend_dropin_symlink",
        "backend_dropin_dir_symlink",
    ),
)
def test_deactivation_rejects_each_legacy_authorization_artifact(
    tmp_path: Path,
    dirty_auth_artifact: str,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_auth_artifact=dirty_auth_artifact,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("dirty_process_unit", "dirty_process_flag"),
    (
        ("health-backend", "true"),
        ("celery-worker", "true"),
        ("celery-beat", "true"),
        ("health-backend", "false"),
    ),
)
def test_deactivation_rejects_each_legacy_process_assignment(
    tmp_path: Path,
    dirty_process_unit: str,
    dirty_process_flag: str,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_process_unit=dirty_process_unit,
        dirty_process_flag=dirty_process_flag,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


def test_deactivation_rejects_dirty_child_process_in_legacy_cgroup(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_process_child_unit="celery-worker",
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


def _run_activation_orchestrator_harness(
    tmp_path: Path,
    *,
    proof_mode: str,
    adopted: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / f"deploy-{proof_mode}.env"
    event_log = tmp_path / f"activation-{proof_mode}.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    coordinator_context = _remote_release_context_shell(
        token="test-owner",
        label="deploy:health-evidence",
        stage=Path("/tmp/health-app-backup-preflight-4242-4242"),
        source_sha="a" * 40,
        source_tree="b" * 40,
        state="sealed",
    )
    harness = f"""
{DEPLOY_SOURCE_FOR_TESTS}
set +e
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
{coordinator_context}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED={"1" if adopted else "0"}
_REMOTE_RELEASE_LOCK_ABANDONED={"1" if adopted else "0"}
verify_deployed_revision() {{ printf 'revision\\n' >> "$ACTIVATION_EVENT_LOG"; }}
verify_runtime_only_kb_contract() {{
    printf 'contract:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
}}
verify_systemd_activation_capability() {{
    printf 'systemd-capability\\n' >> "$ACTIVATION_EVENT_LOG"
}}
stage_health_evidence_activation_artifacts() {{
    printf 'stage\\n' >> "$ACTIVATION_EVENT_LOG"
}}
ACTIVATION_LAUNCHED=0
run_health_evidence_activation_unit() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$ACTIVATION_EVENT_LOG"
    ACTIVATION_LAUNCHED=1
    [ "$ACTIVATION_PROOF_MODE" = "success" ] ||
        [ "$ACTIVATION_PROOF_MODE" = "adopted-not-launched" ]
}}
prove_health_evidence_activation_state() {{
    printf 'prove:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
    case "$ACTIVATION_PROOF_MODE:$1" in
        success:enabled|recovered:staged|adopted-success:enabled|\
adopted-recovered:staged)
            return 0
            ;;
        adopted-not-launched:enabled)
            [ "$ACTIVATION_LAUNCHED" = "1" ]
            ;;
        *) return 1 ;;
    esac
}}
prove_health_evidence_activation_not_launched() {{
    printf 'prove:not-launched\\n' >> "$ACTIVATION_EVENT_LOG"
    [ "$ACTIVATION_PROOF_MODE" = "adopted-not-launched" ]
}}
prove_health_evidence_services_inactive() {{
    printf 'containment-proof\\n' >> "$ACTIVATION_EVENT_LOG"
    return 1
}}
activate_health_evidence_runtime
activation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$activation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$ACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "ACTIVATION_EVENT_LOG": str(event_log),
            "ACTIVATION_PROOF_MODE": proof_mode,
        },
    )
    events = event_log.read_text(encoding="utf-8").splitlines()
    return result, events


def test_activation_orchestrator_releases_delegation_only_after_exact_success(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="success",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_accepts_failure_only_after_exact_guard_proof(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="recovered",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "final:rc=1:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_preserves_stage_and_lease_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="unknown",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "containment-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_adopted_activation_terminal_success_arms_stage_and_lease_cleanup(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-success",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_adopted_activation_terminal_recovery_arms_cleanup_and_fails_closed(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-recovered",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "final:rc=1:delegated=0:abandoned=0",
    ]


def test_adopted_activation_reuses_sealed_artifacts_only_when_never_launched(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-not-launched",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "prove:not-launched",
        "contract:staged",
        "systemd-capability",
        "run:delegated=1",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_adopted_activation_with_launch_intent_but_no_outcome_is_preserved(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-in-flight",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "prove:not-launched",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_activation_persists_launch_intent_before_systemd_rpc():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("run_health_evidence_activation_unit() {")
    end = script.index("prove_health_evidence_activation_state() {", start)
    body = script[start:end]

    intent = body.index("launch-intent")
    durable_sync = body.index('sync -f "$state_dir"', intent)
    systemd_rpc = body.index("systemd-run", durable_sync)

    assert intent < durable_sync < systemd_rpc
    assert 'test ! -e "$intent_file"' in body
    assert 'rm -f "$success_marker" "$outcome_file"' not in body
