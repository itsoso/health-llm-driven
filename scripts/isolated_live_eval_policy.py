"""Transport-independent declarations for a reviewed synthetic live evaluation.

These pure functions do not read credentials, inspect the OS, call providers,
create a launcher, or grant permission. A trusted launcher must independently
prove every isolation claim and pin expected_sha/model/fixture before calling.
Passing this policy cannot by itself establish G3, isolation, or authorization.
Never serialize the configuration projection: it contains the supplied key.
"""
from collections.abc import Mapping
import re

TOKENPLAN_HOST = 'token-plan.cn-beijing.maas.aliyuncs.com'
TOKENPLAN_ENDPOINT = 'https://' + TOKENPLAN_HOST + '/compatible-mode/v1'
MAX_CALLS = 20
MAX_TOKENS = 50000
MAX_TIMEOUT_SECONDS = 300


class PolicyError(ValueError):
    """Value-free failure codes: never interpolate caller-controlled material."""


def _require(condition, code):
    if not condition:
        raise PolicyError(code)


def _closed(value, fields, code):
    _require(isinstance(value, Mapping) and set(value) == set(fields), code)


def _integer(value, low, high, code):
    _require(type(value) is int and low <= value <= high, code)


def _sha(value, size, code):
    _require(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(size) + '}', value) is not None, code)


def _model(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is not None, 'invalid_model')
    return value


def project_test_configuration(source):
    """Project already-supplied data, without loading any secret/config source.

    Only provider inputs are retained. Production DB/passwords, security keys,
    other providers, debug flags and paths are intentionally never inherited.
    Trusted operators supply this mapping; this function is not a secret reader.
    """
    _require(isinstance(source, Mapping), 'invalid_configuration_mapping')
    selected = {}
    for key, value in source.items():
        _require(isinstance(key, str), 'invalid_configuration_name')
        name = key.upper()
        if name in {'TOKENPLAN_API_KEY', 'TOKENPLAN_MODEL', 'TOKENPLAN_BASE_URL'}:
            _require(name not in selected, 'ambiguous_provider_configuration')
            selected[name] = value
    key = selected.get('TOKENPLAN_API_KEY')
    _require(isinstance(key, str) and 1 <= len(key) <= 4096
             and all(32 < ord(character) < 127 for character in key), 'invalid_provider_credential')
    _require(selected.get('TOKENPLAN_BASE_URL', TOKENPLAN_ENDPOINT) == TOKENPLAN_ENDPOINT,
             'undisclosed_provider_endpoint')
    model = _model(selected.get('TOKENPLAN_MODEL', 'MiniMax-M2.5'))
    return {
        'TOKENPLAN_API_KEY': key, 'TOKENPLAN_BASE_URL': TOKENPLAN_ENDPOINT,
        'TOKENPLAN_MODEL': model, 'LLM_PROVIDER': 'tokenplan',
        'APP_ENV': 'test', 'DATABASE_URL': 'sqlite:///:memory:',
        'TEST_DATABASE_URL': '', 'SKIP_DB_INIT': '1', 'DEBUG': 'false',
        'SECRET_KEY': 'synthetic-live-eval-public-test-secret-32chars',
        'LLM_AUTO_RECOVERY_ENABLED': 'false',
        'TOKENPLAN_GLOBAL_DAILY_CALL_QUOTA': str(MAX_CALLS),
        'TOKENPLAN_USER_DAILY_CALL_QUOTA': str(MAX_CALLS),
        'TOKENPLAN_USER_MONTHLY_TOKEN_QUOTA': str(MAX_TOKENS),
    }


def validate_evaluation_binding(expected_sha, observed_sha, fixture):
    """Check identity/shape; a synthetic label is not proof of synthetic origin."""
    _sha(expected_sha, 40, 'invalid_expected_sha')
    _sha(observed_sha, 40, 'invalid_observed_sha')
    _require(expected_sha == observed_sha, 'candidate_drift')
    _closed(fixture, {'schema_version', 'kind', 'sha256', 'case_count', 'expected_api_calls'}, 'invalid_fixture_schema')
    _require(fixture['schema_version'] == 'synthetic_live_eval.fixture.v1'
             and fixture['kind'] == 'synthetic_health', 'non_synthetic_fixture')
    _sha(fixture['sha256'], 64, 'invalid_fixture_digest')
    _integer(fixture['case_count'], 1, 20, 'invalid_fixture_case_count')
    _integer(fixture['expected_api_calls'], 1, MAX_CALLS, 'invalid_fixture_call_count')
    return dict(fixture)


