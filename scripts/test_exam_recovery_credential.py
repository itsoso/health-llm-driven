"""Offline real-filesystem checks for the fixed exam incident credential refresh."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def module():
    path = Path(__file__).with_name('exam_recovery_credential.py')
    spec = importlib.util.spec_from_file_location('exam_credential_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def incoming():
    return {'repository':'itsoso/health-llm-driven', 'token':'test-token-secret', 'expires_at':1300}


@pytest.mark.parametrize('value', [b'', b'{', b'[]', b'{"token":"secret","token":"secret"}', b'x'*8193])
def test_bounded_input_rejects_invalid_without_secret(value):
    m = module()
    with pytest.raises(m.CredentialError) as error:
        m.read_incoming(io.BytesIO(value), now=1000)
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('change', [{'expires_at':True}, {'expires_at':1000}, {'expires_at':5000}, {'token':'a\nb'}, {'repository':'other/repo'}, {'extra':'x'}])
def test_input_requires_exact_repository_fields_and_short_lifetime(change):
    m = module(); data = {**incoming(), **change}
    with pytest.raises(m.CredentialError):
        m.read_incoming(io.BytesIO(json.dumps(data).encode()), now=1000)


def test_input_is_bounded_and_kept_in_memory():
    m = module()
    assert m.read_incoming(io.BytesIO(json.dumps(incoming()).encode()), now=1000) == incoming()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    m = module(); root = tmp_path / 'secure'; root.mkdir(mode=0o700)
    directory = root / 'credential'; directory.mkdir(mode=0o700)
    path = directory / 'credential.json'; path.write_bytes(b'original-expired-credential\n'); path.chmod(0o600)
    monkeypatch.setattr(m, 'OLD_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
    with m.CredentialStore(path, _anchor=root, _owner_uid=os.getuid()) as store:
        yield m, root, path, store


@pytest.mark.parametrize('kind', ['world-readable','hard-link','symlink','parent-writable','wrong-bytes'])
def test_real_reader_rejects_unsafe_file_or_parent(storage, kind):
    m, root, path, store = storage
    if kind == 'world-readable': path.chmod(0o644)
    if kind == 'hard-link': os.link(path, path.with_name('hardlink'))
    if kind == 'symlink':
        path.rename(path.with_name('target')); path.symlink_to('target')
    if kind == 'parent-writable': path.parent.chmod(0o777)
    if kind == 'wrong-bytes': path.write_bytes(b'changed')
    with pytest.raises(m.CredentialError): store.original()


def test_real_atomic_replace_has_private_exact_readback_and_no_old_copy(storage):
    m, root, path, store = storage
    before = store.original(); calls = []
    new_hash = store.replace(incoming(), before, lambda: calls.append('guard'))
    assert json.loads(path.read_bytes()) == incoming()
    assert new_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_mode & 0o777 == 0o600
    assert {p.name for p in path.parent.iterdir()} == {'credential.json'}
    assert calls == ['guard']


def test_swap_during_atomic_write_is_detected_before_replace(storage):
    m, root, path, store = storage
    before = store.original()
    def swap():
        path.unlink(); path.write_bytes(b'swapped'); path.chmod(0o600)
    with pytest.raises(m.CredentialError): store.replace(incoming(), before, swap)
    assert path.read_bytes() == b'swapped'
    assert {p.name for p in path.parent.iterdir()} == {'credential.json'}


def test_parent_swap_is_detected_using_retained_directory_descriptors(storage):
    m, root, path, store = storage
    before = store.original(); original = path.parent
    original.rename(root / 'moved'); original.mkdir(mode=0o700)
    with pytest.raises(m.CredentialError): store.replace(incoming(), before, lambda: None)
    assert (root / 'moved/credential.json').read_bytes() == b'original-expired-credential\n'
    assert not path.exists()


class Adapter:
    recovery_sha = 'c'*40
    def __init__(self): self.events=[]; self.generation=0
    def snapshot(self): self.events.append('snapshot'); return {'generation':self.generation}
    def stopped(self): self.events.append('stopped')


def test_default_inspection_is_read_only_without_incoming_token_or_ci_claim(storage):
    m, root, path, store = storage; a = Adapter(); audit = root/'attempt'; gates=[]
    result = m.refresh(a, store, None, audit, lambda: gates.append('gate'), now=lambda:1000)
    assert result['state']=='INSPECTED' and gates==[] and result['ci_verified'] is False
    assert not audit.exists() and path.read_bytes()==b'original-expired-credential\n'
    assert 'test-token-secret' not in json.dumps(result)


def test_apply_records_once_preserves_incident_and_never_stores_token_in_audit(storage):
    m, root, path, store=storage; a=Adapter(); audit=root/'attempt'
    inspected=m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)
    result=m.refresh(a,store,incoming(),audit,lambda:None,inspected['evidence_sha256'],accept=True,now=lambda:1000)
    assert result['state']=='CREDENTIAL_REPLACED' and result['original_incident_preserved'] is True
    assert {p.name for p in audit.iterdir()}=={'intent.json','completed.json'}
    assert all('test-token-secret' not in p.read_text() for p in audit.iterdir())
    with pytest.raises(m.CredentialError): m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)


@pytest.mark.parametrize('change', ['digest','incident','credential','expired','gate'])
def test_preflight_rejection_does_not_consume_attempt_or_change_credential(storage, change):
    m,root,path,store=storage; a=Adapter(); audit=root/'attempt'; now=lambda:1000
    expected=m.refresh(a,store,None,audit,lambda:None,now=now)['evidence_sha256']
    gate=lambda:None
    if change=='digest': expected='0'*64
    if change=='incident': a.generation+=1
    if change=='credential': path.write_bytes(b'changed')
    if change=='expired': now=lambda:1400
    if change=='gate': gate=lambda:(_ for _ in ()).throw(RuntimeError('test-token-secret'))
    before=path.read_bytes()
    with pytest.raises(m.CredentialError) as error: m.refresh(a,store,incoming(),audit,gate,expected,accept=True,now=now)
    assert 'test-token-secret' not in str(error.value)
    assert not audit.exists() and path.read_bytes()==before


def test_post_intent_failure_is_durable_secret_free_and_no_retry(storage, monkeypatch):
    m,root,path,store=storage; a=Adapter(); audit=root/'attempt'
    expected=m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)['evidence_sha256']
    monkeypatch.setattr(store,'replace',lambda *args:(_ for _ in ()).throw(OSError('test-token-secret')))
    with pytest.raises(m.CredentialError): m.refresh(a,store,incoming(),audit,lambda:None,expected,accept=True,now=lambda:1000)
    assert json.loads((audit/'failure.json').read_text())['state']=='NEEDS_OPERATOR'
    assert all('test-token-secret' not in p.read_text() for p in audit.iterdir())
    with pytest.raises(m.CredentialError): m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)


def test_real_child_token_only_on_stdin_env_and_argv_clean_and_output_discarded(tmp_path, monkeypatch, capfd):
    m=module(); scripts=tmp_path/'scripts'; scripts.mkdir(); evidence=tmp_path/'child.json'
    (scripts/'trusted_release_gate.py').write_text('import sys,os,json\nfrom pathlib import Path\n'
        'token=sys.stdin.buffer.read().decode()\n'
        f'Path({str(evidence)!r}).write_text(json.dumps({{"argv":sys.argv,"env":dict(os.environ),"stdin_valid":token=="test-token-secret"}}))\n'
        'print(token)\nprint(token,file=sys.stderr)\n')
    monkeypatch.setattr(m,'SYSTEM_PYTHON',sys.executable)
    monkeypatch.setenv('GH_TOKEN','legacy-secret'); monkeypatch.setenv('HTTPS_PROXY','private-proxy')
    m.run_gate(tmp_path,'c'*40,incoming()['token'])
    result=json.loads(evidence.read_text())
    assert result['stdin_valid'] is True
    assert '--token-stdin' in result['argv'] and '--observed-main' in result['argv']
    assert 'test-token-secret' not in json.dumps(result['argv'])
    assert not {'GH_TOKEN','HTTPS_PROXY'} & result['env'].keys()
    assert 'test-token-secret' not in ''.join(capfd.readouterr())


@pytest.mark.parametrize('digest,accept', [(None,True), ('0'*64,False), ('bad',True)])
def test_apply_authorization_must_be_explicit_and_digest_bound(storage,digest,accept):
    m,root,path,store=storage; audit=root/'attempt'
    with pytest.raises(m.CredentialError):
        m.refresh(Adapter(),store,None,audit,lambda:None,digest,accept=accept,now=lambda:1000)
    assert not audit.exists()


@pytest.mark.parametrize('kind', ['directory','file','dangling-symlink'])
def test_any_prior_attempt_is_not_retry_authority(storage,kind):
    m,root,path,store=storage; audit=root/'attempt'; a=Adapter()
    if kind=='directory': audit.mkdir()
    if kind=='file': audit.write_text('unknown')
    if kind=='dangling-symlink': audit.symlink_to(root/'missing')
    with pytest.raises(m.CredentialError): m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)
    assert a.events==[]


def test_incoming_credential_is_not_part_of_the_read_only_inspection_digest(storage):
    m,root,path,store=storage; a=Adapter(); audit=root/'attempt'
    inspected=m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)
    fresh={**incoming(),'token':'different-fresh-secret','expires_at':1600}
    result=m.refresh(a,store,fresh,audit,lambda:None,inspected['evidence_sha256'],accept=True,now=lambda:1200)
    assert result['state']=='CREDENTIAL_REPLACED' and json.loads(path.read_bytes())==fresh


def test_temp_collision_never_overwrites_stranger_or_old_credential(storage):
    m,root,path,store=storage; before=store.original()
    temporary=path.parent/('.credential.'+m.ATTEMPT+'.tmp'); temporary.write_bytes(b'stranger'); temporary.chmod(0o600)
    with pytest.raises(m.CredentialError): store.replace(incoming(),before,lambda:None)
    assert temporary.read_bytes()==b'stranger'
    assert path.read_bytes()==b'original-expired-credential\n'


def test_real_gate_failure_never_echoes_token_or_child_exception(tmp_path,monkeypatch,capfd):
    m=module(); scripts=tmp_path/'scripts'; scripts.mkdir()
    (scripts/'trusted_release_gate.py').write_text('import sys\ntoken=sys.stdin.read()\nprint(token,file=sys.stderr)\nraise RuntimeError(token)\n')
    monkeypatch.setattr(m,'SYSTEM_PYTHON',sys.executable)
    with pytest.raises(m.CredentialError) as error: m.run_gate(tmp_path,'c'*40,incoming()['token'])
    assert incoming()['token'] not in str(error.value)+''.join(capfd.readouterr())


def test_actual_low_level_fsync_failure_consumes_attempt_without_secret_diagnostics(storage,monkeypatch):
    m,root,path,store=storage; a=Adapter(); audit=root/'attempt'
    inspected=m.refresh(a,store,None,audit,lambda:None,now=lambda:1000)
    original_fsync=m.os.fsync
    def fail_only_credential_file(fd):
        if os.fstat(fd).st_size==len(m.encoded(incoming())):
            raise OSError('test-token-secret')
        return original_fsync(fd)
    monkeypatch.setattr(m.os,'fsync',fail_only_credential_file)
    with pytest.raises(m.CredentialError) as error:
        m.refresh(a,store,incoming(),audit,lambda:None,inspected['evidence_sha256'],accept=True,now=lambda:1000)
    assert incoming()['token'] not in str(error.value)
    assert path.read_bytes()==b'original-expired-credential\n'
    assert {p.name for p in path.parent.iterdir()}=={'credential.json'}
    assert json.loads((audit/'failure.json').read_text())['state']=='NEEDS_OPERATOR'
