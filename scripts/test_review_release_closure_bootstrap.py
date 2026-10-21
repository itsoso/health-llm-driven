"""Synthetic admission tests for the explicit maintenance-only release path."""
import importlib.util
from pathlib import Path
import pytest


def load():
    path=Path(__file__).with_name('bootstrap_trusted_release.py')
    spec=importlib.util.spec_from_file_location('release_closure_bootstrap_test',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('extra',[
    {'review_advance_receipt':'b'*64}, {'recovery_receipt':'b'*64},
    {'finalized_production_sha':'b'*40}, {'backend_ci':True}])
def test_release_closure_receipt_never_combines_authorities(monkeypatch,extra):
    b=load()
    monkeypatch.setattr(b,'validate_install',lambda *a,**k:None)
    monkeypatch.setattr(b,'reviewed_source',lambda *a:pytest.fail('reject before source or live work'))
    with pytest.raises(b.BootstrapError):
        b.rotate('1ba724dcb62ac389a72e41eecf40fea7aaca27e3','c'*40,0,'synthetic',
                 review_release_closure_receipt='a'*64,**extra)


def test_loader_is_distinct_and_pinned_to_sibling_module(monkeypatch):
    b=load();seen=[]
    monkeypatch.setattr(b,'secure',lambda p:seen.append(p.name))
    monkeypatch.setattr(b.os.path,'lexists',lambda p:False)
    module=b._review_release_closure_module()
    assert seen==['review_maintenance_release_closure.py']
    assert module.KIND!='fixed-review-maintenance-advance-v1'


def test_protected_rotation_input_is_bounded_exact_and_secret_free(monkeypatch):
    import io,json
    b=load()
    valid={'receipt':'a'*64,'github_token':'ghs_synthetic'}
    monkeypatch.setattr(b.sys,'stdin',type('Input',(),{'buffer':io.BytesIO(json.dumps(valid).encode())})())
    assert b._review_release_rotation_input()==valid
    bad=[{}, {**valid,'extra':True},{**valid,'receipt':'bad'},{**valid,'github_token':''},
         {**valid,'github_token':'secret\nheader'}, {**valid,'github_token':'x'*4097}]
    for value in bad:
        monkeypatch.setattr(b.sys,'stdin',type('Input',(),{'buffer':io.BytesIO(json.dumps(value).encode())})())
        with pytest.raises(b.BootstrapError) as error:b._review_release_rotation_input()
        assert 'secret' not in str(error.value)
    raw=b'{"receipt":"'+b'a'*64+b'","github_token":"one","github_token":"two"}'
    monkeypatch.setattr(b.sys,'stdin',type('Input',(),{'buffer':io.BytesIO(raw)})())
    with pytest.raises(b.BootstrapError):b._review_release_rotation_input()


def test_ephemeral_ci_token_cannot_be_used_by_ordinary_rotation(monkeypatch):
    b=load();monkeypatch.setattr(b,'validate_install',lambda *a,**k:None)
    monkeypatch.setattr(b,'reviewed_source',lambda *a:pytest.fail('before any source or live operation'))
    with pytest.raises(b.BootstrapError):b.rotate('a'*40,'b'*40,0,'synthetic',review_release_github_token='ghs_synthetic')
