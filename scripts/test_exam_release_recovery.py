"""Failure barriers for the fixed exam forward recovery coordinator."""
from types import SimpleNamespace
import pytest
import exam_release_recovery as recovery


class Adapter:
    def __init__(self, fail=None):
        self.events = []
        self.fail = fail
    def __getattr__(self, name):
        def call(*args):
            self.events.append(name)
            if name == self.fail:
                raise RuntimeError('private failure')
            return {'proof': name}
        return call


def test_inspection_never_consumes_intent_or_starts_services():
    adapter = Adapter()
    result = recovery.recover(adapter)
    assert result['state'] == 'INSPECTED'
    assert adapter.events == ['admission', 'database_inspect', 'stopped_proof']


def test_mismatch_cannot_consume():
    adapter = Adapter()
    with pytest.raises(recovery.RecoveryBlocked):
        recovery.recover(adapter, '0' * 64)
    assert 'consume_intent' not in adapter.events


def test_forward_order_and_no_restore_or_lease_release():
    digest = recovery.recover(Adapter())['evidence_sha256']
    adapter = Adapter()
    result = recovery.recover(adapter, digest)
    assert result['state'] == 'RECOVERED_CANDIDATE'
    assert adapter.events == ['admission', 'database_inspect', 'stopped_proof',
        'consume_intent', 'assert_authorized', 'database_recover',
        'stopped_proof', 'candidate_preflight', 'assert_authorized',
        'start_services', 'guard_proof', 'assert_authorized', 'commit_runtime',
        'terminal_proof', 'assert_authorized', 'finalize_runtime',
        'finalized_proof', 'record_success']


@pytest.mark.parametrize('stage', ['database_recover', 'candidate_preflight',
    'start_services', 'guard_proof', 'commit_runtime', 'terminal_proof',
    'finalize_runtime', 'finalized_proof', 'record_success'])
def test_failure_never_advances_or_claims_success(stage):
    digest = recovery.recover(Adapter())['evidence_sha256']
    adapter = Adapter(stage)
    with pytest.raises(recovery.RecoveryBlocked, match='preserve') as caught:
        recovery.recover(adapter, digest)
    assert 'private failure' not in str(caught.value)
    assert adapter.events[-1] == 'record_failure'
    assert 'record_success' not in adapter.events or stage == 'record_success'
    assert adapter.events[-2] == stage


def test_finalized_terminal_accepts_only_fixed_no_backup_incident():
    calls = []
    validator = SimpleNamespace(validate_terminal=lambda value, sha: calls.append((value, sha)))
    marker = {'old_sha': recovery.OLD_SHA, 'candidate_sha': recovery.FAILED_SHA,
              'mode': 'code-only-no-backup'}
    recovery.validate_finalized_terminal(validator, marker)
    assert calls == [(marker, recovery.FAILED_SHA)]
    assert marker['mode'] == 'code-only-no-backup'
    for changed in ({'mode': 'backup'}, {'old_sha': '0' * 40}, {'candidate_sha': '1' * 40}):
        with pytest.raises(recovery.RecoveryBlocked):
            recovery.validate_finalized_terminal(validator, {**marker, **changed})


def test_noncanonical_local_cli_context_refused():
    with pytest.raises(recovery.RecoveryBlocked):
        recovery.context('a' * 40)


def test_armed_view_projects_only_enablement_preserving_every_other_property():
    system = SimpleNamespace(show=lambda unit, prop: (unit, prop, 'actual'))
    view = recovery.ArmedEnablementView(system, {'backend': 'enabled'})
    assert view.is_enabled('backend') == 'enabled'
    assert view.show('backend', 'ExecStart') == ('backend', 'ExecStart', 'actual')
    with pytest.raises(recovery.RecoveryBlocked):
        view.is_enabled('unknown')
    with pytest.raises(recovery.RecoveryBlocked):
        recovery.ArmedEnablementView(system, {'backend': 'disabled'}).is_enabled('backend')


def test_adapter_finalization_uses_original_failed_candidate_and_lease():
    adapter = object.__new__(recovery.ProductionAdapter)
    calls = []
    lease = recovery.Path('/var/lock/health-app-release')
    adapter.b = SimpleNamespace(BUSINESS_LEASE=lease)
    adapter.token = 'kept-in-memory'
    adapter.tx = SimpleNamespace(finalize=lambda *args: calls.append(args))
    adapter.finalize_runtime()
    assert calls == [(recovery.FAILED_SHA, lease, 'kept-in-memory')]


def test_adapter_writes_success_only_to_separate_audit():
    adapter = object.__new__(recovery.ProductionAdapter)
    adapter.audit = recovery.ROOT / ('exam-service-recovery-' + recovery.FAILED_SHA)
    calls = []
    adapter.h = SimpleNamespace(write_once=lambda *args: calls.append(args))
    adapter.record_success({'state': 'RECOVERED_CANDIDATE'})
    adapter.record_failure({'state': 'NEEDS_OPERATOR'})
    assert [str(x[0]) for x in calls] == [str(adapter.audit / 'completed.json'), str(adapter.audit / 'failed.json')]
    assert all(x[0].parent != recovery.ROOT / recovery.FAILED_SHA for x in calls)


def test_configuration_proof_keeps_original_lease_instance_untouched():
    adapter = object.__new__(recovery.ProductionAdapter)
    system = SimpleNamespace(show=lambda *args: 'actual')
    adapter.proof = SimpleNamespace(systemd=system, lease='original')
    journal = {'boot_gate_released': False, 'original_enablement': {'backend': 'enabled'}}
    calls = []
    adapter.tx = SimpleNamespace(_load_journal=lambda: journal,
        _verify_boot_gate_armed=lambda value: calls.append(value))
    def check(*args):
        proof = args[-2]
        assert isinstance(proof.systemd, recovery.ArmedEnablementView)
        proof.lease = None
        return {'ok': True}
    adapter.retained = SimpleNamespace(candidate_configuration=check)
    adapter.b, adapter.source, adapter.runtime = object(), object(), object()
    assert adapter.configuration_proof() == {'ok': True}
    assert adapter.proof.lease == 'original'
    assert adapter.proof.systemd is system
    assert calls == [journal]


def test_finalized_terminal_matches_real_runtime_no_backup_marker():
    import retained_candidate_retirement as retained
    transaction = recovery.hashlib.sha256(f'{recovery.OLD_SHA}:{recovery.FAILED_SHA}'.encode()).hexdigest()[:32]
    marker = {'version': 1, 'old_sha': recovery.OLD_SHA, 'candidate_sha': recovery.FAILED_SHA,
              'terminal_sha': recovery.FAILED_SHA, 'phase': 'COMMITTED', 'target': 'candidate',
              'result': 'finalized', 'transaction_id': transaction,
              'reap_name': 'runtime-state-transaction.reap-' + transaction,
              'mode': 'code-only-no-backup'}
    recovery.validate_finalized_terminal(retained, marker)
    with pytest.raises(Exception):
        recovery.validate_finalized_terminal(retained, {**marker, 'target': 'old'})
