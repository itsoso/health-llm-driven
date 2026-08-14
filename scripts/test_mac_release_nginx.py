import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/mac_release_nginx_bootstrap.py"
SNIPPET_PATH = ROOT / "infra/nginx/mac-release-routes.conf"
WRAPPER_PATH = ROOT / "scripts/mac-release-nginx-bootstrap.sh"
DEPLOY_PATH = ROOT / "deploy.sh"
BASELINE_PATH = ROOT / "infra/nginx/health.executor.life.conf"


def _load_module():
    spec = importlib.util.spec_from_file_location("mac_release_nginx_bootstrap", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("command", (("apply", "payload", "token"), ("rollback", "token")))
def test_direct_production_nginx_cli_is_frozen_before_root_or_paths(
    tmp_path: Path,
    command: tuple[str, ...],
) -> None:
    marker = tmp_path / "path-tool-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "nginx", "systemctl"):
        tool = fake_bin / name
        tool.write_text(
            f'#!/bin/sh\nprintf called >> "{marker}"\nexit 91\n',
            encoding="utf-8",
        )
        tool.chmod(0o755)

    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), *command],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "FROZEN" in result.stderr
    assert not marker.exists()


def test_direct_nginx_cli_freezes_before_imports_env_paths_or_tools(
    tmp_path: Path,
) -> None:
    isolated = tmp_path / "bootstrap"
    isolated.mkdir()
    script = isolated / MODULE_PATH.name
    shutil.copyfile(MODULE_PATH, script)
    marker = tmp_path / "import-or-tool-called"
    (isolated / "base64.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "nginx", "ssh", "systemctl"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    secret = "nginx-release-token-must-not-leak"

    result = subprocess.run(
        [sys.executable, str(script), "apply", "/must-not-resolve", secret],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(fake_bin),
            "HOME": str(tmp_path / "poison-home"),
            "MAC_NGINX_REMOTE_LOCK_TOKEN": secret,
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "MAC_NGINX_BOOTSTRAP_FROZEN" in result.stderr
    assert secret not in result.stdout + result.stderr
    assert "/must-not-resolve" not in result.stdout + result.stderr
    assert not marker.exists()


def test_nginx_helper_executable_ignores_hostile_path_before_freeze(
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

    result = subprocess.run(
        [str(MODULE_PATH), "apply", "payload", "token"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "MAC_NGINX_BOOTSTRAP_FROZEN" in result.stderr
    assert not marker.exists()


@pytest.fixture
def module():
    return _load_module()


@pytest.fixture(autouse=True)
def explicit_mac_nginx_protocol_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAC_RELEASE_TEST_MODE", "1")


def _bootstrap_paths(module, root: Path):
    return module.BootstrapPaths(
        target=root / "etc/nginx/conf.d/health.executor.life.conf",
        snippet=root / "etc/nginx/snippets/reva-mac-release-routes.conf",
        state_root=root / "var/lib/health-app/mac-nginx-bootstrap",
        formal_receipt=root / "var/lib/health-app/release-state/mac-runtime.json",
        formal_previous_receipt=(
            root / "var/lib/health-app/release-state/mac-runtime.previous.json"
        ),
        formal_journal=(
            root / "var/lib/health-app/release-state/mac-release.transaction.json"
        ),
        formal_current=root / "opt/health-app-shared/assets/mac/current.json",
    )


def test_route_bootstrap_requires_explicit_test_mode(
    module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MAC_RELEASE_TEST_MODE", raising=False)

    with pytest.raises(module.BootstrapError, match="test mode"):
        module.RouteBootstrap(
            paths=_bootstrap_paths(module, tmp_path),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            run_command=lambda _argv: None,
            probe_http=lambda: {},
        )


def test_route_bootstrap_requires_non_root_identity(
    module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)

    with pytest.raises(module.BootstrapError, match="non-root"):
        module.RouteBootstrap(
            paths=_bootstrap_paths(module, tmp_path),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            run_command=lambda _argv: None,
            probe_http=lambda: {},
        )


def test_route_bootstrap_rejects_production_paths_even_when_tmpdir_is_poisoned(
    module, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer_calls: list[tuple[str, ...]] = []
    monkeypatch.setenv("TMPDIR", str(ROOT))

    with pytest.raises(module.BootstrapError, match="fixed non-production root"):
        module.RouteBootstrap(
            paths=_bootstrap_paths(module, ROOT / "nginx-protocol-fixture"),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            run_command=lambda argv: writer_calls.append(argv),
            probe_http=lambda: {},
        )

    assert writer_calls == []


def test_route_bootstrap_rejects_default_production_callbacks(
    module, tmp_path: Path
) -> None:
    with pytest.raises(module.BootstrapError, match="callbacks"):
        module.RouteBootstrap(
            paths=_bootstrap_paths(module, tmp_path),
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )


@pytest.fixture
def original_config() -> bytes:
    return b"""server {
    listen 443 ssl;

    location = /xiaoba-mac.dmg {
        alias /opt/health-app-shared/assets/xiaoba-mac.dmg;
        add_header X-Reva-Artifact xiaoba-mac-dmg;
    }

    # Rokid glasses push-up APK static distribution
    location = /rokid-companion.apk {
        alias /opt/health-app-shared/assets/rokid-companion.apk;
    }
}
"""


class FakeRuntime:
    def __init__(
        self, target: Path, snippet: Path, *, fail_reload_once: bool = False
    ) -> None:
        self.target = target
        self.snippet = snippet
        self.commands: list[tuple[str, ...]] = []
        self.probe_calls = 0
        self.fail_reload_once = fail_reload_once
        self.legacy_bytes = b"existing-production-dmg"

    def run(self, argv: tuple[str, ...]) -> None:
        self.commands.append(argv)
        if argv == ("/usr/bin/systemctl", "reload", "nginx") and self.fail_reload_once:
            self.fail_reload_once = False
            raise RuntimeError("injected reload failure")

    def probe(self):
        self.probe_calls += 1
        source = self.target.read_text(encoding="utf-8")
        managed = (
            "include /etc/nginx/snippets/reva-mac-release-routes.conf;" in source
            and self.snippet.exists()
            and "# BEGIN REVA MANAGED MAC RELEASE ROUTES"
            in self.snippet.read_text(encoding="utf-8")
        )
        return {
            "legacy_sha256": hashlib.sha256(self.legacy_bytes).hexdigest(),
            "current_status": 200 if managed else 404,
            "current_marker": "mac-current-manifest" if managed else None,
            "immutable_status": 404,
            "immutable_marker": "mac-immutable-dmg" if managed else None,
        }


def _manager(module, tmp_path: Path, config: bytes, **kwargs):
    target_dir = tmp_path / "etc/nginx/conf.d"
    target_dir.mkdir(parents=True)
    target = target_dir / "health.executor.life.conf"
    target.write_bytes(config)
    target.chmod(0o644)
    state_root = tmp_path / "var/lib/health-app/mac-nginx-bootstrap"
    state_root.parent.mkdir(parents=True, mode=0o755)
    snippet_target = tmp_path / "etc/nginx/snippets/reva-mac-release-routes.conf"
    snippet_target.parent.mkdir(parents=True, mode=0o755)
    formal_state_root = tmp_path / "var/lib/health-app/release-state"
    formal_current = tmp_path / "opt/health-app-shared/assets/mac/current.json"
    runtime = FakeRuntime(target, snippet_target, **kwargs)
    manager = module.RouteBootstrap(
        paths=module.BootstrapPaths(
            target=target,
            snippet=snippet_target,
            state_root=state_root,
            formal_receipt=formal_state_root / "mac-runtime.json",
            formal_previous_receipt=formal_state_root / "mac-runtime.previous.json",
            formal_journal=formal_state_root / "mac-release.transaction.json",
            formal_current=formal_current,
        ),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        run_command=runtime.run,
        probe_http=runtime.probe,
    )
    return manager, runtime, target, state_root


def test_snippet_has_bounded_exact_route_contract() -> None:
    snippet = SNIPPET_PATH.read_text(encoding="utf-8")

    assert snippet.count("# BEGIN REVA MANAGED MAC RELEASE ROUTES") == 1
    assert snippet.count("# END REVA MANAGED MAC RELEASE ROUTES") == 1
    assert "location = /xiaoba-mac.dmg" not in snippet
    assert "location = /mac/current.json" in snippet
    assert "mac-current-manifest" in snippet
    assert "mac-immutable-dmg" in snippet
    assert r"^/mac/releases/([0-9a-f]{40})/([0-9a-f]{64})\.dmg$" in snippet
    assert "alias /opt/health-app-shared/assets/" in snippet
    assert "$uri" not in snippet
    assert "location /mac/" in snippet
    assert "X-Content-Type-Options" in snippet


def test_tracked_nginx_baseline_matches_real_target_and_preserves_legacy_routes() -> None:
    baseline = BASELINE_PATH.read_text(encoding="utf-8")
    readme = (ROOT / "infra/README.md").read_text(encoding="utf-8")

    assert baseline.count("location = /xiaoba-mac.dmg") == 1
    assert baseline.count("location = /rokid-pushup-glasses.apk") == 1
    assert baseline.count("# Rokid glasses push-up APK static distribution") == 1
    assert baseline.count(
        "include /etc/nginx/snippets/reva-mac-release-routes.conf;"
    ) == 1
    assert "/etc/nginx/conf.d/health.executor.life.conf" in readme
    assert "/etc/nginx/snippets/reva-mac-release-routes.conf" in readme
    assert "/etc/nginx/sites-available/health.executor.life" not in readme


def test_apply_adopts_exact_tracked_baseline_without_mutation(
    module, tmp_path: Path
) -> None:
    manager, runtime, target, state_root = _manager(
        module, tmp_path, BASELINE_PATH.read_bytes()
    )
    runtime.snippet.write_bytes(SNIPPET_PATH.read_bytes())
    runtime.snippet.chmod(0o644)
    before = target.read_bytes()

    result = manager.apply(SNIPPET_PATH.read_bytes())

    assert result == "tracked-baseline-already-installed"
    assert target.read_bytes() == before
    assert runtime.snippet.read_bytes() == SNIPPET_PATH.read_bytes()
    assert not (state_root / "receipt.json").exists()
    assert ("/usr/bin/systemctl", "reload", "nginx") not in runtime.commands


def test_apply_is_atomic_idempotent_and_preserves_legacy_location(
    module, tmp_path: Path, original_config: bytes
) -> None:
    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    snippet = SNIPPET_PATH.read_bytes()

    first = manager.apply(snippet)
    first_bytes = target.read_bytes()
    second = manager.apply(snippet)

    assert first == "applied"
    assert second == "already-applied"
    assert target.read_bytes() == first_bytes
    assert first_bytes.count(
        b"include /etc/nginx/snippets/reva-mac-release-routes.conf;"
    ) == 1
    assert first_bytes.count(b"location = /xiaoba-mac.dmg") == 1
    assert runtime.snippet.read_bytes().count(b"location = /xiaoba-mac.dmg") == 0
    assert runtime.snippet.read_bytes() == snippet
    assert b"location = /rokid-companion.apk" in first_bytes
    assert first_bytes.index(b"include /etc/nginx/snippets/") < first_bytes.index(
        b"# Rokid glasses push-up APK static distribution"
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert stat.S_IMODE(state_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_root / "receipt.json").stat().st_mode) == 0o600
    assert [command for command in runtime.commands if "reload" in command] == [
        ("/usr/bin/systemctl", "reload", "nginx")
    ]


def test_failed_reload_automatically_restores_exact_original(
    module, tmp_path: Path, original_config: bytes
) -> None:
    manager, runtime, target, state_root = _manager(
        module, tmp_path, original_config, fail_reload_once=True
    )

    with pytest.raises(module.BootstrapError, match="restored"):
        manager.apply(SNIPPET_PATH.read_bytes())

    assert target.read_bytes() == original_config
    assert not runtime.snippet.exists()
    assert not (state_root / "receipt.json").exists()
    assert runtime.commands.count(("/usr/sbin/nginx", "-t")) >= 2
    assert runtime.commands.count(("/usr/bin/systemctl", "reload", "nginx")) == 2


def test_explicit_rollback_is_idempotent_and_restores_http_proof(
    module, tmp_path: Path, original_config: bytes
) -> None:
    manager, _, target, _ = _manager(module, tmp_path, original_config)
    manager.apply(SNIPPET_PATH.read_bytes())

    assert manager.rollback() == "rolled-back"
    assert manager.rollback() == "already-rolled-back"
    assert target.read_bytes() == original_config
    assert not manager.paths.snippet.exists()


@pytest.mark.parametrize(
    "formal_marker",
    (
        "formal_receipt",
        "formal_previous_receipt",
        "formal_journal",
        "formal_current",
    ),
)
def test_rollback_refuses_to_remove_routes_after_formal_mac_release_started(
    module, tmp_path: Path, original_config: bytes, formal_marker: str
) -> None:
    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    manager.apply(SNIPPET_PATH.read_bytes())
    applied = target.read_bytes()
    snippet = manager.paths.snippet.read_bytes()
    commands_before = list(runtime.commands)
    probe_calls_before = runtime.probe_calls
    receipt_before = (state_root / "receipt.json").read_bytes()
    marker_path = getattr(manager.paths, formal_marker)
    marker_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    marker_path.write_text("formal release state\n", encoding="utf-8")

    with pytest.raises(module.BootstrapError, match="formal Mac release"):
        manager.rollback()

    assert target.read_bytes() == applied
    assert manager.paths.snippet.read_bytes() == snippet
    assert runtime.commands == commands_before
    assert runtime.probe_calls == probe_calls_before
    assert (state_root / "receipt.json").read_bytes() == receipt_before
    assert not (state_root / "journal.json").exists()


def test_interrupted_apply_recovers_from_journal_on_next_invocation(
    module, tmp_path: Path, original_config: bytes
) -> None:
    crashed = False

    def crash_after_replace(point: str) -> None:
        nonlocal crashed
        if point == "after-target-replace" and not crashed:
            crashed = True
            raise KeyboardInterrupt("simulated hard interruption")

    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    manager.fault_hook = crash_after_replace
    with pytest.raises(KeyboardInterrupt):
        manager.apply(SNIPPET_PATH.read_bytes())

    assert (state_root / "journal.json").exists()
    assert b"include /etc/nginx/snippets/reva-mac-release-routes.conf;" in target.read_bytes()
    assert manager.paths.snippet.exists()

    recovered = module.RouteBootstrap(
        paths=manager.paths,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        run_command=runtime.run,
        probe_http=runtime.probe,
    )
    assert recovered.apply(SNIPPET_PATH.read_bytes()) == "recovered-applied"
    assert not (state_root / "journal.json").exists()
    assert (state_root / "receipt.json").exists()


def test_interrupted_rollback_recovers_from_journal_on_next_invocation(
    module, tmp_path: Path, original_config: bytes
) -> None:
    crashed = False

    def crash_after_replace(point: str) -> None:
        nonlocal crashed
        if point == "after-target-replace" and not crashed:
            crashed = True
            raise KeyboardInterrupt("simulated hard rollback interruption")

    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    manager.apply(SNIPPET_PATH.read_bytes())
    manager.fault_hook = crash_after_replace
    with pytest.raises(KeyboardInterrupt):
        manager.rollback()

    assert target.read_bytes() == original_config
    assert (state_root / "journal.json").exists()

    recovered = module.RouteBootstrap(
        paths=manager.paths,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        run_command=runtime.run,
        probe_http=runtime.probe,
    )
    assert recovered.rollback() == "recovered-rolled-back"
    assert not (state_root / "journal.json").exists()
    assert target.read_bytes() == original_config


def test_tampered_receipt_is_rejected_without_mutation(
    module, tmp_path: Path, original_config: bytes
) -> None:
    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    manager.apply(SNIPPET_PATH.read_bytes())
    applied = target.read_bytes()
    receipt_path = state_root / "receipt.json"
    receipt = receipt_path.read_text(encoding="utf-8").replace(
        '"target":"', '"unexpected":"value","target":"', 1
    )
    receipt_path.write_text(receipt, encoding="utf-8")
    receipt_path.chmod(0o600)
    commands_before = list(runtime.commands)

    with pytest.raises(module.BootstrapError, match="receipt"):
        manager.rollback()

    assert target.read_bytes() == applied
    assert runtime.commands == commands_before


def test_lost_release_lock_blocks_next_mutation_and_leaves_recoverable_journal(
    module, tmp_path: Path, original_config: bytes
) -> None:
    manager, runtime, target, state_root = _manager(module, tmp_path, original_config)
    checks = 0

    def expiring_lock() -> None:
        nonlocal checks
        checks += 1
        if checks == 7:
            raise module.BootstrapError("remote release lock ownership changed")

    manager.assert_lock = expiring_lock
    with pytest.raises(module.BootstrapError, match="release lock"):
        manager.apply(SNIPPET_PATH.read_bytes())

    assert target.read_bytes() == original_config
    assert not manager.paths.snippet.exists()
    assert (state_root / "journal.json").exists()

    recovered = module.RouteBootstrap(
        paths=manager.paths,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
        run_command=runtime.run,
        probe_http=runtime.probe,
    )
    assert recovered.apply(SNIPPET_PATH.read_bytes()) == "applied"
    assert not (state_root / "journal.json").exists()


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "mode", "anchor"])
def test_apply_rejects_unsafe_target_before_commands(
    module, tmp_path: Path, original_config: bytes, unsafe: str
) -> None:
    manager, runtime, target, _ = _manager(module, tmp_path, original_config)
    if unsafe == "symlink":
        real = target.with_name("real.conf")
        target.replace(real)
        target.symlink_to(real)
    elif unsafe == "hardlink":
        os.link(target, target.with_name("second-link.conf"))
    elif unsafe == "mode":
        target.chmod(0o666)
    else:
        target.write_bytes(original_config.replace(
            b"# Rokid glasses push-up APK static distribution", b"# missing anchor"
        ))

    with pytest.raises(module.BootstrapError):
        manager.apply(SNIPPET_PATH.read_bytes())

    assert runtime.commands == []


def test_remote_cli_pins_paths_and_refuses_path_overrides() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert 'Path("/etc/nginx/conf.d/health.executor.life.conf")' in source
    assert 'Path("/etc/nginx/snippets/reva-mac-release-routes.conf")' in source
    assert 'Path("/var/lib/health-app/mac-nginx-bootstrap")' in source
    assert "--target" not in source
    assert "--state-root" not in source
    assert "Mac nginx production bootstrap is frozen" in source
    assert "effective_uid == 0" in source
    assert 'Path("/var/lib/health-app/release-state/deploy.lock")' in source
    assert "assert_remote_release_lock" in source


def test_wrapper_uses_only_pinned_noninteractive_ssh() -> None:
    source = WRAPPER_PATH.read_text(encoding="utf-8")

    for token in (
        'SERVER="root@39.98.206.178"',
        'ssh-ed25519',
        'AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav',
        '"-F" "/dev/null"',
        '"BatchMode=yes"',
        '"StrictHostKeyChecking=yes"',
        '"UserKnownHostsFile=/dev/null"',
        '"GlobalKnownHostsFile=/dev/null"',
        '"KnownHostsCommand=',
    ):
        assert token in source
    assert "DEPLOY_SERVER" not in source
    assert "HEALTH_MAC_RELEASE_SERVER" not in source
    assert 'case "${1:-}" in' in source
    assert "apply)" in source
    assert "rollback)" in source
    assert "REVA_MAC_BOOTSTRAP_ENTRYPOINT" in source


def test_wrapper_freezes_before_path_resolution_lock_input_or_ssh() -> None:
    source = WRAPPER_PATH.read_text(encoding="utf-8")
    freeze = source.index("Mac production route mutation is frozen")

    assert freeze < source.index('SCRIPT_DIR="')
    assert freeze < source.index("REVA_MAC_BOOTSTRAP_ENTRYPOINT")
    assert freeze < source.index("MAC_NGINX_REMOTE_LOCK_TOKEN")
    assert freeze < source.index('/usr/bin/ssh "${SSH_OPTIONS[@]}"')

    completed = subprocess.run(
        [str(WRAPPER_PATH), "apply"],
        cwd=ROOT,
        env={
            **os.environ,
            "REVA_MAC_BOOTSTRAP_ENTRYPOINT": "deploy.sh",
            "MAC_NGINX_REMOTE_LOCK_DIR": (
                "/var/lib/health-app/release-state/deploy.lock"
            ),
            "MAC_NGINX_REMOTE_LOCK_TOKEN": "attacker-readable-token",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "manual infrastructure Gate" in completed.stderr


def test_deploy_exposes_only_explicit_mac_route_bootstrap_mode() -> None:
    source = DEPLOY_PATH.read_text(encoding="utf-8")

    assert "--bootstrap-mac-routes" in source
    assert 'scripts/mac-release-nginx-bootstrap.sh" "${MAC_ROUTE_ACTION}"' in source
    assert 'MAC_ROUTE_ACTION="apply"' in source
    assert 'MAC_ROUTE_ACTION="rollback"' in source
    assert source.count("bootstrap_mac_release_routes") >= 2
    early = source.index("Production repository entrypoints are frozen")
    option = source.index("--bootstrap-mac-routes", early)
    path_resolution = source.index('SCRIPT_DIR="')
    legacy_guard = source.index('if [[ "REVA_UNREACHABLE_LEGACY" == "NEVER" ]]')
    assert early < legacy_guard < path_resolution < option
    assert "MAC_NGINX_REMOTE_LOCK_TOKEN" in source


def test_python_and_shell_sources_are_syntax_valid() -> None:
    subprocess.run(["python3", "-m", "py_compile", str(MODULE_PATH)], check=True)
    subprocess.run(["bash", "-n", str(WRAPPER_PATH)], check=True)


def test_imported_production_main_freezes_before_root_paths_or_writer_callbacks() -> None:
    snippet = SNIPPET_PATH.read_bytes()
    encoded = __import__("base64").b64encode(snippet).decode("ascii")
    harness = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('bootstrap', {str(MODULE_PATH)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
seen = []
module.os.geteuid = lambda: seen.append('root-check') or 0
module.assert_remote_release_lock = lambda token: seen.append('lock-check')
class FakeBootstrap:
    def __init__(self, **kwargs):
        seen.append('manager-constructed')
    def apply(self, snippet):
        seen.append('writer-called')
        return 'applied'
module.RouteBootstrap = FakeBootstrap
try:
    module.main(['apply', {encoded!r}, 'test-lock-token'])
except module.BootstrapError as error:
    assert 'frozen' in str(error).lower()
else:
    raise AssertionError('imported production main unexpectedly returned')
assert seen == []
"""
    result = subprocess.run(
        [sys.executable, "-c", harness], text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
