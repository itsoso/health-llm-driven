"""Fixed retained artifact: no vendor writes, credentials, or production access."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SHA = 'a' * 40


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def vendor(module):
    build = copy.deepcopy(load('built_unuploaded_proof').BUILD)
    submission = {'id': '12345678-1234-1234-1234-123456789abc', 'status': 'FINISHED',
                  'platform': 'IOS', 'app': build['app'],
                  'iosConfig': {'ascAppIdentifier': module.ASC_APP},
                  'submittedBuild': {'id': module.BUILD_ID}}
    build['submissions'] = [submission]
    return build


def test_vendor_requires_one_finished_exact_build_submission():
    m = load('trusted_retained_testflight')
    good = vendor(m)
    m.validate_after(good)
    for key, value in [('status', 'ERRORED'), ('platform', 'ANDROID'),
                       ('submittedBuild', {'id': 'wrong'}), ('app', {'id': 'wrong'}),
                       ('iosConfig', {'ascAppIdentifier': 'wrong'})]:
        bad = copy.deepcopy(good)
        bad['submissions'][0][key] = value
        with pytest.raises(ValueError):
            m.validate_after(bad)
    for submissions in ([], good['submissions'] * 2):
        bad = copy.deepcopy(good)
        bad['submissions'] = submissions
        with pytest.raises(ValueError):
            m.validate_after(bad)
    for key, value in [('gitCommitHash', SHA), ('id', 'wrong'), ('appBuildVersion', '275'),
                       ('isForIosSimulator', 0), ('unexpected', True)]:
        bad = copy.deepcopy(good)
        bad[key] = value
        with pytest.raises(ValueError):
            m.validate_after(bad)


@pytest.mark.parametrize('path', ['mobile/app.json', 'backend/app/main.py', 'packages/shared/index.ts',
                                 'infra/laya/installer.py', 'scripts/unknown.py', 'docs/prompts.md'])
def test_runtime_or_unknown_tree_delta_is_rejected(path):
    m = load('trusted_retained_testflight')
    with pytest.raises(ValueError):
        m.validate_paths([path])


def test_known_release_tools_only():
    m = load('trusted_retained_testflight')
    m.validate_paths(['scripts/contained_recovery_proof.py', 'scripts/trusted_retained_testflight.py',
                      '.github/workflows/trusted-release.yml'])


@pytest.fixture
def state(tmp_path, monkeypatch):
    s, m, old = (load(name) for name in ('trusted_release_server', 'trusted_retained_testflight', 'built_unuploaded_proof'))
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(s, 'STATE', tmp_path)
    monkeypatch.setattr(s, 'BUSINESS_LEASE', tmp_path / 'business-lease')
    monkeypatch.setattr(s, 'secure_path', lambda *a, **k: None)
    monkeypatch.setattr(s, 'validate_metadata', lambda *a, **k: None)
    monkeypatch.setattr(s, '_assert_deployment_window', lambda p: None)
    monkeypatch.setattr(s, 'validate_loopback', lambda p: None)
    monkeypatch.setattr(s, 'assert_ota_history', lambda: None)
    monkeypatch.setattr(m, 'prove_backend', lambda *a, **k: {'sha': SHA, 'production_sha': SHA, 'state': 'COMPATIBLE'})
    monkeypatch.setattr(m, 'prove_original', lambda *a, **k: {key: '1' * 64 for key in ('retirement', 'closure', 'build_claim')})
    monkeypatch.setattr(m, 'validate_before', lambda p: None)
    monkeypatch.setattr(m.time, 'time', lambda: 1000)
    def move(source, destination):
        if destination.exists():
            raise ValueError('destination exists')
        source.rename(destination)
    monkeypatch.setattr(m, 'move_noreplace', move)
    (tmp_path / SHA).mkdir()
    (tmp_path / SHA / 'completed.json').write_text(json.dumps({'sha': SHA, 'state': 'SUCCEEDED'}))
    before = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000, 'before': {'proof': 'exact'}}
    return s, m, before


def test_once_only_claim_lease_and_finish(state):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    assert result['state'] == 'CLAIMED'
    assert s.BUSINESS_LEASE.exists()
    with pytest.raises(ValueError):
        m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    assert m.finish(s, SimpleNamespace(), SHA, after)['state'] == 'UPLOADED'
    assert not s.BUSINESS_LEASE.exists()
    m.validate_history(s, m.operation())
    s.BUSINESS_LEASE.mkdir()
    (s.BUSINESS_LEASE / 'foreign').write_text('untouched')
    assert m.finish(s, SimpleNamespace(), SHA, after)['state'] == 'UPLOADED'
    assert (s.BUSINESS_LEASE / 'foreign').exists()
    with pytest.raises(ValueError):
        m.claim(s, SimpleNamespace(), {'sha': 'b' * 40}, {**before, 'sha': 'b' * 40})


@pytest.mark.parametrize('bad', ['vendor', 'claim', 'production'])
def test_unknown_or_drift_preserves_claim_and_lease(state, monkeypatch, bad):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    inode = s.BUSINESS_LEASE.stat().st_ino
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    if bad == 'vendor':
        after['after']['submissions'] = []
    elif bad == 'claim':
        after['claim_id'] = '0' * 64
    else:
        monkeypatch.setattr(m, 'prove_backend', lambda *a, **k: (_ for _ in ()).throw(ValueError('drift')))
    with pytest.raises(ValueError):
        m.finish(s, SimpleNamespace(), SHA, after)
    assert s.BUSINESS_LEASE.stat().st_ino == inode
    assert not (m.operation() / 'completed.json').exists()


def test_workflow_retained_target_never_builds_or_deploys():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    assert 'retained-testflight' in workflow.get('on', workflow.get(True))['workflow_dispatch']['inputs']['target']['options']
    for name in ('ios-build', 'backend', 'testflight'):
        assert 'retained-testflight' not in workflow['jobs'][name]['if']
    job = workflow['jobs']['retained-testflight']
    assert job['needs'] == 'preflight'
    assert 'trusted_retained_testflight.py' in json.dumps(job)


@pytest.mark.parametrize('name', ['verified.json', 'completed.json'])
def test_finish_only_crash_recovery_never_repeats_vendor(state, monkeypatch, name):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    inode = s.BUSINESS_LEASE.stat().st_ino
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    original = m.write
    def fail(server, path, value):
        if path.name == name:
            if name == 'verified.json':
                original(server, path, value)
            raise OSError('simulated interrupted persistence')
        original(server, path, value)
    monkeypatch.setattr(m, 'write', fail)
    with pytest.raises(OSError):
        m.finish(s, SimpleNamespace(), SHA, after)
    monkeypatch.setattr(m, 'write', original)
    monkeypatch.setattr(m, 'prove_backend', lambda *a: (_ for _ in ()).throw(AssertionError('not a second transaction')))
    assert m.finish(s, SimpleNamespace(), SHA, after, recover=True)['state'] == 'UPLOADED'
    retired = s.BUSINESS_LEASE.with_name(s.BUSINESS_LEASE.name + '.retained-' + m.BUILD_ID)
    assert retired.stat().st_ino == inode


def test_recover_without_verified_receipt_is_blocked(state):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    with pytest.raises(ValueError, match='previously persisted'):
        m.finish(s, SimpleNamespace(), SHA, after, recover=True)
    assert s.BUSINESS_LEASE.exists()


def test_extra_inventory_blocks_before_lease_release(state):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    (m.operation() / 'foreign').write_text('unknown')
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    with pytest.raises(ValueError, match='inventory'):
        m.finish(s, SimpleNamespace(), SHA, after)
    assert s.BUSINESS_LEASE.exists()


@pytest.mark.parametrize('observed', [0, 879, 1011, True, 1000.0])
def test_stale_or_malformed_proof_never_consumes(state, observed):
    s, m, before = state
    with pytest.raises(ValueError):
        m.claim(s, SimpleNamespace(), {'sha': SHA}, {**before, 'observed_at': observed})
    assert not m.operation().exists()
    assert not s.BUSINESS_LEASE.exists()


def test_foreign_lease_blocks_without_new_intent(state):
    s, m, before = state
    s.BUSINESS_LEASE.mkdir()
    with pytest.raises(ValueError):
        m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    assert not m.operation().exists()


def test_global_history_blocks_partial_and_validates_without_sysmodules(state, monkeypatch):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    monkeypatch.setattr(s, '_retained_module', lambda sha: m)
    with pytest.raises(ValueError):
        s.assert_retained_history()
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    m.finish(s, SimpleNamespace(), SHA, after)
    s.assert_retained_history()


def test_new_rpc_stays_policy_bound():
    s = load('trusted_release_server')
    for action in ('claim-retained-testflight', 'finish-retained-testflight'):
        assert s.authorize_command(action + ' ' + SHA, {'sha': SHA}) == action
        with pytest.raises(s.LaunchError):
            s.authorize_command(action + ' ' + 'b' * 40, {'sha': SHA})


def test_preproof_original_contract_remains_exact():
    m, c = load('trusted_retained_testflight'), load('built_unuploaded_proof')
    m.CONTRACT = c
    proof = {'profile': 'finished-build-unuploaded-v1', 'failed_sha': c.RUN['head_sha'],
             'run_id': c.RUN['id'], 'run_attempt': 1, 'build_id': c.BUILD['id'],
             'build': c.BUILD, 'canonical_hashes': c.HASHES,
             'jobs_sha256': c.JOBS_HASH, 'log_sha256': c.LOG_HASH}
    m.validate_before(proof)
    bad = copy.deepcopy(proof)
    bad['build']['submissions'] = [{'id': 'any'}]
    with pytest.raises(c.ProofError):
        m.validate_before(bad)


@pytest.mark.parametrize('failure', ['rename', 'parent_fsync'])
def test_terminal_is_durable_before_lease_release_and_recovery(state, monkeypatch, failure):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    original_rename, original_sync = m.move_noreplace, s._sync_business_lease_parent
    if failure == 'rename':
        def fail(src, dst):
            m.validate_history(s, m.operation())
            assert s.BUSINESS_LEASE.exists()
            raise OSError('rename interrupted')
        monkeypatch.setattr(m, 'move_noreplace', fail)
    else:
        def fail():
            m.validate_history(s, m.operation())
            raise OSError('fsync interrupted')
        monkeypatch.setattr(s, '_sync_business_lease_parent', fail)
    with pytest.raises(OSError):
        m.finish(s, SimpleNamespace(), SHA, after)
    m.validate_history(s, m.operation())
    monkeypatch.setattr(m, 'move_noreplace', original_rename)
    monkeypatch.setattr(s, '_sync_business_lease_parent', original_sync)
    assert m.finish(s, SimpleNamespace(), SHA, after, recover=True)['state'] == 'UPLOADED'
    assert not s.BUSINESS_LEASE.exists()


def test_runner_workflow_gates_credentials_and_rejects_wrong_dispatch():
    import subprocess
    import yaml
    w = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    steps = w['jobs']['retained-testflight']['steps']
    assert all('secrets.' not in str(step) for step in steps[:3])
    body = steps[0]['run']
    assert 'fetch --depth=1 origin 514c8c28a87ad5761a6f66b284c19a69dff33e8f' in body
    prefix = body.split('/usr/bin/sudo', 1)[0]
    for override in ({'GITHUB_REF': 'refs/heads/other'}, {'GITHUB_SHA': 'b' * 40},
                     {'GITHUB_REPOSITORY': 'other/repo'}, {'TARGET_SHA': 'bad'}):
        env = {'PATH': '/nonexistent', 'TARGET_SHA': SHA, 'GITHUB_SHA': SHA,
               'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': 'itsoso/health-llm-driven', **override}
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-eu', '-c', prefix],
                                env=env, capture_output=True)
        assert result.returncode != 0


def test_unknown_global_audit_blocks_even_different_publisher(state, monkeypatch):
    s, m, before = state
    root = m.operation().parent
    root.mkdir(mode=0o700)
    (root / 'unknown').mkdir(mode=0o700)
    with pytest.raises(s.LaunchError):
        s.assert_retained_history()


@pytest.mark.parametrize('directory_kind', ['directory', 'dangling_symlink'])
def test_cached_helpers_rejected_before_import(tmp_path, monkeypatch, directory_kind):
    m = load('trusted_retained_testflight')
    script = tmp_path / 'scripts' / 'helper.py'
    script.parent.mkdir()
    script.write_text('raise AssertionError("must not execute")')
    cache = script.parent / '__pycache__'
    if directory_kind == 'directory':
        cache.mkdir()
    else:
        cache.symlink_to(tmp_path / 'absent')
    # Test the actual loader's cache check without requiring a root temp tree.
    original = Path.lstat
    def metadata(path):
        value = original(path)
        return SimpleNamespace(st_uid=0, st_mode=value.st_mode & ~0o022)
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(ValueError, match='cached'):
        m.load(tmp_path, SHA, 'helper.py')


def test_completed_write_precedes_real_lease_release(state, monkeypatch):
    s, m, before = state
    result = m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    original = m.write
    def check(server, path, value):
        if path.name == 'completed.json':
            assert s.BUSINESS_LEASE.exists()
            assert (m.operation() / 'released-lease').exists()
        original(server, path, value)
    monkeypatch.setattr(m, 'write', check)
    after = {'sha': SHA, 'profile': m.PROFILE, 'observed_at': 1000,
             'claim_id': result['claim_id'], 'after': vendor(m)}
    m.finish(s, SimpleNamespace(), SHA, after)


def test_no_clobber_move_checks_actual_same_inode(tmp_path, monkeypatch):
    m = load('trusted_retained_testflight')
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    calls = []
    monkeypatch.setattr(m.subprocess, 'run', lambda args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match='no-clobber'):
        m.move_noreplace(source, target)
    assert calls == [['/usr/bin/mv', '--no-clobber', '-T', '--', str(source), str(target)]]
    assert source.exists() and target.exists()


@pytest.mark.skipif(sys.platform != 'linux', reason='GNU mv exact production flags require Linux CI')
def test_linux_no_clobber_move_preserves_inode_and_existing_destination(tmp_path):
    m = load('trusted_retained_testflight')
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    inode = source.stat().st_ino
    m.move_noreplace(source, target)
    assert not source.exists() and target.stat().st_ino == inode
    source.mkdir()
    source_inode = source.stat().st_ino
    # Coreutils versions differ: a skipped collision may return either zero
    # (then our inode check rejects it) or one (check=True rejects it first).
    # Both must leave the original source and destination identities intact.
    with pytest.raises((ValueError, subprocess.CalledProcessError)) as rejected:
        m.move_noreplace(source, target)
    if isinstance(rejected.value, subprocess.CalledProcessError):
        assert rejected.value.returncode == 1
        assert rejected.value.cmd == ['/usr/bin/mv', '--no-clobber', '-T', '--', str(source), str(target)]
    else:
        assert 'no-clobber' in str(rejected.value)
    assert source.stat().st_ino == source_inode and target.stat().st_ino == inode


@pytest.mark.parametrize('existing_root', [False, True])
def test_claim_persists_global_parent_before_lease_permission(state, monkeypatch, existing_root):
    s, m, before = state
    root = m.operation().parent
    if existing_root:
        root.mkdir(mode=0o700)
    synced = []
    original_sync, original_acquire = s._sync_directory, s._acquire_testflight_lease
    def sync(path):
        original_sync(path)
        synced.append(Path(path))
    def acquire(workspace):
        assert m.STATE in synced
        assert root in synced
        assert synced.index(m.STATE) < synced.index(root)
        return original_acquire(workspace)
    monkeypatch.setattr(s, '_sync_directory', sync)
    monkeypatch.setattr(s, '_acquire_testflight_lease', acquire)
    assert m.claim(s, SimpleNamespace(), {'sha': SHA}, before)['state'] == 'CLAIMED'


def test_global_parent_fsync_failure_never_grants_upload_or_lease(state, monkeypatch):
    s, m, before = state
    original = s._sync_directory
    def fail(path):
        if Path(path) == m.STATE:
            raise OSError('global audit parent persistence failed')
        original(path)
    monkeypatch.setattr(s, '_sync_directory', fail)
    with pytest.raises(OSError, match='parent persistence'):
        m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
    assert not s.BUSINESS_LEASE.exists()
    assert not (m.operation() / 'claimed.json').exists()


@pytest.mark.parametrize('fail_parent_sync', [False, True])
def test_persistent_registry_and_volatile_lease_have_independent_durability(state, monkeypatch, fail_parent_sync):
    s, m, before = state
    persistent, volatile = m.STATE / 'persistent-state', m.STATE / 'volatile-locks'
    persistent.mkdir(mode=0o700)
    volatile.mkdir(mode=0o700)
    (persistent / SHA).mkdir()
    (persistent / SHA / 'completed.json').write_text(json.dumps({'sha': SHA, 'state': 'SUCCEEDED'}))
    monkeypatch.setattr(s, 'STATE', persistent)
    monkeypatch.setattr(m, 'STATE', persistent)
    monkeypatch.setattr(s, 'BUSINESS_LEASE', volatile / 'business-lease')
    assert s.BUSINESS_LEASE.parent != m.STATE
    original_sync, original_acquire = s._sync_directory, s._acquire_testflight_lease
    events = []
    def sync(path):
        if Path(path) == persistent and fail_parent_sync:
            raise OSError('persistent directory parent not durable')
        original_sync(path)
        events.append(('fsync', Path(path)))
    def acquire(workspace):
        assert ('fsync', persistent) in events
        events.append(('lease', volatile))
        return original_acquire(workspace)
    monkeypatch.setattr(s, '_sync_directory', sync)
    monkeypatch.setattr(s, '_acquire_testflight_lease', acquire)
    if fail_parent_sync:
        with pytest.raises(OSError, match='not durable'):
            m.claim(s, SimpleNamespace(), {'sha': SHA}, before)
        assert ('lease', volatile) not in events
        assert not s.BUSINESS_LEASE.exists()
        assert not (m.operation() / 'claimed.json').exists()
    else:
        assert m.claim(s, SimpleNamespace(), {'sha': SHA}, before)['state'] == 'CLAIMED'
        assert events.index(('fsync', persistent)) < events.index(('lease', volatile))
