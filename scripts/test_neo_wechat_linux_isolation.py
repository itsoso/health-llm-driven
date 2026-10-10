"""Portable probe-contract tests; native evidence requires the explicit CLI below.

On an ephemeral Linux/systemd CI runner (never production):
  sudo /usr/bin/python3 scripts/neo_wechat_linux_probe.py --ephemeral-runner --require-linux

The native command exits 77 when unsupported, or 1 with --require-linux. Neither
case is a pass. Pytest on macOS runs only these construction/validation tests.
"""
import importlib.util
from pathlib import Path
import subprocess

import pytest
import yaml


SPEC = importlib.util.spec_from_file_location(
    "neo_wechat_linux_probe", Path(__file__).with_name("neo_wechat_linux_probe.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
TEMPLATE = Path(__file__).resolve().parents[1] / "infra/neo-wechat/neo-wechat.service.in"


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


def test_control_changes_only_two_boundaries_and_worker_expectation():
    text, plan = render()
    control, control_plan = render(True)
    expected = "\n".join(
        "InaccessiblePaths=" if line.startswith("InaccessiblePaths=")
        else "SocketBindDeny=" if line.startswith("SocketBindDeny=")
        else line for line in text.splitlines()) + "\n"
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
    lambda s: s.replace("ReadWritePaths=/var/lib/neo-wechat /run/neo-wechat", "ReadWritePaths=/"),
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
