"""Actual orchestration with a synthetic host; never runs production commands."""
import copy

import pytest

from scripts import neo_wechat_runtime_lifecycle as runtime


def context(kind='activate'):
    bindings = {name: 'a' * 64 for name in (
        'dormant_receipt_sha256', 'provisioning_receipt_sha256', 'runtime_sha256',
        'service_unit_sha256', 'socket_unit_sha256', 'config_sha256', 'proxy_receipt_sha256')}
    preserved = {name: 'b' * 64 for name in ('health_services_sha256', 'keys_identity_sha256',
        'data_directory_identity_sha256', 'audit_root_identity_sha256', 'accounts_groups_sha256')}
    return dict(version=1, namespace='runtime-lifecycle-v1', operation_id='c' * 32, kind=kind,
        install_operation_id='d' * 32, provisioning_operation_id='e' * 32,
        dormant_receipt_sha256='a' * 64, provisioning_receipt_sha256='a' * 64,
        runtime_sha256='a' * 64, publisher_sha='f' * 40, production_sha='1' * 40,
        lease_operation_id='c' * 32, lease_identity=[[1, 2], [1, 3]],
        expected_bindings=bindings, expected_preserved=preserved)


class Host:
    """Durable-state and host-effect simulator, deliberately without OS access."""
    def __init__(self, ctx):
        active = ctx['kind'] == 'stop'
        self.snapshot = dict(version=1, bindings=copy.deepcopy(ctx['expected_bindings']),
            preserved=copy.deepcopy(ctx['expected_preserved']),
            units={name: dict(state='active' if active else 'inactive', unit_file_state='static', dropins=[])
                for name in ('neo-wechat.service', 'neo-wechat.socket')},
            proxy=dict(entry='recorded' if active else 'absent', loaded='recorded' if active else 'absent',
                validated=active), socket_path='recorded' if active else 'absent',
            readiness='ready' if active else 'unknown',
            lease=dict(operation_id=ctx['operation_id'], identity=copy.deepcopy(ctx['lease_identity'])))
        self.records = []
        self.actions = []
        self.claimed = False
        self.fail_action = None
        self.fail_record = None

    def guard(self, ctx):
        assert ctx['namespace'] == 'runtime-lifecycle-v1'

    def observe(self, ctx):
        return copy.deepcopy(self.snapshot)

    def assert_fresh(self, ctx):
        if self.claimed:
            raise RuntimeError('synthetic previous operation cannot replay')

    def claim(self, ctx):
        self.assert_fresh(ctx)
        self.claimed = True

    def append_record(self, row):
        self.records.append(copy.deepcopy(row))
        if len(self.records) == self.fail_record:
            raise OSError('synthetic private journal failure')

    def mutation(self, step, *args):
        assert self.records[-1]['phase'] == 'intent'
        assert self.records[-1]['step'] == step
        self.actions.append((step, *args))

    def after(self, step):
        if self.fail_action == step:
            raise TimeoutError('synthetic private unknown result')

    def start_unit(self, unit):
        step = 'start_socket' if unit == 'neo-wechat.socket' else 'start_service'
        self.mutation(step, unit)
        self.snapshot['units'][unit]['state'] = 'active'
        if unit == 'neo-wechat.socket':
            self.snapshot['socket_path'] = 'recorded'
        self.after(step)

    def stop_units(self, units):
        self.mutation('stop_units', units)
        for unit in units:
            self.snapshot['units'][unit]['state'] = 'inactive'
        self.snapshot['socket_path'] = 'absent'
        self.snapshot['readiness'] = 'unknown'
        self.after('stop_units')

    def publish_proxy_include(self, receipt):
        self.mutation('publish_proxy_include', receipt)
        self.snapshot['proxy'].update(entry='recorded', validated=False)
        self.after('publish_proxy_include')

    def unpublish_proxy_include(self, receipt):
        self.mutation('unpublish_proxy_include', receipt)
        self.snapshot['proxy'].update(entry='absent', validated=False)
        self.after('unpublish_proxy_include')

    def validate_proxy(self):
        self.actions.append(('validate_proxy',))
        self.snapshot['proxy']['validated'] = True
        self.after('validate_proxy')
        return True

    def reload_proxy(self, receipt):
        self.mutation('reload_proxy', receipt)
        assert self.snapshot['proxy']['validated']
        self.snapshot['proxy']['loaded'] = self.snapshot['proxy']['entry']
        self.after('reload_proxy')

    def check_readiness(self, kind):
        self.actions.append(('verify_final_state', kind))
        self.snapshot['readiness'] = 'ready' if kind == 'activate' else 'stopped'
        self.after('verify_final_state')
        return True


