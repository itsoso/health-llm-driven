"""Synthetic operator tests never execute root/production commands."""
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest


def module():
    spec = importlib.util.spec_from_file_location('rollback_operator_test', Path(__file__).with_name('rolled_back_release_operator.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


OLD, FAILED = 'a' * 40, 'b' * 40


def terminal():
    transaction = hashlib.sha256(f'{OLD}:{FAILED}'.encode()).hexdigest()[:32]
    return dict(version=1, old_sha=OLD, candidate_sha=FAILED, terminal_sha=OLD,
                target='old', phase='RESTORE_FINALIZED', result='RESTORE_FINALIZED',
                transaction_id=transaction, reap_name='runtime-state-transaction.reap-' + transaction)


def log():
    return ('stage=/tmp/health-app-backup-preflight-123-123456\n'
            '已备份到工作树外并封存 release rollback env: /var/backups/health-app/env/.env.20261010_180000\n'
            f'ROLLBACK_OK commit={OLD} kb_quarantine=passed schema_probe=passed auth_probe=passed services=active process_flag=false runtime_state=restored\n')


@pytest.mark.parametrize('field,bad', [('version', True), ('version', 2), ('old_sha', FAILED),
    ('candidate_sha', OLD), ('terminal_sha', FAILED), ('target', 'candidate'),
    ('phase', 'COMMITTED'), ('result', 'finalized'), ('transaction_id', '0' * 32),
    ('reap_name', 'other'), ('extra', True)])
def test_old_terminal_closed_binding(field, bad):
    m = module()
    value = terminal()
    value[field] = bad
    with pytest.raises(m.RetirementError):
        m.validate_terminal(value, OLD, FAILED)


def test_real_old_marker_shape_and_stage_are_supported():
    m = module()
    m.validate_terminal(terminal(), OLD, FAILED)
    assert m.original_log(log(), OLD) == (Path('/var/backups/health-app/env/.env.20261010_180000'), Path('/tmp/health-app-backup-preflight-123-123456'))


@pytest.mark.parametrize('change', ['no_stage', 'two_stage', 'bad_path', 'missing_backup', 'duplicate_backup', 'no_rollback', 'two_rollback', 'candidate', 'wrong_sha', 'suffix'])
def test_original_log_binding_never_accepts_ambiguity(change):
    m = module()
    value = log()
    if change == 'no_stage': value = value.split('\n', 1)[1]
    if change == 'two_stage': value += 'stage=/tmp/health-app-backup-preflight-999-888\n'
    if change == 'missing_backup': value = '\n'.join(line for line in value.splitlines() if '并封存' not in line)
    if change == 'duplicate_backup': value += value.splitlines()[1] + '\n'
    if change == 'bad_path': value = value.replace('/tmp/health-app-backup-preflight-123-123456', '/tmp/../unsafe')
    if change == 'no_rollback': value = '\n'.join(value.splitlines()[:2])
    if change == 'two_rollback': value += value.splitlines()[2] + '\n'
    if change == 'candidate': value = value.replace('runtime_state=restored', 'runtime_state=candidate-retained')
    if change == 'wrong_sha': value = value.replace(OLD, FAILED)
    if change == 'suffix': value = value.rstrip() + ' ignored\n'
    with pytest.raises(m.RetirementError):
        m.original_log(value, OLD)


@pytest.mark.parametrize('raw', [b'', b'HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n',
    b' export HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n',
    b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n',
    b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\x00\n', b'KEY=value'])
def test_environment_normalization_rejects_drift(raw):
    m = module()
    with pytest.raises(m.RetirementError):
        m.normalize_rollback_env(raw)


def test_original_awk_preimage_normalization():
    m = module()
    assert m.normalize_rollback_env(b'SYNTHETIC=true\n') == b'SYNTHETIC=true\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'
    valid = b'SYNTHETIC=true\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n'
    assert m.normalize_rollback_env(valid) == valid


class FakeAdapter:
    def __init__(self, m, path):
        self.m = m
        self.r = m.load(Path(__file__).with_name('retained_candidate_retirement.py'), 'rollback_test_helpers')
        self.record = path / 'closures' / FAILED
        self.evidence = {'old_sha': FAILED, 'production_sha': OLD, 'closing_sha': 'c' * 40, 'terminal': terminal()}
        self.calls = 0
        self.revoked = False
        self.drift = False
        self.fail_archive = False
        self.fail_revoke = False

    def check_record_parent(self):
        pass

    def inspect(self):
        self.calls += 1
        value = copy.deepcopy(self.evidence)
        if self.drift and self.calls > 1:
            value['production_sha'] = 'd' * 40
        return value

    def archive_preimage(self, evidence):
        if self.fail_archive:
            raise self.m.RetirementError('static failure')

    def retire_authorization(self, evidence):
        self.revoked = True
        if self.fail_revoke:
            raise self.m.RetirementError('static failure')


def test_transaction_is_inspect_exact_digest_then_one_shot(tmp_path):
    import json
    m = module()
    a = FakeAdapter(m, tmp_path)
    result = m.close_transaction(a)
    assert result['state'] == 'INSPECTED_ROLLED_BACK_RELEASE'
    assert not a.record.exists() and not a.revoked
    closed = m.close_transaction(a, result['evidence_sha256'])
    assert closed['state'] == 'CLOSED_ROLLED_BACK_RELEASE'
    intent = json.loads((a.record / 'intent.json').read_text())
    completed = json.loads((a.record / 'completed.json').read_text())
    assert completed['intent_sha256'] == m.digest(intent)
    assert hashlib.sha256(closed['receipt'].encode()).hexdigest() == intent['receipt_sha256']
    assert closed['receipt'] not in (a.record / 'intent.json').read_text()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, result['evidence_sha256'])


@pytest.mark.parametrize('mode', ['drift', 'fail_archive', 'fail_revoke'])
def test_post_intent_failure_preserves_audit_and_forbids_retry(tmp_path, mode):
    m = module()
    a = FakeAdapter(m, tmp_path)
    setattr(a, mode, True)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, m.digest(a.evidence))
    assert (a.record / 'intent.json').exists()
    assert not (a.record / 'completed.json').exists()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, m.digest(a.evidence))


def test_stale_digest_never_revokes_or_consumes(tmp_path):
    m = module()
    a = FakeAdapter(m, tmp_path)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, '0' * 64)
    assert not a.record.exists() and a.revoked is False


