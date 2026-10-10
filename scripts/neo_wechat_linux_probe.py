#!/usr/bin/env python3
"""Synthetic native systemd containment probe, ONLY for an ephemeral CI host.

No application startup, package install, external network traffic or real secrets.
Exact production stdlib listener and credential modules exercise synthetic inputs.
All Health/credential paths are remapped to synthetic fixtures. Service identity
is an existing unprivileged nobody UID, not the production account. The retained
sandbox directives come from the actual unit template. PrivateNetwork is added
to guarantee no outside-network contact; this does NOT validate production egress.
Static verification uses the exact probe bytes with synthetic dependency stubs in
an isolated SYSTEMD_UNIT_PATH. Actual systemctl start separately validates host
dependencies and runtime behavior; those stubs are never installed or started.

Run: sudo /usr/bin/python3 scripts/neo_wechat_linux_probe.py --ephemeral-runner --require-linux
UNSUPPORTED exits 77 (1 when required); PASS is printed only after both actual
sandbox and positive controls complete and cleanup succeeds. No claim of systemd
249 compatibility is made when the observed manager has a different version.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import resource
import shutil
import socket
import stat
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra/neo-wechat/neo-wechat.service.in"
SOCKET_TEMPLATE = TEMPLATE.with_name("neo-wechat.socket.in")
LISTENER_SOURCE = ROOT / "services/neo_wechat/listener.py"
CREDENTIAL_SOURCE = ROOT / "services/neo_wechat/credentials.py"
CREDENTIALS = ("encryption_key", "admin_password_hash", "slack_webhook")
DENIED_SYSCALLS = "~bind listen io_uring_setup io_uring_enter io_uring_register"
PRESERVED_PREFIXES = (
    "Protect", "PrivateTmp=", "PrivateDevices=", "NoNewPrivileges=",
    "CapabilityBoundingSet=", "AmbientCapabilities=", "Restrict", "LockPersonality=",
    "ProcSubset=", "SystemCall", "Memory", "CPUQuota=", "TasksMax=", "Limit", "UMask=",
)
PATH_KEYS = {"ReadWritePaths", "ReadOnlyPaths", "InaccessiblePaths", "WorkingDirectory"}
SERVICE_KEYS = PATH_KEYS | {
    "Type", "User", "Group", "SupplementaryGroups", "ExecStart", "LoadCredential", "Environment",
    "UMask", "StateDirectory", "StateDirectoryMode",
    "ProtectSystem", "ProtectHome", "PrivateTmp", "PrivateDevices", "ProtectProc", "ProcSubset",
    "NoNewPrivileges", "CapabilityBoundingSet", "AmbientCapabilities", "RestrictSUIDSGID",
    "RestrictRealtime", "RestrictNamespaces", "LockPersonality", "ProtectKernelTunables",
    "ProtectKernelModules", "ProtectKernelLogs", "ProtectControlGroups", "RestrictAddressFamilies",
    "SocketBindDeny", "SystemCallArchitectures", "SystemCallFilter", "SystemCallErrorNumber",
    "MemoryMax", "MemorySwapMax", "CPUQuota", "TasksMax", "LimitNOFILE", "LimitCORE", "Restart",
    "RestartSec", "TimeoutStopSec", "KillMode", "StandardOutput", "StandardError", "SyslogIdentifier",
}
SYNTHETIC = "public synthetic fixture; no personal data\n"
# Only parser/job-graph fixtures. Never installed into a manager's search path.
# v249 supports SYSTEMD_UNIT_PATH; --recursive-errors is not available in v249.
# https://github.com/systemd/systemd/blob/v249/src/analyze/analyze-verify.c
_STUB_UNIT = "[Unit]\nDescription=Synthetic static verification dependency\nDefaultDependencies=no\n"
VERIFY_DEPENDENCIES = {
    **{name: _STUB_UNIT for name in ("sysinit.target", "basic.target", "shutdown.target", "sockets.target")},
    **{name: _STUB_UNIT + "[Slice]\n" for name in ("system.slice", "-.slice")},
    **{name: _STUB_UNIT + "[Service]\nType=oneshot\nExecStart=/usr/bin/true\n"
       for name in ("systemd-remount-fs.service", "systemd-tmpfiles-setup.service", "systemd-journald.service")},
    "systemd-journald.socket": _STUB_UNIT + "[Socket]\nListenStream=/run/neo-wx-static-only-journal.sock\n",
    "tmp.mount": _STUB_UNIT + "[Mount]\nWhat=tmpfs\nWhere=/tmp\nType=tmpfs\n",
    "-.mount": _STUB_UNIT + "[Mount]\nWhat=tmpfs\nWhere=/\nType=tmpfs\n",
}


def render_unit(template, name, *, uid, gid, control=False):
    if re.fullmatch(r"neo-wx-probe-[a-f0-9]{12}", name) is None:
        raise ValueError("invalid probe name")
    if uid <= 0 or gid <= 0:
        raise ValueError("unprivileged identity required")
    fixture = Path("/run") / (name + "-fixtures")
    plan = {"name": name, "fixture": str(fixture), "state": "/var/lib/" + name,
            "runtime": "/run/" + name, "credentials": list(CREDENTIALS),
            "hidden_files": [], "control": control, "uid": uid,
            "tmp_marker": "/tmp/" + name + "-host-marker"}
    section, items = None, []
    for raw in template.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            if line not in ("[Unit]", "[Service]"):
                raise ValueError("unexpected unit section")
            section = line
        elif "=" not in line or section is None:
            raise ValueError("unexpected unit syntax")
        else:
            key, value = line.split("=", 1)
            if section == "[Service]" and key not in SERVICE_KEYS:
                raise ValueError("unreviewed service directive: " + key)
            items.append((section, key, value))
    values = {key: value for _, key, value in items}
    for key, expected in {
        "User": "neo-wechat", "Group": "neo-wechat", "SupplementaryGroups": "neo-wechat-proxy",
        "Type": "simple", "SocketBindDeny": "any", "Restart": "on-failure",
        "StateDirectory": "neo-wechat", "Requires": "neo-wechat.socket",
        "ReadWritePaths": "/var/lib/neo-wechat",
    }.items():
        if values.get(key) != expected:
            raise ValueError("unit template shape changed: " + key)
    filters = [value for _, key, value in items if key == "SystemCallFilter"]
    if filters != ["@system-service", DENIED_SYSCALLS]:
        raise ValueError("exact bind/listen syscall boundary required")
    if "neo-wechat.socket" not in values.get("After", "").split():
        raise ValueError("socket startup ordering required")
    if any(key.startswith("Exec") and key != "ExecStart" for _, key, _ in items):
        raise ValueError("additional unit commands forbidden")
    credentials = [value for _, key, value in items if key == "LoadCredential"]
    if sorted(credentials) != sorted(f"{key}:/etc/neo-wechat/{key}" for key in CREDENTIALS):
        raise ValueError("unit credentials changed")
    if sum(key == "ExecStart" for _, key, _ in items) != 1:
        raise ValueError("exactly one command required")

    def remap(path):
        if path in ("/run/neo-wechat", "/var/lib/neo-wechat"):
            return path.replace("neo-wechat", name)
        if not path.startswith("/") or ".." in Path(path).parts:
            raise ValueError("unexpected template path")
        return str(fixture / "fs" / path.lstrip("/"))

    lines = ["[Unit]", "Description=Synthetic Neo WeChat sandbox evidence",
             f"Requires={name}.socket", f"After={name}.socket", "[Service]"]
    overrides = {
        "User": str(uid), "Group": str(gid), "SupplementaryGroups": "",
        "Type": "oneshot", "StateDirectory": name,
        "ExecStart": f"/usr/bin/python3 -I -B {fixture}/probe.py --worker {fixture}/plan.json",
        "Restart": "no", "SyslogIdentifier": name,
    }
    for section, key, value in items:
        if section != "[Service]":
            continue  # Production network ordering/start conditions are not exercised.
        if key in overrides:
            value = overrides[key]
        elif key in PATH_KEYS:
            mapped = []
            for path in value.split():
                target = remap(path.lstrip("-"))
                mapped.append(("-" if path.startswith("-") else "") + target)
                if key == "InaccessiblePaths":
                    original = path.lstrip("-")
                    plan["hidden_files"].append(target if original.startswith("/etc/neo-wechat/")
                                                else target + "/synthetic-record")
            value = " ".join(mapped)
        elif key == "LoadCredential":
            cred, path = value.split(":", 1)
            value = cred + ":" + remap(path)
        if control and key in ("InaccessiblePaths", "SocketBindDeny"):
            value = ""
        if control and key == "SystemCallFilter" and value == DENIED_SYSCALLS:
            continue
        lines.append(key + "=" + value)
    lines.extend(("RemainAfterExit=yes", "TimeoutStartSec=30", "PrivateNetwork=yes"))
    plan["config"] = remap("/etc/neo-wechat/config.json")
    plan["readonly"] = remap("/opt/neo-wechat") + "/synthetic-record"
    return "\n".join(lines) + "\n", plan


def render_socket(template, plan, *, gid):
    expected = {"ListenStream": "/run/neo-wechat/bridge.sock", "SocketUser": "neo-wechat",
                "SocketGroup": "neo-wechat-proxy", "SocketMode": "0660", "DirectoryMode": "0755",
                "RemoveOnStop": "yes", "Service": "neo-wechat.service",
                "FileDescriptorName": "neo-wechat-http", "Backlog": "16"}
    items, section = [], None
    for raw in template.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            if line not in ("[Unit]", "[Socket]"):
                raise ValueError("unexpected socket section")
            section = line
        elif "=" not in line or section is None:
            raise ValueError("unexpected socket syntax")
        elif section == "[Socket]":
            key, value = line.split("=", 1)
            if key not in expected and (key, value) != ("Accept", "no"):
                raise ValueError("unreviewed socket directive")
            items.append((key, value))
    values = dict(items)
    if len(values) != len(items) or any(values.get(key) != value for key, value in expected.items()):
        raise ValueError("socket template shape changed")
    overrides = {"ListenStream": plan["runtime"] + "/bridge.sock", "SocketUser": str(plan["uid"]),
                 "SocketGroup": str(gid), "Service": plan["name"] + ".service"}
    lines = ["[Unit]", "Description=Synthetic Neo WeChat activation socket", "[Socket]"]
    lines.extend(key + "=" + overrides.get(key, value) for key, value in items)
    return "\n".join(lines) + "\n"


def exercise_ip_policy(control):
    """Test both bind forms and Linux implicit autobind via listen, independently."""
    attempts = []
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        for operation, port in (("bind", 0), ("bind", 43193), ("listen", None)):
            with socket.socket(family, socket.SOCK_STREAM) as candidate:
                try:
                    if operation == "bind":
                        candidate.bind((address, port))
                    else:
                        candidate.listen(1)
                except OSError as error:
                    assert not control and error.errno in (errno.EPERM, errno.EACCES), "IP syscall control"
                else:
                    assert control, "IP " + operation + " permitted"
            attempts.append({"family": int(family), "operation": operation, "port": port,
                             "result": "allowed" if control else "denied"})
    return attempts


def io_uring_numbers():
    # Native x86_64 and arm64 share 425..427 (Linux v5.15 syscall_64.tbl /
    # include/uapi/asm-generic/unistd.h). No guessed compatibility-ABI numbers.
    if (sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64")
            or ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_long) != 8):
        raise ValueError("io_uring probe requires verified native Linux x86_64 or aarch64 ABI")
    return (("io_uring_setup", 425, (0, 0)),
            ("io_uring_enter", 426, (-1, 0, 0, 0, 0, 0)),
            ("io_uring_register", 427, (-1, 0, 0, 0)))


def invoke_io_uring(number, args):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    ctypes.set_errno(0)
    result = libc.syscall(ctypes.c_long(number), *(ctypes.c_long(arg) for arg in args))
    return int(result), ctypes.get_errno()


def exercise_io_uring_policy(control):
    outcomes = []
    for name, number, args in io_uring_numbers():
        result, error = invoke_io_uring(number, args)
        if result >= 0:
            # Setup is the only syscall here that could return an owned FD.
            if name == "io_uring_setup":
                os.close(result)
            assert control and name == "io_uring_setup", "io_uring syscall unexpectedly succeeded"
            outcome = "allowed_result_closed"
        else:
            assert result == -1, "io_uring malformed return value"
            if error in (errno.EPERM, errno.EACCES):
                outcome = "control_permission_denied_not_attributable" if control else "denied"
            else:
                assert control and error in (errno.EBADF, errno.EINVAL, errno.EFAULT, errno.ENOSYS), "io_uring denial missing"
                outcome = "kernel_unavailable_not_attributable" if error == errno.ENOSYS else "allowed_invalid_arguments"
        outcomes.append({"syscall": name, "number": number, "result": result,
                         "errno": error if result < 0 else 0, "outcome": outcome})
    return outcomes


def validate_cgroup(values):
    assert values["memory.max"] == "268435456", "memory cgroup limit"
    assert values["memory.swap.max"] == "0", "swap cgroup limit"
    assert values["pids.max"] == "32", "task cgroup limit"
    parts = values["cpu.max"].split()
    assert len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit(), "CPU cgroup limit"
    assert int(parts[0]) * 4 == int(parts[1]), "CPU cgroup quota"


def probe_credentials(directory, names, uid, reader):
    """Use the exact production reader, then independently probe write denial."""
    report = {"files": []}
    for name in names:
        assert name in CREDENTIALS, "unexpected credential name"
        contents, metadata = reader(directory, name, uid=uid)
        assert contents == SYNTHETIC.encode(), "credential copied"
        if "directory" in report:
            assert report["directory"] == metadata["directory"], "credential directory changed"
        report["directory"] = metadata["directory"]
        file_report = dict(metadata["file"])
        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            try:
                writable = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dfd)
            except OSError as error:
                assert error.errno in (errno.EACCES, errno.EPERM, errno.EROFS), "credential write denial"
                file_report['write_open_errno'] = error.errno
            else:
                os.close(writable)
                raise AssertionError("credential write-open permitted")
        finally:
            os.close(dfd)
        report['files'].append(file_report)
    return report


def copy_production_helpers(fixture):
    for source in (LISTENER_SOURCE, CREDENTIAL_SOURCE):
        target = fixture / source.name
        shutil.copyfile(source, target)
        target.chmod(0o644)


def worker(plan_path):
    """Executed by systemd as an unprivileged UID in the real sandbox."""
    plan = json.loads(Path(plan_path).read_text())
    assert os.getuid() == plan["uid"] != 0, "unprivileged UID"
    # Copy of the production stdlib-only adapter, with only the expected path remapped.
    sys.path.insert(0, plan["fixture"])
    from listener import inherited_listener
    from credentials import read_credential_with_metadata
    listener = inherited_listener(plan["runtime"] + "/bridge.sock")
    # asyncio calls listen again even for activated sockets; adapter must no-op.
    listener.listen(16)
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    assert status["NoNewPrivs"].strip() == "1", "no-new-privileges"
    for cap in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        assert int(status[cap].strip(), 16) == 0, "capability set"
    assert resource.getrlimit(resource.RLIMIT_NOFILE) == (256, 256), "descriptor limit"
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0), "core limit"
    assert not Path(plan["tmp_marker"]).exists(), "private temporary directory"
    assert Path(plan["config"]).read_text() == SYNTHETIC, "nonsecret config readable"
    assert Path(plan["readonly"]).read_text() == SYNTHETIC, "readonly positive control"
    try:
        with open(plan["readonly"], "a") as stream:
            stream.write("unexpected write")
    except OSError as error:
        assert error.errno == errno.EROFS, "must fail at read-only mount, not DAC"
    else:
        raise AssertionError("readonly runtime writable")
    for path in plan["hidden_files"]:
        try:
            contents = Path(path).read_text()
        except OSError as error:
            assert not plan["control"] and error.errno in (errno.EACCES, errno.EPERM), "hidden path control"
        else:
            assert plan["control"] and contents == SYNTHETIC, "sensitive fixture exposed"
    credential_report = probe_credentials(os.environ["CREDENTIALS_DIRECTORY"], plan["credentials"], plan["uid"],
                                          read_credential_with_metadata)
    with listener:
        listener.settimeout(10)
        with listener.accept()[0] as accepted:
            accepted.settimeout(10)
            assert accepted.recv(9) == b"synthetic", "inherited Unix socket exchange"
            accepted.sendall(b"synthetic")
    ip_attempts = exercise_ip_policy(plan["control"])
    io_attempts = exercise_io_uring_policy(plan["control"])
    entries = Path("/proc/self/cgroup").read_text().splitlines()
    unified = [entry[3:] for entry in entries if entry.startswith("0::/")]
    assert len(unified) == 1 and ".." not in Path(unified[0]).parts, "unified cgroup path"
    cgroup = Path("/sys/fs/cgroup") / unified[0].lstrip("/")
    limits = {name: (cgroup / name).read_text().strip()
              for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}
    validate_cgroup(limits)
    output = {"status": "PASS", "control": plan["control"], "hidden_fixtures": len(plan["hidden_files"]),
              "unix_socket": "inherited FD PASS", "ip_syscalls": ip_attempts,
              "io_uring_syscalls": io_attempts,
              "credential_copies": "PASS", "credential_metadata": credential_report,
              "cgroup": limits, "privilege_limits": "PASS"}
    (Path(plan["state"]) / "report.json").write_text(json.dumps(output))


def unsupported_reason():
    if sys.platform != "linux":
        return "Linux required; native sandbox unverified"
    if os.geteuid() != 0:
        return "root required on a disposable runner"
    if not Path("/run/systemd/system").is_dir() or Path("/proc/1/comm").read_text().strip() != "systemd":
        return "systemd system manager required"
    if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        return "unified cgroup v2 required"
    if any(Path(path).exists() for path in ("/opt/health-app", "/etc/health-app", "/var/lib/reva-release", "/etc/neo-wechat")):
        return "refusing a host with Health/release/bridge paths"
    for command in ("/usr/bin/python3", "/usr/bin/systemctl", "/usr/bin/systemd-analyze"):
        if not Path(command).is_file():
            return "required Linux command missing"
    return None


def run(*args, timeout=45):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin", "LANG": "C"}, timeout=timeout)
    if result.returncode:
        # Only this probe's controlled commands are passed here; bounded synthetic diagnostics.
        raise RuntimeError(f"probe command failed ({Path(args[0]).name}): {result.stderr[:4000]}")
    return result.stdout


def verify_unit(unit, fixture, *paired_units):
    """Fail on every diagnostic, excluding host units by load path, not text filters."""
    directory = fixture / "verify-units"
    directory.mkdir(mode=0o755)
    for name, content in VERIFY_DEPENDENCIES.items():
        (directory / name).write_text(content)
    candidates = []
    for source in (unit, *paired_units):
        candidate = directory / source.name
        candidate.write_bytes(source.read_bytes())
        candidates.append(candidate)
    # No trailing colon: defaults are replaced, not appended. The CLI argument's
    # directory is also isolated; v249 prepends it to its generated unit path.
    verified = subprocess.run(["/usr/bin/systemd-analyze", "--man=no", "verify", *map(str, candidates)],
                              capture_output=True, text=True, timeout=20,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C", "SYSTEMD_COLORS": "0",
                                   "SYSTEMD_UNIT_PATH": str(directory)})
    if verified.returncode or verified.stderr.strip() or verified.stdout.strip():
        raise RuntimeError("unit verification failed: " + (verified.stderr or verified.stdout)[:4000])
    return {"dependency_scope": "synthetic static dependencies only",
            "unit_sha256": hashlib.sha256(candidates[0].read_bytes()).hexdigest(),
            "paired_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in candidates[1:]}}


def unit_failure_diagnostics(error, *units):
    """Keep the triggering error even when its scoped journal is unavailable."""
    try:
        diagnostics = run("/usr/bin/journalctl", "--no-pager", "--output=cat", "-n", "30",
                          *("--unit=" + unit for unit in units))[-2400:]
    except (OSError, RuntimeError, subprocess.SubprocessError) as journal_error:
        diagnostics = "journal unavailable: " + str(journal_error)[:600]
    return "synthetic unit failed: " + repr(error)[:1000] + "; scoped journal: " + diagnostics


def cleanup_probe(unit, socket_unit, fixture, state, runtime, marker, *, registered, primary_error):
    """Prove both units inactive before removal; never replace the primary error."""
    try:
        if registered:
            run("/usr/bin/systemctl", "stop", socket_unit.name, unit.name)
            for candidate in (unit, socket_unit):
                def read_state():
                    output = run("/usr/bin/systemctl", "show", "--property=LoadState,ActiveState", candidate.name)
                    values = dict(line.split("=", 1) for line in output.splitlines())
                    if set(values) != {"LoadState", "ActiveState"} or values["LoadState"] not in ("loaded", "not-found"):
                        raise RuntimeError("unexpected cleanup unit state: " + output[:500])
                    return values["ActiveState"]
                active = read_state()
                # Inactive units may already have been garbage-collected by the
                # manager. reset-failed on such a unit is invalid, not cleanup.
                if active == "failed":
                    run("/usr/bin/systemctl", "reset-failed", candidate.name)
                    active = read_state()
                if active != "inactive":
                    raise RuntimeError("cleanup unit not inactive: " + candidate.name + " " + active)
        unit.unlink(missing_ok=True)
        socket_unit.unlink(missing_ok=True)
        run("/usr/bin/systemctl", "daemon-reload")
        for owned in (fixture, state, runtime):
            if owned.exists():
                shutil.rmtree(owned)
        marker.unlink(missing_ok=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as cleanup_error:
        primary = ("primary failure: " + repr(primary_error)[:3000] + "; ") if primary_error is not None else ""
        raise RuntimeError(primary + "cleanup failed: " + repr(cleanup_error)[:800]) from cleanup_error


def native(template):
    io_uring_numbers()  # Fail before any host mutation if the ABI is unsupported.
    identity = pwd.getpwnam("nobody")
    results = []
    version = run("/usr/bin/systemd-analyze", "--version").splitlines()[0]
    for control in (False, True):
        name = "neo-wx-probe-" + uuid.uuid4().hex[:12]
        text, plan = render_unit(template, name, uid=identity.pw_uid, gid=identity.pw_gid, control=control)
        fixture = Path(plan["fixture"])
        state = Path(plan["state"])
        runtime = Path(plan["runtime"])
        unit = Path("/run/systemd/system") / (name + ".service")
        socket_unit = unit.with_suffix(".socket")
        socket_text = render_socket(SOCKET_TEMPLATE.read_text(), plan, gid=identity.pw_gid)
        marker = Path(plan["tmp_marker"])
        if any(path.exists() or path.is_symlink() for path in (fixture, state, runtime, unit, socket_unit, marker)):
            raise RuntimeError("probe object collision")
        fixture.mkdir(mode=0o755)
        registered = False
        primary_error = None
        try:
            for target in plan["hidden_files"] + [plan["config"], plan["readonly"]]:
                path = Path(target)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(SYNTHETIC)
                path.chmod(0o644)
            # Remove DAC as a confounder: write must fail because of the read-only mount.
            Path(plan["readonly"]).chmod(0o666)
            for parent in fixture.rglob("*"):
                if parent.is_dir():
                    parent.chmod(0o755)
            shutil.copyfile(__file__, fixture / "probe.py")
            (fixture / "probe.py").chmod(0o644)
            copy_production_helpers(fixture)
            (fixture / "plan.json").write_text(json.dumps(plan))
            (fixture / "plan.json").chmod(0o644)
            marker.write_text(SYNTHETIC)
            marker.chmod(0o644)
            unit.write_text(text)
            unit.chmod(0o644)
            socket_unit.write_text(socket_text)
            socket_unit.chmod(0o644)
            verification = verify_unit(unit, fixture, socket_unit)
            run("/usr/bin/systemctl", "daemon-reload")
            registered = True
            try:
                run("/usr/bin/systemctl", "start", socket_unit.name)
                assert runtime.stat().st_uid == 0 and stat.S_IMODE(runtime.stat().st_mode) == 0o755
                node = (runtime / "bridge.sock").stat()
                assert stat.S_ISSOCK(node.st_mode) and node.st_uid == identity.pw_uid
                assert node.st_gid == identity.pw_gid and stat.S_IMODE(node.st_mode) == 0o660
                # Enqueue the service explicitly; don't depend on client traffic to start it.
                run("/usr/bin/systemctl", "--no-block", "start", unit.name)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(15)
                    client.connect(str(runtime / "bridge.sock"))
                    client.sendall(b"synthetic")
                    assert client.recv(9) == b"synthetic", "root client Unix exchange"
                # Wait for the oneshot checks and report to finish, with their 30s timeout.
                run("/usr/bin/systemctl", "start", name + ".service")
            except (RuntimeError, OSError, AssertionError, subprocess.SubprocessError) as error:
                # Only this synthetic pair is queried, never unrelated services.
                raise RuntimeError(unit_failure_diagnostics(error, unit.name, socket_unit.name)) from error
            assert run("/usr/bin/systemctl", "is-active", name + ".service").strip() == "active"
            report = json.loads((state / "report.json").read_text())
            assert report["status"] == "PASS" and report["control"] == control
            report["static_verification"] = verification
            report["host_dependency_start"] = "PASS"
            report["listener_sha256"] = hashlib.sha256((fixture / "listener.py").read_bytes()).hexdigest()
            report["credentials_sha256"] = hashlib.sha256((fixture / "credentials.py").read_bytes()).hexdigest()
            results.append(report)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            cleanup_probe(unit, socket_unit, fixture, state, runtime, marker,
                          registered=registered, primary_error=primary_error)
    return {"status": "PASS", "manager": version,
            "systemd_249_observed": bool(re.match(r"systemd 249(?:\s|$)", version)),
            "template_sha256": hashlib.sha256(template.encode()).hexdigest(), "runs": results,
            "socket_template_sha256": hashlib.sha256(SOCKET_TEMPLATE.read_bytes()).hexdigest(),
            "scope": "synthetic remapped paths and nobody UID; production identity, egress and proxy unverified"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ephemeral-runner", action="store_true")
    parser.add_argument("--require-linux", action="store_true")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker is not None:
        worker(args.worker)
        return 0
    if not args.ephemeral_runner:
        parser.error("explicit --ephemeral-runner is required; never run on production")
    reason = unsupported_reason()
    if reason:
        print(json.dumps({"status": "UNSUPPORTED", "reason": reason}))
        return 1 if args.require_linux else 77
    try:
        result = native(TEMPLATE.read_text())
    except (AssertionError, OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)[:4000]}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
