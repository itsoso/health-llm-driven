"""Portable probe-contract tests; native evidence requires the explicit CLI below.

On an ephemeral Linux/systemd CI runner (never production):
  sudo /usr/bin/python3 scripts/neo_wechat_linux_probe.py --ephemeral-runner --require-linux

The native command exits 77 when unsupported, or 1 with --require-linux. Neither
case is a pass. Pytest on macOS runs only these construction/validation tests.
"""
import importlib.util
from pathlib import Path
import subprocess
import errno
import socket

import pytest
import yaml


SPEC = importlib.util.spec_from_file_location(
    "neo_wechat_linux_probe", Path(__file__).with_name("neo_wechat_linux_probe.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
TEMPLATE = Path(__file__).resolve().parents[1] / "infra/neo-wechat/neo-wechat.service.in"
SOCKET_TEMPLATE = TEMPLATE.with_name("neo-wechat.socket.in")


def test_ci_requires_actual_target_manager_before_release_invariants():
    jobs = yaml.safe_load((TEMPLATE.parents[2] / '.github/workflows/ci.yml').read_text())['jobs']
    job = jobs['neo-wechat-systemd249']
    assert job['runs-on'] == 'ubuntu-22.04'
    assert job['permissions'] == {'contents': 'read'}
    assert job['timeout-minutes'] <= 5
    assert 'neo-wechat-systemd249' in jobs['release-invariants']['needs']
    assert 'always()' not in jobs['release-invariants']['if']
    commands = '\n'.join(step.get('run', '') for step in job['steps'])
    assert '--ephemeral-runner --require-linux' in commands
    assert "result['systemd_249_observed'] is True" in commands
    assert "result['status'] == 'PASS'" in commands


def test_ci_native_failure_remains_failed_and_emits_diagnostics(tmp_path):
    jobs = yaml.safe_load((TEMPLATE.parents[2] / '.github/workflows/ci.yml').read_text())['jobs']
    command = next(step['run'] for step in jobs['neo-wechat-systemd249']['steps'] if 'run' in step)
    command = command.replace('/tmp/neo-wechat-systemd249.json', str(tmp_path / 'report.json'))
    # Synthetic shell control: no sudo or systemd command executes in this test.
    result = subprocess.run(['bash', '-e', '-c',
        "sudo() { printf '%s\\n' '{\"status\":\"FAIL\",\"reason\":\"synthetic\"}'; return 1; };\n" + command],
        text=True, capture_output=True)
    assert result.returncode == 1
    assert '"reason":"synthetic"' in result.stdout


def render(control=False):
    return probe.render_unit(TEMPLATE.read_text(), "neo-wx-probe-0123456789ab",
                             uid=65534, gid=65534, control=control)


def test_render_retains_all_sandbox_directives_from_actual_template():
    text, plan = render()
    for line in TEMPLATE.read_text().splitlines():
        if line.startswith(probe.PRESERVED_PREFIXES):
            assert line in text
    assert "User=65534" in text and "Group=65534" in text
    assert "SupplementaryGroups=\n" in text
    assert "PrivateNetwork=yes" in text
    assert "Restart=no" in text and "TimeoutStartSec=30" in text
    assert "TimeoutStopSec=30" in text and "RuntimeMaxSec=" not in text
    assert "@REVISION@" not in text and "[Install]" not in text
    assert all(path.startswith("/run/neo-wx-probe-0123456789ab-fixtures/fs/")
               for path in plan["hidden_files"])
    paths_line = next(line for line in TEMPLATE.read_text().splitlines() if line.startswith("InaccessiblePaths="))
    assert len(plan["hidden_files"]) == len(paths_line.split("=", 1)[1].split())
    assert "MemoryMax=256M" in text and "TasksMax=32" in text
    assert "RuntimeDirectory=" not in text
    assert f"Requires={plan['name']}.socket" in text
    assert f"ReadWritePaths={plan['state']}\n" in text
    assert "SystemCallFilter=" + probe.DENIED_SYSCALLS in text


def test_control_changes_only_two_boundaries_and_worker_expectation():
    text, plan = render()
    control, control_plan = render(True)
    expected = "\n".join(
        "InaccessiblePaths=" if line.startswith("InaccessiblePaths=")
        else "SocketBindDeny=" if line.startswith("SocketBindDeny=")
        else line for line in text.splitlines() if line != "SystemCallFilter=" + probe.DENIED_SYSCALLS) + "\n"
    assert expected == control
    assert plan | {"control": True} == control_plan


@pytest.mark.parametrize("name", ["neo-wechat", "../oops", "neo-wx-probe-$bad", "neo-wx-probe-0123456789ab.service"])
def test_probe_names_cannot_target_real_units_or_escape(name):
    with pytest.raises(ValueError, match="probe name"):
        probe.render_unit(TEMPLATE.read_text(), name, uid=65534, gid=65534)


@pytest.mark.parametrize("mutation", [
    lambda s: s + "\n[Install]\nWantedBy=multi-user.target\n",
    lambda s: s.replace("LoadCredential=encryption_key:", "LoadCredential=unexpected:"),
    lambda s: s.replace("SocketBindDeny=any", "SocketBindDeny=ipv4:tcp"),
    lambda s: s.replace("ReadWritePaths=/var/lib/neo-wechat", "ReadWritePaths=/"),
    lambda s: s.replace("SystemCallFilter=~bind listen", "SystemCallFilter=~bind"),
    lambda s: s.replace("User=neo-wechat", "User=root"),
    lambda s: s + "\nEnvironmentFile=/etc/unrelated-secrets\n",
    lambda s: s + "\nExecStartPre=/usr/bin/true\n",
])
def test_unreviewed_template_shape_fails_closed(mutation):
    with pytest.raises(ValueError):
        probe.render_unit(mutation(TEMPLATE.read_text()), "neo-wx-probe-0123456789ab", uid=65534, gid=65534)


def test_credential_probes_cover_copies_and_hidden_originals():
    text, plan = render()
    assert set(plan["credentials"]) == {"encryption_key", "admin_password_hash", "slack_webhook"}
    for name in plan["credentials"]:
        original = f'/run/neo-wx-probe-0123456789ab-fixtures/fs/etc/neo-wechat/{name}'
        assert original in plan["hidden_files"]
        assert f"LoadCredential={name}:{original}" in text
    assert plan["state"] == "/var/lib/neo-wx-probe-0123456789ab"
    assert plan["runtime"] == "/run/neo-wx-probe-0123456789ab"


def test_socket_template_preserves_permissions_fd_name_and_remaps_only_identity():
    _, plan = render()
    text = probe.render_socket(SOCKET_TEMPLATE.read_text(), plan, gid=65534)
    assert f"ListenStream={plan['runtime']}/bridge.sock" in text
    assert "SocketUser=65534" in text and "SocketGroup=65534" in text
    for line in ("SocketMode=0660", "DirectoryMode=0755", "RemoveOnStop=yes", "Backlog=16",
                 "FileDescriptorName=neo-wechat-http", f"Service={plan['name']}.service"):
        assert line in text
    assert "[Install]" not in text


@pytest.mark.parametrize("mutation", [
    lambda s: s.replace("SocketMode=0660", "SocketMode=0666"),
    lambda s: s.replace("RemoveOnStop=yes", "RemoveOnStop=no"),
    lambda s: s.replace("ListenStream=/run/neo-wechat/bridge.sock", "ListenStream=8080"),
    lambda s: s + "\nExecStartPost=/usr/bin/true\n",
])
def test_socket_boundary_drift_fails_closed(mutation):
    with pytest.raises(ValueError):
        probe.render_socket(mutation(SOCKET_TEMPLATE.read_text()), render()[1], gid=65534)


def fake_sockets(monkeypatch, denied_errno=None):
    seen = []
    class Candidate:
        def __init__(self, family, kind):
            self.family = family
            assert kind == socket.SOCK_STREAM
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def act(self, operation, value):
            seen.append((int(self.family), operation, value))
            if denied_errno:
                raise OSError(denied_errno, "synthetic")
        def bind(self, address):
            self.act("bind", address[1])
        def listen(self, backlog):
            self.act("listen", None)
    monkeypatch.setattr(probe.socket, "socket", Candidate)
    return seen


@pytest.mark.parametrize("control,denied_errno", [(False, errno.EPERM), (True, None)])
def test_native_network_checks_cover_zero_fixed_and_implicit_listen(monkeypatch, control, denied_errno):
    seen = fake_sockets(monkeypatch, denied_errno)
    result = probe.exercise_ip_policy(control)
    expected = [(int(family), operation, port) for family in (socket.AF_INET, socket.AF_INET6)
                for operation, port in (("bind", 0), ("bind", 43193), ("listen", None))]
    assert seen == expected
    assert len(result) == 6
    assert all(item["result"] == ("allowed" if control else "denied") for item in result)


@pytest.mark.parametrize("control,denied_errno", [(False, None), (False, errno.EADDRINUSE), (True, errno.EPERM)])
def test_network_policy_cannot_pass_without_real_expected_outcome(monkeypatch, control, denied_errno):
    fake_sockets(monkeypatch, denied_errno)
    with pytest.raises(AssertionError):
        probe.exercise_ip_policy(control)


def io_native_abi(monkeypatch, architecture="x86_64"):
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe.platform, "machine", lambda: architecture)


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
def test_io_uring_numbers_are_explicit_native_abi(monkeypatch, architecture):
    io_native_abi(monkeypatch, architecture)
    assert probe.io_uring_numbers() == (
        ("io_uring_setup", 425, (0, 0)),
        ("io_uring_enter", 426, (-1, 0, 0, 0, 0, 0)),
        ("io_uring_register", 427, (-1, 0, 0, 0)))


@pytest.mark.parametrize("architecture", ["i386", "x32", "armv7l", "unknown", "x86_64\n"])
def test_unsupported_abi_fails_required_mode_before_host_commands(monkeypatch, capsys, architecture):
    io_native_abi(monkeypatch, architecture)
    monkeypatch.setattr(probe, "unsupported_reason", lambda: None)
    monkeypatch.setattr(probe, "run", lambda *a, **kw: pytest.fail("host command forbidden"))
    assert probe.main(["--ephemeral-runner", "--require-linux"]) == 1
    output = capsys.readouterr().out
    assert '"status": "FAIL"' in output and "verified native Linux" in output


def test_compat_32bit_process_is_not_native_x86_64(monkeypatch):
    io_native_abi(monkeypatch)
    monkeypatch.setattr(probe.ctypes, "sizeof", lambda value: 4)
    with pytest.raises(ValueError, match="native Linux"):
        probe.io_uring_numbers()


@pytest.mark.parametrize("control,error,expected", [
    (False, errno.EPERM, "denied"), (False, errno.EACCES, "denied"),
    (True, errno.EBADF, "allowed_invalid_arguments"),
    (True, errno.EINVAL, "allowed_invalid_arguments"),
    (True, errno.EFAULT, "allowed_invalid_arguments"),
    (True, errno.ENOSYS, "kernel_unavailable_not_attributable"),
    (True, errno.EPERM, "control_permission_denied_not_attributable"),
])
def test_io_uring_results_preserve_errno_and_attribution(monkeypatch, control, error, expected):
    io_native_abi(monkeypatch)
    seen = []
    def invoke(number, args):
        seen.append((number, args))
        return -1, error
    monkeypatch.setattr(probe, "invoke_io_uring", invoke)
    results = probe.exercise_io_uring_policy(control)
    assert [number for number, args in seen] == [425, 426, 427]
    assert all(item["errno"] == error and item["outcome"] == expected for item in results)


@pytest.mark.parametrize("result,error", [(-1, errno.EBADF), (-1, errno.ENOSYS), (-2, errno.EPERM)])
def test_io_uring_protected_fail_open_or_malformed_is_failure(monkeypatch, result, error):
    io_native_abi(monkeypatch)
    monkeypatch.setattr(probe, "invoke_io_uring", lambda *a: (result, error))
    with pytest.raises(AssertionError):
        probe.exercise_io_uring_policy(False)


def test_io_uring_unexpected_setup_fd_is_closed_before_protected_failure(monkeypatch):
    io_native_abi(monkeypatch)
    closed = []
    monkeypatch.setattr(probe.os, "close", closed.append)
    monkeypatch.setattr(probe, "invoke_io_uring", lambda *a: (99, 0))
    with pytest.raises(AssertionError):
        probe.exercise_io_uring_policy(False)
    assert closed == [99]


def test_cgroup_limits_are_effective_values_not_just_unit_strings():
    good = {"memory.max": "268435456", "memory.swap.max": "0", "pids.max": "32", "cpu.max": "25000 100000"}
    probe.validate_cgroup(good)
    for field in good:
        with pytest.raises(AssertionError):
            probe.validate_cgroup(good | {field: "max"})


def test_refuses_host_with_existing_health_paths(monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "linux")
    monkeypatch.setattr(probe.os, "geteuid", lambda: 0)
    monkeypatch.setattr(probe.Path, "is_dir", lambda self: str(self) == "/run/systemd/system")
    monkeypatch.setattr(probe.Path, "is_file", lambda self: True)
    monkeypatch.setattr(probe.Path, "read_text", lambda self: "systemd\n")
    monkeypatch.setattr(probe.Path, "exists", lambda self: str(self) == "/opt/health-app")
    assert "refusing a host" in probe.unsupported_reason()


def test_explicit_ephemeral_runner_acknowledgment_required():
    with pytest.raises(SystemExit) as error:
        probe.main([])
    assert error.value.code == 2


def test_unsupported_is_not_success(monkeypatch, capsys):
    monkeypatch.setattr(probe, "unsupported_reason", lambda: "synthetic unsupported")
    assert probe.main(["--ephemeral-runner"]) == 77
    assert probe.main(["--ephemeral-runner", "--require-linux"]) == 1
    assert '"status": "UNSUPPORTED"' in capsys.readouterr().out


VENDOR_WARNING = "/lib/systemd/system/snapd.service:23: Unknown key name 'RestartMode' in section 'Service', ignoring.\n"
OWN_NAME = "neo-wx-probe-0123456789ab.service"


def test_verify_uses_exact_copy_and_only_synthetic_dependency_path(tmp_path, monkeypatch):
    unit = tmp_path / OWN_NAME
    unit.write_text(render()[0])
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    captured = []
    def fake_run(argv, **kwargs):
        captured.append((argv, kwargs))
        copied = Path(argv[-1])
        assert copied.read_bytes() == unit.read_bytes()
        assert copied.parent == fixture / "verify-units"
        assert kwargs["env"]["SYSTEMD_UNIT_PATH"] == str(copied.parent)
        assert not kwargs["env"]["SYSTEMD_UNIT_PATH"].endswith(":")
        assert "--man=no" in argv
        assert set(p.name for p in copied.parent.iterdir()) == set(probe.VERIFY_DEPENDENCIES) | {OWN_NAME}
        assert all(not p.is_symlink() for p in copied.parent.iterdir())
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    report = probe.verify_unit(unit, fixture)
    assert len(captured) == 1
    assert report["dependency_scope"] == "synthetic static dependencies only"
    assert report["unit_sha256"] == probe.hashlib.sha256(unit.read_bytes()).hexdigest()


def test_verify_includes_exact_paired_socket_bytes(tmp_path, monkeypatch):
    unit = tmp_path / OWN_NAME
    unit.write_text(render()[0])
    paired = unit.with_suffix(".socket")
    paired.write_text(probe.render_socket(SOCKET_TEMPLATE.read_text(), render()[1], gid=65534))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    def fake_run(argv, **kwargs):
        assert [Path(path).name for path in argv[-2:]] == [unit.name, paired.name]
        assert Path(argv[-2]).read_bytes() == unit.read_bytes()
        assert Path(argv[-1]).read_bytes() == paired.read_bytes()
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    report = probe.verify_unit(unit, fixture, paired)
    assert report["paired_sha256"] == {paired.name: probe.hashlib.sha256(paired.read_bytes()).hexdigest()}


@pytest.mark.parametrize("diagnostic", [
    VENDOR_WARNING,
    f"{OWN_NAME}: RuntimeMaxSec= has no effect in combination with Type=oneshot. Ignoring.\n",
    VENDOR_WARNING + f"/run/systemd/system/{OWN_NAME}:23: Unknown key name 'ProtectSystemX' in section 'Service', ignoring.\n",
    "Failed to initialize manager: Permission denied\n",
])
def test_isolated_verification_rejects_all_stderr(tmp_path, monkeypatch, diagnostic):
    unit = tmp_path / OWN_NAME
    unit.write_text(render()[0])
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(probe.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", diagnostic))
    with pytest.raises(RuntimeError, match="unit verification failed"):
        probe.verify_unit(unit, fixture)


@pytest.mark.parametrize("returncode,stdout", [(1, ""), (0, "unexpected output")])
def test_isolated_verification_rejects_nonzero_and_unknown_output(tmp_path, monkeypatch, returncode, stdout):
    unit = tmp_path / OWN_NAME
    unit.write_text(render()[0])
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(probe.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], returncode, stdout, ""))
    with pytest.raises(RuntimeError, match="unit verification failed"):
        probe.verify_unit(unit, fixture)


