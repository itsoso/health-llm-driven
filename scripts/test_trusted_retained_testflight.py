"""Fixed retained artifact: no vendor writes, credentials, or production access."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
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


def hardening_code():
    import yaml
    w = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    body = w['jobs']['retained-testflight']['steps'][0]['run']
    return body.split("<<'REVA_RUNNER_ROOT'\n", 1)[1].split('\nREVA_RUNNER_ROOT', 1)[0]


def test_retained_runner_hardening_and_smoke_precede_credentials():
    import yaml
    w = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    steps = w['jobs']['retained-testflight']['steps']
    assert "harden(Path('/opt'))" in hardening_code()
    smoke = next(i for i, step in enumerate(steps) if '--check-runner' in step.get('run', ''))
    credentials = next(i for i, step in enumerate(steps) if 'EXPO_TOKEN' in str(step))
    assert smoke < credentials
    assert all('secrets.' not in str(step) for step in steps[:smoke + 1])
    assert '--runner ' not in steps[smoke]['run']


def test_source_smoke_loads_both_helpers_without_reading_credentials(monkeypatch):
    m = load('trusted_retained_testflight')
    seen = []
    def checked_load(source, sha, filename):
        seen.append(filename)
        return SimpleNamespace()
    def read_git(source, *args):
        return (SHA + '\n').encode() if args == ('rev-parse', 'HEAD') else b''
    monkeypatch.setattr(m, 'load', checked_load)
    monkeypatch.setattr(m, 'git', read_git)
    class ForbiddenEnvironment(dict):
        def get(self, *args):
            raise AssertionError('credential lookup forbidden in smoke')
    monkeypatch.setattr(m.os, 'environ', ForbiddenEnvironment())
    m.validate_runner_source(Path('/opt/reva-release/source'), SHA)
    assert seen == ['built_unuploaded_proof.py', 'trusted_release_gate.py']


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                    reason='real root-owned canonical loader requires dedicated Linux sudo CI step')
def test_real_linux_runner_bootstrap_and_loader():
    import ast
    import subprocess
    import tempfile
    import shutil
    m = load('trusted_retained_testflight')
    # Reuse the exact production workflow function; only its final fixed /opt
    # invocation is excluded so the test never changes the CI host's /opt.
    tree = ast.parse(hardening_code())
    tree.body = [item for item in tree.body if isinstance(item, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    namespace = {}
    exec(compile(tree, '<actual-retained-workflow-bootstrap>', 'exec'), namespace)
    harden = namespace['harden']
    with tempfile.TemporaryDirectory(prefix='retained-runner-smoke-', dir='/root') as directory:
        root = Path(directory)
        opt = root / 'opt'
        opt.mkdir(mode=0o777)
        opt.chmod(0o777)
        source = opt / 'reva-release' / 'source'
        (source / 'scripts').mkdir(parents=True)
        for filename in ('built_unuploaded_proof.py', 'trusted_release_gate.py'):
            shutil.copyfile(Path(__file__).with_name(filename), source / 'scripts' / filename)
        env = {**m.ENV, 'GIT_AUTHOR_NAME': 'release-test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
               'GIT_COMMITTER_NAME': 'release-test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
        def git(*args):
            return subprocess.run(['/usr/bin/git', '-C', str(source), *args], env=env,
                                  capture_output=True, check=True).stdout
        git('init', '-b', 'main')
        git('add', 'scripts/built_unuploaded_proof.py', 'scripts/trusted_release_gate.py')
        git('commit', '-m', 'test canonical helpers')
        sha = git('rev-parse', 'HEAD').decode().strip()
        with pytest.raises(ValueError, match='CONTRACT_METADATA'):
            m.validate_runner_source(source, sha)
        harden(opt)
        assert opt.stat().st_mode & 0o777 == 0o755
        assert m.validate_runner_source(source, sha) is not None
        cache = source / 'scripts' / '__pycache__'
        cache.symlink_to(root / 'missing')
        with pytest.raises(ValueError, match='CONTRACT_CANONICAL'):
            m.validate_runner_source(source, sha)
        cache.unlink()
        helper = source / 'scripts' / 'built_unuploaded_proof.py'
        helper.write_text(helper.read_text() + '\n# drift\n')
        with pytest.raises(ValueError):
            m.validate_runner_source(source, sha)
        for mode in (0o700, 0o775):
            opt.chmod(mode)
            with pytest.raises(ValueError):
                harden(opt)
            assert opt.stat().st_mode & 0o777 == mode
        opt.chmod(0o755)
        os.chown(opt, 12345, 0)
        with pytest.raises(ValueError):
            harden(opt)
        os.chown(opt, 0, 0)
        alias = root / 'opt-alias'
        alias.symlink_to(opt, target_is_directory=True)
        with pytest.raises(ValueError):
            harden(alias)


def test_startup_errors_are_static_without_exception_details(monkeypatch, capsys):
    m = load('trusted_retained_testflight')
    monkeypatch.setattr(m, 'load', lambda *a: (_ for _ in ()).throw(OSError('SECRET_SENTINEL /private/arbitrary')))
    with pytest.raises(m.StartupError) as error:
        m.validate_runner_source(Path('/opt/reva-release/source'), SHA)
    assert error.value.code == 'CONTRACT_FILESYSTEM'
    assert 'SECRET_SENTINEL' not in str(error.value)


@pytest.mark.parametrize('reason', ['isolated', 'no_site', 'dont_write_bytecode', 'uid', 'sha', 'path', 'forged'])
def test_actual_cli_startup_reports_only_allowlisted_phase(monkeypatch, capsys, reason):
    m = load('trusted_retained_testflight')
    flags = {'isolated': 1, 'no_site': 1, 'dont_write_bytecode': 1}
    if reason in flags:
        flags[reason] = 0
    monkeypatch.setattr(m.sys, 'flags', SimpleNamespace(**flags))
    monkeypatch.setattr(m.os, 'geteuid', lambda: 12345 if reason == 'uid' else 0)
    monkeypatch.setattr(m.sys, 'argv', ['retained.py', '--check-runner', '--sha',
                                      'SECRET_SENTINEL' if reason == 'sha' else SHA])
    if reason == 'forged':
        error = m.StartupError('ENTRY')
        error.code = 'SECRET_SENTINEL /arbitrary-path'
        monkeypatch.setattr(m, 'runner_source', lambda _: (_ for _ in ()).throw(error))
    assert m.main() == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'SECRET_SENTINEL' not in output.err
    expected = 'RUNNER_PATH' if reason == 'path' else 'ENTRY'
    assert output.err == 'Retained runner startup blocked: ' + expected + '.\n'


def test_fidelity_reuses_actual_steps_omitting_only_release_admission():
    import yaml
    w = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    steps = w['jobs']['retained-testflight']['steps']
    materialize = fidelity_command('materialize')
    assert 'test "$GITHUB_REF" = refs/heads/main' not in materialize
    assert 'trusted_release_gate.py --sha' not in materialize
    assert 'test "$TARGET_SHA" = "$GITHUB_SHA"' in materialize
    assert 'GITHUB_REPOSITORY' in materialize
    assert "harden(Path('/opt'))" in materialize
    assert fidelity_command('tools') == steps[2]['run']
    assert fidelity_command('smoke') == steps[3]['run']
    assert 'secrets.' not in ''.join(fidelity_command(p) for p in ('materialize', 'tools', 'smoke'))
    with pytest.raises(ValueError):
        fidelity_command('upload')


def test_fidelity_ci_uses_pinned_node_and_all_three_real_phases():
    import yaml
    ci = yaml.safe_load(Path('.github/workflows/ci.yml').read_text())
    release = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    assert ci['jobs']['release-invariants']['runs-on'] == release['jobs']['retained-testflight']['runs-on']
    steps = ci['jobs']['release-invariants']['steps']
    phases = [step for step in steps if '--fidelity-phase' in step.get('run', '')]
    assert len(phases) == 3
    assert [phase['run'].split('--fidelity-phase ')[1].strip() for phase in phases] == ['materialize', 'tools', 'smoke']
    index = steps.index(phases[0])
    assert steps[index + 1]['uses'] == 'actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444'
    assert steps[index + 1]['with'] == {'node-version': '22.13.0', 'package-manager-cache': False}


def fidelity_command(phase):
    """CI test adapter only; no production flags or alternate runtime checks.

