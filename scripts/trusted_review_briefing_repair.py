"""Canonical one-shot addition of the fixed Store 279 demo briefing.

Independent explicit authorization, never an UNKNOWN reset retry or release
unblock. Default inspection is read-only. Original receipts/data are retained.
"""
import argparse
import contextlib
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

STATE = Path('/var/lib/reva-release')
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}
TARGET = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
OPERATION = 'a71c3840b6f24bc79937d178cb838066'


class BriefingError(Exception):
    """Static secret-free diagnostics."""


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def context(sha, *, verify_ci=True, token_stdin=False):
    if (re.fullmatch('[a-f0-9]{40}', sha or '') is None or os.geteuid() != 0
            or sys.executable != '/usr/bin/python3.12' or not sys.flags.isolated
            or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or 'SSH_ORIGINAL_COMMAND' in os.environ):
        raise BriefingError('isolated canonical root operator required')
    source = STATE / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/trusted_review_briefing_repair.py'
    helper = source / 'scripts/review_maintenance_acknowledgement.py'
    if Path(__file__).absolute() != entry:
        raise BriefingError('canonical briefing entry required')
    for path in [*reversed(entry.parents), entry, helper]:
        info = path.lstat()
        file = path in (entry, helper)
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                or (file and info.st_nlink != 1)):
            raise BriefingError('unsafe canonical metadata')
    ack = load(helper, 'briefing_ack_readers')
    checked, b, server, readers = ack.context(sha, verify_ci=verify_ci, token_stdin=token_stdin)
    if checked != source:
        raise BriefingError('canonical source mismatch')
    core_path = source / 'scripts/review_demo_briefing_repair.py'
    b.secure(core_path)
    core = load(core_path, 'briefing_core')
    if (core.TARGET != TARGET or core.FAILED_OPERATION != OPERATION or core.SCHEMA != 'public'):
        raise BriefingError('fixed repair profile differs')
    return source, b, server, readers, ack, core


RECONCILIATION_PREDECESSOR = '2162488aedb9337690a9acc51d5e8f9ac28f4aec'
RECONCILIATION_PREDECESSOR_EVIDENCE = '30a9e7379398c1a50e96ff098620c3820b17c69315bb9bdf5dc960b6b077e9cb'
RECONCILIATION_PREDECESSOR_FILES = {'intent.json': {'identity': {'st_uid': 0, 'st_gid': 0, 'st_mode': 33152, 'st_nlink': 1, 'st_ino': 16661006, 'st_dev': 64513, 'st_size': 8464, 'st_mtime_ns': 1792469566602966751, 'st_ctime_ns': 1792469566602966751}, 'sha256': '01c7e87aea2f615e177fc778171a0db2c9b7582509bd872b9d7b25956e5b3a1d'}, 'completed.json': {'identity': {'st_uid': 0, 'st_gid': 0, 'st_mode': 33152, 'st_nlink': 1, 'st_ino': 16661007, 'st_dev': 64513, 'st_size': 2589, 'st_mtime_ns': 1792469735298761534, 'st_ctime_ns': 1792469735298761534}, 'sha256': 'e027e63f5d4dbdebc057dd9c31454f9d54f540c6ef59a1d7421a0f874bc65933'}}

def fixed_reconciliation_succession(record, inventory, sha, evidence, ack):
    if (re.fullmatch('[a-f0-9]{40}', sha or '') is None or sha in (TARGET, RECONCILIATION_PREDECESSOR)
            or evidence.get('closing_sha') != RECONCILIATION_PREDECESSOR
            or ack.digest(evidence) != RECONCILIATION_PREDECESSOR_EVIDENCE):
        raise BriefingError('fixed predecessor and distinct canonical successor required')
    for name, expected in RECONCILIATION_PREDECESSOR_FILES.items():
        info = (record / name).lstat()
        if ({field:getattr(info,field) for field in expected['identity']} != expected['identity']
                or inventory.get(name, {}).get('sha256') != expected['sha256']):
            raise BriefingError('immutable predecessor reconciliation changed')
    return {'predecessor_operator_sha':RECONCILIATION_PREDECESSOR, 'operator_sha':sha,
            'predecessor_evidence_sha256':RECONCILIATION_PREDECESSOR_EVIDENCE,
            'predecessor_files':RECONCILIATION_PREDECESSOR_FILES}


