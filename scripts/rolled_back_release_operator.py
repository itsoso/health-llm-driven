"""Close an observed automatic rollback to old code; never deploy or resume.

Root-only canonical operator. Original NEEDS_OPERATOR remains immutable. A new
one-shot closure audit precedes exact consumed-key revocation. Runtime UNKNOWN,
paused state and generations are not settled by this lifecycle closure.
"""
import argparse
import fcntl
import hashlib
import grp
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/var/lib/reva-release')
RUNTIME = Path('/var/lib/health-app/release-state')
PRODUCTION = Path('/opt/health-app')
ROOT_NAME = 'rolled-back-release-closures'
TERMINAL = 'CLOSED_ROLLED_BACK_RELEASE'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}


class RetirementError(Exception):
    """Only static diagnostics may leave this secret-bearing operator."""


def require(value):
    if not value:
        raise RetirementError('rollback closure evidence invalid or incomplete')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(value, length=40):
    require(type(value) is str and re.fullmatch('[a-f0-9]{' + str(length) + '}', value) is not None)
    return value


def validate_terminal(marker, old, failed):
    sha(old)
    sha(failed)
    require(old != failed and type(marker) is dict)
    transaction = hashlib.sha256(f'{old}:{failed}'.encode()).hexdigest()[:32]
    require(type(marker.get('version')) is int and marker == {
        'version': 1, 'old_sha': old, 'candidate_sha': failed, 'terminal_sha': old,
        'target': 'old', 'phase': 'RESTORE_FINALIZED', 'result': 'RESTORE_FINALIZED',
        'transaction_id': transaction, 'reap_name': 'runtime-state-transaction.reap-' + transaction,
    })


def original_log(log, old):
    sha(old)
    require(type(log) is str and len(log) <= 16_000_000)
    require(not any(ord(c) < 32 and c not in '\n\t\r\x1b' for c in log))
    # ANSI decoration is allowed only around non-authoritative human progress;
    # the authoritative producer line must remain exact and undecorated.
    expected = (f'ROLLBACK_OK commit={old} kb_quarantine=passed schema_probe=passed '
                'auth_probe=passed services=active process_flag=false runtime_state=restored')
    require([line for line in log.splitlines() if 'ROLLBACK_OK' in line] == [expected])
    backups = [line for line in log.splitlines() if '并封存 release rollback env:' in line]
    require(len(backups) == 1)
    match = re.fullmatch(r'已备份到工作树外并封存 release rollback env: (/var/backups/health-app/env/\.env\.([0-9]{8}_[0-9]{6}))', backups[0])
    require(match is not None)
    datetime.strptime(match[2], '%Y%m%d_%H%M%S')
    mentions = set(re.findall(r'/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*', log))
    require(len(mentions) == 1)
    return Path(match[1]), Path(next(iter(mentions)))