def cleanup_objects(tmp_path):
    paths = [tmp_path / name for name in ('probe.service', 'probe.socket', 'fixture', 'state', 'runtime', 'marker')]
    for path in paths:
        if path.name in ('fixture', 'state', 'runtime'):
            path.mkdir()
        else:
            path.write_text('synthetic')
    return paths


def test_cleanup_inactive_unloaded_unit_never_resets_failed(tmp_path, monkeypatch):
    paths = cleanup_objects(tmp_path)
    calls = []
    def fake_run(*args, **kwargs):
        calls.append(args)
        if args[1] == 'show':
            return 'LoadState=not-found\nActiveState=inactive\n'
        assert args[1] != 'reset-failed'
        return ''
    monkeypatch.setattr(probe, 'run', fake_run)
    probe.cleanup_probe(*paths, registered=True, primary_error=None)
    assert calls[0][1:] == ('stop', 'probe.socket', 'probe.service')
    assert calls[-1][1] == 'daemon-reload'
    assert not any(path.exists() for path in paths)


def test_cleanup_resets_only_failed_then_requires_inactive(tmp_path, monkeypatch):
    paths = cleanup_objects(tmp_path)
    calls = []
    failed = True
    def fake_run(*args, **kwargs):
        nonlocal failed
        calls.append(args)
        if args[1] == 'reset-failed':
            assert args[-1] == 'probe.service'
            failed = False
        if args[1] == 'show':
            active = 'failed' if failed and args[-1] == 'probe.service' else 'inactive'
            return f'LoadState=loaded\nActiveState={active}\n'
        return ''
    monkeypatch.setattr(probe, 'run', fake_run)
    probe.cleanup_probe(*paths, registered=True, primary_error=None)
    assert sum(call[1] == 'reset-failed' for call in calls) == 1
    assert not any(path.exists() for path in paths)