CI is allowed to validate a diagnostic branch before merge. Omit exactly the
main-entry assertion and circular fresh-CI attestation in this TEST adapter;
retain canonical URL, real branch SHA, clean source, root and loader checks.
"""
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/trusted-release.yml').read_text())
    steps = workflow['jobs']['retained-testflight']['steps']
    names = {'materialize': 'Materialize exact publisher and fixed retained source before credentials',
             'tools': 'Install and verify locked vendor tools without credentials',
             'smoke': 'Verify canonical retained runner startup without credentials'}
    if phase not in names:
        raise ValueError('only credential-free startup phases are allowed')
    selected = [step for step in steps if step.get('name') == names[phase]]
    if len(selected) != 1 or 'secrets.' in str(selected[0]):
        raise ValueError('ambiguous or credential-bearing startup phase')
    body = selected[0]['run']
    if phase == 'materialize':
        omissions = ['test "$GITHUB_REF" = refs/heads/main',
                     '/usr/bin/python3 -I scripts/trusted_release_gate.py --sha "$1" --workflow-sha "$1"']
        for omitted in omissions:
            lines = body.splitlines()
            if sum(line.strip() == omitted for line in lines) != 1:
                raise ValueError('production admission changed; update the test adapter explicitly')
            body = '\n'.join(line for line in lines if line.strip() != omitted) + '\n'
    return body


def run_fidelity_phase(phase):
    import subprocess
    import re
    if sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('credential-free fidelity runs only on ephemeral Linux CI')
    sha, ref = os.environ.get('GITHUB_SHA', ''), os.environ.get('GITHUB_REF', '')
    if re.fullmatch(r'[0-9a-f]{40}', sha) is None or not ref.startswith(('refs/heads/', 'refs/pull/')):
        raise ValueError('actual CI revision and ref required')
    # No credentials or caller proxy/Git/CA settings reach the fresh startup.
    env = {'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'],
           'GITHUB_REPOSITORY': 'itsoso/health-llm-driven', 'GITHUB_SHA': sha,
           'GITHUB_REF': ref, 'TARGET_SHA': sha}
    print('Credential-free retained startup fidelity: ' + phase +
          '; CI-only main-entry and fresh-CI admission omitted, runtime checks unchanged.', flush=True)
    subprocess.run(['/bin/bash', '--noprofile', '--norc', '-euo', 'pipefail', '-c', fidelity_command(phase)],
                   env=env, check=True, timeout=600)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--fidelity-phase', choices=('materialize', 'tools', 'smoke'), required=True)
    run_fidelity_phase(parser.parse_args().fidelity_phase)