def normalize_rollback_env(raw):
    """Exact original producer normalization, not an environment parser."""
    require(type(raw) is bytes and 0 < len(raw) <= 1_000_000 and b'\0' not in raw)
    lines = raw.splitlines(keepends=True)
    assignments = [line for line in lines if re.match(rb'^[ \t]*(export[ \t]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[ \t]*=', line)]
    require(len(assignments) <= 1)
    if assignments:
        require(assignments == [b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'])
        return raw
    require(raw.endswith(b'\n'))
    return raw + b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def helpers(b, source):
    return b_helper(b, source, 'retained_candidate_retirement.py', 'rollback_retained')


def b_helper(b, source, filename, name):
    path = source / 'scripts' / filename
    b.secure(path)
    require(not os.path.lexists(path.parent / '__pycache__'))
    return load(path, name)


def conflicts(b, failed):
    for name in ('recoveries', 'retained-candidate-closures', 'partial-laya-closures',
                 'contained-release-closures', 'unchanged-release-closures',
                 'review-maintenance-closures', 'lost-closure-receipt-acknowledgments',
                 'contained-service-recoveries', 'native-only-closures'):
        require(not os.path.lexists(b.STATE / name / failed))


def close_transaction(adapter, evidence_sha256=None):
    r = adapter.r
    require(not os.path.lexists(adapter.record))
    adapter.check_record_parent()
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_ROLLED_BACK_RELEASE', 'evidence_sha256': fingerprint}
    sha(evidence_sha256, 64)
    require(evidence_sha256 == fingerprint)
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        r.sync(adapter.record.parent.parent)
    adapter.check_record_parent()
    adapter.record.mkdir(mode=0o700)
    r.sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {**evidence, 'evidence_sha256': fingerprint,
              'receipt_sha256': hashlib.sha256(receipt.encode()).hexdigest()}
    r.write_json(adapter.record / 'intent.json', intent)
    # Any post-intent failure is permanent; no cleanup, recovery or rerun.
    require(adapter.inspect() == evidence)
    adapter.archive_preimage(evidence)
    adapter.retire_authorization(evidence)
    r.write_json(adapter.record / 'completed.json', {
        'state': TERMINAL, 'old_sha': evidence['old_sha'], 'intent_sha256': digest(intent),
    })
    return {'state': TERMINAL, 'sha': evidence['old_sha'], 'receipt': receipt}


def probe_child(old, failed, closing):
    """Canonical isolated, PostgreSQL read-only/rollback protected probes."""
    import contextlib
    source = ROOT / 'bootstrap' / closing / 'source'
    b = load(source / 'scripts/bootstrap_trusted_release.py', 'rollback_child_bootstrap')
    require(b.canonical_source(closing) == source)
    r = helpers(b, source)
    r.workspace_evidence(b, failed)
    validate_terminal(b._read_json(RUNTIME / 'runtime-state-terminal.json'), old, failed)
    reset = b_helper(b, source, 'trusted_review_reset.py', 'rollback_child_reset')
    server = b_helper(b, source, 'trusted_release_server.py', 'rollback_child_server')
    reset._assert_isolated_search_path()
    old_source = b.canonical_source(old)
    reset._revision_proof(old, old_source, b)
    reset._validate_application_imports(old_source, server)
    reset._validate_venv(server)
    sys.path.append('/opt/health-app/backend/venv/lib/python3.12/site-packages')
    environment = reset._parse_maintenance_environment(server.read_production_env())
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(old_source / 'backend')
    sys.path.insert(0, str(old_source / 'backend'))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(old_source, environment)
        schema_module = r.load(b, old_source / 'backend/scripts/verify_runtime_schema_compatibility.py', 'rollback_schema')
        schema_module.main()
        probe = r.load(b, old_source / 'backend/scripts/verify_runtime_only_kb_contract.py', 'rollback_kb')
        manifest = probe._load_manifest(Path('data/system_kb_v2_seed/review_manifest.json'))
        from app.database import SessionLocal
        with SessionLocal() as db:
            # Old code/manifest and OLD actor, but exact FAILED deployment window.
            value = r.quarantined_kb_probe(db, probe, manifest, old,
                datetime.fromtimestamp((b.STATE / failed / 'deployment-started.json').stat().st_mtime, UTC),
                datetime.fromtimestamp((b.STATE / failed / 'completed.json').stat().st_mtime, UTC),
                runtime_enabled=probe.settings.health_evidence_runtime_enabled)
    print(json.dumps(value, sort_keys=True))


def application_probes(b, source, old, failed, closing):
    code = ('import runpy; m=runpy.run_path(' + repr(str(source / 'scripts/rolled_back_release_operator.py'))
            + "); m['probe_child'](" + repr(old) + ',' + repr(failed) + ',' + repr(closing) + ')')
    result = subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', '-c', code],
        env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=180)
    require(len(result.stdout) <= 8192)
    value = json.loads(result.stdout)
    helpers(b, source).validate_quarantine_evidence(value, old)
    return value


def verify_loopback_private(b):
    b.secure(b.CONFIG / 'loopback.key', private=True)
    info = (b.CONFIG / 'loopback.key').lstat()
    require(info.st_gid == 0 and stat.S_IMODE(info.st_mode) == 0o600)
    derived = subprocess.run(['/usr/bin/ssh-keygen', '-y', '-f', str(b.CONFIG / 'loopback.key')],
        env=ENV, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=10).stdout
    require(len(derived) <= 4096)
    public = (b.CONFIG / 'loopback.pub').read_text().strip().split()
    require(derived.decode().strip().split()[:2] == public[:2])


class Adapter:
    def __init__(self, b, source, closing, failed, old, check):
        self.b, self.source, self.closing, self.failed, self.old, self.check = b, source, closing, failed, old, check
        self.r = helpers(b, source)
        self.record = b.STATE / ROOT_NAME / failed

    def check_record_parent(self):
        if os.path.lexists(self.record.parent):
            self.r.private_directory(self.b, self.record.parent)
        else:
            self.b.secure(self.record.parent.parent)

    def original(self):
        b, r = self.b, self.r
        original = r.workspace_evidence(b, self.failed)
        path = b.STATE / self.failed / 'deployment.log'
        b.secure(path, private=True)
        require(path.stat().st_size <= 16_000_000)
        raw = path.read_bytes()
        log = raw.decode('utf-8')
        backup, stage = original_log(log, self.old)
        # Successful automatic rollback cleanup deliberately removed this stage.
        require(not os.path.lexists(stage) and not os.path.lexists(Path(str(stage) + '.activation-state')))
        return original, backup, stage, hashlib.sha256(raw).hexdigest()

    def snapshot(self):
        b, r = self.b, self.r
        self.check()
        b._assert_idle()
        b._recovery_process_proof()
        r.assert_no_transaction(RUNTIME)
        marker = b._read_json(RUNTIME / 'runtime-state-terminal.json')
        validate_terminal(marker, self.old, self.failed)
        terminal_identity = b._recovery_file_identity(RUNTIME / 'runtime-state-terminal.json')
        require(terminal_identity['mode'] == 0o600 and terminal_identity['uid'] == 0 and terminal_identity['gid'] == 0)
        original, backup, stage, log_sha = self.original()
        old_source = b.canonical_source(self.old)
        b._recovery_production_proof(self.old, self.source)
        module = b_helper(b, self.source, 'contained_recovery_proof.py', 'rollback_service_proof')
        runtime = r.load(b, self.source / 'backend/scripts/runtime_state_release_transaction.py', 'rollback_runtime')
        proof = object.__new__(module.RecoveryProof)
        proof.proc, proof.cgroup = Path('/proc'), Path('/sys/fs/cgroup')
        proof.bootstrap, proof.source = b, self.source
        proof.production, proof.production_sha, proof.failed_sha = PRODUCTION, self.old, self.failed
        proof.systemd_root, proof.stage, proof.lease = Path('/etc/systemd/system'), stage, None
        proof.systemd, proof.runtime, proof.installed_laya = runtime.SubprocessSystemd(), runtime, True
        raw, backup_identity = proof._file(backup, 0o600)
        require(backup_identity['gid'] == grp.getgrnam('health-app').gr_gid)
        for parent in (backup.parent.parent, backup.parent):
            r.private_directory(b, parent)
        normalized = normalize_rollback_env(raw)
        live, live_identity = proof._file(PRODUCTION / 'backend/.env', 0o640)
        module.require_false(live)
        require(live == normalized)
        start = (b.STATE / self.failed / 'deployment-started.json').stat().st_mtime
        end = (b.STATE / self.failed / 'completed.json').stat().st_mtime
        # cp -p preserves the predecessor mtime/group. Filename and ctime
        # bind creation to the original window; mtime must merely not be future.
        created = datetime.strptime(backup.name[5:], '%Y%m%d_%H%M%S').timestamp()
        require(start < end and start <= created <= end
                and start <= backup.stat().st_ctime <= end
                and backup.stat().st_mtime <= end)
        # All activation aliases, pending artifacts and process flags fail closed.
        proof._absent(Path('/var/lib/reva-health-evidence-runtime/enabled.env'),
            Path('/run/reva-health-evidence-activation'), PRODUCTION / 'backend/.env.reva-release.tmp',
            *[Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf' for unit in module.UNITS[1:]])
        # The retained verifier validates present old configuration/Laya against
        # canonical old exports. Its Laya provenance marker is data, not the
        # runtime terminal; only validate_terminal above admits the actual old target.
        installer = r.load(b, self.source / 'infra/laya/install.py', 'rollback_laya_selector')
        exported = module.object_json(proof._file(installer.STATE / 'sources' / self.old / 'source.json', 0o400)[0])
        require(type(exported) is dict and set(exported) == {'sha', 'old_sha', 'old_has_decisions', 'files'} and exported['sha'] == self.old)
        sha(exported['old_sha'])
        require(exported['old_sha'] != self.old)
        configuration = r.candidate_configuration(b, self.source, self.old,
                                                  {'old_sha': exported['old_sha']}, proof, runtime)
        r.validate_configuration(b, self.source, self.old, configuration)
        services = proof.running_services_snapshot()
        return {'terminal': marker, 'terminal_identity': terminal_identity,
                'configuration': configuration, 'services': services,
                'environment': {'backup_path': str(backup), 'backup': backup_identity,
                    'normalized_sha256': hashlib.sha256(normalized).hexdigest(), 'live': live_identity,
                    'provenance': 'original-log-root-archived-preimage-v1'},
                'original_log_sha256': log_sha, 'workspace': original}

    def inspect(self):
        b, r = self.b, self.r
        self.check()
        self.check_record_parent()
        conflicts(b, self.failed)
        require(b.canonical_source(self.closing) == self.source)
        history = b._retired_history()
        b._assert_known_activity(history, self.failed)
        require(self.failed not in history and not any(os.path.lexists(p) for p in b._archives(self.failed)))
        before = self.snapshot()
        active = r.active_installation_evidence(b, self.failed, before['workspace']['executor_sha256'])
        verify_loopback_private(b)
        kb = application_probes(b, self.source, self.old, self.failed, self.closing)
        recovery = b_helper(b, self.source, 'recover_contained_services.py', 'rollback_http')
        recovery._http_probes()
        time.sleep(7)
        require(self.snapshot() == before)
        self.check()
        return {'old_sha': self.failed, 'production_sha': self.old, 'closing_sha': self.closing,
                'workspace': before['workspace'], 'active_installation': active,
                'installation': {'config': {k: v for k, v in active['config'].items() if k != 'loopback.key'}, 'library': active['library']},
                'live': before, 'kb_quarantine': kb,
                'launcher': b._recovery_file_identity(b.STATE / 'launcher.lock')}

    def archive_preimage(self, evidence):
        path = Path(evidence['live']['environment']['backup_path'])
        self.b.secure(path, private=True)
        require(self.b._recovery_file_identity(path) == evidence['live']['environment']['backup'])
        raw = path.read_bytes()
        fd = os.open(self.record / 'rollback.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        self.r.sync(self.record)
        require(hashlib.sha256(raw).hexdigest() == evidence['live']['environment']['backup']['sha256'])

    def retire_authorization(self, evidence):
        b, r = self.b, self.r
        self.check()
        require(self.snapshot() == evidence['live'])
        require(r.active_installation_evidence(b, self.failed, evidence['workspace']['executor_sha256']) == evidence['active_installation'])
        policy = b._read_json(b.CONFIG / 'authorized-release.json')
        public = [(b.CONFIG / n).read_text().strip() for n in ('cloud.pub', 'loopback.pub')]
        verify_loopback_private(b)
        expected = b.key_lines(policy['expires_at'], *public)
        retained = b''.join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
            if line.decode().rstrip('\r\n') not in expected)
        b._replace_authorized(retained)
        require(b.AUTHORIZED.read_bytes() == retained)
        require(b._inventory(b.CONFIG, evidence['active_installation']['config'].keys() - {'.'}) == evidence['active_installation']['config'])
        (b.CONFIG / 'loopback.key').unlink()
        r.sync(b.CONFIG)
        require(b._installation_evidence(self.failed, b.CONFIG, b.INSTALLED.parent) == evidence['installation'])
        require(self.snapshot() == evidence['live'])
        self.check()


def closed_evidence(b, failed, receipt, *, historical=False):
    conflicts(b, failed)
    root = b.STATE / ROOT_NAME / failed
    r = helpers(b, Path(__file__).absolute().parents[1])
    r.private_directory(b, root.parent)
    r.private_directory(b, root)
    b._inventory(root, {'intent.json', 'completed.json', 'rollback.env'})
    intent, completed = b._read_json(root / 'intent.json'), b._read_json(root / 'completed.json')
    fields = {'old_sha', 'production_sha', 'closing_sha', 'workspace', 'active_installation', 'installation', 'live', 'kb_quarantine', 'launcher', 'evidence_sha256', 'receipt_sha256'}
    require(type(intent) is dict and set(intent) == fields and intent['old_sha'] == failed)
    for k in ('old_sha', 'production_sha', 'closing_sha'): sha(intent[k])
    require(len({intent[k] for k in ('old_sha', 'production_sha', 'closing_sha')}) == 3)
    require(intent['evidence_sha256'] == digest({k: v for k, v in intent.items() if k not in {'evidence_sha256', 'receipt_sha256'}}))
    require(completed == {'state': TERMINAL, 'old_sha': failed, 'intent_sha256': digest(intent)})
    sha(receipt, 64)
    sha(intent['receipt_sha256'], 64)
    require(secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), intent['receipt_sha256']))
    source = b.canonical_source(intent['closing_sha'])
    r = helpers(b, source)
    validate_terminal(intent['live']['terminal'], intent['production_sha'], failed)
    r.validate_quarantine_evidence(intent['kb_quarantine'], intent['production_sha'])
    r.validate_configuration(b, source, intent['production_sha'], intent['live']['configuration'])
    require(r.workspace_evidence(b, failed) == intent['workspace'] == intent['live']['workspace'])
    log_raw = (b.STATE / failed / 'deployment.log').read_bytes()
    backup, _ = original_log(log_raw.decode(), intent['production_sha'])
    require(hashlib.sha256(log_raw).hexdigest() == intent['live']['original_log_sha256'])
    environment = intent['live']['environment']
    require(environment['backup_path'] == str(backup) and environment['provenance'] == 'original-log-root-archived-preimage-v1')
    b.secure(root / 'rollback.env', private=True)
    raw = (root / 'rollback.env').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == environment['backup']['sha256'])
    require(hashlib.sha256(normalize_rollback_env(raw)).hexdigest() == environment['normalized_sha256'] == environment['live']['sha256'])
    active = intent['active_installation']
    require(intent['installation'] == {'config': {k: v for k, v in active['config'].items() if k != 'loopback.key'}, 'library': active['library']} and 'loopback.key' in active['config'])
    config, library = b._archives(failed)
    if not os.path.lexists(config) and not os.path.lexists(library): config, library = b.CONFIG, b.INSTALLED.parent
    require(b._installation_evidence(failed, config, library) == intent['installation'])
    require(b._recovery_file_identity(b.STATE / 'launcher.lock') == intent['launcher'])
    if not historical:
        current = Adapter(b, source, intent['closing_sha'], failed, intent['production_sha'], lambda: None)
        require(current.snapshot() == intent['live'])
    return {'state': TERMINAL, 'closure': digest(completed), 'workspace': intent['workspace']}


