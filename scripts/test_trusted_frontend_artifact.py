"""Prepared frontend artifacts are local, immutable and claimed exactly once."""
import importlib.util
from pathlib import Path
import os
from types import SimpleNamespace
import pytest


def load():
    spec = importlib.util.spec_from_file_location('artifact_test', Path(__file__).with_name('trusted_frontend_artifact.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_identity_is_exact_and_versioned():
    m = load()
    value = m.identity('a'*40, 'b'*40, 'c'*32, 'd'*64, {'BACKEND_URL':'http://127.0.0.1:8000'}, {'node':'22'}, 'e'*64)
    assert value['schema_version'] == 1
    assert value['artifact_id'] == 'c'*32
    for args in [('x', 'b'*40, 'c'*32, 'd'*64), ('a'*40, 'b'*40, '../escape', 'd'*64)]:
        with pytest.raises(m.ArtifactError): m.identity(*args, {}, {}, 'e'*64)


def test_real_metadata_rejects_writeable_hardlinked_and_symlink_files(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m, 'OWNER', os.getuid())
    path = tmp_path/'proof'; path.write_text('proof'); path.chmod(0o600)
    assert m.private_bytes(path) == b'proof'
    path.chmod(0o666)
    with pytest.raises(m.ArtifactError): m.private_bytes(path)
    path.chmod(0o600); os.link(path, tmp_path/'hard')
    with pytest.raises(m.ArtifactError): m.private_bytes(path)
    (tmp_path/'hard').unlink(); (tmp_path/'link').symlink_to(path)
    with pytest.raises(m.ArtifactError): m.private_bytes(tmp_path/'link')


def test_claim_is_exclusive_and_binds_publication(tmp_path, monkeypatch):
    m=load(); monkeypatch.setattr(m,'OWNER',os.getuid())
    def write(path, data):
        fd=os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
    server=SimpleNamespace(_write_private=write,_sync_directory=lambda p:None)
    proof={'artifact_id':'c'*32,'manifest_sha256':'a'*64}
    m.claim(tmp_path, proof, 'b'*40, 'c'*32, server)
    assert b'"production_sha": "bbbb' in (tmp_path/'claim.json').read_bytes()
    with pytest.raises(FileExistsError):m.claim(tmp_path,proof,'b'*40,'c'*32,server)
    with pytest.raises(m.ArtifactError):m.claim(tmp_path,proof,'b'*40,'d'*32,server)


def test_entry_is_before_environment_loading():
    source=(Path(__file__).parents[1]/'deploy.sh').read_text()
    assert source.index('--prepare-frontend-artifact') < source.index('ENV_FILE=')


def prepared_fixture(tmp_path, monkeypatch):
    import hashlib
    import json
    m=load();monkeypatch.setattr(m,'OWNER',os.getuid())
    monkeypatch.setattr(m,'STATE',tmp_path/'state');monkeypatch.setattr(m,'BUILDS',tmp_path/'builds')
    m.STATE.mkdir(mode=0o700);m.BUILDS.mkdir(mode=0o700)
    plan=m.identity('a'*40,'b'*40,'c'*32,'d'*64,{'BACKEND_URL':'http://127.0.0.1:8000'},{'node':'22'},'e'*64)
    def write(path,data):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as out:out.write(data)
    server=SimpleNamespace(_write_private=write,_sync_directory=lambda p:None,secure_path=lambda *a,**kw:None)
    def copy(source,stage,env):
        stage.mkdir(mode=0o700);(stage/'frontend').mkdir(mode=0o700)
    def compile(*args,**kwargs):
        stage=m.BUILDS/plan['artifact_id']/'frontend'
        for name in ('.next','node_modules'):
            (stage/name).mkdir();(stage/name/'compiled').write_bytes(b'actual compiled bytes');(stage/name/'compiled').chmod(0o644)
        (stage/'node_modules/entry').symlink_to('compiled')
        kwargs['stdout'].write(b'build completed\n')
    monkeypatch.setattr(m.subprocess,'run',compile)
    monkeypatch.setattr(m,'binding',lambda *a:plan)
    build=SimpleNamespace(copy_build_inputs=copy,ENV={},freeze_artifacts=lambda p:None,
                          write_json=lambda server,path,value:write(path,json.dumps(value,sort_keys=True).encode()))
    def digest(front,build):
        h=hashlib.sha256()
        for p in sorted(front.rglob('*')):
            if p.is_file():h.update(p.relative_to(front).as_posix().encode()+p.read_bytes())
        return h.hexdigest()
    publisher=SimpleNamespace(build_command=lambda *a:['mock-sandbox'],prepare_cache=lambda p:None,bundle_digest=digest)
    m.prepare(plan,tmp_path,publisher,build,server)
    return m,plan,publisher,build,server


def test_ready_artifact_real_files_consumed_once_without_compiler(tmp_path,monkeypatch):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    proof=m.verify(expected,publisher,build,server)
    plan=dict(publisher_sha=expected['publisher_sha'],frontend_tree=expected['frontend_tree'],operation_id=expected['artifact_id'],
              public_build_env=expected['public_build_env'],production_sha='f'*40,prepared_artifact=proof)
    audit=tmp_path/'publication';audit.mkdir(mode=0o700)
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:pytest.fail('consumer must not compile or invoke npm'))
    assert m.consume(plan,tmp_path,publisher,build,server,audit)==proof['manifest']['artifact_digest']
    assert (audit/'build.log').read_bytes()==b'build completed\n'
    with pytest.raises(m.ArtifactError):m.verify(expected,publisher,build,server)
    assert (m.STATE/'frontend-artifacts'/expected['artifact_id']/'claim.json').is_file()


@pytest.mark.parametrize('change',['bytes','added','hardlink','world_write','intent','log','ready','failed','toolchain','lock','environment'])
def test_artifact_tampering_or_binding_drift_rejected(tmp_path,monkeypatch,change):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    audit=m.STATE/'frontend-artifacts'/expected['artifact_id'];file=m.BUILDS/expected['artifact_id']/'frontend/node_modules/compiled'
    if change=='bytes':file.write_bytes(b'tampered')
    elif change=='added':(file.parent/'extra').write_text('extra')
    elif change=='hardlink':os.link(file,file.parent/'hard')
    elif change=='world_write':file.chmod(0o666)
    elif change in ('intent','log','ready'):(audit/{'intent':'intent.json','log':'build.log','ready':'ready.json'}[change]).write_text('{}')
    elif change=='failed':(audit/'failed.json').write_text('{}')
    else:expected={**expected,{'toolchain':'toolchain','lock':'package_lock_sha256','environment':'public_build_env'}[change]:'drift'}
    with pytest.raises(m.ArtifactError):m.verify(expected,publisher,build,server)


def test_unknown_preparation_retained_no_same_id_retry(tmp_path,monkeypatch):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    with pytest.raises(FileExistsError):m.prepare(expected,tmp_path,publisher,build,server)
    audit=m.STATE/'frontend-artifacts'/expected['artifact_id']
    assert (audit/'ready.json').exists() and not (audit/'claim.json').exists()


def test_prepare_lock_prevents_partially_finalized_consumption(tmp_path,monkeypatch):
    import fcntl
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    with (m.STATE/'frontend-artifacts'/expected['artifact_id']/'prepare.lock').open('rb') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):m.verify(expected,publisher,build,server)


