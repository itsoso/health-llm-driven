"""Additive viewer policies must preserve the already authorized viewers."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('viewer_extension', Path(__file__).with_name('edu_viewer_activation.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_additive_policy_preserves_existing_and_unrelated_configuration():
    m.configure(7, 9, '8')
    before = b'OTHER=keep\nEDU_SSO_VIEWER_IDS=8\n'
    assert m.patch_env(before) == b'OTHER=keep\nEDU_SSO_VIEWER_IDS=8,9\n'
    assert m.patch_env(m.patch_env(before)) == m.patch_env(before)
    assert m.OLD == {m.KEY: '8'}
    assert m.NEW == {m.KEY: '8,9'}


@pytest.mark.parametrize('existing', ['8,8', '7', '9', '08', '8,', ' 8', '8\nOTHER=1'])
def test_rejects_ambiguous_or_overlapping_existing_policy(existing):
    with pytest.raises(m.ActivationError):
        m.configure(7, 9, existing)


def test_missing_or_different_existing_policy_cannot_be_overwritten():
    m.configure(7, 9, '8')
    for raw in [b'OTHER=keep\n', b'EDU_SSO_VIEWER_IDS=10\n']:
        with pytest.raises(m.ActivationError):
            m.patch_env(raw)


def test_initial_policy_still_uses_original_contract():
    m.configure(7, 8)
    assert m.OLD == {}
    assert m.patch_env(b'OTHER=keep\n') == b'OTHER=keep\nEDU_SSO_VIEWER_IDS=8\n'


@pytest.fixture
def extension_runtime(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('viewer_test_helpers', Path(__file__).with_name('test_edu_viewer_activation.py'))
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    monkeypatch.setattr(helpers, 'm', m)
    original_env = helpers.old_env
    monkeypatch.setattr(helpers, 'old_env', lambda: original_env() + b'EDU_SSO_VIEWER_IDS=8\n')
    m.configure(7, 9, '8')
    values = helpers.fake_runtime(tmp_path, monkeypatch)
    args = values[0]
    args.viewer_id = 9
    args.existing_viewer_ids = '8'
    original_root = values[2]
    original_root.mkdir()
    (original_root / 'journal.json').write_text('original completed operation must remain unchanged')
    return values


def test_extension_uses_separate_journal_and_preserves_completed_initial_operation(extension_runtime):
    import json
    args, env, root, lease, calls, *_ = extension_runtime
    assert m.execute(args)['state'] == 'READY'
    assert not (root.parent / 'reva-edu-viewer-add-9').exists()
    args.apply = True
    result = m.execute(args)
    assert result['policy'] == 'edu-viewer-add-v2'
    assert result['existing_viewer_ids'] == '8'
    assert m.selected(env.read_bytes()) == {m.KEY: '8,9'}
    assert (root / 'journal.json').read_text() == 'original completed operation must remain unchanged'
    journal = json.loads((root.parent / 'reva-edu-viewer-add-9/journal.json').read_text())
    assert journal['state'] == 'CONFIGURATION_SUCCEEDED'
    assert not lease.exists()
    assert m.execute(args)['state'] == 'CONFIGURATION_SUCCEEDED'
    assert calls.count('health-backend') == 1


def test_extension_restart_interruption_resumes_only_same_binding(extension_runtime):
    args, env, root, lease, calls, io, *_ = extension_runtime
    original_run = io.run
    def interrupted(*values):
        if values[-1] == 'celery-worker':
            raise RuntimeError('synthetic interruption')
        return original_run(*values)
    io.run = interrupted
    args.apply = True
    with pytest.raises(RuntimeError):
        m.execute(args)
    assert lease.exists()
    args.existing_viewer_ids = '10'
    args.resume = True
    with pytest.raises(m.ActivationError):
        m.execute(args)
    args.existing_viewer_ids = '8'
    io.run = original_run
    assert m.execute(args)['state'] == 'CONFIGURATION_SUCCEEDED'
    assert calls.count('health-backend') == 1


def test_extension_does_not_replace_comment_containing_old_assignment():
    m.configure(7, 9, '8')
    raw = b'# previous EDU_SSO_VIEWER_IDS=8\nEDU_SSO_VIEWER_IDS=8\n'
    assert m.patch_env(raw) == b'# previous EDU_SSO_VIEWER_IDS=8\nEDU_SSO_VIEWER_IDS=8,9\n'
