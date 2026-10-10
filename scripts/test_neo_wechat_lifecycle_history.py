"""Synthetic strict history/readback tests; never execute host lifecycle actions."""
import copy
import json

import pytest

from scripts import neo_wechat_lifecycle_history as h


def context(kind='activate'):
    return dict(version=1,namespace='runtime-lifecycle-v1',operation_id='a'*32,kind=kind,
        install_operation_id='b'*32,provisioning_operation_id='c'*32,
        dormant_receipt_sha256='d'*64,provisioning_receipt_sha256='e'*64,
        runtime_sha256='f'*64,publisher_sha='1'*40,production_sha='2'*40,
        lease_operation_id='a'*32,lease_identity=[[1,2],[1,3]],
        expected_bindings=dict(dormant_receipt_sha256='d'*64,provisioning_receipt_sha256='e'*64,
            runtime_sha256='f'*64,service_unit_sha256='3'*64,socket_unit_sha256='4'*64,
            config_sha256='5'*64,proxy_receipt_sha256='6'*64),
        expected_preserved=dict(health_services_sha256='7'*64,keys_identity_sha256='8'*64,
            data_directory_identity_sha256='9'*64,audit_root_identity_sha256='0'*64,
            accounts_groups_sha256='a'*64))


def observation(ctx=None):
    ctx = ctx or context()
    active = ctx['kind'] == 'activate'
    return dict(version=1,bindings=copy.deepcopy(ctx['expected_bindings']),
        preserved=copy.deepcopy(ctx['expected_preserved']),
        units={name:dict(state='active' if active else 'inactive',unit_file_state='static',dropins=[])
               for name in ('neo-wechat.service','neo-wechat.socket')},
        proxy=dict(entry='recorded' if active else 'absent',loaded='recorded' if active else 'absent',validated=True),
        socket_path='recorded' if active else 'absent',readiness='ready' if active else 'stopped',
        lease=dict(operation_id=ctx['operation_id'],identity=copy.deepcopy(ctx['lease_identity'])))


def history(ctx=None):
    ctx = ctx or context()
    rows=[]
    for step in h.STEPS[ctx['kind']]:
        rows.append(h.make_record(ctx,rows,'intent',step))
        rows.append(h.make_record(ctx,rows,'verified',step,observation(ctx)))
    rows.append(h.make_record(ctx,rows,'completed','complete',observation(ctx)))
    return rows


def provenance(ctx,rows,**changes):
    value=dict(version=1,original_provenance='authenticated',context_sha256=h.digest(ctx),
        lease_operation_id=ctx['operation_id'],lease_identity=copy.deepcopy(ctx['lease_identity']),
        completion=dict(record_sha256=h.digest(rows[-1]),fsync_confirmed=True,final_guard_confirmed=True))
    value.update(changes)
    return value


@pytest.mark.parametrize('kind',['activate','stop'])
def test_complete_authenticated_original_history_only_reports_completion_without_authority(kind):
    ctx=context(kind); rows=history(ctx); seen=observation(ctx);proof=provenance(ctx,rows)
    calls=[]
    def auth(value):
        calls.append('authenticate')
        assert value == ctx
        return proof
    def read(value):
        calls.append('readback')
        return seen
    result=h.inspect_recovery(ctx,rows,authenticate=auth,readback=read)
    assert result['classification']=='CONFIRMED_ORIGINAL_COMPLETION'
    assert result['authority']=='none' and result['executable_actions']==[]
    assert calls==['authenticate','readback','authenticate']


def test_all_interrupted_prefixes_remain_uncertain_even_if_host_looks_complete():
    ctx=context();rows=history(ctx)
    for prefix in (rows[:n] for n in range(len(rows))):
        result=h.inspect_recovery(ctx,prefix,authenticate=lambda _:provenance(ctx,rows),readback=lambda _:observation(ctx))
        assert result['classification']=='RETAIN_UNCERTAIN'
        assert result['executable_actions']==[]


