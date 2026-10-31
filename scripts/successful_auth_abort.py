"""Close the fixed interrupted authorization attempt without revoking any key.

This is an incident profile, not an incomplete-audit bypass. The original
intent remains immutable. A durable receipt is required for a new successor.
"""
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path

OLD = '8d4d6c5c627ec50b27e67b6282946ec4ccb664c7'
FAILED = 'a030c61539c388e78a79fa6c6e01392310044d12'
ORIGINAL_INTENT = '41b4ecf2dc6524525f7080d54ebc71194ab6fee55a75b83630b5692465324301'
POLICY = '00aa7ec48d090948eee79712b854bf0ed140d4ce3531d27e40fc71c23b12dc47'
BASE = {'intent.json', 'abort-intent.json', 'abort-completed.json'}
CONFIG_NAMES = {'authorized-release.json', 'cloud.pub', 'loopback.pub',
                'known_hosts', 'loopback.conf', 'loopback.key'}


def original(b, record):
    if record != b.STATE / 'successful-auth-revocations' / OLD:
        raise b.BootstrapError('abort profile requires the fixed original attempt')
    b.secure(record / 'intent.json', private=True)
    if hashlib.sha256((record / 'intent.json').read_bytes()).hexdigest() != ORIGINAL_INTENT:
        raise b.BootstrapError('original successful identity intent changed')
    intent = b._read_json(record / 'intent.json')
    if (intent.get('old_sha') != OLD or intent.get('new_sha') != FAILED
            or intent.get('backend_succeeded') is not True):
        raise b.BootstrapError('original successful identity target differs')
    return intent


def history(b, record):
    """Validate immutable closure; never require destroyed old live key material."""
    intent = original(b, record)
    names = {p.name for p in record.iterdir()}
    if names not in (BASE, BASE | {'successor'}):
        raise b.BootstrapError('incomplete or unknown pre-revocation abort inventory')
    b.secure(record)
    if not record.is_dir() or stat.S_IMODE(record.lstat().st_mode) != 0o700:
        raise b.BootstrapError('invalid private abort directory')
    for name in BASE:
        b.secure(record / name, private=True)
    proof = b._read_json(record / 'abort-intent.json')
    expected = {'state', 'old_sha', 'failed_sha', 'producer_sha', 'original_intent_sha256',
                'evidence', 'evidence_sha256', 'receipt_sha256', 'implementation_sha256'}
    if (not isinstance(proof, dict) or set(proof) != expected
            or proof['state'] != 'ABORT_BEFORE_REVOCATION_INTENT'
            or proof['old_sha'] != OLD or proof['failed_sha'] != FAILED
            or proof['original_intent_sha256'] != ORIGINAL_INTENT
            or not isinstance(proof['producer_sha'], str)
            or re.fullmatch('[0-9a-f]{40}', proof['producer_sha']) is None
            or proof['producer_sha'] in (OLD, FAILED)
            or any(not isinstance(proof[k], str) or re.fullmatch('[0-9a-f]{64}', proof[k]) is None
                   for k in ('evidence_sha256', 'receipt_sha256', 'implementation_sha256'))
            or b._digest_json(proof['evidence']) != proof['evidence_sha256']):
        raise b.BootstrapError('invalid pre-revocation abort intent')
    source = b.canonical_source(proof['producer_sha'])
    if hashlib.sha256((source / 'scripts/successful_auth_abort.py').read_bytes()).hexdigest() != proof['implementation_sha256']:
        raise b.BootstrapError('abort producer implementation differs')
    evidence = proof['evidence']
    if (not isinstance(evidence, dict) or set(evidence) != {
            'original_intent_sha256', 'config', 'library', 'authorized', 'workspace',
            'workspace_completed_sha256', 'key_identity', 'production_sha', 'locks'}
            or evidence['original_intent_sha256'] != ORIGINAL_INTENT
            or evidence['production_sha'] != OLD
            or evidence['workspace'] != intent['workspace']
            or evidence['workspace_completed_sha256'] != intent['workspace_completed_sha256']
            or evidence['authorized'].get('sha256') != intent['old_authorized_sha256']
            or evidence['config']['authorized-release.json']['sha256'] != POLICY
            or evidence['library'][b.INSTALLED.name]['sha256'] != intent['old_executor_sha256']
            or evidence['key_identity']['public_sha256'] != intent['loopback_public_sha256']
            or b._workspace_evidence(OLD, historical=True) != intent['workspace']
            or hashlib.sha256((b.STATE / OLD / 'completed.json').read_bytes()).hexdigest() != intent['workspace_completed_sha256']):
        raise b.BootstrapError('abort proof does not bind original successful installation')
    digest = hashlib.sha256((record / 'abort-intent.json').read_bytes()).hexdigest()
    if b._read_json(record / 'abort-completed.json') != {
            'state': 'ABORTED_BEFORE_REVOCATION', 'old_sha': OLD, 'failed_sha': FAILED,
            'abort_intent_sha256': digest}:
        raise b.BootstrapError('invalid pre-revocation abort completion')
    successor = record / 'successor'
    if 'successor' in names:
        b._inventory(successor, {'intent.json', 'completed.json'})
        next_intent = b._read_json(successor / 'intent.json')
        if (next_intent.get('prior_abort_sha256') != digest
                or next_intent.get('new_sha') in (OLD, FAILED)):
            raise b.BootstrapError('successor differs from original abort')
        return successor, digest
    return None, digest


