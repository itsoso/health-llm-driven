"""Synthetic production adapter tests; no real demo or production access."""
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name('trusted_review_briefing_repair.py')
    spec = importlib.util.spec_from_file_location('trusted_briefing_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_context_required():
    m = load()
    with pytest.raises(m.BriefingError):
        m.context('a' * 40)


def modules():
    m = load()
    root = Path(__file__).resolve().parents[1]
    core = m.load(root / 'scripts/review_demo_briefing_repair.py', 'test_briefing_core')
    ack = m.load(root / 'scripts/review_maintenance_acknowledgement.py', 'test_briefing_ack')
    return m, core, ack


def evidence(core):
    return {'target_sha': core.TARGET, 'failed_operation': core.FAILED_OPERATION,
            'fixture_sha256': core.FIXTURE_SHA256, 'action': core.ACTION,
            'acknowledgement_sha256': 'a' * 64, 'production_evidence_sha256': 'b' * 64,
            'database_snapshot_sha256': 'c' * 64, 'health_snapshot_sha256': 'd' * 64,
            'demo_user_id': 44}


class Transaction:
    def __init__(self, events, fail_commit=False):
        self.events, self.is_active, self.fail_commit = events, True, fail_commit
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.is_active = False
    def commit(self):
        self.events.append('commit')
        self.is_active = False
        if self.fail_commit:
            raise OSError('ambiguous response')
    def rollback(self):
        self.events.append('rollback')
        self.is_active = False


class Engine:
    def __init__(self, fail_commit=False):
        self.events, self.fail_commit = [], fail_commit
    def connect(self):
        engine = self
        class Connection:
            def __enter__(self):
                engine.events.append('connect')
                return self
            def __exit__(self, *args):
                engine.events.append('close')
            def begin(self):
                return Transaction(engine.events, engine.fail_commit)
            def exec_driver_sql(self, sql):
                engine.events.append(sql)
        return Connection()


def database_stubs(monkeypatch, m, core, engine, *, health_values=None, readback_fail=False):
    from types import SimpleNamespace
    counts = iter(health_values or ['d' * 64] * 3)
    monkeypatch.setattr(m, 'assert_insert_surface', lambda conn: engine.events.append('surface'))
    monkeypatch.setattr(m, 'health_snapshot', lambda *args: next(counts))
    def create(conn, email, uid, before, fixture):
        assert uid == 44 and before == 'c' * 64
        engine.events.append('insert')
        return {'state': 'VERIFIED_BRIEFING_ONLY', 'before_sha256': before, 'after_sha256': 'e' * 64}
    def verify(*args):
        engine.events.append('readback')
        assert engine.events.count('commit') == 1
        if readback_fail:
            raise ValueError('readback failed')
    monkeypatch.setattr(core, 'create_briefing_rows', create)
    monkeypatch.setattr(core, 'verify_created_briefing_rows', verify)
    return SimpleNamespace()


def test_database_commits_once_then_uses_fresh_readback(monkeypatch):
    m, core, ack = modules()
    engine = Engine()
    readers = database_stubs(monkeypatch, m, core, engine)
    result = m.database_work(engine, core, readers, 'synthetic@example.invalid', Path('/fixture'), b'x' * 32,
                             evidence=evidence(core))
    assert result['state'] == 'VERIFIED_BRIEFING_ONLY'
    assert engine.events.count('commit') == 1
    assert engine.events.count('connect') == 2
    assert engine.events.index('insert') < engine.events.index('commit') < engine.events.index('readback')
    assert any(sql.startswith('LOCK TABLE public.agent_conversations') for sql in engine.events)


def test_health_side_effect_rolls_back_before_commit(monkeypatch):
    m, core, ack = modules()
    engine = Engine()
    readers = database_stubs(monkeypatch, m, core, engine, health_values=['d' * 64, 'f' * 64])
    with pytest.raises(m.BriefingError, match='within repair'):
        m.database_work(engine, core, readers, 'synthetic@example.invalid', Path('/fixture'), b'x' * 32,
                        evidence=evidence(core))
    assert engine.events.count('rollback') == 1
    assert 'commit' not in engine.events


def test_uncertain_commit_never_replays_or_claims_success(monkeypatch):
    m, core, ack = modules()
    engine = Engine(fail_commit=True)
    readers = database_stubs(monkeypatch, m, core, engine)
    with pytest.raises(OSError):
        m.database_work(engine, core, readers, 'synthetic@example.invalid', Path('/fixture'), b'x' * 32,
                        evidence=evidence(core))
    assert engine.events.count('commit') == engine.events.count('insert') == 1
    assert 'readback' not in engine.events


def test_failed_readback_never_retries(monkeypatch):
    m, core, ack = modules()
    engine = Engine()
    readers = database_stubs(monkeypatch, m, core, engine, readback_fail=True)
    with pytest.raises(ValueError):
        m.database_work(engine, core, readers, 'synthetic@example.invalid', Path('/fixture'), b'x' * 32,
                        evidence=evidence(core))
    assert engine.events.count('commit') == engine.events.count('insert') == 1


def test_postcommit_health_drift_rejected(monkeypatch):
    m, core, ack = modules()
    engine = Engine()
    readers = database_stubs(monkeypatch, m, core, engine, health_values=['d' * 64, 'd' * 64, 'f' * 64])
    with pytest.raises(m.BriefingError, match='post-commit'):
        m.database_work(engine, core, readers, 'synthetic@example.invalid', Path('/fixture'), b'x' * 32,
                        evidence=evidence(core))
    assert engine.events.count('commit') == 1


@pytest.mark.parametrize('change', [None, 'operator', 'terminal', 'unblocked', 'digest'])
def test_acknowledgement_must_be_same_operator_and_no_authority(tmp_path, change):
    from types import SimpleNamespace
    m, core, ack = modules()
    sha = 'f' * 40
    source_evidence = {'closing_sha': sha, 'old_sha': m.TARGET, 'operation_id': m.OPERATION,
                       'original_outcome': 'UNKNOWN'}
    intent = {'evidence': source_evidence, 'accept_unknown_review_writes': True,
              'original_outcome': 'UNKNOWN', 'evidence_sha256': ack.digest(source_evidence)}
    complete = {'state': ack.TERMINAL, 'original_outcome': 'UNKNOWN',
        'evidence_sha256': ack.digest(source_evidence), 'reset_authorized': False,
        'release_unblocked': False, 'historical_no_write_proven': False,
        'authority': {'reset': False, 'retry': False, 'rotation': False, 'deployment': False}, 'account': {}}
    if change == 'operator':
        source_evidence['closing_sha'] = 'a' * 40
    elif change == 'terminal':
        complete['state'] = 'SUCCEEDED'
    elif change == 'unblocked':
        complete['release_unblocked'] = True
    elif change == 'digest':
        complete['evidence_sha256'] = 'a' * 64
    b = SimpleNamespace(_inventory=lambda *args: {'completed.json': {'sha256': 'a' * 64}},
                        _read_json=lambda p: intent if p.name == 'intent.json' else complete)
    readers = SimpleNamespace(validate_account_summary=lambda value: None)
    if change is None:
        assert m.acknowledgement_evidence(b, readers, ack, sha)['completed_sha256'] == 'a' * 64
    else:
        with pytest.raises(m.BriefingError):
            m.acknowledgement_evidence(b, readers, ack, sha)


def test_child_cli_cannot_receive_github_token_or_bypass_authorization(monkeypatch):
    import sys
    m = load()
    monkeypatch.setattr(sys, 'argv', ['repair', '--sha', 'a' * 40, '--database-probe', 'apply', '--token-stdin'])
    monkeypatch.setattr(m, 'database_child', lambda *args: pytest.fail('must not call child'))
    assert m.main() == 1


def test_real_adapter_readonly_inspection_and_authorized_one_shot(tmp_path, monkeypatch):
    """Actual wrapper/ack construction and core state machine; OS/DB stubs only."""
    from types import SimpleNamespace
    m, core, ack = modules()
    root = Path(__file__).resolve().parents[1]
    readers = m.load(root / 'scripts/review_maintenance_retirement.py', 'wrapper_real_readers')
    m.STATE = tmp_path
    sha = 'f' * 40
    receipt = {'completed_sha256': 'a' * 64, 'inventory': {'synthetic': True}}
    b = SimpleNamespace(STATE=tmp_path, secure=lambda *args, **kwargs: None,
                        _read_json=lambda path: json.loads(path.read_text()))
    actual_make = ack.make_adapter
    guards = []
    def make(*args):
        guard = actual_make(*args)
        monkeypatch.setattr(guard, 'inspect', lambda: {'production': 'stable'})
        monkeypatch.setattr(guard, '_quiescent', lambda: None)
        monkeypatch.setattr(guard.c, '_private_directory', lambda *args: None)
        guards.append(guard)
        return guard
    monkeypatch.setattr(ack, 'make_adapter', make)
    monkeypatch.setattr(m, 'acknowledgement_evidence', lambda *args: receipt)
    subprocess_calls = []
    def run(argv, **kwargs):
        assert '--token-stdin' not in argv
        assert kwargs['env'] == m.ENV
        mode = argv[argv.index('--database-probe') + 1]
        subprocess_calls.append(mode)
        assert len(kwargs['pass_fds']) == 3
        if mode == 'inspect':
            value = {'demo_user_id': 44, 'database_snapshot_sha256': 'c' * 64,
                     'health_snapshot_sha256': 'd' * 64}
        else:
            value = {'state': 'VERIFIED_BRIEFING_ONLY', 'before_sha256': 'c' * 64, 'after_sha256': 'e' * 64}
        return SimpleNamespace(stdout=json.dumps(value).encode())
    monkeypatch.setattr(m.subprocess, 'run', run)
    monkeypatch.setattr(m, 'parent_identity', lambda pid: {'pid': pid, 'start_ticks': '1234'})
    adapter = m.make_adapter(root, b, object(), readers, ack, core, sha, lambda: None, launcher_fd=100, build_fd=101)
    result = core.repair(adapter)
    assert result['state'] == 'INSPECTED_NOT_AUTHORIZED'
    assert not adapter.record.exists() and 'apply' not in subprocess_calls
    terminal = core.repair(adapter, authorized=True, evidence_sha256=result['evidence_sha256'])
    assert terminal['state'] == 'BRIEFING_REPAIRED_ONLY'
    assert terminal['release_unblocked'] is False
    assert subprocess_calls.count('apply') == 1
    intent = json.loads((adapter.record / 'intent.json').read_text())
    assert intent['operator_sha'] == sha and intent['accept_demo_briefing_repair'] is True
    assert intent['evidence']['demo_user_id'] == 44
    with pytest.raises(core.RepairError, match='no retry'):
        core.repair(adapter, authorized=True, evidence_sha256=result['evidence_sha256'])
    assert subprocess_calls.count('apply') == 1


@pytest.mark.parametrize('rows', [[], [('agent_conversations', 'r', True, False, False), ('agent_messages', 'r', False, False, False)],
                                [('agent_conversations', 'v', False, False, False), ('agent_messages', 'r', False, False, False)],
                                [('agent_conversations', 'r', False, True, False), ('agent_messages', 'r', False, False, False)]])
def test_unreviewed_insert_surface_is_blocked(rows):
    from types import SimpleNamespace
    m = load()
    connection = SimpleNamespace(execute=lambda query: SimpleNamespace(all=lambda: rows))
    with pytest.raises(m.BriefingError):
        m.assert_insert_surface(connection)


@pytest.fixture
def pg_adapter():
    """A random disposable database on an explicitly supplied synthetic cluster."""
    import os
    import uuid
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    url = os.environ.get('REVA_REVIEW_CLOSURE_TEST_DATABASE_URL')
    if not url:
        pytest.skip('dedicated PostgreSQL integration URL required')
    parsed = make_url(url)
    # This fixture creates only a new synthetic database; never adopt public
    # tables in a supplied database or a remote/production server.
    if parsed.host not in (None, '', 'localhost', '127.0.0.1') or not str(parsed.query.get('host', '')).startswith('/tmp/reva-'):
        pytest.fail('dedicated local Unix-socket test cluster required')
    name = 'briefing_adapter_' + uuid.uuid4().hex
    control = create_engine(url, isolation_level='AUTOCOMMIT')
    with control.connect() as c:
        c.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(parsed.set(database=name), isolation_level='SERIALIZABLE')
    m, core, ack = modules()
    root = Path(__file__).resolve().parents[1]
    readers = m.load(root / 'scripts/review_maintenance_retirement.py', 'pg_adapter_readers')
    fixture = root / 'backend/fixtures/demo_user_minimal.json'
    try:
        with engine.begin() as c:
            c.execute(text('CREATE TABLE public.users (id SERIAL PRIMARY KEY, email TEXT UNIQUE, is_active BOOLEAN, is_approved BOOLEAN, is_admin BOOLEAN)'))
            c.execute(text('CREATE TABLE public.agent_conversations (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), title TEXT, session_key TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)'))
            c.execute(text('CREATE TABLE public.agent_messages (id SERIAL PRIMARY KEY, conversation_id INTEGER REFERENCES agent_conversations(id), role TEXT, content TEXT, image_url TEXT, meta JSONB, created_at TIMESTAMP)'))
            c.execute(text("INSERT INTO users VALUES (1,'review@example.invalid',true,true,false),(2,'other@example.invalid',true,true,false)"))
            c.execute(text("INSERT INTO agent_conversations(user_id,title,session_key,created_at,updated_at) VALUES (1,'old','old',now()-interval '1 day',now()-interval '1 day'),(2,'other','other',now()-interval '1 day',now()-interval '1 day')"))
            c.execute(text("INSERT INTO agent_messages(conversation_id,role,content,created_at) VALUES(1,'user','old content',now()),(2,'user','other content',now())"))
            for table in readers.DIRECT_TABLES:
                if table == 'agent_conversations':
                    continue
                c.execute(text(f'CREATE TABLE public.{table} (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), payload JSONB)'))
                c.execute(text(f'INSERT INTO public.{table} VALUES (1,1,\'{{"synthetic":"demo"}}\'),(2,2,\'{{"synthetic":"other"}}\')'))
            for table, (fk, parent) in readers.CHILD_TABLES.items():
                if table == 'agent_messages':
                    continue
                c.execute(text(f'CREATE TABLE public.{table} (id INTEGER PRIMARY KEY, {fk} INTEGER REFERENCES public.{parent}(id), payload JSONB)'))
                c.execute(text(f'INSERT INTO public.{table} VALUES (1,1,\'{{"synthetic":"demo-child"}}\'),(2,2,\'{{"synthetic":"other-child"}}\')'))
        yield m, core, readers, engine, fixture
    finally:
        engine.dispose()
        with control.connect() as c:
            c.execute(text('DROP DATABASE ' + name))
        control.dispose()


def test_postgres_actual_database_work_public_schema(pg_adapter):
    from sqlalchemy import text
    m, core, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32)
    before = evidence(core)
    before.update(observed)
    result = m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32, evidence=before)
    assert result['state'] == 'VERIFIED_BRIEFING_ONLY'
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 3
        assert c.execute(text('SELECT count(*) FROM agent_messages')).scalar_one() == 4
        assert c.execute(text("SELECT content FROM agent_messages WHERE id=2")).scalar_one() == 'other content'
        assert m.health_snapshot(c, 1, b'k' * 32, readers) == before['health_snapshot_sha256']
    with pytest.raises(core.RepairError, match='already exists'):
        m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32)


