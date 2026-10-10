"""Synthetic pure lifecycle evidence checks; never execute lifecycle actions."""
import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'neo_lifecycle', Path(__file__).with_name('neo_wechat_lifecycle.py'))
life = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(life)


def receipt():
    return dict(state='INSTALLED_DORMANT', publisher_sha='a' * 40, production_sha='b' * 40,
        operation_id='c' * 32, evidence_sha256='d' * 64, runtime_sha256='e' * 64,
        proxy_gid=1234, activated=False, nginx_included=False,
        health_services_unchanged=True, secrets_created=False)


def observation():
    return dict(version=1, install_operation_id='c' * 32,
        dormant_receipt_sha256=life.digest(receipt()), runtime_sha256='e' * 64,
        publisher_sha='a' * 40, production_sha='b' * 40,
        bridge='inactive_static', nginx='unpublished', health='unchanged',
        config='empty', data='empty', terminal='absent',
        lease=dict(state='original_present', operation_id='c' * 32,
                   recorded_identity=[[1, 2], [1, 3]], observed_identity=[[1, 2], [1, 3]]))


def chain(observed=None, kind='finalize_install'):
    seen = observed or observation()
    original = receipt()
    result = []
    previous = life.digest(original)
    for step in life.RECONCILIATION_STEPS[:2]:
        for phase in ('intent', 'verified'):
            row = dict(version=1, operation_id=original['operation_id'], kind=kind,
                dormant_receipt_sha256=life.digest(original), previous_record_sha256=previous,
                sequence=len(result) + 1, step=step, phase=phase,
                evidence_sha256=life.digest(seen) if phase == 'verified' else None)
            result.append(row)
            previous = life.digest(row)
    return result


def test_exact_consistent_inventory_is_only_candidate_not_authority():
    result = life.classify_recovery(receipt(), chain(), observation())
    assert result['classification'] == 'FINALIZATION_CANDIDATE'
    assert result['authority'] == 'none'
    assert result['executable_actions'] == []
    assert 'fresh_trusted_locked_observation' in result['remaining_gates']


@pytest.mark.parametrize('field,value', [
    ('activated', True), ('nginx_included', True), ('secrets_created', True),
    ('health_services_unchanged', False), ('proxy_gid', True), ('proxy_gid', 0),
    ('operation_id', 'x'), ('publisher_sha', 'A' * 40), ('state', 'ACTIVE'),
    ('unexpected_secret', 'synthetic-sensitive'),
])
def test_receipt_rejects_expansion_without_echo(field, value):
    value_receipt = receipt()
    value_receipt[field] = value
    with pytest.raises(life.LifecycleError) as error:
        life.validate_dormant_receipt(value_receipt)
    assert str(error.value) == 'lifecycle_evidence_rejected'


def test_detached_receipt_does_not_change_with_caller_mutation():
    value = receipt()
    detached = life.validate_dormant_receipt(value)
    value['publisher_sha'] = 'f' * 40
    assert detached['publisher_sha'] == 'a' * 40


@pytest.mark.parametrize('mutator', [
    lambda rows: rows[0].update(version=2),
    lambda rows: rows[0].update(sequence=True),
    lambda rows: rows[0].update(previous_record_sha256='f' * 64),
    lambda rows: rows[0].update(dormant_receipt_sha256='f' * 64),
    lambda rows: rows[0].update(operation_id='f' * 32),
    lambda rows: rows[0].update(step='delete_state'),
    lambda rows: rows[0].update(kind='activate'),
    lambda rows: rows[0].update(phase='verified'),
    lambda rows: rows[1].update(evidence_sha256=None),
    lambda rows: rows.reverse(),
])
def test_record_tamper_or_invalid_order_is_rejected(mutator):
    rows = chain()
    mutator(rows)
    with pytest.raises(life.LifecycleError):
        life.validate_records(receipt(), rows)


@pytest.mark.parametrize('lease', [
    dict(state='missing', operation_id='c' * 32, recorded_identity=[[1, 2], [1, 3]], observed_identity=None),
    dict(state='foreign', operation_id='f' * 32, recorded_identity=[[1, 2], [1, 3]], observed_identity=[[1, 7], [1, 8]]),
    dict(state='partial', operation_id='c' * 32, recorded_identity=[[1, 2], [1, 3]], observed_identity=None),
    dict(state='original_present', operation_id='c' * 32, recorded_identity=[[1, 2], [1, 3]], observed_identity=[[1, 7], [1, 8]]),
])
def test_lost_replaced_or_partial_lease_is_never_recreated(lease):
    observed = observation()
    observed['lease'] = lease
    result = life.classify_recovery(receipt(), chain(observed), observed)
    assert result['classification'] == 'RETAIN_UNCERTAIN'
    assert result['executable_actions'] == []


