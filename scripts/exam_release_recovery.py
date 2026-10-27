"""Fixed-incident forward recovery coordinator; never a deployment retry.

The production adapter must hold the original launcher/build locks throughout.
It owns canonical-source/CI admission and the exact failed-release proof. This
coordinator never releases the business lease or changes the failed receipt.
"""
import hashlib
import json
import re


class RecoveryBlocked(RuntimeError):
    """Sanitized operator failure; original evidence must remain available."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def recover(adapter, expected_digest=None):
    if expected_digest is not None and re.fullmatch(r'[a-f0-9]{64}', expected_digest) is None:
        raise RecoveryBlocked('exact inspection digest required')
    evidence = {
        'admission': adapter.admission(),
        'database': adapter.database_inspect(),
        'stopped': adapter.stopped_proof(),
    }
    fingerprint = digest(evidence)
    if expected_digest is None:
        return {'state': 'INSPECTED', 'evidence_sha256': fingerprint}
    if expected_digest != fingerprint:
        raise RecoveryBlocked('inspection evidence changed; no recovery consumed')
    # O_EXCL must precede every mutation. Existing intent, including a partial
    # failure after database commit, is not permission to repeat this sequence.
    adapter.consume_intent(evidence, fingerprint)
    stage = 'authorization'
    try:
        adapter.assert_authorized()
        stage = 'database'
        database = adapter.database_recover()
        adapter.stopped_proof()
        stage = 'candidate_preflight'
        adapter.candidate_preflight()
        adapter.assert_authorized()
        # Runtime commit requires active services. Keep the boot gate armed
        # while starting and proving the candidate; never call old restore.
        stage = 'start_services'
        adapter.start_services()
        stage = 'guard_proof'
        guard = adapter.guard_proof()
        adapter.assert_authorized()
        stage = 'commit_runtime'
        adapter.commit_runtime()
        stage = 'terminal_proof'
        terminal = adapter.terminal_proof()
        adapter.assert_authorized()
        stage = 'finalize_runtime'
        adapter.finalize_runtime()
        stage = 'finalized_proof'
        finalized = adapter.finalized_proof()
        result = {'state': 'RECOVERED_CANDIDATE', 'evidence_sha256': fingerprint,
                  'database': database, 'guard': guard, 'terminal': terminal,
                  'finalized': finalized}
        stage = 'record_success'
        adapter.record_success(result)
        return result
    except BaseException:
        # No stop/rollback guess after a partial operation: preserve journal,
        # intent and original lease for stage-specific operator diagnosis.
        adapter.record_failure({'state': 'NEEDS_OPERATOR', 'stage': stage,
                                'evidence_sha256': fingerprint})
        raise RecoveryBlocked('forward recovery incomplete; preserve original lease and all evidence') from None


# The CLI is deliberately bound to one incident. The original release executor
# is neither invoked nor re-authorized by this operator.
import argparse
import fcntl
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import copy

ROOT = Path('/var/lib/reva-release')
FAILED_SHA = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
OLD_SHA = '83876750fcbb404255b7439482688fee82a490d4'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def context(sha):
    if (re.fullmatch('[a-f0-9]{40}', sha or '') is None or sha in (FAILED_SHA, OLD_SHA)
            or os.geteuid() != 0 or sys.platform != 'linux'
            or sys.executable != '/usr/bin/python3.12'
            or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
            or 'SSH_ORIGINAL_COMMAND' in os.environ):
        raise RecoveryBlocked('isolated root canonical operator required')
    source = ROOT / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/exam_release_recovery.py'
    if Path(__file__).absolute() != entry:
        raise RecoveryBlocked('fixed canonical operator required')
    for path in [*reversed(entry.parents), entry, entry.with_name('bootstrap_trusted_release.py')]:
        info = path.lstat()
        if (info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                or stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
            raise RecoveryBlocked('unsafe canonical path')
    if os.path.lexists(entry.parent / '__pycache__'):
        raise RecoveryBlocked('cached operator code forbidden')
    os.umask(0o077)
    bootstrap = load(entry.with_name('bootstrap_trusted_release.py'), 'exam_recovery_bootstrap')
    if bootstrap.canonical_source(sha) != source:
        raise RecoveryBlocked('canonical source differs')
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
                    '--sha', sha, '--workflow-sha', sha], env=ENV, check=True, timeout=90,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return source, bootstrap


def validate_finalized_terminal(retained, marker):
    if (not isinstance(marker, dict) or marker.get('mode') != 'code-only-no-backup'
            or marker.get('old_sha') != OLD_SHA or marker.get('candidate_sha') != FAILED_SHA):
        raise RecoveryBlocked('fixed no-backup terminal binding differs')
    retained.validate_terminal(marker, FAILED_SHA)


class ArmedEnablementView:
    """Project only journal enablement after the real boot gate was proved.

    The existing configuration proof assumes an enabled finalized candidate.
    Every actual command, security property and drop-in still comes from systemd.
    """
    def __init__(self, systemd, original):
        self.systemd, self.original = systemd, original

    def is_enabled(self, unit):
        if unit not in self.original or self.original[unit] != 'enabled':
            raise RecoveryBlocked('original candidate enablement differs')
        return self.original[unit]

    def __getattr__(self, name):
        return getattr(self.systemd, name)


class ProductionAdapter:
    def __init__(self, source, bootstrap, sha, token, launcher_fd, build_fd):
        self.source, self.b, self.sha, self.token = source, bootstrap, sha, token
        self.launcher_fd, self.build_fd = launcher_fd, build_fd
        self.audit = ROOT / ('exam-service-recovery-' + FAILED_SHA)
        self.server = self.module('scripts/trusted_release_server.py', 'exam_recovery_server')
        self.service = self.module('scripts/recover_contained_services.py', 'exam_recovery_services')
        self.retained = self.module('scripts/retained_candidate_retirement.py', 'exam_recovery_retained')
        self.h = self.module('scripts/exam_attempts_release.py', 'exam_recovery_helper')
        self.db_record = self.h.STATE / ('recovery-' + FAILED_SHA)
        self.core = self.module('scripts/exam_attempts_recovery.py', 'exam_recovery_core')
        self.pmod = self.module('scripts/contained_recovery_proof.py', 'exam_recovery_proof')
        self.proof = self.pmod.RecoveryProof(source, bootstrap, self.server, FAILED_SHA, OLD_SHA, token,
                                               unchanged=False, installed_laya=False)
        self.runtime = self.proof.runtime
        self.proof._original_lease = self.proof._lease_snapshot()
        pointer = self.proof._file(self.proof.lease / 'stage', 0o600)[0]
        if re.fullmatch(rb'/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+\n', pointer) is None:
            raise RecoveryBlocked('fixed original stage required')
        self.proof.stage = Path(pointer.decode().strip())
        self.tx = self.runtime.ReleaseTransaction(self.runtime.production_layout(self.proof.stage),
                                                   self.proof.systemd, code_only=True)
        self.engines = None

    def module(self, relative, name):
        path = self.source / relative
        self.b.secure(path)
        if os.path.lexists(path.parent / '__pycache__'):
            raise RecoveryBlocked('cached canonical helper forbidden')
        return load(path, name)

    def assert_authorized(self):
        self.b._assert_original_lock(ROOT / 'launcher.lock', self.launcher_fd)
        self.service._check_original_build_lock(self.b, FAILED_SHA, self.build_fd)
        self.b._recovery_process_proof()
        self.proof._assert_original_lease()
        self.b._recovery_production_proof(FAILED_SHA, self.source)
        if self.proof._workspace(self.b.canonical_source(FAILED_SHA)) != self.workspace:
            raise RecoveryBlocked('original failed release evidence changed')

    def admission(self):
        if os.path.lexists(self.audit):
            raise RecoveryBlocked('recovery already consumed; inspect retained evidence')
        failed = self.b.canonical_source(FAILED_SHA)
        self.workspace = self.proof._workspace(failed)
        self.assert_authorized()
        # Bind the sealed no-backup stage without importing or executing it.
        expected = set(self.pmod.ARTIFACTS) | {'staged.sha256'}
        self.proof._directory(self.proof.stage)
        if {p.name for p in self.proof.stage.iterdir()} != expected:
            raise RecoveryBlocked('no-backup stage inventory differs')
        raw = self.proof._file(self.proof.stage / 'staged.sha256', 0o400)[0]
        manifest = {}
        for line in raw.splitlines():
            match = re.fullmatch(rb'([a-f0-9]{64})  ([A-Za-z0-9._-]+)', line)
            if not match or match[2].decode() in manifest:
                raise RecoveryBlocked('sealed stage manifest differs')
            manifest[match[2].decode()] = match[1].decode()
        if set(manifest) != set(self.pmod.ARTIFACTS):
            raise RecoveryBlocked('sealed stage manifest inventory differs')
        for name, relative in self.pmod.ARTIFACTS.items():
            data = self.proof._file(self.proof.stage / name)[0]
            if hashlib.sha256(data).hexdigest() != manifest[name] or data != self.proof._file(failed / relative)[0]:
                raise RecoveryBlocked('sealed stage canonical bytes differ')
        # Runtime helper must be identical to the one that prepared the journal.
        if (self.source / 'backend/scripts/runtime_state_release_transaction.py').read_bytes() != (failed / 'backend/scripts/runtime_state_release_transaction.py').read_bytes():
            raise RecoveryBlocked('runtime transaction implementation changed')
        self.journal = self.tx._load_journal()
        if (self.journal['version'] != 2 or self.journal['phase'] != 'INSTALLED'
                or self.journal['old_sha'] != OLD_SHA or self.journal['candidate_sha'] != FAILED_SHA
                or self.journal['release_target'] is not None or self.journal['boot_gate_released']):
            raise RecoveryBlocked('fixed installed transaction required')
        self.tx._verify_boot_gate_armed(self.journal)
        self.tx._validate_candidate_effective(self.journal)
        self.tx._validate_old_effective(self.journal)
        self.pmod.require_false(self.proof._file(Path('/opt/health-app/backend/.env'), 0o640)[0])
        self.proof._absent(Path('/var/lib/reva-health-evidence-runtime/enabled.env'),
                           Path('/run/reva-health-evidence-activation'),
                           Path('/opt/health-app/backend/.env.reva-release.tmp'))
        self.tx._verify_upload_authority(self.journal, target='candidate')
        return {'publisher_sha': self.sha, 'failed_sha': FAILED_SHA, 'old_sha': OLD_SHA,
                'workspace': self.workspace, 'lease': self.proof._original_lease,
                'journal': self.journal, 'manifest': manifest}

    def stopped_proof(self):
        self.proof.stopped()
        return {'writers': 'inactive'}

    def database(self, mutate):
        if self.engines is None:
            reset = self.module('scripts/trusted_review_reset.py', 'exam_recovery_venv')
            reset._validate_venv(self.server)
            sys.path.append('/opt/health-app/backend/venv/lib/python3.12/site-packages')
            for path in reversed(self.h.CREDENTIAL.parents):
                self.h.secure(path, directory=True)
            migration_url = self.h.parse_migration_env(self.h.protected_read(self.h.CREDENTIAL, private=True))
            os.environ.clear()
            os.environ.update(ENV)
            os.chdir('/opt/health-app/backend')
            config = self.source / 'backend/app/config.py'
            settings = self.h.load_runtime_settings(self.h.protected_read(config), config)
            if settings.app_env.lower() != 'production':
                raise RecoveryBlocked('production settings required')
            from sqlalchemy import create_engine
            self.engines = (create_engine(migration_url, hide_parameters=True),
                            create_engine(settings.effective_database_url, hide_parameters=True))
        method = self.core.recover if mutate else self.core.inspect
        return method(self.h, *self.engines, self.source, self.db_record, self.sha, self.token, self.assert_authorized)

    def database_inspect(self):
        return self.database(False)

    def database_recover(self):
        return self.database(True)

    def consume_intent(self, evidence, fingerprint):
        self.assert_authorized()
        self.audit.mkdir(mode=0o700)
        self.h.sync_directory(ROOT)
        self.h.write_once(self.audit / 'intent.json', {'publisher_sha': self.sha,
            'evidence_sha256': fingerprint, 'evidence': evidence})

    def candidate_preflight(self):
        self.service._application_probes(FAILED_SHA, self.sha)

    def configuration_proof(self):
        journal = self.tx._load_journal()
        proof = copy.copy(self.proof)
        if not journal['boot_gate_released']:
            self.tx._verify_boot_gate_armed(journal)
            proof.systemd = ArmedEnablementView(proof.systemd, journal['original_enablement'])
        return self.retained.candidate_configuration(self.b, self.source, FAILED_SHA,
                                                     journal, proof, self.runtime)

    def start_services(self):
        self.tx._verify_boot_gate_armed(self.tx._load_journal())
        for unit in self.pmod.UNITS:
            self.service._systemctl('start', unit)

    def guard_proof(self):
        self.tx._validate_candidate_effective(self.tx._load_journal())
        self.candidate_preflight()
        self.service._http_probes()
        configuration = self.configuration_proof()
        before = self.proof.running_snapshot()
        time.sleep(7)
        if self.proof.running_snapshot() != before:
            raise RecoveryBlocked('candidate process generation unstable')
        # Existing exact Laya source, receipt, service, network and vision proof.
        laya = self.retained.candidate_laya(self.b, self.source, FAILED_SHA, self.journal, self.proof)
        return {'services': before, 'configuration': configuration, 'laya': laya, 'schema': True, 'runtime_only_kb': True,
                'health_dependencies': True, 'unauthenticated_401': True}

    def commit_runtime(self):
        self.tx.commit(FAILED_SHA, self.proof.lease, self.token)

    def terminal_proof(self):
        result = self.guard_proof()
        result['configuration'] = self.retained.candidate_configuration(self.b, self.source,
            FAILED_SHA, self.journal, copy.copy(self.proof), self.runtime)
        return result

    def finalize_runtime(self):
        self.tx.finalize(FAILED_SHA, self.b.BUSINESS_LEASE, self.token)

    def finalized_proof(self):
        marker = self.tx._load_terminal_marker()
        validate_finalized_terminal(self.retained, marker)
        if self.tx.layout.transaction_root.exists():
            raise RecoveryBlocked('runtime finalization incomplete')
        self.assert_authorized()
        return {'terminal': marker, 'original_lease_preserved': True}

    def record_success(self, result):
        self.h.write_once(self.audit / 'completed.json', result)

    def record_failure(self, result):
        self.h.write_once(self.audit / 'failed.json', result)


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--sha', required=True)
        parser.add_argument('--evidence-sha256')
        args = parser.parse_args()
        source, bootstrap = context(args.sha)
        raw = sys.stdin.buffer.read(257)
        if re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', raw) is None:
            raise RecoveryBlocked('original lease token on stdin required')
        lock = ROOT / 'launcher.lock'
        bootstrap.secure(lock, private=True)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        build_fd, adapter = None, None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            build_fd = bootstrap._acquire_existing_build_lock(FAILED_SHA)
            adapter = ProductionAdapter(source, bootstrap, args.sha, raw[:-1].decode(), fd, build_fd)
            result = recover(adapter, args.evidence_sha256)
            print(json.dumps(result, sort_keys=True))
        finally:
            if adapter is not None and adapter.engines is not None:
                for engine in adapter.engines:
                    engine.dispose()
            if build_fd is not None:
                os.close(build_fd)
            os.close(fd)
        return 0
    except BaseException as error:
        trace, line = error.__traceback__, None
        while trace is not None:
            if trace.tb_frame.f_code.co_filename == __file__:
                line = trace.tb_lineno
            trace = trace.tb_next
        # Code position only: never driver errors, SQL, argv, locals or tokens.
        print('EXAM_FORWARD_RECOVERY_DIAGNOSTIC: ' + json.dumps({'operator_line': line}), file=sys.stderr)
        print('EXAM_FORWARD_RECOVERY_BLOCKED: preserve original lease, failure and recovery evidence', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
