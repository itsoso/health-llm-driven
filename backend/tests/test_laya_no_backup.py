"""No-copy deploy context must reach the unchanged installed-generation verifier."""
import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location('laya_no_backup', ROOT / 'backend/scripts/verify_laya_no_backup.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


@pytest.fixture
def exported(tmp_path, monkeypatch):
    base = tmp_path / 'laya'
    sha = 'a'*40
    source = base / 'sources' / sha
    source.mkdir(parents=True)
    files = {}
    for name in verifier.ASSETS:
        data = (ROOT / 'infra/laya' / name).read_bytes()
        (source / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    (source / 'source.json').write_text(json.dumps({'sha':sha,'old_sha':'b'*40,'old_has_decisions':True,'files':files}))
    stage = tmp_path / 'stage'
    stage.mkdir()
    manifests = []
    for name in verifier.STAGED:
        data = name.encode()
        (stage / name).write_bytes(data)
        manifests.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
    (stage / 'staged.sha256').write_text(''.join(manifests))
    lock = tmp_path / 'lock'
    lock.mkdir()
    (lock / 'token').write_text('token\n')
    (lock / 'stage').write_text(str(stage)+'\n')
    env = tmp_path / 'live.env'
    env.write_text('DECISION_PROVIDER=laya\nDECISION_MODE=on\nDECISION_ADMIN_CONTROL_ENABLED=true\nDECISION_BASE_URL=http://127.0.0.1:8092/v1\nDECISION_MODEL=multilingual\nDECISION_API_KEY='+'a'*48+'\n')
    monkeypatch.setattr(verifier, 'BASE', base)
    monkeypatch.setattr(verifier, 'LIVE_ENV', env)
    monkeypatch.setattr(verifier, 'STAGE_PATTERN', str(stage))
    monkeypatch.setattr(verifier.sys, 'platform', 'linux')
    monkeypatch.setattr(verifier.sys, 'dont_write_bytecode', True)
    monkeypatch.setattr(verifier.os, 'geteuid', lambda: 0)
    # Root ownership is unavailable on unprivileged CI; keep real file/hash/lease
    # context and normalize only ownership/modes separately covered by helpers.
    monkeypatch.setattr(verifier, 'secure', lambda path, **kw: None)
    monkeypatch.setattr(verifier.grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=env.stat().st_gid))
    module = verifier.load_installer(source)
    monkeypatch.setattr(module, 'resolve_business_lease', lambda path: Path(path))
    monkeypatch.setattr(module, 'secure', lambda path, **kw: None)
    monkeypatch.setattr(verifier, 'load_installer', lambda path: module)
    return SimpleNamespace(sha=sha, lock=str(lock), token='token', stage=str(stage), phase='provision'),source,env,module


def test_no_backup_context_uses_live_env_without_creating_candidate(exported):
    args, source, env, module = exported
    # Original deployment consumer genuinely fails on the removed candidate
    # env file; only OS ownership is normalized, context is executed unchanged.
    prior_secure = module.secure
    module.secure = lambda path, **kw: Path(path).lstat()
    try:
        with pytest.raises(FileNotFoundError) as error:
            module.context(args)
        assert Path(error.value.filename).name == 'backend.env.candidate'
    finally:
        module.secure = prior_secure
    context = verifier.context(args)
    assert context['config']['DECISION_PROVIDER'] == 'laya'
    assert not (Path(args.stage) / 'backend.env.candidate').exists()
    assert module.expected_install(source, context['config'])[3]['generation'] == verifier.generation_digest(source)


@pytest.mark.parametrize('fault',['token','stage_digest','env_copy','source_digest','ambiguous_config'])
def test_no_backup_context_blocks_drift(exported, fault):
    args, source, env, module = exported
    if fault == 'token': (Path(args.lock)/'token').write_text('wrong\n')
    elif fault == 'stage_digest': (Path(args.stage)/'backup_db.sh').write_text('changed')
    elif fault == 'env_copy': (Path(args.stage)/'backend.env.candidate').write_text('must reject')
    elif fault == 'source_digest': (source/'serve.py').write_text('changed')
    else: env.write_text(' DECISION_PROVIDER=remote\n'+env.read_text())
    with pytest.raises((verifier.VerificationError, module.InstallError)):
        verifier.context(args)


@pytest.mark.parametrize('phase',['provision','activate','verify'])
@pytest.mark.parametrize('fault',[None,'missing_receipt','generation','live_env_changed','health'])
def test_real_context_existing_install_consumer_never_mutates_or_infers(exported, monkeypatch, tmp_path, phase, fault):
    args,source,env,module=exported
    args.phase=phase
    state=tmp_path/'installed';state.mkdir()
    monkeypatch.setattr(module,'STATE',state)
    parsed=module.parse_config(env.read_text())
    generation,unit,service_env,expected=module.expected_install(source,parsed)
    if fault!='missing_receipt':
        (state/'install.json').write_text(json.dumps({**expected,'state':'INSTALLED'}))
    unit_path=tmp_path/'unit';unit_path.write_bytes(unit)
    env_path=tmp_path/'service.env';env_path.write_bytes(service_env)
    monkeypatch.setattr(module,'UNIT',unit_path);monkeypatch.setattr(module,'ENV',env_path)
    monkeypatch.setattr(module,'validate_account',lambda:SimpleNamespace(pw_gid=env_path.stat().st_gid))
    def verify_generation(src,gen):
        assert src==source and gen==generation
        if fault=='generation': raise module.InstallError('generation_source_mismatch')
    monkeypatch.setattr(module,'verify_generation',verify_generation)
    monkeypatch.setattr(module,'command',lambda args: '')
    for method in ['prepare','activate','probe','save_receipt','write_atomic']:
        monkeypatch.setattr(module,method,lambda *a:pytest.fail('must not mutate or infer'))
    monkeypatch.setattr(verifier,'process_binding',lambda *a:({'pid':'123'},b'100'))
    calls=[]
    def health():
        calls.append('GET')
        if fault=='health':raise verifier.VerificationError('health failed')
    monkeypatch.setattr(verifier,'health_get',health)
    def sleep(seconds):
        assert seconds==7
        if fault=='live_env_changed':env.write_text(env.read_text()+'UNRELATED_CHANGED=1\n')
    monkeypatch.setattr(verifier.time,'sleep',sleep)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    if fault:
        with pytest.raises((verifier.VerificationError,module.InstallError)):
            verifier.verify_existing(args)
    else:
        result=verifier.verify_existing(args)
        assert result=={'state':'LAYA_EXISTING_HEALTH_VERIFIED','generation':expected['generation'],'inference_performed':False}
        assert calls==['GET','GET']
        assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_health_contract_performs_only_get(monkeypatch):
    calls=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return b'{"status":"ok","loaded":["multilingual"],"device":"cpu"}'
    class Opener:
        def open(self,url,*,timeout):
            assert isinstance(url,str)
            calls.append((url,timeout));return Response()
    monkeypatch.setattr(verifier,'build_opener',lambda *args:Opener())
    verifier.health_get()
    assert calls==[('http://127.0.0.1:8092/health',5)]


def test_deploy_bundle_producer_reaches_no_copy_context_and_verifier(exported, monkeypatch, tmp_path):
    import subprocess
    args,old_source,env,module=exported
    repo=tmp_path/'production';repo.mkdir()
    def git(*values):
        return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-C',str(repo),*values],stderr=subprocess.DEVNULL)
    git('init','-b','main')
    for name in verifier.ASSETS:
        target=repo/'infra/laya'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/'infra/laya'/name).read_bytes())
    target=repo/'backend/scripts/verify_laya_no_backup.py';target.parent.mkdir(parents=True)
    target.write_bytes((ROOT/'backend/scripts/verify_laya_no_backup.py').read_bytes())
    app=repo/'backend/app/config.py';app.parent.mkdir();app.write_text('DECISION_PROVIDER = "laya"\n')
    git('add','infra','backend')
    git('-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-m','synthetic fixture')
    revision=git('rev-parse','HEAD').decode().strip()
    bundle=tmp_path/'deploy.bundle';git('bundle','create',str(bundle),'HEAD');bundle.chmod(0o600)
    base=tmp_path/'exported'
    body=(ROOT/'deploy.sh').read_text().split("<<'REMOTE_LAYA_SOURCE'\n",1)[1].split('\nREMOTE_LAYA_SOURCE',1)[0]
    body=body.replace("Path('/var/lib/reva-laya-release')",f'Path({str(base)!r})')
    body=body.replace("Path('/opt/health-app')",f'Path({str(repo)!r})')
    # Normalize only root ownership to the unprivileged fixture owner.
    body=body.replace('info.st_uid != 0','info.st_uid != os.getuid()')
    for path in [Path(args.lock),Path(args.stage)]:path.chmod(0o700)
    for path in Path(args.lock).iterdir():path.chmod(0o600)
    calls=[]
    class Executed(Exception):pass
    def execute(binary,argv,child_env):
        calls.append((binary,argv,child_env));raise Executed()
    monkeypatch.setattr(os,'execve',execute)
    monkeypatch.setattr(verifier.sys,'argv',['export',str(bundle),revision,args.lock,args.token,args.stage,revision])
    with pytest.raises(Executed):exec(compile(body,'deploy.sh:REMOTE_LAYA_SOURCE','exec'),{})
    new_source=base/'sources'/revision
    own=base/'verifiers'/revision/'verify_laya_no_backup.py'
    assert calls[0][1][4]==str(own)
    assert set(p.name for p in new_source.iterdir())==set(verifier.ASSETS)|{'source.json'}
    assert (new_source/'install.py').read_bytes()==(ROOT/'infra/laya/install.py').read_bytes()
    assert own.read_bytes()==target.read_bytes()
    binding=json.loads((own.parent/'source.json').read_text())
    assert binding=={'sha':revision,'sha256':hashlib.sha256(own.read_bytes()).hexdigest()}
    args.sha=revision
    monkeypatch.setattr(verifier,'BASE',base)
    assert verifier.context(args)['source']==new_source
    test_real_context_existing_install_consumer_never_mutates_or_infers(
        (args,new_source,env,module),monkeypatch,tmp_path,'verify',None)
    command=(ROOT/'deploy.sh').read_text().split('laya_service_command() {',1)[1].split('\n}',1)[0]
    assert '/verifiers/$DEPLOY_EXPECTED_SHA/verify_laya_no_backup.py' in command
    assert '/install.py' not in command