@pytest.mark.parametrize('field,value', [
    ('runtime_sha256', 'f' * 64), ('publisher_sha', 'f' * 40),
    ('production_sha', 'f' * 40), ('bridge', 'active'), ('nginx', 'published'),
    ('health', 'changed'), ('config', 'nonempty'), ('data', 'nonempty'),
    ('terminal', 'conflicting'), ('install_operation_id', 'f' * 32),
])
def test_inventory_drift_cannot_finalize_or_offer_removal(field, value):
    observed = observation()
    observed[field] = value
    result = life.classify_recovery(receipt(), chain(observed), observed)
    assert result['classification'] == 'RETAIN_UNCERTAIN'
    assert 'remove' not in str(result).lower()


def test_old_install_evidence_with_no_new_step_provenance_is_retained():
    assert life.classify_recovery(receipt(), [], observation())['classification'] == 'RETAIN_UNCERTAIN'


def test_observation_changed_after_recording_is_rejected():
    rows = chain()
    observed = observation()
    observed['lease']['observed_identity'][0][1] += 1
    assert life.classify_recovery(receipt(), rows, observed)['classification'] == 'RETAIN_UNCERTAIN'


def test_uncertain_finalization_attempt_is_not_replayed():
    rows = chain()
    last = copy.deepcopy(rows[-1])
    last.update(sequence=5, previous_record_sha256=life.digest(rows[-1]),
                step=life.RECONCILIATION_STEPS[2], phase='intent', evidence_sha256=None)
    rows.append(last)
    assert life.classify_recovery(receipt(), rows, observation())['classification'] == 'RETAIN_UNCERTAIN'


def test_deactivation_plan_is_fixed_and_preserves_owner_material():
    plan = life.deactivation_plan(receipt())
    assert plan['executable_actions'] == []
    assert plan['steps'] == list(life.DEACTIVATION_STEPS)
    assert 'stop_and_disable_only_neo_wechat_service_and_socket' in plan['steps']
    assert plan['preserve'] == ['keys', 'encrypted_data', 'audit', 'accounts', 'groups']
    assert plan['revocation'] == 'requires_separate_confirmed_receipt'
    assert 'delete' not in str(plan)
    assert 'purge' not in str(plan)
    assert 'activation' not in str(plan['steps'])


def test_malformed_input_is_bounded_constant_classification():
    for observed in (None, [], {'secret': 'synthetic-sensitive'}):
        result = life.classify_recovery(receipt(), [], observed)
        assert result['classification'] == 'RETAIN_UNCERTAIN'
        assert 'synthetic-sensitive' not in str(result)


def test_module_has_no_io_or_cli_surface():
    import ast
    tree = ast.parse(Path(life.__file__).read_text())
    imports = {alias.name.split('.')[0] for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {'hashlib', 'json', 're'}
    assert not hasattr(life, 'main')
    assert not hasattr(life, 'execute')
    assert not hasattr(life, 'write')


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 1.1, 2 ** 64,
    {'unexpected': 'x' * 4097}, {1: 'nonstring'}, [None] * 129, object()])
def test_digest_rejects_non_json_or_oversize_values(value):
    with pytest.raises(life.LifecycleError, match='^lifecycle_evidence_rejected$'):
        life.digest(value)


def test_recursive_input_rejected_before_python_recursion_limit():
    value = []
    value.append(value)
    with pytest.raises(life.LifecycleError):
        life.digest(value)


def test_record_count_bounded_and_return_detached():
    rows = chain()
    detached = life.validate_records(receipt(), rows)
    rows[0]['kind'] = 'synthetic-sensitive'
    assert detached[0]['kind'] == 'finalize_install'
    with pytest.raises(life.LifecycleError):
        life.validate_records(receipt(), chain() * 2)


def test_unknown_observation_fields_and_bool_identities_rejected():
    observed = observation()
    observed['secret'] = 'synthetic-sensitive'
    assert life.classify_recovery(receipt(), chain(observed), observed)['classification'] == 'RETAIN_UNCERTAIN'
    observed = observation()
    observed['lease']['recorded_identity'][0][0] = True
    observed['lease']['observed_identity'][0][0] = True
    assert life.classify_recovery(receipt(), chain(observed), observed)['classification'] == 'RETAIN_UNCERTAIN'


def test_canonical_hash_is_order_independent_and_value_sensitive():
    assert life.digest({'b': 2, 'a': 1}) == life.digest({'a': 1, 'b': 2})
    assert life.digest({'a': 1}) != life.digest({'a': True})
