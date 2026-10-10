#!/usr/bin/env python3
"""Synthetic native systemd containment probe, ONLY for an ephemeral CI host.

No application code, package install, external network traffic or real secrets.
All Health/credential paths are remapped to synthetic fixtures. Service identity
is an existing unprivileged nobody UID, not the production account. The retained
sandbox directives come from the actual unit template. PrivateNetwork is added
to guarantee no outside-network contact; this does NOT validate production egress.

Run: sudo /usr/bin/python3 scripts/neo_wechat_linux_probe.py --ephemeral-runner --require-linux
UNSUPPORTED exits 77 (1 when required); PASS is printed only after both actual
sandbox and positive controls complete and cleanup succeeds. No claim of systemd
249 compatibility is made when the observed manager has a different version.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
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
CREDENTIALS = ("encryption_key", "admin_password_hash", "slack_webhook")
PRESERVED_PREFIXES = (
    "Protect", "PrivateTmp=", "PrivateDevices=", "NoNewPrivileges=",
    "CapabilityBoundingSet=", "AmbientCapabilities=", "Restrict", "LockPersonality=",
    "ProcSubset=", "SystemCall", "Memory", "CPUQuota=", "TasksMax=", "Limit", "UMask=",
)
PATH_KEYS = {"ReadWritePaths", "ReadOnlyPaths", "InaccessiblePaths", "WorkingDirectory"}
SERVICE_KEYS = PATH_KEYS | {
    "Type", "User", "Group", "SupplementaryGroups", "ExecStart", "LoadCredential", "Environment",
    "UMask", "RuntimeDirectory", "RuntimeDirectoryMode", "StateDirectory", "StateDirectoryMode",
    "ProtectSystem", "ProtectHome", "PrivateTmp", "PrivateDevices", "ProtectProc", "ProcSubset",
    "NoNewPrivileges", "CapabilityBoundingSet", "AmbientCapabilities", "RestrictSUIDSGID",
    "RestrictRealtime", "RestrictNamespaces", "LockPersonality", "ProtectKernelTunables",
    "ProtectKernelModules", "ProtectKernelLogs", "ProtectControlGroups", "RestrictAddressFamilies",
    "SocketBindDeny", "SystemCallArchitectures", "SystemCallFilter", "SystemCallErrorNumber",
    "MemoryMax", "MemorySwapMax", "CPUQuota", "TasksMax", "LimitNOFILE", "LimitCORE", "Restart",
    "RestartSec", "TimeoutStopSec", "KillMode", "StandardOutput", "StandardError", "SyslogIdentifier",
}
SYNTHETIC = "public synthetic fixture; no personal data\n"


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
        "RuntimeDirectory": "neo-wechat", "StateDirectory": "neo-wechat",
        "ReadWritePaths": "/var/lib/neo-wechat /run/neo-wechat",
    }.items():
        if values.get(key) != expected:
            raise ValueError("unit template shape changed: " + key)
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

    lines = ["[Unit]", "Description=Synthetic Neo WeChat sandbox evidence", "[Service]"]
    overrides = {
        "User": str(uid), "Group": str(gid), "SupplementaryGroups": "",
        "Type": "oneshot", "RuntimeDirectory": name, "StateDirectory": name,
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
        lines.append(key + "=" + value)
    lines.extend(("RemainAfterExit=yes", "RuntimeMaxSec=30", "TimeoutStartSec=30", "PrivateNetwork=yes"))
    plan["config"] = remap("/etc/neo-wechat/config.json")
    plan["readonly"] = remap("/opt/neo-wechat") + "/synthetic-record"
    return "\n".join(lines) + "\n", plan


def validate_cgroup(values):
    assert values["memory.max"] == "268435456", "memory cgroup limit"
    assert values["memory.swap.max"] == "0", "swap cgroup limit"
    assert values["pids.max"] == "32", "task cgroup limit"
    parts = values["cpu.max"].split()
    assert len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit(), "CPU cgroup limit"
    assert int(parts[0]) * 4 == int(parts[1]), "CPU cgroup quota"


def worker(plan_path):
    """Executed by systemd as an unprivileged UID in the real sandbox."""
    plan = json.loads(Path(plan_path).read_text())
    assert os.getuid() == plan["uid"] != 0, "unprivileged UID"
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
    creds = Path(os.environ["CREDENTIALS_DIRECTORY"])
    for name in plan["credentials"]:
        path = creds / name
        assert path.read_text() == SYNTHETIC, "credential copied"
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0, "credential private mode"
    runtime = Path(plan["runtime"])
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(runtime / "bridge.sock"))
        listener.listen(1)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(runtime / "bridge.sock"))
            with listener.accept()[0] as accepted:
                accepted.settimeout(2)
                client.sendall(b"synthetic")
                assert accepted.recv(9) == b"synthetic", "Unix socket exchange"
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            try:
                listener.bind((address, 0))
                listener.listen(1)
            except OSError as error:
                assert not plan["control"] and error.errno in (errno.EPERM, errno.EACCES), "IP bind control"
            else:
                assert plan["control"], "IP listener permitted"
    entries = Path("/proc/self/cgroup").read_text().splitlines()
    unified = [entry[3:] for entry in entries if entry.startswith("0::/")]
    assert len(unified) == 1 and ".." not in Path(unified[0]).parts, "unified cgroup path"
    cgroup = Path("/sys/fs/cgroup") / unified[0].lstrip("/")
    limits = {name: (cgroup / name).read_text().strip()
              for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}
    validate_cgroup(limits)
    output = {"status": "PASS", "control": plan["control"], "hidden_fixtures": len(plan["hidden_files"]),
              "unix_socket": "PASS", "ip_bind": "allowed" if plan["control"] else "denied",
              "credential_copies": "PASS", "cgroup": limits, "privilege_limits": "PASS"}
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


def native(template):
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
        marker = Path(plan["tmp_marker"])
        if any(path.exists() or path.is_symlink() for path in (fixture, state, runtime, unit, marker)):
            raise RuntimeError("probe object collision")
        fixture.mkdir(mode=0o755)
        registered = False
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
            (fixture / "plan.json").write_text(json.dumps(plan))
            (fixture / "plan.json").chmod(0o644)
            marker.write_text(SYNTHETIC)
            marker.chmod(0o644)
            unit.write_text(text)
            unit.chmod(0o644)
            # An unsupported directive must not silently turn into a passing test.
            verified = subprocess.run(["/usr/bin/systemd-analyze", "verify", str(unit)],
                                      capture_output=True, text=True, timeout=20,
                                      env={"PATH": "/usr/bin:/bin", "LANG": "C"})
            if verified.returncode or verified.stderr.strip():
                raise RuntimeError("unit verification failed: " + verified.stderr[:4000])
            run("/usr/bin/systemctl", "daemon-reload")
            registered = True
            try:
                run("/usr/bin/systemctl", "start", name + ".service")
            except RuntimeError:
                # Only our uniquely named synthetic unit is queried, never other services.
                diagnostics = run("/usr/bin/journalctl", "--no-pager", "--output=cat", "-n", "30",
                                  "--unit=" + name + ".service")
                raise RuntimeError("synthetic unit failed: " + diagnostics[-4000:]) from None
            assert run("/usr/bin/systemctl", "is-active", name + ".service").strip() == "active"
            report = json.loads((state / "report.json").read_text())
            assert report["status"] == "PASS" and report["control"] == control
            results.append(report)
        finally:
            # Stop must succeed before removing any possible working/state paths.
            if registered:
                run("/usr/bin/systemctl", "stop", name + ".service")
                run("/usr/bin/systemctl", "reset-failed", name + ".service")
            unit.unlink(missing_ok=True)
            run("/usr/bin/systemctl", "daemon-reload")
            for owned in (fixture, state, runtime):
                if owned.exists():
                    shutil.rmtree(owned)
            marker.unlink(missing_ok=True)
    return {"status": "PASS", "manager": version,
            "systemd_249_observed": bool(re.match(r"systemd 249(?:\s|$)", version)),
            "template_sha256": hashlib.sha256(template.encode()).hexdigest(), "runs": results,
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