def test_cli_diagnostics_do_not_echo_arguments_or_exception(monkeypatch, capsys):
    m = module()
    monkeypatch.setattr(m.sys, 'argv', ['operator', '--unknown-secret', 'sensitive-value'])
    assert m.cli() == 1
    output = capsys.readouterr()
    assert 'sensitive-value' not in output.err
    assert 'unknown-secret' not in output.err
    assert 'CLOSURE_BLOCKED' in output.err
    assert output.out == ''


def test_protected_receipt_rejects_nonfile_before_context(monkeypatch):
    from types import SimpleNamespace
    m = module()
    monkeypatch.setattr(m.os, 'fstat', lambda _: SimpleNamespace(st_mode=0o010600))
    with pytest.raises(m.RetirementError):
        m.protected_receipt_output('c' * 40)


def test_no_deploy_or_runtime_mutation_commands_in_operator():
    text = Path(__file__).with_name('rolled_back_release_operator.py').read_text()
    for mutation in ("systemctl', 'restart", 'resume_runtime', 'acknowledge_generation',
                     "['deploy.sh'", "['rollback_release.sh'", 'UPDATE agent_runtime'):
        assert mutation not in text


def test_bootstrap_closure_branch_delegates_only_to_closed_proof(tmp_path, monkeypatch):
    import types
    m = module()
    b = m.load(Path(__file__).with_name('bootstrap_trusted_release.py'), 'rollback_bootstrap_test')
    b.STATE = tmp_path
    (tmp_path / 'rolled-back-release-closures' / FAILED).mkdir(parents=True)
    monkeypatch.setattr(b, 'secure', lambda *a, **k: None)
    real_exists = b.os.path.lexists
    monkeypatch.setattr(b.os.path, 'lexists', lambda p: False if Path(p).name == '__pycache__' else real_exists(p))
    calls = []
    def proof(*args, **kwargs):
        calls.append((args, kwargs))
        return {'state': 'CLOSED_ROLLED_BACK_RELEASE'}
    fake = types.SimpleNamespace(closed_evidence=proof)
    monkeypatch.setattr(b.importlib.util, 'spec_from_file_location', lambda *a: types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m: None)))
    monkeypatch.setattr(b.importlib.util, 'module_from_spec', lambda spec: fake)
    assert b._workspace_evidence(FAILED, recovery_receipt='receipt', historical=True)['state'] == 'CLOSED_ROLLED_BACK_RELEASE'
    assert calls[0][0][1:] == (FAILED, 'receipt')
    assert calls[0][1] == {'historical': True}
    (tmp_path / 'retained-candidate-closures' / FAILED).mkdir(parents=True)
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(FAILED, recovery_receipt='receipt')
    assert len(calls) == 1