@pytest.mark.parametrize('failure', ['stop', 'show', 'reset-failed'])
def test_cleanup_failure_preserves_primary_and_all_paths(tmp_path, monkeypatch, failure):
    paths = cleanup_objects(tmp_path)
    def fake_run(*args, **kwargs):
        if args[1] == failure:
            raise RuntimeError('cleanup synthetic ' + failure)
        if args[1] == 'show':
            return 'LoadState=loaded\nActiveState=failed\n'
        return ''
    monkeypatch.setattr(probe, 'run', fake_run)
    with pytest.raises(RuntimeError, match='primary synthetic.*cleanup synthetic ' + failure):
        probe.cleanup_probe(*paths, registered=True, primary_error=RuntimeError('primary synthetic'))
    assert all(path.exists() for path in paths)


@pytest.mark.parametrize('state', ['active', 'activating', 'deactivating', 'unexpected'])
def test_cleanup_refuses_removal_without_confirmed_stop(tmp_path, monkeypatch, state):
    paths = cleanup_objects(tmp_path)
    monkeypatch.setattr(probe, 'run', lambda *a, **k: f'LoadState=loaded\nActiveState={state}\n' if a[1] == 'show' else '')
    with pytest.raises(RuntimeError, match='cleanup failed'):
        probe.cleanup_probe(*paths, registered=True, primary_error=None)
    assert all(path.exists() for path in paths)


