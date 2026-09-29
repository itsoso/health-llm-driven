from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_application_units_hide_staking_data_and_bound_resources():
    for name in ("health-backend", "celery-worker", "celery-beat"):
        for path in (ROOT / "infra/systemd" / f"{name}.service",
                     ROOT / "infra/systemd/dropins" / f"{name}-runtime-state.conf"):
            body = path.read_text()
            assert "InaccessiblePaths=-/mnt -/opt/eth-ops" in body
            assert "MemoryMax=" in body
            assert "CPUQuota=" in body
            assert "IPAddressDeny=100.64.0.0/10 169.254.0.0/16" in body
            assert "CapabilityBoundingSet=\n" in body


def load(name):
    import importlib.util
    path = ROOT / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location('tested_' + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_canonical_rule_comparison_preserves_reply_direction_and_chain_order():
    m = load('harden_public_host')
    _, rules, _ = m.firewall_rules('health-app', 997)
    canonical = m.canonical_rule
    assert canonical(rules[0]) == canonical(('-m','conntrack','--ctstate','RELATED,ESTABLISHED','--ctdir','REPLY','-j','RETURN'))
    assert canonical(rules[0]) != canonical(('-m','conntrack','--ctstate','RELATED,ESTABLISHED','--ctdir','ORIGINAL','-j','RETURN'))
    assert canonical(rules[2]) == canonical(('-p','udp','-m','addrtype','--dst-type','LOCAL','-m','udp','--dport','53','-j','RETURN'))


def test_backup_reads_every_file_and_records_absence(tmp_path, monkeypatch):
    import hashlib
    import json
    m = load('harden_public_host')
    monkeypatch.setattr(m, 'trusted', lambda *args, **kwargs: None)
    source = tmp_path / 'old.service'
    source.write_text('synthetic previous configuration')
    missing = tmp_path / 'absent.service'
    receipt = tmp_path / 'receipt'
    receipt.mkdir()
    m.backup_configuration(receipt, [source, missing])
    manifest = json.loads((receipt / 'config-manifest.json').read_text())
    assert manifest[0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest[1] == {'path': str(missing), 'exists': False}
    assert (receipt / 'config-before.tar.gz').stat().st_mode & 0o777 == 0o600


def test_host_operator_rejects_noncanonical_entry_before_loading_code():
    import pytest
    m = load('trusted_public_host')
    with pytest.raises(RuntimeError, match='canonical operator staging'):
        m.load_reviewed('a' * 40)


def test_hardening_requires_exact_backend_success():
    import pytest
    m = load('trusted_public_host')
    m.require_backend_receipt('a' * 40, {'sha': 'a' * 40, 'state': 'SUCCEEDED'})
    for receipt in ({'sha': 'b' * 40, 'state': 'SUCCEEDED'}, {'sha': 'a' * 40, 'state': 'STARTED'}, {}):
        with pytest.raises(RuntimeError):
            m.require_backend_receipt('a' * 40, receipt)


def test_host_entry_precedes_any_environment_or_shell_helper():
    body = (ROOT / 'deploy.sh').read_text()
    assert body.index('--security-hardening') < body.index('ENV_FILE=') < body.index('source "$SCRIPT_DIR/scripts/release_lock.sh"')
    assert '/usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_public_host.py"' in body


def test_frontend_unknown_state_cannot_choose_legacy_root_branch(tmp_path):
    import subprocess
    body = (ROOT / 'deploy.sh').read_text()
    start = body.index('frontend_runtime_kind() {')
    end = body.index('# 推送代码到 GitHub', start)
    functions = body[start:end]
    for response, status, expected in [('hardened',0,'systemctl restart'),('legacy',0,'pm2 restart'),('',255,None),('garbage',0,None)]:
        script = functions + '''
print_step() { :; }
print_error() { :; }
print_success() { :; }
assert_remote_release_lock_if_acquired() { :; }
SERVER=fixture
frontend_runtime_kind() { printf '%s' "$RESPONSE"; return "$STATUS"; }
ssh() { printf '%s\\n' "$*" >> "$RECORD"; }
restart_frontend_service
'''
        record = tmp_path / ('record' + str(status) + response)
        result = subprocess.run(['bash','-c',script], env={'PATH':'/usr/bin:/bin','RESPONSE':response,'STATUS':str(status),'RECORD':str(record)}, capture_output=True)
        if expected:
            assert result.returncode == 0
            assert expected in record.read_text()
        else:
            assert result.returncode != 0
            assert not record.exists()


def test_release_candidate_cannot_reenable_public_registration():
    m = load('trusted_release_server')
    result = m.invitation_only_config('AUTH_PHONE_SELF_REGISTRATION_ENABLED=true\n export REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=false\nUNCHANGED=value\n')
    assert result.count('AUTH_PHONE_SELF_REGISTRATION_ENABLED=') == 1
    assert 'AUTH_PHONE_SELF_REGISTRATION_ENABLED=false\n' in result
    assert 'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=true\n' in result
    assert 'UNCHANGED=value\n' in result


def test_cached_helper_is_rejected_before_top_level_execution(tmp_path, monkeypatch):
    import pytest
    m = load('trusted_public_host')
    monkeypatch.setattr(m, 'secure', lambda path: None)
    path = tmp_path / 'helper.py'
    path.write_text('raise AssertionError("must not execute")')
    (tmp_path / '__pycache__').mkdir()
    with pytest.raises(RuntimeError, match='cached code forbidden'):
        m.module(path, 'dangerous_cached_helper')


def test_completed_host_audit_is_retireable_but_unknown_attempt_is_not(tmp_path, monkeypatch):
    import json
    import pytest
    m = load('bootstrap_trusted_release')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(m, 'secure', lambda *args, **kwargs: None)
    sha = 'a' * 40
    root = tmp_path / sha / 'host-hardening'
    root.mkdir(parents=True, mode=0o700)
    records = {'frontend.json': {'operation_id': 'b' * 32, 'frontend_tree': 'c' * 40, 'artifact_digest': 'd' * 64}, 'started.json': {'sha': sha, 'state': 'STARTED'},
               'verified.json': {'sha': sha, 'state': 'LOCAL_VERIFIED'},
               'completed.json': {'sha': sha, 'state': 'LOCAL_VERIFIED', 'external_readback_required': True}}
    for name, value in records.items():
        (root / name).write_text(json.dumps(value))
    assert set(m._host_hardening_evidence(sha)) == set(records) | {"."}
    (root / 'completed.json').unlink()
    with pytest.raises(m.BootstrapError):
        m._host_hardening_evidence(sha)
    (root / 'completed.json').write_text(json.dumps(records['completed.json']))
    (root / 'failed.json').write_text('{}')
    with pytest.raises(m.BootstrapError):
        m._host_hardening_evidence(sha)


def test_final_frontend_receipt_requires_live_digest_and_unique_attempt(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    import pytest
    m = load('trusted_public_host')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    sha = 'a' * 40
    tree = 'b' * 40
    op = 'c' * 32
    operation = tmp_path / 'frontend-rebuilds' / op
    operation.mkdir(parents=True)
    frontend = load('trusted_frontend_rebuild')
    frontend.PRODUCTION = tmp_path / 'production'
    monkeypatch.setattr(frontend, 'git', lambda *args: tree)
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'd' * 64)
    monkeypatch.setattr(m, 'module', lambda *args: frontend)
    digest = hashlib.sha256(('d' * 128).encode()).hexdigest()
    receipts = {name: frontend.receipt(sha, sha, op, tree, state, digest) for name, state in (
        ('completed.json','FRONTEND_SUCCEEDED'),('verified.json','FRONTEND_VERIFIED'),('install-started.json','FRONTEND_INSTALLING'))}
    bootstrap = SimpleNamespace(_read_json=lambda path: receipts[path.name])
    checked = []
    server = SimpleNamespace(secure_path=lambda *args, **kwargs: None,
                             assert_frontend_rebuild_history=lambda *args: checked.append(True))
    assert m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)['artifact_digest'] == digest
    assert checked
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'e' * 64)
    with pytest.raises(RuntimeError, match='artifacts differ'):
        m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'd' * 64)
    (operation.parent / ('f' * 32)).mkdir()
    with pytest.raises(RuntimeError, match='exactly one'):
        m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)
