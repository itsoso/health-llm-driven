"""Persistent incident evidence blocks ordinary publishers even after reboot."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize('module_name,entry', [
    ('bootstrap_trusted_release', '_assert_known_activity'),
    ('bootstrap_trusted_release', '_assert_idle'),
    ('bootstrap_trusted_release', 'assert_frontend_rebuild_history'),
    ('bootstrap_trusted_release', 'assert_ota_history'),
    ('trusted_release_server', 'assert_frontend_rebuild_history'),
    ('trusted_release_server', 'assert_ota_history'),
])
@pytest.mark.parametrize('attempt', ['exam-a8-forward-acl-v1', 'exam-a8-read-credential-v1'])
@pytest.mark.parametrize('state', ['intent', 'failure', 'completed', 'file', 'dangling_symlink'])
def test_all_incident_states_block_without_volatile_lease(monkeypatch, tmp_path, module_name, entry, attempt, state):
    path = Path(__file__).with_name(module_name + '.py')
    spec = importlib.util.spec_from_file_location(module_name + '_exam_history', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'STATE', tmp_path)
    if module_name == 'bootstrap_trusted_release':
        monkeypatch.setattr(module, 'BUSINESS_LEASE', tmp_path / 'absent-lease')
    record = tmp_path / attempt
    if state == 'file':
        record.write_text('unknown')
    elif state == 'dangling_symlink':
        record.symlink_to(tmp_path / 'absent-target')
    else:
        record.mkdir()
        (record / (state + '.json')).write_text(json.dumps({'state': 'FORWARD_RECOVERED'}))
    error = module.BootstrapError if module_name == 'bootstrap_trusted_release' else module.LaunchError
    with pytest.raises(error, match='exam recovery requires independent closure'):
        getattr(module, entry)(*([{}] if entry == '_assert_known_activity' else []))
    assert not (tmp_path / 'absent-lease').exists()
