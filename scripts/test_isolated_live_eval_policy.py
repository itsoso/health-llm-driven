"""Pure contracts only: fixtures contain no real credential or health record."""
import copy

import pytest

from isolated_live_eval_policy import (
    PolicyError, TOKENPLAN_ENDPOINT, TOKENPLAN_HOST,
    project_test_configuration, validate_evaluation_binding,
    validate_isolation_attestation, build_audit_receipt,
)

SHA = 'a' * 40
DIGEST = 'b' * 64


def manifest():
    return {'schema_version': 'synthetic_live_eval.fixture.v1',
            'kind': 'synthetic_health', 'sha256': DIGEST, 'case_count': 5, 'expected_api_calls': 10}


def isolation():
    return {'schema_version': 'synthetic_live_eval.isolation.v1',
            'process_uid': 1001, 'production_paths_accessible': False,
            'production_sockets_accessible': False, 'source_readonly': True,
            'environment_inherited': False, 'production_secret_files_accessible': False,
            'effective_database_url': 'sqlite:///:memory:',
            'max_calls': 10, 'max_tokens': 20000, 'timeout_seconds': 120,
            'deadline_epoch': 1120, 'tls_allowed_hosts': [TOKENPLAN_HOST],
            'tls_verification': True, 'source_sha': SHA, 'fixture_sha256': DIGEST}


def receipt_inputs():
    return {'expected_sha': SHA, 'observed_sha': SHA, 'fixture': manifest(),
            'attestation': isolation(), 'started_at': 1000, 'finished_at': 1010,
            'consent': {'accepted': True, 'policy_version': 'test-policy-v1',
                        'audited': True, 'synthetic_subject': True,
                        'destination': TOKENPLAN_ENDPOINT},
            'usage': [{'provider': 'tokenplan', 'model': 'MiniMax-M2.5',
                       'status': 'success', 'token_source': 'api',
                       'prompt_tokens': 100, 'completion_tokens': 50}] * 10,
            'quality': {'case_count': 5, 'passed': 5, 'failed': 0, 'errored': 0},
            'baseline': {'status': 'missing', 'sha256': None, 'regressions': None},
            'expected_model': 'MiniMax-M2.5'}


def test_configuration_projects_only_disclosed_provider_and_forces_disposable_db():
    source = {'TOKENPLAN_API_KEY': 'synthetic-test-key', 'TOKENPLAN_MODEL': 'MiniMax-M2.5',
              'POSTGRES_PASSWORD': 'never-copy', 'POSTGRES_HOST': 'production',
              'DATABASE_URL': 'postgresql://production', 'SECRET_KEY': 'production-secret',
              'DEBUG': 'true', 'OPENAI_API_KEY': 'never-copy', 'DATA_DIR': '/production',
              'APP_ENV': 'production'}
    original = copy.deepcopy(source)
    result = project_test_configuration(source)
    assert source == original
    assert result['TOKENPLAN_API_KEY'] == 'synthetic-test-key'
    assert result['TOKENPLAN_BASE_URL'] == TOKENPLAN_ENDPOINT
    assert result['APP_ENV'] == 'test'
    assert result['DATABASE_URL'] == 'sqlite:///:memory:'
    assert result['SECRET_KEY'] != source['SECRET_KEY']
    assert result['DEBUG'] == 'false'
    assert result['LLM_AUTO_RECOVERY_ENABLED'] == 'false'
    assert not any(key.startswith('POSTGRES') or key in {'OPENAI_API_KEY', 'DATA_DIR'} for key in result)
    assert all(value != 'never-copy' for value in result.values())


@pytest.mark.parametrize('endpoint', ['http://'+TOKENPLAN_HOST, TOKENPLAN_ENDPOINT+'/',
                                     TOKENPLAN_ENDPOINT+'?key=synthetic',
                                     'https://evil.invalid/v1'])
def test_configuration_rejects_endpoint_substitution(endpoint):
    with pytest.raises(PolicyError):
        project_test_configuration({'TOKENPLAN_API_KEY': 'synthetic', 'TOKENPLAN_BASE_URL': endpoint})


@pytest.mark.parametrize('source', [{}, {'TOKENPLAN_API_KEY': ''},
                                   {'TOKENPLAN_API_KEY': 'synthetic\nkey'},
                                   {'TOKENPLAN_API_KEY': 'one', 'tokenplan_api_key': 'two'}])
def test_configuration_rejects_missing_or_ambiguous_secret_without_echoing(source):
    with pytest.raises(PolicyError) as error:
        project_test_configuration(source)
    assert 'synthetic\nkey' not in str(error.value)


def test_binding_is_exact_and_input_manifest_is_not_mutated():
    data = manifest()
    assert validate_evaluation_binding(SHA, SHA, data) == data
    assert data == manifest()


@pytest.mark.parametrize('fault', ['sha', 'uppercase', 'hash', 'real-data', 'extra', 'boolean-count'])
def test_binding_rejects_drift_non_synthetic_and_unknown_fields(fault):
    data, observed = manifest(), SHA
    if fault == 'sha': observed = 'c' * 40
    elif fault == 'uppercase': observed = SHA.upper()
    elif fault == 'hash': data['sha256'] = 'not-a-hash'
    elif fault == 'real-data': data['kind'] = 'production_health'
    elif fault == 'extra': data['prompt'] = 'forbidden'
    else: data['case_count'] = True
    with pytest.raises(PolicyError):
        validate_evaluation_binding(SHA, observed, data)