@pytest.mark.parametrize('bad', [True, 'g' * 40, OLD])
def test_ambiguous_revision_bindings_are_rejected(bad):
    m = module()
    with pytest.raises(m.RetirementError):
        m.validate_terminal(terminal(), bad, FAILED if bad != OLD else OLD)


# Reuse the existing isolated, opt-in PostgreSQL schema fixture. It never points
# at production and requires an explicit URL containing a test database name.
_fixture_spec = importlib.util.spec_from_file_location('rollback_pg_fixture_module', Path(__file__).with_name('test_retained_candidate_retirement.py'))
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
retained_pg = _fixture_module.retained_pg


@pytest.mark.parametrize('wrong_actor', [False, True])
def test_old_target_quarantine_postgres_preserves_documents_and_runtime(retained_pg, wrong_actor):
    from app.models.system_knowledge import KBAudit, KBDocument
    from app.models.agent_runtime import AgentRun, AgentRuntimeRolloutState
    from app.models.user import User
    from datetime import date
    from sqlalchemy import text
    m = module()
    r = m.load(Path(__file__).with_name('retained_candidate_retirement.py'), 'rollback_pg_helpers')
    db, probe, manifest, before, after = retained_pg
    audit = db.query(KBAudit).filter_by(op='rollback_kb_quarantine').one()
    audit.actor = 'rollback:' + (FAILED if wrong_actor else OLD)[:12]
    user = User(username='rollback-synthetic', email='rollback@example.invalid',
                hashed_password='synthetic-not-a-password', name='Synthetic',
                birth_date=date(1990, 1, 1), gender='男', is_active=True, is_approved=True)
    db.add(user)
    db.flush()
    runtime = AgentRuntimeRolloutState(id=1, version=1, status='paused',
        reason_code='reconciliation_detected', reconciliation_generation=8,
        reconciliation_acknowledged_generation=7)
    run = AgentRun(run_id='rollback-synthetic-unknown', user_id=user.id,
        current_attempt_id='rollback-synthetic-attempt', status='reconciliation_required', origin='test')
    db.add_all([runtime, run])
    db.commit()
    before_documents = [(d.doc_id, d.is_archived) for d in db.query(KBDocument).order_by(KBDocument.doc_id)]
    db.rollback()
    if wrong_actor:
        with pytest.raises(r.RetirementError, match='rollback audit ambiguous'):
            r.quarantined_kb_probe(db, probe, manifest, OLD, before, after, runtime_enabled=False)
    else:
        result = r.quarantined_kb_probe(db, probe, manifest, OLD, before, after, runtime_enabled=False)
        r.validate_quarantine_evidence(result, OLD)
        assert result['candidate_sha'] == OLD
        assert result['generic_eligible_documents'] == result['runtime_eligible_claims'] == 0
    db.refresh(runtime)
    db.refresh(run)
    assert (runtime.status, runtime.reconciliation_generation,
            runtime.reconciliation_acknowledged_generation, run.status) == ('paused', 8, 7, 'reconciliation_required')
    assert [(d.doc_id, d.is_archived) for d in db.query(KBDocument).order_by(KBDocument.doc_id)] == before_documents
    db.rollback()
    assert db.execute(text("SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'")).scalar() == 0
    db.rollback()