@pytest.mark.parametrize('damage',['symlink','writable','owner','hardlink'])
def test_root_controlled_verifier_paths_reject_unsafe_metadata(monkeypatch, damage):
    target=Path('/fixture/verify.py')
    def info(path):
        is_file=path==target
        mode=(stat.S_IFREG|0o400) if is_file else (stat.S_IFDIR|0o755)
        if is_file and damage=='symlink':mode=stat.S_IFLNK|0o777
        if is_file and damage=='writable':mode=stat.S_IFREG|0o666
        return SimpleNamespace(st_mode=mode,st_uid=1000 if is_file and damage=='owner' else 0,
                               st_nlink=2 if is_file and damage=='hardlink' else 1)
    monkeypatch.setattr(Path,'lstat',info)
    with pytest.raises(verifier.VerificationError):verifier.secure(target,mode=0o400)


@pytest.mark.parametrize('damage',[None,'wrong_key','duplicate_key','restarts'])
def test_live_process_configuration_is_bound_without_inference(monkeypatch,tmp_path,damage):
    proc=tmp_path/'123';proc.mkdir()
    (proc/'stat').write_bytes(b'123 (python) '+b' '.join([b'0']*19+[b'500']))
    key='a'*48
    raw=('LAYA_API_KEY='+('wrong' if damage=='wrong_key' else key)).encode()+b'\0'
    if damage=='duplicate_key':raw+=('LAYA_API_KEY='+key).encode()+b'\0'
    (proc/'environ').write_bytes(raw)
    monkeypatch.setattr(verifier,'PROC',tmp_path)
    module=SimpleNamespace(service_identity=lambda generation:{'MainPID':'123','NRestarts':'1' if damage=='restarts' else '0'})
    if damage:
        with pytest.raises(verifier.VerificationError):
            verifier.process_binding(module,tmp_path,{'DECISION_API_KEY':key})
    else:
        assert verifier.process_binding(module,tmp_path,{'DECISION_API_KEY':key})[1]==b'500'