def test_postgres_trigger_blocks_before_any_insert(pg_adapter):
    from sqlalchemy import text
    m, core, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32)
    before = evidence(core)
    before.update(observed)
    with engine.begin() as c:
        c.execute(text("CREATE FUNCTION unwanted() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE weight_records SET payload='{}'::jsonb; RETURN NEW; END $$"))
        c.execute(text('CREATE TRIGGER unwanted BEFORE INSERT ON agent_conversations FOR EACH ROW EXECUTE FUNCTION unwanted()'))
    with pytest.raises(m.BriefingError, match='unreviewed'):
        m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32, evidence=before)
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 2
        assert m.health_snapshot(c, 1, b'k' * 32, readers) == before['health_snapshot_sha256']


def test_postgres_email_reassignment_does_not_change_bound_owner(pg_adapter):
    from sqlalchemy import text
    m, core, readers, engine, fixture = pg_adapter
    observed = m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32)
    before = evidence(core)
    before.update(observed)
    with engine.begin() as c:
        c.execute(text("UPDATE users SET email='old-review@example.invalid' WHERE id=1"))
        c.execute(text("UPDATE users SET email='review@example.invalid' WHERE id=2"))
    with pytest.raises(core.RepairError, match='review identity'):
        m.database_work(engine, core, readers, 'review@example.invalid', fixture, b'k' * 32, evidence=before)
    with engine.begin() as c:
        assert c.execute(text('SELECT count(*) FROM agent_conversations')).scalar_one() == 2


