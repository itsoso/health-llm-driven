"""Read-only evidence for one reviewed journey configuration preflight failure.

No deployment, migration phase, service operation, backup or retry is exposed.
The enclosing closure owns the original launcher, build and business leases.
"""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import stat
import sys

FAILED = '6a24b64596464f41eac852306da29bef6ff31da0'
PRODUCTION = '25b85536e3722dc111c528b8a915062a3f971397'
PROFILE = 'daily-journey-config-preflight-v1'
IMPLEMENTATIONS = {
    'deploy.sh': 'd01655afff653c26185c75b53ed7fd5f5280b867406f6374c510365ccba1009e',
    'scripts/trusted_release_server.py': '25744743a662226f831e1f0852055eb9781799307a30a63db60a0c68e2425bd7',
    'backend/scripts/runtime_state_release_transaction.py': '89306f825b3c89da0fc4c515752cc4b8a4f9e6c27dfb74b527cecffc00ba246a',
    'scripts/daily_journey_release.py': 'e55ac749de916f95d45bb7a756c0bb0aec6f77418be8c3dd8407092dfab1230c',
    'backend/app/config.py': '6db93c29fe70f5661270dbe6b549983b2b32786fb212bc24cbca455d9831ffd6',
}
FAILURE_SUFFIX = ('DAILY_JOURNEY_RELEASE_BLOCKED: prerequisites or outcome require operator review; evidence retained\n'
    '\x1b[0;31m✗\x1b[0m 行程新增表预检未通过；未停写，原租约和迁移意图保留\n').encode()
FORBIDDEN_LOG = (b'DAILY_JOURNEY_PREFLIGHT_OK', b'DAILY_JOURNEY_READBACK_OK', b'DAILY_JOURNEY_APPLIED_OK',
    b'phase=env_staging_started', b'phase=deactivation_started', b'phase=guard_started',
    b'phase=remote_writers_stopped', b'phase=remote_checkout_completed', b'command=preflight-code',
    b'command=prepare', b'command=install', b'command=commit', b'command=restore',
    b'LAYA_INSTALL_STEP', b'LAYA_PREPARED', b'LAYA_INSTALLED', b'systemctl stop')

REQUIRED_LOG = (
    ('\x1b[0;32m✓\x1b[0m 已核验 origin/main: ' + FAILED[:12] + '\n').encode(),
    'REVA_RELEASE_TIMING phase=backend_started '.encode(),
    '\x1b[0;32m✓\x1b[0m 生产 env 预检通过\n'.encode(),
    b'REVA_RELEASE_TIMING phase=env_checked ',
    '\x1b[0;32m✓\x1b[0m 发布工具已校验；未执行备份、恢复演练或站外归档\n'.encode(),
    ('RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED '
     'old_sha=6fa1c1d5ff9e2a953b0b8d3be5b6a30238aa5ccf candidate_sha=' + PRODUCTION +
     ' gate_armed=false gate_released=true release_target=candidate next_action=none '
     'state_source=terminal mode=code-only-no-backup\n').encode(),
    b'REVA_RELEASE_TIMING phase=preparation_checked ',
    ('ROLLBACK_POINT_SCHEMA_OK commit=' + PRODUCTION + '\n').encode(),
    ('\x1b[0;32m✓\x1b[0m 发布前生产 SHA 已验证并记录: ' + PRODUCTION[:12] + '\n').encode(),
)


class JourneyProofError(RuntimeError):
    pass


def validate_implementations(value):
    if value != IMPLEMENTATIONS:
        raise JourneyProofError('journey failed code differs')


def validate_failure_log(raw):
    witness = ('ROLLBACK_POINT_SCHEMA_OK commit=' + PRODUCTION + '\n').encode()
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 16000000
            or not raw.endswith(FAILURE_SUFFIX) or raw.count(b'DAILY_JOURNEY_RELEASE_BLOCKED:') != 1
            or raw.count(witness) != 1 or any(token in raw for token in FORBIDDEN_LOG)
            or any(raw.count(token) != 1 for token in REQUIRED_LOG)
            or raw.count(b'RUNTIME_STATE_TRANSACTION_') != 1
            or raw.count(b'REVA_RELEASE_TIMING phase=') != 3
            or b'RUNTIME_STATE_TRANSACTION_FAILED' in raw
            or any(raw.index(a) >= raw.index(b) for a,b in zip(REQUIRED_LOG, REQUIRED_LOG[1:]))):
        raise JourneyProofError('exact journey pre-stop failure required')


def validate_catalog(value):
    expected = {'state':'PENDING', 'target_tables':[], 'read_only':True, 'health_rows_read':False,
                'failed_sha':FAILED, 'production_sha':PRODUCTION}
    if (not isinstance(value, dict) or set(value) != set(expected) | {'database_sha256', 'ledger_sha256'}
            or any(value.get(k) != v for k,v in expected.items())
            or value.get('read_only') is not True or value.get('health_rows_read') is not False
            or any(not isinstance(value.get(k), str) or re.fullmatch('[0-9a-f]{64}', value[k]) is None
                   for k in ('database_sha256','ledger_sha256'))):
        raise JourneyProofError('journey catalog evidence differs')
    return value


