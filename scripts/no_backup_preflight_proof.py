"""Bounded, read-only proof for the reviewed pre-mutation no-backup failure.

This module grants no deployment or retry authority and creates no copies.
Historical environment equality is unavailable: only current identity, chronology,
reviewed failed code and still-running old processes support the narrower claim.
"""
import grp
import hashlib
import importlib.util
import os
import re
import shlex
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "no_backup_contained_proof", Path(__file__).with_name("contained_recovery_proof.py"))
_contained = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contained)
ARTIFACTS, UNITS = _contained.ARTIFACTS, _contained.UNITS
ProofError, RecoveryProof = _contained.ProofError, _contained.RecoveryProof
_retained_spec = importlib.util.spec_from_file_location(
    "no_backup_retained_vision", Path(__file__).with_name("retained_candidate_retirement.py"))
_retained = importlib.util.module_from_spec(_retained_spec)
_retained_spec.loader.exec_module(_retained)

FAILED_IMPLEMENTATIONS = {
    'deploy.sh': '7444684608ed028f53845e8cc8d94c1dd7c2abd1a0524bf0776898cc32560f90',
    'scripts/trusted_release_server.py': '4ec7fd78e5477100c6bbd0612046b40fab28cf27eefe87c56d0fcaeab9d0d226',
    'backend/scripts/runtime_state_release_transaction.py': 'fc46bb5b5874f69ab27f2b8a717b3c7131f1d921eb3147df1964199940122675',
}
LAYA_FAILED_IMPLEMENTATIONS = {
    'deploy.sh': '7444684608ed028f53845e8cc8d94c1dd7c2abd1a0524bf0776898cc32560f90',
    'scripts/trusted_release_server.py': '4ec7fd78e5477100c6bbd0612046b40fab28cf27eefe87c56d0fcaeab9d0d226',
    'backend/scripts/runtime_state_release_transaction.py': '89306f825b3c89da0fc4c515752cc4b8a4f9e6c27dfb74b527cecffc00ba246a',
    'infra/laya/install.py': '306ccb538f0dea31d249488f2eb7663e2e8ba57d4ef22d296070a870ce0bba42',
}
_laya_spec = importlib.util.spec_from_file_location('no_backup_laya_context',
    Path(__file__).with_name('no_backup_laya_context_proof.py'))
_laya = importlib.util.module_from_spec(_laya_spec)
_laya_spec.loader.exec_module(_laya)
LAYA_FAILURE_SUFFIX = (b'LAYA_BLOCKED:FileNotFoundError\n' +
    '\x1b[0;31m✗\x1b[0m Laya preparation failed; backend writers unchanged, release evidence retained\n'.encode())


def validate_laya_failure_log(raw):
    success = b'RUNTIME_STATE_TRANSACTION_OK command=preflight-code result=current\n'
    env = '\x1b[0;32m✓\x1b[0m 现行 env 未改变；仅验证摘要与权限，未生成配置副本\n'.encode()
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 16_000_000
            or not raw.endswith(LAYA_FAILURE_SUFFIX) or raw.count(success) != 1 or raw.count(env) != 1
            or raw.index(success) >= raw.index(env) or raw.count(b'LAYA_BLOCKED:') != 1
            or any(value in raw for value in (b'RUNTIME_STATE_TRANSACTION_FAILED', b'command=prepare',
                b'command=install', b'command=commit', b'command=restore', b'phase=deactivation_started',
                b'phase=guard_started', b'phase=remote_writers_stopped', b'phase=remote_checkout_completed',
                b'LAYA_INSTALL_STEP', b'LAYA_PREPARED', b'LAYA_INSTALLED', b'systemctl stop'))):
        raise ProofError('exact Laya context failure before mutation required')


FAILURE_SUFFIX = ('RUNTIME_STATE_TRANSACTION_FAILED error=code-only requires migrated persistent state\n'
                  '\x1b[0;31m✗\x1b[0m runtime state 只读预检失败；服务与 live env 尚未变更，现场与租约保留\n').encode()
AUTHORITY = {
    'APP_ENV': 'production',
    'HEALTH_RUNTIME_DATA_DIR': '/var/lib/health-app/runtime',
    'HEALTH_GENE_KNOWLEDGE_PATH': '/var/lib/health-app/runtime/gene_knowledge.json',
    'HEALTH_EVIDENCE_RUNTIME_ENABLED': 'false',
}
STAGE_PATTERN = r'/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+'