@pytest.mark.parametrize('phase',['provision','activate','verify'])
@pytest.mark.parametrize('pending_name',['receipt','unit','env'])
@pytest.mark.parametrize('kind',['file','directory','symlink'])
def test_existing_install_pending_artifacts_block_before_health(exported,monkeypatch,tmp_path,phase,pending_name,kind):
    args,source,env,module=exported
    args.phase=phase
    state=tmp_path/'installed';state.mkdir()
    monkeypatch.setattr(module,'STATE',state)
    monkeypatch.setattr(module,'UNIT',tmp_path/'unit')
    monkeypatch.setattr(module,'ENV',tmp_path/'service.env')
    targets={'receipt':state/'install.json.pending','unit':tmp_path/'unit.pending','env':tmp_path/'service.env.pending'}
    target=targets[pending_name]
    if kind=='file':target.write_text('preserve original partial operation')
    elif kind=='directory':target.mkdir()
    else:target.symlink_to(tmp_path/'absent-target')
    initial=target.lstat()
    monkeypatch.setattr(module,'existing_install',lambda expected:pytest.fail('pending must block before receipt'))
    monkeypatch.setattr(verifier,'health_get',lambda:pytest.fail('pending must block before GET'))
    with pytest.raises(verifier.VerificationError,match='pending_laya_operation'):
        verifier.verify_existing(args)
    assert target.lstat()==initial