def acknowledgement_evidence(b, readers, ack, sha, *, allow_fixed_successor=False):
    record = STATE / 'review-maintenance-acknowledgements' / TARGET
    if os.path.lexists(STATE / 'review-maintenance-ack-reconciliations' / TARGET):
        failed_inventory, old_evidence = ack.failed_ack_evidence(b)
        record = STATE / 'review-maintenance-ack-reconciliations' / TARGET
        inventory = b._inventory(record, {'intent.json', 'completed.json'})
        intent, complete = (b._read_json(record / name) for name in ('intent.json', 'completed.json'))
        evidence = intent.get('evidence', {})
        succession = None
        if allow_fixed_successor and evidence.get('closing_sha') == RECONCILIATION_PREDECESSOR and sha != RECONCILIATION_PREDECESSOR:
            succession = fixed_reconciliation_succession(record, inventory, sha, evidence, ack)
        expected = {**old_evidence, 'closing_sha': RECONCILIATION_PREDECESSOR if succession else sha, 'failed_ack': failed_inventory}
        if (evidence != expected or intent.get('accept_unknown_review_writes') is not True
                or intent.get('original_outcome') != 'UNKNOWN'
                or intent.get('evidence_sha256') != ack.digest(expected)
                or complete.get('evidence_sha256') != ack.digest(expected)
                or complete.get('state') != ack.RECONCILED
                or complete.get('original_outcome') != 'UNKNOWN'
                or complete.get('authority') != {'reset': False, 'retry': False, 'rotation': False, 'deployment': False}
                or complete.get('reset_authorized') is not False
                or complete.get('release_unblocked') is not False
                or complete.get('historical_no_write_proven') is not False):
            raise BriefingError('fixed same-operator reconciliation required')
        readers.validate_account_summary(complete.get('account'))
        if b._inventory(record, {'intent.json', 'completed.json'}) != inventory:
            raise BriefingError('reconciliation changed during observation')
        return {'inventory': inventory, 'failed_ack': failed_inventory,
                'completed_sha256': inventory['completed.json']['sha256'],
                **({'succession':succession} if succession else {})}
    inventory = b._inventory(record, {'intent.json', 'completed.json'})
    intent, complete = (b._read_json(record / name) for name in ('intent.json', 'completed.json'))
    evidence = intent.get('evidence', {})
    if (intent.get('accept_unknown_review_writes') is not True or intent.get('original_outcome') != 'UNKNOWN'
            or evidence.get('closing_sha') != sha or evidence.get('old_sha') != TARGET
            or evidence.get('operation_id') != OPERATION or evidence.get('original_outcome') != 'UNKNOWN'
            or intent.get('evidence_sha256') != ack.digest(evidence)
            or complete.get('evidence_sha256') != ack.digest(evidence)
            or complete.get('state') != ack.TERMINAL or complete.get('original_outcome') != 'UNKNOWN'
            or complete.get('authority') != {'reset': False, 'retry': False, 'rotation': False, 'deployment': False}
            or complete.get('reset_authorized') is not False or complete.get('release_unblocked') is not False
            or complete.get('historical_no_write_proven') is not False):
        raise BriefingError('same-operator completed UNKNOWN acknowledgement required')
    readers.validate_account_summary(complete.get('account'))
    return {'inventory': inventory, 'completed_sha256': inventory['completed.json']['sha256']}


def record_path():
    return STATE / 'review-demo-briefing-repairs' / TARGET


SUCCESSOR_ATTEMPT = 'after-1e676eaa-intent-only-v1'


def attempt_binding(source, b, sha, attempt_profile):
    if attempt_profile == 'original':
        return None
    if attempt_profile != SUCCESSOR_ATTEMPT:
        raise BriefingError('unknown fixed attempt profile')
    path = source / 'scripts/review_briefing_unstarted_closure.py'
    b.secure(path)
    closure = load(path, 'briefing_unstarted_closure')
    return closure.closed_evidence(b, sha)


def attempt_record(b, attempt_profile):
    if attempt_profile == 'original':
        return record_path()
    if attempt_profile != SUCCESSOR_ATTEMPT:
        raise BriefingError('unknown fixed attempt profile')
    return b.STATE / 'review-demo-briefing-successors' / TARGET / SUCCESSOR_ATTEMPT