@pytest.mark.parametrize('field,value', [
    ('process_uid', 0), ('process_uid', True), ('production_paths_accessible', True),
    ('production_sockets_accessible', True), ('source_readonly', False),
    ('environment_inherited', True), ('production_secret_files_accessible', True),
    ('effective_database_url', 'sqlite:////tmp/persist.db'), ('max_calls', 10000),
    ('max_tokens', 1000000), ('timeout_seconds', 86400), ('deadline_epoch', 0),
    ('tls_allowed_hosts', [TOKENPLAN_HOST, 'evil.invalid']), ('tls_verification', False),
])
def test_attestation_rejects_every_unsafe_boundary(field, value):
    data = isolation()
    data[field] = value
    with pytest.raises(PolicyError):
        validate_isolation_attestation(data)


@pytest.mark.parametrize('fault', ['missing', 'unknown'])
def test_attestation_has_a_closed_complete_schema(fault):
    data = isolation()
    if fault == 'missing': del data['source_readonly']
    else: data['root_override'] = True
    with pytest.raises(PolicyError):
        validate_isolation_attestation(data)


def test_receipt_contains_only_metadata_and_truthful_missing_baseline():
    inputs = receipt_inputs()
    original = copy.deepcopy(inputs)
    receipt = build_audit_receipt(**inputs)
    assert inputs == original
    assert receipt['status'] == 'passed'
    assert receipt['baseline_status'] == 'missing'
    assert receipt['no_regression'] is False
    assert receipt['usage'] == {'calls': 10, 'prompt_tokens': 1000, 'completion_tokens': 500, 'total_tokens': 1500}
    assert receipt['isolation'] == 'declared_not_independently_verified'
    assert receipt['production_call_authorized'] is False
    assert not any(key in repr(receipt) for key in ['api_key', 'prompt\'', 'response\'', 'synthetic-test-key'])


@pytest.mark.parametrize('fault', ['failed-call', 'other-provider', 'fake-usage', 'model',
    'call-budget', 'token-budget', 'deadline', 'duration', 'candidate', 'attested-candidate',
    'fixture', 'consent', 'consent-audit', 'destination', 'unknown-usage', 'unknown-consent',
    'failed-quality', 'boolean-token', 'negative-token', 'no-calls', 'baseline-regression'])
def test_receipt_cannot_pass_invalid_or_unbounded_live_evidence(fault):
    inputs = receipt_inputs()
    row = inputs['usage'][0]
    if fault == 'failed-call': row['status'] = 'error'
    elif fault == 'other-provider': row['provider'] = 'openai'
    elif fault == 'fake-usage': row['token_source'] = 'estimate'
    elif fault == 'model': row['model'] = 'different'
    elif fault == 'call-budget': inputs['usage'] *= 11
    elif fault == 'token-budget': row['prompt_tokens'] = 20001
    elif fault == 'deadline': inputs['finished_at'] = 1121
    elif fault == 'duration': inputs['started_at'] = 800
    elif fault == 'candidate': inputs['observed_sha'] = 'c' * 40
    elif fault == 'attested-candidate': inputs['attestation']['source_sha'] = 'c' * 40
    elif fault == 'fixture': inputs['attestation']['fixture_sha256'] = 'c' * 64
    elif fault == 'consent': inputs['consent']['accepted'] = False
    elif fault == 'consent-audit': inputs['consent']['audited'] = False
    elif fault == 'destination': inputs['consent']['destination'] = 'https://evil.invalid'
    elif fault == 'unknown-usage': row['response'] = 'must-never-appear'
    elif fault == 'unknown-consent': inputs['consent']['token'] = 'must-never-appear'
    elif fault == 'failed-quality': inputs['quality'].update(passed=4, failed=1)
    elif fault == 'boolean-token': row['prompt_tokens'] = True
    elif fault == 'negative-token': row['prompt_tokens'] = -1
    elif fault == 'no-calls': inputs['usage'] = []
    else: inputs['baseline'] = {'status': 'compared', 'sha256': 'e' * 64, 'regressions': 1}
    with pytest.raises(PolicyError) as error:
        build_audit_receipt(**inputs)
    assert 'must-never-appear' not in str(error.value)


def test_valid_baseline_comparison_is_explicit_and_hash_bound():
    inputs = receipt_inputs()
    inputs['baseline'] = {'status': 'compared', 'sha256': 'e' * 64, 'regressions': 0}
    receipt = build_audit_receipt(**inputs)
    assert receipt['no_regression'] is True
    assert receipt['baseline_sha256'] == 'e' * 64


def test_receipt_rejects_missing_calls_against_trusted_fixture_inventory():
    inputs = receipt_inputs()
    inputs['usage'] = inputs['usage'][:1]
    with pytest.raises(PolicyError, match='usage_inventory_mismatch'):
        build_audit_receipt(**inputs)


@pytest.mark.parametrize('payload,field,value', [
    ('baseline', 'regressions', 0), ('baseline', 'sha256', 'e' * 64),
    ('quality', 'extra', True), ('consent', 'synthetic_subject', False),
])
def test_receipt_rejects_fabricated_baseline_or_incomplete_evidence(payload, field, value):
    inputs = receipt_inputs()
    inputs[payload][field] = value
    with pytest.raises(PolicyError):
        build_audit_receipt(**inputs)
