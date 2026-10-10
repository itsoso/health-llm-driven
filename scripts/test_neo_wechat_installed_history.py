"""Actual synthetic filesystem admission checks; no production or credential I/O."""
import copy
import json
import os
from pathlib import Path
import tempfile

import pytest

from scripts import neo_wechat_installed_history as installed
from scripts import neo_wechat_lifecycle_history as history
from scripts.test_neo_wechat_lifecycle_history import (
    context, dormant, observation, provision_context, provision_history,
)


def write(path,value):
    path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
    path.chmod(0o600)


def mkdir(path):
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


@pytest.fixture
def owned_tmp():
    # /tmp is a shared writable ancestor on Linux. Exercise the same strict
    # production traversal policy using a private workspace fixture instead.
    workspace=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='.neo-installed-test-',dir=workspace) as path:
        root=Path(path)
        root.chmod(0o700)
        yield root


@pytest.fixture
def tree(owned_tmp):
    state=mkdir(owned_tmp/'state')
    lease=mkdir(owned_tmp/'lease')
    for name in ('token','label','stage','started_at'):
        (lease/name).write_text('public-synthetic-lease-metadata\n')
        (lease/name).chmod(0o600)
    lease_identity=[[lease.stat().st_dev,lease.stat().st_ino],
                    [(lease/'token').stat().st_dev,(lease/'token').stat().st_ino]]
    old=mkdir(state/'neo-wechat')
    original=dormant()
    audit=mkdir(old/original['operation_id'])
    before={key:original[key] for key in ('publisher_sha','production_sha','operation_id')}
    original['evidence_sha256']=history.digest(before)
    values={'before':before,'completed':original,'verified':original,
        'intent':dict(state='INSTALL_STARTED',evidence_sha256=original['evidence_sha256'],
                      operation_id=original['operation_id'],publisher_sha=original['publisher_sha']),
        'lease':{'identity':[[1,2],[1,3]]}}
    for name,value in values.items():write(audit/(name+'.json'),value)
    yield state,lease,lease_identity,original


def populate(tree,kind='activate',count=None):
    state,lease,identity,original=tree
    root=mkdir(state/'neo-wechat-lifecycle')
    namespace=mkdir(root/'runtime-lifecycle-v1')
    ctx=context(kind)
    ctx['lease_identity']=identity
    ctx['dormant_receipt_sha256']=history.digest(original)
    ctx['expected_bindings']['dormant_receipt_sha256']=history.digest(original)
    op=mkdir(namespace/ctx['operation_id'])
    write(op/'context.json',ctx);write(op/'original-dormant.json',original)
    rows=[]
    seen=observation(ctx)
    for step in history.STEPS[kind]:
        rows.append(history.make_record(ctx,rows,'intent',step))
        rows.append(history.make_record(ctx,rows,'verified',step,seen))
    rows.append(history.make_record(ctx,rows,'completed','complete',seen))
    for row in rows if count is None else rows[:count]:
        index=row['sequence']
        write(op/f'{index:03d}-{row["phase"]}.json',row)
        if row['phase']=='verified':write(op/f'{index:03d}-evidence.json',seen)
    return op,ctx,rows


def inspect(tree):
    state,lease,_,_=tree
    return installed.inspect_installed_history(state,owner_uid=os.getuid(),lease_path=lease)


def test_absent_namespace_reports_no_history_not_operation_success(tree):
    state,lease,_,_=tree
    result=installed.assert_installed_history(state,owner_uid=os.getuid(),lease_path=lease)
    assert result['state']=='NO_LIFECYCLE_HISTORY'
    assert result['authority']=='none' and result['executable_actions']==[]
    assert 'success' not in str(result).lower()


@pytest.mark.parametrize('kind',['activate','stop'])
def test_complete_history_with_original_live_lease_still_blocks_without_closure_authority(tree,kind):
    op,ctx,rows=populate(tree,kind)
    result=inspect(tree)
    assert result['state']=='RETAIN_UNCERTAIN'
    assert result['operations'][0]['history_state']=='complete'
    assert result['operations'][0]['lease_state']=='original_present'
    assert result['operations'][0]['operation_id']==ctx['operation_id']
    before={p.name:p.read_bytes() for p in op.iterdir()}
    with pytest.raises(installed.InstalledHistoryError,match='^neo_wechat_lifecycle_history_blocked$'):
        installed.assert_installed_history(tree[0],owner_uid=os.getuid(),lease_path=tree[1])
    assert before=={p.name:p.read_bytes() for p in op.iterdir()}


def test_each_interruption_prefix_blocks_including_empty_history(tree):
    op,ctx,rows=populate(tree,count=1)
    result=inspect(tree)
    assert result['operations'][0]['history_state']=='incomplete'
    assert result['operations'][0]['record_count']==1
    assert result['state']=='RETAIN_UNCERTAIN'


