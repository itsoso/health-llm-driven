"""Synthetic protocol tests; do not contact production or inspect real accounts."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name('review_maintenance_acknowledgement.py')
    spec = importlib.util.spec_from_file_location('ack_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Adapter:
    def __init__(self, root):
        self.record = root / 'ack'
        self.evidence = {'old_sha': 'a' * 40, 'closing_sha': 'b' * 40,
                         'operation_id': 'c' * 32, 'original_outcome': 'UNKNOWN'}
        self.original = root / 'original.json'
        self.original.write_text('{"state":"NEEDS_OPERATOR"}')
        self.calls = 0
        self.keys = []
        self.account = {'verification': 'CURRENT_ACCOUNT_ONLY_NOT_RESET'}
        self.change_at = None
        self.account_change = False
        self.invalid_account = False

    def inspect(self):
        self.calls += 1
        evidence = copy.deepcopy(self.evidence)
        if self.calls == self.change_at:
            evidence['changed'] = True
        return evidence

    def prepare_record(self):
        self.record.mkdir(mode=0o700)

    def write(self, name, value):
        with (self.record / name).open('x') as stream:
            json.dump(value, stream)

    def inspect_account(self, key):
        assert (self.record / 'intent.json').exists()
        self.keys.append(key)
        if self.account_change and len(self.keys) == 2:
            return {'changed': True}
        return copy.deepcopy(self.account)

    def validate_account(self, value):
        if self.invalid_account:
            raise ValueError('invalid account')


def test_inspect_is_readonly_and_needs_no_acceptance(tmp_path):
    m, a = load(), Adapter(tmp_path)
    assert m.acknowledge(a)['state'] == 'INSPECTED_UNKNOWN_NO_RETRY_AUTHORITY'
    assert not a.record.exists()
    assert not a.keys


def test_exec_requires_explicit_acceptance(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.AcknowledgementError, match='explicit'):
        m.acknowledge(a, evidence_sha256=m.digest(a.evidence))
    assert not a.record.exists()


def test_stale_inspection_is_rejected_before_intent(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.AcknowledgementError, match='changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256='f' * 64)
    assert not a.record.exists()


def test_success_preserves_original_unknown_and_grants_no_authority(tmp_path):
    m, a = load(), Adapter(tmp_path)
    old = a.original.read_bytes()
    result = m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    completed = json.loads((a.record / 'completed.json').read_text())
    assert result['state'] == 'UNKNOWN_ACCEPTED_AUDIT_ONLY'
    assert completed['original_outcome'] == 'UNKNOWN'
    assert completed['reset_authorized'] is False
    assert completed['release_unblocked'] is False
    assert not any(completed['authority'].values())
    assert completed['historical_no_write_proven'] is False
    assert a.original.read_bytes() == old
    assert len(a.keys) == 2 and len(a.keys[0]) == 32 and a.keys[0] == a.keys[1]
    assert {p.name for p in a.record.iterdir()} == {'intent.json', 'completed.json'}
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


@pytest.mark.parametrize('change_at', [2, 3, 4])
def test_evidence_drift_retains_intent_and_blocks_retry(tmp_path, change_at):
    m, a = load(), Adapter(tmp_path)
    a.change_at = change_at
    with pytest.raises(m.AcknowledgementError, match='changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert (a.record / 'intent.json').exists()
    assert not (a.record / 'completed.json').exists()
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


def test_changed_demo_hmac_cannot_complete(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.account_change = True
    with pytest.raises(m.AcknowledgementError, match='snapshot changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert not (a.record / 'completed.json').exists()


def test_invalid_demo_proof_cannot_complete(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.invalid_account = True
    with pytest.raises(ValueError):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert not (a.record / 'completed.json').exists()


def test_existing_symlink_record_is_not_followed(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.record.symlink_to(tmp_path / 'missing')
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


def test_noncanonical_context_rejected():
    m = load()
    with pytest.raises(m.AcknowledgementError, match='canonical'):
        m.context('a' * 40)


def test_no_existing_history_consumer_references_audit_namespace():
    root = Path(__file__).parent
    for name in ('trusted_review_reset.py', 'bootstrap_trusted_release.py', 'trusted_release_server.py'):
        assert 'review-maintenance-acknowledgements' not in (root / name).read_text()


def pair():
    start = {'operator_sha': 'b' * 40, 'target_sha': 'a' * 40, 'operation_id': 'c' * 32,
             'production_identity': [1] * 9, 'production_sha256': 'd' * 64,
             'environment_sha256': 'e' * 64, 'ci': {}, 'state': 'STARTED'}
    return start, {**start, 'state': 'NEEDS_OPERATOR'}


def test_exact_failed_maintenance_pair_is_accepted():
    m = load()
    start, end = pair()
    m.validate_failed_pair(start, end, 'a' * 40, 'c' * 32)


@pytest.mark.parametrize('field,value', [('state', 'SUCCEEDED'), ('target_sha', 'f' * 40),
                                        ('operation_id', 'f' * 32), ('operator_sha', None)])
def test_inconsistent_failed_maintenance_pair_is_blocked(field, value):
    m = load()
    start, end = pair()
    end[field] = value
    with pytest.raises(m.AcknowledgementError):
        m.validate_failed_pair(start, end, 'a' * 40, 'c' * 32)


def test_matching_wrong_operation_pair_still_blocked():
    m = load()
    start, end = pair()
    start['operation_id'] = end['operation_id'] = 'f' * 32
    with pytest.raises(m.AcknowledgementError):
        m.validate_failed_pair(start, end, 'a' * 40, 'c' * 32)


def test_probe_refuses_github_token_flag_before_context(monkeypatch):
    import sys
    m = load()
    monkeypatch.setattr(sys, 'argv', ['ack', '--sha', 'b' * 40, '--release-sha', 'a' * 40,
                                   '--operation-id', 'c' * 32, '--account-probe', '--token-stdin'])
    def forbidden(*args, **kwargs):
        pytest.fail('context or stdin must not be reached')
    monkeypatch.setattr(m, 'context', forbidden)
    assert m.main() == 1
