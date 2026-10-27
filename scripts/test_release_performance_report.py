"""Observations never turn CI or an upload into a production receipt."""
import copy
import importlib.util
from pathlib import Path

import pytest


def status_module():
    spec = importlib.util.spec_from_file_location('release_run_status', Path(__file__).with_name('release_run_status.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def status_sample(**changes):
    value = dict(id=12, head_sha='a' * 40, run_attempt=1, name='CI', status='completed', conclusion='success')
    return {**value, **changes}


def test_status_read_retries_transport_only_without_restarting_run():
    import subprocess
    s = status_module()
    calls, sleeps = [], []
    def read(run_id):
        calls.append(run_id)
        if len(calls) < 3:
            raise subprocess.TimeoutExpired('gh', 12)
        return status_sample()
    result, code = s.observe(12, 'a' * 40, 1, read=read, sleep=sleeps.append)
    assert code == 0 and result['status'] == 'completed'
    assert result['release_authority'] is False
    assert calls == [12, 12, 12] and sleeps == [2, 4]


@pytest.mark.parametrize('changes', [{'id':13}, {'head_sha':'b'*40}, {'run_attempt':2}, {'name':'foreign'}, {'name':[]}, {'status':[]}, {'conclusion':[]}, {'status':'completed','conclusion':None}])
def test_status_binding_mismatch_stops_without_retry(changes):
    s = status_module()
    calls = []
    result, code = s.observe(12, 'a'*40, 1, read=lambda n: calls.append(n) or status_sample(**changes), sleep=lambda _: pytest.fail('invalid metadata must not retry'))
    assert code == 2 and result['status'] == 'unknown' and calls == [12]


def test_status_exhausted_read_does_not_leak_error_or_report_success():
    import subprocess
    s = status_module()
    def read(_):
        raise subprocess.CalledProcessError(1, 'gh', stderr='SECRET-private-error')
    result, code = s.observe(12, 'a'*40, 1, read=read, sleep=lambda _: None)
    assert code == 2 and result['status'] == 'unknown'
    assert 'SECRET' not in str(result)


@pytest.mark.parametrize('status,conclusion,expected', [('in_progress',None,3), ('queued',None,3), ('completed','failure',1), ('completed','cancelled',1)])
def test_status_pending_and_failure_are_distinct(status, conclusion, expected):
    result, code = status_module().observe(12, 'a'*40, 1, read=lambda _: status_sample(status=status,conclusion=conclusion), sleep=lambda _: None)
    assert code == expected and result['release_authority'] is False


def test_status_gh_is_one_fixed_read_with_deadline(monkeypatch):
    import json
    import subprocess
    s = status_module()
    def run(argv, **kwargs):
        assert argv[:3] == ['gh','api','repos/itsoso/health-llm-driven/actions/runs/12']
        assert kwargs['timeout'] == 12 and kwargs['check'] is True
        return subprocess.CompletedProcess(argv,0,stdout=json.dumps(status_sample()))
    monkeypatch.setattr(s.subprocess,'run',run)
    assert s.read_run(12) == status_sample()


def test_status_real_trusted_run_title_binds_input_sha():
    s = status_module()
    for name, expected in [('Trusted release · backend · '+'a'*40,0), ('Trusted OTA · publish · '+'a'*40,0), ('Trusted release · backend · '+'b'*40,2)]:
        assert s.observe(12,'a'*40,1,read=lambda _, name=name: status_sample(name=name))[1] == expected


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


def test_critical_path_partitions_wall_without_adding_parallel_jobs():
    r, j = sample()
    job = j['jobs'][0]
    job['steps'] = [
        dict(name='Install dependencies', started_at='2026-10-10T00:00:12Z', completed_at='2026-10-10T00:00:22Z'),
        dict(name='Run isolated shards (balanced-01)', started_at='2026-10-10T00:00:22Z', completed_at='2026-10-10T00:01:02Z'),
    ]
    aggregate = dict(job, id=24, name='backend-tests', steps=[],
                     started_at='2026-10-10T00:01:12Z', completed_at='2026-10-10T00:01:15Z')
    j['jobs'].append(aggregate); j['total_count'] = 2
    row = module().summarize([r], {12:j})['runs'][0]
    path = row['critical_path_breakdown']
    assert path['start_delay_seconds'] == 10
    assert path['step_seconds'] == {'dependency_install':10, 'test_execution':40}
    assert path['unattributed_job_seconds'] == 10
    assert path['after_critical_job_seconds'] == 5
    assert sum(path['step_seconds'].values()) + path['start_delay_seconds'] + path['unattributed_job_seconds'] + path['after_critical_job_seconds'] == row['wall_seconds'] == 75


@pytest.mark.parametrize('start,end', [('00:00:09','00:00:20'), ('00:00:15','00:01:11'), ('00:00:15','00:00:14')])
def test_breakdown_rejects_steps_outside_job_or_negative(start,end):
    r,j=sample()
    j['jobs'][0]['steps']=[dict(name='Install dependencies', started_at=f'2026-10-10T{start}Z', completed_at=f'2026-10-10T{end}Z')]
    with pytest.raises(ValueError):
        module().summarize([r],{12:j})


def test_breakdown_does_not_double_count_overlapping_steps():
    r,j=sample()
    j['jobs'][0]['steps']=[dict(name='unknown private name',started_at='2026-10-10T00:00:15Z',completed_at='2026-10-10T00:00:25Z'),
                          dict(name='Install dependencies',started_at='2026-10-10T00:00:20Z',completed_at='2026-10-10T00:00:30Z')]
    with pytest.raises(ValueError):
        module().summarize([r],{12:j})
