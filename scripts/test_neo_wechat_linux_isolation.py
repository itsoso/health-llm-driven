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
