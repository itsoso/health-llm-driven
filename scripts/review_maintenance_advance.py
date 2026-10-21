"""Fixed, separately authorized advance after Store 279 review maintenance.

UNKNOWN remains UNKNOWN. Audit-only acknowledgements never authorize this
operation themselves. No database access, reset, retry, backup or deployment.
The bootstrap owns locks, exact candidate CI and canonical-source admission.
"""
import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys

TARGET = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
OPERATION = 'a71c3840b6f24bc79937d178cb838066'
READY = 'FIXED_REVIEW_MAINTENANCE_ADVANCE_READY'
KIND = 'fixed-review-maintenance-advance-v1'


class AdvanceError(Exception):
    """Static, non-sensitive diagnostics."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def profile(old, new):
    if old != TARGET or not isinstance(new, str) or re.fullmatch('[a-f0-9]{40}', new) is None or new == old:
        raise AdvanceError('only fixed review maintenance advance supported')


def load(b, source, name):
    path = source / 'scripts' / (name + '.py')
    b.secure(path)
    if os.path.lexists(path.parent / '__pycache__'):
        raise AdvanceError('cached advance code forbidden')
    spec = importlib.util.spec_from_file_location('advance_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def modules(b, source):
    return tuple(load(b, source, n) for n in ('review_maintenance_acknowledgement',
        'review_maintenance_retirement', 'trusted_review_briefing_repair', 'review_demo_briefing_repair'))


def dependencies(b, source, sha):
    """Protected receipts only; never query live demo or other account data."""
    profile(TARGET, sha)
    ack, readers, briefing, core = modules(b, source)
    if not os.path.lexists(b.STATE / 'review-maintenance-ack-reconciliations' / TARGET):
        raise AdvanceError('completed fixed reconciliation required')
    reconciled = briefing.acknowledgement_evidence(b, readers, ack, sha, allow_fixed_successor=True)
    root = b.STATE / 'review-demo-briefing-repairs' / TARGET
    closure = None
    closure_root = b.STATE / 'review-demo-briefing-unstarted-closures' / TARGET
    successor_root = b.STATE / 'review-demo-briefing-successors' / TARGET
    if os.path.lexists(closure_root):
        closure_module = load(b, source, 'review_briefing_unstarted_closure')
        closure = closure_module.closed_evidence(b, sha)
        root = closure_module.successor_path(b)
    elif os.path.lexists(successor_root):
        raise AdvanceError('successor lacks complete fixed audit closure')
    inventory = b._inventory(root, {'intent.json', 'database-started.json', 'completed.json'})
    intent = b._read_json(root / 'intent.json')
    end = b._read_json(root / 'completed.json')
    if closure is not None:
        if (intent.get('attempt_profile') != closure_module.ATTEMPT
                or intent.get('accept_successor_briefing_attempt') is not True
                or intent.get('unstarted_closure') != closure):
            raise AdvanceError('successor intent lacks explicit fixed closure chain')
    elif any(k in intent for k in ('attempt_profile','unstarted_closure','accept_successor_briefing_attempt')):
        raise AdvanceError('ordinary briefing cannot consume successor authority')
    evidence = intent.get('evidence')
    core.validate_evidence(evidence)
    expected = digest(evidence)
    result = end.get('result', {})
    if (intent.get('reconciliation_succession') != reconciled.get('succession')
            or intent.get('operator_sha') != sha or intent.get('accept_demo_briefing_repair') is not True
            or intent.get('evidence_sha256') != expected
            or evidence['acknowledgement_sha256'] != reconciled['completed_sha256']
            or b._read_json(root / 'database-started.json') != {'state': 'DATABASE_ATTEMPT_STARTED',
                'operator_sha': sha, 'evidence_sha256': expected}
            or set(end) != {'state', 'evidence_sha256', 'result', 'original_outcome',
                           'reset_authorized', 'release_unblocked', 'retry_authorized'}
            or end['state'] != 'BRIEFING_REPAIRED_ONLY' or end['evidence_sha256'] != expected
            or end['original_outcome'] != 'UNKNOWN' or end['reset_authorized'] is not False
            or end['release_unblocked'] is not False or end['retry_authorized'] is not False
            or set(result) != {'state', 'before_sha256', 'after_sha256'}
            or result['state'] != 'VERIFIED_BRIEFING_ONLY'
            or result['before_sha256'] != evidence['database_snapshot_sha256']
            or re.fullmatch('[a-f0-9]{64}', result.get('after_sha256', '')) is None):
        raise AdvanceError('same-operator completed fixed briefing required')
    original = readers.original_workspace(b, TARGET, OPERATION)
    maintenance = b.STATE / 'review-maintenance' / TARGET
    maintenance_inventory = b._inventory(maintenance, {'started.json', 'completed.json'})
    ack.validate_failed_pair(b._read_json(maintenance / 'started.json'),
                             b._read_json(maintenance / 'completed.json'), TARGET, OPERATION)
    return {'original': original, 'maintenance': maintenance_inventory,
            'reconciliation': reconciled, 'briefing': inventory,
            **({'unstarted_closure': closure} if closure is not None else {})}


def make_adapter(b, source, server, sha, check):
    profile(TARGET, sha)
    ack, readers, _, _ = modules(b, source)
    guard = ack.make_adapter(source, b, server, readers, sha, TARGET, OPERATION, check)
    class Adapter:
        record = b.STATE / 'review-maintenance-advances' / TARGET
        def inspect(self):
            check()
            b._assert_idle()
            observed = guard.inspect()
            deps = dependencies(b, source, sha)
            if guard.inspect() != observed:
                raise AdvanceError('production changed during advance inspection')
            return {'kind': KIND, 'old_sha': TARGET, 'new_sha': sha, 'operation_id': OPERATION,
                    'original_outcome': 'UNKNOWN', 'reset_authorized': False,
                    'production': observed, 'dependencies': deps}

        def prepare(self):
            if not self.record.parent.exists():
                self.record.parent.mkdir(mode=0o700)
                b._sync_parent(self.record.parent)
            guard.c._private_directory(b, self.record.parent)
            self.record.mkdir(mode=0o700)
            b._sync_parent(self.record)

        def write(self, name, value):
            if name not in {'intent.json', 'completed.json'}:
                raise AdvanceError('invalid advance audit output')
            check()
            b._write(self.record / name, json.dumps(value, sort_keys=True).encode())

        def revoke_once(self, evidence):
            # Full live check immediately before the first credential mutation.
            if self.inspect() != evidence:
                raise AdvanceError('advance evidence drift before revocation')
            policy = b._read_json(b.CONFIG / 'authorized-release.json')
            public = [(b.CONFIG / n).read_text().strip() for n in ('cloud.pub', 'loopback.pub')]
            expected = b.key_lines(policy['expires_at'], *public)
            lines = b.AUTHORIZED.read_bytes().splitlines(keepends=True)
            retained = b''.join(line for line in lines if line.decode().rstrip('\r\n') not in expected)
            check()
            b._replace_authorized(retained)
            if b.AUTHORIZED.read_bytes() != retained:
                raise AdvanceError('exact revocation postcondition failed')
            b.secure(b.CONFIG / 'loopback.key', private=True)
            (b.CONFIG / 'loopback.key').unlink()
            b._sync_parent(b.CONFIG / 'loopback.key')
            installation = b._installation_evidence(TARGET, b.CONFIG, b.INSTALLED.parent)
            verify_live(b, source, server, sha, check, evidence)
            return installation
    return Adapter()


def verify_live(b, source, server, sha, check, evidence):
    """Post-revocation checks omit only the deliberately removed key entries."""
    ack, readers, _, _ = modules(b, source)
    guard = ack.make_adapter(source, b, server, readers, sha, TARGET, OPERATION, check)
    b._assert_idle()
    guard._quiescent()
    guard.r._http_probes()
    if (guard._base() != evidence['production']['original']
            or guard._lease() != evidence['production']['lease']
            or guard._services() != evidence['production']['services']
            or dependencies(b, source, sha) != evidence['dependencies']):
        raise AdvanceError('live production or original audit changed')
    guard._quiescent()
    if guard.ssh_observation != evidence['production']['ssh_observation']:
        raise AdvanceError('publisher ownership changed')
    check()


def advance(adapter, *, accepted=False, evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise AdvanceError('advance already attempted; no replay')
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_NO_ADVANCE_AUTHORITY', 'evidence_sha256': fingerprint}
    if accepted is not True or evidence_sha256 != fingerprint:
        raise AdvanceError('fresh explicit advance authorization required')
    receipt = secrets.token_hex(32)
    intent = {'evidence': evidence, 'evidence_sha256': fingerprint,
              'accept_fixed_review_maintenance_advance': True,
              'receipt_sha256': hashlib.sha256(receipt.encode()).hexdigest()}
    adapter.prepare()
    adapter.write('intent.json', intent)
    installation = adapter.revoke_once(evidence)
    adapter.write('completed.json', {'state': READY, 'original_outcome': 'UNKNOWN',
        'reset_authorized': False, 'intent_sha256': digest(intent), 'installation': installation})
    return {'state': READY, 'original_outcome': 'UNKNOWN', 'receipt': receipt}


def saved(b, source, sha, *, receipt=None, proof=None):
    """Historical consumption is file-only, preserving both UNKNOWN receipts."""
    profile(TARGET, sha)
    root = b.STATE / 'review-maintenance-advances' / TARGET
    inventory = b._inventory(root, {'intent.json', 'completed.json'})
    intent, end = (b._read_json(root / n) for n in ('intent.json', 'completed.json'))
    evidence = intent.get('evidence', {})
    if (set(intent) != {'evidence', 'evidence_sha256', 'accept_fixed_review_maintenance_advance', 'receipt_sha256'}
            or intent['accept_fixed_review_maintenance_advance'] is not True
            or intent['evidence_sha256'] != digest(evidence)
            or re.fullmatch('[a-f0-9]{64}', intent['receipt_sha256']) is None
            or set(evidence) != {'kind','old_sha','new_sha','operation_id','original_outcome','reset_authorized','production','dependencies'}
            or evidence['kind'] != KIND or evidence['old_sha'] != TARGET or evidence['new_sha'] != sha
            or evidence['operation_id'] != OPERATION or evidence['original_outcome'] != 'UNKNOWN'
            or evidence['reset_authorized'] is not False
            or set(end) != {'state','original_outcome','reset_authorized','intent_sha256','installation'}
            or end['state'] != READY or end['original_outcome'] != 'UNKNOWN'
            or end['reset_authorized'] is not False or end['intent_sha256'] != digest(intent)
            or dependencies(b, source, sha) != evidence['dependencies']):
        raise AdvanceError('completed fixed advance evidence differs')
    result = {'kind': KIND, 'old_sha': TARGET, 'new_sha': sha,
              'original_outcome': 'UNKNOWN', 'reset_authorized': False, 'inventory': inventory}
    if proof is not None:
        if proof != result:
            raise AdvanceError('retirement-bound advance proof differs')
    elif (not isinstance(receipt, str) or re.fullmatch('[a-f0-9]{64}', receipt) is None
          or hashlib.sha256(receipt.encode()).hexdigest() != intent['receipt_sha256']):
        raise AdvanceError('protected one-shot advance receipt required')
    return result, evidence, end['installation']


def workspace(evidence):
    return {'state': READY, 'original_outcome': 'UNKNOWN', 'reset_authorized': False,
            'evidence_sha256': digest(evidence)}