@pytest.mark.parametrize('missing', [(None, None, None), (3, None, 5), (3, 3, 5), (0, 4, 5)])
def test_child_without_distinct_inherited_proof_fails(missing):
    m = load()
    with pytest.raises(m.BriefingError, match='inherited'):
        m.validate_parent_proof(Path('/canonical'), 'a' * 40, 'apply', *missing, object())


@pytest.mark.parametrize('change', [None, 'holder', 'start', 'exe', 'argv', 'uid', 'nonce', 'old_intent'])
def test_parent_proof_binds_real_parent_start_fds_and_lock_owner(tmp_path, monkeypatch, change):
    import hashlib
    import os
    from types import SimpleNamespace
    m, core, ack = modules()
    proc = tmp_path / 'proc'
    parent = proc / '900'
    parent.mkdir(parents=True)
    (parent / 'fd').mkdir()
    fields = ['S', '1', '1', '1', '0'] + ['0'] * 14 + ['1234']
    (parent / 'stat').write_text('900 (python) ' + ' '.join(fields))
    (parent / 'status').write_text('Uid:\t0\t0\t0\t0\n')
    source = tmp_path / 'canonical'
    sha = 'a' * 40
    argv = ['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_review_briefing_repair.py'), '--sha', sha]
    (parent / 'cmdline').write_bytes(b'\0'.join(item.encode() for item in argv) + b'\0')
    (parent / 'exe').symlink_to('/usr/bin/python3.12')
    launcher, build = tmp_path / 'launcher', tmp_path / 'build'
    launcher.write_text('')
    build.write_text('')
    lfd, bfd = os.open(launcher, os.O_RDWR), os.open(build, os.O_RDWR)
    read_fd, write_fd = os.pipe()
    try:
        for fd, path in ((lfd, launcher), (bfd, build)):
            (parent / 'fd' / str(fd)).symlink_to(path)
        lock_lines = []
        for n, fd in enumerate((lfd, bfd)):
            info = os.fstat(fd)
            lock_lines.append(f'{n}: FLOCK ADVISORY WRITE {901 if change == "holder" else 900} {os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino} 0 EOF')
        (proc / 'locks').write_text('\n'.join(lock_lines))
        proof = {'parent': {'pid': 900, 'start_ticks': '1234'}, 'nonce': 'c' * 64,
                 'sha': sha, 'mode': 'apply', 'evidence_sha256': core.digest(evidence(core))}
        if change == 'start':
            proof['parent']['start_ticks'] = '9999'
        elif change == 'exe':
            (parent / 'exe').unlink()
            (parent / 'exe').symlink_to('/usr/bin/python3.11')
        elif change == 'argv':
            (parent / 'cmdline').write_bytes(b'python\0-c\0unrelated\0')
        elif change == 'uid':
            (parent / 'status').write_text('Uid:\t1000\t1000\t1000\t1000\n')
        elif change == 'nonce':
            proof['nonce'] = 'invalid'
        os.write(write_fd, json.dumps(proof).encode())
        os.close(write_fd)
        write_fd = None
        real_fstat = os.fstat
        def root_pipe(fd):
            info = real_fstat(fd)
            if fd == read_fd:
                return SimpleNamespace(st_mode=info.st_mode, st_uid=0)
            return info
        monkeypatch.setattr(m.os, 'fstat', root_pipe)
        monkeypatch.setattr(m.os, 'getppid', lambda: 900)
        b = SimpleNamespace(_assert_original_lock=lambda path, fd: None)
        if change not in (None, 'old_intent'):
            with pytest.raises(m.BriefingError):
                m.validate_parent_proof(source, sha, 'apply', read_fd, lfd, bfd, b, proc)
        else:
            verified = m.validate_parent_proof(source, sha, 'apply', read_fd, lfd, bfd, b, proc)
            value = evidence(core)
            intent = {'operator_sha': sha, 'accept_demo_briefing_repair': True,
                'evidence': value, 'evidence_sha256': core.digest(value),
                'parent_binding': {**proof['parent'], 'nonce_sha256': hashlib.sha256(('d' * 64 if change == 'old_intent' else proof['nonce']).encode()).hexdigest()}}
            if change == 'old_intent':
                with pytest.raises(m.BriefingError, match='fresh'):
                    m.validate_apply_intent(intent, verified, sha, core, tmp_path)
            else:
                assert m.validate_apply_intent(intent, verified, sha, core, tmp_path) == value
    finally:
        for fd in (lfd, bfd, read_fd, write_fd):
            if fd is not None:
                os.close(fd)