@pytest.mark.parametrize('change',[
    lambda r:r[0].update(operation_id='0'*32),
    lambda r:r[0].update(context_sha256='0'*64),
    lambda r:r[0].update(runtime_sha256='0'*64),
    lambda r:r[0].update(publisher_sha='0'*40),
    lambda r:r[0].update(namespace='dormant-install'),
    lambda r:r[0].update(kind='stop'),
    lambda r:r[0].update(version=True),
    lambda r:r[0].update(sequence=True),
    lambda r:r[0].update(phase='verified'),
    lambda r:r[0].update(step='run_shell'),
    lambda r:r[0].update(evidence_sha256='0'*64),
    lambda r:r[1].update(evidence_sha256=None),
    lambda r:r[1].update(previous_record_sha256='0'*64),
    lambda r:r.reverse(),lambda r:r.pop(2),lambda r:r.append(copy.deepcopy(r[-1])),
])
def test_tampered_foreign_reordered_unknown_history_rejected(change):
    ctx=context();rows=history(ctx);change(rows)
    with pytest.raises(h.HistoryError,match='^lifecycle_history_rejected$'):
        h.validate_history(ctx,rows)


@pytest.mark.parametrize('mutator',[
    lambda p:p.update(original_provenance='unproven'),
    lambda p:p.update(context_sha256='0'*64),lambda p:p.update(completion=None),
    lambda p:p['completion'].update(fsync_confirmed=False),
    lambda p:p['completion'].update(final_guard_confirmed=False),
    lambda p:p['completion'].update(record_sha256='0'*64),
    lambda p:p.update(lease_operation_id='0'*32),lambda p:p.update(lease_identity=[[1,7],[1,8]]),
])
def test_visible_completion_is_not_durability_or_authority(mutator):
    ctx=context();rows=history(ctx);proof=provenance(ctx,rows);mutator(proof)
    assert h.inspect_recovery(ctx,rows,authenticate=lambda _:proof,readback=lambda _:observation(ctx))['classification']=='RETAIN_UNCERTAIN'


@pytest.mark.parametrize('mutator',[
    lambda o:o.pop('lease'), lambda o:o.update(lease=None),
    lambda o:o['lease'].update(identity=[[1,7],[1,8]]),
    lambda o:o['lease'].update(operation_id='0'*32),
    lambda o:o['units']['neo-wechat.service'].update(state='inactive'),
    lambda o:o['units']['neo-wechat.service'].update(dropins=['unknown']),
    lambda o:o['proxy'].update(loaded='absent'),lambda o:o.update(readiness='unknown'),
    lambda o:o['preserved'].update(health_services_sha256='0'*64),
    lambda o:o['bindings'].update(runtime_sha256='0'*64),
    lambda o:o.update(untrusted_secret='synthetic-sensitive'),
])
def test_inexact_missing_or_replaced_live_state_has_no_actions(mutator):
    ctx=context();rows=history(ctx);seen=observation(ctx);mutator(seen)
    result=h.inspect_recovery(ctx,rows,authenticate=lambda _:provenance(ctx,rows),readback=lambda _:seen)
    assert result['classification']=='RETAIN_UNCERTAIN'
    assert result['executable_actions']==[] and 'synthetic-sensitive' not in str(result)


def test_final_guard_or_readback_exception_is_sanitized():
    ctx=context();rows=history(ctx);n=[0]
    def auth(_):
        n[0]+=1
        if n[0]==2: raise RuntimeError('synthetic-sensitive')
        return provenance(ctx,rows)
    result=h.inspect_recovery(ctx,rows,authenticate=auth,readback=lambda _:observation(ctx))
    assert result['classification']=='RETAIN_UNCERTAIN' and 'synthetic-sensitive' not in str(result)


def test_history_and_context_are_detached_and_bounded():
    ctx=context();rows=history(ctx);validated=h.validate_history(ctx,rows)
    rows[0]['kind']='foreign'
    assert validated[0]['kind']=='activate'
    for value in (rows*100, [object()], 'bad'):
        with pytest.raises(h.HistoryError):h.validate_history(ctx,value)
    for value in ({'secret':'x'*70000},float('nan'),2**100):
        with pytest.raises(h.HistoryError):h.digest(value)
    cyclic=[];cyclic.append(cyclic)
    with pytest.raises(h.HistoryError):h.digest(cyclic)