def validate(value, failed_sha, production_sha):
    if (failed_sha != FAILED or production_sha != PRODUCTION or not isinstance(value, dict)
            or set(value) != {'catalog', 'implementations', 'migration_state_absent', 'laya_candidate_absent'}
            or value['migration_state_absent'] is not True or value['laya_candidate_absent'] is not True):
        raise JourneyProofError('journey closure binding differs')
    validate_catalog(value['catalog'])
    validate_implementations(value['implementations'])


def secure_chain(path):
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if (info.st_uid != 0 or info.st_mode & 0o022
                or (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    if item == path else not stat.S_ISDIR(info.st_mode))):
            raise JourneyProofError('unsafe journey proof source')


def absent(proof):
    state = Path('/var/lib/reva-release/daily-journey-migrations')
    if os.path.lexists(state):
        proof._directory(state)
    # No per-candidate intent, outcome or partial directory may have existed.
    proof._absent(Path('/var/lib/reva-release/daily-journey-migrations') / FAILED,
                  Path('/var/lib/reva-laya-release/sources') / FAILED,
                  Path('/var/lib/reva-laya-release/install.json.pending'),
                  Path('/etc/systemd/system/reva-laya.service.pending'),
                  Path('/etc/reva-laya/service.env.pending'),
                  proof.bootstrap.STATE / FAILED / 'deployment.env')


def inspect(proof, failed):
    if proof.failed_sha != FAILED or proof.production_sha != PRODUCTION:
        raise JourneyProofError('journey revisions differ')
    binding = {name: proof._file(failed / name)[1]['sha256'] for name in IMPLEMENTATIONS}
    validate_implementations(binding)
    absent(proof)
    module = proof.source / 'scripts/no_backup_daily_journey_proof.py'
    proof.bootstrap.secure(module)
    # The canonical old venv supplies pinned dependencies, isolated from caller
    # site/PYTHONPATH. Never execute the failed helper's preflight/apply entry.
    result = subprocess.run([str(proof.production / 'backend/venv/bin/python'), '-I', '-B',
                             str(module), '--catalog'], env={'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LC_ALL':'C'},
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=90, check=False)
    if result.returncode != 0 or len(result.stdout) > 2000:
        raise JourneyProofError('read-only journey catalog proof failed')
    value = {'catalog':json.loads(result.stdout), 'implementations':binding,
             'migration_state_absent':True, 'laya_candidate_absent':True}
    absent(proof)
    validate(value, proof.failed_sha, proof.production_sha)
    return value


def read_catalog(helper, conn, expected):
    if helper.sql(conn, 'SHOW transaction_read_only').scalar_one() != 'on':
        raise JourneyProofError('read-only database required')
    identity = helper.role_identity(conn)
    ledger = sorted([list(row) for row in helper.sql(conn, 'SELECT id, checksum FROM public.schema_migrations').all()])
    state = helper.database_state(conn, expected)
    value = {'state':state, 'target_tables':[], 'read_only':True, 'health_rows_read':False,
             'failed_sha':FAILED, 'production_sha':PRODUCTION,
             'database_sha256':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
             'ledger_sha256':hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()}
    return validate_catalog(value)


def catalog_probe():
    """Fixed catalog SELECTs only, server-enforced read-only from connection start."""
    if os.geteuid() != 0 or not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise JourneyProofError('isolated root probe required')
    source = Path('/var/lib/reva-release/bootstrap') / FAILED / 'source'
    # Load exact historical helper for read-only parsing/catalog functions only.
    path = source / 'scripts/daily_journey_release.py'
    secure_chain(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != IMPLEMENTATIONS['scripts/daily_journey_release.py']:
        raise JourneyProofError('catalog helper source differs')
    spec = importlib.util.spec_from_file_location('journey_catalog_helper', path)
    helper = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), helper.__dict__)
    for name, digest in IMPLEMENTATIONS.items():
        secure_chain(source / name)
        content = helper.protected_read(source / name)
        if hashlib.sha256(content).hexdigest() != digest or content != helper.git(source, 'show', 'HEAD:' + name):
            raise JourneyProofError('catalog canonical code differs')
    if helper.git(source, 'rev-parse', 'HEAD').decode().strip() != FAILED:
        raise JourneyProofError('catalog source revision differs')
    config = source / 'backend/app/config.py'
    os.environ.clear(); os.environ.update(helper.ENV)
    secure_chain(Path('/opt/health-app/backend/.env'))
    os.chdir('/opt/health-app/backend')
    namespace = {'__name__':'journey_closure_settings','__file__':str(config)}
    exec(compile(helper.protected_read(config), str(config), 'exec', dont_inherit=True), namespace)
    settings = namespace['settings']
    if settings.app_env.lower() != 'production':
        raise JourneyProofError('production config required')
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    engine = create_engine(settings.effective_database_url, poolclass=NullPool, hide_parameters=True,
        connect_args={'connect_timeout':10, 'options':'-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=5000'})
    try:
        if engine.dialect.name != 'postgresql':
            raise JourneyProofError('PostgreSQL proof required')
        with engine.connect() as conn:
            return read_catalog(helper, conn, helper.expected_migrations(source))
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['--catalog']:
            raise JourneyProofError('fixed catalog mode required')
        print(json.dumps(catalog_probe(), sort_keys=True))
    except Exception:
        print('JOURNEY_CATALOG_PROOF_BLOCKED', file=sys.stderr)
        raise SystemExit(70) from None