@pytest.mark.parametrize('pending_name',['receipt','unit','env'])
def test_pending_appearing_during_stability_wait_is_preserved_and_blocks(exported,monkeypatch,tmp_path,pending_name):
    args,source,env,module=exported
    state=tmp_path/'installed';state.mkdir()
    monkeypatch.setattr(module,'STATE',state)
    generation,unit,service_env,expected=module.expected_install(source,module.parse_config(env.read_text()))
    (state/'install.json').write_text(json.dumps({**expected,'state':'INSTALLED'}))
    unit_path=tmp_path/'unit';unit_path.write_bytes(unit)
    env_path=tmp_path/'service.env';env_path.write_bytes(service_env)
    monkeypatch.setattr(module,'UNIT',unit_path);monkeypatch.setattr(module,'ENV',env_path)
    monkeypatch.setattr(module,'validate_account',lambda:SimpleNamespace(pw_gid=env_path.stat().st_gid))
    monkeypatch.setattr(module,'verify_generation',lambda *args:None)
    monkeypatch.setattr(module,'command',lambda *args:'')
    monkeypatch.setattr(verifier,'process_binding',lambda *args:({'pid':'123'},b'100'))
    monkeypatch.setattr(verifier,'health_get',lambda:None)
    target={'receipt':state/'install.json.pending','unit':tmp_path/'unit.pending','env':tmp_path/'service.env.pending'}[pending_name]
    monkeypatch.setattr(verifier.time,'sleep',lambda seconds:target.symlink_to(tmp_path/'missing'))
    with pytest.raises(verifier.VerificationError,match='pending_laya_operation'):
        verifier.verify_existing(args)
    assert target.is_symlink()
