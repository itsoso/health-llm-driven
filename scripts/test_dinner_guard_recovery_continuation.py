"""Synthetic continuation bridge tests; no production or model access."""
import importlib.util
from pathlib import Path
import copy
import pytest


def module():
    path = Path(__file__).with_name('dinner_guard_recovery_continuation.py')
    spec = importlib.util.spec_from_file_location('continuation_test', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fixture():
    old = {'files': {'unit': {'sha256': 'same'}}, 'lease': {'fixed': True},
           'units': {'example': {'effective_sha256': 'raw', 'files': {'fixed': True}}}}
    new = copy.deepcopy(old)
    new['units']['example']['effective_sha256'] = 'static'
    return old, new


def test_bridge_allows_only_reviewed_static_hash_replacement():
    m = module(); old, new = fixture()
    m.verify_bridge(old, new, {'example': 'raw'}, {'example': 'static'})


@pytest.mark.parametrize('field', ['lease', 'files', 'unit_files', 'static_pin', 'raw_pin', 'extra'])
def test_bridge_rejects_any_other_change(field):
    m = module(); old, new = fixture()
    if field == 'unit_files': new['units']['example']['files'] = {}
    elif field == 'static_pin': new['units']['example']['effective_sha256'] = 'other'
    elif field == 'raw_pin': old['units']['example']['effective_sha256'] = 'other'
    else: new[field] = {'changed': True}
    with pytest.raises(RuntimeError):
        m.verify_bridge(old, new, {'example': 'raw'}, {'example': 'static'})


def harness(tmp_path, monkeypatch):
    import hashlib, json, types, sys
    m = module()
    source = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('core_cont_test', source / 'scripts/recover_contained_services.py')
    core = importlib.util.module_from_spec(spec); sys.modules[spec.name] = core; spec.loader.exec_module(core)
    monkeypatch.setattr(core, 'STATE', tmp_path)
    raw_pins = m.literal_pins((source / 'scripts/dinner_guard_recovery.py').read_bytes())
    static_pins = {k: 'static-' + k for k in raw_pins}
    old = {'lease': {'fixed': True}, 'units': {k: {'effective_sha256': v, 'files': {'unchanged': True}} for k,v in raw_pins.items()}}
    current = copy.deepcopy(old)
    for k in current['units']: current['units'][k]['effective_sha256'] = static_pins[k]
    base = types.SimpleNamespace(STATE=tmp_path, FAILED='a'*40, PRODUCTION='f'*40,
        UNIT_CONFIG_PINS=raw_pins, UNIT_STATIC_CONFIG_PINS=static_pins, secure=lambda *a: None)
    audit = tmp_path / 'contained-service-recoveries' / base.FAILED; audit.mkdir(parents=True)
    data = {'recovery_sha':m.PRIOR_RECOVERY, 'failed_sha':base.FAILED, 'production_sha':base.PRODUCTION, 'snapshot':old}
    digest=core._digest(data); monkeypatch.setattr(m,'PRIOR_DIGEST',digest)
    raw=json.dumps({**data,'evidence_sha256':digest}).encode(); (audit/'intent.json').write_bytes(raw)
    monkeypatch.setattr(m,'INTENT_PIN',hashlib.sha256(raw).hexdigest())
    def identity(path,pin=None):
        raw=Path(path).read_bytes(); digest=hashlib.sha256(raw).hexdigest()
        if pin is not None: assert digest==pin
        return {'sha256':digest},raw
    base.identity=identity
    underlying=types.SimpleNamespace(snapshot=lambda:copy.deepcopy(current),stopped=lambda:None,
        base=types.SimpleNamespace(systemd=types.SimpleNamespace(show=lambda unit,key: {'ActiveState':'inactive','SubState':'dead','MainPID':'0'}[key]),_pids=lambda u:[]))
    bootstrap=types.SimpleNamespace(canonical_source=lambda sha:source)
    args=types.SimpleNamespace(sha='b'*40,accept_20261023_continuation=True,evidence_sha256=None)
    calls=[]
    monkeypatch.setattr(core,'_systemctl',lambda action,unit:calls.append((action,unit)))
    monkeypatch.setattr(core,'_application_probes',lambda *a:None)
    monkeypatch.setattr(core,'_wait_ready',lambda p:{'stable':True})
    monkeypatch.setattr(core,'_http_probes',lambda:None)
    return m,core,base,source,bootstrap,underlying,args,audit,calls,raw


@pytest.mark.parametrize('failure', [None, 'start', 'health', 'snapshot', 'observer'])
def test_single_continuation_preserves_original_and_contains_failure(tmp_path,monkeypatch,failure):
    m,core,base,source,bootstrap,underlying,args,audit,calls,raw=harness(tmp_path,monkeypatch)
    invoke=lambda:m.run_continuation(base,source,core,bootstrap,underlying,args)
    inspection=invoke(); assert inspection['state']=='INSPECTED'
    assert list(audit.iterdir())==[audit/'intent.json'] and not calls
    args.evidence_sha256=inspection['evidence_sha256']
    if failure=='start':
        def start(action,unit):
            calls.append((action,unit))
            if action=='start':raise RuntimeError('secret must not be emitted')
        monkeypatch.setattr(core,'_systemctl',start)
    elif failure=='health':
        monkeypatch.setattr(core,'_http_probes',lambda:(_ for _ in ()).throw(RuntimeError('secret')))
    elif failure=='snapshot':
        original=underlying.snapshot
        def snapshot():
            value=original()
            if calls:value['lease']={'changed':True}
            return value
        underlying.snapshot=snapshot
    elif failure=='observer':
        original=core.recover_services
        def wrapped(*a,**kw):
            observed=kw['stage_observer']
            def observer(stage):
                if stage.startswith('start_'):raise RuntimeError('secret')
                observed(stage)
            kw['stage_observer']=observer
            return original(*a,**kw)
        monkeypatch.setattr(core,'recover_services',wrapped)
    target=audit/m.CONTINUATION
    if failure:
        with pytest.raises(Exception):invoke()
        assert {u for a,u in calls if a=='stop'}==set(core.UNITS)
        assert not (target/'completed.json').exists()
        assert (target/'failure.json').exists()
        assert 'secret' not in (target/'failure.json').read_text()
        import json
        diagnostic=json.loads((target/'failure.json').read_text())
        if failure=='snapshot':
            assert diagnostic['first_proof_failure']['phase']=='snapshot_static_bridge'
            assert diagnostic['first_proof_failure']['exceptions'][0]['frames']
        if failure=='health':
            assert diagnostic['phase']=='http_auth_probes'
            assert len(diagnostic['exceptions']) >= 2
    else:
        assert invoke()['state']=='RESTORED_PREVIOUS_SERVICES'
        assert (target/'completed.json').exists()
    assert (audit/'intent.json').read_bytes()==raw and not (audit/'completed.json').exists()
    with pytest.raises(Exception):invoke()


@pytest.mark.parametrize('change',['completed','existing_child','intent','sha','accept'])
def test_continuation_admission_rejects_drift_before_action(tmp_path,monkeypatch,change):
    m,core,base,source,bootstrap,underlying,args,audit,calls,raw=harness(tmp_path,monkeypatch)
    if change=='completed':(audit/'completed.json').write_text('{}')
    elif change=='existing_child':(audit/m.CONTINUATION).mkdir()
    elif change=='intent':(audit/'intent.json').write_text('{}')
    elif change=='sha':args.sha=m.PRIOR_RECOVERY
    elif change=='accept':args.accept_20261023_continuation=False
    with pytest.raises(Exception):m.run_continuation(base,source,core,bootstrap,underlying,args)
    assert not calls


def test_entry_rejected_before_helper_execution(monkeypatch):
    m=module()
    monkeypatch.setattr(m.importlib.util,'spec_from_file_location',lambda *a:pytest.fail('helper executed before admission'))
    with pytest.raises(RuntimeError):m.main()


def test_helper_identity_excludes_read_only_atime():
    m=module()
    assert "st_atime" not in m.IDENTITY_FIELDS and "st_atime_ns" not in m.IDENTITY_FIELDS
    assert "st_ctime_ns" in m.IDENTITY_FIELDS and "st_mtime_ns" in m.IDENTITY_FIELDS
