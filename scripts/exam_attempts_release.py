#!/usr/bin/env python3
"""One reviewed, additive no-backup migration, inside deploy.sh's existing lease.

Never a generic migration runner. Credentials remain in this child process.
An intent with an uncommitted/unknown database result blocks automatic replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

MIGRATION = '20261028_120000_life_exam_attempts'
SQL_HASH = '383f4907d892b2b3e0c5812d1030b8d675e79c6033d89cda3bf8cb8854ea097d'
PINNED = {
    f'backend/migrations/managed/{MIGRATION}.postgresql.sql': SQL_HASH,
    f'backend/migrations/managed/{MIGRATION}.sqlite.sql': '7164f2624bc02e8920d07d6b97003c0c0fc98ff93d6d78110b31cc1e640cdea4',
    'backend/app/models/exam_practice.py': 'c311f6f2ceee61b9014db70401d51b512bd6a424dbc618ab95bae3e953da4868',
}
INIT = 'backend/app/models/__init__.py'
ANCHOR = b'from app.models.life_navigation import LifeNavigationWorkspace\n'
IMPORT = b'\nfrom app.models.exam_practice import ExamAttemptRecord\n'
SCOPES = ('backend/migrations/managed', 'backend/app/models', 'infra/systemd/dropins')
TABLES = ('life_exam_attempts',)
SEQUENCES = ('life_exam_attempts_sequence_seq',)
STATE = Path('/var/lib/reva-release/exam-attempts-migrations')
LEASE = Path('/var/lock/health-app-release')
LIVE = Path('/opt/health-app')
CREDENTIAL = Path('/etc/health-app/migration.env')
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1'}


class ReleaseBlocked(RuntimeError):
    """Only static, sanitized messages may cross the release log boundary."""


def git(root, *args):
    return subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c',
                           'core.fsmonitor=false', '-C', str(root), *args], env=ENV,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True, timeout=30).stdout


def source_admission(root, old, candidate):
    if any(re.fullmatch('[0-9a-f]{40}', sha) is None for sha in (old, candidate)):
        raise ReleaseBlocked('exact source revisions required')
    changed = set(git(root, 'diff', '--name-only', '-z', old, candidate, '--', *SCOPES).decode().strip('\0').split('\0')) - {''}
    if not changed:
        return False
    if changed != set(PINNED) | {INIT}:
        raise ReleaseBlocked('schema source delta is outside the reviewed addition')
    for path, digest in PINNED.items():
        if git(root, 'ls-tree', old, '--', path):
            raise ReleaseBlocked('reviewed target must be absent in the prior revision')
        mode = git(root, 'ls-tree', candidate, '--', path).decode().split()[0]
        if mode != '100644' or hashlib.sha256(git(root, 'show', f'{candidate}:{path}')).hexdigest() != digest:
            raise ReleaseBlocked('reviewed migration or model bytes differ')
    before = git(root, 'show', f'{old}:{INIT}')
    after = git(root, 'show', f'{candidate}:{INIT}')
    if before.count(ANCHOR) != 1 or IMPORT in before or after != before.replace(ANCHOR, ANCHOR + IMPORT):
        raise ReleaseBlocked('model registration is not the exact additive insertion')
    if git(root, 'ls-tree', candidate, '--', INIT).decode().split()[0] != '100644':
        raise ReleaseBlocked('model registration mode changed')
    return True


def pending_state(expected, applied):
    if set(applied) - set(expected):
        raise ReleaseBlocked('managed ledger contains unknown migration IDs')
    if expected.get(MIGRATION) != SQL_HASH:
        raise ReleaseBlocked('candidate migration checksum differs')
    for key, checksum in expected.items():
        if key != MIGRATION and applied.get(key) != checksum:
            raise ReleaseBlocked('other pending migrations or checksum drift')
    if MIGRATION in applied:
        if applied[MIGRATION] != SQL_HASH:
            raise ReleaseBlocked('exam attempts ledger checksum drift')
        return 'APPLIED'
    return 'PENDING'


def parse_migration_env(raw):
    # Literal dotenv subset, deliberately not shell evaluation/interpolation.
    lines = [line.strip() for line in raw.decode('utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or not lines[0].startswith('MIGRATION_DATABASE_URL='):
        raise ReleaseBlocked('migration credential file has unsupported keys')
    value = lines[0].split('=', 1)[1]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if not value.startswith(('postgresql://', 'postgresql+psycopg2://')) or any(c in value for c in '$`\r\n\x00'):
        raise ReleaseBlocked('migration credential value is not a literal PostgreSQL URL')
    return value


def secure(path, *, directory=False, private=False):
    info = path.lstat()
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    if not predicate(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ReleaseBlocked('unsafe release file metadata')
    if not directory and info.st_nlink != 1:
        raise ReleaseBlocked('hardlinked release file rejected')
    if private and stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise ReleaseBlocked('private release file permissions differ')
    return (info.st_dev, info.st_ino)


def protected_read(path, *, private=False):
    identity = secure(path, private=private)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if identity != (info.st_dev, info.st_ino) or info.st_size > 1000000:
            raise ReleaseBlocked('release file changed during open')
        result = stream.read(1000001)
    if len(result) > 1000000 or secure(path, private=private) != identity:
        raise ReleaseBlocked('release file changed during read')
    return result


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(path, value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def reentry_state(record, plan, database_state):
    intent = record / 'intent.json'
    if os.path.lexists(intent):
        if intent.is_symlink() or json.loads(intent.read_bytes()) != plan:
            raise ReleaseBlocked('migration intent binding differs')
        if database_state != 'APPLIED':
            raise ReleaseBlocked('NEEDS_OPERATOR: pending migration intent; readback only')
        return 'READBACK'
    if database_state == 'APPLIED':
        raise ReleaseBlocked('migration ledger has no matching release intent')
    if os.path.lexists(record / 'completed.json'):
        raise ReleaseBlocked('completed migration has no intent')
    return 'NEW'


def lease_check(token):
    if re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', token) is None:
        raise ReleaseBlocked('invalid release lease binding')
    # /var/lock is the standard system symlink; the lease itself cannot be one.
    identity = secure(LEASE, directory=True)
    raw = protected_read(LEASE / 'token', private=True)
    if raw.decode().strip() != token:
        raise ReleaseBlocked('release lease changed')
    return identity + secure(LEASE / 'token', private=True)


def expected_migrations(source):
    result = {}
    directory = source / 'backend/migrations/managed'
    for path in sorted(directory.glob('*.sql')):
        if '.down.' in path.name or path.name.endswith('.sqlite.sql'):
            continue
        suffix = '.postgresql.sql' if path.name.endswith('.postgresql.sql') else '.sql'
        key = path.name.removesuffix(suffix)
        if key not in result or suffix == '.postgresql.sql':
            raw = protected_read(path)
            if raw != git(source, 'show', f'HEAD:backend/migrations/managed/{path.name}'):
                raise ReleaseBlocked('candidate managed source drift')
            result[key] = hashlib.sha256(raw.decode().encode()).hexdigest()
    return result


def sql(connection, statement, **params):
    from sqlalchemy import text
    return connection.execute(text(statement), params)


def database_state(connection, expected):
    # Never call the generic runner: its preflight itself creates the ledger.
    applied = dict(sql(connection, 'SELECT id, checksum FROM public.schema_migrations').all())
    state = pending_state(expected, applied)
    present = set(sql(connection, "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relname IN ('life_exam_attempts','life_exam_attempts_sequence_seq')").scalars())
    if state == 'PENDING' and present or state == 'APPLIED' and present != set(TABLES + SEQUENCES):
        raise ReleaseBlocked('target tables and ledger disagree')
    return state


def role_identity(connection):
    row = sql(connection, "SELECT current_database() AS db, current_user AS role, inet_server_addr()::text AS host, inet_server_port() AS port, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user").mappings().one()
    if row['host'] is None or row['port'] is None:
        raise ReleaseBlocked('TCP database identity is required for this bounded release')
    if any(row[key] for key in ('rolsuper', 'rolbypassrls', 'rolcreatedb', 'rolcreaterole')):
        raise ReleaseBlocked('database role has forbidden elevated privileges')
    return {key: row[key] for key in ('db', 'role', 'host', 'port')}


def schema_evidence(connection, runtime_role):
    """Bounded catalog proof includes FKs, checks, indexes, and runtime grants.

    The first proof is created inside the pinned DDL transaction. Readback must
    reproduce it exactly; no attempt rows or application payloads are read.
    """
    tables = {}
    for name in TABLES:
        meta = sql(connection, "SELECT relkind, relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:name)", name='public.' + name).one()
        if tuple(meta) != ('r', False, False):
            raise ReleaseBlocked('target table kind or row security differs')
        if sql(connection, 'SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass(:name) AND NOT tgisinternal)', name='public.' + name).scalar_one():
            raise ReleaseBlocked('unexpected exam table trigger')
        if sql(connection, "SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=to_regclass(:name) AND (a.grantee=0 OR (a.grantee<>(SELECT oid FROM pg_roles WHERE rolname=:role) AND a.grantee<>c.relowner)))", name='public.' + name, role=runtime_role).scalar_one():
            raise ReleaseBlocked('exam table grants expose additional roles')
        if sql(connection, 'SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass(:name) AND attnum>0 AND NOT attisdropped AND attacl IS NOT NULL)', name='public.' + name).scalar_one():
            raise ReleaseBlocked('unexpected exam column-level grants')
        for privilege in ('UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER', 'REFERENCES', 'SELECT WITH GRANT OPTION', 'INSERT WITH GRANT OPTION'):
            if sql(connection, 'SELECT has_table_privilege(:role,:name,:privilege)', role=runtime_role, name='public.' + name, privilege=privilege).scalar_one():
                raise ReleaseBlocked('runtime exam privileges exceed append access')
        columns = [list(row) for row in sql(connection, "SELECT attname, format_type(atttypid,atttypmod), attnotnull, pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=to_regclass(:name) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum", name='public.' + name)]
        constraints = [list(row) for row in sql(connection, 'SELECT conname, contype, pg_get_constraintdef(oid), convalidated FROM pg_constraint WHERE conrelid=to_regclass(:name) ORDER BY conname', name='public.' + name)]
        indexes = [list(row) for row in sql(connection, 'SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=to_regclass(:name) ORDER BY c.relname', name='public.' + name)]
        required_indexes = {
            'life_exam_attempts': {'life_exam_attempts_pkey', 'life_exam_attempts_id_key', 'uq_life_exam_owner_request', 'ix_life_exam_owner_question_sequence', 'ix_life_exam_owner_date_sequence'},
        }
        required_constraints = {
            'life_exam_attempts': {'life_exam_attempts_pkey', 'life_exam_attempts_id_key', 'uq_life_exam_owner_request', 'life_exam_attempts_user_id_fkey', 'ck_life_exam_version', 'ck_life_exam_choices', 'ck_life_exam_elapsed', 'ck_life_exam_grade'},
        }
        if set(row[0] for row in indexes) != required_indexes[name] or any(not row[2] or not row[3] for row in indexes):
            raise ReleaseBlocked('required exam indexes are absent or invalid')
        if set(row[0] for row in constraints) != required_constraints[name] or any(not row[3] for row in constraints):
            raise ReleaseBlocked('required exam constraints are absent or invalid')
        for privilege in ('SELECT', 'INSERT'):
            if not sql(connection, 'SELECT has_table_privilege(:role,:name,:privilege)', role=runtime_role, name='public.' + name, privilege=privilege).scalar_one():
                raise ReleaseBlocked('runtime role lacks required exam append access')
        identity = sql(connection, 'SELECT oid, pg_get_userbyid(relowner) FROM pg_class WHERE oid=to_regclass(:name)', name='public.' + name).one()
        if identity[1] != sql(connection, 'SELECT current_user').scalar_one():
            raise ReleaseBlocked('exam table owner differs from the migration role')
        tables[name] = {'oid': identity[0], 'owner': identity[1], 'columns': columns, 'constraints': constraints, 'indexes': indexes}
    return {'tables': tables, 'sequences': sequence_evidence(connection, runtime_role)}


def sequence_evidence(connection, runtime_role):
    """Prove serial identity/ownership and USAGE-only grants without reading its value."""
    name = 'public.life_exam_attempts_sequence_seq'
    meta = sql(connection, "SELECT oid, relkind, pg_get_userbyid(relowner) FROM pg_class WHERE oid=to_regclass(:name)", name=name).one()
    if meta[1] != 'S' or meta[2] != sql(connection, 'SELECT current_user').scalar_one():
        raise ReleaseBlocked('exam sequence kind or owner differs')
    if sql(connection, "SELECT pg_get_serial_sequence('public.life_exam_attempts','sequence')").scalar_one() != name:
        raise ReleaseBlocked('exam serial identity differs')
    ownership = [list(row) for row in sql(connection, "SELECT n.nspname,c.relname,a.attname,d.deptype FROM pg_depend d JOIN pg_class c ON c.oid=d.refobjid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=d.refobjsubid WHERE d.classid='pg_class'::regclass AND d.objid=to_regclass(:name) AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')", name=name)]
    if ownership != [['public', 'life_exam_attempts', 'sequence', 'a']]:
        raise ReleaseBlocked('exam serial ownership dependency differs')
    properties = list(sql(connection, 'SELECT seqtypid::regtype::text,seqstart,seqincrement,seqmin,seqmax,seqcache,seqcycle FROM pg_sequence WHERE seqrelid=to_regclass(:name)', name=name).one())
    if properties != ['integer', 1, 1, 1, 2147483647, 1, False]:
        raise ReleaseBlocked('exam serial properties differ')
    if sql(connection, "SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(COALESCE(c.relacl,acldefault('S',c.relowner))) a WHERE c.oid=to_regclass(:name) AND (a.grantee=0 OR (a.grantee<>(SELECT oid FROM pg_roles WHERE rolname=:role) AND a.grantee<>c.relowner)))", name=name, role=runtime_role).scalar_one():
        raise ReleaseBlocked('exam sequence grants expose additional roles')
    if not sql(connection, "SELECT has_sequence_privilege(:role,:name,'USAGE')", role=runtime_role, name=name).scalar_one():
        raise ReleaseBlocked('runtime role lacks exam sequence usage')
    for privilege in ('SELECT', 'UPDATE', 'USAGE WITH GRANT OPTION'):
        if sql(connection, 'SELECT has_sequence_privilege(:role,:name,:privilege)', role=runtime_role, name=name, privilege=privilege).scalar_one():
            raise ReleaseBlocked('runtime sequence privileges exceed usage')
    return {name: {'oid': meta[0], 'owner': meta[2], 'ownership': ownership, 'properties': properties}}


def committed_proof(connection, plan, record, runtime_role):
    # Proof is transactionally stored beside the migration ledger, in the new
    # table's COMMENT (metadata only). It closes the fsync/DB-commit crash window.
    raw = sql(connection, "SELECT obj_description('public.life_exam_attempts'::regclass,'pg_class')").scalar_one()
    proof = json.loads(raw or '{}')
    if proof.get('binding') != plan or proof.get('schema') != schema_evidence(connection, runtime_role):
        raise ReleaseBlocked('committed migration schema/binding differs')
    completed = {'binding': plan, 'schema_sha256': hashlib.sha256(json.dumps(proof['schema'], sort_keys=True).encode()).hexdigest()}
    path = record / 'completed.json'
    if os.path.lexists(path):
        if json.loads(protected_read(path, private=True)) != completed:
            raise ReleaseBlocked('migration receipt differs')
    return completed


def apply_exact(connection, source, plan, runtime_role):
    from sqlalchemy import text
    raw = protected_read(source / f'backend/migrations/managed/{MIGRATION}.postgresql.sql')
    if hashlib.sha256(raw).hexdigest() != SQL_HASH:
        raise ReleaseBlocked('migration SQL drift')
    sql(connection, "SET LOCAL search_path TO public, pg_catalog")
    # This pinned SQL has no procedural blocks or semicolons in literals.
    statements = '\n'.join(line for line in raw.decode().splitlines() if not line.lstrip().startswith('--'))
    for statement in statements.split(';'):
        if statement.strip():
            connection.execute(text(statement))
    quoted = connection.dialect.identifier_preparer.quote(runtime_role)
    for table in TABLES:
        connection.execute(text(f'GRANT SELECT, INSERT ON TABLE public.{table} TO {quoted}'))
    connection.execute(text(f'GRANT USAGE ON SEQUENCE public.life_exam_attempts_sequence_seq TO {quoted}'))
    evidence = schema_evidence(connection, runtime_role)
    proof = json.dumps({'binding': plan, 'schema': evidence}, sort_keys=True)
    # Use driver parameter binding; COMMENT grammar cannot bind a parameter in
    # all drivers, so quote the server-produced JSON as a SQL literal safely.
    literal = "'" + proof.replace("'", "''") + "'"
    connection.execute(text('COMMENT ON TABLE public.life_exam_attempts IS ' + literal))
    sql(connection, 'INSERT INTO public.schema_migrations(id,checksum) VALUES(:id,:checksum)', id=MIGRATION, checksum=SQL_HASH)


def load_runtime_settings(config_bytes, path):
    namespace = {'__name__': 'exam_attempts_release_settings', '__file__': str(path)}
    # The helper uses postponed annotations; the canonical config does not.
    # Preserve the config's own semantics rather than inheriting our future flags.
    exec(compile(config_bytes, str(path), 'exec', dont_inherit=True), namespace)
    return namespace['settings']


def remote_run(source, old, candidate, token, phase):
    if os.geteuid() != 0 or source != Path('/var/lib/reva-release/bootstrap') / candidate / 'source':
        raise ReleaseBlocked('fixed root canonical staging required')
    for directory in [*reversed(source.parents), source, source / 'scripts', source / 'backend', STATE.parent]:
        secure(directory, directory=True)
    if git(source, 'rev-parse', 'HEAD').decode().strip() != candidate or git(source, 'status', '--porcelain', '--untracked-files=all'):
        raise ReleaseBlocked('canonical candidate is not clean and exact')
    if not source_admission(source, old, candidate):
        raise ReleaseBlocked('no reviewed additive delta')
    lease = lease_check(token)
    for parent in reversed(CREDENTIAL.parents):
        secure(parent, directory=True)
    migration_url = parse_migration_env(protected_read(CREDENTIAL, private=True))
    # app config is the canonical candidate code, and only reads the fixed live
    # env. It does not inherit caller-selected URL credentials.
    secure(LIVE / 'backend', directory=True)
    protected_read(LIVE / 'backend/.env')
    os.environ.clear()
    os.environ.update(ENV)
    os.chdir(LIVE / 'backend')
    path = source / 'backend/app/config.py'
    secure(path.parent, directory=True)
    config_bytes = protected_read(path)
    if config_bytes != git(source, 'show', 'HEAD:backend/app/config.py'):
        raise ReleaseBlocked('runtime settings source drift')
    # Compile verified bytes directly: no ignored/stale Python cache is loaded.
    settings = load_runtime_settings(config_bytes, path)
    if settings.app_env.lower() != 'production':
        raise ReleaseBlocked('production runtime configuration required')
    from sqlalchemy import create_engine
    runtime = create_engine(settings.effective_database_url, pool_pre_ping=True, hide_parameters=True)
    migration = create_engine(migration_url, pool_pre_ping=True, hide_parameters=True)
    try:
        if runtime.dialect.name != 'postgresql' or migration.dialect.name != 'postgresql':
            raise ReleaseBlocked('PostgreSQL required')
        with runtime.connect() as conn:
            runtime_identity = role_identity(conn)
        with migration.connect() as conn:
            sql(conn, "SET TRANSACTION READ ONLY")
            sql(conn, "SET LOCAL statement_timeout='15s'")
            identity = role_identity(conn)
            if identity['role'] == runtime_identity['role'] or any(identity[k] != runtime_identity[k] for k in ('db', 'host', 'port')):
                raise ReleaseBlocked('separate roles in the same database required')
            if sql(conn, "SELECT has_schema_privilege(current_user,'public','CREATE')").scalar_one() is not True:
                raise ReleaseBlocked('migration role lacks bounded schema create capability')
            if sql(conn, "SELECT pg_has_role(:runtime, current_user, 'MEMBER') OR has_schema_privilege(:runtime,'public','CREATE')", runtime=runtime_identity['role']).scalar_one():
                raise ReleaseBlocked('runtime role inherits migration or schema-create authority')
            for privilege in ('SELECT', 'INSERT'):
                if not sql(conn, "SELECT has_table_privilege(current_user,'public.schema_migrations',:privilege)", privilege=privilege).scalar_one():
                    raise ReleaseBlocked('migration role lacks ledger access')
            if not sql(conn, "SELECT has_table_privilege(current_user,'public.users','REFERENCES')").scalar_one():
                raise ReleaseBlocked('migration role lacks users reference capability')
            expected = expected_migrations(source)
            state = database_state(conn, expected)
        plan = {'old': old, 'candidate': candidate, 'checksum': SQL_HASH,
                'lease_sha256': hashlib.sha256(token.encode()).hexdigest(),
                'database_sha256': hashlib.sha256(json.dumps([identity, runtime_identity], sort_keys=True).encode()).hexdigest()}
        record = STATE / candidate
        if STATE.exists():
            secure(STATE, directory=True, private=True)
        if os.path.lexists(record):
            secure(record, directory=True, private=True)
            for child in record.iterdir():
                if child.name not in ('intent.json', 'completed.json'):
                    raise ReleaseBlocked('unknown migration release artifact')
                protected_read(child, private=True)
        mode = reentry_state(record, plan, state)
        if lease_check(token) != lease:
            raise ReleaseBlocked('release lease identity changed')
        if phase == 'preflight' and mode == 'NEW':
            print('EXAM_ATTEMPTS_PREFLIGHT_OK pending=1')
            return
        if mode == 'READBACK':
            with migration.connect() as conn:
                completed = committed_proof(conn, plan, record, runtime_identity['role'])
            # Preflight/readback never alters evidence. Apply may seal a proved
            # committed outcome, but cannot execute DDL again.
            if phase == 'apply' and not (record / 'completed.json').exists():
                write_once(record / 'completed.json', completed)
            print('EXAM_ATTEMPTS_READBACK_OK committed=1')
            return
        if phase != 'apply':
            raise ReleaseBlocked('migration has no committed readback')
        for unit in ('health-backend.socket', 'health-backend', 'celery-worker', 'celery-beat'):
            value = subprocess.run(['/usr/bin/systemctl', 'show', unit, '-p', 'ActiveState', '--value'], env=ENV, capture_output=True, check=True, text=True, timeout=15).stdout.strip()
            if value != 'inactive':
                raise ReleaseBlocked('all writers must be stopped')
        if git(LIVE, 'rev-parse', 'HEAD').decode().strip() != candidate or git(LIVE, 'status', '--porcelain', '--untracked-files=no'):
            raise ReleaseBlocked('live checkout is not the exact candidate')
        if not STATE.exists():
            STATE.mkdir(mode=0o700)
            sync_directory(STATE.parent)
        record.mkdir(mode=0o700)
        sync_directory(STATE)
        write_once(record / 'intent.json', plan)
        with migration.begin() as conn:
            sql(conn, "SET LOCAL lock_timeout='5s'")
            sql(conn, "SET LOCAL statement_timeout='30s'")
            if not sql(conn, 'SELECT pg_try_advisory_xact_lock(730228120000)').scalar_one():
                raise ReleaseBlocked('migration transaction is already running')
            if database_state(conn, expected) != 'PENDING' or lease_check(token) != lease:
                raise ReleaseBlocked('migration state changed after intent')
            apply_exact(conn, source, plan, runtime_identity['role'])
            if lease_check(token) != lease:
                raise ReleaseBlocked('release lease changed before commit')
        with migration.connect() as conn:
            completed = committed_proof(conn, plan, record, runtime_identity['role'])
        if lease_check(token) != lease:
            raise ReleaseBlocked('release lease changed after commit')
        write_once(record / 'completed.json', completed)
        print('EXAM_ATTEMPTS_APPLIED_OK committed=1')
    finally:
        runtime.dispose()
        migration.dispose()



def failure_diagnostic(error, phase):
    """Bounded code metadata only: never exception text, SQL, locals or paths."""
    allowed = {'ValueError', 'TypeError', 'KeyError', 'OSError', 'FileNotFoundError',
               'PermissionError', 'TimeoutError', 'TimeoutExpired', 'CalledProcessError',
               'OperationalError', 'ProgrammingError', 'InterfaceError', 'InternalError',
               'IntegrityError', 'DatabaseError', 'ModuleNotFoundError', 'ImportError', 'PydanticUserError'}
    name = type(error).__name__
    line = None
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == __file__:
            line = trace.tb_lineno
        trace = trace.tb_next
    return {'phase': phase if phase in ('source-check', 'preflight', 'apply', 'readback') else 'unknown',
            'exception': name if name in allowed else 'Exception', 'helper_line': line}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('source-check', 'preflight', 'apply', 'readback'))
    parser.add_argument('old')
    parser.add_argument('candidate')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--lease-token')
    args = parser.parse_args()
    try:
        if args.phase == 'source-check':
            print('EXAM_ATTEMPTS_ADDITIVE' if source_admission(args.source, args.old, args.candidate) else 'CODE_ONLY')
        else:
            remote_run(args.source, args.old, args.candidate, args.lease_token or '', args.phase)
        return 0
    except ReleaseBlocked as error:
        print('EXAM_ATTEMPTS_RELEASE_BLOCKED: ' + str(error), file=sys.stderr)
        return 70
    except Exception as error:
        print("EXAM_ATTEMPTS_DIAGNOSTIC: " + json.dumps(failure_diagnostic(error, args.phase), sort_keys=True), file=sys.stderr)
        # Database drivers may include credentials, SQL and connection details.
        # The preserved lease/intent is the diagnostic authority, never repr(e).
        print('EXAM_ATTEMPTS_RELEASE_BLOCKED: prerequisites or outcome require operator review; evidence retained', file=sys.stderr)
        return 70


if __name__ == '__main__':
    raise SystemExit(main())