def context(closing):
    sha(closing)
    require(sys.platform == 'linux' and os.geteuid() == 0 and 'SSH_ORIGINAL_COMMAND' not in os.environ
            and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and sys.executable == '/usr/bin/python3.12')
    source = ROOT / 'bootstrap' / closing / 'source'
    entry = source / 'scripts/rolled_back_release_operator.py'
    require(Path(__file__).absolute() == entry)
    for path in [*reversed(entry.parents), entry, entry.with_name('bootstrap_trusted_release.py')]:
        info = path.lstat()
        require(info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o022
            and (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) and not stat.S_ISLNK(info.st_mode)
            and (not stat.S_ISREG(info.st_mode) or info.st_nlink == 1))
    require(not os.path.lexists(entry.parent / '__pycache__'))
    os.umask(0o077)
    b = load(entry.with_name('bootstrap_trusted_release.py'), 'rollback_bootstrap')
    b.use_system_timezone()
    require(b.canonical_source(closing) == source)
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'), '--sha', closing, '--workflow-sha', closing],
        env=ENV, check=True, timeout=90, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return b, source


def protected_receipt_output(closing):
    """Mutation results go only to a fresh root-private protected file."""
    info = os.fstat(1)
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_gid == 0
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and info.st_size == 0 and os.lseek(1, 0, os.SEEK_CUR) == 0)
    target = Path(os.readlink('/proc/self/fd/1'))
    require(target.parent == ROOT / 'operator-receipts' / closing
            and re.fullmatch(r'closure-[a-f0-9]{32}\.json', target.name) is not None)
    require(target.is_absolute() and target.lstat().st_ino == info.st_ino
            and target.lstat().st_dev == info.st_dev)
    parent = target.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and parent.st_gid == 0
            and stat.S_IMODE(parent.st_mode) == 0o700)
    for ancestor in target.parent.parents:
        metadata = ancestor.lstat()
        shared_tmp = ancestor == Path('/tmp') and stat.S_IMODE(metadata.st_mode) == 0o1777
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_gid == 0
                and (not metadata.st_mode & 0o022 or shared_tmp))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RetirementError('invalid operator arguments')


def main():
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--failed-sha', required=True)
    parser.add_argument('--production-sha', required=True)
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    for value in (args.sha, args.failed_sha, args.production_sha): sha(value)
    require(len({args.sha, args.failed_sha, args.production_sha}) == 3)
    if args.evidence_sha256 is not None:
        sha(args.evidence_sha256, 64)
        protected_receipt_output(args.sha)
    b, source = context(args.sha)
    b.secure(b.STATE / 'launcher.lock', private=True)
    fd = os.open(b.STATE / 'launcher.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def check():
            b._assert_original_lock(b.STATE / 'launcher.lock', fd)
            require(not os.path.lexists(b.STATE / args.failed_sha / 'build.lock'))
        print(json.dumps(close_transaction(Adapter(b, source, args.sha, args.failed_sha, args.production_sha, check), args.evidence_sha256), sort_keys=True), flush=True)
        if args.evidence_sha256 is not None:
            os.fsync(1)
    finally:
        os.close(fd)


def cli():
    try:
        main()
        return 0
    except Exception:
        print(json.dumps({'state': 'ROLLED_BACK_RELEASE_CLOSURE_BLOCKED', 'retry_allowed': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(cli())
