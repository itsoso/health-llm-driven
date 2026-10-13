"""No-backup release policy, exercised without network or production state."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'deploy.sh'


def run(tmp_path, body, variables=None):
    env = tmp_path / 'candidate.env'
    env.write_text('DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/fake-repo\n')
    return subprocess.run(['bash', '-c', f'source "{SCRIPT}"\n{body}'],
        env={**os.environ, 'DEPLOY_ENV_FILE': str(env), **(variables or {})},
        capture_output=True, text=True, timeout=5)


def test_legacy_backup_opt_in_cannot_reenable_backup(tmp_path):
    result = run(tmp_path, '''
ssh() { echo unexpected-ssh; return 99; }
stage_backup_preflight_scripts() { echo unexpected-stage; return 99; }
backup_database
''', {'DEPLOY_DATABASE_BACKUP': '1'})
    assert result.returncode != 0
    assert 'unexpected-' not in result.stdout


def test_env_sync_only_proves_live_configuration_without_copy(tmp_path):
    result = run(tmp_path, '''
validate_deploy_env_preflight() { echo verified; }
backup_remote_env() { echo forbidden-backup; return 99; }
upload_backend_env_file() { echo forbidden-upload; return 99; }
seal_release_env_snapshots() { echo forbidden-seal; return 99; }
sync_env
''')
    assert result.returncode == 0, result.stdout
    assert 'verified' in result.stdout
    assert 'forbidden-' not in result.stdout


def test_failure_preserves_lease_and_never_restores(tmp_path):
    result = run(tmp_path, '''
ssh() { echo forbidden-restore; return 99; }
ROLLBACK_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
set +e
rollback_deploy
rc=$?
printf 'state=%s:%s\n' "$rc" "$_REMOTE_RELEASE_LOCK_ABANDONED"
exit "$rc"
''')
    assert result.returncode != 0
    assert 'forbidden-restore' not in result.stdout
    assert 'state=1:1' in result.stdout


@pytest.mark.parametrize('option', ['-e', '-H'])
def test_unsupported_env_mutations_block_before_lock_or_network(tmp_path, option):
    result = run(tmp_path, f'''
acquire_release_lock() {{ echo forbidden-lock; return 99; }}
ssh() {{ echo forbidden-ssh; return 99; }}
main {option}
''')
    assert result.returncode != 0
    assert 'forbidden-' not in result.stdout


def test_code_only_deploy_contract_excludes_backups_and_legacy_mutation():
    script = SCRIPT.read_text()
    start = script.index('deploy_backend() {')
    body = script[start:script.index('render_backend_env_file() {', start)]
    assert 'preflight-code' in body
    assert "prepare-code '$ROLLBACK_CANDIDATE_COMMIT'" in body
    assert 'verify_code_only_source_changes' in body
    assert 'deactivate_health_evidence_runtime_before_mutation' not in body
    sync = script[script.index('remote_git_sync_command() {'):script.index('verify_deployed_revision() {')]
    assert 'git stash' not in sync
    assert 'git status --porcelain' in sync


def test_live_env_does_not_require_synthetic_config_copy(tmp_path):
    env = tmp_path / 'live.env'
    env.write_text('APP_ENV=production\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n')
    result = subprocess.run(['bash', '-c', f'source "{SCRIPT}"\ntest "$SERVER" = fake-server\ntest "$REMOTE_PATH" = /tmp/fake-repo'],
        env={**os.environ, 'DEPLOY_ENV_FILE': str(env), 'DEPLOY_SERVER': 'fake-server',
             'DEPLOY_PATH': '/tmp/fake-repo'}, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert env.read_text() == 'APP_ENV=production\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'


@pytest.mark.parametrize('case', ['valid', 'changed', 'symlink', 'permissions', 'hardlink'])
def test_live_env_hash_metadata_proof_never_creates_backup(tmp_path, case):
    candidate = tmp_path / 'candidate.env'
    live_dir = tmp_path / 'repo/backend'
    live_dir.mkdir(parents=True)
    live = live_dir / '.env'
    raw = 'APP_ENV=production\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'
    candidate.write_text('DEPLOY_SERVER=fake-server\nDEPLOY_PATH=/tmp/ignored\n' + raw)
    live.write_text(raw)
    live.chmod(0o640)
    if case == 'changed':
        live.write_text(raw + '# changed\n')
    elif case == 'symlink':
        live.unlink()
        live.symlink_to(candidate)
    elif case == 'permissions':
        live.chmod(0o666)
    elif case == 'hardlink':
        os.link(live, live_dir / 'unwanted-copy')
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    stat = fake_bin / 'stat'
    stat.write_text('''#!/usr/bin/env python3
import os, sys
info = os.stat(sys.argv[3])
if sys.argv[2] == '%h': print(info.st_nlink)
elif sys.argv[2] == '%U:%G:%a': print(f'root:root:{info.st_mode & 0o7777:o}')
else: raise SystemExit(64)
''')
    stat.chmod(0o700)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob('*'))
    result = subprocess.run(['bash', '-c', f'''
source "{SCRIPT}"
REMOTE_PATH='{tmp_path / 'repo'}'
ssh() {{ shift; "$@"; }}
scp() {{ echo forbidden-copy; return 99; }}
verify_live_env_matches_candidate
'''], env={**os.environ, 'DEPLOY_ENV_FILE': str(candidate),
            'PATH': f'{fake_bin}:{os.environ["PATH"]}'}, capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) is (case == 'valid'), (result.stdout, result.stderr)
    assert 'forbidden-copy' not in result.stdout
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob('*')) == before


@pytest.mark.parametrize('path,allowed', [
    ('backend/app/services/synthetic.py', True),
    ('backend/app/models/synthetic.py', False),
    ('backend/migrations/managed/synthetic.sql', False),
    ('infra/systemd/dropins/synthetic.conf', False),
])
def test_source_scope_blocks_schema_and_runtime_before_mutation(tmp_path, path, allowed):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Synthetic')
    git('config', 'user.email', 'synthetic@example.test')
    (repo / 'seed').write_text('synthetic')
    git('add', 'seed')
    git('commit', '-qm', 'initial')
    old = git('rev-parse', 'HEAD')
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('synthetic change')
    git('add', path)
    git('commit', '-qm', 'candidate')
    candidate = git('rev-parse', 'HEAD')
    result = run(tmp_path, f'''
SCRIPT_DIR='{repo}'
ROLLBACK_CANDIDATE_COMMIT='{old}'
DEPLOY_EXPECTED_SHA='{candidate}'
ssh() {{ echo forbidden-network; return 99; }}
verify_code_only_source_changes
''')
    assert (result.returncode == 0) is allowed, (result.stdout, result.stderr)
    assert 'forbidden-network' not in result.stdout


@pytest.mark.parametrize('case,allowed', [
    ('idle', True), ('pending', False), ('missing-release', False),
    ('head-mismatch', False), ('same-candidate', False),
])
def test_finalized_legacy_marker_is_idle_only_never_new_success(tmp_path, case, allowed):
    old = 'a' * 40
    previous = 'b' * 40
    candidate = previous if case == 'same-candidate' else 'c' * 40
    target = 'candidate'
    action = 'finalize' if case == 'pending' else 'none'
    released = 'false' if case == 'missing-release' else 'true'
    head = old if case == 'head-mismatch' else previous
    result = run(tmp_path, f'''
DEPLOY_EXPECTED_SHA={candidate}
run_runtime_state_transaction() {{
    test "$1" = status || {{ echo forbidden-mutation; return 99; }}
    printf '%s\\n' 'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED old_sha={old} candidate_sha={previous} gate_armed=false gate_released={released} release_target={target} next_action={action} state_source=terminal'
}}
ssh() {{
    case "$*" in *'rev-parse HEAD'*) printf '%s\\n' '{head}';;
    *) echo forbidden-backup-read; return 99;; esac
}}
if inspect_runtime_state_transaction_before_deploy; then
    test "$RUNTIME_STATE_RESUME_PHASE" = NONE
    test "$RUNTIME_STATE_ALREADY_FINALIZED" = 0
    exit 0
fi
exit 1
''')
    assert (result.returncode == 0) is allowed, (result.stdout, result.stderr)
    assert 'forbidden-' not in result.stdout