@pytest.mark.parametrize('journal_fails', [False, True])
def test_unit_diagnostics_preserve_original_and_query_socket_too(monkeypatch, journal_fails):
    def fake_run(*args, **kwargs):
        assert '--unit=probe.service' in args and '--unit=probe.socket' in args
        if journal_fails:
            raise RuntimeError('journal unavailable')
        return 'synthetic socket detail'
    monkeypatch.setattr(probe, 'run', fake_run)
    message = probe.unit_failure_diagnostics(RuntimeError('original start failure'), 'probe.service', 'probe.socket')
    assert 'original start failure' in message
    assert ('journal unavailable' if journal_fails else 'synthetic socket detail') in message
@pytest.fixture(scope="module")
def credentials():
    spec = importlib.util.spec_from_file_location("neo_wechat_production_credentials", probe.CREDENTIAL_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def credential_stat(mode=0o440, uid=0):
    return probe.os.stat_result((probe.stat.S_IFREG | mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))


def credential_acl(uid=65534):
    import struct
    entries = [(1, 4, 0xffffffff), (2, 4, uid), (4, 0, 0xffffffff),
               (16, 4, 0xffffffff), (32, 0, 0xffffffff)]
    return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)


def test_credential_acl_mask_is_not_owning_group_access(credentials):
    report = credentials.validate_credential_metadata(credential_stat(), credential_acl(), 65534)
    assert report['access_model'] == 'root_owner_service_uid_read_acl'
    assert report['mode'] == '0440' and report['uid'] == 0