@pytest.mark.parametrize('kind',['candidate','unknown','hardlink','symlink','dir_symlink','mode','owner','reordered','evidence','orphan'])
def test_bad_inventory_or_metadata_is_never_admitted(tree,kind,monkeypatch):
    op,ctx,rows=populate(tree)
    first=op/'001-intent.json'
    if kind=='candidate':write(op/'final-guard.json',{'fsync_confirmed':True,'final_guard_confirmed':True})
    if kind=='unknown':write(op/'unrecognized.json',{})
    if kind=='hardlink':os.link(first,op/'hardlink.json')
    if kind=='symlink':
        first.unlink();first.symlink_to(op/'context.json')
    if kind=='dir_symlink':
        namespace=op.parent;namespace.rename(namespace.with_name('foreign'))
        namespace.symlink_to(namespace.with_name('foreign'),target_is_directory=True)
    if kind=='mode':first.chmod(0o644)
    if kind=='owner':
        real=os.fstat
        def changed(fd):
            value=real(fd)
            if value.st_ino==first.stat().st_ino:
                data=list(value);data[4]=value.st_uid+1
                return os.stat_result(data)
            return value
        monkeypatch.setattr(installed.os,'fstat',changed)
    if kind=='reordered':
        value=json.loads(first.read_text());value['sequence']=2;write(first,value)
    if kind=='evidence':
        path=op/'002-evidence.json';value=json.loads(path.read_text());value['readiness']='unknown';write(path,value)
    if kind=='orphan':write(op/'099-evidence.json',observation(ctx))
    result=inspect(tree)
    assert result['state']=='RETAIN_UNCERTAIN' and result['reason']=='invalid_or_unknown_history'
    assert result['executable_actions']==[]


@pytest.mark.parametrize('fault',['missing','replaced','partial','token_hardlink','unproven'])
def test_live_original_lease_loss_replacement_or_partial_never_recreated(tree,fault):
    populate(tree)
    state,lease,_,_=tree
    options={'owner_uid':os.getuid(),'lease_path':lease}
    if fault=='missing':
        for p in lease.iterdir():p.unlink()
        lease.rmdir()
    if fault=='replaced':
        lease.rename(lease.with_name('original-retained'))
        mkdir(lease)
        for name in ('token','label','stage','started_at'):
            (lease/name).write_text('public replacement');(lease/name).chmod(0o600)
    if fault=='partial':(lease/'stage').unlink()
    if fault=='token_hardlink':os.link(lease/'token',lease/'extra')
    if fault=='unproven':options['lease_path']=None
    result=installed.inspect_installed_history(state,**options)
    assert result['state']=='RETAIN_UNCERTAIN'
    assert result['operations'][0]['lease_state']!='original_present'
    if fault=='missing':assert not lease.exists()


def test_history_persists_block_when_lease_disappears_simulating_reboot(tree):
    populate(tree)
    _,lease,_,_=tree
    for child in lease.iterdir():child.unlink()
    lease.rmdir()
    assert inspect(tree)['state']=='RETAIN_UNCERTAIN'
    with pytest.raises(installed.InstalledHistoryError):
        installed.assert_installed_history(tree[0],owner_uid=os.getuid(),lease_path=lease)


def test_unknown_namespace_and_empty_namespace_both_block(tree):
    state,_,_,_=tree
    root=mkdir(state/'neo-wechat-lifecycle')
    assert inspect(tree)['state']=='RETAIN_UNCERTAIN'
    mkdir(root/'unexpected')
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_original_dormant_receipt_mismatch_blocks(tree):
    op,ctx,_=populate(tree)
    value=json.loads((op/'original-dormant.json').read_text())
    value['publisher_sha']='0'*40
    write(op/'original-dormant.json',value)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_metadata_read_is_bounded_and_duplicate_keys_rejected(tree):
    op,_,_=populate(tree)
    path=op/'context.json'
    raw=path.read_bytes();path.write_bytes(raw.replace(b'"version":1',b'"version":1,"version":1'))
    assert inspect(tree)['reason']=='invalid_or_unknown_history'
    path.write_bytes(b'x'*65537)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_relative_and_symlink_state_paths_block(tree):
    state,lease,_,_=tree
    for path in (Path('relative'),state.parent/'linked'):
        if path.name=='linked':path.symlink_to(state,target_is_directory=True)
        result=installed.inspect_installed_history(path,owner_uid=os.getuid(),lease_path=lease)
        assert result['state']=='RETAIN_UNCERTAIN'


def populate_provision(tree,count=None):
    state,lease,identity,original=tree
    root=mkdir(state/'neo-wechat-lifecycle')
    namespace=mkdir(root/'provision-v1')
    ctx=provision_context();ctx['lease_identity']=identity
    ctx['dormant_receipt_sha256']=history.digest(original)
    op=mkdir(namespace/ctx['operation_id'])
    write(op/'context.json',ctx);write(op/'original-dormant.json',original)
    rows=provision_history();previous=ctx['dormant_receipt_sha256']
    for row in rows:
        row['dormant_receipt_sha256']=ctx['dormant_receipt_sha256']
        row['previous_record_sha256']=previous
        previous=history.provision_record_digest(row)
    for row in rows if count is None else rows[:count]:
        write(op/f'{row["sequence"]:03d}-{row["phase"]}.json',row)
    return op,ctx,rows