def make_adapter(source, b, server, readers, ack, core, sha, check, *, launcher_fd=None, build_fd=None, attempt_profile="original", successor_authorized=False):
    guard = ack.make_adapter(source, b, server, readers, sha, TARGET, OPERATION, check)
    class Adapter:
        record = attempt_record(b, attempt_profile)
        def __init__(self):
            self.parent_nonce = secrets.token_hex(32)
            self.parent_identity = parent_identity(os.getpid())

        def production(self):
            observed = guard.inspect()
            receipt = acknowledgement_evidence(b, readers, ack, sha, allow_fixed_successor=True)
            binding = attempt_binding(source, b, sha, attempt_profile)
            if binding is not None:
                receipt = {**receipt, 'unstarted_closure': binding}
            return observed, receipt

        def inspect(self):
            before, receipt = self.production()
            database = self.child('inspect')
            if self.production() != (before, receipt):
                raise BriefingError('production evidence changed during inspection')
            if set(database) != {'demo_user_id', 'database_snapshot_sha256', 'health_snapshot_sha256', 'ordering_metadata_plan'}:
                raise BriefingError('invalid database observation')
            value = {'target_sha': TARGET, 'failed_operation': OPERATION,
                     'fixture_sha256': core.FIXTURE_SHA256, 'action': core.ACTION,
                     'acknowledgement_sha256': receipt['completed_sha256'],
                     'production_evidence_sha256': ack.digest({'production': before, 'ack': receipt}),
                     **database}
            core.validate_evidence(value)
            return value

        def prepare_record(self):
            if attempt_profile != 'original' and successor_authorized is not True:
                raise BriefingError('separate explicit successor write authority required')
            if attempt_profile != 'original' and not self.record.parent.parent.exists():
                self.record.parent.parent.mkdir(mode=0o700)
                readers.sync(self.record.parent.parent.parent)
            if attempt_profile != 'original':
                guard.c._private_directory(b, self.record.parent.parent)
            if not self.record.parent.exists():
                self.record.parent.mkdir(mode=0o700)
                readers.sync(self.record.parent.parent)
            guard.c._private_directory(b, self.record.parent)
            self.record.mkdir(mode=0o700)
            readers.sync(self.record.parent)

        def write(self, name, value):
            if name not in {'intent.json', 'completed.json'}:
                raise BriefingError('invalid repair output')
            guard.c._private_directory(b, self.record)
            if name == 'intent.json':
                receipt = acknowledgement_evidence(b, readers, ack, sha, allow_fixed_successor=True)
                binding = attempt_binding(source, b, sha, attempt_profile)
                if binding is not None:
                    value = {**value, 'attempt_profile': attempt_profile, 'unstarted_closure': binding,
                             'accept_successor_briefing_attempt': True}
                if 'succession' in receipt:
                    value = {**value, 'reconciliation_succession':receipt['succession']}
                value = {**value, 'operator_sha': sha, 'accept_demo_briefing_repair': True,
                         'parent_binding': {**self.parent_identity,
                            'nonce_sha256': hashlib.sha256(self.parent_nonce.encode()).hexdigest()}}
            readers.write_json(self.record / name, value)

        def child(self, mode):
            if mode == 'apply' and attempt_profile != 'original' and successor_authorized is not True:
                raise BriefingError('separate explicit successor write authority required')
            guard._quiescent()
            if launcher_fd is None or build_fd is None:
                raise BriefingError('both original parent lock descriptors required')
            expected = None
            if mode == 'apply':
                expected = b._read_json(self.record / 'intent.json')['evidence_sha256']
            proof = {'parent': self.parent_identity, 'nonce': self.parent_nonce,
                     'sha': sha, 'mode': mode, 'evidence_sha256': expected}
            if attempt_profile != 'original':
                proof['attempt_profile'] = attempt_profile
            raw = json.dumps(proof, sort_keys=True).encode()
            if len(raw) > 4096:
                raise BriefingError('parent proof exceeds bound')
            read_fd, write_fd = os.pipe()
            try:
                if os.write(write_fd, raw) != len(raw):
                    raise BriefingError('parent proof pipe incomplete')
                os.close(write_fd)
                write_fd = None
                result = subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B',
                    str(source / 'scripts/trusted_review_briefing_repair.py'), '--sha', sha,
                    '--database-probe', mode, '--parent-proof-fd', str(read_fd),
                    '--publisher-lock-fd', str(launcher_fd), '--build-lock-fd', str(build_fd),
                    *(['--attempt-profile', attempt_profile] if attempt_profile != 'original' else [])],
                    env=ENV, stdin=subprocess.DEVNULL, pass_fds=(read_fd, launcher_fd, build_fd),
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180, check=True)
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
            guard._quiescent()
            if len(result.stdout) > 16384:
                raise BriefingError('database summary exceeds bound')
            return json.loads(result.stdout)

        def apply_once(self, evidence):
            before, receipt = self.production()
            if ack.digest({'production': before, 'ack': receipt}) != evidence['production_evidence_sha256']:
                raise BriefingError('production evidence changed before repair')
            result = self.child('apply')
            if self.production() != (before, receipt):
                raise BriefingError('production evidence changed after repair; do not retry')
            return result
    return Adapter()