def test_raw_history_decode_rejects_duplicates_and_oversize():
    ctx=context();rows=history(ctx)
    raw=b'\n'.join(json.dumps(r).encode() for r in rows)+b'\n'
    assert h.decode_history(ctx,raw)==rows
    duplicate=raw.replace(b'"version": 1',b'"version": 1, "version": 1',1)
    with pytest.raises(h.HistoryError):h.decode_history(ctx,duplicate)
    with pytest.raises(h.HistoryError):h.decode_history(ctx,b'x'*131073)


def dormant():
    return dict(state='INSTALLED_DORMANT',publisher_sha='9'*40,production_sha='2'*40,
        operation_id='b'*32,evidence_sha256='8'*64,runtime_sha256='f'*64,proxy_gid=1234,
        activated=False,nginx_included=False,health_services_unchanged=True,secrets_created=False)


def provision_context():
    return dict(version=1,namespace='provision-v1',operation_id='a'*32,install_operation_id='b'*32,
        dormant_receipt_sha256=h.digest(dormant()),publisher_sha='1'*40,runtime_sha256='f'*64,
        production_sha='2'*40,lease_operation_id='a'*32,lease_identity=[[1,2],[1,3]],
        config_identity=[1,4],audit_root_identity=[1,5],owner_uid=0,audit_gid=0,bridge_gid=1234)


def provision_history():
    ctx=provision_context();previous=ctx['dormant_receipt_sha256'];rows=[]
    protocol=[('intent',None)]+[(phase,name) for name in h.PROVISION_FILES for phase in ('intent','verified')]+[('completed',None)]
    for index,(phase,name) in enumerate(protocol):
        row=dict(version=1,kind='provision',phase=phase,sequence=index,operation_id=ctx['operation_id'],
            dormant_receipt_sha256=ctx['dormant_receipt_sha256'],publisher_sha=ctx['publisher_sha'],previous_record_sha256=previous)
        if name:row['filename']=name
        if phase=='verified':
            row['file_identity']=dict(dev=1,ino=index+10,uid=0,gid=1234 if name=='config.json' else 0,
                mode=0o100640 if name=='config.json' else 0o100600,nlink=1,size=64,mtime_ns=100,ctime_ns=100)
        if phase=='completed':row.update(state='PROVISIONED_DORMANT',activation_authorized=False)
        rows.append(row);previous=h.provision_record_digest(row)
    return rows


def provision_observation(ctx,rows):
    value={key:copy.deepcopy(ctx[key]) for key in ('version','namespace','operation_id','install_operation_id',
        'dormant_receipt_sha256','publisher_sha','runtime_sha256','production_sha','config_identity','audit_root_identity')}
    value.update(lease={'operation_id':ctx['operation_id'],'identity':ctx['lease_identity']},
        files={r['filename']:copy.deepcopy(r['file_identity']) for r in rows if r['phase']=='verified'},
        bridge='inactive_static',proxy='unpublished',health_services_unchanged=True)
    return value


def test_existing_provision_schema_validated_but_no_completion_authority():
    ctx=provision_context();rows=provision_history()
    assert h.validate_provision_history(ctx,dormant(),rows)==rows
    assert h.inspect_provision_recovery(ctx,dormant(),rows)['classification']=='RETAIN_UNCERTAIN'
    proof=provenance(ctx,rows)
    proof['completion']['record_sha256']=h.provision_record_digest(rows[-1])
    result=h.inspect_provision_recovery(ctx,dormant(),rows,authenticate=lambda _:proof,
        readback=lambda _:provision_observation(ctx,rows))
    assert result['classification']=='CONFIRMED_ORIGINAL_COMPLETION'
    assert result['executable_actions']==[]


def test_all_provision_interrupted_prefixes_remain_uncertain():
    ctx=provision_context();rows=provision_history()
    for n in range(len(rows)):
        assert h.validate_provision_history(ctx,dormant(),rows[:n])==rows[:n]
        assert h.inspect_provision_recovery(ctx,dormant(),rows[:n])['classification']=='RETAIN_UNCERTAIN'