def test_credential_legacy_service_owned_mode_requires_no_acl(credentials):
    report = credentials.validate_credential_metadata(credential_stat(0o400, 65534), None, 65534)
    assert report['access_model'] == 'service_owner_read_only'


@pytest.mark.parametrize('mode,owner,acl', [
    (0o440, 0, None), (0o444, 0, credential_acl()),
    (0o640, 0, credential_acl()), (0o450, 0, credential_acl()),
    (0o440, 123, credential_acl()), (0o440, 65534, credential_acl()),
    (0o400, 0, None), (0o400, 123, None),
    (0o440, 0, credential_acl(123)), (0o440, 0, b''),
    (0o440, 0, b'\x03' + credential_acl()[1:]),
    (0o440, 0, credential_acl()[:-1]),
])
def test_credential_metadata_rejects_unreviewed_access(credentials, mode, owner, acl):
    with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
        credentials.validate_credential_metadata(credential_stat(mode, owner), acl, 65534)


@pytest.mark.parametrize('entry,permission', [(0, 6), (1, 6), (2, 4), (3, 6), (4, 4)])
def test_credential_acl_rejects_write_group_other_or_broad_mask(credentials, entry, permission):
    import struct
    acl = bytearray(credential_acl())
    struct.pack_into('<H', acl, 4 + 8 * entry + 2, permission)
    with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
        credentials.validate_credential_metadata(credential_stat(), bytes(acl), 65534)


