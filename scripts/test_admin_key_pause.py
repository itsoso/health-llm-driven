"""Temporary single-key denial must never weaken other SSH authorization."""
import base64
import importlib.util
import json
import os
from pathlib import Path

import pytest


def load():
    spec = importlib.util.spec_from_file_location("admin_pause_test", Path(__file__).with_name("admin_key_pause.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public(seed=1):
    raw = b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + bytes([seed]) * 32
    return b"ssh-ed25519 " + base64.b64encode(raw)


class Adapter:
    def __init__(self, root):
        self.record = root / "record"
        self.events = []
        self.evidence = {"sha": "a" * 40, "key_digest": "b" * 64, "approved": "single-key"}

    def inspect(self):
        self.events.append("inspect")
        return self.evidence.copy()

    def install(self, evidence):
        assert (self.record / "intent.json").exists()
        self.events.append("install")

    def verify_paused(self, evidence):
        self.events.append("verify_paused")

    def terminate(self, evidence):
        assert self.events[-1] == "verify_paused"
        self.events.append("terminate")

    def restore(self, evidence):
        self.events.append("restore")


def test_pause_requires_specific_consent_and_defaults_to_read_only(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.PauseError):
        m.pause(a)
    assert a.events == []
    result = m.pause(a, consent=True)
    assert result["state"] == "INSPECTED"
    assert a.events == ["inspect"] and not a.record.exists()


def test_pause_uses_durable_intent_and_denies_before_termination(tmp_path):
    m, a = load(), Adapter(tmp_path)
    fingerprint = m.pause(a, consent=True)["evidence_sha256"]
    result = m.pause(a, consent=True, evidence_sha256=fingerprint)
    assert result["state"] == "PAUSED_RESTORE_REQUIRED"
    assert a.events[-5:] == ["inspect", "inspect", "install", "verify_paused", "terminate"]
    assert json.loads((a.record / "intent.json").read_text())["consent"] == "TEMPORARY_SINGLE_KEY_DENIAL"
    with pytest.raises(m.PauseError):
        m.pause(a, consent=True, evidence_sha256=fingerprint)


@pytest.mark.parametrize("point", ["install", "verify_paused", "terminate"])
def test_partial_pause_keeps_auditable_restore_pending(tmp_path, monkeypatch, point):
    m, a = load(), Adapter(tmp_path)
    fingerprint = m.pause(a, consent=True)["evidence_sha256"]
    def fail(*args):
        raise OSError("injected")
    monkeypatch.setattr(a, point, fail)
    with pytest.raises(OSError):
        m.pause(a, consent=True, evidence_sha256=fingerprint)
    assert (a.record / "intent.json").exists()
    assert not (a.record / "paused.json").exists()
    assert not (a.record / "restored.json").exists()


def test_restore_works_for_partial_pause_without_replaying_it(tmp_path, monkeypatch):
    m, a = load(), Adapter(tmp_path)
    fingerprint = m.pause(a, consent=True)["evidence_sha256"]
    monkeypatch.setattr(a, "install", lambda *_: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        m.pause(a, consent=True, evidence_sha256=fingerprint)
    assert m.restore(a, consent=True)["state"] == "RESTORED"
    assert a.events[-1] == "restore"
    assert (a.record / "restored.json").exists()


def test_restore_failure_never_claims_restored(tmp_path, monkeypatch):
    m, a = load(), Adapter(tmp_path)
    fingerprint = m.pause(a, consent=True)["evidence_sha256"]
    m.pause(a, consent=True, evidence_sha256=fingerprint)
    monkeypatch.setattr(a, "restore", lambda *_: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        m.restore(a, consent=True)
    assert (a.record / "restore-intent.json").exists()
    assert not (a.record / "restored.json").exists()


def test_public_key_selection_never_accepts_duplicate_or_options():
    m = load()
    key = public()
    target = m.key_digest(key)
    assert m.select_key(key + b" comment\n" + public(2) + b"\n", target) == key
    for raw in (key + b"\n" + key + b"\n", b'command="false" ' + key + b"\n", public(2) + b"\n"):
        with pytest.raises(m.PauseError):
            m.select_key(raw, target)


@pytest.mark.parametrize("wire", [b"bad", b"ssh-rsa AAAA", b"ssh-ed25519 AAAA", public() + b" extra", public() + b"\n"])
def test_invalid_public_wire_is_rejected(wire):
    m = load()
    with pytest.raises(m.PauseError):
        m.key_digest(wire)


def test_publication_is_atomic_and_does_not_clobber(tmp_path, monkeypatch):
    m = load()
    path = tmp_path / "pause.conf"
    real_link = m.os.link
    calls = []
    def link(source, dest, **kwargs):
        assert not path.exists()
        assert source.read_bytes() == b"complete\n"
        calls.append("published")
        return real_link(source, dest, **kwargs)
    monkeypatch.setattr(m.os, "link", link)
    m.publish(path, b"complete\n")
    assert path.read_bytes() == b"complete\n" and calls == ["published"]
    monkeypatch.setattr(m.os, "link", real_link)
    with pytest.raises(FileExistsError):
        m.publish(path, b"replacement")
    assert path.read_bytes() == b"complete\n"


@pytest.mark.parametrize("point", ["fsync", "link"])
def test_failed_publication_never_exposes_partial_config(tmp_path, monkeypatch, point):
    m = load()
    path = tmp_path / "pause.conf"
    def fail(*args, **kwargs):
        raise OSError("injected")
    monkeypatch.setattr(m.os, point, fail)
    with pytest.raises(OSError):
        m.publish(path, b"complete\n")
    assert not path.exists()


@pytest.mark.parametrize("accepted", [True, False])
def test_public_offer_requires_exact_protocol_outcome(accepted):
    m = load()
    fp = m.fingerprint(m.key_digest(public()))
    outcome = f"debug1: Server accepts key: /public ED25519 {fp} explicit" if accepted else "debug1: Authentications that can continue: publickey"
    log = f"debug1: Offering public key: /public ED25519 {fp} explicit\n{outcome}\ndebug1: No more authentication methods to try.\nroot@127.0.0.1: Permission denied (publickey).\n"
    assert m.offer_result(log.encode(), fp) is accepted
    for broken in (log.replace(fp, "SHA256:other"), log.replace(outcome, "Connection closed"), log.replace("Permission denied (", "Connection reset (")):
        with pytest.raises(m.PauseError):
            m.offer_result(broken.encode(), fp)


def test_public_offer_survives_ssh_closing_inherited_descriptors(monkeypatch):
    from types import SimpleNamespace
    m = load()
    descriptors = iter([41, 42])
    monkeypatch.setattr(m.os, "memfd_create", lambda *args: next(descriptors), raising=False)
    monkeypatch.setattr(m.os, "MFD_ALLOW_SEALING", 2, raising=False)
    monkeypatch.setattr(m.os, "write", lambda fd, raw: len(raw))
    monkeypatch.setattr(m.os, "close", lambda _: None)
    for name in ("F_ADD_SEALS", "F_SEAL_WRITE", "F_SEAL_GROW", "F_SEAL_SHRINK", "F_SEAL_SEAL"):
        monkeypatch.setattr(m.fcntl, name, 1, raising=False)
    monkeypatch.setattr(m.fcntl, "fcntl", lambda *args: None)
    calls = []
    monkeypatch.setattr(m, "run", lambda argv, **kw: calls.append((argv, kw)) or SimpleNamespace(stdout=b"", stderr=b"synthetic"))
    monkeypatch.setattr(m, "offer_result", lambda *args: True)
    assert m.public_offer(public(), b"pinned") is True
    argv, kwargs = calls[0]
    assert argv[argv.index("-i") + 1] == f"/proc/{os.getpid()}/fd/41"
    assert f"UserKnownHostsFile=/proc/{os.getpid()}/fd/42" in argv
    assert "pass_fds" not in kwargs


@pytest.mark.parametrize("first", ["unknown", "old_policy"])
def test_offer_readiness_retries_only_reads_until_both_keys_proven(monkeypatch, first):
    m = load()
    now, calls = [0.0], []
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    def probe(key, *, timeout):
        calls.append((key, timeout))
        if len(calls) == 1 and first == "unknown":
            raise m.PauseError("public-key offer outcome unknown")
        return key == public(2) or len(calls) == 1
    m.wait_public_offers(probe, (public(), public(2)), (False, True))
    assert len(calls) >= 3 and now[0] > 0
    assert all(0 < limit <= 10 for _, limit in calls)


@pytest.mark.parametrize("failure", ["unknown", "wrong", "timeout"])
def test_offer_readiness_deadline_never_accepts_unknown_or_wrong_policy(monkeypatch, failure):
    m = load()
    now, calls = [0.0], []
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(m.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    def probe(key, *, timeout):
        calls.append(timeout)
        if failure == "unknown":
            raise m.PauseError("unknown")
        if failure == "timeout":
            now[0] += timeout
            raise m.subprocess.TimeoutExpired("synthetic", timeout)
        return False
    with pytest.raises(m.PauseError, match="readiness unproven"):
        m.wait_public_offers(probe, (public(), public(2)), (True, True), timeout=1)
    assert now[0] <= 1.01 and 1 <= len(calls) <= 22


def test_offer_readiness_does_not_swallow_unrelated_errors(monkeypatch):
    m = load()
    def probe(*args, **kwargs):
        raise OSError("unexpected filesystem failure")
    with pytest.raises(OSError):
        m.wait_public_offers(probe, (public(), public(2)), (True, True))


@pytest.mark.parametrize("action,previous,valid", [
    ("restore", "b" * 40, True), ("pause", "b" * 40, False),
    ("restore", "../other", False), ("restore", "a" * 40, False),
])
def test_old_audit_can_only_be_restored_from_canonical_scope(action, previous, valid):
    from types import SimpleNamespace
    m, seen = load(), []
    b = SimpleNamespace(canonical_source=lambda sha: seen.append(sha))
    if valid:
        assert m.audit_sha(action, "a" * 40, previous, b) == previous
        assert seen == [previous]
    else:
        with pytest.raises(m.PauseError):
            m.audit_sha(action, "a" * 40, previous, b)
        assert not seen


def test_old_audit_canonical_failure_propagates():
    from types import SimpleNamespace
    m = load()
    def reject(sha):
        raise RuntimeError("canonical source drift")
    with pytest.raises(RuntimeError):
        m.audit_sha("restore", "a" * 40, "b" * 40, SimpleNamespace(canonical_source=reject))


def test_restore_cli_uses_new_code_but_original_audit(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m, calls = load(), []
    (tmp_path / "launcher.lock").write_bytes(b"")
    b = SimpleNamespace(STATE=tmp_path, secure=lambda *a, **kw: None,
        canonical_source=lambda sha: calls.append(("canonical", sha)),
        _assert_original_lock=lambda *a: None, _recovery_process_proof=lambda: None)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "context", lambda sha, **kw: calls.append(("code", sha, kw)) or b)
    monkeypatch.setattr(m, "Operator", lambda bootstrap, sha, key: calls.append(("audit", sha, key)) or SimpleNamespace(record=tmp_path / "missing"))
    monkeypatch.setattr(m, "restore", lambda adapter, **kw: {"state": "RESTORED"})
    monkeypatch.setattr(m.sys, "argv", ["operator", "restore", "--sha", "a" * 40,
        "--pause-sha", "b" * 40, "--key-digest", "c" * 64, "--consent-temporary-key-pause"])
    assert m.main() == 0
    assert calls == [("code", "a" * 40, {"recovery": True}), ("canonical", "b" * 40), ("audit", "b" * 40, "c" * 64)]


def test_operator_restore_waits_after_reload_without_replaying_reload(tmp_path, monkeypatch):
    m, a, e, calls = operator(tmp_path, monkeypatch)
    real_offer, attempts = a.offer, []
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    def transient(key, *, timeout=20):
        attempts.append(key)
        if len(attempts) == 1:
            raise m.PauseError("reload still starting")
        return real_offer(key)
    monkeypatch.setattr(a, "offer", transient)
    a.restore(e)
    assert len(attempts) == 3
    assert calls.count(["/usr/bin/systemctl", "reload", "ssh.service"]) == 1


def test_effective_configuration_only_allows_target_revocation_change():
    m = load()
    before = "port 22\nauthorizedkeyscommand /usr/bin/vendor --uid %U\nrevokedkeys none\n"
    after = before.replace("revokedkeys none", "revokedkeys /etc/ssh/target.pub")
    m.assert_effective_change(before, after, "/etc/ssh/target.pub")
    for changed in (after.replace("port 22", "port 23"), after.replace("/usr/bin/vendor", "none"), after + "revokedkeys none\n"):
        with pytest.raises(m.PauseError):
            m.assert_effective_change(before, changed, "/etc/ssh/target.pub")


def test_restore_must_not_rewrite_authorized_keys():
    m = load()
    import inspect
    body = inspect.getsource(m.Operator.restore)
    assert "_replace_authorized" not in body
    assert "self.conf.unlink" in body
    assert "self.pub.unlink" not in body


def operator(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load()
    monkeypatch.setattr(m, "boot_id", lambda: "test-boot")
    config = tmp_path / "sshd_config"
    config.write_text(f"Include {tmp_path}/*.conf\n")
    # Isolate filesystem/sshd adapters; exercise real transition methods.
    b = SimpleNamespace(secure=lambda *args, **kwargs: None, AUTHORIZED=tmp_path / "authorized_keys")
    b.AUTHORIZED.write_bytes(public() + b"\n" + public(2) + b"\n")
    a = m.Operator(b, "a" * 40, m.key_digest(public()))
    a.record = tmp_path / "record"
    a.record.mkdir()
    a.pub, a.conf = tmp_path / "target.pub", tmp_path / "pause.conf"
    monkeypatch.setattr(a, "configuration", lambda: {"fixed": "config"})
    monkeypatch.setattr(a, "daemon", lambda: {"pid": 1})
    before = "port 22\nrevokedkeys none\n"
    monkeypatch.setattr(a, "effective", lambda: before.replace("none", str(a.pub)) if a.conf.exists() else before)
    calls = []
    monkeypatch.setattr(m, "run", lambda args, **kwargs: calls.append(args))
    def offer(key, **kwargs):
        calls.append(["offer", key])
        return not (a.conf.exists() and key == public())
    monkeypatch.setattr(a, "offer", offer)
    e = {"sha": a.sha, "key_digest": a.target, "public": public().decode(), "operator": public(2).decode(),
         "configuration": a.configuration(), "daemon": a.daemon(), "effective": before, "sessions": [],
         "authorized": a.file(b.AUTHORIZED), "known_hosts": "pinned"}
    return m, a, e, calls


def test_operator_real_install_and_restore_preserves_authorization_drift(tmp_path, monkeypatch):
    m, a, e, calls = operator(tmp_path, monkeypatch)
    a.install(e)
    a.verify_paused(e)
    # Closure removes managed keys; restoring the admin must never undo that.
    a.b.AUTHORIZED.write_bytes(public(2) + b"\n")
    a.restore(e)
    assert a.pub.exists() and not a.conf.exists()
    assert a.b.AUTHORIZED.read_bytes() == public(2) + b"\n"
    assert calls.count(["/usr/bin/systemctl", "reload", "ssh.service"]) == 2


@pytest.mark.parametrize("point", ["pub", "conf", "marker", "reload", "probe"])
def test_operator_partial_install_can_restore_without_replaying_pause(tmp_path, monkeypatch, point):
    m, a, e, calls = operator(tmp_path, monkeypatch)
    real_publish, real_write, real_run, real_offer = m.publish, m.write_json, m.run, a.offer
    def fail(*args, **kwargs):
        raise OSError("injected")
    def publish(path, *args):
        if path == (a.pub if point == "pub" else a.conf):
            fail()
        return real_publish(path, *args)
    if point in {"pub", "conf"}:
        monkeypatch.setattr(m, "publish", publish)
    elif point == "marker":
        monkeypatch.setattr(m, "write_json", fail)
    elif point == "reload":
        monkeypatch.setattr(m, "run", fail)
    elif point == "probe":
        monkeypatch.setattr(a, "offer", fail)
    with pytest.raises(OSError):
        a.install(e)
        a.verify_paused(e)
    monkeypatch.setattr(m, "publish", real_publish)
    monkeypatch.setattr(m, "write_json", real_write)
    monkeypatch.setattr(m, "run", real_run)
    monkeypatch.setattr(a, "offer", real_offer)
    a.restore(e)
    assert not a.conf.exists()


@pytest.mark.parametrize("point", ["configuration", "daemon", "public", "operator", "key_digest", "extra"])
def test_bound_evidence_rejects_mixed_identity_and_drift(tmp_path, monkeypatch, point):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    e[point] = public().decode() if point == "operator" else "drift"
    with pytest.raises((m.PauseError, ValueError)):
        a.bound(e)


@pytest.mark.parametrize("point", ["missing_pub", "unreadable_pub", "changed_conf", "replaced_conf"])
def test_paused_policy_drift_blocks(tmp_path, monkeypatch, point):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    a.install(e)
    if point == "missing_pub":
        a.pub.unlink()
    elif point == "unreadable_pub":
        a.pub.chmod(0o600)
    elif point == "changed_conf":
        a.conf.write_text("RevokedKeys none\n")
    elif point == "replaced_conf":
        raw = a.conf.read_bytes()
        replacement = tmp_path / "replacement"
        replacement.write_bytes(raw)
        replacement.replace(a.conf)
    with pytest.raises((m.PauseError, OSError)):
        a.verify_paused(e)


def test_restore_reload_unknown_remains_retryable_without_false_completion(tmp_path, monkeypatch):
    m, a, e, calls = operator(tmp_path, monkeypatch)
    m.write_json(a.record / "intent.json", {"consent": "TEMPORARY_SINGLE_KEY_DENIAL", "evidence": e})
    a.install(e)
    original = m.run
    monkeypatch.setattr(m, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unknown reload")))
    with pytest.raises(OSError):
        m.restore(a, consent=True)
    assert not a.conf.exists() and not (a.record / "restored.json").exists()
    monkeypatch.setattr(m, "run", original)
    assert m.restore(a, consent=True)["state"] == "RESTORED"


@pytest.mark.parametrize("protected", ["operator", "managed"])
def test_inspection_rejects_operator_and_managed_key(tmp_path, monkeypatch, protected):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    proc = tmp_path / "proc" / "123"
    proc.mkdir(parents=True)
    (proc / "comm").write_text("sshd\n")
    actual_path = Path
    monkeypatch.setattr(m, "Path", lambda path: tmp_path / "proc" if path == "/proc" else actual_path(path))
    monkeypatch.setattr(m, "ancestry", lambda: [123])
    monkeypatch.setattr(m, "session", lambda pid: {"pid": pid})
    monkeypatch.setattr(m, "authenticated_key", lambda _: m.fingerprint(m.key_digest(public(1 if protected == "operator" else 2))))
    a.b.CONFIG = tmp_path / "managed"
    a.b.CONFIG.mkdir()
    (a.b.CONFIG / "cloud.pub").write_bytes(public())
    a.b._retired_history = lambda: {}
    with pytest.raises(m.PauseError, match="cannot pause"):
        a.inspect()


@pytest.mark.parametrize("failure", ["pid_changed", "auth_changed", "children", "timeout", "reconnected", "pidfd"])
def test_terminate_preserves_exact_identity_and_unknown_blocks(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    m, a, e, _ = operator(tmp_path, monkeypatch)
    identity = {"pid": 123, "start": 456}
    monkeypatch.setattr(m, "process_state", lambda _: b"S")
    monkeypatch.setattr(a, "verify_paused", lambda _: None)
    iterations = iter([[identity], [identity] if failure == "reconnected" else []])
    monkeypatch.setattr(a, "target_sessions", lambda: next(iterations))
    monkeypatch.setattr(m, "session", lambda _: {} if failure == "pid_changed" else identity)
    monkeypatch.setattr(m, "authenticated_key", lambda _: "wrong" if failure == "auth_changed" else m.fingerprint(a.target))
    def children(_):
        if failure == "children":
            raise m.PauseError("children")
    monkeypatch.setattr(a, "no_children", children)
    def open_pid(_):
        if failure == "pidfd":
            raise OSError("pidfd failed")
        return 42
    monkeypatch.setattr(m.os, "pidfd_open", open_pid, raising=False)
    monkeypatch.setattr(m.os, "close", lambda _: None)
    signals = []
    monkeypatch.setattr(m.signal, "pidfd_send_signal", lambda fd, sig: signals.append((fd, sig)), raising=False)
    monkeypatch.setattr(m, "wait_stopped", lambda _: None)
    resumes = []
    monkeypatch.setattr(m, "resume_identity", lambda identity, target: resumes.append(identity))
    monkeypatch.setattr(m.select, "poll", lambda: SimpleNamespace(register=lambda *args: None, poll=lambda _: [] if failure == "timeout" else [(42, 1)]))
    with pytest.raises((m.PauseError, OSError)):
        a.terminate(e)
    assert len(signals) == (2 if failure in {"timeout", "reconnected"} else 1 if failure == "children" else 0)
    assert bool(resumes) == (failure in {"children", "timeout"})


def test_restore_unlink_failure_retains_restriction_and_pending_audit(tmp_path, monkeypatch):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    m.write_json(a.record / "intent.json", {"consent": "TEMPORARY_SINGLE_KEY_DENIAL", "evidence": e})
    a.install(e)
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == a.conf:
            raise OSError("injected unlink failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError):
        m.restore(a, consent=True)
    assert a.conf.exists() and (a.record / "restore-intent.json").exists()
    assert not (a.record / "restored.json").exists()


def test_other_pending_pause_blocks_even_when_drop_in_is_absent(tmp_path, monkeypatch):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "ROOT", tmp_path / "audits")
    m.ROOT.mkdir(mode=0o700)
    old = m.ROOT / (e["sha"] + "-" + e["key_digest"])
    old.mkdir(mode=0o700)
    m.write_json(old / "intent.json", {"consent": "TEMPORARY_SINGLE_KEY_DENIAL", "evidence": e})
    m.write_json(old / "restore-intent.json", {"state": "RESTORE_PENDING", "evidence_sha256": m.digest(e)})
    with pytest.raises(m.PauseError, match="unfinished"):
        a.no_pending_pauses()
    m.write_json(old / "restored.json", {"state": "RESTORED", "evidence_sha256": m.digest(e)})
    a.no_pending_pauses()


def test_freeze_prevents_fork_between_child_check_and_termination(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m, a, e, _ = operator(tmp_path, monkeypatch)
    identity = {"pid": 123, "start": 456}
    monkeypatch.setattr(m, "process_state", lambda _: b"S")
    monkeypatch.setattr(a, "verify_paused", lambda _: None)
    iterations = iter([[identity], []])
    monkeypatch.setattr(a, "target_sessions", lambda: next(iterations))
    monkeypatch.setattr(m, "session", lambda _: identity)
    monkeypatch.setattr(m, "authenticated_key", lambda _: m.fingerprint(a.target))
    monkeypatch.setattr(m.os, "pidfd_open", lambda _: 42, raising=False)
    monkeypatch.setattr(m.os, "close", lambda _: None)
    state = {"frozen": False, "dead": False}
    def send(fd, sig):
        assert (a.record / "freeze-123-456.json").exists()
        if sig == m.signal.SIGSTOP:
            state["frozen"] = True
        elif sig == m.signal.SIGKILL:
            assert state["frozen"]
            state["dead"] = True
        elif sig == m.signal.SIGCONT:
            state["frozen"] = False
        else:
            pytest.fail("unexpected signal")
    monkeypatch.setattr(m.signal, "pidfd_send_signal", send, raising=False)
    monkeypatch.setattr(m, "wait_stopped", lambda _: state["frozen"] or pytest.fail("not frozen"))
    monkeypatch.setattr(a, "no_children", lambda _: state["frozen"] or pytest.fail("fork window"))
    monkeypatch.setattr(m.select, "poll", lambda: SimpleNamespace(register=lambda *args: None, poll=lambda _: [(42, 1)] if state["dead"] else []))
    a.terminate(e)
    assert state["dead"]


@pytest.mark.parametrize("point", ["stop", "wait_stopped", "no_children", "kill"])
def test_freeze_failure_always_attempts_recorded_resume(tmp_path, monkeypatch, point):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    identity = {"pid": 123, "start": 456}
    monkeypatch.setattr(m, "process_state", lambda _: b"S")
    monkeypatch.setattr(a, "verify_paused", lambda _: None)
    monkeypatch.setattr(a, "target_sessions", lambda: [identity])
    monkeypatch.setattr(m, "session", lambda _: identity)
    monkeypatch.setattr(m, "authenticated_key", lambda _: m.fingerprint(a.target))
    monkeypatch.setattr(m.os, "pidfd_open", lambda _: 42, raising=False)
    monkeypatch.setattr(m.os, "close", lambda _: None)
    def failure():
        raise KeyboardInterrupt()
    def send(fd, sig):
        if (sig == m.signal.SIGSTOP and point == "stop") or (sig == m.signal.SIGKILL and point == "kill"):
            failure()
    monkeypatch.setattr(m.signal, "pidfd_send_signal", send, raising=False)
    monkeypatch.setattr(m, "wait_stopped", lambda _: failure() if point == "wait_stopped" else None)
    monkeypatch.setattr(a, "no_children", lambda _: failure() if point == "no_children" else None)
    resumes = []
    monkeypatch.setattr(m, "resume_identity", lambda identity, target: resumes.append((identity, target)))
    with pytest.raises(KeyboardInterrupt):
        a.terminate(e)
    assert resumes == [(identity, a.target)]
    assert json.loads((a.record / "freeze-123-456.json").read_bytes()) == {"identity": identity, "key_digest": a.target}


@pytest.mark.parametrize("state", ["stopped", "running", "reused", "gone", "wrong_key", "argv_drift", "other_boot"])
def test_resume_identity_never_signals_reused_pid_or_other_key(monkeypatch, state):
    m = load()
    identity = {"pid": 123, "start": 456, "boot_id": "test-boot"}
    monkeypatch.setattr(m, "boot_id", lambda: "other-boot" if state == "other_boot" else "test-boot")
    target = m.key_digest(public())
    opened = []
    monkeypatch.setattr(m.os, "pidfd_open", lambda pid: opened.append(pid) or 42, raising=False)
    monkeypatch.setattr(m.os, "close", lambda _: None)
    monkeypatch.setattr(m, "exited", lambda _: state == "gone")
    monkeypatch.setattr(m, "session", lambda _: {"pid": 123, "start": 999} if state == "reused" else {**identity, "argv": "sshd: root@notty"} if state == "argv_drift" else identity)
    monkeypatch.setattr(m, "authenticated_key", lambda _: "other" if state == "wrong_key" else m.fingerprint(target))
    signals = []
    monkeypatch.setattr(m.signal, "pidfd_send_signal", lambda fd, sig: signals.append((fd, sig)), raising=False)
    monkeypatch.setattr(m, "process_state", lambda _: b"T" if state in {"stopped", "argv_drift"} and not signals else b"S")
    if state == "wrong_key":
        with pytest.raises(m.PauseError):
            m.resume_identity(identity, target)
    else:
        m.resume_identity(identity, target)
    assert signals == ([(42, m.signal.SIGCONT)] if state in {"stopped", "argv_drift"} else [])
    assert opened == ([] if state == "other_boot" else [123])


@pytest.mark.parametrize("state", [b"T", b"t"])
def test_already_stopped_session_is_not_owned_or_resumed(tmp_path, monkeypatch, state):
    m, a, e, _ = operator(tmp_path, monkeypatch)
    identity = {"pid": 123, "start": 456}
    monkeypatch.setattr(a, "verify_paused", lambda _: None)
    monkeypatch.setattr(a, "target_sessions", lambda: [identity])
    monkeypatch.setattr(m, "session", lambda _: identity)
    monkeypatch.setattr(m, "authenticated_key", lambda _: m.fingerprint(a.target))
    monkeypatch.setattr(m, "process_state", lambda _: state)
    monkeypatch.setattr(m.os, "pidfd_open", lambda _: 42, raising=False)
    monkeypatch.setattr(m.os, "close", lambda _: None)
    signals = []
    monkeypatch.setattr(m.signal, "pidfd_send_signal", lambda *args: signals.append(args), raising=False)
    monkeypatch.setattr(m, "resume_identity", lambda *args: signals.append(args))
    with pytest.raises(m.PauseError, match="already stopped"):
        a.terminate(e)
    assert not signals and not list(a.record.glob("freeze-*.json"))


def test_restore_recovers_freeze_before_ssh_policy(tmp_path, monkeypatch):
    m, a, e, calls = operator(tmp_path, monkeypatch)
    identity = {"pid": 123, "start": 456}
    m.write_json(a.record / "freeze-123-456.json", {"identity": identity, "key_digest": a.target})
    monkeypatch.setattr(m, "resume_identity", lambda identity, target: calls.append(["resume", identity]))
    a.restore(e)
    assert calls[0] == ["resume", identity]


@pytest.mark.skipif(os.environ.get("REVA_TEST_NATIVE_SSH") != "1", reason="isolated root Linux OpenSSH CI gate")
def test_native_openssh_dynamic_key_pause_restore_and_missing_file(tmp_path, monkeypatch):
    """Real new TCP offers through static AND dynamic authorization sources."""
    import signal
    import socket
    import subprocess
    m = load()
    original_run, diagnostics = m.run, []
    def capture_test_client(argv, **kwargs):
        result = original_run(argv, **kwargs)
        if argv[0] == "/usr/bin/ssh":
            # This isolated test uses only throwaway public keys, never accounts
            # or credentials from production. Keep the last bounded client log.
            diagnostics[:] = [result.stderr.decode(errors="replace")[-12000:]]
        return result
    monkeypatch.setattr(m, "run", capture_test_client)
    assert os.geteuid() == 0 and hasattr(os, "memfd_create")
    for name in ("host", "operator", "target"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / name)], check=True)
    keys = {name: b" ".join((tmp_path / (name + ".pub")).read_bytes().split()[:2]) for name in ("host", "operator", "target")}
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    known = f"[127.0.0.1]:{port} ".encode() + keys["host"] + b"\n"
    conf, drop, pub = tmp_path / "sshd_config", tmp_path / "pause.conf", tmp_path / "revoked.pub"
    conf.write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {tmp_path / 'host'}\nPidFile {tmp_path / 'pid'}\n"
        f"Include {tmp_path}/*.conf\nAuthorizedKeysFile {tmp_path / 'operator.pub'}\n"
        f"AuthorizedKeysCommand /usr/bin/echo {keys['target'].decode()}\nAuthorizedKeysCommandUser root\n"
        "PermitRootLogin yes\nAllowUsers root\nUsePAM yes\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nStrictModes yes\nLogLevel ERROR\n")
    daemon = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        def offers(expected_target, expected_operator):
            def probe(key, *, timeout):
                assert daemon.poll() is None, "isolated sshd exited"
                return m.public_offer(key, known, port=port, timeout=timeout)
            try:
                # Same readiness implementation as the production operator,
                # not a test-only retry loop masking reload races.
                m.wait_public_offers(probe, (keys["target"], keys["operator"]), (expected_target, expected_operator))
            except m.PauseError:
                pytest.fail(f"new TCP offer outcomes unproven; isolated client: {diagnostics}")
        offers(True, True)
        m.publish(pub, keys["target"] + b"\n")
        m.publish(drop, f"RevokedKeys {pub}\n".encode())
        daemon.send_signal(signal.SIGHUP)
        offers(False, True)
        pub.rename(tmp_path / "retained.pub")
        offers(False, False)  # Missing file is fail-closed for ALL public keys.
        (tmp_path / "retained.pub").rename(pub)
        offers(False, True)
        drop.unlink()
        daemon.send_signal(signal.SIGHUP)
        offers(True, True)
        assert pub.exists()
    finally:
        daemon.terminate()
        daemon.communicate(timeout=10)