def snapshot(b, source, *, applying=False):
    record = b.STATE / 'successful-auth-revocations' / OLD
    b._inventory(record, BASE if applying == 'closed' else ({'intent.json', 'abort-intent.json'} if applying else {'intent.json'}))
    intent = original(b, record)
    if any(os.path.lexists(p) for p in (
            b.STATE / 'retired' / OLD, b.STATE / FAILED, *b._archives(OLD), *b._archives(FAILED))):
        raise b.BootstrapError('revocation, retirement or failed target consumption already started')
    history_state = b._retired_history(_pending_successful_abort=ORIGINAL_INTENT)
    b._assert_known_activity(history_state, OLD)
    b._assert_idle()
    b._recovery_process_proof()
    b._assert_backend_terminated_or_unstarted(OLD)
    b._recovery_production_proof(OLD, source)
    config = b._inventory(b.CONFIG, CONFIG_NAMES)
    library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
    canonical_executor = hashlib.sha256((b.canonical_source(OLD) / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    policy = b._read_json(b.CONFIG / 'authorized-release.json')
    if (config['authorized-release.json']['sha256'] != POLICY
            or policy != {'sha': OLD, 'expires_at': 0, 'executor_sha256': canonical_executor}
            or library[b.INSTALLED.name]['sha256'] != canonical_executor
            or canonical_executor != intent['old_executor_sha256']):
        raise b.BootstrapError('old authorization policy or executor changed')
    authorized = b._recovery_file_identity(b.AUTHORIZED)
    if authorized['sha256'] != intent['old_authorized_sha256']:
        raise b.BootstrapError('authorization changed or partially revoked')
    cloud, public = [(b.CONFIG / name).read_text().strip() for name in ('cloud.pub', 'loopback.pub')]
    for key in (cloud, public):
        b.validate_install(OLD, 1, key, now=0)
    lines = b.AUTHORIZED.read_text().splitlines()
    for key, expected in zip((cloud, public), b.key_lines(0, cloud, public)):
        if [line for line in lines if key.split()[1] in line] != [expected]:
            raise b.BootstrapError('managed authorization line differs')
    key = b.CONFIG / 'loopback.key'
    b.secure(key, private=True)
    before = key.lstat()
    derived = b._run(['/usr/bin/ssh-keygen', '-y', '-f', str(key)], capture=True).stdout.strip()
    if (derived.split()[:2] != public.split()[:2]
            or hashlib.sha256(public.encode()).hexdigest() != intent['loopback_public_sha256']):
        raise b.BootstrapError('old cryptographic key identity changed')
    after = key.lstat()
    attrs = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink')
    if tuple(getattr(before, x) for x in attrs) != tuple(getattr(after, x) for x in attrs) or after.st_nlink != 1:
        raise b.BootstrapError('key changed during inspection')
    workspace = b._workspace_evidence(OLD)
    completed = hashlib.sha256((b.STATE / OLD / 'completed.json').read_bytes()).hexdigest()
    if workspace != intent['workspace'] or completed != intent['workspace_completed_sha256']:
        raise b.BootstrapError('successful workspace changed')
    return {'original_intent_sha256': ORIGINAL_INTENT, 'config': config, 'library': library,
            'authorized': authorized, 'workspace': workspace, 'workspace_completed_sha256': completed,
            'key_identity': {**{x: getattr(after, x) for x in attrs},
                             'public_sha256': intent['loopback_public_sha256']}, 'production_sha': OLD,
            'locks': {'launcher': b._recovery_file_identity(b.STATE / 'launcher.lock'),
                      'build': (b._recovery_file_identity(b.STATE / OLD / 'build.lock')
                                if os.path.lexists(b.STATE / OLD / 'build.lock') else None)}}


def successor(b, old_sha, new_sha, receipt):
    record = b.STATE / 'successful-auth-revocations' / old_sha
    if not os.path.lexists(record):
        if receipt is not None:
            raise b.BootstrapError('abort receipt without original attempt')
        return record, None
    if old_sha != OLD or new_sha in (OLD, FAILED):
        raise b.BootstrapError('successful closure already attempted')
    existing, digest = history(b, record)
    proof = b._read_json(record / 'abort-intent.json')
    if (existing is not None or not isinstance(receipt, str)
            or re.fullmatch('[0-9a-f]{64}', receipt) is None
            or hashlib.sha256(receipt.encode()).hexdigest() != proof['receipt_sha256']):
        raise b.BootstrapError('one durable abort receipt required for fresh successor')
    # The old identity must still match the inspect/apply snapshot immediately
    # before the new closure writes its own intent. No old receipt is rewritten.
    if snapshot_after_abort(b, record, proof) != proof['evidence']:
        raise b.BootstrapError('old identity drifted after abort')
    return record / 'successor', digest


def snapshot_after_abort(b, record, proof):
    # Same live invariants, with the immutable terminal inventory admitted.
    return snapshot(b, b.canonical_source(proof['producer_sha']), applying='closed')


def abort(b, sha, *, evidence_sha256=None):
    if (not isinstance(sha, str) or re.fullmatch('[0-9a-f]{40}', sha) is None
            or sha in (OLD, FAILED) or 'SSH_ORIGINAL_COMMAND' in os.environ
            or (evidence_sha256 is not None and re.fullmatch('[0-9a-f]{64}', evidence_sha256) is None)):
        raise b.BootstrapError('exact distinct canonical abort producer required')
    source, _server = b.reviewed_source(sha)
    b._run(['/usr/bin/python3.12', '-I', str(source / 'scripts/trusted_release_gate.py'),
            '--sha', sha, '--workflow-sha', sha, '--observed-main', sha])
    lock = b.STATE / 'launcher.lock'
    b.secure(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = b._acquire_existing_build_lock(OLD)
        def locks():
            b._assert_original_lock(lock, fd)
            build_path = b.STATE / OLD / 'build.lock'
            if build_fd is None:
                if os.path.lexists(build_path):
                    raise b.BootstrapError('historical build lock appeared')
            else:
                b._assert_original_lock(build_path, build_fd)
        locks()
        evidence = snapshot(b, source)
        digest = b._digest_json(evidence)
        locks()
        if evidence_sha256 is None:
            return {'state': 'ABORTABLE_BEFORE_REVOCATION', 'old_sha': OLD,
                    'failed_sha': FAILED, 'producer_sha': sha, 'evidence_sha256': digest}
        if evidence_sha256 != digest:
            raise b.BootstrapError('abort evidence changed since inspection')
        record = b.STATE / 'successful-auth-revocations' / OLD
        receipt = secrets.token_hex(32)
        proof = {'state': 'ABORT_BEFORE_REVOCATION_INTENT', 'old_sha': OLD, 'failed_sha': FAILED,
                 'producer_sha': sha, 'original_intent_sha256': ORIGINAL_INTENT, 'evidence': evidence,
                 'evidence_sha256': digest, 'receipt_sha256': hashlib.sha256(receipt.encode()).hexdigest(),
                 'implementation_sha256': hashlib.sha256((source / 'scripts/successful_auth_abort.py').read_bytes()).hexdigest()}
        b._write(record / 'abort-intent.json', json.dumps(proof, sort_keys=True).encode())
        if snapshot(b, source, applying=True) != evidence:
            raise b.BootstrapError('abort evidence changed after intent')
        locks()
        b._write(record / 'abort-completed.json', json.dumps({
            'state': 'ABORTED_BEFORE_REVOCATION', 'old_sha': OLD, 'failed_sha': FAILED,
            'abort_intent_sha256': hashlib.sha256((record / 'abort-intent.json').read_bytes()).hexdigest(),
        }, sort_keys=True).encode())
        history(b, record)
        locks()
        return {'state': 'ABORTED_BEFORE_REVOCATION', 'old_sha': OLD, 'failed_sha': FAILED,
                'producer_sha': sha, 'receipt': receipt}
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)
