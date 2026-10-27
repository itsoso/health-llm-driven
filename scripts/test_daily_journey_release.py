"""Bounded additive release admission: no production access or backup fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'scripts/daily_journey_release.py'


def module():
    spec = importlib.util.spec_from_file_location('daily_journey_release_test', ENTRY)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def source(tmp_path):
    m = module()
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Release test')
    git(tmp_path, 'config', 'user.email', 'release@example.invalid')
    init = tmp_path / m.INIT
    init.parent.mkdir(parents=True)
    init.write_bytes(b'# existing models\n' + m.ANCHOR)
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'old')
    old = git(tmp_path, 'rev-parse', 'HEAD')
    for path in m.PINNED:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    init.write_bytes(init.read_bytes().replace(m.ANCHOR, m.ANCHOR + m.IMPORT))
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'candidate')
    return m, tmp_path, old, git(tmp_path, 'rev-parse', 'HEAD')


def test_exact_additive_source_is_admitted(source):
    m, root, old, new = source
    assert m.source_admission(root, old, new) is True
    assert m.source_admission(root, new, new) is False


@pytest.mark.parametrize('kind', ['migration', 'model', 'registration', 'dropin', 'different_sql'])
def test_other_source_changes_are_rejected(source, kind):
    m, root, old, _ = source
    names = {
        'migration': 'backend/migrations/managed/20990101_other.sql',
        'model': 'backend/app/models/another.py',
        'registration': m.INIT,
        'dropin': 'infra/systemd/dropins/extra.conf',
        'different_sql': next(p for p in m.PINNED if p.endswith('postgresql.sql')),
    }
    path = root / names[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as stream:
        stream.write(b'\n# unexpected mutation\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'unexpected')
    with pytest.raises(m.ReleaseBlocked):
        m.source_admission(root, old, git(root, 'rev-parse', 'HEAD'))


def test_existing_target_model_is_not_an_additive_exception(source):
    m, root, old, new = source
    # Reversing the approved delta must not become a model rollback exemption.
    with pytest.raises(m.ReleaseBlocked):
        m.source_admission(root, new, old)


@pytest.mark.parametrize('applied', [
    {'old': 'a', 'unknown': 'extra'}, {'old': 'wrong'}, {}, {'old': 'a', '20261018_120000_daily_journeys': 'wrong'},
])
def test_pending_migrations_or_checksum_drift_block(applied):
    m = module()
    with pytest.raises(m.ReleaseBlocked):
        m.pending_state({'old': 'a', m.MIGRATION: m.SQL_HASH}, applied)


def test_only_exact_pending_or_committed_migration_allowed():
    m = module()
    expected = {'old': 'a', m.MIGRATION: m.SQL_HASH}
    assert m.pending_state(expected, {'old': 'a'}) == 'PENDING'
    assert m.pending_state(expected, expected) == 'APPLIED'


def test_migration_env_has_one_literal_key_and_never_expands_shell():
    m = module()
    assert m.parse_migration_env(b'MIGRATION_DATABASE_URL="postgresql://m:p@localhost/db"\n') == 'postgresql://m:p@localhost/db'
    for value in [b'MIGRATION_DATABASE_URL=x\nOTHER=x\n', b'MIGRATION_DATABASE_URL=x\nMIGRATION_DATABASE_URL=y\n', b'MIGRATION_DATABASE_URL=$(touch /tmp/invalid)\n', b'export MIGRATION_DATABASE_URL=x\n']:
        with pytest.raises(m.ReleaseBlocked):
            m.parse_migration_env(value)


def test_existing_intent_with_pending_database_never_reexecutes(tmp_path):
    m = module()
    plan = {'old': 'a' * 40, 'candidate': 'b' * 40, 'checksum': m.SQL_HASH}
    m.write_once(tmp_path / 'intent.json', plan)
    with pytest.raises(m.ReleaseBlocked):
        m.reentry_state(tmp_path, plan, 'PENDING')
    assert not (tmp_path / 'completed.json').exists()


def test_unknown_commit_readback_requires_original_intent(tmp_path):
    m = module()
    plan = {'old': 'a' * 40, 'candidate': 'b' * 40, 'checksum': m.SQL_HASH}
    with pytest.raises(m.ReleaseBlocked):
        m.reentry_state(tmp_path, plan, 'APPLIED')
    m.write_once(tmp_path / 'intent.json', plan)
    assert m.reentry_state(tmp_path, plan, 'APPLIED') == 'READBACK'
    with pytest.raises(m.ReleaseBlocked):
        m.reentry_state(tmp_path, {**plan, 'old': 'c' * 40}, 'APPLIED')


def test_write_once_never_replaces_intent_or_follows_link(tmp_path):
    m = module()
    path = tmp_path / 'intent.json'
    m.write_once(path, {'binding': 'original'})
    with pytest.raises(FileExistsError):
        m.write_once(path, {'binding': 'replacement'})
    assert json.loads(path.read_text()) == {'binding': 'original'}
    link = tmp_path / 'link.json'
    link.symlink_to(path)
    with pytest.raises(OSError):
        m.write_once(link, {'binding': 'replacement'})


def test_deploy_integration_preflight_before_stop_apply_before_candidate_schema():
    body = (ROOT / 'deploy.sh').read_text().split('deploy_backend() {', 1)[1].split('render_backend_env_file() {', 1)[0]
    assert body.index('daily_journey_release_preflight') < body.index('停止后端 socket')
    assert body.index('$daily_journey_apply') < body.index('启动服务前验证完整 runtime schema')
    assert 'unset MIGRATION_DATABASE_URL' in body


def test_cli_sanitizes_database_exception(monkeypatch, capsys):
    m = module()
    monkeypatch.setattr(m.sys, 'argv', [str(ENTRY), 'preflight', 'a' * 40, 'b' * 40])
    def fail(*args):
        raise RuntimeError('postgresql://sensitive:password@private/database')
    monkeypatch.setattr(m, 'remote_run', fail)
    assert m.main() == 70
    captured = capsys.readouterr()
    assert 'sensitive' not in captured.err and 'password' not in captured.err
    assert 'RELEASE_BLOCKED' in captured.err


def test_preflight_unknown_outcome_preserves_lease(tmp_path):
    script = ROOT / 'deploy.sh'
    env = tmp_path / 'candidate.env'
    env.write_text('DEPLOY_SERVER=fake\nDEPLOY_PATH=/opt/health-app\n')
    import os
    result = subprocess.run(['bash', '-c', f'''source "{script}"
DAILY_JOURNEY_ADDITIVE=1
daily_journey_release_command() {{ echo readonly-placeholder; }}
ssh() {{ return 255; }}
if daily_journey_release_preflight; then exit 99; fi
test "$_REMOTE_RELEASE_LOCK_ABANDONED" = 1
'''], env={**os.environ, 'DEPLOY_ENV_FILE': str(env)}, capture_output=True, text=True)
    assert result.returncode == 0


def test_remote_loader_verifies_code_and_does_not_forward_credentials():
    source = (ROOT / 'deploy.sh').read_text()
    loader = source.split('daily_journey_release_command() {', 1)[1].split('daily_journey_release_preflight() {', 1)[0]
    assert "git('rev-parse',sha+':scripts/'+profile)" in loader
    assert "if profile not in ('daily_journey_release.py', 'exam_attempts_release.py')" in loader
    assert "os.execve(executable" in loader
    assert 'MIGRATION_DATABASE_URL' not in loader
    assert 'migration.env' not in loader


def test_unexpected_failure_exposes_only_bounded_diagnostic(monkeypatch, capsys):
    m = module()
    monkeypatch.setattr(m.sys, 'argv', [str(ENTRY), 'preflight', 'a' * 40, 'b' * 40])
    def fail(*args):
        raise ValueError('postgresql://private:secret@internal/health')
    monkeypatch.setattr(m, 'remote_run', fail)
    assert m.main() == 70
    error = capsys.readouterr().err
    diagnostic = json.loads(error.split('DAILY_JOURNEY_DIAGNOSTIC: ', 1)[1].splitlines()[0])
    assert set(diagnostic) == {'phase', 'exception', 'helper_line'}
    assert diagnostic['phase'] == 'preflight' and diagnostic['exception'] == 'ValueError'
    assert isinstance(diagnostic['helper_line'], int) and diagnostic['helper_line'] > 0
    assert 'private' not in error and 'secret' not in error and 'internal' not in error


def test_diagnostic_does_not_echo_custom_exception_name():
    m = module()
    secret_type = type('PatientSecret', (Exception,), {})
    assert m.failure_diagnostic(secret_type('password'), 'preflight')['exception'] == 'Exception'


def test_runtime_settings_does_not_inherit_release_helper_future_annotations():
    m = module()
    config = b"from typing import List\nfrom pydantic import BaseModel\nclass Settings(BaseModel):\n    values: List[str] = []\nsettings = Settings()\n"
    settings = m.load_runtime_settings(config, Path('/canonical/config.py'))
    assert settings.values == []


def test_load_actual_runtime_configuration_in_isolated_namespace(tmp_path, monkeypatch):
    m = module()
    path = ROOT / 'backend/app/config.py'
    monkeypatch.chdir(tmp_path)
    settings = m.load_runtime_settings(path.read_bytes(), path)
    assert isinstance(settings.app_env, str)
    assert isinstance(settings.effective_database_url, str)
