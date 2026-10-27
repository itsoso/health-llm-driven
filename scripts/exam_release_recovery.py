#!/usr/bin/env python3
"""One fixed forward recovery of a8's post-checkout exam migration failure.

Default is read-only inspection. This is not deploy.sh, retry authority, a
checkout operation, or release closure. Original immutable evidence, installed
release authorization and business lease survive even a successful recovery.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.request

FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
PREVIOUS = '83876750fcbb404255b7439482688fee82a490d4'
ATTEMPT = 'exam-a8-forward-acl-v1'
JOURNAL_PIN = '79c9088df6c9861eabb07806b05809be7e977ac76b4ca841401e424348bd1c8f'
INTENT_PIN = '0c0e14c8537aac6f3eccb74fa18b7a13a338d2cbe685ba71062b576043f2c589'
STATE = Path('/var/lib/reva-release')
LIVE = Path('/opt/health-app')
UNITS = ('health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service')
VISION_STATIC_PROPERTIES = ('EnvironmentFiles', 'DropInPaths', 'UnsetEnvironment', 'User',
    'Group', 'WorkingDirectory', 'NoNewPrivileges', 'ProtectSystem', 'ProtectHome',
    'PrivateTmp', 'CapabilityBoundingSet')
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
       'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'}


class RecoveryError(RuntimeError):
    """Static, secret-free messages only."""


def need(condition, message='fixed recovery evidence rejected'):
    if not condition:
        raise RecoveryError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write((json.dumps(value, sort_keys=True) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def validate_journal(value):
    expected = {'version': 2, 'mode': 'code-only-no-backup', 'phase': 'INSTALLED',
                'candidate_sha': FAILED, 'old_sha': PREVIOUS, 'boot_gate_armed': True,
                'boot_gate_released': False, 'release_target': None}
    need(isinstance(value, dict) and all(type(value.get(k)) is type(v) and value.get(k) == v
                                       for k, v in expected.items()))
    need(not {'snapshots', 'metadata'} & value.keys())


def dependency_digest(path, bootstrap):
    bootstrap.secure(path)
    before = path.lstat()
    fields = ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    need(before.st_size <= 128 * 1024 * 1024, 'dependency file exceeds bound')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    value = hashlib.sha256()
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        need(all(getattr(before,k) == getattr(opened,k) for k in fields))
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
        after = os.fstat(stream.fileno())
    named = path.lstat()
    need(all(getattr(before,k) == getattr(after,k) == getattr(named,k) for k in fields), 'dependency changed during read')
    return value.hexdigest()


def validate_pi_lock(canonical, installed):
    need(canonical.get('lockfileVersion') == installed.get('lockfileVersion') == 3)
    expected, actual = canonical.get('packages'), installed.get('packages')
    need(isinstance(expected, dict) and isinstance(actual, dict) and '' in expected)
    required = {key for key, value in expected.items() if key and not value.get('dev') and not value.get('optional')}
    need(required <= actual.keys() and actual.keys() <= expected.keys() - {''}, 'Pi installed package inventory differs')
    for key, value in actual.items():
        need(isinstance(key, str) and key.startswith('node_modules/') and
             not any(part in ('', '.', '..') for part in Path(key).parts))
        need(isinstance(value, dict) and not value.get('link') and
             all(value.get(field) == expected[key].get(field) for field in ('version','resolved','integrity')),
             'Pi installed package lock differs')
    return sorted(actual)


def health_summary(report):
    need(isinstance(report, dict), 'health score JSON contract rejected')
    score = report.get('total_score')
    need(type(score) in (int,float) and math.isfinite(score) and 35 <= score <= 60 and
         report.get('max_possible') == 60 and report.get('threshold') == 35 and
         report.get('pass') is True and report.get('critical_failures') == [],
         'canonical health score hard gate failed')
    dimensions = report.get('dimensions')
    need(isinstance(dimensions, dict) and isinstance(dimensions.get('agent_runtime_circuit'),dict))
    circuit = dimensions['agent_runtime_circuit']
    detail, deferred = circuit.get('detail'), report.get('deferred_failures')
    need(isinstance(detail,str) and circuit.get('release_safe') is True)
    if circuit.get('healthy') is False:
        match = re.fullmatch(r'paused:reconciliation_detected:generation=([0-9]+):ack=([0-9]+)', detail)
        need(deferred == ['agent_runtime_circuit'] and match is not None)
        generation, acknowledged = map(int,match.groups())
        need(0 <= acknowledged < generation, 'runtime pause proof failed')
        paused = True
    else:
        need(circuit.get('healthy') is True and deferred == [])
        if detail not in ('disabled','not_initialized'):
            match = re.fullmatch(r'active:(?:none|manual_resume):generation=([0-9]+):ack=([0-9]+)',detail)
            need(match is not None and int(match[1]) == int(match[2]))
        paused = False
    return {'score':score, 'maximum':60, 'critical_failures':[],
            'runtime_pause_preserved':paused, 'runtime':detail}


def manifest_summary(payload, expected):
    need(isinstance(payload,dict) and isinstance(payload.get('skills'),list) and expected,
         'skills manifest unavailable')
    values = payload['skills']
    need(all(isinstance(item,dict) and isinstance(item.get('slug'),str) for item in values))
    slugs = [item['slug'] for item in values]
    need(len(slugs) == len(expected) and len(slugs) == len(set(slugs)) and set(slugs) == set(expected),
         'skills manifest differs from canonical a8')
    return {'count':len(slugs), 'slugs_sha256':digest(sorted(slugs))}


def recover(adapter, evidence_sha256=None, *, accept=False):
    """No resume path: once mkdir succeeds any unknown result is operator-only."""
    need((evidence_sha256 is not None) == accept, 'digest and fixed authorization required together')
    need(evidence_sha256 is None or re.fullmatch('[a-f0-9]{64}', evidence_sha256), 'invalid inspection digest')
    need(not os.path.lexists(adapter.audit), 'fixed recovery already attempted; retry forbidden')
    before = adapter.snapshot()
    adapter.stopped()
    database = adapter.preflight()
    need(database.get('database_state') == 'PENDING', 'only proven pending original migration is admitted')
    need(adapter.snapshot() == before, 'inspection evidence changed')
    adapter.stopped()
    evidence = {'attempt': ATTEMPT, 'recovery_sha': adapter.recovery_sha,
                'failed_sha': FAILED, 'previous_sha': PREVIOUS,
                'original': before, 'database': database}
    inspection = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED', 'attempt': ATTEMPT, 'evidence_sha256': inspection,
                'recovery_sha': adapter.recovery_sha, 'restored_source_sha': FAILED}
    need(evidence_sha256 == inspection, 'inspection digest changed')
    adapter.audit.mkdir(mode=0o700)
    sync(adapter.audit.parent)
    phase = 'intent'
    try:
        write_once(adapter.audit / 'intent.json', {**evidence, 'evidence_sha256': inspection})
        need(adapter.snapshot() == before, 'original evidence changed after intent')
        adapter.stopped()
        phase = 'database'
        plan = {'attempt': ATTEMPT, 'recovery_sha': adapter.recovery_sha,
                'source_sha': FAILED, 'original_intent_sha256': INTENT_PIN,
                'original_journal_sha256': JOURNAL_PIN, 'evidence_sha256': inspection}
        write_once(adapter.audit / 'database-started.json', plan)
        committed = adapter.database_apply(plan)
        need(adapter.readback(plan) == committed, 'database committed readback differs')
        write_once(adapter.audit / 'database-completed.json', committed)
        need(adapter.snapshot() == before, 'original evidence changed after database commit')
        phase = 'candidate_guards'
        adapter.candidate_guards()
        adapter.stopped()
        need(adapter.snapshot() == before, 'candidate guards changed original evidence')
        phase = 'start'
        adapter.start()
        phase = 'stable_guards'
        adapter.stable()
        adapter.candidate_guards()
        adapter.http()
        adapter.stable()
        need(adapter.snapshot() == before, 'post-start original evidence changed')
        phase = 'runtime_commit'
        adapter.commit_runtime()
        phase = 'runtime_finalize'
        terminal = adapter.finalize_runtime()
        need(terminal.get('terminal_sha') == FAILED, 'runtime finalized a different candidate')
        phase = 'final_health'
        health = adapter.http()
        stable = adapter.stable()
        need(adapter.snapshot() == before, 'immutable evidence changed after runtime finalization')
        result = {'state': 'FORWARD_RECOVERED', 'attempt': ATTEMPT,
                  'recovery_sha': adapter.recovery_sha, 'production_sha': FAILED,
                  'previous_sha': PREVIOUS, 'original_release_state': 'NEEDS_OPERATOR',
                  'original_lease_and_authorization_preserved': True,
                  'notification_fix_deployed': False, 'evidence_sha256': inspection,
                  'database': committed, 'runtime_terminal': terminal, 'stable_services': stable,
                  'health_guards': health}
        phase = 'completed'
        write_once(adapter.audit / 'completed.json', result)
        return result
    except BaseException:
        containment = 'PROVEN'
        try:
            adapter.stop()
        except BaseException:
            containment = 'UNPROVEN'
        write_once(adapter.audit / 'failure.json', {'state': 'NEEDS_OPERATOR',
            'attempt': ATTEMPT, 'phase': phase, 'containment': containment,
            'automatic_retry_forbidden': True})
        raise RecoveryError('fixed recovery failed; retain original and new attempt evidence') from None


def load(path, name, bootstrap):
    bootstrap.secure(path)
    need(not os.path.lexists(path.parent / '__pycache__'), 'cached operator code rejected')
    raw = path.read_bytes()
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def context(sha, *, verify_ci=True):
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site and
         sys.flags.dont_write_bytecode and not sys.flags.optimize and
         sys.executable == '/usr/bin/python3.12' and 'SSH_ORIGINAL_COMMAND' not in os.environ,
         'isolated root system operator required')
    need(isinstance(sha, str) and re.fullmatch('[a-f0-9]{40}', sha) and sha not in (FAILED, PREVIOUS))
    source = STATE / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/exam_release_recovery.py'
    need(Path(__file__).absolute() == entry, 'canonical operator path required')
    for path in [*reversed(entry.parents), entry, entry.with_name('bootstrap_trusted_release.py')]:
        info = path.lstat()
        need(info.st_uid == 0 and not info.st_mode & 0o022 and
             (stat.S_ISDIR(info.st_mode) if path in entry.parents else
              stat.S_ISREG(info.st_mode) and info.st_nlink == 1), 'unsafe canonical operator path')
    need(not os.path.lexists(entry.parent / '__pycache__'))
    spec = importlib.util.spec_from_file_location('exam_forward_bootstrap', entry.with_name('bootstrap_trusted_release.py'))
    bootstrap = importlib.util.module_from_spec(spec)
    exec(compile(entry.with_name('bootstrap_trusted_release.py').read_bytes(), str(entry.with_name('bootstrap_trusted_release.py')), 'exec', dont_inherit=True), bootstrap.__dict__)
    checked, server = bootstrap.reviewed_source(sha)
    need(checked == source)
    if verify_ci:
        subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
            '--sha', sha, '--workflow-sha', sha], env=ENV, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=90)
    return source, bootstrap, server


def _guard_child(sha, *, schema=False, health_score=False):
    """Canonical a8 guards after intent; score mode is read-only and sanitized."""
    need(type(schema) is bool and type(health_score) is bool and not (schema and health_score))
    source, bootstrap, server = context(sha, verify_ci=False)
    reset = load(source / 'scripts/trusted_review_reset.py', 'exam_guard_reset', bootstrap)
    reset._assert_isolated_search_path()
    candidate = bootstrap.canonical_source(FAILED)
    reset._revision_proof(FAILED, candidate, bootstrap)
    reset._validate_application_imports(candidate, server)
    reset._validate_venv(server)
    site = LIVE / 'backend/venv/lib/python3.12/site-packages'
    sys.path.append(str(site))
    # Strict literal parser, validated .env; no shell evaluation or URL override.
    environment = reset._parse_maintenance_environment(server.read_production_env())
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(candidate / 'backend')
    sys.path.insert(0, str(candidate / 'backend'))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(candidate, environment)
        if schema:
            probe = load(source / 'backend/scripts/verify_runtime_schema_compatibility.py', 'exam_schema_guard', bootstrap)
            probe.main()
        if health_score:
            probe = load(candidate / 'backend/scripts/system_health_score.py', 'exam_score_guard', bootstrap)
            report = probe.calculate_health_score('http://localhost:8000', skip_tests=True, allow_paused_runtime=True)
            summary = health_summary(report)
        else:
            kb = load(candidate / 'backend/scripts/verify_runtime_only_kb_contract.py', 'exam_kb_guard', bootstrap)
            sys.argv = ['verify_runtime_only_kb_contract.py', '--phase', 'guard']
            need(kb.main() == 0, 'KB serving guard failed')
    if health_score:
        print(json.dumps(summary,sort_keys=True))


class GateView:
    """Read-only projection of already-proven gate enablement for old verifier."""
    def __init__(self, systemd, original, *, released):
        need(set(original) == set(UNITS))
        self.systemd, self.original, self.released = systemd, original, released

    def show(self, unit, prop):
        return self.systemd.show(unit, prop)

    def is_enabled(self, unit):
        actual = self.systemd.is_enabled(unit)
        if unit not in self.original:
            return actual
        original = self.original[unit]
        expected = original if self.released or original != 'enabled' else 'disabled'
        need(actual == expected, 'runtime enablement changed')
        return original


def verify_running_vision(vision, services, model_services):
    need(set(model_services) == set(vision.SERVICES), 'vision service inventory differs')
    result = {}
    for unit in vision.SERVICES:
        model = model_services[unit]
        running = services[unit + '.service']
        need(model['MainPID'] == running['MainPID'] and
             model['process_start'] == running['processes'].get(model['MainPID']),
             'vision main process does not match service cgroup')
        result[unit] = {}
        for pid, started in running['processes'].items():
            number = int(pid)
            need(vision.process_start(number) == started, 'vision cgroup process changed')
            applied = vision.target_process_model(number)
            flags = {key:vision.target_process_value(number,key) for key in vision.FLAGS}
            need(flags == model['authorization_flags'], 'vision cgroup authorization flags differ')
            need(vision.process_start(number) == started, 'vision process changed during environment proof')
            result[unit][pid] = {'start':started, 'model':applied, 'authorization_flags':flags}
    return result


class Adapter:
    def __init__(self, source, bootstrap, server, core, token, check):
        self.source, self.bootstrap, self.server, self.core = source, bootstrap, server, core
        self.recovery_sha, self.token, self.check = source.parent.name, token, check
        self.server.assert_no_competing_exam_recovery(self.bootstrap.STATE)
        self.audit = STATE / ATTEMPT
        self.helper = load(source / 'scripts/exam_attempts_release.py', 'exam_forward_ddl', bootstrap)
        module = load(source / 'scripts/no_backup_preflight_proof.py', 'exam_original_no_backup', bootstrap)
        self.object_json = module._contained.object_json
        self.base_units = module._contained.RecoveryProof._units
        self.proof = module.NoBackupPreflightProof(source, bootstrap, server, FAILED, PREVIOUS, token)
        self.failed_source = bootstrap.canonical_source(FAILED)
        # These components read/advance the original runtime transaction and must
        # remain byte-identical to its reviewed producer; only the DDL ACL helper
        # and schema probe are intentionally taken from the new reviewed source.
        for name in ('backend/scripts/runtime_state_release_transaction.py',
                     'scripts/contained_recovery_proof.py', 'scripts/no_backup_preflight_proof.py',
                     'scripts/retained_candidate_retirement.py'):
            need(self.helper.git(source, 'show', f'HEAD:{name}') ==
                 self.helper.git(self.failed_source, 'show', f'HEAD:{name}'), 'original runtime proof implementation changed')
        self.stage_proof = self.proof._stage(self.failed_source)
        self.transaction = self.proof.runtime.ReleaseTransaction(
            self.proof.runtime.production_layout(self.proof.stage), self.proof.systemd, code_only=True)
        path = self.transaction.layout.transaction_root / 'journal.json'
        raw, self.journal_identity = self.proof._file(path, 0o600)
        need(hashlib.sha256(raw).hexdigest() == JOURNAL_PIN, 'original runtime journal pin differs')
        self.journal = self.transaction._load_journal()
        validate_journal(self.journal)
        self._runtime_inventory()
        terminal_path = self.transaction._terminal_marker_path()
        _, self.previous_terminal_identity = self.proof._file(terminal_path, 0o600)
        self.previous_terminal = self.transaction._load_terminal_marker()
        need(self.previous_terminal['phase'] == 'COMMITTED' and self.previous_terminal['terminal_sha'] == PREVIOUS)
        self.transaction._verify_boot_gate_armed(self.journal)
        self.transaction._validate_code_only_layout(self.journal)
        self.transaction._validate_base_units()
        self.original_record = self.helper.STATE / FAILED
        self.proof._directory(self.original_record)
        need({p.name for p in self.original_record.iterdir()} == {'intent.json'}, 'original migration artifacts differ')
        raw, self.intent_identity = self.proof._file(self.original_record / 'intent.json', 0o600)
        need(hashlib.sha256(raw).hexdigest() == INTENT_PIN, 'original migration intent pin differs')
        self.old_plan = module._contained.object_json(raw)
        need(set(self.old_plan) == {'old','candidate','checksum','lease_sha256','database_sha256'} and
             self.old_plan['old'] == PREVIOUS and self.old_plan['candidate'] == FAILED and
             self.old_plan['checksum'] == self.helper.SQL_HASH and
             self.old_plan['lease_sha256'] == hashlib.sha256(token.encode()).hexdigest())
        need(self.helper.source_admission(self.failed_source, PREVIOUS, FAILED))
        self.expected = self.helper.expected_migrations(self.failed_source)
        self.retained = load(source / 'scripts/retained_candidate_retirement.py', 'exam_configuration_guard', bootstrap)
        self.vision = load(source / 'scripts/trusted_vision_model.py', 'exam_vision_guard', bootstrap)
        self.reset = self.proof.reset
        self.finalized = False
        self.runtime = self.migration = None
        self.db_identity = None
        self.original_laya = None
        self.dependencies = None
        self.review = self._review()

    def _runtime_inventory(self):
        root = self.transaction.layout.transaction_root
        need({p.name for p in root.iterdir()} == {'journal.json'}, 'unexpected runtime transaction artifact')
        need(not os.path.lexists(self.transaction._preparing_root()))
        need(not list(root.parent.glob('runtime-state-transaction.reap-*')))

    def _authority(self):
        self.check()
        self.server.assert_no_competing_exam_recovery(self.bootstrap.STATE)
        self.proof._assert_original_lease()
        self.server.assert_no_competing_exam_recovery(self.bootstrap.STATE)

    def _review(self):
        path = self.source.parent / 'exam-forward-g4.json'
        raw = self.helper.protected_read(path, private=True)
        value = self.object_json(raw)
        need(set(value) == {'schema','attempt','reviewed_sha','verdict','review_sha256'} and
             value['schema'] == 'exam-forward-g4.v1' and value['attempt'] == ATTEMPT and
             value['reviewed_sha'] == self.recovery_sha and value['verdict'] == 'GO' and
             re.fullmatch('[a-f0-9]{64}', value['review_sha256']), 'independent candidate-bound G4 proof required')
        return hashlib.sha256(raw).hexdigest()

    def _vision_static(self):
        """Fixed qwen3.8 overlay admission valid while business units are stopped.

        This reuses the original model transaction/history/file validators. No
        PID, activation timestamp or process environment enters immutable proof.
        """
        b, vision, retained = self.bootstrap, self.vision, self.retained
        self.server.assert_vision_model_history(b.STATE)
        root = b.STATE / 'vision-models'
        retained.private_directory(b, root)
        operations = sorted(path.name for path in root.iterdir())
        need(len(operations) == 1 and re.fullmatch('[a-f0-9]{32}', operations[0]),
             'only the proven initial vision operation is supported')
        history = retained.vision_history(b, self.source, operations[0])
        vision.finalization_model_files(rolled_back=False)
        files = {str(path): vision.optional_model_file(path) for path in
                 [vision.MODEL, *(vision.SYSTEMD / (unit + '.service.d') / vision.DROPIN_NAME
                                  for unit in vision.SERVICES)]}
        need(all(item is not None and item['metadata']['uid'] == 0 and
                 item['metadata']['gid'] == 0 and stat.S_IMODE(item['metadata']['mode']) == 0o600
                 for item in files.values()), 'vision model file metadata differs')
        services, raw_dropins = {}, {}
        for unit in vision.SERVICES:
            raw = vision.run(['/usr/bin/systemctl', 'show', unit,
                '--property=' + ','.join(VISION_STATIC_PROPERTIES)])
            values = vision.parse_service_properties(raw)
            need(set(values) == set(VISION_STATIC_PROPERTIES), 'vision static properties differ')
            vision.validate_env_sources(values['EnvironmentFiles'], installed=True)
            vision.validate_unset_environment(values['UnsetEnvironment'])
            name = unit + '.service'
            need(values['DropInPaths'] == ' '.join(retained.vision_paths(name)),
                 'vision model drop-in inventory differs')
            need(self.proof.systemd.show(name, 'DropInPaths') == values['DropInPaths'],
                 'vision static unit snapshots differ')
            raw_dropins[name] = values['DropInPaths']
            services[unit] = values
        retained.VisionBaseView(self.proof.systemd, raw_dropins)
        return {'model':'qwen3.8-flash', 'history':history, 'files':files,
                'services':services, 'raw_dropins':raw_dropins}

    def _configuration(self):
        # The no-backup wrapper requires active vision PIDs. At this fixed
        # post-checkout incident we prove its exact static overlay separately,
        # then call the unchanged base unit/security/network contract directly.
        transaction, proof = self.transaction, self.proof
        raw = proof.systemd
        if self.finalized:
            transaction._verify_original_enablement(self.journal)
        else:
            transaction._verify_boot_gate_armed(self.journal)
        overlay = self._vision_static()
        gated = GateView(raw, self.journal['original_enablement'], released=self.finalized)
        view = self.retained.VisionBaseView(gated, overlay['raw_dropins'])
        proof.systemd = transaction.systemd = view
        try:
            value = self.base_units(proof, self.failed_source, transaction, started_at=proof._started_text)
        finally:
            proof.systemd = transaction.systemd = raw
        need(self._vision_static() == overlay, 'vision static proof changed')
        value['vision_overlay'] = overlay
        return value

    def snapshot(self):
        self.check()
        self.server.assert_no_competing_exam_recovery(self.bootstrap.STATE)
        self.reset._revision_proof(FAILED, self.failed_source, self.bootstrap)
        result = {'lease_stage': self.proof._stage(self.failed_source),
                  'workspace': self.proof._workspace(self.failed_source),
                  'original_migration_intent': self.proof._file(self.original_record / 'intent.json', 0o600)[1],
                  'original_runtime_journal_sha256': JOURNAL_PIN,
                  'original_runtime_journal': self.journal,
                  'previous_runtime_terminal': self.previous_terminal,
                  'configuration': self._configuration(), 'g4_sha256': self._review()}
        need(result['original_migration_intent'] == self.intent_identity)
        need({p.name for p in self.original_record.iterdir()} == {'intent.json'})
        self.proof._absent(LIVE / 'backend/.env.reva-release.tmp', Path('/var/lib/reva-health-evidence-runtime/enabled.env'), Path('/run/reva-health-evidence-activation'))
        for unit in UNITS[1:]:
            self.proof._absent(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf')
        if not self.finalized:
            self._runtime_inventory()
            need(self.proof._file(self.transaction._terminal_marker_path(), 0o600)[1] == self.previous_terminal_identity)
            need(self.proof._file(self.transaction.layout.transaction_root / 'journal.json', 0o600)[1] == self.journal_identity)
        self.check()
        self.server.assert_no_competing_exam_recovery(self.bootstrap.STATE)
        return result

    def stopped(self):
        self.check()
        self.proof.stopped()
        for unit in UNITS:
            need(self.proof.systemd.show(unit, 'ControlPID') in ('0',''))
        self.check()

    def _dependencies(self):
        self.reset._validate_application_imports(self.failed_source, self.server)
        self.reset._validate_venv(self.server)
        verifier = self.failed_source / 'backend/scripts/verify_locked_requirements.py'
        # Existing lock/RECORD verification runs without site startup. Its exact
        # canonical source is executed, and only the attested production site is
        # added for metadata discovery; no install/prune/cache mutation occurs.
        code = ('import sys,runpy;sys.path.append("/opt/health-app/backend/venv/lib/python3.12/site-packages");'
                'sys.argv=[' + repr(str(verifier)) + ',' + repr(str(self.failed_source / 'backend/requirements.lock')) + '];'
                'runpy.run_path(' + repr(str(verifier)) + ',run_name="__main__")')
        subprocess.run(['/usr/bin/python3.12','-I','-S','-B','-c',code], env=ENV,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=180)
        live_verifier = LIVE / 'backend/scripts/verify_locked_requirements.py'
        subprocess.run(['/usr/sbin/runuser','-u','health-app','--',
                        str(LIVE / 'backend/venv/bin/python'),'-I','-B',str(live_verifier),
                        '--runtime-user','health-app',str(LIVE / 'backend/requirements.lock')],
                       env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=180)
        pi = self._pi_dependencies()
        if self.dependencies is not None:
            need(pi == self.dependencies['pi'], 'Pi dependency bytes changed')
        self.dependencies = {'pi': pi, 'python_lock_sha256': hashlib.sha256(
            self.helper.protected_read(self.failed_source / 'backend/requirements.lock')).hexdigest()}

    def _pi_dependencies(self):
        root = LIVE / 'backend/pi-runtime'
        canonical = json.loads(self.helper.protected_read(self.failed_source / 'backend/pi-runtime/package-lock.json'))
        installed = json.loads(self.helper.protected_read(root / 'node_modules/.package-lock.json'))
        packages = validate_pi_lock(canonical, installed)
        entries = []
        # Root-owned dependency bytes, including ignored files, are the existing
        # installation authority. Never install, prune, update or copy them.
        for path, info in self.reset._runtime_entries(root / 'node_modules'):
            if stat.S_ISLNK(info.st_mode):
                need(info.st_uid == 0 and info.st_gid == 0 and info.st_nlink == 1 and
                     path.parent.name == '.bin' and path.resolve(strict=True).is_relative_to(root / 'node_modules'))
                self.bootstrap.secure(path.resolve(strict=True))
                entries.append([str(path.relative_to(root)), 'link', os.readlink(path)])
            elif stat.S_ISDIR(info.st_mode):
                self.bootstrap.secure(path)
            else:
                self.bootstrap.secure(path)
                entries.append([str(path.relative_to(root)), dependency_digest(path, self.bootstrap)])
        node = self.reset.NODE_TOOLCHAIN / 'bin/node'
        self.bootstrap.secure(node)
        # Exact producer import check, with no npm install or production secret.
        installer = self.helper.protected_read(self.failed_source / 'backend/pi-runtime/install.sh').decode()
        marker = "node --input-type=module <<'JS'\n"
        need(installer.count(marker) == 1 and installer.endswith('\nJS\n'))
        script = installer.split(marker, 1)[1][:-4]
        subprocess.run(['/usr/sbin/runuser','-u','health-app','--',str(node),'--input-type=module','-e',script],
                       cwd=root, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=60)
        return {'packages': len(packages), 'entries_sha256': digest(sorted(entries))}

    def _connect(self):
        if self.runtime is not None:
            return
        self._dependencies()
        # Only the root production credential sources are consulted. Import the
        # candidate's pure settings bytes after attesting dependencies and source.
        site = LIVE / 'backend/venv/lib/python3.12/site-packages'
        sys.path.append(str(site))
        os.environ.clear(); os.environ.update(ENV)
        os.chdir(LIVE / 'backend')
        path = self.failed_source / 'backend/app/config.py'
        settings = self.helper.load_runtime_settings(self.helper.protected_read(path), path)
        need(settings.app_env.lower() == 'production')
        self.bootstrap.secure(self.helper.CREDENTIAL, private=True)
        migration_url = self.helper.parse_migration_env(self.helper.protected_read(self.helper.CREDENTIAL, private=True))
        from sqlalchemy import create_engine
        self.runtime = create_engine(settings.effective_database_url, hide_parameters=True, connect_args={'connect_timeout':10})
        self.migration = create_engine(migration_url, hide_parameters=True, connect_args={'connect_timeout':10})
        need(self.runtime.dialect.name == self.migration.dialect.name == 'postgresql')

    def _database(self, conn):
        h = self.helper
        with self.runtime.connect() as runtime:
            h.sql(runtime, 'SET TRANSACTION READ ONLY')
            h.sql(runtime, "SET LOCAL statement_timeout='15s'")
            runtime_id = h.role_identity(runtime)
        identity = h.role_identity(conn)
        need(identity['role'] != runtime_id['role'] and all(identity[k] == runtime_id[k] for k in ('db','host','port')))
        bound = hashlib.sha256(json.dumps([identity, runtime_id], sort_keys=True).encode()).hexdigest()
        need(bound == self.old_plan['database_sha256'], 'original database target changed')
        need(h.sql(conn, "SELECT has_schema_privilege(current_user,'public','CREATE')").scalar_one() is True)
        need(h.sql(conn, "SELECT pg_has_role(:runtime,current_user,'MEMBER') OR has_schema_privilege(:runtime,'public','CREATE')", runtime=runtime_id['role']).scalar_one() is False)
        for privilege in ('SELECT','INSERT'):
            need(h.sql(conn, "SELECT has_table_privilege(current_user,'public.schema_migrations',:privilege)", privilege=privilege).scalar_one())
        need(h.sql(conn, "SELECT has_table_privilege(current_user,'public.users','REFERENCES')").scalar_one())
        self.runtime_role = runtime_id['role']
        return {'database_state': h.database_state(conn, self.expected), 'database_sha256': bound}

    def preflight(self):
        self.check()
        self.bootstrap._recovery_process_proof()
        self._connect()
        with self.migration.connect() as conn:
            self.helper.sql(conn, 'SET TRANSACTION READ ONLY')
            self.helper.sql(conn, "SET LOCAL statement_timeout='15s'")
            evidence = self._database(conn)
        self.original_laya = self.retained.candidate_laya(self.bootstrap, self.source, FAILED, self.journal, self.proof)
        self.check()
        self.bootstrap._recovery_process_proof()
        return {**evidence, 'laya': self.original_laya, 'dependencies': self.dependencies,
                'active_release_processes': False}

    def database_apply(self, plan):
        h = self.helper
        self.check(); self.stopped()
        self.bootstrap._recovery_process_proof()
        with self.migration.begin() as conn:
            h.sql(conn, "SET LOCAL lock_timeout='5s'")
            h.sql(conn, "SET LOCAL statement_timeout='30s'")
            need(h.sql(conn, 'SELECT pg_try_advisory_xact_lock(730228120000)').scalar_one())
            need(self._database(conn)['database_state'] == 'PENDING')
            self.snapshot(); self.stopped()
            h.apply_exact(conn, self.failed_source, plan, self.runtime_role)
            need(h.database_state(conn, self.expected) == 'APPLIED')
            self._authority(); self.stopped()
            self.bootstrap._recovery_process_proof()
        return self.readback(plan)

    def readback(self, plan):
        with self.migration.connect() as conn:
            self.helper.sql(conn, 'SET TRANSACTION READ ONLY')
            self.helper.sql(conn, "SET LOCAL statement_timeout='15s'")
            need(self._database(conn)['database_state'] == 'APPLIED')
            return self.helper.committed_proof(conn, plan, self.audit, self.runtime_role)

    def _application_guard(self, *, schema):
        code = ('import runpy;m=runpy.run_path(' + repr(str(self.source / 'scripts/exam_release_recovery.py')) + ');m["_guard_child"](' + repr(self.recovery_sha) + ',schema=' + repr(schema) + ')')
        subprocess.run(['/usr/bin/python3.12','-I','-S','-B','-c',code], env=ENV,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=300)

    def candidate_guards(self):
        self.check(); self._dependencies()
        self._application_guard(schema=True)
        current = self.retained.candidate_laya(self.bootstrap, self.source, FAILED, self.journal, self.proof)
        need(current == self.original_laya, 'Laya generation or process changed')
        self.transaction._validate_code_only_layout(self.journal)
        self._configuration(); self.check()

    def start(self):
        self._authority(); self.stopped()
        need(self.transaction.install(PREVIOUS, FAILED, self.proof.lease, self.token) == 'INSTALLED')
        for unit in UNITS:
            self._authority(); self.core._systemctl('start', unit)
        self.check()

    def running_snapshot(self):
        self._authority()
        services = self.proof.running_snapshot()
        overlay = self.retained.inspect_vision_overlay(self.bootstrap, self.source, self.proof.systemd)
        projected = {**overlay, 'services':{
            unit:{key:values[key] for key in VISION_STATIC_PROPERTIES}
            for unit,values in overlay['services'].items()}}
        need(projected == self._vision_static(), 'running vision configuration differs')
        models = verify_running_vision(self.vision, services, overlay['services'])
        need(self.proof.running_snapshot() == services, 'service identity changed during vision proof')
        self._authority()
        return {'services':services, 'vision':overlay, 'cgroup_model_identity':models}

    def stable(self):
        self.check()
        # Both service/cgroup and model/flags identities participate in every
        # sample and in the same existing seven-second RestartSec stability gate.
        value = self.core._wait_ready(self)
        self.check()
        return value

    def http(self):
        self._authority()
        self.core._http_probes()
        code = ('import runpy;m=runpy.run_path(' + repr(str(self.source / 'scripts/exam_release_recovery.py')) +
                ');m["_guard_child"](' + repr(self.recovery_sha) + ',health_score=True)')
        completed = subprocess.run(['/usr/bin/python3.12','-I','-S','-B','-c',code], env=ENV,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=180)
        need(len(completed.stdout) <= 4096, 'health summary exceeds bound')
        score = self.object_json(completed.stdout)
        need(set(score) == {'score','maximum','critical_failures','runtime_pause_preserved','runtime'})
        expected = {path.parent.name for path in (self.failed_source / 'backend/skills').glob('*/SKILL.md')}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), self.core._NoRedirect())
        with opener.open('https://health.executor.life/api/skills/manifest.json', timeout=15) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            need(response.status == 200 and len(raw) <= 8 * 1024 * 1024, 'skills manifest response rejected')
        manifest = manifest_summary(self.object_json(raw), expected)
        self.health_evidence = {'health_score':score, 'skills_manifest':manifest}
        self._authority()
        return self.health_evidence

    def commit_runtime(self):
        self._authority()
        need(self.transaction.commit(FAILED, self.proof.lease, self.token) == 'COMMITTED')
        self.check()

    def finalize_runtime(self):
        self._authority()
        need(self.transaction.finalize(FAILED, self.proof.lease, self.token) == 'finalized')
        marker = self.transaction._load_terminal_marker()
        need(marker['terminal_sha'] == FAILED and marker['old_sha'] == PREVIOUS and marker['phase'] == 'COMMITTED')
        self.finalized = True
        self.check()
        return marker

    def stop(self):
        # Best-effort each unit, then prove containment; failure is durable and
        # never changes/rearms a partly released journal or claims rollback.
        errors = []
        for unit in UNITS:
            try:
                self._authority()
                self.core._systemctl('stop', unit)
            except BaseException:
                errors.append(unit)
        self.stopped()
        need(not errors, 'service stop result unproven')

    def close(self):
        for engine in (self.runtime, self.migration):
            if engine is not None:
                engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--accept-exam-a8-forward-acl-v1', action='store_true')
    args = parser.parse_args()
    source, bootstrap, server = context(args.sha)
    os.umask(0o077)
    core = load(source / 'scripts/recover_contained_services.py', 'exam_forward_core', bootstrap)
    token_path = bootstrap.BUSINESS_LEASE / 'token'
    # Fixed OS lock alias is validated by the existing root lease reader.
    reset = load(source / 'scripts/trusted_review_reset.py', 'exam_forward_reset', bootstrap)
    reset._secure_lease_path(server, token_path, private=True)
    raw = token_path.read_bytes()
    need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,200}\n', raw))
    token = raw[:-1].decode('ascii')
    launcher = STATE / 'launcher.lock'
    bootstrap.secure(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build = None; adapter = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = bootstrap._acquire_existing_build_lock(FAILED)
        def check():
            bootstrap._assert_original_lock(launcher, fd)
            core._check_original_build_lock(bootstrap, FAILED, build)
        check()
        bootstrap._recovery_process_proof()
        adapter = Adapter(source, bootstrap, server, core, token, check)
        result = recover(adapter, args.evidence_sha256, accept=args.accept_exam_a8_forward_acl_v1)
        check()
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        if adapter is not None: adapter.close()
        if build is not None: os.close(build)
        os.close(fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('EXAM_FORWARD_RECOVERY_BLOCKED: retain original lease and all attempt evidence', file=sys.stderr)
        raise SystemExit(70) from None