def test_activation_starts_socket_and_explicit_service_then_validates_before_reload():
    ctx = context()
    host = Host(ctx)
    result = runtime.run(ctx, host)
    assert host.actions == [
        ('start_socket', 'neo-wechat.socket'), ('start_service', 'neo-wechat.service'),
        ('publish_proxy_include', 'a' * 64), ('validate_proxy',),
        ('reload_proxy', 'a' * 64), ('verify_final_state', 'activate')]
    assert result['state'] == 'ACTIVE_UNVERIFIED'
    assert result['acceptance_complete'] is False
    assert result['lease_released'] is False
    assert host.records[-1]['phase'] == 'completed'


def test_stop_both_units_one_request_then_exact_include_only_preserves_material():
    ctx = context('stop')
    host = Host(ctx)
    before = copy.deepcopy(host.snapshot['preserved'])
    result = runtime.run(ctx, host)
    assert host.actions == [('stop_units', ('neo-wechat.socket', 'neo-wechat.service')),
        ('unpublish_proxy_include', 'a' * 64), ('validate_proxy',),
        ('reload_proxy', 'a' * 64), ('verify_final_state', 'stop')]
    assert host.snapshot['preserved'] == before
    assert result['state'] == 'STOPPED_UNPUBLISHED'
    assert result['remote_revocation_confirmed'] is False


@pytest.mark.parametrize('kind,step', [
    ('activate', 'start_socket'), ('activate', 'start_service'),
    ('activate', 'publish_proxy_include'), ('activate', 'validate_proxy'),
    ('activate', 'reload_proxy'), ('activate', 'verify_final_state'),
    ('stop', 'stop_units'), ('stop', 'unpublish_proxy_include'),
    ('stop', 'validate_proxy'), ('stop', 'reload_proxy'), ('stop', 'verify_final_state'),
])
def test_unknown_result_stops_without_compensation_or_retry(kind, step):
    ctx = context(kind)
    host = Host(ctx)
    host.fail_action = step
    with pytest.raises(runtime.RuntimeLifecycleError, match='^runtime_lifecycle_uncertain$'):
        runtime.run(ctx, host)
    assert host.actions[-1][0] == step
    assert host.records[-1]['phase'] == 'intent'
    previous = copy.deepcopy(host.actions)
    ctx['operation_id'] = ctx['lease_operation_id'] = '9' * 32
    host.snapshot['lease']['operation_id'] = '9' * 32
    with pytest.raises(runtime.RuntimeLifecycleError):
        runtime.run(ctx, host)
    assert host.actions == previous


@pytest.mark.parametrize('kind,number', [(kind, number)
    for kind, count in (('activate', 15), ('stop', 13)) for number in range(1, count + 1)])
def test_durable_record_failure_never_advances_after_uncertain_record(kind, number):
    ctx = context(kind)
    host = Host(ctx)
    host.fail_record = number
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert len(host.records) == number
    assert len(host.actions) <= 6
    assert not any(row['phase'] == 'completed' for row in host.records[:-1])


@pytest.mark.parametrize('group,key', [('bindings', 'dormant_receipt_sha256'),
    ('bindings', 'provisioning_receipt_sha256'), ('bindings', 'runtime_sha256'),
    ('bindings', 'service_unit_sha256'), ('bindings', 'socket_unit_sha256'),
    ('bindings', 'config_sha256'), ('bindings', 'proxy_receipt_sha256'),
    ('preserved', 'health_services_sha256'), ('preserved', 'keys_identity_sha256'),
    ('preserved', 'data_directory_identity_sha256'), ('preserved', 'audit_root_identity_sha256'),
    ('preserved', 'accounts_groups_sha256')])
def test_wrong_receipt_or_preserved_identity_blocks_before_claim(group, key):
    ctx = context()
    host = Host(ctx)
    host.snapshot[group][key] = '0' * 64
    with pytest.raises(runtime.RuntimeLifecycleError, match='precondition'):
        runtime.run(ctx, host)
    assert not host.claimed and not host.records and not host.actions


@pytest.mark.parametrize('unit', ['neo-wechat.service', 'neo-wechat.socket'])
def test_dropins_are_rejected_before_claim(unit):
    ctx = context()
    host = Host(ctx)
    host.snapshot['units'][unit]['dropins'] = ['synthetic.conf']
    with pytest.raises(runtime.RuntimeLifecycleError, match='precondition'):
        runtime.run(ctx, host)
    assert not host.claimed


