"""Explicitly authorized, no-copy retirement after the fixed dinner guard recovery.

No service restarts, deployment, environment writes, or original receipt edits.
The protected receipt is emitted only after completed.json is durable. Operators
must capture stdout privately; never place that receipt in argv or public logs.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

FAILED = 'ae49cf1fc53c567b305c2a9f6cfff5c3257e7309'
PRODUCTION = 'f42bb4c6d1c962453a6eadd1318ca6b663174b80'
PRIOR_RECOVERY = '6492f31789edf257ace6710cdfdff7b6c6c3b8b6'
RESTORED_FROM = '2c2679bf137aadc926c35d2197d740b3cefd5552'
CONTINUATION = 'continuation-20261023-static-unit-proof'
PRIOR_INTENT_PIN = 'bb519db5741aeed48403c686f0f5c7539f0fa77c86a813ad3bdad8f3ae7c7367'
CONTINUATION_INTENT_PIN = '8e9976e1628d94d843d8226e96bcb4b695abc5fe6b5039749a74ba4d4e2eb965'
CONTINUATION_COMPLETED_PIN = '823aa60e076575e977913cfeab39807d78af81014ae201b204307d826fd09902'
PRIOR_EVIDENCE = '3d9c4ba906fae58c67c25d18bbc0ea2a18be37176a6745347a74387f3f2446a2'
CONTINUATION_EVIDENCE = 'b79b4a14f724648f264db72193db08424a0fdc5dffd30abb5a97b217e68ccf9f'
SNAPSHOT_FIELDS = {'lease', 'log', 'completed', 'terminal', 'files', 'units', 'dependencies'}
PRIOR_FIELDS = {'prior_consumed_intent', 'prior_recovery_sha', 'prior_evidence_sha256'}
ROOT_NAME = 'dinner-guard-closures'
TERMINAL = 'CLOSED_DINNER_GUARD_RELEASE'
STATE = Path('/var/lib/reva-release')
LEASE = Path('/run/lock/health-app-release')
RETIRED_LEASE = Path('/run/lock/health-app-release.retired-' + FAILED)
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'}
CONFLICTS = ('contained-release-closures', 'unchanged-release-closures',
             'retained-candidate-closures', 'rolled-back-release-closures',
             'native-only-closures', 'partial-laya-closures',
             'review-maintenance-closures', 'recoveries',
             'lost-closure-receipt-acknowledgments')


class ClosureError(Exception):
    """Secret-free fail-closed boundary."""


def need(value):
    if not value:
        raise ClosureError('dinner retirement proof rejected')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def rotation_input(raw):
    def unique(pairs):
        value = dict(pairs)
        need(len(value) == len(pairs))
        return value
    need(isinstance(raw, bytes) and 0 < len(raw) <= 8192)
    value = json.loads(raw, object_pairs_hook=unique)
    need(isinstance(value, dict) and set(value) == {'receipt', 'github_token'})
    need(isinstance(value['receipt'], str) and re.fullmatch('[a-f0-9]{64}', value['receipt']))
    need(isinstance(value['github_token'], str) and re.fullmatch('[A-Za-z0-9_.-]{1,4096}', value['github_token']))
    return value


def close_transaction(adapter, evidence_sha256=None):
    need(not os.path.lexists(adapter.record))
    evidence = adapter.inspect()
    value = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_DINNER_GUARD_RELEASE', 'evidence_sha256': value}
    need(evidence_sha256 == value)
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        sync(adapter.record.parent.parent)
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {**evidence, 'evidence_sha256': value,
              'receipt_sha256': hashlib.sha256(receipt.encode()).hexdigest()}
    write(adapter.record / 'intent.json', intent)
    need(adapter.inspect() == evidence)
    adapter.retire(evidence)
    closed = adapter.verify_closed(evidence)
    write(adapter.record / 'completed.json', {'old_sha': evidence['old_sha'],
          'state': TERMINAL, 'intent_sha256': digest(intent), **closed})
    return {'sha': evidence['old_sha'], 'state': TERMINAL, 'receipt': receipt}


def load(b, path, name):
    b.secure(path)
    need(not os.path.lexists(path.parent / '__pycache__'))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def no_conflicts(b, sha):
    need(sha == FAILED)
    need(not any(os.path.lexists(b.STATE / name / sha) for name in CONFLICTS))


def workspace(b, source):
    # The fixed ae49 incident failed before deployment.env was created. This is
    # a distinct, strictly ten-entry profile, not an optional-env relaxation of
    # any generic retained-candidate contract.
    root = b.STATE / FAILED
    b.secure(root, private=True)
    need(stat.S_ISDIR(root.lstat().st_mode) and stat.S_IMODE(root.lstat().st_mode) == 0o700)
    expected = {'bin', 'completed.json', 'deployment-started.json', 'deployment.log',
                'home', 'preparation-started.json', 'preparation.log', 'prepared.json',
                'source', 'started.json'}
    need({path.name for path in root.iterdir()} == expected)
    canonical = b.canonical_source(FAILED)
    executor = hashlib.sha256((canonical / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    for name, state in (('started.json', 'STARTED'),
                        ('preparation-started.json', 'PREPARING'),
                        ('prepared.json', 'PREPARED'),
                        ('deployment-started.json', 'DEPLOYING'),
                        ('completed.json', 'NEEDS_OPERATOR')):
        value = {'sha': FAILED, 'state': state}
        if name == 'preparation-started.json':
            value['executor_sha256'] = executor
        need(b._read_json(root / name) == value)
    # Entire retained tree, including Git, logs and tools, is hash-bound without
    # executing it or emitting its contents. Original receipts remain untouched.
    return {'executor_sha256': executor, 'manifest': b._preparation_manifest(root)}


def semantic_snapshot(snapshot):
    # Only the three explicitly validated continuation provenance fields are
    # removed. New, missing or drifted business proof fields cannot disappear.
    need(isinstance(snapshot, dict) and set(snapshot) == SNAPSHOT_FIELDS | PRIOR_FIELDS)
    return {key: snapshot[key] for key in SNAPSHOT_FIELDS}


def validate_restoration(prior, prior_identity, intent, completed, base, bridge):
    keys = {'recovery_sha', 'failed_sha', 'production_sha', 'snapshot', 'evidence_sha256'}
    for value, recovery, expected_digest in ((prior, PRIOR_RECOVERY, PRIOR_EVIDENCE),
                                             (intent, RESTORED_FROM, CONTINUATION_EVIDENCE)):
        need(isinstance(value, dict) and set(value) == keys)
        need(value['recovery_sha'] == recovery and value['failed_sha'] == FAILED
             and value['production_sha'] == PRODUCTION and value['evidence_sha256'] == expected_digest)
        need(digest({k: v for k, v in value.items() if k != 'evidence_sha256'}) == expected_digest)
    need(isinstance(completed, dict) and set(completed) == {
        'state', 'recovery_sha', 'failed_sha', 'production_sha', 'evidence_sha256',
        'stable_services', 'original_release_and_lease_preserved'})
    need(completed['state'] == 'RESTORED_PREVIOUS_SERVICES'
         and completed['original_release_and_lease_preserved'] is True
         and isinstance(completed['stable_services'], dict))
    need(all(completed[key] == intent[key] for key in ('recovery_sha', 'failed_sha', 'production_sha', 'evidence_sha256')))
    snapshot = prior['snapshot']
    need(isinstance(snapshot, dict) and set(snapshot) == SNAPSHOT_FIELDS)
    need(set(snapshot['lease']) == set(base.LEASE_PINS))
    need(all(snapshot['lease'][key]['sha256'] == pin for key, pin in base.LEASE_PINS.items()))
    need(snapshot['log']['sha256'] == base.LOG_PIN and snapshot['completed']['sha256'] == base.COMPLETED_PIN)
    need(snapshot['terminal']['sha256'] == base.TERMINAL_PIN)
    need(set(snapshot['files']) == set(base.FILE_PINS))
    need(all(snapshot['files'][key]['sha256'] == pin for key, pin in base.FILE_PINS.items()))
    need(set(snapshot['units']) == set(base.UNIT_CONFIG_PINS))
    need(all(snapshot['units'][key]['effective_sha256'] == pin for key, pin in base.UNIT_CONFIG_PINS.items()))
    current = semantic_snapshot(intent['snapshot'])
    need(prior_identity.get('sha256') == PRIOR_INTENT_PIN)
    need(intent['snapshot']['prior_consumed_intent'] == prior_identity
         and intent['snapshot']['prior_recovery_sha'] == PRIOR_RECOVERY
         and intent['snapshot']['prior_evidence_sha256'] == PRIOR_EVIDENCE)
    # The reviewed bridge changes ONLY raw ExecStart configuration digests into
    # their fixed static equivalents. Every other nested value must be equal.
    bridge.verify_bridge(snapshot, current, base.UNIT_CONFIG_PINS, base.UNIT_STATIC_CONFIG_PINS)


def restoration(b, source):
    root = b.STATE / 'contained-service-recoveries' / FAILED
    child = root / CONTINUATION
    for directory, names in ((root, {'intent.json', CONTINUATION}),
                             (child, {'intent.json', 'completed.json'})):
        b.secure(directory, private=True)
        need(stat.S_ISDIR(directory.lstat().st_mode))
        need({p.name for p in directory.iterdir()} == names)
    recovery_source = b.canonical_source(RESTORED_FROM)
    base = load(b, recovery_source / 'scripts/dinner_guard_recovery.py', 'dinner_original_recovery')
    bridge = load(b, recovery_source / 'scripts/dinner_guard_recovery_continuation.py', 'dinner_original_continuation')
    need(bridge.PRIOR_RECOVERY == PRIOR_RECOVERY and bridge.INTENT_PIN == PRIOR_INTENT_PIN
         and bridge.PRIOR_DIGEST == PRIOR_EVIDENCE and bridge.CONTINUATION == CONTINUATION)
    old_source = b.canonical_source(PRIOR_RECOVERY)
    _, raw_code = base.identity(old_source / 'scripts/dinner_guard_recovery.py')
    need(bridge.literal_pins(raw_code) == base.UNIT_CONFIG_PINS)
    prior_identity, prior_raw = base.identity(root / 'intent.json', pin=PRIOR_INTENT_PIN)
    intent_identity, intent_raw = base.identity(child / 'intent.json', pin=CONTINUATION_INTENT_PIN)
    completed_identity, completed_raw = base.identity(child / 'completed.json', pin=CONTINUATION_COMPLETED_PIN)
    prior, intent, completed = (json.loads(raw) for raw in (prior_raw, intent_raw, completed_raw))
    validate_restoration(prior, prior_identity, intent, completed, base, bridge)
    audit = {'prior_intent': prior_identity, 'continuation_intent': intent_identity,
             'continuation_completed': completed_identity}
    for name, directory in (('root', root), ('continuation', child)):
        info = directory.lstat()
        audit[name] = {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}
    return intent, completed, audit


def lease_directory(m, path):
    # Fixed /run/lock sticky parent is the only intentional writable ancestor.
    need(path in (LEASE, RETIRED_LEASE))
    for parent in reversed(path.parents):
        m.secure(parent, True, lease_parent=(parent == Path('/run/lock')))
    info = m.secure(path, True)
    need(info.st_gid == 0 and stat.S_IMODE(info.st_mode) in (0o700, 0o755))
    return {key: getattr(info, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}


def moved_lease(m, expected):
    need(not os.path.lexists(LEASE) and lease_directory(m, RETIRED_LEASE) == expected['lease_directory'])
    need({p.name for p in RETIRED_LEASE.iterdir()} == set(m.LEASE_PINS))
    # identity() permits the original lease only. Open archived children directly
    # beneath the already checked fixed root; parent rename preserves files.
    for name, before in expected['snapshot']['lease'].items():
        p = RETIRED_LEASE / name
        m.secure(p)
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            a = os.fstat(f.fileno())
            raw = f.read(4097)
            z = os.fstat(f.fileno())
        n = p.lstat()
        need(len(raw) <= 4096 and all(getattr(a, k) == getattr(z, k) == getattr(n, k) == before[k] for k in m.FIELDS))
        need(hashlib.sha256(raw).hexdigest() == before['sha256'])


class Adapter:
    def __init__(self, source, b, core, m, proof, sha, check):
        self.source, self.b, self.core, self.m, self.proof = source, b, core, m, proof
        self.sha, self.check = sha, check
        self.record = b.STATE / ROOT_NAME / FAILED

    def inspect(self):
        b, p, m = self.b, self.proof, self.m
        self.check()
        no_conflicts(b, FAILED)
        if os.path.lexists(self.record.parent):
            b.secure(self.record.parent, private=True)
            need(stat.S_ISDIR(self.record.parent.lstat().st_mode))
        b._recovery_process_proof()
        original, completed, audit = restoration(b, self.source)
        need(self.sha not in (FAILED, PRODUCTION, original['recovery_sha']))
        need(p.snapshot() == semantic_snapshot(original['snapshot']))
        need(not os.path.lexists(RETIRED_LEASE))
        history = b._retired_history()
        b._assert_known_activity(history, FAILED)
        need(FAILED not in history and not any(os.path.lexists(q) for q in b._archives(FAILED)))
        config = b._inventory(b.CONFIG, {'known_hosts', 'loopback.conf', 'authorized-release.json', 'loopback.pub', 'cloud.pub', 'loopback.key'})
        library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
        policy = b._read_json(b.CONFIG / 'authorized-release.json')
        executor = hashlib.sha256((b.canonical_source(FAILED) / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
        need(policy == {'sha': FAILED, 'expires_at': 0, 'executor_sha256': executor})
        need(library[b.INSTALLED.name]['sha256'] == executor)
        keys = [(b.CONFIG / n).read_text().strip() for n in ('cloud.pub', 'loopback.pub')]
        need(keys[0] != keys[1])
        for key in keys:
            b.validate_install(FAILED, 0, key, now=0)
        b.secure(b.AUTHORIZED, private=True)
        lines = b.AUTHORIZED.read_text().splitlines()
        for key, line in zip(keys, b.key_lines(0, *keys)):
            need([v for v in lines if key.split()[1] in v] == [line])
        self.core._application_probes(PRODUCTION, self.sha)
        self.core._http_probes()
        stable = self.core._wait_ready(p)
        need(stable == completed['stable_services'] and p.snapshot() == semantic_snapshot(original['snapshot']))
        self.check()
        b._recovery_process_proof()
        return {'old_sha': FAILED, 'closing_sha': self.sha, 'production_sha': PRODUCTION,
                'restoration': audit, 'snapshot': semantic_snapshot(original['snapshot']), 'workspace': workspace(b, self.source),
                'lease_directory': lease_directory(m, LEASE), 'config': config, 'library': library,
                'authorized': b._recovery_file_identity(b.AUTHORIZED), 'services': stable,
                'launcher': b._recovery_file_identity(b.STATE / 'launcher.lock'),
                'build': b._recovery_file_identity(b.STATE / FAILED / 'build.lock') if os.path.lexists(b.STATE / FAILED / 'build.lock') else None}

    def retire(self, evidence):
        b, p = self.b, self.proof
        need(self.inspect() == evidence)
        keys = [(b.CONFIG / n).read_text().strip() for n in ('cloud.pub', 'loopback.pub')]
        exact = b.key_lines(0, *keys)
        retained = b''.join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
                            if line.decode().rstrip('\r\n') not in exact)
        need(b._recovery_file_identity(b.AUTHORIZED) == evidence['authorized'])
        b._replace_authorized(retained)
        need(b.AUTHORIZED.read_bytes() == retained)
        need(b._inventory(b.CONFIG, evidence['config'].keys() - {'.'}) == evidence['config'])
        (b.CONFIG / 'loopback.key').unlink()
        sync(b.CONFIG)
        b._installation_evidence(FAILED, b.CONFIG, b.INSTALLED.parent)
        need(p.snapshot() == evidence['snapshot'] and self.core._wait_ready(p) == evidence['services'])
        need(lease_directory(self.m, LEASE) == evidence['lease_directory'] and not os.path.lexists(RETIRED_LEASE))
        b._recovery_process_proof()
        self.check()
        b.secure(Path('/usr/bin/mv'))
        need(LEASE.lstat().st_dev == LEASE.parent.lstat().st_dev)
        subprocess.run(['/usr/bin/mv', '--no-clobber', '-T', '--', str(LEASE), str(RETIRED_LEASE)],
                       env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=15)
        sync(LEASE.parent)
        moved_lease(self.m, evidence)

    def verify_closed(self, evidence):
        b, m, p = self.b, self.m, self.proof
        self.check()
        moved_lease(m, evidence)
        b._assert_idle()
        b._recovery_process_proof()
        need(workspace(b, self.source) == evidence['workspace'])
        need(restoration(b, self.source)[2] == evidence['restoration'])
        # Recheck the static production proof without treating removed active
        # lease as authority; its original immutable bytes remain separately bound.
        b.canonical_source(PRODUCTION)
        p.base.reset._revision_proof(PRODUCTION, b.canonical_source(PRODUCTION), b)
        need(m.run(['/usr/bin/git', '-C', str(m.LIVE), 'rev-parse', 'HEAD']).decode().strip() == PRODUCTION)
        m.run(['/usr/bin/git', '-C', str(m.LIVE), 'diff', '--quiet', 'HEAD', '--'])
        need(m.identity(STATE / FAILED / 'deployment.log')[0] == evidence['snapshot']['log'])
        need(m.identity(STATE / FAILED / 'completed.json')[0] == evidence['snapshot']['completed'])
        runtime = Path('/var/lib/health-app/release-state')
        need({x.name for x in runtime.iterdir()} == {'runtime-state-terminal.json'})
        need(m.identity(runtime / 'runtime-state-terminal.json')[0] == evidence['snapshot']['terminal'])
        need({path: m.identity(path)[0] for path in m.FILE_PINS} == evidence['snapshot']['files'])
        need(p.unit_configuration() == evidence['snapshot']['units'])
        need({path: m.dependency_metadata(path) for path in evidence['snapshot']['dependencies']} == evidence['snapshot']['dependencies'])
        for path in ('/var/lib/reva-health-evidence-runtime/enabled.env', '/run/reva-health-evidence-activation', '/opt/health-app/backend/.env.reva-release.tmp'):
            need(not os.path.lexists(path))
        for unit in ('health-backend.service', 'celery-worker.service', 'celery-beat.service'):
            need(not os.path.lexists(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf'))
        self.core._application_probes(PRODUCTION, self.sha)
        self.core._http_probes()
        class Services:
            def running_snapshot(inner):
                return p.base.running_services_snapshot()
        need(self.core._wait_ready(Services()) == evidence['services'])
        expected = {'config': {k: v for k, v in evidence['config'].items() if k != 'loopback.key'}, 'library': evidence['library']}
        need(b._installation_evidence(FAILED, b.CONFIG, b.INSTALLED.parent) == expected)
        moved_lease(m, evidence)
        self.check()
        return {'installation': expected}


def closed_evidence(b, sha, receipt, *, historical=False):
    no_conflicts(b, sha)
    root = b.STATE / ROOT_NAME / sha
    b.secure(root, private=True)
    b._inventory(root, {'intent.json', 'completed.json'})
    intent, done = (b._read_json(root / n) for n in ('intent.json', 'completed.json'))
    fields = {'old_sha', 'closing_sha', 'production_sha', 'restoration', 'snapshot', 'workspace',
              'lease_directory', 'config', 'library', 'authorized', 'services', 'launcher', 'build',
              'evidence_sha256', 'receipt_sha256'}
    need(isinstance(intent, dict) and set(intent) == fields and intent['old_sha'] == FAILED and intent['production_sha'] == PRODUCTION)
    need(isinstance(intent['closing_sha'], str) and re.fullmatch('[a-f0-9]{40}', intent['closing_sha']))
    need(intent['closing_sha'] not in (FAILED, PRODUCTION))
    need(intent['evidence_sha256'] == digest({k: v for k, v in intent.items() if k not in {'evidence_sha256', 'receipt_sha256'}}))
    need(isinstance(receipt, str) and re.fullmatch('[a-f0-9]{64}', receipt))
    need(isinstance(intent['receipt_sha256'], str) and secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), intent['receipt_sha256']))
    expected = {'config': {k: v for k, v in intent['config'].items() if k != 'loopback.key'}, 'library': intent['library']}
    need(done == {'old_sha': sha, 'state': TERMINAL, 'intent_sha256': digest(intent), 'installation': expected})
    source = b.canonical_source(intent['closing_sha'])
    restored, completed, audit = restoration(b, source)
    need(semantic_snapshot(restored['snapshot']) == intent['snapshot'] and audit == intent['restoration'] and completed['stable_services'] == intent['services'])
    need(intent['closing_sha'] != restored['recovery_sha'])
    need(workspace(b, source) == intent['workspace'])
    need(b._recovery_file_identity(b.STATE / 'launcher.lock') == intent['launcher'])
    build = b.STATE / sha / 'build.lock'
    need((b._recovery_file_identity(build) if os.path.lexists(build) else None) == intent['build'])
    # Historical consumption is checked by bootstrap retirement audit against
    # saved canonical executor/public-key hashes. Never require removed config,
    # the volatile /run archive, or production that a later release may replace.
    if not historical:
        need(b._installation_evidence(sha, b.CONFIG, b.INSTALLED.parent) == expected)
        m = load(b, source / 'scripts/dinner_guard_recovery.py', 'dinner_closed_proof')
        moved_lease(m, intent)
        fd = os.open(RETIRED_LEASE / 'token', os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            raw = stream.read(257)
        need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', raw))
        need(hashlib.sha256(raw).hexdigest() == m.LEASE_PINS['token'])
        module = load(b, source / 'scripts/contained_recovery_proof.py', 'dinner_closed_services')
        core = load(b, source / 'scripts/recover_contained_services.py', 'dinner_closed_core')
        _, server = b.reviewed_source(intent['closing_sha'])
        base = module.RecoveryProof(source, b, server, FAILED, PRODUCTION, raw[:-1].decode('ascii'))
        class ClosedProof:
            def unit_configuration(self):
                return m.DinnerProof.unit_configuration(self)
        proof = ClosedProof()
        proof.base = base
        def check():
            need(b._recovery_file_identity(b.STATE / 'launcher.lock') == intent['launcher'])
            need((b._recovery_file_identity(build) if os.path.lexists(build) else None) == intent['build'])
        Adapter(source, b, core, m, proof, intent['closing_sha'], check).verify_closed(intent)
    return {'state': TERMINAL, 'closure': digest(done), 'workspace': intent['workspace']}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--github-token-stdin', required=True, action='store_true')
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--accept-dinner-guard-retirement', action='store_true')
    args = parser.parse_args()
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize)
    need(re.fullmatch('[a-f0-9]{40}', args.sha) and args.sha not in (FAILED, PRODUCTION))
    need(args.evidence_sha256 is None or (args.accept_dinner_guard_retirement and re.fullmatch('[a-f0-9]{64}', args.evidence_sha256)))
    source = STATE / 'bootstrap' / args.sha / 'source'
    need(Path(__file__).absolute() == source / 'scripts/dinner_guard_retirement.py')
    # Recover helper checks every root-owned path before importing the bootstrap.
    path = source / 'scripts/recover_contained_services.py'
    for item in [*reversed(path.parents), path]:
        s = item.lstat()
        need(s.st_uid == 0 and not s.st_mode & 0o022 and (stat.S_ISREG(s.st_mode) and s.st_nlink == 1 if item == path else stat.S_ISDIR(s.st_mode)))
    spec = importlib.util.spec_from_file_location('dinner_close_core', path)
    core = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = core
    spec.loader.exec_module(core)
    _, b, server = core._context(args.sha, verify_ci=False)
    raw = sys.stdin.buffer.read(4097)
    need(re.fullmatch(rb'[A-Za-z0-9_.-]{1,4096}', raw))
    subprocess.run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
                    '--sha', args.sha, '--workflow-sha', args.sha, '--token-stdin'],
                   input=raw, env=ENV, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    del raw
    os.umask(0o077)
    m = load(b, source / 'scripts/dinner_guard_recovery.py', 'dinner_close_proof')
    _, raw = m.identity(m.LEASE / 'token', pin=m.LEASE_PINS['token'])
    need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,255}\n', raw))
    token = raw[:-1].decode('ascii')
    launcher = b.STATE / 'launcher.lock'
    b.secure(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = b._acquire_existing_build_lock(FAILED)
        def check():
            b._assert_original_lock(launcher, fd)
            core._check_original_build_lock(b, FAILED, build)
        proof = m.DinnerProof(source, b, server, token, check)
        result = close_transaction(Adapter(source, b, core, m, proof, args.sha, check), args.evidence_sha256)
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build is not None:
            os.close(build)
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('dinner retirement blocked; preserve original evidence; no retry', file=sys.stderr)
        sys.exit(1)