def validate_isolation_attestation(attestation):
    """Validate a closed claim. The caller still must prove the OS reality."""
    fields = {'schema_version', 'process_uid', 'production_paths_accessible',
              'production_sockets_accessible', 'source_readonly', 'environment_inherited',
              'production_secret_files_accessible', 'effective_database_url',
              'max_calls', 'max_tokens', 'timeout_seconds', 'deadline_epoch',
              'tls_allowed_hosts', 'tls_verification', 'source_sha', 'fixture_sha256'}
    _closed(attestation, fields, 'invalid_isolation_schema')
    _require(attestation['schema_version'] == 'synthetic_live_eval.isolation.v1', 'invalid_isolation_version')
    _integer(attestation['process_uid'], 1, 2**32 - 2, 'root_or_invalid_identity')
    for name in ('production_paths_accessible', 'production_sockets_accessible',
                 'environment_inherited', 'production_secret_files_accessible'):
        _require(attestation[name] is False, 'unsafe_isolation_boundary')
    for name in ('source_readonly', 'tls_verification'):
        _require(attestation[name] is True, 'unsafe_isolation_boundary')
    _require(attestation['effective_database_url'] == 'sqlite:///:memory:', 'non_memory_database')
    _integer(attestation['max_calls'], 1, MAX_CALLS, 'unbounded_calls')
    _integer(attestation['max_tokens'], 1, MAX_TOKENS, 'unbounded_tokens')
    _integer(attestation['timeout_seconds'], 1, MAX_TIMEOUT_SECONDS, 'unbounded_timeout')
    _integer(attestation['deadline_epoch'], 1, 2**63 - 1, 'invalid_deadline')
    _require(type(attestation['tls_allowed_hosts']) is list
             and attestation['tls_allowed_hosts'] == [TOKENPLAN_HOST], 'undisclosed_tls_host')
    _sha(attestation['source_sha'], 40, 'invalid_attested_sha')
    _sha(attestation['fixture_sha256'], 64, 'invalid_attested_fixture')
    result = dict(attestation)
    result['tls_allowed_hosts'] = list(attestation['tls_allowed_hosts'])
    return result


def build_audit_receipt(*, expected_sha, observed_sha, fixture, attestation,
                        started_at, finished_at, consent, usage, quality,
                        baseline, expected_model):
    """Return a redacted declaration summary, never a production authorization.

    Usage must be extracted by a reviewed adapter from normal API usage audit,
    not supplied by the evaluated model. No prompts, responses, errors or keys
    are accepted. Missing baseline remains missing, even if all cases pass.
    """
    fixture = validate_evaluation_binding(expected_sha, observed_sha, fixture)
    isolation = validate_isolation_attestation(attestation)
    _require(isolation['source_sha'] == expected_sha, 'attested_candidate_drift')
    _require(isolation['fixture_sha256'] == fixture['sha256'], 'attested_fixture_drift')
    _integer(started_at, 1, 2**63 - 1, 'invalid_start_time')
    _integer(finished_at, started_at, 2**63 - 1, 'invalid_finish_time')
    _require(finished_at <= isolation['deadline_epoch']
             and isolation['deadline_epoch'] - started_at <= isolation['timeout_seconds']
             and finished_at - started_at <= isolation['timeout_seconds'], 'evaluation_deadline_exceeded')
    model = _model(expected_model)
    _closed(consent, {'accepted', 'policy_version', 'audited', 'synthetic_subject', 'destination'}, 'invalid_consent_schema')
    _require(all(consent[name] is True for name in ('accepted', 'audited', 'synthetic_subject')),
             'missing_audited_synthetic_consent')
    _require(isinstance(consent['policy_version'], str)
             and re.fullmatch(r'[A-Za-z0-9._-]{1,80}', consent['policy_version']) is not None,
             'invalid_consent_version')
    _require(consent['destination'] == TOKENPLAN_ENDPOINT, 'undisclosed_consent_destination')
    _require(type(usage) is list and 1 <= len(usage) <= isolation['max_calls'], 'usage_call_budget_exceeded')
    _require(len(usage) == fixture['expected_api_calls'], 'usage_inventory_mismatch')
    totals = {'calls': len(usage), 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    for row in usage:
        _closed(row, {'provider', 'model', 'status', 'token_source', 'prompt_tokens', 'completion_tokens'}, 'invalid_usage_schema')
        _require(row['provider'] == 'tokenplan' and row['model'] == model, 'usage_provider_or_model_drift')
        _require(row['status'] == 'success' and row['token_source'] == 'api', 'unverified_or_failed_api_call')
        for name in ('prompt_tokens', 'completion_tokens'):
            _integer(row[name], 0, MAX_TOKENS, 'invalid_api_token_count')
            totals[name] += row[name]
        _require(row['prompt_tokens'] + row['completion_tokens'] > 0, 'empty_api_usage')
    totals['total_tokens'] = totals['prompt_tokens'] + totals['completion_tokens']
    _require(totals['total_tokens'] <= isolation['max_tokens'], 'usage_token_budget_exceeded')
    _closed(quality, {'case_count', 'passed', 'failed', 'errored'}, 'invalid_quality_schema')
    for name in quality:
        _integer(quality[name], 0, 20, 'invalid_quality_count')
    _require(quality['case_count'] == fixture['case_count'] == quality['passed']
             and quality['failed'] == quality['errored'] == 0, 'quality_gate_failed')
    _closed(baseline, {'status', 'sha256', 'regressions'}, 'invalid_baseline_schema')
    _require(baseline['status'] in {'missing', 'compared'}, 'invalid_baseline_status')
    compared = baseline['status'] == 'compared'
    if compared:
        _sha(baseline['sha256'], 64, 'invalid_baseline_digest')
        _integer(baseline['regressions'], 0, 20, 'invalid_regression_count')
        _require(baseline['regressions'] == 0, 'baseline_regression')
    else:
        _require(baseline['sha256'] is None and baseline['regressions'] is None, 'fabricated_missing_baseline')
    return {'schema_version': 'synthetic_live_eval.receipt.v1', 'status': 'passed',
            'candidate_sha': expected_sha, 'fixture_sha256': fixture['sha256'],
            'case_count': fixture['case_count'], 'model': model,
            'endpoint': TOKENPLAN_ENDPOINT, 'consent_policy_version': consent['policy_version'],
            'started_at': started_at, 'finished_at': finished_at, 'usage': totals,
            'baseline_status': baseline['status'], 'baseline_sha256': baseline['sha256'],
            'no_regression': compared, 'isolation': 'declared_not_independently_verified',
            'production_call_authorized': False}
