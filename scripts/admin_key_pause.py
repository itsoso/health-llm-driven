"""Canonical root operator: temporarily deny ONE explicitly approved SSH key.

Never edits authorized_keys, disables an authorization source, restarts sshd,
runs a release, or treats an interrupted operation as restored.
"""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import sys
import time

ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}
ROOT = Path("/var/lib/reva-admin-key-pauses")
CONFIG = Path("/etc/ssh/sshd_config")
INCLUDES = Path("/etc/ssh/sshd_config.d")
CONF = INCLUDES / "00-reva-admin-key-pause.conf"


class PauseError(Exception):
    """Only fixed diagnostics leave this operator."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def write_json(path, value):
    write(path, json.dumps(value, sort_keys=True).encode())


def publish(path, data, mode=0o644):
    """Complete, synced bytes before a no-clobber atomic publication.

    Temporary names never match sshd's *.conf include. A failed publication
    remains for audit; it cannot affect sshd's configuration.
    """
    temporary = path.parent / ("." + path.name + ".reva-pause.pending")
    write(temporary, data, mode)
    os.link(temporary, path, follow_symlinks=False)
    temporary.unlink()
    sync(path.parent)


def pause(adapter, *, consent=False, evidence_sha256=None):
    if consent is not True:
        raise PauseError("explicit temporary single-key consent required")
    if os.path.lexists(adapter.record):
        raise PauseError("pause already attempted; inspect and restore instead")
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED", "evidence_sha256": fingerprint}
    if fingerprint != evidence_sha256:
        raise PauseError("pause evidence changed")
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    write_json(adapter.record / "intent.json", {"consent": "TEMPORARY_SINGLE_KEY_DENIAL", "evidence": evidence})
    if adapter.inspect() != evidence:
        raise PauseError("pause evidence changed after intent; restore required")
    adapter.install(evidence)
    adapter.verify_paused(evidence)
    adapter.terminate(evidence)
    write_json(adapter.record / "paused.json", {"state": "PAUSED_RESTORE_REQUIRED", "evidence_sha256": fingerprint})
    return {"state": "PAUSED_RESTORE_REQUIRED"}


def restore(adapter, *, consent=False):
    if consent is not True:
        raise PauseError("explicit restoration consent required")
    intent = json.loads((adapter.record / "intent.json").read_bytes())
    if set(intent) != {"consent", "evidence"} or intent["consent"] != "TEMPORARY_SINGLE_KEY_DENIAL":
        raise PauseError("invalid original pause intent")
    evidence = intent["evidence"]
    marker = {"state": "RESTORE_PENDING", "evidence_sha256": digest(evidence)}
    pending = adapter.record / "restore-intent.json"
    if not pending.exists():
        write_json(pending, marker)
    elif json.loads(pending.read_bytes()) != marker:
        raise PauseError("restore intent differs")
    adapter.restore(evidence)
    result = {"state": "RESTORED", "evidence_sha256": digest(evidence)}
    completed = adapter.record / "restored.json"
    if not completed.exists():
        write_json(completed, result)
    elif json.loads(completed.read_bytes()) != result:
        raise PauseError("restoration evidence differs")
    return result


def key_digest(public):
    if not isinstance(public, bytes) or re.fullmatch(rb"ssh-ed25519 [A-Za-z0-9+/]+={0,2}", public) is None:
        raise PauseError("exact ed25519 public key required")
    try:
        wire = base64.b64decode(public.split()[1], validate=True)
    except ValueError:
        raise PauseError("invalid public key") from None
    prefix = b"\0\0\0\x0bssh-ed25519\0\0\0\x20"
    if len(wire) != len(prefix) + 32 or not wire.startswith(prefix) or base64.b64encode(wire) != public.split()[1]:
        raise PauseError("invalid ed25519 wire format")
    return hashlib.sha256(wire).hexdigest()


def fingerprint(hex_digest):
    return "SHA256:" + base64.b64encode(bytes.fromhex(hex_digest)).decode().rstrip("=")


def select_key(raw, target):
    found = []
    for line in raw.splitlines():
        parts = line.split()
        for i, part in enumerate(parts[:-1]):
            if part == b"ssh-ed25519":
                public = b" ".join(parts[i:i + 2])
                if key_digest(public) == target:
                    if i != 0:
                        raise PauseError("target key must be a plain authorized key")
                    found.append(public)
    if len(found) != 1:
        raise PauseError("one exact target authorization required")
    return found[0]


def assert_effective_change(before, after, revoked):
    old, new = before.splitlines(), after.splitlines()
    if [s for s in old if s.startswith("revokedkeys ")] != ["revokedkeys none"]:
        raise PauseError("existing revocation policy must not be overwritten")
    expected = ["revokedkeys " + revoked if s == "revokedkeys none" else s for s in old]
    if new != expected:
        raise PauseError("SSH configuration changed outside target revocation")


def run(argv, *, accepted=(0,), timeout=20, **kwargs):
    result = subprocess.run(argv, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, **kwargs)
    if result.returncode not in accepted or len(result.stdout) + len(result.stderr) > 1_000_000:
        raise PauseError("bounded system command failed")
    return result


def context(sha, *, recovery=False):
    if (re.fullmatch(r"[a-f0-9]{40}", sha or "") is None or os.geteuid() != 0
            or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or sys.executable != "/usr/bin/python3.12" or "SSH_ORIGINAL_COMMAND" in os.environ):
        raise PauseError("isolated canonical root operator required")
    source = Path("/var/lib/reva-release/bootstrap") / sha / "source"
    entry = source / "scripts/admin_key_pause.py"
    if Path(__file__).absolute() != entry:
        raise PauseError("fixed canonical entry required")
    for path in [*reversed(entry.parents), entry, entry.with_name("review_maintenance_retirement.py")]:
        info = path.lstat()
        file = path in (entry, entry.with_name("review_maintenance_retirement.py"))
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                or (file and info.st_nlink != 1)):
            raise PauseError("unsafe canonical metadata")
    spec = importlib.util.spec_from_file_location("admin_pause_context", entry.with_name("review_maintenance_retirement.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Restore must remain possible after main moves or CI changes, but still
    # requires the original canonical bytes and isolation. Pause requires CI.
    _, bootstrap, _ = module.context(sha, verify_ci=not recovery)
    return bootstrap


def session(pid):
    p = Path("/proc") / str(pid)
    info = (p / "stat").read_bytes().rsplit(b")", 1)[-1].split()
    return {"pid": pid, "ppid": int(info[1]), "start": int(info[19]), "uid": p.stat().st_uid,
            "exe": os.readlink(p / "exe"), "argv": (p / "cmdline").read_bytes().rstrip(b"\0").decode()}


def ancestry():
    values, pid = [], os.getpid()
    while pid > 1:
        if pid in values or len(values) > 64:
            raise PauseError("operator ancestry uncertain")
        values.append(pid)
        pid = int((Path("/proc") / str(pid) / "stat").read_bytes().rsplit(b")", 1)[-1].split()[1])
    return values


def process_state(pid):
    return (Path("/proc") / str(pid) / "stat").read_bytes().rsplit(b")", 1)[-1].split()[0]


def wait_stopped(identity):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if session(identity["pid"]) != identity:
            raise PauseError("session changed while freezing")
        if process_state(identity["pid"]) == b"T":
            return
        time.sleep(0.01)
    raise PauseError("session freeze unproven")


def exited(fd, timeout=0):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    return bool(poller.poll(timeout))


def resume_identity(identity, target):
    """Undo only our recorded freeze, never signal a reused PID or other key."""
    try:
        fd = os.pidfd_open(identity["pid"])
    except ProcessLookupError:
        return
    try:
        if exited(fd):
            return
        current = session(identity["pid"])
        if current["start"] != identity["start"]:
            return  # Original process is gone; the replacement must not be touched.
        if current != identity or authenticated_key(current) != fingerprint(target):
            raise PauseError("frozen session identity drifted")
        if process_state(identity["pid"]) == b"T":
            signal.pidfd_send_signal(fd, signal.SIGCONT)
            deadline = time.monotonic() + 2
            while not exited(fd) and process_state(identity["pid"]) == b"T":
                if time.monotonic() >= deadline:
                    raise PauseError("session resume unproven")
                time.sleep(0.01)
    finally:
        os.close(fd)


def authenticated_key(identity):
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "")
    raw = run(["/usr/bin/journalctl", "--no-pager", "-o", "json", f"_PID={identity['pid']}", f"_BOOT_ID={boot}"]).stdout
    found = set()
    for line in raw.splitlines():
        item = json.loads(line)
        if int(item["__MONOTONIC_TIMESTAMP"]) < identity["start"] * 1_000_000 // os.sysconf("SC_CLK_TCK"):
            continue
        message = item.get("MESSAGE", "")
        matched = re.fullmatch(r"Accepted publickey for root .* (SHA256:[A-Za-z0-9+/]+)", message)
        if matched:
            found.add(matched[1])
        elif message.startswith("Accepted "):
            raise PauseError("unsupported session authentication")
    if len(found) != 1 or session(identity["pid"]) != identity:
        raise PauseError("session authentication identity uncertain")
    return found.pop()


def offer_result(stderr, target):
    text = stderr.decode("utf-8", "strict")
    offered = [i for i, line in enumerate(text.splitlines()) if line.startswith("debug1: Offering public key:") and target in line]
    if len(offered) != 1 or "No more authentication methods to try." not in text or "Permission denied (" not in text:
        raise PauseError("public-key offer outcome unknown")
    after = text.splitlines()[offered[0] + 1:]
    if any(line.startswith("debug1: Server accepts key:") and target in line for line in after):
        return True
    if any(line.startswith("debug1: Authentications that can continue: publickey") for line in after):
        return False
    raise PauseError("public-key denial unproven")


def public_offer(public, known_hosts, *, port=22):
    """Fresh TCP unsigned offer, not authentication or command execution proof."""
    target = fingerprint(key_digest(public))
    descriptors = []
    try:
        for name, raw in (("public-only-offer", public + b"\n"), ("pinned-host", known_hosts)):
            fd = os.memfd_create(name, os.MFD_ALLOW_SEALING)
            descriptors.append(fd)
            if os.write(fd, raw) != len(raw):
                raise PauseError("short public probe input write")
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        result = run(["/usr/bin/ssh", "-vv", "-F", "/dev/null", "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none", "-o", "CertificateFile=none",
            "-o", "PreferredAuthentications=publickey", "-o", "PasswordAuthentication=no",
            "-o", "StrictHostKeyChecking=yes", "-o", "GlobalKnownHostsFile=/dev/null",
            "-o", f"UserKnownHostsFile=/proc/self/fd/{descriptors[1]}", "-o", "ControlPath=none",
            "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1",
            "-p", str(port), "-i", f"/proc/self/fd/{descriptors[0]}", "root@127.0.0.1", "true"],
            accepted=(255,), pass_fds=tuple(descriptors))
        if result.stdout:
            raise PauseError("unexpected public offer output")
        return offer_result(result.stderr, target)
    finally:
        for fd in descriptors:
            os.close(fd)


class Operator:
    def __init__(self, bootstrap, sha, target):
        self.b, self.sha, self.target = bootstrap, sha, target
        self.record = ROOT / (sha + "-" + target)
        self.conf = CONF
        self.pub = INCLUDES / ("reva-admin-" + sha + "-" + target + ".pub")

    def file(self, path):
        info = path.lstat()
        interrupted_link = False
        if info.st_nlink == 2 and path in (self.conf, self.pub):
            self.b.secure(path.parent)
            temporary = path.parent / ("." + path.name + ".reva-pause.pending")
            peer = temporary.lstat()
            interrupted_link = (info.st_uid == 0 and not info.st_mode & 0o022 and stat.S_ISREG(peer.st_mode)
                                and (peer.st_dev, peer.st_ino) == (info.st_dev, info.st_ino))
        else:
            self.b.secure(path)
        if not stat.S_ISREG(info.st_mode) or (info.st_nlink != 1 and not interrupted_link) or info.st_size > 1_000_000:
            raise PauseError("invalid configuration file")
        return {"uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
                "dev": info.st_dev, "ino": info.st_ino, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def configuration(self):
        self.b.secure(INCLUDES)
        result, includes = {}, 0
        for path in [CONFIG, *sorted(INCLUDES.glob("*.conf"))]:
            if path == self.conf:
                continue
            result[str(path)] = self.file(path)
            for line in path.read_text().splitlines():
                tokens = line.split("#", 1)[0].split()
                if not tokens:
                    continue
                if tokens[0].lower() in {"match", "revokedkeys"}:
                    raise PauseError("ambiguous or existing SSH policy")
                if tokens[0].lower() == "include":
                    if path != CONFIG or tokens != ["Include", "/etc/ssh/sshd_config.d/*.conf"]:
                        raise PauseError("unsupported nested SSH configuration")
                    includes += 1
        if includes != 1:
            raise PauseError("one canonical SSH include required")
        return result

    def daemon(self):
        pid = int(run(["/usr/bin/systemctl", "show", "ssh.service", "--property=MainPID", "--value"]).stdout)
        identity = session(pid)
        if (identity["uid"] != 0 or identity["ppid"] != 1 or identity["exe"] != "/usr/sbin/sshd"
                or re.fullmatch(r"sshd: /usr/sbin/sshd -D \[listener\] \d+ of \d+-\d+ startups", identity["argv"]) is None):
            raise PauseError("actual sshd instance/configuration not bound")
        self.b.secure(Path(identity["exe"]))
        version = run(["/usr/sbin/sshd", "-V"], accepted=(0, 1)).stderr.decode()
        if "OpenSSH_" not in version:
            raise PauseError("sshd version unavailable")
        return {**{k: v for k, v in identity.items() if k != "argv"},
                "binary": self.file(Path(identity["exe"])),
                "version": version}

    def effective(self):
        run(["/usr/sbin/sshd", "-t"])
        return run(["/usr/sbin/sshd", "-T"]).stdout.decode()

    def offer(self, public):
        return public_offer(public, self.known_hosts)

    def target_sessions(self):
        mine = ancestry()
        found = []
        for p in Path("/proc").iterdir():
            if not p.name.isdigit() or int(p.name) in mine:
                continue
            argv = (p / "cmdline").read_bytes()
            if not argv.startswith((b"sshd:", b"sshd-session:")):
                continue
            identity = session(int(p.name))
            if (identity["argv"] != "sshd: root" or identity["exe"] != "/usr/sbin/sshd" or identity["uid"] != 0
                    or authenticated_key(identity) != fingerprint(self.target)):
                raise PauseError("unrelated or pending SSH session present")
            self.no_children(identity["pid"])
            found.append(identity)
        return sorted(found, key=lambda row: row["pid"])

    def no_children(self, pid):
        for p in Path("/proc").iterdir():
            if p.name.isdigit() and int((p / "stat").read_bytes().rsplit(b")", 1)[-1].split()[1]) == pid:
                raise PauseError("target SSH connection has child processes")

    def no_pending_pauses(self):
        if not ROOT.exists():
            return
        self.b.secure(ROOT)
        records = list(ROOT.iterdir())
        if len(records) > 1000:
            raise PauseError("pause audit inventory exceeds bound")
        for record in records:
            if record == self.record:
                continue  # Same transaction reinspection after durable intent.
            self.b.secure(record)
            if not record.is_dir() or re.fullmatch(r"[a-f0-9]{40}-[a-f0-9]{64}", record.name) is None:
                raise PauseError("unknown pause audit")
            required = [record / name for name in ("intent.json", "restore-intent.json", "restored.json")]
            if not all(path.exists() for path in required):
                raise PauseError("another unfinished pause requires restoration")
            for path in record.iterdir():
                self.b.secure(path, private=True)
                if path.stat().st_size > 1_000_000:
                    raise PauseError("pause audit exceeds bound")
            intent, pending, restored = [json.loads(path.read_bytes()) for path in required]
            if (set(intent) != {"consent", "evidence"} or intent["consent"] != "TEMPORARY_SINGLE_KEY_DENIAL"
                    or record.name != intent["evidence"]["sha"] + "-" + intent["evidence"]["key_digest"]
                    or pending != {"state": "RESTORE_PENDING", "evidence_sha256": digest(intent["evidence"])}
                    or restored != {"state": "RESTORED", "evidence_sha256": digest(intent["evidence"])}):
                raise PauseError("another unfinished or invalid pause audit")

    def inspect(self):
        self.no_pending_pauses()
        if os.path.lexists(self.conf) or os.path.lexists(self.pub):
            raise PauseError("existing temporary pause must be restored")
        config, daemon = self.configuration(), self.daemon()
        self.b.secure(self.b.AUTHORIZED, private=True)
        raw = self.b.AUTHORIZED.read_bytes()
        public = select_key(raw, self.target)
        mine = next(session(pid) for pid in ancestry() if (Path("/proc") / str(pid) / "comm").read_text().strip() == "sshd")
        operator_fingerprint = authenticated_key(mine)
        if operator_fingerprint == fingerprint(self.target):
            raise PauseError("cannot pause operator identity")
        operator = None
        for line in raw.splitlines():
            tokens = line.split()
            if len(tokens) >= 2 and tokens[0] == b"ssh-ed25519":
                key = b" ".join(tokens[:2])
                if fingerprint(key_digest(key)) == operator_fingerprint:
                    operator = key
        if operator is None:
            raise PauseError("independent plain operator key unavailable")
        history = self.b._retired_history()
        for directory in [self.b.CONFIG, *(self.b._retired_config(sha, item) for sha, item in history.items())]:
            for name in ("cloud.pub", "loopback.pub"):
                self.b.secure(directory / name, private=True)
                if key_digest((directory / name).read_bytes().strip()) == self.target:
                    raise PauseError("cannot pause a managed release identity")
        before = self.effective()
        assert_effective_change(before, before, "none")
        self.b.secure(self.b.CONFIG / "known_hosts", private=True)
        self.known_hosts = (self.b.CONFIG / "known_hosts").read_bytes()
        sessions = self.target_sessions()
        if not sessions or not self.offer(public) or not self.offer(operator):
            raise PauseError("live allowed-key offer baseline missing")
        if self.configuration() != config or self.daemon() != daemon:
            raise PauseError("SSH baseline changed")
        return {"sha": self.sha, "key_digest": self.target, "public": public.decode(), "operator": operator.decode(),
                "configuration": config, "daemon": daemon, "effective": before, "sessions": sessions,
                "authorized": self.file(self.b.AUTHORIZED), "known_hosts": self.known_hosts.decode()}

    def bound(self, evidence):
        if (set(evidence) != {"sha", "key_digest", "public", "operator", "configuration", "daemon", "effective", "sessions", "authorized", "known_hosts"}
                or evidence.get("sha") != self.sha or evidence.get("key_digest") != self.target
                or key_digest(evidence["public"].encode()) != self.target
                or key_digest(evidence["operator"].encode()) == self.target
                or self.configuration() != evidence["configuration"] or self.daemon() != evidence["daemon"]):
            raise PauseError("pause evidence or SSH configuration drifted")
        self.known_hosts = evidence["known_hosts"].encode()

    def install(self, evidence):
        self.no_pending_pauses()
        self.bound(evidence)
        if self.file(self.b.AUTHORIZED) != evidence["authorized"]:
            raise PauseError("authorization changed before pause")
        publish(self.pub, evidence["public"].encode() + b"\n")
        self.check_pub(evidence)
        publish(self.conf, f"RevokedKeys {self.pub}\n".encode())
        write_json(self.record / "installed.json", {"pub": self.file(self.pub), "conf": self.file(self.conf)})
        assert_effective_change(evidence["effective"], self.effective(), str(self.pub))
        run(["/usr/bin/systemctl", "reload", "ssh.service"])

    def check_pub(self, evidence):
        info = self.file(self.pub)
        if info["mode"] != 0o644 or self.pub.read_bytes() != evidence["public"].encode() + b"\n":
            raise PauseError("revocation file missing, unreadable or changed")

    def verify_paused(self, evidence):
        self.bound(evidence)
        self.check_pub(evidence)
        if json.loads((self.record / "installed.json").read_bytes()) != {"pub": self.file(self.pub), "conf": self.file(self.conf)}:
            raise PauseError("installed pause identity drifted")
        assert_effective_change(evidence["effective"], self.effective(), str(self.pub))
        if self.offer(evidence["public"].encode()) or not self.offer(evidence["operator"].encode()):
            raise PauseError("new-connection single-key offer denial unproven")

    def terminate(self, evidence):
        self.verify_paused(evidence)
        for identity in self.target_sessions():
            fd = os.pidfd_open(identity["pid"])
            freeze_attempted, terminated = False, False
            try:
                if session(identity["pid"]) != identity or authenticated_key(identity) != fingerprint(self.target):
                    raise PauseError("SSH identity changed before termination")
                write_json(self.record / f"freeze-{identity['pid']}-{identity['start']}.json",
                           {"identity": identity, "key_digest": self.target})
                freeze_attempted = True
                signal.pidfd_send_signal(fd, signal.SIGSTOP)
                wait_stopped(identity)
                # STOP is kernel-confirmed: this exact process cannot fork
                # between the final child inventory and SIGKILL.
                self.no_children(identity["pid"])
                signal.pidfd_send_signal(fd, signal.SIGKILL)
                if not exited(fd, 5000):
                    raise PauseError("target connection termination unproven")
                terminated = True
            finally:
                try:
                    if freeze_attempted and not terminated:
                        resume_identity(identity, self.target)
                finally:
                    os.close(fd)
        if self.target_sessions():
            raise PauseError("new target connection raced with pause")

    def restore(self, evidence):
        if evidence.get("sha") != self.sha or evidence.get("key_digest") != self.target:
            raise PauseError("restore scope mismatch")
        for path in sorted(self.record.glob("freeze-*.json")):
            self.b.secure(path, private=True)
            frozen = json.loads(path.read_bytes())
            identity = frozen["identity"]
            if (set(frozen) != {"identity", "key_digest"} or frozen["key_digest"] != self.target
                    or path.name != f"freeze-{identity['pid']}-{identity['start']}.json"):
                raise PauseError("frozen session audit differs")
            resume_identity(identity, self.target)
        self.bound(evidence)
        if self.pub.exists():
            self.check_pub(evidence)
        if os.path.lexists(self.conf):
            self.check_pub(evidence)
            self.file(self.conf)
            if self.conf.read_bytes() != f"RevokedKeys {self.pub}\n".encode():
                raise PauseError("temporary drop-in drifted; restore pending")
            installed = self.record / "installed.json"
            if installed.exists() and json.loads(installed.read_bytes()) != {"pub": self.file(self.pub), "conf": self.file(self.conf)}:
                raise PauseError("installed pause identity drifted")
            self.conf.unlink()
            sync(self.conf.parent)
        # Keep the public revocation file: an older preauth process may still
        # refer to it. Removing it could deny ALL keys in that older process.
        if self.effective() != evidence["effective"]:
            raise PauseError("original SSH policy not restored")
        run(["/usr/bin/systemctl", "reload", "ssh.service"])
        if not self.offer(evidence["public"].encode()) or not self.offer(evidence["operator"].encode()):
            raise PauseError("restored public-key offer baseline unproven")
        self.bound(evidence)


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("action", choices=("pause", "restore"))
        parser.add_argument("--sha", required=True)
        parser.add_argument("--key-digest", required=True)
        parser.add_argument("--consent-temporary-key-pause", action="store_true")
        parser.add_argument("--evidence-sha256")
        args = parser.parse_args()
        if (not args.consent_temporary_key_pause or re.fullmatch(r"[a-f0-9]{64}", args.key_digest) is None
                or (args.evidence_sha256 is not None and re.fullmatch(r"[a-f0-9]{64}", args.evidence_sha256) is None)
                or (args.action == "restore" and args.evidence_sha256 is not None)):
            raise PauseError("explicit exact single-key scope required")
        os.umask(0o077)
        b = context(args.sha, recovery=args.action == "restore")
        lock = b.STATE / "launcher.lock"
        b.secure(lock, private=True)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            b._assert_original_lock(lock, fd)
            b._recovery_process_proof()
            if not ROOT.exists():
                if args.action == "restore" or args.evidence_sha256 is None:
                    if args.action == "restore":
                        raise PauseError("no original pause audit")
                else:
                    ROOT.mkdir(mode=0o700)
                    sync(ROOT.parent)
            if ROOT.exists():
                b.secure(ROOT)
                if stat.S_IMODE(ROOT.stat().st_mode) != 0o700:
                    raise PauseError("pause audit root must be private")
            adapter = Operator(b, args.sha, args.key_digest)
            if adapter.record.exists():
                b.secure(adapter.record)
                if stat.S_IMODE(adapter.record.stat().st_mode) != 0o700:
                    raise PauseError("pause audit must be private")
                for file in adapter.record.iterdir():
                    b.secure(file, private=True)
            result = (restore(adapter, consent=True) if args.action == "restore" else
                      pause(adapter, consent=True, evidence_sha256=args.evidence_sha256))
            b._assert_original_lock(lock, fd)
            print(json.dumps(result, sort_keys=True))
        finally:
            os.close(fd)
        return 0
    except (Exception, KeyboardInterrupt):
        print("admin key pause: rejected or incomplete; inspect durable audit; restore may be pending", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