def test_wrong_proxy_entry_cannot_be_removed():
    ctx = context('stop')
    host = Host(ctx)
    host.snapshot['proxy']['entry'] = 'foreign'
    with pytest.raises(runtime.RuntimeLifecycleError, match='precondition'):
        runtime.run(ctx, host)
    assert not host.actions


def test_guard_failure_contains_no_private_error_and_never_claims():
    ctx = context()
    host = Host(ctx)
    def guard(_ctx):
        raise RuntimeError('synthetic-sensitive-error')
    host.guard = guard
    with pytest.raises(runtime.RuntimeLifecycleError) as error:
        runtime.run(ctx, host)
    assert str(error.value) == 'runtime_lifecycle_precondition_failed'
    assert not host.claimed


def test_health_drift_after_service_start_stops_before_proxy_publication():
    ctx = context()
    host = Host(ctx)
    original = host.start_unit
    def changed(unit):
        original(unit)
        if unit == 'neo-wechat.service':
            host.snapshot['preserved']['health_services_sha256'] = '0' * 64
    host.start_unit = changed
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert [row[0] for row in host.actions] == ['start_socket', 'start_service']


def test_no_cli_or_production_adapter_imports():
    assert not hasattr(runtime, 'main')
    assert not hasattr(runtime, 'subprocess')
    assert not hasattr(runtime, 'os')
    assert not hasattr(runtime, 'socket')


def test_failed_validation_prevents_reload_and_does_not_remove_created_include():
    ctx = context()
    host = Host(ctx)
    host.validate_proxy = lambda: False
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert [row[0] for row in host.actions] == ['start_socket', 'start_service', 'publish_proxy_include']
    assert host.snapshot['proxy']['entry'] == 'recorded'
    assert host.snapshot['proxy']['loaded'] == 'absent'


def test_proxy_drift_during_reload_intent_prevents_reload():
    ctx = context()
    host = Host(ctx)
    append = host.append_record
    def changed(row):
        append(row)
        if row['phase'] == 'intent' and row['step'] == 'reload_proxy':
            host.snapshot['proxy']['validated'] = False
    host.append_record = changed
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert not any(row[0] == 'reload_proxy' for row in host.actions)


def test_false_guard_is_not_silently_treated_as_authentication():
    ctx = context()
    host = Host(ctx)
    host.guard = lambda _ctx: False
    with pytest.raises(runtime.RuntimeLifecycleError, match='precondition'):
        runtime.run(ctx, host)
    assert not host.claimed


def test_failed_claim_is_uncertain_even_when_no_unit_effect_observed():
    ctx = context()
    host = Host(ctx)
    def unknown(_ctx):
        host.claimed = True
        raise OSError('synthetic-private')
    host.claim = unknown
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert not host.actions


def test_success_return_without_effect_fails_readback():
    ctx = context()
    host = Host(ctx)
    host.start_unit = lambda _unit: None
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert host.records[-1]['step'] == 'start_socket'
    assert host.records[-1]['phase'] == 'intent'


def test_final_guard_failure_does_not_claim_completed_record_as_success():
    ctx = context()
    host = Host(ctx)
    guard = host.guard
    def changed(value):
        guard(value)
        if host.records and host.records[-1]['phase'] == 'completed':
            raise RuntimeError('synthetic-private')
    host.guard = changed
    with pytest.raises(runtime.RuntimeLifecycleError, match='uncertain'):
        runtime.run(ctx, host)
    assert host.records[-1]['phase'] == 'completed'


@pytest.mark.parametrize('field', ['operation_id', 'identity'])
def test_changed_original_lease_blocks_before_claim(field):
    ctx = context()
    host = Host(ctx)
    host.snapshot['lease'][field] = '9' * 32 if field == 'operation_id' else [[8, 9], [8, 10]]
    with pytest.raises(runtime.RuntimeLifecycleError, match='precondition'):
        runtime.run(ctx, host)
    assert not host.claimed


@pytest.mark.parametrize('kind', ['activate', 'stop'])
def test_live_credentials_never_enter_runtime_records(kind):
    ctx = context(kind)
    host = Host(ctx)
    result = runtime.run(ctx, host)
    assert 'password' not in str(result)
    assert 'webhook' not in str(host.records)
    assert not any('delete' in row[0] or 'purge' in row[0] for row in host.actions)
