#!/usr/bin/env python3
"""Fixed-scope host hardening, invoked only by deploy.sh after exact revision proof.

No validator restart, key copy, chain flush or generic command input is supported.
An interrupted apply leaves a root-only receipt and requires operator inspection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path("/opt/health-app")
UNITS = Path("/etc/systemd/system")
STAKING = Path("/mnt/data/lighthouse/validators")
APPLICATION_PORTS = {"health-app": (5432, 6379, 8000, 8092, 8719, 443),
                     "health-web": (8000, 443)}


def run(*args):
    args = ({"useradd": "/usr/sbin/useradd", "ufw": "/usr/sbin/ufw"}.get(args[0], args[0]), *args[1:])
    result = subprocess.run(args, text=True, capture_output=True, timeout=60)
    if result.returncode:
        # Never print process output: PM2 and systemd may include environment data.
        raise RuntimeError(f"command failed: {args[0]} (exit={result.returncode})")
    return result.stdout


def trusted(path, *, directory=False):
    s = path.lstat()
    if s.st_uid != 0 or s.st_mode & 0o022 or stat.S_ISLNK(s.st_mode):
        raise RuntimeError("untrusted filesystem metadata")
    if not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)):
        raise RuntimeError("unexpected filesystem object type")


def atomic_write(path, text, mode=0o644):
    if path.exists() or path.is_symlink():
        trusted(path)
    temp = path.with_name(path.name + ".reva-security-new")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    os.fchmod(fd, mode)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temp.exists():
            temp.unlink()


def firewall_rules(user, uid, ipv6=False):
    if user not in APPLICATION_PORTS or not isinstance(uid, int) or uid <= 0:
        raise ValueError("dedicated non-root application identity required")
    chain = "REVA_HEALTH_APP" if user == "health-app" else "REVA_HEALTH_WEB"
    reject = ("-j", "REJECT", "--reject-with", "icmp6-port-unreachable" if ipv6 else "icmp-port-unreachable")
    rules = [
        ("-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "--ctdir", "REPLY", "-j", "RETURN"),
        ("-m", "addrtype", "--dst-type", "LOCAL", "-p", "tcp", "-m", "multiport",
         "--dports", ",".join(map(str, APPLICATION_PORTS[user])), "-j", "RETURN"),
        ("-m", "addrtype", "--dst-type", "LOCAL", "-p", "udp", "--dport", "53", "-j", "RETURN"),
        ("-m", "addrtype", "--dst-type", "LOCAL", "-p", "tcp", "--dport", "53", "-j", "RETURN"),
        ("-m", "addrtype", "--dst-type", "LOCAL", *reject),
    ]
    denied = ("fc00::/7", "fe80::/10") if ipv6 else (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16")
    rules.extend(("-d", cidr, *reject) for cidr in denied)
    return chain, rules, ("-m", "owner", "--uid-owner", str(uid), "-j", chain)


def canonical_rule(rule):
    """Compare option/value multisets within each rule; retain chain order."""
    if len(rule) % 2:
        raise RuntimeError("unexpected iptables serialization")
    pairs = []
    for option, value in zip(rule[::2], rule[1::2]):
        if option == "-m" and value in ("tcp", "udp"):
            continue
        if option == "--ctstate":
            value = ",".join(sorted(value.split(",")))
        pairs.append((option, value))
    return sorted(pairs)


def network_guard():
    for user in APPLICATION_PORTS:
        uid = pwd.getpwnam(user).pw_uid
        for binary, ipv6 in (("/usr/sbin/iptables", False), ("/usr/sbin/ip6tables", True)):
            chain, rules, jump = firewall_rules(user, uid, ipv6)
            found = subprocess.run([binary, "-w", "5", "-S", chain], capture_output=True, text=True)
            if found.returncode == 1:
                run(binary, "-w", "5", "-N", chain)
                for rule in rules:
                    run(binary, "-w", "5", "-A", chain, *rule)
            elif found.returncode != 0:
                raise RuntimeError("cannot inspect application egress chain")
            # Existing chains are never flushed or silently repaired.
            for rule in rules:
                run(binary, "-w", "5", "-C", chain, *rule)
            actual = [shlex.split(x)[2:] for x in run(binary, "-w", "5", "-S", chain).splitlines()
                      if x.startswith("-A ")]
            if [canonical_rule(rule) for rule in actual] != [canonical_rule(rule) for rule in rules]:
                raise RuntimeError("unexpected egress chain rules")
            check = subprocess.run([binary, "-w", "5", "-C", "OUTPUT", *jump], capture_output=True)
            if check.returncode == 1:
                run(binary, "-w", "5", "-I", "OUTPUT", "1", *jump)
            elif check.returncode:
                raise RuntimeError("cannot inspect application egress attachment")

    # Owner jumps must precede UFW or any other permissive OUTPUT rule.
    for binary, ipv6 in (("/usr/sbin/iptables", False), ("/usr/sbin/ip6tables", True)):
        actual = [shlex.split(line)[2:] for line in run(binary, "-w", "5", "-S", "OUTPUT").splitlines()
                  if line.startswith("-A ")]
        expected = [firewall_rules(user, pwd.getpwnam(user).pw_uid, ipv6)[2]
                    for user in reversed(APPLICATION_PORTS)]
        if [canonical_rule(x) for x in actual[:2]] != [canonical_rule(x) for x in expected]:
            raise RuntimeError("application egress jumps are not first in OUTPUT")


def ready(port):
    deadline = time.monotonic() + 30
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/login", timeout=2) as r:
                if r.status == 200:
                    return
        except (OSError, ValueError):
            time.sleep(.5)
    raise RuntimeError("frontend did not become ready")


def pm2_frontend():
    entries = [x for x in json.loads(run("pm2", "jlist")) if x.get("name") == "health-frontend"]
    if len(entries) != 1:
        raise RuntimeError("expected exactly one legacy frontend process")
    item = entries[0]
    env = item["pm2_env"]
    if env.get("pm_cwd") != str(ROOT / "frontend") or env.get("pm_exec_path") != "/usr/bin/npm":
        raise RuntimeError("legacy frontend identity mismatch")
    return item["pid"]


def backup_configuration(receipt, paths):
    manifest = []
    archive_path = receipt / "config-before.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in paths:
            if not path.exists() and not path.is_symlink():
                manifest.append({"path": str(path), "exists": False})
                continue
            trusted(path)
            data = path.read_bytes()
            manifest.append({"path": str(path), "exists": True,
                             "mode": stat.S_IMODE(path.stat().st_mode),
                             "sha256": hashlib.sha256(data).hexdigest()})
            archive.add(path, arcname=str(path).lstrip("/"), recursive=False)
    os.chmod(archive_path, 0o600)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        expected = [entry for entry in manifest if entry["exists"]]
        if len(members) != len(expected):
            raise RuntimeError("configuration archive membership mismatch")
        for entry in expected:
            member = archive.getmember(entry["path"].lstrip("/"))
            if not member.isfile() or member.mode != entry["mode"]:
                raise RuntimeError("configuration archive metadata mismatch")
            with archive.extractfile(member) as source:
                if hashlib.sha256(source.read()).hexdigest() != entry["sha256"]:
                    raise RuntimeError("configuration archive content mismatch")
    with archive_path.open("rb") as source:
        os.fsync(source.fileno())
    atomic_write(receipt / "config-manifest.json", json.dumps(manifest), 0o600)



def preflight_commands():
    for path in ("/usr/sbin/useradd", "/usr/sbin/ufw", "/usr/sbin/iptables",
                 "/usr/sbin/ip6tables", "/usr/sbin/iptables-save", "/usr/sbin/ip6tables-save",
                 "/usr/bin/node", "/usr/bin/npm", "/usr/bin/pm2", "/usr/bin/git",
                 "/usr/bin/systemctl", "/usr/bin/systemd-analyze"):
        original = Path(path)
        resolved = original.resolve(strict=True)
        for item in (original, *reversed(resolved.parents), resolved):
            info = item.lstat()
            if info.st_uid != 0 or (not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022):
                raise RuntimeError("unsafe required command")
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise RuntimeError("required command is not executable")
    if "Status: active" not in run("/usr/sbin/ufw", "status"):
        raise RuntimeError("UFW is not active")


def apply(sha):
    if not re.fullmatch(r"[a-f0-9]{40}", sha or ""):
        raise ValueError("exact revision required")
    trusted(ROOT, directory=True)
    if run("git", "-C", str(ROOT), "rev-parse", "HEAD").strip() != sha:
        raise RuntimeError("production revision mismatch")
    if run("git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("production source is dirty")
    if run("systemctl", "show", "health-frontend", "-p", "MainPID", "--value").strip() != "0":
        raise RuntimeError("unexpected existing systemd frontend")
    legacy_pid = pm2_frontend()
    ready(30001)
    for binary in ("/usr/bin/node", "/usr/sbin/iptables", "/usr/sbin/ip6tables"):
        if not Path(binary).exists():
            raise RuntimeError("required host binary absent")
    for name in ("health-frontend", "health-network-guard"):
        trusted(ROOT / "infra/systemd" / f"{name}.service")
    trusted(STAKING, directory=True)
    keys = [p for p in STAKING.rglob("*") if "keystore" in p.name and p.is_file()]
    if not keys:
        raise RuntimeError("no inventoried keystore metadata")
    for key in keys:
        trusted(key)
    base = Path("/var/backups/health-app/host-security")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    trusted(base, directory=True)
    receipt = base / sha
    receipt.mkdir(mode=0o700)  # Never replay an incomplete operation.
    atomic_write(receipt / "intent.json", json.dumps({"sha": sha, "legacy_pid": legacy_pid,
        "key_modes": [{"path": str(k), "mode": stat.S_IMODE(k.stat().st_mode)} for k in keys]}), 0o600)
    backup_configuration(receipt, [
        UNITS / "health-frontend.service", UNITS / "health-network-guard.service",
        UNITS / "health-frontend-security-preflight.service",
        *(UNITS / f"{name}.service.d/security-network.conf"
          for name in ("health-backend", "celery-worker", "celery-beat")),
        Path("/etc/ufw/user.rules"), Path("/etc/ufw/user6.rules"),
        Path("/root/.pm2/dump.pm2"),
    ])
    for family in ("iptables", "ip6tables"):
        atomic_write(receipt / f"{family}-before.txt", run(f"/usr/sbin/{family}-save"), 0o600)
    _apply_prepared(sha, receipt, legacy_pid, keys)


def _apply_prepared(sha, receipt, legacy_pid, keys):
    """Only normal apply or the independently proven recovery may enter here."""
    try:
        user = pwd.getpwnam("health-web")
        if user.pw_uid == 0 or user.pw_shell not in ("/usr/sbin/nologin", "/sbin/nologin"):
            raise RuntimeError("unexpected health-web account")
    except KeyError:
        run("useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin", "health-web")
    user = pwd.getpwnam("health-web")
    cache = ROOT / "frontend/.next/cache"
    cache.mkdir(exist_ok=True)
    paths = [cache, *cache.rglob("*")]
    if any(p.is_symlink() for p in paths):
        raise RuntimeError("frontend cache contains links")
    for path in paths:
        os.chown(path, user.pw_uid, user.pw_gid, follow_symlinks=False)
    network_guard()
    for name in ("health-network-guard", "health-frontend"):
        atomic_write(UNITS / f"{name}.service", (ROOT / "infra/systemd" / f"{name}.service").read_text())
    for name in ("health-backend", "celery-worker", "celery-beat"):
        directory = UNITS / f"{name}.service.d"
        directory.mkdir(exist_ok=True)
        trusted(directory, directory=True)
        atomic_write(directory / "security-network.conf", "[Unit]\nRequires=health-network-guard.service\nAfter=health-network-guard.service\n")
    template = (ROOT / "infra/systemd/health-frontend.service").read_text()
    preflight = UNITS / "health-frontend-security-preflight.service"
    if preflight.exists():
        raise RuntimeError("preflight service already exists")
    atomic_write(preflight, template.replace("-p 30001", "-p 30002"))
    run("systemd-analyze", "verify", str(UNITS / "health-frontend.service"), str(UNITS / "health-network-guard.service"), str(preflight))
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "health-network-guard")
    run("systemctl", "start", preflight.name)
    try:
        ready(30002)
    finally:
        run("systemctl", "stop", preflight.name)
    if pm2_frontend() != legacy_pid:
        raise RuntimeError("legacy frontend changed during preflight")
    atomic_write(receipt / "phase.json", '{"phase":"frontend_cutover"}', 0o600)
    run("pm2", "stop", "health-frontend")
    try:
        run("systemctl", "enable", "--now", "health-frontend")
        ready(30001)
        first = run("systemctl", "show", "health-frontend", "-p", "MainPID", "-p", "NRestarts")
        time.sleep(6)
        if first != run("systemctl", "show", "health-frontend", "-p", "MainPID", "-p", "NRestarts"):
            raise RuntimeError("frontend is not stable")
        pid = run("systemctl", "show", "health-frontend", "-p", "MainPID", "--value").strip()
        uid_line = next(x for x in Path(f"/proc/{pid}/status").read_text().splitlines() if x.startswith("Uid:"))
        if set(uid_line.split()[1:]) != {str(user.pw_uid)}:
            raise RuntimeError("frontend did not drop privilege")
    except Exception:
        run("systemctl", "disable", "--now", "health-frontend")
        run("pm2", "restart", "health-frontend")
        ready(30001)
        atomic_write(receipt / "failed.json", '{"status":"FRONTEND_ROLLED_BACK"}', 0o600)
        raise
    run("pm2", "delete", "health-frontend")
    run("pm2", "save", "--force")
    for key in keys:
        os.chmod(key, 0o600, follow_symlinks=False)
    if "Status: active" not in run("ufw", "status"):
        raise RuntimeError("UFW is not active")
    for port in ("9090", "9100"):
        run("ufw", "insert", "1", "deny", "in", "proto", "tcp", "from", "any", "to", "any", "port", port)
    network_guard()  # UFW must not move permissive rules above owner guards.
    for name in ("lighthouse-validator", "lighthouse-beacon", "eth1", "health-backend"):
        run("systemctl", "is-active", "--quiet", name)
    ready(30001)
    atomic_write(receipt / "completed.json", json.dumps({"sha": sha, "status": "APPLIED"}), 0o600)
    print("PUBLIC_HOST_HARDENING_APPLIED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or not args.network:
        raise SystemExit("use canonical deploy.sh --security-hardening for mutations")
    os.umask(0o077)
    network_guard()