def test_symlink_containment_and_special_objects(tmp_path,monkeypatch):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    node=m.BUILDS/expected['artifact_id']/'frontend/node_modules'
    (node/'escape').symlink_to(tmp_path)
    with pytest.raises(m.ArtifactError,match='escapes'):m.verify(expected,publisher,build,server)
    (node/'escape').unlink();os.mkfifo(node/'pipe')
    with pytest.raises(m.ArtifactError,match='unsupported'):m.verify(expected,publisher,build,server)


def test_file_identity_ignores_read_access_time():
    m=load()
    values=dict(st_dev=1,st_ino=2,st_mode=0o600,st_nlink=1,st_uid=0,st_gid=0,st_size=2,st_mtime_ns=1,st_ctime_ns=2)
    assert m.file_identity(SimpleNamespace(**values,st_atime_ns=3))==m.file_identity(SimpleNamespace(**values,st_atime_ns=4))


@pytest.mark.skipif(os.environ.get('REVA_TEST_FRONTEND_ARTIFACT_BUILD')!='1',reason='requires isolated Linux systemd runner and real npm build')
def test_native_prepare_then_consume_actual_frontend_without_rebuild(monkeypatch):
    """Real npm/Next output and sandbox, with synthetic paths and service account."""
    import json
    import shutil
    import subprocess
    import tempfile
    import uuid
    assert os.geteuid()==0 and Path('/run/systemd/system').is_dir()
    repository=Path(__file__).resolve().parents[1]
    m=load()
    def module(name):
        spec=importlib.util.spec_from_file_location('native_'+name,repository/'scripts'/f'{name}.py')
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
    build=module('trusted_frontend_rebuild');publisher=module('trusted_frontend_publish');server=module('trusted_release_server')
    root=Path(tempfile.mkdtemp(prefix='reva-prepared-artifact-',dir='/var/lib'));root.chmod(0o700)
    state=root/'state';state.mkdir(mode=0o700)
    stages=root/'builds';stages.mkdir(mode=0o755)
    for target in (m,build,publisher):monkeypatch.setattr(target,'STATE',state);monkeypatch.setattr(target,'BUILDS',stages)
    # Explicit fixture repository, not an executable deployment source override.
    def git(source,*args):
        return subprocess.check_output(['/usr/bin/git','-c',f'safe.directory={source}','-C',str(source),*args],text=True).strip()
    monkeypatch.setattr(build,'git',git)
    username='reva-artifact-'+uuid.uuid4().hex[:10]
    subprocess.run(['/usr/sbin/useradd','--system','--no-create-home',username],check=True)
    getpwnam=publisher.pwd.getpwnam
    monkeypatch.setattr(publisher.pwd,'getpwnam',lambda name:getpwnam(username if name=='health-web' else name))
    try:
        sha=git(repository,'rev-parse','HEAD');tree=git(repository,'rev-parse','HEAD:frontend');operation=uuid.uuid4().hex
        expected=m.binding(repository,sha,tree,operation,{'BACKEND_URL':'http://127.0.0.1:8000'},build)
        prepared=m.prepare(expected,repository,publisher,build,server)
        proof=m.verify(expected,publisher,build,server)
        assert prepared['artifact_digest']==proof['manifest']['artifact_digest']
        assert (stages/operation/'frontend/.next/BUILD_ID').read_text().strip()
        audit=root/'publication';audit.mkdir(mode=0o700)
        plan=dict(publisher_sha=sha,frontend_tree=tree,operation_id=operation,production_sha=sha,
                  public_build_env=expected['public_build_env'],prepared_artifact=proof)
        run=subprocess.run
        def no_compiler(argv,*args,**kwargs):
            assert '/usr/bin/systemd-run' not in argv and 'ci' not in argv and 'build' not in argv
            return run(argv,*args,**kwargs)
        monkeypatch.setattr(m.subprocess,'run',no_compiler)
        assert m.consume(plan,repository,publisher,build,server,audit)==prepared['artifact_digest']
        assert json.loads((state/'frontend-artifacts'/operation/'claim.json').read_bytes())['operation_id']==operation
        with pytest.raises(m.ArtifactError):m.verify(expected,publisher,build,server)
    finally:
        subprocess.run(['/usr/sbin/userdel',username],check=True)
        shutil.rmtree(root)