@pytest.mark.parametrize('change',[
    lambda r:r[0].update(operation_id='0'*32),lambda r:r[0].update(version=True),
    lambda r:r[0].update(sequence=True),lambda r:r[1].update(filename='other-secret'),
    lambda r:r[2]['file_identity'].update(nlink=2),lambda r:r[2]['file_identity'].update(mode=0o100644),
    lambda r:r[2]['file_identity'].update(uid=999),lambda r:r[2]['file_identity'].update(size=8193),
    lambda r:r[-1].update(activation_authorized=True),lambda r:r[-1].update(state='ACTIVE'),
    lambda r:r.reverse(),lambda r:r.pop(1),lambda r:r[2].update(unexpected='synthetic-sensitive')])
def test_provision_foreign_reordered_tampered_metadata_rejected(change):
    rows=provision_history();change(rows)
    with pytest.raises(h.HistoryError):h.validate_provision_history(provision_context(),dormant(),rows)


@pytest.mark.parametrize('change',[
    lambda c:c.update(version=True),lambda c:c.update(kind=[]),
    lambda c:c.update(operation_id='b'*32,lease_operation_id='b'*32),
    lambda c:c.update(lease_identity=[[True,2],[1,3]]),
    lambda c:c.update(unexpected='synthetic-sensitive'),lambda c:c.update(publisher_sha='x'*70000),
])
def test_malformed_context_rejected_with_constant_code(change):
    ctx=context();change(ctx)
    with pytest.raises(h.HistoryError,match='^lifecycle_history_rejected$'):h.validate_context(ctx)


@pytest.mark.parametrize('fault',['lease_missing','lease_replaced','files_partial','file_replaced','fsync_uncertain','guard_uncertain'])
def test_provision_recovery_retains_uncertain_lease_partial_or_durability(fault):
    ctx=provision_context();rows=provision_history();seen=provision_observation(ctx,rows)
    proof=provenance(ctx,rows);proof['completion']['record_sha256']=h.provision_record_digest(rows[-1])
    if fault=='lease_missing':seen['lease']=None
    if fault=='lease_replaced':seen['lease']['identity']=[[1,7],[1,8]]
    if fault=='files_partial':seen['files'].pop('encryption_key')
    if fault=='file_replaced':seen['files']['encryption_key']['ino']+=100
    if fault=='fsync_uncertain':proof['completion']['fsync_confirmed']=False
    if fault=='guard_uncertain':proof['completion']['final_guard_confirmed']=False
    result=h.inspect_provision_recovery(ctx,dormant(),rows,authenticate=lambda _:proof,readback=lambda _:seen)
    assert result['classification']=='RETAIN_UNCERTAIN' and result['executable_actions']==[]


def test_actual_synthetic_provision_writer_output_matches_history(tmp_path):
    import base64
    import os
    from scripts.neo_wechat_provisioning import prepare
    from scripts.neo_wechat_provision_transaction import provision
    config=tmp_path/'config';audit=tmp_path/'lifecycle'
    config.mkdir(mode=0o710);audit.mkdir(mode=0o700)
    config.chmod(0o710);audit.chmod(0o700)
    config_fd=os.open(config,os.O_RDONLY|os.O_DIRECTORY)
    audit_fd=os.open(audit,os.O_RDONLY|os.O_DIRECTORY)
    def identity(fd):
        s=os.fstat(fd)
        return [s.st_dev,s.st_ino]
    ctx=provision_context()
    ctx.update(config_identity=identity(config_fd),audit_root_identity=identity(audit_fd),
        owner_uid=os.getuid(),audit_gid=os.getgid(),bridge_gid=os.getgid())
    package=prepare(config=dict(owner='synthetic-owner',origin='https://health.example',
        client_id='synthetic-client',redirect_uri='https://client.example/callback',
        proxy_gid=1234,health_client_id='synthetic-health'),
        encryption_key=base64.b64encode(bytes(range(32))).decode(),
        password='synthetic-test-password',password_confirmation='synthetic-test-password',
        webhook='https://hooks.slack.com/services/T6TNPEFLY/B123/synthetic-only',
        workspace_confirmation='T6TNPEFLY',channel_confirmation='C0C89QBQLBB')
    try:
        completed=provision(config_fd=config_fd,audit_root_fd=audit_fd,
            config_identity=tuple(ctx['config_identity']),audit_identity=tuple(ctx['audit_root_identity']),
            bundle=package,operation_id=ctx['operation_id'],dormant_receipt_sha256=ctx['dormant_receipt_sha256'],
            publisher_sha=ctx['publisher_sha'],owner_uid=ctx['owner_uid'],audit_gid=ctx['audit_gid'],
            bridge_gid=ctx['bridge_gid'],guard=lambda:None)
        paths=sorted((audit/'provision-v1'/ctx['operation_id']).glob('*.json'))
        # Read metadata history only, never any of the synthetic credential files.
        raw=[p.read_bytes() for p in paths]
        rows=[json.loads(value) for value in raw]
        assert len(rows)==10 and rows[-1]==completed
        assert h.validate_provision_history(ctx,dormant(),rows)==rows
        import hashlib
        assert all(h.provision_record_digest(row)==hashlib.sha256(value).hexdigest()
                   for row,value in zip(rows,raw))
        result=h.inspect_provision_recovery(ctx,dormant(),rows)
        assert result['classification']=='RETAIN_UNCERTAIN'
        assert result['authority']=='none' and result['executable_actions']==[]
    finally:
        os.close(config_fd);os.close(audit_fd)