def validate_failure_log(raw):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 16_000_000
            or not raw.endswith(FAILURE_SUFFIX)
            or raw.count(b'RUNTIME_STATE_TRANSACTION_FAILED') != 1
            or any(value in raw for value in (b'phase=env_staging_started', b'phase=deactivation_started',
                                              b'RUNTIME_STATE_TRANSACTION_COMMITTED'))):
        raise ProofError('exact pre-mutation failure log required')


def parse_manifest(raw):
    result = {}
    for line in raw.splitlines():
        match = re.fullmatch(rb'([0-9a-f]{64})  ([A-Za-z0-9._-]+)', line)
        if not match or match[2].decode() in result:
            raise ProofError('sealed manifest invalid')
        result[match[2].decode()] = match[1].decode()
    if set(result) != set(ARTIFACTS):
        raise ProofError('no-backup sealed inventory differs')
    return result


def validate_process_environment(raw):
    if len(raw) > 1_000_000:
        raise ProofError('process environment bound exceeded')
    fields = raw.split(b'\0')
    for key, value in AUTHORITY.items():
        matches = [item for item in fields if item.startswith(key.encode() + b'=')]
        if not matches and key == 'HEALTH_GENE_KNOWLEDGE_PATH':
            continue
        if matches != [(key + '=' + value).encode()]:
            raise ProofError('process external authority differs')


def temporal_environment_proof(ctime_ns, mtime_ns, receipt_ns, lease_ns, now_ns):
    if (any(type(value) is not int or value <= 0 for value in
            (ctime_ns, mtime_ns, receipt_ns, lease_ns, now_ns))
            or max(ctime_ns, mtime_ns) >= receipt_ns or receipt_ns >= lease_ns or lease_ns > now_ns):
        raise ProofError('environment chronology is not pre-release')
    return {'env_ctime_ns': ctime_ns, 'env_mtime_ns': mtime_ns,
            'receipt_ctime_ns': receipt_ns, 'lease_started_ns': lease_ns,
            'historical_env_digest_available': False}


