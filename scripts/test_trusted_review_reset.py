"""Offline contract tests; no production, network, SSH or database execution."""

import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SHA = "a" * 40
OP = "b" * 32
OTHER = "c" * 32
SCRIPTS = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def put(path, data, mode=0o600):
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    path.chmod(mode)


class ReviewResetTests(unittest.TestCase):
    def test_reset_requires_time_for_completion_and_recovery(self):
        self.policy["expires_at"] = 100 + self.server.DEPLOY_TIMEOUT_SECONDS
        put(self.config / "authorized-release.json", self.policy)
        with self.assertRaises(self.server.LaunchError):
            self.reset.reset_review(SHA, OP)
        self.assertFalse(self.operation.exists())

    def test_failing_ci_gate_never_reads_production_credentials(self):
        self.gate_error = subprocess.TimeoutExpired("offline-gate", 1)
        self.patch(self.server, "read_production_env", lambda: self.fail("credential read before CI"))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.reset.reset_review(SHA, OP)
        self.assertFalse(self.operation.exists())

    def assert_slow_proof_blocks_without_intent(self, elapsed):
        now = [100]
        self.patch(self.reset.time, "time", lambda: now[0])
        self.policy["expires_at"] = 7301
        put(self.config / "authorized-release.json", self.policy)
        def slow_proof(*args):
            now[0] += elapsed
        with patch.object(self.reset, "_validate_production", slow_proof), self.assertRaises(self.server.LaunchError):
            self.reset.reset_review(SHA, OP)
        self.assertFalse(self.operation.exists())
        self.assertNotIn("execute", self.events)

    def test_slow_production_proof_rechecks_window_before_operation_intent(self):
        self.assert_slow_proof_blocks_without_intent(300)

    def test_production_proof_cannot_consume_an_expired_authorization(self):
        self.assert_slow_proof_blocks_without_intent(7300)

    def setUp(self):
        self.reset = load("trusted_review_reset")
        self.bootstrap = load("bootstrap_trusted_release")
        self.server = load("trusted_release_server")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.workspace = self.state / SHA
        self.source = self.state / "bootstrap" / SHA / "source"
        self.config = self.root / "config"
        self.installed = self.root / "installed.py"
        self.production = self.root / "production"
        self.lease = self.root / "business-lease"
        for path in (self.workspace, self.source / "scripts", self.config,
                     self.production / ".git", self.workspace / "bin", self.workspace / "home"):
            path.mkdir(parents=True, mode=0o700)
        self.lock = self.state / "launcher.lock"
        put(self.lock, b"")
        put(self.source / "scripts/trusted_release_server.py", b"reviewed executor")
        put(self.source / "scripts/trusted_release_gate.py", b"reviewed gate")
        put(self.source / "scripts/trusted_review_reset.py", b"reviewed reset")
        put(self.source / "deploy.sh", b"reviewed deploy")
        put(self.production / ".git/config", b"")
        put(self.installed, b"reviewed executor")
        self.policy = {"sha": SHA, "expires_at": 10000,
                       "executor_sha256": hashlib.sha256(b"reviewed executor").hexdigest()}
        put(self.config / "authorized-release.json", self.policy)
        for name, state in (("started.json", "STARTED"), ("completed.json", "SUCCEEDED")):
            put(self.workspace / name, {"sha": SHA, "state": state})
        self.production_env = "SECRET=offline-fixture\nDEPLOY_SERVER=old\nDEPLOY_PATH=/old\n"
        put(self.workspace / "deployment.env",
            b"SECRET=offline-fixture\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n")
        for command in ("ssh", "scp", "python3"):
            target = "/usr/bin/python3.12" if command == "python3" else "/usr/bin/" + command
            args = "" if command == "python3" else " -F /etc/reva-release/loopback.conf"
            put(self.workspace / "bin" / command,
                f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode(), 0o700)
        self.events = []
        self.command_error = None
        self.gate_error = None
        self.head = SHA
        self.patch(self.reset, "STATE", self.state)
        self.patch(self.reset, "PRODUCTION", self.production)
        self.patch(self.bootstrap, "STATE", self.state)
        self.patch(self.bootstrap, "CONFIG", self.config)
        self.patch(self.bootstrap, "INSTALLED", self.installed)
        self.patch(self.bootstrap, "BUSINESS_LEASE", self.lease)
        self.patch(self.server, "STATE", self.state)
        self.patch(self.server, "CONFIG", self.config)
        self.patch(self.server, "POLICY", self.config / "authorized-release.json")
        self.patch(self.reset, "load_reviewed", lambda sha: (self.source, self.bootstrap, self.server))
        def production_proof(sha, *args):
            self.events.append("head")
            if self.head != sha:
                raise self.reset.ResetError("production proof failed")
        self.patch(self.reset, "_validate_production", production_proof)
        self.patch(self.bootstrap, "canonical_source", lambda sha: self.source)
        self.patch(self.bootstrap, "secure", self.secure)
        self.patch(self.server, "secure_path", self.secure)
        # Only uid and ancestors outside the fixture are virtualized. File type,
        # modes, links, locking, exclusive writes and fsync remain real.
        original_metadata = self.server.validate_metadata
        def metadata(info, **kwargs):
            values = list(info)
            values[4] = 0
            return original_metadata(os.stat_result(values), **kwargs)
        self.patch(self.server, "validate_metadata", metadata)
        self.patch(self.server, "read_production_env", lambda: self.production_env)
        self.patch(self.server, "validate_loopback", lambda policy: self.events.append("loopback"))
        self.patch(self.reset.time, "time", lambda: 100)
        self.patch(self.reset.subprocess, "run", self.run_command)
        self.real_sync = self.server._sync_directory
        def sync(path):
            self.real_sync(path)
            self.events.append(("sync", Path(path)))
        self.patch(self.server, "_sync_directory", sync)

    def patch(self, obj, name, value):
        item = patch.object(obj, name, value)
        item.start()
        self.addCleanup(item.stop)

    def secure(self, path, *, private=False, directory=False):
        path = Path(path)
        if not path.is_relative_to(self.root):
            return
        for item in (path, *path.parents):
            if item == self.root.parent:
                break
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022 or (
                    stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                raise RuntimeError("unsafe fixture path")
        if directory and not path.is_dir():
            raise RuntimeError("not a directory")
        if private and (not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600):
            raise RuntimeError("not private")

    @property
    def operations(self):
        return self.workspace / "review-resets"

    @property
    def operation(self):
        return self.operations / OP

    def marker(self, operation_id, state):
        return {"sha": SHA, "operation_id": operation_id, "state": state}

    def run_command(self, args, **kwargs):
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(kwargs["check"])
        self.assertNotIn("shell", kwargs)
        if args[0] == "/usr/bin/git":
            self.events.append("head")
            return SimpleNamespace(stdout=self.head + "\n", returncode=0)
        if args[0] == "/usr/bin/python3.12":
            self.assertEqual(args, [self.server.PYTHON, "-I", "-S", "-B",
                str(self.source / "scripts/trusted_release_gate.py"), "--sha", SHA, "--workflow-sha", SHA])
            self.events.append("gate")
            if self.gate_error:
                raise self.gate_error
            return SimpleNamespace(returncode=0)
        self.assertEqual(args, ["/bin/bash", str(self.source / "deploy.sh"), "-R"])
        self.assertEqual(kwargs["cwd"], self.source)
        expected_env = self.server.clean_environment(self.workspace)
        expected_env.update(DEPLOY_SOURCE_SHA=SHA, DEPLOY_ENV_FILE=str(self.workspace / "deployment.env"))
        self.assertEqual(kwargs["env"], expected_env)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"], self.server.DEPLOY_TIMEOUT_SECONDS)
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(json.loads((self.operation / "started.json").read_bytes()), self.marker(OP, "STARTED"))
        for parent in (self.operation, self.operations, self.workspace):
            self.assertIn(("sync", parent), self.events)
        self.assertIn("gate", self.events)
        self.assertIn("loopback", self.events)
        with self.lock.open("r+") as held, self.assertRaises(BlockingIOError):
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.events.append("execute")
        if self.command_error:
            self.lease.mkdir()
            raise self.command_error
        return SimpleNamespace(returncode=0)

    def invoke(self, sha=SHA, operation_id=OP):
        return self.reset.reset_review(sha, operation_id)

    def assert_blocked(self):
        with self.assertRaises((self.reset.ResetError, self.bootstrap.BootstrapError,
                                self.server.LaunchError, OSError, RuntimeError,
                                subprocess.SubprocessError)):
            self.invoke()
        self.assertNotIn("execute", self.events)
        self.assertFalse(self.operation.exists())

    def test_success_is_durable_ordered_and_preserves_original_lock(self):
        inode = self.lock.stat().st_ino
        with patch.dict(os.environ, {"BASH_ENV": "/evil", "DEPLOY_SERVER": "evil", "GH_TOKEN": "secret"}):
            self.assertEqual(self.invoke(), self.marker(OP, "SUCCEEDED"))
        self.assertEqual(self.lock.stat().st_ino, inode)
        self.assertEqual({p.name for p in self.operation.iterdir()}, {"started.json", "completed.json"})
        self.assertEqual(json.loads((self.operation / "completed.json").read_bytes()), self.marker(OP, "SUCCEEDED"))
        for path in (self.operations, self.operation):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        for path in self.operation.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertGreater(self.events.index(("sync", self.operation)), self.events.index("gate"))

    def test_ids_are_exact_before_any_io(self):
        for sha, operation_id in ((SHA[:39], OP), (SHA.upper(), OP), (SHA + "\n", OP),
                                  (SHA, OP[:31]), (SHA, OP.upper()), (SHA, "../" + OP)):
            with self.subTest(sha=sha, operation_id=operation_id), self.assertRaises(self.reset.ResetError):
                self.invoke(sha, operation_id)
        self.assertEqual(self.events, [])

    def test_duplicate_success_id_cannot_retry_or_replace_markers(self):
        self.invoke()
        before = {p.name: (p.stat().st_ino, p.read_bytes()) for p in self.operation.iterdir()}
        with self.assertRaises(self.reset.ResetError):
            self.invoke()
        self.assertEqual(before, {p.name: (p.stat().st_ino, p.read_bytes()) for p in self.operation.iterdir()})
        self.assertEqual(self.events.count("execute"), 1)

    def test_previous_unknown_and_malformed_evidence_block_new_id(self):
        self.operations.mkdir(mode=0o700)
        previous = self.operations / OTHER
        previous.mkdir(mode=0o700)
        variants = ({}, {"started.json": self.marker(OTHER, "STARTED")},
                    {"started.json": self.marker(OTHER, "STARTED"), "completed.json": self.marker(OTHER, "NEEDS_OPERATOR")},
                    {"started.json": self.marker(OP, "STARTED"), "completed.json": self.marker(OTHER, "SUCCEEDED")},
                    {"completed.json": self.marker(OTHER, "SUCCEEDED")})
        for files in variants:
            with self.subTest(files=files):
                for path in previous.iterdir():
                    path.unlink()
                for name, data in files.items():
                    put(previous / name, data)
                self.assert_blocked()

    def test_previous_success_permits_distinct_id_but_not_unknown_inventory(self):
        self.operations.mkdir(mode=0o700)
        previous = self.operations / OTHER
        previous.mkdir(mode=0o700)
        put(previous / "started.json", self.marker(OTHER, "STARTED"))
        put(previous / "completed.json", self.marker(OTHER, "SUCCEEDED"))
        put(previous / "unknown", b"")
        self.assert_blocked()
        (previous / "unknown").unlink()
        self.invoke()

    def test_unknown_reset_for_other_sha_blocks(self):
        other = self.state / ("d" * 40) / "review-resets" / OTHER
        other.mkdir(parents=True, mode=0o700)
        self.assert_blocked()

    def test_existing_lock_missing_symlink_or_busy_never_recreated(self):
        self.lock.unlink()
        self.assert_blocked()
        self.assertFalse(self.lock.exists())
        self.lock.symlink_to(self.root / "missing")
        self.assert_blocked()
        self.assertTrue(self.lock.is_symlink())
        self.lock.unlink()
        put(self.lock, b"")
        with self.lock.open("r+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_blocked()

    def test_gate_failure_has_no_intent_or_execution(self):
        self.gate_error = subprocess.TimeoutExpired("secret", 1)
        self.assert_blocked()
        self.assertFalse(self.operations.exists())

    def test_backend_sha_policy_expiry_and_hash_fail_closed(self):
        variants = ({**self.policy, "sha": "d" * 40}, {**self.policy, "expires_at": 100},
                    {**self.policy, "executor_sha256": "0" * 64})
        for policy in variants:
            with self.subTest(policy=policy):
                put(self.config / "authorized-release.json", policy)
                self.assert_blocked()
        put(self.config / "authorized-release.json", self.policy)
        put(self.installed, b"unreviewed")
        put(self.config / "authorized-release.json", {**self.policy,
            "executor_sha256": hashlib.sha256(b"unreviewed").hexdigest()})
        self.assert_blocked()
        put(self.installed, b"reviewed executor")
        put(self.config / "authorized-release.json", self.policy)
        for state in ("STARTED", "NEEDS_OPERATOR", "PREPARATION_FAILED"):
            put(self.workspace / "completed.json", {"sha": SHA, "state": state})
            self.assert_blocked()

    def test_head_and_canonical_source_mismatch_block(self):
        self.head = "d" * 40
        self.assert_blocked()
        self.head = SHA
        self.patch(self.bootstrap, "canonical_source", lambda sha: self.workspace / "source")
        self.assert_blocked()

    def test_wrappers_env_and_loopback_must_be_reviewed(self):
        wrapper = self.workspace / "bin/ssh"
        original = wrapper.read_bytes()
        put(wrapper, b"#!/bin/sh\necho arbitrary\n", 0o700)
        self.assert_blocked()
        put(wrapper, original, 0o700)
        candidate = self.workspace / "deployment.env"
        original = candidate.read_bytes()
        put(candidate, original.replace(b"health\n", b"evil\n"))
        self.assert_blocked()
        put(candidate, original, 0o644)
        self.assert_blocked()
        put(candidate, original)
        self.patch(self.server, "validate_loopback", lambda policy: (_ for _ in ()).throw(RuntimeError("secret")))
        self.assert_blocked()

    def test_existing_business_lease_is_never_adopted_or_removed(self):
        self.lease.symlink_to(self.root / "missing")
        self.assert_blocked()
        self.assertTrue(self.lease.is_symlink())

    def test_timeout_nonzero_and_interrupt_are_unknown_and_preserve_lease(self):
        for error in (subprocess.TimeoutExpired("secret", 1), subprocess.CalledProcessError(2, "secret"), KeyboardInterrupt()):
            with self.subTest(error=error):
                self.command_error = error
                with self.assertRaises(self.reset.ResetError):
                    self.invoke()
                self.assertEqual(json.loads((self.operation / "completed.json").read_bytes()), self.marker(OP, "NEEDS_OPERATOR"))
                self.assertTrue(self.lease.is_dir())
                with self.assertRaises(self.reset.ResetError):
                    self.invoke(operation_id=OTHER)
                # Fixture-only cleanup allows another independent failure case.
                for path in self.operation.iterdir():
                    path.unlink()
                self.operation.rmdir()
                self.lease.rmdir()

    def test_intent_fsync_failure_never_executes_and_blocks_following_id(self):
        original = self.server._sync_directory
        def fail(path):
            if Path(path) == self.operation:
                raise OSError("secret durability failure")
            return original(path)
        self.patch(self.server, "_sync_directory", fail)
        with self.assertRaises(OSError):
            self.invoke()
        self.assertNotIn("execute", self.events)
        self.assertTrue(self.operation.exists())
        with self.assertRaises(self.reset.ResetError):
            self.invoke(operation_id=OTHER)

    def test_main_sanitizes_even_parser_errors_and_rejects_caller_options(self):
        self.patch(self.reset, "operator_context", lambda: None)
        self.patch(self.reset, "reset_review", lambda *args: (_ for _ in ()).throw(RuntimeError("credential-value")))
        for argv in (["--sha", SHA, "--operation-id", OP],
                     ["--sha", SHA, "--operation-id", OP, "--env", "credential-value"],
                     ["--sha", "credential-value", "--operation-id", OP]):
            output = io.StringIO()
            with patch.object(self.reset.sys, "argv", ["reset", *argv]), contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
                self.assertEqual(self.reset.main(), 1)
            self.assertNotIn("credential-value", output.getvalue())

    def test_local_source_entry_is_rejected_before_import(self):
        reset = load("trusted_review_reset")
        with patch.object(reset.importlib.util, "spec_from_file_location") as imported:
            with self.assertRaises(reset.ResetError):
                reset.load_reviewed(SHA)
            imported.assert_not_called()

    def test_cached_bootstrap_is_rejected_before_any_import(self):
        reset = load("trusted_review_reset")
        cached = self.source / "scripts/__pycache__"
        cached.mkdir(mode=0o700)
        with patch.object(reset, "STATE", self.state), patch.object(reset, "__file__", str(self.source / "scripts/trusted_review_reset.py")), patch.object(reset, "_secure_import"), patch.object(reset.importlib.util, "spec_from_file_location") as imported:
            with self.assertRaises(reset.ResetError):
                reset.load_reviewed(SHA)
            imported.assert_not_called()

    def test_lock_replacement_during_gate_cannot_authorize_execution(self):
        run = self.run_command
        def replace_lock(args, **kwargs):
            result = run(args, **kwargs)
            if args[0] == self.server.PYTHON:
                self.lock.rename(self.state / "original.lock")
                put(self.lock, b"")
            return result
        self.patch(self.reset.subprocess, "run", replace_lock)
        self.assert_blocked()

    def test_policy_expiration_or_target_drift_during_gate_blocks(self):
        run = self.run_command
        def expire(args, **kwargs):
            result = run(args, **kwargs)
            if args[0] == self.server.PYTHON:
                put(self.config / "authorized-release.json", {**self.policy, "expires_at": 100})
            return result
        self.patch(self.reset.subprocess, "run", expire)
        self.assert_blocked()

    def test_success_marker_write_failure_leaves_blocking_started(self):
        write = self.server._write_private
        def fail(path, data):
            if path == self.operation / "completed.json":
                raise OSError("private completion failure")
            return write(path, data)
        self.patch(self.server, "_write_private", fail)
        with self.assertRaises(OSError):
            self.invoke()
        self.assertIn("execute", self.events)
        self.assertFalse((self.operation / "completed.json").exists())
        with self.assertRaises(self.reset.ResetError):
            self.invoke(operation_id=OTHER)
        self.assertEqual(self.events.count("execute"), 1)

    def test_previous_duplicate_json_and_symlink_or_hardlink_are_blocking(self):
        self.operations.mkdir(mode=0o700)
        previous = self.operations / OTHER
        previous.mkdir(mode=0o700)
        put(previous / "started.json", self.marker(OTHER, "STARTED"))
        complete = previous / "completed.json"
        put(complete, ('{"sha":"' + SHA + '","operation_id":"' + OTHER +
                       '","state":"NEEDS_OPERATOR","state":"SUCCEEDED"}').encode())
        self.assert_blocked()
        complete.unlink()
        complete.symlink_to(self.root / "missing")
        self.assert_blocked()
        complete.unlink()
        put(self.root / "other-receipt", self.marker(OTHER, "SUCCEEDED"))
        os.link(self.root / "other-receipt", complete)
        self.assert_blocked()

    def test_all_intent_fsync_levels_fail_closed(self):
        for level in (self.workspace, self.operations):
            with self.subTest(level=level):
                sync = self.server._sync_directory
                def fail(path, level=level, sync=sync):
                    if Path(path) == level:
                        raise OSError("private fsync failure")
                    return sync(path)
                with patch.object(self.server, "_sync_directory", fail), self.assertRaises(OSError):
                    self.invoke()
                self.assertNotIn("execute", self.events)
                if self.operation.exists():
                    with self.assertRaises(self.reset.ResetError):
                        self.invoke(operation_id=OTHER)

    def test_marker_file_fsync_is_before_directory_fsync_and_execution(self):
        fsync = os.fsync
        def observe(fd):
            fsync(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                self.events.append("file-fsync")
        with patch.object(os, "fsync", observe):
            self.invoke()
        first_file = self.events.index("file-fsync")
        self.assertLess(first_file, self.events.index(("sync", self.operation)))
        self.assertLess(first_file, self.events.index("execute"))
        self.assertEqual(self.events.count("file-fsync"), 2)

    def test_operator_boundary_root_isolation_system_python_and_rpc(self):
        reset = self.reset
        for isolated, uid, executable, rpc in ((False, 0, "/usr/bin/python3", False),
                (True, 1000, "/usr/bin/python3", False),
                (True, 0, "/tmp/python3", False), (True, 0, "/usr/bin/python3", True)):
            with (
                self.subTest(isolated=isolated, uid=uid, executable=executable, rpc=rpc),
                patch.object(reset.sys, "flags", SimpleNamespace(isolated=isolated, no_site=True, dont_write_bytecode=True)),
                patch.object(reset.os, "geteuid", return_value=uid),
                patch.object(reset.sys, "executable", executable),
                patch.dict(os.environ, {"SSH_ORIGINAL_COMMAND": "run " + SHA} if rpc else {}, clear=True),
                self.assertRaises(reset.ResetError),
            ):
                reset.operator_context()

    def test_root_import_metadata_rejects_wrong_owner_mode_and_links(self):
        target = Path("/fixed/source/scripts/trusted_review_reset.py")
        for fault in ("owner", "writable", "symlink", "hardlink"):
            def metadata(path, fault=fault):
                mode = stat.S_IFREG | 0o644 if path == target else stat.S_IFDIR | 0o755
                uid, links = 0, 1
                if path == target:
                    if fault == "owner":
                        uid = 501
                    elif fault == "writable":
                        mode |= 0o022
                    elif fault == "symlink":
                        mode = stat.S_IFLNK | 0o777
                    else:
                        links = 2
                return os.stat_result((mode, 1, 1, links, uid, 0, 0, 0, 0, 0))
            with self.subTest(fault=fault), patch.object(Path, "lstat", metadata), self.assertRaises(self.reset.ResetError):
                self.reset._secure_import(target)

    def test_reviewed_loader_uses_same_directory_bootstrap_and_exact_sha(self):
        reset = load("trusted_review_reset")
        path = self.source / "scripts/bootstrap_trusted_release.py"
        put(path, b"# import boundary fixture")
        put(self.source / "scripts/trusted_release_server.py", (SCRIPTS / "trusted_release_server.py").read_bytes())
        original_spec = importlib.util.spec_from_file_location
        imported = []
        def spec(name, location):
            imported.append((name, Path(location)))
            result = original_spec(name, location)
            if name == "reviewed_reset_bootstrap":
                result.loader.exec_module = lambda module: module.__dict__.update(self.bootstrap.__dict__)
            return result
        with patch.object(reset, "STATE", self.state), patch.object(reset, "__file__", str(self.source / "scripts/trusted_review_reset.py")), patch.object(reset, "_secure_import", self.secure), patch.object(self.bootstrap, "__file__", str(path)), patch.object(reset.importlib.util, "spec_from_file_location", spec):
            source, bootstrap, server = reset.load_reviewed(SHA)
        self.assertEqual(source, self.source)
        self.assertEqual(bootstrap.STATE, self.state)
        self.assertEqual(server.PYTHON, "/usr/bin/python3.12")
        self.assertEqual(imported, [("reviewed_reset_bootstrap", path),
            ("reviewed_release_server", self.source / "scripts/trusted_release_server.py")])

    def test_private_directory_and_wrapper_inventory_rejections(self):
        self.workspace.chmod(0o755)
        self.assert_blocked()
        self.workspace.chmod(0o700)
        put(self.workspace / "bin/unreviewed", b"")
        self.assert_blocked()
        (self.workspace / "bin/unreviewed").unlink()
        (self.workspace / "started.json").unlink()
        self.assert_blocked()

    def test_unknown_child_name_and_mode_block(self):
        self.operations.mkdir(mode=0o700)
        child = self.operations / "not-an-operation"
        child.mkdir(mode=0o700)
        self.assert_blocked()
        child.rmdir()
        child = self.operations / OTHER
        child.mkdir(mode=0o755)
        self.assert_blocked()

    def test_marker_exclusive_write_never_replaces_existing_bytes(self):
        self.operations.mkdir(mode=0o700)
        self.operation.mkdir(mode=0o700)
        target = self.operation / "started.json"
        put(target, self.marker(OP, "STARTED"))
        before = (target.stat().st_ino, target.read_bytes())
        with self.assertRaises(FileExistsError):
            self.server._write_private(target, b"overwrite")
        self.assertEqual((target.stat().st_ino, target.read_bytes()), before)

    def test_main_success_prints_only_operation_receipt(self):
        self.patch(self.reset, "operator_context", lambda: None)
        output = io.StringIO()
        with patch.object(self.reset.sys, "argv", ["reset", "--sha", SHA, "--operation-id", OP]), contextlib.redirect_stdout(output):
            self.assertEqual(self.reset.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), self.marker(OP, "SUCCEEDED"))

    def test_operator_success_sets_private_umask_without_accepting_environment(self):
        with patch.object(self.reset.sys, "flags", SimpleNamespace(isolated=True, no_site=True, dont_write_bytecode=True)), patch.object(self.reset.os, "geteuid", return_value=0), patch.object(self.reset.sys, "executable", "/usr/bin/python3.12"), patch.object(Path, "resolve", return_value=Path("/usr/bin/python3.12")), patch.object(self.reset, "_secure_import") as secure, patch.object(os, "umask") as umask, patch.dict(os.environ, {}, clear=True):
            self.reset.operator_context()
            secure.assert_called_once_with(Path("/usr/bin/python3.12"))
            umask.assert_called_once_with(0o077)
            self.assertTrue(self.reset.sys.dont_write_bytecode)


class ProductionExecutionTests(unittest.TestCase):
    """Real isolated Git/content proofs; only root metadata is virtualized."""

    def setUp(self):
        self.reset = load("trusted_review_reset")
        self.bootstrap = load("bootstrap_trusted_release")
        self.server = load("trusted_release_server")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "source"
        self.repo = self.root / "production"
        self.source.mkdir()
        self.git(self.source, "init", "-b", "main")
        self.git(self.source, "config", "user.name", "Offline Fixture")
        self.git(self.source, "config", "user.email", "fixture@example.invalid")
        for name, content in {
            ".gitignore": "venv/\n*.pyc\n__pycache__/\nignored/\n",
            ".gitattributes": "backend/app/model.py filter=evil\n",
            "backend/scripts/seed_demo_account.py": "from app import model\n",
            "backend/app/__init__.py": "",
            "backend/app/model.py": "value = 1\n",
            "backend/requirements.lock": "fixture==1.0\n",
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            put(path, content.encode(), 0o644)
        runner = self.source / "backend/scripts/activate_health_evidence_runtime.sh"
        put(runner, (SCRIPTS.parent / "backend/scripts/activate_health_evidence_runtime.sh").read_bytes(), 0o644)
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "offline fixture")
        self.sha = self.git(self.source, "rev-parse", "HEAD").stdout.strip()
        shutil.copytree(self.source, self.repo)
        self.venv = self.repo / "backend/venv"
        self.site = self.venv / "lib/python3.12/site-packages"
        self.site.mkdir(parents=True)
        (self.venv / "bin").mkdir()
        self.python = self.root / "system/python3.12"
        self.python.parent.mkdir()
        put(self.python, b"never executed", 0o755)
        (self.venv / "bin/python").symlink_to("python3")
        (self.venv / "bin/python3").symlink_to(self.python)
        put(self.venv / "pyvenv.cfg", f"home = {self.python.parent}\ninclude-system-site-packages = false\nversion = 3.12.1\n".encode())
        put(self.site / "fixture.py", b"value = 1\n", 0o644)
        self.lease = self.root / "lease"
        self.lease.mkdir(mode=0o700)
        self.token = "fixture-lease-token"
        put(self.lease / "token", (self.token + "\n").encode())
        self.patch(self.reset, "PRODUCTION", self.repo)
        self.patch(self.reset, "SYSTEM_PYTHON", self.python)
        self.patch(self.bootstrap, "BUSINESS_LEASE", self.lease)
        self.patch(self.reset, "operator_context", lambda: None)
        self.patch(self.reset, "load_reviewed", lambda sha: (self.source, self.bootstrap, self.server))
        self.patch(self.server, "secure_path", self.secure)
        self.patch(self.bootstrap, "secure", self.secure)
        real_lstat = Path.lstat
        def metadata(path, *args, **kwargs):
            info = list(real_lstat(path, *args, **kwargs))
            info[4], info[5] = 0, 0
            return os.stat_result(info)
        self.patch(Path, "lstat", metadata)
        self.real_run = subprocess.run
        self.patch(self.reset.subprocess, "run", self.proof_run)

    def patch(self, obj, name, value):
        item = patch.object(obj, name, value)
        item.start()
        self.addCleanup(item.stop)

    def git(self, repo, *args):
        run = getattr(self, "real_run", subprocess.run)
        return run(["/usr/bin/git", "-C", str(repo), *args], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})

    def secure(self, path, *, private=False, directory=False):
        path = Path(path)
        for entry in (path, *path.parents):
            if entry == self.root.parent:
                break
            info = entry.lstat()
            if info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode) or (
                    stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                raise self.reset.ResetError("unsafe fixture metadata")
        if directory and not path.is_dir():
            raise self.reset.ResetError("expected directory")
        if not directory and not stat.S_ISREG(path.lstat().st_mode):
            raise self.reset.ResetError("expected regular file")
        if private and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise self.reset.ResetError("expected private file")

    def proof_run(self, args, **kwargs):
        if args[0] == "/usr/bin/git":
            self.assertEqual(args, ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(self.source), "ls-tree", "-rz", "--full-tree", "HEAD", "--", "backend"])
            return self.real_run(args, **kwargs)
        self.assertEqual(args[:4], ["/bin/bash", "-e", "-u", "-c"])
        self.assertNotIn("activate\n", args[4])
        self.assertEqual(kwargs["env"]["REPO_PATH"], str(self.repo))
        self.assertEqual(kwargs["env"]["EXPECTED_SHA"], self.sha)
        # The production proof uses GNU stat. This adapter supplies only its
        # metadata ABI on macOS, preserving actual mode/link/content checks.
        stat_args = "-f '%Lp'" if sys.platform == "darwin" else "-c '%a'"
        adapter = '''
id() { printf '0\\n'; }
stat() {
    printf 'root:root:'
    /usr/bin/stat ''' + stat_args + ''' "${@: -1}"
}
'''
        return self.real_run([*args[:4], adapter + args[4]], **kwargs)

    def invoke(self):
        return self.reset.validate_production_execution(self.sha, self.lease, self.token)

    def test_clean_production_with_normal_python_symlink_passes_without_execution(self):
        self.assertIsNone(self.invoke())

    def test_private_media_is_not_an_application_import_source(self):
        media = self.repo / "backend/ignored/private_media"
        media.mkdir(parents=True)
        media.chmod(0o700)
        put(media / "not_executed.py", b"raise RuntimeError('private media')\n")
        # This runtime tree is outside the canonical import root; not read,
        # recursively normalized or deleted by maintenance.
        original = media.lstat().st_ino
        with patch.object(self.server, "secure_path", wraps=self.secure) as checked:
            self.assertIsNone(self.invoke())
        self.assertFalse(any(Path(call.args[0]).is_relative_to(media) for call in checked.call_args_list))
        self.assertEqual(media.lstat().st_ino, original)

    def test_root_managed_pth_is_inert_but_writable_pth_is_rejected(self):
        hook = self.site / "dependency.pth"
        put(hook, b"import definitely_untrusted_startup_hook\n/tmp/untrusted\n", 0o644)
        self.assertIsNone(self.invoke())
        hook.chmod(0o666)
        with self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_nested_dependency_customization_module_is_not_a_startup_hook(self):
        package = self.site / "dependency/instrumentation"
        (package / "__pycache__").mkdir(parents=True)
        put(package / "sitecustomize.py", b"raise RuntimeError('not a startup source')\n", 0o644)
        put(package / "__pycache__/sitecustomize.cpython-312.pyc", b"root-managed dependency bytecode", 0o644)
        self.assertIsNone(self.invoke())
        for path in (self.site / "sitecustomize.py", self.site / "__pycache__/sitecustomize.cpython-312.pyc"):
            path.parent.mkdir(exist_ok=True)
            put(path, b"startup source", 0o644)
            with self.assertRaises(self.reset.ResetError):
                self.invoke()
            path.unlink()
        (package / "sitecustomize.py").chmod(0o666)
        with self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_ignored_code_in_canonical_import_tree_is_rejected(self):
        extra = self.source / "backend/ignored/shadow.py"
        extra.parent.mkdir()
        put(extra, b"pass\n", 0o644)
        with self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_system_python3_alias_resolves_only_to_fixed_system_binary(self):
        alias = self.python.with_name("python3")
        alias.symlink_to("python3.12")
        (self.venv / "bin/python3").unlink()
        (self.venv / "bin/python3").symlink_to(alias)
        self.assertIsNone(self.invoke())
        alias.unlink()
        alias.symlink_to(self.root / "unreviewed-python")
        with self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_same_head_seeder_bytes_permissions_links_and_app_import_tamper_fail(self):
        target = self.repo / "backend/scripts/seed_demo_account.py"
        original = target.read_bytes()
        for fault in ("bytes", "mode", "symlink", "hardlink", "app", "ignored"):
            with self.subTest(fault=fault):
                if fault == "bytes":
                    put(target, b"print('tampered')\n", 0o644)
                elif fault == "mode":
                    target.chmod(0o666)
                elif fault in {"symlink", "hardlink"}:
                    put(self.root / "linked-seeder", original, 0o644)
                    target.unlink()
                    if fault == "symlink":
                        target.symlink_to(self.root / "linked-seeder")
                    else:
                        os.link(self.root / "linked-seeder", target)
                elif fault == "app":
                    put(self.repo / "backend/app/model.py", b"value = 2\n", 0o644)
                else:
                    extra = self.source / "backend/ignored/shadow.py"
                    extra.parent.mkdir()
                    put(extra, b"pass\n", 0o644)
                with self.assertRaises(self.reset.ResetError):
                    self.invoke()
                target.unlink()
                put(target, original, 0o644)
                put(self.repo / "backend/app/model.py", b"value = 1\n", 0o644)
                if fault == "ignored":
                    shutil.rmtree(self.source / "backend/ignored")
                self.assertIsNone(self.invoke())

    def test_venv_content_import_path_mode_and_interpreter_fail_closed(self):
        baseline = self.root / "venv-baseline"
        shutil.copytree(self.venv, baseline, symlinks=True)
        for fault in ("mode", "system-site", "python", "hardlink", "sitecustomize", "editable", "outside-link", "cfg-home"):
            with self.subTest(fault=fault):
                if fault == "mode":
                    (self.site / "fixture.py").chmod(0o666)
                elif fault == "system-site":
                    put(self.venv / "pyvenv.cfg", b"include-system-site-packages = true\n")
                elif fault == "python":
                    (self.venv / "bin/python3").unlink()
                    (self.venv / "bin/python3").symlink_to(self.root / "other-python")
                elif fault == "hardlink":
                    os.link(self.site / "fixture.py", self.site / "linked.py")
                elif fault == "sitecustomize":
                    put(self.site / "sitecustomize.py", b"pass\n", 0o644)
                elif fault == "editable":
                    put(self.site / "editable.egg-link", b"/tmp/source\n", 0o644)
                elif fault == "outside-link":
                    (self.site / "outside").symlink_to(self.root)
                else:
                    put(self.venv / "pyvenv.cfg", b"home = /tmp/untrusted\ninclude-system-site-packages = false\nversion = 3.12.1\n")
                with self.assertRaises(self.reset.ResetError):
                    self.invoke()
                shutil.rmtree(self.venv)
                shutil.copytree(baseline, self.venv, symlinks=True)
                self.assertIsNone(self.invoke())

    def test_wrong_or_replaced_lease_fails_before_or_after_proof(self):
        with self.assertRaises(self.reset.ResetError):
            self.reset.validate_production_execution(self.sha, self.lease, "wrong")
        with self.assertRaises(self.reset.ResetError):
            self.reset.validate_production_execution(self.sha, self.root, self.token)
        proof = self.proof_run
        def replaced(args, **kwargs):
            result = proof(args, **kwargs)
            put(self.lease / "token", b"changed\n")
            return result
        with patch.object(self.reset.subprocess, "run", replaced), self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_empty_writable_directory_fifo_and_old_bytecode_are_independent_rejections(self):
        base = self.source / "backend/ignored"
        for fault in ("empty-writable", "fifo", "pyc", "ancestor", "module-link"):
            with self.subTest(fault=fault):
                base.mkdir()
                if fault == "empty-writable":
                    base.chmod(0o777)
                elif fault == "fifo":
                    os.mkfifo(base / "blocked.py")
                elif fault == "pyc":
                    put(base / "shadow.pyc", b"cached code", 0o644)
                elif fault == "ancestor":
                    (self.repo / "backend/app").chmod(0o777)
                else:
                    (base / "module").symlink_to(self.root)
                with self.assertRaises(self.reset.ResetError):
                    self.invoke()
                (self.repo / "backend/app").chmod(0o755)
                shutil.rmtree(base)
                self.assertIsNone(self.invoke())

    def test_isolated_proof_ignores_hooks_filters_worktree_and_index_flags(self):
        marker = self.root / "hook-executed"
        target = self.repo / "backend/app/model.py"
        for fault in ("fsmonitor", "filter", "worktree", "assume-unchanged", "skip-worktree"):
            with self.subTest(fault=fault):
                config = self.repo / ".git/config"
                original = config.read_bytes()
                if fault == "fsmonitor":
                    self.git(self.repo, "config", "core.fsmonitor", f"touch {marker}")
                elif fault == "filter":
                    self.git(self.repo, "config", "filter.evil.clean", f"touch {marker}; cat")
                elif fault == "worktree":
                    self.git(self.repo, "config", "core.worktree", str(self.source))
                else:
                    self.git(self.repo, "update-index", "--" + fault, "backend/app/model.py")
                put(target, b"value = 2\n", 0o644)
                self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout.strip(), self.sha)
                with self.assertRaises(self.reset.ResetError):
                    self.invoke()
                self.assertFalse(marker.exists())
                put(config, original, 0o644)
                self.git(self.repo, "update-index", "--no-assume-unchanged", "backend/app/model.py")
                self.git(self.repo, "update-index", "--no-skip-worktree", "backend/app/model.py")
                put(target, b"value = 1\n", 0o644)
                self.assertIsNone(self.invoke())

    def test_runtime_entry_budget_is_total_and_fail_closed(self):
        with patch.object(self.reset, "MAX_RUNTIME_ENTRIES", 2), self.assertRaises(self.reset.ResetError):
            self.invoke()

    def test_failure_is_sanitized_and_reads_no_env_or_venv_code(self):
        with patch.object(self.reset, "_revision_proof", side_effect=RuntimeError("private-token-and-env")), self.assertRaisesRegex(self.reset.ResetError, "^production execution proof failed$"):
            self.invoke()

    def test_execution_proof_failure_never_reads_credentials_or_imports_seeder(self):
        with patch.object(self.reset, "_assert_isolated_search_path"), patch.object(self.reset, "_validate_production", side_effect=RuntimeError("private diagnostic")), patch.object(self.server, "read_production_env") as credentials, patch.object(self.reset, "_run_canonical_seeder") as execute:
            with self.assertRaisesRegex(self.reset.ResetError, "^review maintenance failed; preserve evidence and lease$"):
                self.reset.execute_review_maintenance(self.sha, self.lease, self.token)
            credentials.assert_not_called()
            execute.assert_not_called()

    def test_configuration_is_fixed_and_missing_database_or_credentials_never_executes(self):
        values = {"DATABASE_URL": "postgresql://localhost/review_fixture_test",
                  "APP_STORE_REVIEW_DEMO_ACCOUNT": "fixture@example.invalid",
                  "APP_STORE_REVIEW_DEMO_PASSWORD": "synthetic-fixture-only"}
        for absent in values:
            environment = "\n".join(f"{key}={value}" for key, value in values.items() if key != absent)
            with self.subTest(absent=absent), patch.object(self.reset, "_assert_isolated_search_path"), patch.object(self.reset, "_validate_production"), patch.object(self.server, "read_production_env", return_value=environment), patch.object(self.reset, "_run_canonical_seeder") as execute:
                with self.assertRaises(self.reset.ResetError):
                    self.reset.execute_review_maintenance(self.sha, self.lease, self.token)
                execute.assert_not_called()
        output = io.StringIO()
        environment = "\n".join(f"{key}={value}" for key, value in values.items())
        def seeder(source, site, supplied, before_write):
            self.assertEqual(source, self.source)
            self.assertEqual(site, self.site)
            self.assertEqual(supplied, {**values, "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
            before_write()
        with patch.object(self.reset, "_assert_isolated_search_path"), patch.object(self.reset, "_validate_production"), patch.object(self.server, "read_production_env", return_value=environment), patch.object(self.reset, "_run_canonical_seeder", seeder), patch.dict(os.environ, {"APP_STORE_REVIEW_DEMO_ACCOUNT": "caller@example.invalid"}), contextlib.redirect_stdout(output):
            self.reset.execute_review_maintenance(self.sha, self.lease, self.token)
        self.assertEqual(output.getvalue(), "APP_STORE_REVIEW_RESET_OK\n")

    def test_lease_replaced_with_identical_bytes_before_write_is_rejected(self):
        environment = "DATABASE_URL=postgresql://localhost/review_fixture_test\nAPP_STORE_REVIEW_DEMO_ACCOUNT=fixture@example.invalid\nAPP_STORE_REVIEW_DEMO_PASSWORD=synthetic-fixture-only\n"
        wrote = []
        def seeder(source, site, supplied, before_write):
            (self.lease / "token").rename(self.lease / "original-token")
            put(self.lease / "token", (self.token + "\n").encode())
            before_write()
            wrote.append(True)
        with patch.object(self.reset, "_assert_isolated_search_path"), patch.object(self.reset, "_validate_production"), patch.object(self.server, "read_production_env", return_value=environment), patch.object(self.reset, "_run_canonical_seeder", seeder), self.assertRaises(self.reset.ResetError):
            self.reset.execute_review_maintenance(self.sha, self.lease, self.token)
        self.assertEqual(wrote, [])


class IsolatedSeederTests(unittest.TestCase):
    def test_real_settings_target_override_is_blocked_before_seeder_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp).resolve()
            for path in (source / "backend/app", source / "backend/scripts"):
                path.mkdir(parents=True)
            put(source / "backend/app/__init__.py", b"")
            put(source / "backend/app/config.py", (SCRIPTS.parent / "backend/app/config.py").read_bytes())
            marker = source / "seeder-imported"
            put(source / "backend/scripts/seed_demo_account.py", (
                "from pathlib import Path\nimport json\n"
                f"Path({str(marker)!r}).touch()\n"
                "def main():\n"
                "    print(json.dumps(dict(verification='PASS', daily_plan_actions=1, timeline_events=1, demo_conversation_messages=2)))\n"
                "    return 0\n").encode())
            site = Path(sys.executable).parent.parent / "lib/python3.12/site-packages"
            environment = {"DATABASE_URL": "postgresql://localhost/review_fixture_test",
                           "SECRET_KEY": "test-secret-key-32-chars-minimum!!"}
            code = '''import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('review_reset', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def context():
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
module.operator_context = context
module.SYSTEM_SEARCH_PATHS = frozenset(sys.path)
try:
    module._run_canonical_seeder(Path(sys.argv[2]), Path(sys.argv[3]), json.loads(sys.argv[4]), lambda: None)
except module.ResetError:
    assert 'app.database' not in sys.modules
    print('BLOCKED_BEFORE_DATABASE')
else:
    print('MATCHING_TARGET_PASS')
'''
            for override in ({"database_url": "sqlite:////tmp/synthetic-wrong-target.db"},
                             {"POSTGRES_HOST": "other.invalid", "POSTGRES_PASSWORD": "synthetic"}, {}):
                with self.subTest(override=override):
                    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                        str(SCRIPTS / "trusted_review_reset.py"), str(source), str(site), json.dumps({**environment, **override})],
                        capture_output=True, text=True, timeout=20, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "BLOCKED_BEFORE_DATABASE\n" if override else "MATCHING_TARGET_PASS\n")
                    self.assertEqual(marker.exists(), not override)

    def test_environment_parser_rejects_ambiguous_keys_and_unresolved_targets(self):
        reset = load("trusted_review_reset")
        good = "DATABASE_URL=postgresql://localhost/review_fixture_test\nAPP_STORE_REVIEW_DEMO_ACCOUNT=fixture@example.invalid\nAPP_STORE_REVIEW_DEMO_PASSWORD='literal-${not_expanded}'\n"
        for bad in (good + "database_url=sqlite:////tmp/wrong.db\n",
                    good + "DATABASE_URL=postgresql://other/wrong\n",
                    good + "BROKEN='unterminated\n",
                    good.replace("fixture@example.invalid", "${REVIEW_EMAIL}"),
                    good.replace("fixture@example.invalid", "$REVIEW_EMAIL"),
                    good.replace("fixture@example.invalid", "not-an-email"),
                    good.replace("localhost", "${DB_HOST}")):
            with self.subTest(bad=bad), self.assertRaises(reset.ResetError):
                reset._parse_maintenance_environment(bad)
        self.assertEqual(reset._parse_maintenance_environment(good)["APP_STORE_REVIEW_DEMO_PASSWORD"], "literal-${not_expanded}")

    def test_real_process_does_not_execute_pth_or_import_live_or_environment_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source, site, live, hostile = (root / name for name in ("canonical", "site", "live", "hostile"))
            for path in (source / "backend/scripts", source / "backend/app", source / "backend/fixtures", site, live, hostile):
                path.mkdir(parents=True)
            marker = root / "hook-executed"
            tripwire = f"from pathlib import Path; Path({str(marker)!r}).touch()\n"
            put(site / "dependency.pth", ("import pathlib; pathlib.Path(" + repr(str(marker)) + ").touch()\n" + str(hostile) + "\n").encode())
            for parent in (site, hostile, live):
                put(parent / "sitecustomize.py", tripwire.encode())
                put(parent / "usercustomize.py", tripwire.encode())
            put(live / "live_only.py", tripwire.encode())
            put(hostile / "outside_only.py", tripwire.encode())
            put(source / "backend/app/__init__.py", b"ORIGIN = 'canonical'\n")
            put(source / "backend/app/config.py", b"class Config:\n    effective_database_url = 'postgresql://localhost/review_fixture_test'\nsettings = Config()\n")
            put(source / "backend/fixtures/synthetic.json", b'{"synthetic": true}')
            put(site / "verified_dependency.py", b"VALUE = 1\n")
            seeder = '''import importlib.util, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import app, verified_dependency
assert app.ORIGIN == 'canonical' and verified_dependency.VALUE == 1
assert Path.cwd() == Path(__file__).parent.parent
assert json.loads((Path(__file__).parent.parent / 'fixtures/synthetic.json').read_text())['synthetic']
assert os.environ.get('CALLER_ACCOUNT') is None
assert os.environ['APP_STORE_REVIEW_DEMO_ACCOUNT'] == 'fixture@example.invalid'
assert importlib.util.find_spec('live_only') is None
assert importlib.util.find_spec('outside_only') is None
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
def main():
    assert sys.argv[1:] == ['--secret-free']
    print(json.dumps(dict(verification='PASS', daily_plan_actions=1, timeline_events=1, demo_conversation_messages=2)))
    return 0
'''
            put(source / "backend/scripts/seed_demo_account.py", seeder.encode())
            # Only OS location/uid differ in this portable fixture. The child is
            # a real -I -S -B interpreter, never a mocked import or startup flow.
            code = '''import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('review_reset', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def context():
    assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
module.operator_context = context
module.SYSTEM_SEARCH_PATHS = frozenset(sys.path)
module._run_canonical_seeder(Path(sys.argv[2]), Path(sys.argv[3]),
    {'APP_STORE_REVIEW_DEMO_ACCOUNT': 'fixture@example.invalid', 'DATABASE_URL': 'postgresql://localhost/review_fixture_test'}, lambda: None)
print('ISOLATED_FIXTURE_OK')
'''
            result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                str(SCRIPTS / "trusted_review_reset.py"), str(source), str(site)],
                cwd=live, env={**os.environ, "PYTHONPATH": str(hostile), "HOME": str(hostile),
                               "CALLER_ACCOUNT": "not-the-review-account"},
                capture_output=True, text=True, timeout=20, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ISOLATED_FIXTURE_OK\n")
            self.assertFalse(marker.exists())
            self.assertEqual(list(source.rglob("*.pyc")), [])

    def test_summary_rejects_duplicates_extra_fields_boolean_counts_and_oversized_output(self):
        reset = load("trusted_review_reset")
        good = dict(verification="PASS", daily_plan_actions=1, timeline_events=1, demo_conversation_messages=2)
        reset._validate_summary(json.dumps(good))
        for value in ({**good, "extra": 1}, {**good, "daily_plan_actions": True},
                      {**good, "timeline_events": 0}, {**good, "demo_conversation_messages": 3},
                      {**good, "verification": "FAIL"}, []):
            with self.subTest(value=value), self.assertRaises(reset.ResetError):
                reset._validate_summary(json.dumps(value))
        with self.assertRaises(reset.ResetError):
            reset._validate_summary(json.dumps(good)[:-1] + ', "verification": "PASS"}')
        with self.assertRaises(reset.ResetError):
            reset._BoundedSummary().write("x" * 16385)

    def test_no_site_and_no_bytecode_are_mandatory(self):
        reset = load("trusted_review_reset")
        for no_site, no_bytecode in ((False, True), (True, False)):
            with patch.object(reset.sys, "flags", SimpleNamespace(isolated=True, no_site=no_site, dont_write_bytecode=no_bytecode)), self.assertRaises(reset.ResetError):
                reset.operator_context()

    def test_search_path_rejects_cwd_live_and_arbitrary_archives(self):
        reset = load("trusted_review_reset")
        for path in ("", ".", "/opt/health-app/backend", "/tmp/shadow.zip", "/tmp/source"):
            with patch.object(sys, "path", ["/usr/lib/python3.12", path]), self.assertRaises(reset.ResetError):
                reset._assert_isolated_search_path()


if __name__ == "__main__":
    unittest.main()