def test_credential_acl_rejects_extra_named_identity_and_duplicates(credentials):
    import struct
    for tag in (2, 8):
        acl = credential_acl() + struct.pack('<HHI', tag, 4, 123)
        with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
            credentials.validate_credential_metadata(credential_stat(), acl, 65534)


def test_credential_symlink_is_not_regular_file(credentials):
    info = probe.os.stat_result((probe.stat.S_IFLNK | 0o400, 0, 0, 1, 65534, 0, 0, 0, 0, 0))
    with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
        credentials.validate_credential_metadata(info, None, 65534)


def directory_metadata(acl=True):
    import struct
    info = probe.os.stat_result((probe.stat.S_IFDIR | (0o550 if acl else 0o500),
                                 0, 0, 1, 0 if acl else 65534, 0, 0, 0, 0, 0))
    encoded = bytearray(credential_acl()) if acl else None
    if acl:
        for index in (0, 1, 3):
            struct.pack_into('<H', encoded, 4 + 8 * index + 2, 5)
        encoded = bytes(encoded)
    return info, encoded


@pytest.mark.parametrize('acl', [False, True])
def test_credential_directory_allows_only_service_and_root_traversal(credentials, acl):
    info, encoded = directory_metadata(acl)
    report = credentials.validate_credential_metadata(info, encoded, 65534, directory=True)
    assert report['mode'] == ('0550' if acl else '0500')


@pytest.mark.parametrize('default', [b'', credential_acl()])
def test_credential_directory_rejects_any_default_acl(credentials, default):
    info, encoded = directory_metadata()
    with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
        credentials.validate_credential_metadata(info, encoded, 65534, directory=True, default_acl=default)


@pytest.mark.parametrize('index', [1, 2, 4])
def test_credential_directory_rejects_wrong_traversal_grants(credentials, index):
    import struct
    info, encoded = directory_metadata()
    encoded = bytearray(encoded)
    struct.pack_into('<H', encoded, 4 + 8 * index + 2, 4 if index == 1 else 5)
    with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
        credentials.validate_credential_metadata(info, bytes(encoded), 65534, directory=True)