class NoBackupPreflightProof(RecoveryProof):
    def __init__(self, source, bootstrap, server, failed_sha, production_sha, lease_token, *, unchanged=True, installed_laya=False, built_unuploaded=None):
        if unchanged is not True or installed_laya is not False or built_unuploaded is not None:
            raise ProofError('no-backup closure must be unchanged')
        super().__init__(source, bootstrap, server, failed_sha, production_sha, lease_token,
                         unchanged=True, installed_laya=True)
        self.no_backup_preflight = True
        self._closed = False

    def verify_closed(self, expected_snapshot):
        return verify_closed(self, expected_snapshot)

    def _units(self, old_source, transaction, *, started_at=None):
        # Project only the exact independently proven vision drop-in. All other
        # effective properties, including EnvironmentFiles, remain unmodified.
        raw_systemd = self.systemd
        raw_transaction_systemd = transaction.systemd
        overlay = _retained.inspect_vision_overlay(self.bootstrap, self.source, raw_systemd)
        view = _retained.VisionBaseView(raw_systemd, overlay['raw_dropins'])
        self.systemd = transaction.systemd = view
        try:
            units = super()._units(old_source, transaction, started_at=started_at)
        finally:
            self.systemd = raw_systemd
            transaction.systemd = raw_transaction_systemd
        if _retained.inspect_vision_overlay(self.bootstrap, self.source, raw_systemd) != overlay:
            raise ProofError('vision overlay changed during no-backup proof')
        units['vision_overlay'] = overlay
        return units

    def _lease_snapshot(self):
        if self._closed:
            return self._original_lease
        return super()._lease_snapshot()

    def _lease_read(self, name):
        if self._closed:
            return self._lease_contents[name]
        value = self._file(self.lease / name, 0o600)
        if not hasattr(self, '_lease_contents'):
            self._lease_contents = {}
        self._lease_contents[name] = value
        return value

    def _stage(self, failed_source):
        result = self._lease_snapshot().copy()
        if not hasattr(self, '_original_lease'):
            self._original_lease = result.copy()
        self._assert_original_lease()
        pointer, result['pointer'] = self._lease_read('stage')
        if re.fullmatch((STAGE_PATTERN + '\n').encode(), pointer) is None:
            raise ProofError('original stage pointer invalid')
        self.stage = Path(pointer.decode().rstrip('\n'))
        result['directory'] = self._directory(self.stage)
        if {p.name for p in self.stage.iterdir()} != set(ARTIFACTS) | {'staged.sha256'}:
            raise ProofError('no-backup stage must not contain copies')
        manifest, result['manifest'] = self._file(self.stage / 'staged.sha256', 0o400)
        for name, digest in parse_manifest(manifest).items():
            raw, identity = self._file(self.stage / name)
            if identity['gid'] != 0 or identity['sha256'] != digest or raw != self._file(failed_source / ARTIFACTS[name])[0]:
                raise ProofError('sealed canonical artifact differs')
            result[name] = identity
        env = self.production / 'backend/.env'
        before = env.lstat()
        raw, result['live_env'] = self._file(env, 0o640)
        after = env.lstat()
        if ((before.st_ctime_ns, before.st_mtime_ns) != (after.st_ctime_ns, after.st_mtime_ns)
                or result['live_env']['gid'] != grp.getgrnam('health-app').gr_gid):
            raise ProofError('live environment identity differs')
        try:
            lines = raw.decode().splitlines()
            for line in lines:
                if line.rstrip().endswith('\\'):
                    raise ValueError('continuation')
                shlex.split(line, comments=True, posix=True)
            for key, value in AUTHORITY.items():
                matches = [line for line in lines if re.match(r'\s*(?:export\s+)?' + key + r'\s*=', line)]
                if not matches and key == 'HEALTH_GENE_KNOWLEDGE_PATH':
                    continue
                if matches != [key + '=' + value]:
                    raise ValueError('authority')
        except (UnicodeError, ValueError):
            raise ProofError('live environment authority unsupported') from None
        started, _ = self._lease_read('started_at')
        self._started_text = started.decode()
        self._started = datetime.strptime(self._started_text, '%Y-%m-%dT%H:%M:%SZ\n').replace(tzinfo=UTC).timestamp()
        receipt = self.bootstrap.STATE / self.failed_sha / 'started.json'
        self._file(receipt, 0o600)
        self._chronology = temporal_environment_proof(before.st_ctime_ns, before.st_mtime_ns,
            receipt.lstat().st_ctime_ns, int(self._started * 1_000_000_000), time.time_ns())
        return result

    def running_services_snapshot(self):
        result = super().running_services_snapshot()
        for unit, fields in result.items():
            for pid, ticks in fields.get('processes', {}).items():
                process = self.proc / pid
                before = (process / 'stat').read_bytes().rsplit(b')', 1)[-1].split()
                with (process / 'environ').open('rb') as stream:
                    validate_process_environment(stream.read(1_000_001))
                after = (process / 'stat').read_bytes().rsplit(b')', 1)[-1].split()
                if len(before) < 20 or len(after) < 20 or before[19] != after[19] or before[19].decode() != ticks:
                    raise ProofError('process identity changed during authority proof')
        return result

    def _services_predate_release(self):
        boot = re.findall(r'^btime ([0-9]+)$', (self.proc / 'stat').read_text(), re.MULTILINE)
        if len(boot) != 1:
            raise ProofError('boot time unavailable')
        for unit, fields in self.running_snapshot().items():
            if ((unit.endswith('.service') and fields['NRestarts'] != '0')
                    or int(boot[0]) + int(fields['ActiveEnterTimestampMonotonic']) / 1_000_000 >= self._started - 60
                    or any(int(boot[0]) + int(ticks) / os.sysconf('SC_CLK_TCK') >= self._started - 60
                           for ticks in fields.get('processes', {}).values())):
                raise ProofError('running old generation does not predate release')

    def snapshot(self):
        failed = self.bootstrap.canonical_source(self.failed_sha)
        old = self.bootstrap.canonical_source(self.production_sha)
        self.reset._revision_proof(self.production_sha, self.source, self.bootstrap)
        binding = {relative: self._file(failed / relative)[1]['sha256'] for relative in FAILED_IMPLEMENTATIONS}
        if binding == FAILED_IMPLEMENTATIONS:
            profile, implementations = 'pre-mutation-no-copy-v1', FAILED_IMPLEMENTATIONS
        elif binding == {key: LAYA_FAILED_IMPLEMENTATIONS[key] for key in FAILED_IMPLEMENTATIONS}:
            binding['infra/laya/install.py'] = self._file(failed / 'infra/laya/install.py')[1]['sha256']
            if binding != LAYA_FAILED_IMPLEMENTATIONS:
                raise ProofError('failed Laya context implementation differs')
            profile, implementations = 'laya-context-missing-candidate', LAYA_FAILED_IMPLEMENTATIONS
        else:
            raise ProofError('failed implementation is not a reviewed independent profile')
        if profile == 'laya-context-missing-candidate':
            self._absent(self.bootstrap.STATE / self.failed_sha / 'deployment.env')
        result = {'workspace': self._workspace(failed), 'stage': self._stage(failed)}
        log, _ = self._file(self.bootstrap.STATE / self.failed_sha / 'deployment.log', 0o600)
        (validate_failure_log if profile == 'pre-mutation-no-copy-v1' else validate_laya_failure_log)(log)
        transaction = self.runtime.ReleaseTransaction(self.runtime.production_layout(self.stage), self.systemd)
        if not self._closed:
            transaction._assert_release_lock(self.lease, self.token)
        self._absent(transaction.layout.transaction_root, transaction._preparing_root())
        marker = transaction._load_terminal_marker()
        if marker['phase'] != 'COMMITTED' or marker['terminal_sha'] != self.production_sha:
            raise ProofError('production terminal differs')
        if list(self.runtime_root.glob('runtime-state-transaction.reap-*')):
            raise ProofError('terminal cleanup pending')
        self._absent(Path('/var/lib/reva-health-evidence-runtime/enabled.env'),
                     Path('/run/reva-health-evidence-activation'), self.production / 'backend/.env.reva-release.tmp')
        for unit in UNITS[1:]:
            self._absent(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf')
        transaction._validate_retained_knowledge_authority()
        _, result['terminal'] = self._file(transaction._terminal_marker_path())
        result['units'] = self._units(old, transaction, started_at=self._started_text)
        self._services_predate_release()
        result['no_backup_preflight'] = {
            'profile': profile, 'failed_sha': self.failed_sha,
            'production_sha': self.production_sha, 'original_stage': str(self.stage),
            'failed_implementations': dict(implementations),
            'chronology': self._chronology, 'started_at': self._started_text, 'historical_env_digest_available': False,
            'laya_install_not_reached': True,
        }
        if profile == 'laya-context-missing-candidate':
            try:
                result['no_backup_preflight']['laya_context'] = _laya.inspect(self, failed, old, result['stage']['live_env'])
            except Exception:
                raise ProofError('read-only Laya context proof failed') from None
        validate_snapshot(result)
        return result



def _validate_identity(value, *, directory=False, mode=None, group=0):
    keys = {'dev', 'ino', 'mode', 'uid', 'gid'} | (set() if directory else {'sha256'})
    if (not isinstance(value, dict) or set(value) != keys
            or any(type(value[key]) is not int or value[key] < 0 for key in keys - {'sha256'})
            or value['ino'] <= 0 or value['uid'] != 0
            or (group is not None and value['gid'] != group)
            or not 0 <= value['mode'] <= 0o777 or value['mode'] & 0o022
            or (mode is not None and value['mode'] != mode)
            or (not directory and (not isinstance(value['sha256'], str)
                or re.fullmatch(r'[0-9a-f]{64}', value['sha256']) is None))):
        raise ProofError('no-backup evidence identity differs')


def _validate_stage_snapshot(stage, marker):
    expected = {'lease', 'token', 'label', 'stage', 'started_at', 'pointer',
                'directory', 'live_env', 'manifest'} | set(ARTIFACTS)
    if not isinstance(stage, dict) or set(stage) != expected:
        raise ProofError('no-backup stage snapshot shape differs')
    for name, identity in stage.items():
        if name in {'lease', 'directory'}:
            _validate_identity(identity, directory=True, mode=0o700)
        elif name == 'live_env':
            _validate_identity(identity, mode=0o640, group=None)
        else:
            _validate_identity(identity, mode=0o400 if name == 'manifest' else
                               0o600 if name in {'token','label','stage','started_at','pointer'} else None)
    pointer_hash = hashlib.sha256((marker['original_stage'] + '\n').encode()).hexdigest()
    if (stage['pointer'] != stage['stage'] or stage['pointer']['sha256'] != pointer_hash
            or stage['label']['sha256'] != hashlib.sha256(b'deploy:backend\n').hexdigest()
            or stage['started_at']['sha256'] != hashlib.sha256(marker['started_at'].encode()).hexdigest()
            or stage['runtime_state_release_transaction.py']['sha256'] !=
                marker['failed_implementations']['backend/scripts/runtime_state_release_transaction.py']):
        raise ProofError('no-backup stage snapshot binding differs')


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {'workspace', 'stage', 'terminal', 'units', 'no_backup_preflight'}:
        raise ProofError('no-backup snapshot shape differs')
    marker = snapshot['no_backup_preflight']
    profile = marker.get('profile') if isinstance(marker, dict) else None
    implementations = (FAILED_IMPLEMENTATIONS if profile == 'pre-mutation-no-copy-v1' else
                       LAYA_FAILED_IMPLEMENTATIONS if profile == 'laya-context-missing-candidate' else None)
    additional = {'laya_context'} if profile == 'laya-context-missing-candidate' else set()
    if (not isinstance(marker, dict) or set(marker) != additional | {'profile', 'failed_sha', 'production_sha',
            'original_stage', 'failed_implementations', 'chronology', 'started_at', 'historical_env_digest_available', 'laya_install_not_reached'}
            or implementations is None
            or marker['failed_implementations'] != implementations
            or marker['historical_env_digest_available'] is not False or marker['laya_install_not_reached'] is not True
            or any(re.fullmatch(r'[0-9a-f]{40}', marker[key]) is None for key in ('failed_sha','production_sha'))
            or not isinstance(marker['started_at'], str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n', marker['started_at']) is None
            or marker['failed_sha'] == marker['production_sha']
            or re.fullmatch(STAGE_PATTERN, marker['original_stage']) is None):
        raise ProofError('no-backup marker differs')
    chronology = marker['chronology']
    if not isinstance(chronology, dict) or set(chronology) != {'env_ctime_ns','env_mtime_ns','receipt_ctime_ns','lease_started_ns','historical_env_digest_available'}:
        raise ProofError('no-backup chronology shape differs')
    expected = temporal_environment_proof(chronology['env_ctime_ns'], chronology['env_mtime_ns'],
        chronology['receipt_ctime_ns'], chronology['lease_started_ns'], time.time_ns())
    if int(datetime.strptime(marker['started_at'], '%Y-%m-%dT%H:%M:%SZ\n').replace(tzinfo=UTC).timestamp() * 1_000_000_000) != chronology['lease_started_ns']:
        raise ProofError('no-backup lease chronology binding differs')
    if chronology != expected or not all(isinstance(snapshot[key], dict) and snapshot[key] for key in ('workspace','stage','terminal','units')):
        raise ProofError('no-backup evidence incomplete')
    overlay = snapshot['units'].get('vision_overlay')
    if (not isinstance(overlay, dict) or set(overlay) != {'model', 'history', 'files', 'services', 'raw_dropins'}
            or overlay['model'] != 'qwen3.8-flash'
            or any(not isinstance(overlay[key], dict) or not overlay[key]
                   for key in ('history', 'files', 'services', 'raw_dropins'))):
        raise ProofError('no-backup vision evidence missing')
    _retained.VisionBaseView(None, overlay['raw_dropins'])
    _validate_stage_snapshot(snapshot['stage'], marker)
    _validate_identity(snapshot['terminal'])
    if additional:
        try:
            _laya.validate(marker['laya_context'], marker['failed_sha'], marker['production_sha'],
                chronology['lease_started_ns'], snapshot['stage']['live_env'])
        except Exception:
            raise ProofError('historical Laya context grammar differs') from None
    return marker


def verify_closed(proof, expected_snapshot):
    """Same owned instance only; caller separately validates the retired lease.

    Canonical executor/policy revocation changes workspace evidence, so compare
    all original stage, environment, terminal and unit evidence here. The caller
    must independently preserve/verify the original immutable workspace audits.
    """
    validate_snapshot(expected_snapshot)
    if not isinstance(proof, NoBackupPreflightProof) or not hasattr(proof, '_original_lease'):
        raise ProofError('same no-backup proof instance required')
    original_workspace = proof._workspace
    proof._workspace = lambda failed: expected_snapshot['workspace']
    proof._closed = True
    try:
        if proof.snapshot() != expected_snapshot:
            raise ProofError('closed preflight evidence changed')
    finally:
        proof._workspace = original_workspace
        proof._closed = False


def validate_archived_vision(bootstrap, source, snapshot):
    """Consume original vision audits and fixed public configuration evidence.

    This validates historical evidence without querying today's live services,
    reading backup trees, or involving Laya assets.
    """
    value = snapshot.get('units', {}).get('vision_overlay')
    _retained.validate_archived_vision(bootstrap, Path(source), value)
    marker = snapshot.get('no_backup_preflight', {})
    if marker.get('profile') == 'laya-context-missing-candidate':
        validate_snapshot(snapshot)
        try:
            _laya.validate_history(bootstrap, Path(source), marker['laya_context'])
        except Exception:
            raise ProofError('historical canonical Laya evidence differs') from None