def test_build_failure_preserves_failed_intent_and_never_produces_ready(tmp_path,monkeypatch):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    expected={**expected,'artifact_id':'f'*32}
    def fail(*a,**kw):raise RuntimeError('synthetic compiler failure')
    monkeypatch.setattr(m.subprocess,'run',fail)
    with pytest.raises(RuntimeError):m.prepare(expected,tmp_path,publisher,build,server)
    audit=m.STATE/'frontend-artifacts'/expected['artifact_id']
    assert (audit/'intent.json').is_file() and (audit/'failed.json').is_file()
    assert not (audit/'ready.json').exists() and not (audit/'claim.json').exists()
    with pytest.raises(m.ArtifactError):m.verify(expected,publisher,build,server)
    with pytest.raises(FileExistsError):m.prepare(expected,tmp_path,publisher,build,server)


def test_canonical_loader_rejects_real_ignored_pyc_before_any_execution(tmp_path,monkeypatch):
    import py_compile
    import shutil
    import subprocess
    m=load();monkeypatch.setattr(m,'OWNER',os.getuid())
    source=tmp_path/'source';source.mkdir();(source/'scripts').mkdir()
    entry=source/'scripts/publisher.py';entry.write_text('VALUE = "source"\n');entry.chmod(0o644)
    def git(*args):return subprocess.check_output(['git','-C',str(source),*args],text=True).strip()
    git('init','-q');git('add','scripts/publisher.py')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
    sha=git('rev-parse','HEAD')
    sentinel=tmp_path/'executed'
    entry.write_text(f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("cached execution")\n')
    py_compile.compile(str(entry),doraise=True,invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    entry.write_text('VALUE = "source"\n')
    with pytest.raises(m.ArtifactError,match='cached'):m.canonical_module('artifact_pyc_negative',entry,source,sha)
    assert not sentinel.exists()
    shutil.rmtree(entry.parent/'__pycache__')
    assert m.canonical_module('artifact_source_control',entry,source,sha).VALUE=='source'
    entry.write_text('raise RuntimeError("uncommitted substitution")\n')
    with pytest.raises(m.ArtifactError,match='canonical bytes'):m.canonical_module('artifact_changed_source',entry,source,sha)


def test_artifact_root_must_be_real_directory_not_relative_alias(tmp_path,monkeypatch):
    m,expected,publisher,build,server=prepared_fixture(tmp_path,monkeypatch)
    front=m.BUILDS/expected['artifact_id']/'frontend'
    (front/'node_modules').rename(front/'aliased')
    (front/'node_modules').symlink_to('aliased')
    with pytest.raises(m.ArtifactError,match='root'):m.verify(expected,publisher,build,server)