def assert_insert_surface(connection):
    from sqlalchemy import text
    rows = connection.execute(text("SELECT c.relname, c.relkind, "
        "EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid=c.oid AND NOT t.tgisinternal AND t.tgenabled <> 'D'), "
        "EXISTS (SELECT 1 FROM pg_rewrite r WHERE r.ev_class=c.oid), c.relrowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relname IN ('agent_conversations','agent_messages')")).all()
    if (len(rows) != 2 or {row[0] for row in rows} != {'agent_conversations', 'agent_messages'}
            or any(row[1] != 'r' or row[2] is not False or row[3] is not False or row[4] is not False for row in rows)):
        raise BriefingError('fixed insert tables have unreviewed trigger rule or relation type')


def demo_identity(connection, email):
    from sqlalchemy import text
    rows = connection.execute(text('SELECT id FROM public.users WHERE email=:email AND is_active=true '
        'AND is_approved=true AND is_admin=false LIMIT 2'), {'email': email}).scalars().all()
    if len(rows) != 1 or type(rows[0]) is not int or rows[0] < 1:
        raise BriefingError('unique configured demo identity required')
    return rows[0]


def health_snapshot(connection, user_id, key, readers):
    """Only configured demo rows. Hashes are keyed; no payload leaves child."""
    from sqlalchemy import text
    if connection.dialect.name != 'postgresql' or len(key) != 32:
        raise BriefingError('PostgreSQL and private health fingerprint required')
    result, total = {}, 0
    direct = tuple(name for name in readers.DIRECT_TABLES if name != 'agent_conversations')
    children = {name: relation for name, relation in readers.CHILD_TABLES.items() if name != 'agent_messages'}
    for name in (*direct, *children):
        if name in children:
            fk, parent = children[name]
            condition = f'{fk} IN (SELECT id FROM public.{parent} WHERE user_id=:uid)'
        else:
            condition = 'user_id=:uid'
        rows = connection.execute(text(f'SELECT to_jsonb(t) FROM public.{name} t WHERE {condition} ORDER BY id LIMIT 10001'),
                                  {'uid': user_id}).scalars().all()
        if len(rows) > 10000:
            raise BriefingError('health snapshot count exceeds bound')
        raw = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
        total += len(raw)
        if total > 16_000_000:
            raise BriefingError('health snapshot bytes exceed bound')
        result[name] = hmac.new(key, name.encode() + b'\0' + raw, hashlib.sha256).hexdigest()
    return hmac.new(key, json.dumps(result, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def database_work(engine, core, readers, email, fixture, key, *, evidence=None):
    """The only commit is explicit, once. Never retry an uncertain response."""
    if evidence is None:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            uid = demo_identity(connection, email)
            snapshot = core.inspect_briefing_metadata(connection, email, uid)
            assert_insert_surface(connection)
            health = health_snapshot(connection, uid, key, readers)
            return {'demo_user_id': uid, **snapshot, 'health_snapshot_sha256': health}
    core.validate_evidence(evidence)
    uid = evidence['demo_user_id']
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET LOCAL lock_timeout = '2000ms'")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
            connection.exec_driver_sql('LOCK TABLE public.agent_conversations, public.agent_messages IN SHARE ROW EXCLUSIVE MODE')
            assert_insert_surface(connection)
            if health_snapshot(connection, uid, key, readers) != evidence['health_snapshot_sha256']:
                raise BriefingError('demo health snapshot changed before repair')
            result = core.create_briefing_rows(connection, email, uid,
                evidence['database_snapshot_sha256'], fixture,
                ordering_metadata_plan=evidence['ordering_metadata_plan'])
            if health_snapshot(connection, uid, key, readers) != evidence['health_snapshot_sha256']:
                raise BriefingError('demo health rows changed within repair')
            transaction.commit()
        except BaseException:
            # Rollback is only the current uncommitted DB transaction, not a
            # backup, historical restoration, or automatic retry.
            if transaction.is_active:
                transaction.rollback()
            raise
    with engine.connect() as connection, connection.begin():
        core.verify_created_briefing_rows(connection, email, uid, result['after_sha256'], fixture)
        if health_snapshot(connection, uid, key, readers) != evidence['health_snapshot_sha256']:
            raise BriefingError('post-commit demo health snapshot changed; no retry')
    return result


def parent_identity(pid, proc=Path('/proc')):
    raw = (proc / str(pid) / 'stat').read_bytes()
    fields = raw.rsplit(b')', 1)[-1].split()
    if len(raw) > 65536 or len(fields) < 20 or not fields[19].isdigit():
        raise BriefingError('parent process identity unavailable')
    return {'pid': pid, 'start_ticks': fields[19].decode()}


def validate_parent_proof(source, sha, mode, proof_fd, launcher_fd, build_fd, b, proc=Path('/proc'), *, attempt_profile='original'):
    fds = (proof_fd, launcher_fd, build_fd)
    if any(type(fd) is not int or fd < 3 for fd in fds) or len(set(fds)) != 3:
        raise BriefingError('distinct inherited parent proof descriptors required')
    info = os.fstat(proof_fd)
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid != 0:
        raise BriefingError('private inherited parent pipe required')
    raw = os.read(proof_fd, 4097)
    if not raw or len(raw) > 4096 or os.read(proof_fd, 1):
        raise BriefingError('bounded one-shot parent proof required')
    proof = json.loads(raw)
    expected_keys = {'parent', 'nonce', 'sha', 'mode', 'evidence_sha256'}
    if attempt_profile != 'original':
        if attempt_profile != SUCCESSOR_ATTEMPT:
            raise BriefingError('unknown parent attempt profile')
        expected_keys.add('attempt_profile')
    if (not isinstance(proof, dict) or set(proof) != expected_keys
            or (attempt_profile != 'original' and proof.get('attempt_profile') != attempt_profile)
            or proof['sha'] != sha or proof['mode'] != mode
            or not isinstance(proof['nonce'], str) or re.fullmatch('[a-f0-9]{64}', proof['nonce']) is None
            or (mode == 'apply' and re.fullmatch('[a-f0-9]{64}', proof['evidence_sha256'] or '') is None)
            or (mode == 'inspect' and proof['evidence_sha256'] is not None)):
        raise BriefingError('parent proof does not authorize this child')
    parent = os.getppid()
    if parent <= 1 or proof['parent'] != parent_identity(parent, proc):
        raise BriefingError('original canonical parent absent or replaced')
    entry = proc / str(parent)
    uid = [line.split()[1:] for line in (entry / 'status').read_bytes().splitlines() if line.startswith(b'Uid:')]
    if uid != [[b'0'] * 4]:
        raise BriefingError('canonical parent UID differs')
    if os.readlink(entry / 'exe') != '/usr/bin/python3.12':
        raise BriefingError('parent executable differs')
    argv_raw = (entry / 'cmdline').read_bytes()
    argv = argv_raw.rstrip(b'\0').split(b'\0')
    expected = [b'/usr/bin/python3.12', b'-I', b'-S', b'-B',
                str(source / 'scripts/trusted_review_briefing_repair.py').encode()]
    if (len(argv_raw) > 16384 or argv[:5] != expected or b'--database-probe' in argv
            or argv.count(b'--sha') != 1 or argv[argv.index(b'--sha') + 1:argv.index(b'--sha') + 2] != [sha.encode()]):
        raise BriefingError('parent is not the canonical CI-gated operator')
    if attempt_profile != 'original':
        if mode == 'apply' and (argv.count(b'--accept-successor-briefing-attempt') != 1
                                or argv.count(b'--accept-demo-briefing-repair') != 1):
            raise BriefingError('successor parent lacks separate explicit authority')
        if (argv.count(b'--attempt-profile') != 1
                or argv[argv.index(b'--attempt-profile') + 1:argv.index(b'--attempt-profile') + 2] != [attempt_profile.encode()]):
            raise BriefingError('parent attempt profile differs')
    elif b'--attempt-profile' in argv:
        raise BriefingError('original child cannot consume successor parent authority')
    locks = (proc / 'locks').read_text()
    if len(locks) > 1048576:
        raise BriefingError('publisher lock inventory exceeds bound')
    for fd, path in ((launcher_fd, STATE / 'launcher.lock'), (build_fd, STATE / TARGET / 'build.lock')):
        b._assert_original_lock(path, fd)
        child_stat, parent_stat = os.fstat(fd), (entry / 'fd' / str(fd)).stat()
        if (child_stat.st_dev, child_stat.st_ino) != (parent_stat.st_dev, parent_stat.st_ino):
            raise BriefingError('original inherited parent lock differs')
        found = False
        for line in locks.splitlines():
            fields = line.split()
            if len(fields) != 8 or fields[1:4] != ['FLOCK', 'ADVISORY', 'WRITE'] or fields[4] != str(parent):
                continue
            device = fields[5].split(':')
            if len(device) == 3 and (int(device[0], 16), int(device[1], 16), int(device[2])) == (
                    os.major(child_stat.st_dev), os.minor(child_stat.st_dev), child_stat.st_ino):
                found = True
        if not found:
            raise BriefingError('canonical parent does not hold both publisher locks')
    if proof['parent'] != parent_identity(parent, proc) or os.getppid() != parent:
        raise BriefingError('canonical parent changed during proof')
    return proof


def validate_apply_intent(intent, proof, sha, core, record):
    evidence = intent.get('evidence')
    core.validate_evidence(evidence)
    if (intent.get('operator_sha') != sha or intent.get('accept_demo_briefing_repair') is not True
            or intent.get('parent_binding') != {**proof['parent'], 'nonce_sha256': hashlib.sha256(proof['nonce'].encode()).hexdigest()}
            or intent.get('evidence_sha256') != proof['evidence_sha256']
            or intent.get('evidence_sha256') != core.digest(evidence)
            or os.path.lexists(record / 'completed.json') or os.path.lexists(record / 'database-started.json')):
        raise BriefingError('fresh explicitly authorized repair intent required')
    return evidence


def database_child(sha, mode, proof_fd, launcher_fd, build_fd, *, attempt_profile="original"):
    source, b, server, readers, ack, core = context(sha, verify_ci=False)
    proof = validate_parent_proof(source, sha, mode, proof_fd, launcher_fd, build_fd, b,
                                  **({'attempt_profile': attempt_profile} if attempt_profile != 'original' else {}))
    binding = attempt_binding(source, b, sha, attempt_profile)
    receipt = acknowledgement_evidence(b, readers, ack, sha, allow_fixed_successor=True)
    if os.path.lexists(b.BUSINESS_LEASE):
        raise BriefingError('business lease exists')
    evidence = None
    if mode == 'apply':
        record = attempt_record(b, attempt_profile)
        b._inventory(record, {'intent.json'})
        intent = b._read_json(record / 'intent.json')
        evidence = validate_apply_intent(intent, proof, sha, core, record)
        if binding is not None:
            if (intent.get('attempt_profile') != attempt_profile
                    or intent.get('unstarted_closure') != binding
                    or intent.get('accept_successor_briefing_attempt') is not True):
                raise BriefingError('fresh separate successor authorization required')
        elif any(k in intent for k in ('attempt_profile','unstarted_closure','accept_successor_briefing_attempt')):
            raise BriefingError('original attempt cannot consume successor evidence')
        if intent.get('reconciliation_succession') != receipt.get('succession'):
            raise BriefingError('repair intent predecessor binding differs')
        readers.write_json(record / 'database-started.json', {'state': 'DATABASE_ATTEMPT_STARTED',
                           'operator_sha': sha, 'evidence_sha256': intent['evidence_sha256']})
    elif mode != 'inspect':
        raise BriefingError('invalid database mode')
    target = b.canonical_source(TARGET)
    reset = readers.load(source / 'scripts/trusted_review_reset.py', 'briefing_reset_readers')
    reset._assert_isolated_search_path()
    reset._validate_production(TARGET, target, b, server)
    # Production proof above validates this root-managed dependency tree.
    sys.path.append('/opt/health-app/backend/venv/lib/python3.12/site-packages')
    raw_environment = server.read_production_env()
    environment = reset._parse_maintenance_environment(raw_environment)
    key = hmac.new(hashlib.sha256(raw_environment.encode()).digest(),
                   ('fixed-demo-briefing-health-v1:' + sha).encode(), hashlib.sha256).digest()
    del raw_environment
    fixture = target / 'backend/fixtures/demo_user_minimal.json'
    b.secure(fixture)
    if hashlib.sha256(fixture.read_bytes()).hexdigest() != core.FIXTURE_SHA256:
        raise BriefingError('frozen fixture changed')
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(target / 'backend')
    sys.path.insert(0, str(target / 'backend'))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(target, environment)
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        url = make_url(environment['DATABASE_URL'])
        if not url.database:
            raise BriefingError('explicit production database required')
        engine = create_engine(url, isolation_level='SERIALIZABLE', connect_args={'connect_timeout': 5})
        try:
            return database_work(engine, core, readers, environment['APP_STORE_REVIEW_DEMO_ACCOUNT'],
                                 fixture, key, evidence=evidence)
        finally:
            engine.dispose()


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--sha', required=True)
        parser.add_argument('--token-stdin', action='store_true')
        parser.add_argument('--accept-demo-briefing-repair', action='store_true')
        parser.add_argument('--evidence-sha256')
        parser.add_argument('--attempt-profile', choices=(SUCCESSOR_ATTEMPT,), default='original')
        parser.add_argument('--accept-successor-briefing-attempt', action='store_true')
        parser.add_argument('--parent-proof-fd', type=int, help=argparse.SUPPRESS)
        parser.add_argument('--publisher-lock-fd', type=int, help=argparse.SUPPRESS)
        parser.add_argument('--build-lock-fd', type=int, help=argparse.SUPPRESS)
        parser.add_argument('--database-probe', choices=('inspect', 'apply'), help=argparse.SUPPRESS)
        args = parser.parse_args()
        if args.database_probe:
            if args.token_stdin or args.accept_demo_briefing_repair or args.accept_successor_briefing_attempt or args.evidence_sha256:
                raise BriefingError('database child must not consume external authorization or credentials')
            result = database_child(args.sha, args.database_probe, args.parent_proof_fd, args.publisher_lock_fd, args.build_lock_fd, attempt_profile=args.attempt_profile)
        else:
            if any(fd is not None for fd in (args.parent_proof_fd, args.publisher_lock_fd, args.build_lock_fd)):
                raise BriefingError('inherited proof arguments only valid in child')
            if args.attempt_profile == 'original':
                if args.accept_successor_briefing_attempt:
                    raise BriefingError('successor authority cannot be used for original attempt')
            elif (args.accept_demo_briefing_repair or args.accept_successor_briefing_attempt or args.evidence_sha256):
                if not (args.accept_demo_briefing_repair and args.accept_successor_briefing_attempt and args.evidence_sha256):
                    raise BriefingError('separate successor authority and fresh digest required')
            source, b, server, readers, ack, core = context(args.sha, token_stdin=args.token_stdin)
            lock = STATE / 'launcher.lock'
            b.secure(lock, private=True)
            fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
            build_fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                build = STATE / TARGET / 'build.lock'
                exists = os.path.lexists(build)
                build_fd = b._acquire_existing_build_lock(TARGET)
                def check():
                    b._assert_original_lock(lock, fd)
                    if os.path.lexists(build) != exists:
                        raise BriefingError('build lock presence changed')
                    if build_fd is not None:
                        b._assert_original_lock(build, build_fd)
                adapter = make_adapter(source, b, server, readers, ack, core, args.sha, check, launcher_fd=fd, build_fd=build_fd, attempt_profile=args.attempt_profile, successor_authorized=args.accept_successor_briefing_attempt)
                result = core.repair(adapter, authorized=args.accept_demo_briefing_repair,
                                     evidence_sha256=args.evidence_sha256)
            finally:
                if build_fd is not None:
                    os.close(build_fd)
                os.close(fd)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):
        print('briefing repair rejected or incomplete; preserve evidence; do not retry', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
