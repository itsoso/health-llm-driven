"""Observations never turn CI or an upload into a production receipt."""
import copy
import importlib.util
from pathlib import Path

import pytest


def module():
    spec = importlib.util.spec_from_file_location('release_performance_report', Path(__file__).with_name('release_performance_report.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sample(name='CI', attempt=1):
    run = dict(databaseId=12, workflowName=name, headSha='a' * 40,
               createdAt='2026-10-10T00:00:00Z', conclusion='success', status='completed')
    job = dict(id=23, run_id=12, head_sha='a' * 40, run_attempt=attempt,
               name='backend-test-balanced-01', conclusion='success', status='completed',
               started_at='2026-10-10T00:00:10Z', completed_at='2026-10-10T00:01:10Z', steps=[])
    return run, dict(total_count=1, jobs=[job])


def test_first_attempt_wall_and_runner_time_have_distinct_boundaries():
    r, j = sample()
    result = module().summarize([r], {12: j})
    obs = result['runs'][0]
    assert obs['wall_seconds'] == 70
    assert obs['attempt_execution_span_seconds'] == 60
    assert obs['runner_seconds'] == 60
    assert result['cohorts'][0]['first_attempt_success']['sample_count'] == 1
    assert result['release_authority'] is False


def test_retry_is_not_mixed_into_first_attempt_latency_or_hidden():
    r, j = sample(attempt=2)
    result = module().summarize([r], {12: j})
    assert result['cohorts'][0]['first_attempt_success']['sample_count'] == 0
    assert result['runs'][0]['attempt'] == 2
    assert result['runs'][0]['wall_seconds'] == 70


def test_green_preflight_is_not_backend_and_upload_not_apple_ready():
    r, j = sample('Trusted release')
    j['jobs'][0]['name'] = 'preflight'
    result = module().summarize([r], {12: j})['runs'][0]
    assert result['kind'] == 'preflight-only'
    assert result['production_state'] == 'unverified'
    j['jobs'][0]['name'] = 'testflight'
    result = module().summarize([r], {12: j})['runs'][0]
    assert result['kind'] == 'native-upload-path'
    assert result['apple_processing_seconds'] is None
    assert result['tester_availability'] == 'unverified'


def test_ota_prepare_and_publish_failure_are_separate_observations():
    r, j = sample('Trusted OTA')
    job = j['jobs'][0]
    job['name'] = 'ota'
    job['steps'] = [dict(name='Prepare exact OTA artifact without consuming a publication claim', conclusion='success',
                         started_at=job['started_at'], completed_at=job['completed_at'])]
    assert module().summarize([r], {12: j})['runs'][0]['kind'] == 'ota-prepare'
    job['steps'][0]['name'] = 'Publish one bound iOS artifact and verify server receipt'
    job['steps'][0]['conclusion'] = job['conclusion'] = r['conclusion'] = 'failure'
    result = module().summarize([r], {12: j})['runs'][0]
    assert result['kind'] == 'ota-publish-path'
    assert result['production_state'] == 'unverified'


@pytest.mark.parametrize('mutation', ['truncated', 'sha', 'run', 'mixed-attempt', 'duplicate-job', 'negative-time', 'duplicate-run'])
def test_unbound_or_partial_evidence_is_rejected(mutation):
    r, j = sample()
    runs = [r]
    if mutation == 'truncated':
        j['total_count'] = 2
    elif mutation == 'sha':
        j['jobs'][0]['head_sha'] = 'b' * 40
    elif mutation == 'run':
        j['jobs'][0]['run_id'] = 13
    elif mutation == 'mixed-attempt':
        other = copy.deepcopy(j['jobs'][0]); other.update(id=24, run_attempt=2)
        j['jobs'].append(other); j['total_count'] = 2
    elif mutation == 'duplicate-job':
        j['jobs'].append(copy.deepcopy(j['jobs'][0])); j['total_count'] = 2
    elif mutation == 'negative-time':
        j['jobs'][0]['completed_at'] = '2026-10-09T00:00:00Z'
    elif mutation == 'duplicate-run':
        runs.append(copy.deepcopy(r))
    with pytest.raises(ValueError):
        module().summarize(runs, {12: j})


def test_pending_and_failed_samples_not_disguised_as_success_or_zero_duration():
    r, j = sample()
    r['status'] = j['jobs'][0]['status'] = 'in_progress'
    r['conclusion'] = j['jobs'][0]['conclusion'] = None
    j['jobs'][0]['completed_at'] = None
    result = module().summarize([r], {12: j})
    assert result['runs'][0]['wall_seconds'] is None
    assert result['cohorts'][0]['first_attempt_success']['sample_count'] == 0


def test_raw_names_and_payloads_do_not_enter_report():
    import json
    r, j = sample('Trusted release')
    j['jobs'][0]['name'] = 'secret=DO_NOT_EMIT'
    j['jobs'][0]['steps'] = [dict(name='patient=DO_NOT_EMIT', conclusion='failure')]
    j['jobs'][0]['untrusted'] = 'DO_NOT_EMIT'
    result = json.dumps(module().summarize([r], {12: j}))
    assert 'DO_NOT_EMIT' not in result