@pytest.mark.parametrize('value',[{},[],None,True,123])
def test_context_kind_types_fail_with_fixed_error(value):
    ctx=context();ctx['kind']=value
    with pytest.raises(h.HistoryError,match='^lifecycle_history_rejected$'):h.validate_context(ctx)
    with pytest.raises(h.HistoryError,match='^lifecycle_history_rejected$'):h.decode_history(ctx,b'')


def test_trusted_callbacks_cannot_mutate_validated_inputs():
    ctx=context();rows=history(ctx)
    expected=copy.deepcopy(ctx)
    proof=provenance(ctx,rows)
    def authenticate(value):
        value['operation_id']='0'*32
        return proof
    def readback(value):
        value['operation_id']='0'*32
        return observation(expected)
    result=h.inspect_recovery(ctx,rows,authenticate=authenticate,readback=readback)
    assert result['classification']=='CONFIRMED_ORIGINAL_COMPLETION'
    assert ctx==expected


def test_recovery_absent_authentication_does_not_read_host():
    calls=[]
    result=h.inspect_recovery(context(),history(),readback=lambda _:calls.append('read'))
    assert result['classification']=='RETAIN_UNCERTAIN' and calls==[]


@pytest.mark.parametrize('field,value',[
    ('version',False),('sequence',1.0),('kind',{}),('phase',[]),('step',{}),
    ('previous_record_sha256',None),('evidence_sha256',{'secret':'synthetic-sensitive'}),
])
def test_record_invalid_field_types_are_fixed_errors(field,value):
    rows=history();rows[0][field]=value
    with pytest.raises(h.HistoryError,match='^lifecycle_history_rejected$'):
        h.validate_history(context(),rows)


def test_authenticated_provenance_changes_after_readback_is_retained():
    ctx=context();rows=history(ctx);count=[0]
    def authenticate(_):
        count[0]+=1
        proof=provenance(ctx,rows)
        if count[0]==2:proof['lease_identity']=[[1,7],[1,8]]
        return proof
    result=h.inspect_recovery(ctx,rows,authenticate=authenticate,readback=lambda _:observation(ctx))
    assert result['classification']=='RETAIN_UNCERTAIN'
    assert result['preserve_original_lease'] is True


def test_module_has_no_host_or_cli_dispatch_surface():
    import ast
    from pathlib import Path
    tree=ast.parse(Path(h.__file__).read_text())
    imports={alias.name.split('.')[0] for node in ast.walk(tree)
             if isinstance(node,ast.Import) for alias in node.names}
    assert imports <= {'hashlib','json','re','stat'}
    assert not any(isinstance(node,ast.Assert) for node in ast.walk(tree))
    for name in ('main','execute','write','release_lease','cleanup','resume'):
        assert not hasattr(h,name)
