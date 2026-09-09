"""An accepted unknown outcome must never become a successful reset."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name("review_maintenance_retirement.py")
    spec = importlib.util.spec_from_file_location("review_closure_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("context_passes", [False, True])
def test_main_validates_context_before_consuming_lease_token(monkeypatch, context_passes):
    m = load()
    events = []
    monkeypatch.setattr(sys, "argv", ["review_maintenance_retirement.py", "--sha", "b" * 40,
        "--release-sha", "a" * 40, "--operation-id", "c" * 32, "--accept-unknown-review-writes"])

    def context(sha):
        events.append("context")
        assert sha == "b" * 40
        if not context_passes:
            raise m.ClosureError("canonical or CI gate rejected")
        return None, None, None

    class ProtectedInput:
        def read(self, size):
            events.append("stdin")
            assert size == 258
            # Stop at this boundary: no lease, locks or production operations.
            raise m.ClosureError("protected input sentinel")

    monkeypatch.setattr(m, "context", context)
    monkeypatch.setattr(sys, "stdin", ProtectedInput())
    assert m.main() == 1
    assert events == (["context", "stdin"] if context_passes else ["context"])


class Adapter:
    def __init__(self, root):
        self.record = root / "closure"
        self.events = []
        self.evidence = {"old_sha": "a" * 40, "closing_sha": "b" * 40,
                         "operation_id": "c" * 32, "original_outcome": "UNKNOWN"}

    def inspect(self):
        self.events.append("inspect")
        return copy.deepcopy(self.evidence)

    def isolate(self, evidence):
        assert (self.record / "intent.json").is_file()
        self.events.append("isolate")
        return {"revoked": True}

    def inspect_account(self):
        assert self.events[-1] == "isolate"
        self.events.append("account")
        return {"verification": "CURRENT_ACCOUNT_ONLY_NOT_RESET", "account_key_sha256": "e" * 64,
                "counts": {"user_profiles": 1}}

    def archive(self, evidence):
        assert self.events[-1] == "account"
        self.events.append("archive")

    def verify_closed(self, evidence, isolation, account):
        self.events.append("verify")
        return {"installation": {}, "archives": {}, "account": account}


def test_explicit_unknown_write_acceptance_required(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.ClosureError):
        m.close_transaction(a)
    assert a.events == []
    assert not a.record.exists()


def test_inspection_and_digest_mismatch_are_non_mutating(tmp_path):
    m, a = load(), Adapter(tmp_path)
    result = m.close_transaction(a, accept_unknown=True)
    assert result["state"] == "INSPECTED_UNKNOWN_REVIEW_MAINTENANCE"
    assert not a.record.exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, accept_unknown=True, evidence_sha256="0" * 64)
    assert not a.record.exists()


def test_isolate_before_account_and_archive_never_claims_reset(tmp_path):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a, accept_unknown=True)["evidence_sha256"]
    result = m.close_transaction(a, accept_unknown=True, evidence_sha256=digest)
    assert result["state"] == "CLOSED_UNKNOWN_REVIEW_MAINTENANCE"
    assert a.events[-5:] == ["inspect", "isolate", "account", "archive", "verify"]
    intent = json.loads((a.record / "intent.json").read_text())
    completed = json.loads((a.record / "completed.json").read_text())
    assert intent["original_outcome"] == "UNKNOWN"
    assert completed["original_outcome"] == "UNKNOWN"
    assert result["receipt"] not in (a.record / "intent.json").read_text()
    assert intent["receipt_sha256"] == hashlib.sha256(result["receipt"].encode()).hexdigest()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, accept_unknown=True, evidence_sha256=digest)


@pytest.mark.parametrize("point", ["intent", "drift", "isolate", "account", "archive", "verify", "completed"])
def test_failure_preserves_intent_forbids_replay_and_issues_no_receipt(tmp_path, monkeypatch, point):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a, accept_unknown=True)["evidence_sha256"]
    original = m.write_json
    def write(path, value):
        if path.stem == point:
            raise OSError("injected durable write failure")
        original(path, value)
        if point == "drift" and path.stem == "intent":
            a.evidence["changed"] = True
    monkeypatch.setattr(m, "write_json", write)
    if point in {"isolate", "account", "archive", "verify"}:
        target = {"account": "inspect_account", "verify": "verify_closed"}.get(point, point)
        def fail(*args):
            raise OSError("injected boundary failure")
        monkeypatch.setattr(a, target, fail)
    with pytest.raises((OSError, m.ClosureError)):
        m.close_transaction(a, accept_unknown=True, evidence_sha256=digest)
    assert a.record.exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, accept_unknown=True, evidence_sha256=digest)


def test_account_inspection_is_user_scoped_and_read_only():
    m = load()
    class Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()
        def __init__(self): self.calls = []
        def exec_driver_sql(self, query):
            self.calls.append(query)
            value = {"SHOW transaction_read_only": "on", "SHOW transaction_isolation": "repeatable read", "SELECT current_database()": "testdb"}.get(query)
            return type("Scalar", (), {"scalar_one": lambda s: value})()
        def execute(self, query, parameters=None):
            self.calls.append((str(query), parameters))
            if "FROM users" in str(query):
                return type("Rows", (), {"mappings": lambda s: s, "all": lambda s: [{"id": 9, "is_active": True, "is_approved": True, "is_admin": False}]})()
            assert parameters == {"user_id": 9}
            return [({"id": 1, "user_id": 9},)]
    conn = Connection()
    result = m.inspect_account_rows(conn, "review@example.invalid", b"k" * 32, "testdb")
    assert conn.calls[0] == "SET TRANSACTION READ ONLY"
    assert "CURRENT_ACCOUNT_ONLY_NOT_RESET" == result["verification"]
    assert "review@example.invalid" not in json.dumps(result)
    assert all("WHERE" in item[0] for item in conn.calls if isinstance(item, tuple))


@pytest.mark.parametrize("dialect", ["sqlite", "mysql"])
def test_non_postgresql_cannot_prove_account(dialect):
    m = load()
    conn = type("Connection", (), {"dialect": type("Dialect", (), {"name": dialect})()})()
    with pytest.raises(m.ClosureError):
        m.inspect_account_rows(conn, "review@example.invalid", b"k" * 32, "testdb")


@pytest.fixture
def postgres_account():
    from sqlalchemy import Boolean, Column, Date, Integer, MetaData, String, Table, create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.schema import CreateSchema, DropSchema
    url = os.environ.get("REVA_REVIEW_CLOSURE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("dedicated PostgreSQL integration URL required")
    engine = create_engine(url, isolation_level="REPEATABLE READ")
    if engine.dialect.name != "postgresql":
        pytest.fail("dedicated test target must be PostgreSQL")
    schema = "review_closure_test_" + uuid.uuid4().hex
    metadata = MetaData(schema=schema)
    users = Table("users", metadata, Column("id", Integer, primary_key=True), Column("email", String),
                  Column("name", String), Column("birth_date", Date), Column("gender", String),
                  Column("onboarding_completed", Boolean), Column("is_active", Boolean),
                  Column("is_approved", Boolean), Column("is_admin", Boolean))
    m = load()
    tables = {}
    for name in (*m.DIRECT_TABLES, *m.CHILD_TABLES):
        fields = [Column("id", Integer, primary_key=True), Column("payload", JSONB)]
        fields.append(Column(m.CHILD_TABLES[name][0] if name in m.CHILD_TABLES else "user_id", Integer))
        tables[name] = Table(name, metadata, *fields)
    with engine.begin() as conn:
        conn.execute(CreateSchema(schema))
        metadata.create_all(conn)
        conn.execute(users.insert(), [{"id": n, "email": f"review{n}@example.invalid", "name": "Synthetic", "is_active": True, "is_approved": True, "is_admin": False} for n in (1, 2)])
        for name, table in tables.items():
            fk = m.CHILD_TABLES[name][0] if name in m.CHILD_TABLES else "user_id"
            conn.execute(table.insert(), [{"id": n, fk: n, "payload": {"synthetic": str(n)}} for n in (1, 2)])
    try:
        yield engine, schema, tables
    finally:
        with engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def test_postgres_real_read_only_user_isolation_and_relationships(postgres_account):
    from sqlalchemy.exc import DBAPIError
    engine, schema, tables = postgres_account
    m, key = load(), b"k" * 32
    def snapshot():
        with engine.connect() as conn, conn.begin():
            conn.exec_driver_sql('SET LOCAL search_path TO "' + schema + '"')
            result = m.inspect_account_rows(conn, "review1@example.invalid", key, engine.url.database)
            assert all(t["count"] == 1 for t in result["tables"].values())
            with pytest.raises(DBAPIError):
                conn.execute(tables["user_profiles"].insert().values(id=3, user_id=1))
            return result
    before = snapshot()
    with engine.begin() as conn:
        for table in tables.values():
            conn.execute(table.update().where(table.c.id == 2).values(payload={"outsider": "changed"}))
    assert snapshot() == before
    with engine.begin() as conn:
        target = tables["medical_exam_items"]
        conn.execute(target.update().where(target.c.id == 1).values(payload={"review": "changed"}))
    assert snapshot() != before


def test_postgres_wrong_database_rejected_before_account_query(postgres_account):
    engine, schema, _ = postgres_account
    m = load()
    with engine.connect() as conn, conn.begin():
        conn.exec_driver_sql('SET LOCAL search_path TO "' + schema + '"')
        with pytest.raises(m.ClosureError):
            m.inspect_account_rows(conn, "review1@example.invalid", b"k" * 32, "definitely_not_this_database")


@pytest.mark.parametrize("case", ["missing", "admin", "inactive", "duplicate"])
def test_postgres_invalid_review_identity_blocks(postgres_account, case):
    engine, schema, _ = postgres_account
    m = load()
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.exec_driver_sql('SET LOCAL search_path TO "' + schema + '"')
        if case == "missing":
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1})
        elif case == "duplicate":
            conn.execute(text("UPDATE users SET email = :email WHERE id = :id"), {"email": "review1@example.invalid", "id": 2})
        else:
            query = "UPDATE users SET is_admin = true WHERE id = :id" if case == "admin" else "UPDATE users SET is_active = false WHERE id = :id"
            conn.execute(text(query), {"id": 1})
    with engine.connect() as conn, conn.begin():
        conn.exec_driver_sql('SET LOCAL search_path TO "' + schema + '"')
        with pytest.raises(m.ClosureError):
            m.inspect_account_rows(conn, "review1@example.invalid", b"k" * 32, engine.url.database)


@pytest.mark.parametrize("command", [b"sshd: root@notty\0", b"sshd: root [priv]\0", b"sshd-session: root@notty\0"])
def test_authenticated_or_pending_ssh_session_blocks(tmp_path, command):
    m = load()
    current = tmp_path / str(os.getpid())
    current.mkdir()
    (current / "stat").write_text(f"{os.getpid()} (python) S 1 0 0")
    other = tmp_path / "99999999"
    other.mkdir()
    (other / "cmdline").write_bytes(command)
    with pytest.raises(m.ClosureError):
        m.assert_no_other_ssh_sessions(tmp_path)


def test_only_operator_ancestry_is_excluded_from_ssh_checks(tmp_path):
    m = load()
    current = tmp_path / str(os.getpid())
    current.mkdir()
    (current / "stat").write_text(f"{os.getpid()} (python) S 99999998 0 0")
    parent = tmp_path / "99999998"
    parent.mkdir()
    (parent / "stat").write_text("99999998 (sshd) S 1 0 0")
    (parent / "cmdline").write_bytes(b"sshd: root@notty\0")
    m.assert_no_other_ssh_sessions(tmp_path)


def test_local_cli_is_not_a_canonical_root_bypass():
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(Path(__file__).with_name("review_maintenance_retirement.py")),
                             "--sha", "b" * 40, "--release-sha", "a" * 40, "--operation-id", "c" * 32,
                             "--accept-unknown-review-writes"], input="synthetic-private-token", capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "synthetic-private-token" not in result.stderr
    assert "preserve all evidence" in result.stderr


def test_invalid_cli_arguments_do_not_echo_values():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("review_maintenance_retirement.py")),
                             "--sha", "b" * 40, "--release-sha", "a" * 40, "--unknown", "synthetic-secret"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert "synthetic-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize("invalid", ["extra", "boolean_count", "missing_table", "raw_health", "false_success", "unkeyed"])
def test_account_proof_schema_rejects_untrusted_summary(invalid):
    m = load()
    account = {"verification": "CURRENT_ACCOUNT_ONLY_NOT_RESET", "account_hmac_sha256": "a" * 64,
               "tables": {n: {"count": 1, "rows_hmac_sha256": "b" * 64} for n in (*m.DIRECT_TABLES, *m.CHILD_TABLES)}}
    m.validate_account_summary(account)
    if invalid == "extra": account["extra"] = True
    elif invalid == "boolean_count": account["tables"]["user_profiles"]["count"] = True
    elif invalid == "missing_table": del account["tables"]["medical_exam_items"]
    elif invalid == "raw_health": account["tables"]["medical_exam_items"]["rows"] = ["private"]
    elif invalid == "false_success": account["verification"] = "PASS"
    else: account["account_hmac_sha256"] = "review@example.invalid"
    with pytest.raises(m.ClosureError):
        m.validate_account_summary(account)


def real_file_adapter(tmp_path, monkeypatch):
    """Actual writes/renames and original receipts; OS root/proc probes stubbed."""
    import stat
    from types import SimpleNamespace
    path = Path(__file__).with_name("test_contained_release_retirement.py")
    spec = importlib.util.spec_from_file_location("shared_closure_file_fixture", path)
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    c, old_adapter, b, r, _ = helpers.proof_fixture(tmp_path, monkeypatch)
    m = load()
    old, closing, operation_id = "a" * 40, "b" * 40, "c" * 32
    workspace = b.STATE / old
    for name, state in (("started.json", "STARTED"), ("completed.json", "SUCCEEDED")):
        (workspace / name).write_text(json.dumps({"sha": old, "state": state}))
    operation = workspace / "review-resets" / operation_id
    operation.parent.mkdir(mode=0o700)
    operation.mkdir(mode=0o700)
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR")):
        m.write_json(operation / name, {"sha": old, "operation_id": operation_id, "state": state})
    for name in m.CANONICAL_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"canonical executor")
    policy = {"sha": old, "expires_at": 100, "executor_sha256": hashlib.sha256(b"canonical executor").hexdigest()}
    (b.CONFIG / "authorized-release.json").write_text(json.dumps(policy))
    a = m.Adapter.__new__(m.Adapter)
    a.source, a.b = tmp_path, b
    a.server = SimpleNamespace(validate_policy=lambda value, **kwargs: value)
    a.sha, a.old_sha, a.operation_id, a.token = closing, old, operation_id, "synthetic-token"
    a.record = b.STATE / "review-maintenance-closures" / old
    a.volatile = tmp_path / "archived-original-lease"
    a.c, a.r = c, r
    a.reset = SimpleNamespace(_revision_proof=lambda *args: None)
    lease = old_adapter.proof.lease
    (lease / "label").write_bytes(b"deploy:app-store-review-reset\n")
    (lease / "stage").write_bytes(b"/tmp/health-app-backup-preflight-123456789-987654321\n")
    def directory(path):
        info = path.lstat()
        return {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
    a.p = SimpleNamespace(lease=lease, _directory=directory,
                          _file=lambda path, *args: old_adapter.proof._file(path),
                          running_services_snapshot=lambda: {"stable": True})
    a.check = lambda: None
    a._quiescent = lambda: None
    a._services = lambda: {"stable": True}
    account = {"verification": "CURRENT_ACCOUNT_ONLY_NOT_RESET", "account_hmac_sha256": "a" * 64,
               "tables": {n: {"count": 1, "rows_hmac_sha256": "b" * 64} for n in (*m.DIRECT_TABLES, *m.CHILD_TABLES)}}
    a.inspect_account = lambda: copy.deepcopy(account)
    original_load = m.load
    monkeypatch.setattr(m, "load", lambda path, name: c if name == "review_history_file_helpers" else original_load(path, name))
    return m, a, b, operation


def test_real_files_preserve_unknown_revoke_exact_keys_and_verify_history(tmp_path, monkeypatch):
    m, a, b, operation = real_file_adapter(tmp_path, monkeypatch)
    original = {p.name: p.read_bytes() for p in operation.iterdir()}
    lease_inode = a.p.lease.stat().st_ino
    fingerprint = m.close_transaction(a, accept_unknown=True)["evidence_sha256"]
    result = m.close_transaction(a, accept_unknown=True, evidence_sha256=fingerprint)
    assert result["state"] == m.TERMINAL
    assert b.AUTHORIZED.read_bytes() == b"unrelated\n"
    assert not (b.CONFIG / "loopback.key").exists()
    assert not a.p.lease.exists()
    assert a.volatile.stat().st_ino == lease_inode
    assert {p.name: p.read_bytes() for p in operation.iterdir()} == original
    proof = m.closed_evidence(b, a.old_sha, result["receipt"])
    assert proof["original_outcome"] == "UNKNOWN"
    assert proof["operation_id"] == a.operation_id
    # Historical proof survives service/PID changes and actual retirement.
    a._services = lambda: (_ for _ in ()).throw(AssertionError("history must not read current services"))
    config, library = b._archives(a.old_sha)
    os.rename(b.CONFIG, config)
    os.rename(b.INSTALLED.parent, library)
    b._installation_evidence = lambda sha, config, library: {
        "config": b._inventory(config, {p.name for p in config.iterdir()}),
        "library": b._inventory(library, {b.INSTALLED.name})}
    assert m.closed_evidence(b, a.old_sha, result["receipt"]) == proof


@pytest.mark.parametrize("point", ["original", "archive", "account_key", "completed", "canonical", "receipt", "extra_operation"])
def test_closed_history_refuses_any_tampering(tmp_path, monkeypatch, point):
    m, a, b, operation = real_file_adapter(tmp_path, monkeypatch)
    fingerprint = m.close_transaction(a, accept_unknown=True)["evidence_sha256"]
    result = m.close_transaction(a, accept_unknown=True, evidence_sha256=fingerprint)
    receipt = result["receipt"]
    if point == "original": (operation / "completed.json").write_text("{}")
    elif point == "archive": (a.record / "lease/token").write_text("changed")
    elif point == "account_key": (a.record / "account-hmac.key").write_bytes(b"x" * 32)
    elif point == "completed": (a.record / "completed.json").write_text("{}")
    elif point == "canonical": (tmp_path / "deploy.sh").write_text("changed")
    elif point == "receipt": receipt = "0" * 64
    else: (operation.parent / ("d" * 32)).mkdir(mode=0o700)
    with pytest.raises((m.ClosureError, a.c.ClosureError)):
        m.closed_evidence(b, a.old_sha, receipt)


@pytest.mark.parametrize("failure", ["archive_copy", "revocation", "private_key", "session", "rename", "post_account"])
def test_real_transaction_failures_never_make_failed_reset_success(tmp_path, monkeypatch, failure):
    m, a, b, operation = real_file_adapter(tmp_path, monkeypatch)
    fingerprint = m.close_transaction(a, accept_unknown=True)["evidence_sha256"]
    original = (operation / "completed.json").read_bytes()
    def fail(*args, **kwargs): raise OSError("injected operator boundary")
    if failure == "archive_copy": a._copy_archives = fail
    elif failure == "revocation": b._replace_authorized = fail
    elif failure == "private_key":
        unlink = Path.unlink
        monkeypatch.setattr(Path, "unlink", lambda p, *args, **kwargs: fail() if p.name == "loopback.key" else unlink(p, *args, **kwargs))
    elif failure == "session":
        a._quiescent = lambda: fail() if b.AUTHORIZED.read_bytes() == b"unrelated\n" else None
    elif failure == "rename": a.c._move_no_clobber = fail
    else:
        count = [0]
        account = a.inspect_account
        def changing_account():
            count[0] += 1
            value = account()
            if count[0] > 1: value["account_hmac_sha256"] = "c" * 64
            return value
        a.inspect_account = changing_account
    with pytest.raises((OSError, m.ClosureError)):
        m.close_transaction(a, accept_unknown=True, evidence_sha256=fingerprint)
    assert (operation / "completed.json").read_bytes() == original
    assert (a.record / "intent.json").is_file()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, accept_unknown=True, evidence_sha256=fingerprint)


@pytest.mark.parametrize("retirement", ["matching", "missing", "wrong_operation", "wrong_state", "wrong_outcome"])
def test_future_reset_accepts_only_exact_retired_unknown_operation(tmp_path, monkeypatch, retirement):
    from types import SimpleNamespace
    path = Path(__file__).with_name("trusted_review_reset.py")
    spec = importlib.util.spec_from_file_location("review_history_guard_test", path)
    reset = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reset)
    old, operation_id = "a" * 40, "b" * 32
    operation = tmp_path / old / "review-resets" / operation_id
    operation.mkdir(parents=True, mode=0o700)
    operation.parent.chmod(0o700)
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR")):
        (operation / name).write_text(json.dumps({"sha": old, "operation_id": operation_id, "state": state}))
        (operation / name).chmod(0o600)
    closed = {"state": "CLOSED_UNKNOWN_REVIEW_MAINTENANCE", "operation_id": operation_id, "original_outcome": "UNKNOWN"}
    if retirement == "wrong_operation": closed["operation_id"] = "c" * 32
    if retirement == "wrong_state": closed["state"] = "SUCCEEDED"
    if retirement == "wrong_outcome": closed["original_outcome"] = "SUCCEEDED"
    b = SimpleNamespace(_read_json=lambda p: json.loads(p.read_bytes()),
                        _retired_history=lambda: {} if retirement == "missing" else {old: {"workspace": closed}})
    server = SimpleNamespace(secure_path=lambda *args, **kwargs: None)
    monkeypatch.setattr(reset, "STATE", tmp_path)
    if retirement == "matching":
        reset._assert_previous_resets(b, server)
        assert json.loads((operation / "completed.json").read_text())["state"] == "NEEDS_OPERATOR"
    else:
        with pytest.raises(reset.ResetError):
            reset._assert_previous_resets(b, server)


def test_ci_keeps_postgresql_closure_probe_on_real_database():
    import yaml
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["agent-runtime-postgres"]
    assert "postgres" in job["services"]
    step = next(s for s in job["steps"] if s.get("name") == "Verify isolated review closure PostgreSQL boundary")
    assert step["env"]["REVA_REVIEW_CLOSURE_TEST_DATABASE_URL"].startswith("postgresql://")
    assert "scripts/test_review_maintenance_retirement.py -k postgres" in step["run"]


@pytest.mark.parametrize("case", ["backend_failed", "already_success", "other_unknown", "extra_workspace", "incomplete_phase", "wrong_label", "wrong_token", "wrong_stage"])
def test_invalid_original_state_cannot_consume_closure(tmp_path, monkeypatch, case):
    m, a, b, operation = real_file_adapter(tmp_path, monkeypatch)
    workspace = b.STATE / a.old_sha
    if case == "backend_failed":
        (workspace / "completed.json").write_text(json.dumps({"sha": a.old_sha, "state": "NEEDS_OPERATOR"}))
    elif case == "already_success":
        (operation / "completed.json").write_text(json.dumps({"sha": a.old_sha, "operation_id": a.operation_id, "state": "SUCCEEDED"}))
    elif case == "other_unknown":
        other = operation.parent / ("d" * 32)
        other.mkdir(mode=0o700)
        for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR")):
            m.write_json(other / name, {"sha": a.old_sha, "operation_id": other.name, "state": state})
    elif case == "extra_workspace": m.write_bytes(workspace / "unknown", b"unknown")
    elif case == "incomplete_phase": m.write_json(workspace / "prepared.json", {"sha": a.old_sha, "state": "PREPARED"})
    elif case == "wrong_label": (a.p.lease / "label").write_bytes(b"deploy:backend\n")
    elif case == "wrong_token": (a.p.lease / "token").write_bytes(b"not-original\n")
    else: (a.p.lease / "stage").write_bytes(b"/unexpected/path\n")
    with pytest.raises((m.ClosureError, a.c.ClosureError)):
        m.close_transaction(a, accept_unknown=True)
    assert not a.record.exists()
    assert (b.CONFIG / "loopback.key").exists()
    assert b.AUTHORIZED.read_bytes() == b"unrelated\ncloud exact\nloopback exact\n"