@pytest.mark.parametrize('error', [errno.ENODATA, errno.EOPNOTSUPP, errno.EACCES, errno.EIO])
def test_credential_xattr_absence_is_distinct_from_read_failure(credentials, monkeypatch, error):
    def fail(*args):
        raise OSError(error, 'synthetic')
    monkeypatch.setattr(probe.os, 'getxattr', fail, raising=False)
    if error in (errno.ENODATA, errno.EOPNOTSUPP):
        assert credentials.credential_xattr(99, 'system.posix_acl_access') is None
    else:
        with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
            credentials.credential_xattr(99, 'system.posix_acl_access')


@pytest.mark.parametrize('readonly', [False, True])
def test_credential_owned_fallback_requires_effective_readonly_mount(credentials, monkeypatch, readonly):
    from types import SimpleNamespace
    monkeypatch.setattr(probe.os, 'fstat', lambda fd: credential_stat(0o400, 65534))
    monkeypatch.setattr(credentials, 'credential_xattr', lambda *a: None)
    monkeypatch.setattr(probe.os, 'fstatvfs', lambda fd: SimpleNamespace(f_flag=probe.os.ST_RDONLY if readonly else 0))
    if readonly:
        assert credentials.credential_fd_metadata(99, 65534)['mount_read_only'] is True
    else:
        with pytest.raises(credentials.CredentialError, match='unsafe_credential'):
            credentials.credential_fd_metadata(99, 65534)


@pytest.mark.parametrize('write_error', [None, errno.EACCES, errno.EROFS, errno.EIO])
def test_credential_runtime_read_write_and_nofollow_controls(monkeypatch, write_error):
    closed = []
    def fake_open(path, flags, **kwargs):
        assert flags & probe.os.O_NOFOLLOW and flags & probe.os.O_CLOEXEC
        if path == '/synthetic':
            assert flags & probe.os.O_DIRECTORY
            return 90
        assert path == 'encryption_key' and kwargs == {'dir_fd': 90}
        if flags & probe.os.O_WRONLY:
            if write_error is not None:
                raise OSError(write_error, 'synthetic')
            return 92
        return 91
    monkeypatch.setattr(probe.os, 'open', fake_open)
    monkeypatch.setattr(probe.os, 'close', closed.append)
    reads = []
    def reader(directory, name, *, uid):
        reads.append((directory, name, uid))
        return probe.SYNTHETIC.encode(), {'directory': {'numeric_fixture': 1}, 'file': {'numeric_fixture': 2}}
    if write_error in (errno.EACCES, errno.EROFS):
        result = probe.probe_credentials('/synthetic', ['encryption_key'], 65534, reader)
        assert result['files'][0]['write_open_errno'] == write_error
    else:
        with pytest.raises(AssertionError, match='credential write'):
            probe.probe_credentials('/synthetic', ['encryption_key'], 65534, reader)
    assert reads == [('/synthetic', 'encryption_key', 65534)]
    assert closed == ([92, 90] if write_error is None else [90])


def test_native_fixture_copies_exact_production_helpers(tmp_path):
    probe.copy_production_helpers(tmp_path)
    for source in (probe.LISTENER_SOURCE, probe.CREDENTIAL_SOURCE):
        target = tmp_path / source.name
        assert target.read_bytes() == source.read_bytes()
        assert probe.stat.S_IMODE(target.stat().st_mode) == 0o644
    source = Path(probe.__file__).read_text()
    assert 'from credentials import read_credential_with_metadata' in source
    assert 'report["credentials_sha256"]' in source
    assert 'def validate_credential_metadata(' not in source


def test_probe_rejects_wrong_shared_reader_content_before_write_probe(monkeypatch):
    monkeypatch.setattr(probe.os, 'open', lambda *a, **k: pytest.fail('must reject content first'))
    def wrong_content(*a, **k):
        return b'wrong synthetic fixture', {'directory': {}, 'file': {}}
    with pytest.raises(AssertionError, match='credential copied'):
        probe.probe_credentials('/synthetic', ['encryption_key'], 65534, wrong_content)