@pytest.mark.parametrize('count',[0,1,3,9,10])
def test_provision_filesystem_history_never_authorizes_activation_or_release(tree,count):
    op,ctx,rows=populate_provision(tree,count)
    result=inspect(tree)
    assert result['state']=='RETAIN_UNCERTAIN'
    assert result['operations'][0]['record_count']==count
    assert result['operations'][0]['history_state']==('complete' if count==10 else 'incomplete')
    with pytest.raises(installed.InstalledHistoryError):
        installed.assert_installed_history(tree[0],owner_uid=os.getuid(),lease_path=tree[1])


def test_known_metadata_hardlink_rejected(tree):
    op,_,_=populate(tree)
    outside=tree[0].parent/'retained-context.json'
    os.link(op/'context.json',outside)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'
    assert outside.exists()


def test_replaced_operation_directory_detected_after_descriptor_read(tree,monkeypatch):
    op,_,_=populate(tree)
    original=history.validate_history;changed=[False]
    def replacing(ctx,rows):
        result=original(ctx,rows)
        if not changed[0]:
            changed[0]=True
            op.rename(tree[0].parent/'retained-operation')
            mkdir(op)
        return result
    monkeypatch.setattr(installed.history,'validate_history',replacing)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'
    assert (tree[0].parent/'retained-operation').is_dir()


def test_no_lease_contents_or_unknown_files_are_read(tree,monkeypatch):
    populate(tree)
    _,lease,_,_=tree
    identities={(p.stat().st_dev,p.stat().st_ino) for p in lease.iterdir()}
    original=os.read
    def guarded(fd,size):
        st=os.fstat(fd)
        assert (st.st_dev,st.st_ino) not in identities,'lease contents must never be read'
        return original(fd,size)
    monkeypatch.setattr(installed.os,'read',guarded)
    assert inspect(tree)['operations'][0]['lease_state']=='original_present'


def test_root_identity_replacement_during_inspection_fails_closed(tree,monkeypatch):
    op,_,_=populate(tree)
    root=op.parent.parent
    original=installed._Tree.verify;changed=[False]
    def replacing(self):
        # Lease tree verifies first; mutate only the history tree holding files.
        if len(self.files)>5 and not changed[0]:
            changed[0]=True
            root.rename(root.parent/'retained-lifecycle')
            mkdir(root)
        return original(self)
    monkeypatch.setattr(installed._Tree,'verify',replacing)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_original_dormant_audit_unknown_file_blocks_but_is_not_modified(tree):
    populate(tree)
    state,_,_,original=tree
    old=state/'neo-wechat'/original['operation_id']
    write(old/'unknown.json',{'metadata':'synthetic'})
    before={p.name:p.read_bytes() for p in old.iterdir()}
    assert inspect(tree)['reason']=='invalid_or_unknown_history'
    assert before=={p.name:p.read_bytes() for p in old.iterdir()}


def test_missing_state_is_not_treated_as_absent_lifecycle(owned_tmp):
    result=installed.inspect_installed_history(owned_tmp/'missing',owner_uid=os.getuid())
    assert result['state']=='RETAIN_UNCERTAIN'


def test_missing_context_and_orphan_evidence_from_interrupted_write_block(tree):
    op,ctx,_=populate(tree,count=1)
    write(op/'002-evidence.json',observation(ctx))
    assert inspect(tree)['reason']=='invalid_or_unknown_history'
    (op/'002-evidence.json').unlink();(op/'context.json').unlink()
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_no_callback_or_success_flag_bypass_is_exposed(tree):
    import inspect as introspection
    params=set(introspection.signature(installed.assert_installed_history).parameters)
    assert params=={'state','owner_uid','lease_path'}
    assert not hasattr(installed,'main') and not hasattr(installed,'write')


def test_file_permission_drift_during_read_is_detected(tree,monkeypatch):
    op,_,_=populate(tree)
    target=op/'context.json';target_identity=(target.stat().st_dev,target.stat().st_ino)
    actual_read=os.read;changed=[False]
    def drift(fd,size):
        raw=actual_read(fd,size)
        st=os.fstat(fd)
        if not changed[0] and (st.st_dev,st.st_ino)==target_identity:
            changed[0]=True;target.chmod(0o644)
        return raw
    monkeypatch.setattr(installed.os,'read',drift)
    assert inspect(tree)['reason']=='invalid_or_unknown_history'


def test_fixture_uses_owned_workspace_not_shared_system_temp(tree):
    state,_,_,_=tree
    workspace=Path(__file__).resolve().parents[1]
    assert workspace in state.parents


def test_root_and_synthetic_policy_both_reject_shared_sticky_ancestor():
    import stat
    from types import SimpleNamespace
    shared=SimpleNamespace(st_mode=stat.S_IFDIR|0o1777,st_uid=0)
    for owner_uid in (0,12345):
        with pytest.raises(installed.InstalledHistoryError):
            installed._directory_metadata(shared,owner_uid,ancestor=True)
