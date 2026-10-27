import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def module():
 spec=importlib.util.spec_from_file_location('exam_lease_test',ROOT/'scripts/exam_recovery_lease.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Adapter:
 def __init__(self):self.events=[];self.consumed=False;self.fail=None
 def inspection(self):
  self.events.append('inspect')
  if self.fail=='inspect':raise RuntimeError('unhealthy')
  return {'state':'RECOVERED_CANDIDATE','lease':'exact-original','terminal':'finalized'}
 def consume(self,evidence,fingerprint):
  if self.consumed:raise RuntimeError('already consumed')
  self.consumed=True;self.events.append('intent')
 def remove(self,evidence):
  self.events.append('remove')
  if self.fail=='remove':raise RuntimeError('partial')
 def after_removal(self):self.events.append('prove_absent');return {'absent':True}
 def complete(self,result):self.events.append('completed')
def test_inspection_is_read_only_and_retirement_is_ordered_once():
 m=module();a=Adapter();proof=m.retire(a);assert a.events==['inspect']
 a.events=[];r=m.retire(a,proof['evidence_sha256']);assert r['state']=='EXAM_RECOVERY_LEASE_RETIRED';assert a.events==['inspect','intent','inspect','remove','prove_absent','completed']
 with pytest.raises(RuntimeError):m.retire(a,proof['evidence_sha256'])
def test_digest_drift_and_unhealthy_never_consume():
 m=module();a=Adapter()
 with pytest.raises(m.LeaseBlocked):m.retire(a,'a'*64)
 assert not a.consumed
 a.fail='inspect'
 with pytest.raises(RuntimeError):m.retire(a)
 assert not a.consumed
def test_partial_unlink_never_replays_or_completes():
 m=module();a=Adapter();proof=m.retire(a);a.fail='remove'
 with pytest.raises(RuntimeError):m.retire(a,proof['evidence_sha256'])
 assert a.consumed and 'completed' not in a.events
 with pytest.raises(RuntimeError,match='already consumed'):m.retire(a,proof['evidence_sha256'])

import hashlib,json,os,stat
from types import SimpleNamespace

def file_proof(path,mode):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=mode:raise RuntimeError('file metadata')
 return path.read_bytes(),{'dev':s.st_dev,'ino':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def directory_proof(path):
 s=path.lstat()
 if not stat.S_ISDIR(s.st_mode):raise RuntimeError('not directory')
 return {'dev':s.st_dev,'ino':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode)}
def lease(tmp_path,m):
 p=tmp_path/'lease';p.mkdir(mode=0o700)
 for name in m.NAMES:(p/name).write_text(name);(p/name).chmod(0o600)
 return p,{'lease':directory_proof(p),**{n:file_proof(p/n,0o600)[1] for n in m.NAMES}}
def test_exact_lease_removal_leaves_unrelated_evidence(tmp_path):
 m=module();p,expected=lease(tmp_path,m);other=tmp_path/'failure.json';other.write_text('NEEDS_OPERATOR')
 m.remove_exact_lease(p,expected,file_proof,directory_proof)
 assert not p.exists() and other.read_text()=='NEEDS_OPERATOR'
@pytest.mark.parametrize('change',['bytes','replace','extra','symlink'])
def test_changed_lease_blocks_before_deleting_anything(tmp_path,change):
 m=module();p,expected=lease(tmp_path,m)
 if change=='bytes':(p/'token').write_text('different')
 if change=='replace':
  fresh=tmp_path/'fresh';fresh.write_text('token');fresh.chmod(0o600);fresh.replace(p/'token')
 if change=='extra':(p/'extra').write_text('extra')
 if change=='symlink':
  (p/'token').unlink();(p/'token').symlink_to(tmp_path/'missing')
 with pytest.raises((m.LeaseBlocked,RuntimeError)):m.remove_exact_lease(p,expected,file_proof,directory_proof)
 assert (p/'started_at').exists() and (p/'label').exists()
def test_partial_removal_cannot_run_again(tmp_path,monkeypatch):
 m=module();p,expected=lease(tmp_path,m);unlink=m.os.unlink
 def interrupted(name,**kwargs):
  if name=='label':raise OSError('synthetic IO failure')
  return unlink(name,**kwargs)
 monkeypatch.setattr(m.os,'unlink',interrupted)
 with pytest.raises(OSError):m.remove_exact_lease(p,expected,file_proof,directory_proof)
 monkeypatch.setattr(m.os,'unlink',unlink)
 with pytest.raises(m.LeaseBlocked):m.remove_exact_lease(p,expected,file_proof,directory_proof)
 assert not (p/'token').exists() and (p/'label').exists()

def success_adapter(tmp_path,m):
 audit=tmp_path/'audit';audit.mkdir()
 r=SimpleNamespace(audit=audit,sha='c'*40,proof=SimpleNamespace(_directory=directory_proof,_file=file_proof))
 a=m.ProductionAdapter(r,SimpleNamespace(OLD_SHA='d'*40))
 evidence={'admission':{'publisher_sha':r.sha,'failed_sha':m.FAILED_SHA,'old_sha':'d'*40}}
 intent={'publisher_sha':r.sha,'evidence_sha256':m.digest(evidence),'evidence':evidence}
 completed={'state':'RECOVERED_CANDIDATE','evidence_sha256':m.digest(evidence)}
 for name,value in [('intent.json',intent),('completed.json',completed)]:
  (audit/name).write_text(json.dumps(value));(audit/name).chmod(0o600)
 return a,intent,completed
@pytest.mark.parametrize('change',['failed','missing','digest','publisher','old','extra'])
def test_only_exact_successful_recovery_admits_retirement(tmp_path,change):
 m=module();a,i,c=success_adapter(tmp_path,m)
 a.read_success()
 if change=='failed':c['state']='NEEDS_OPERATOR'
 if change=='missing':(a.r.audit/'completed.json').unlink()
 if change=='digest':c['evidence_sha256']='f'*64
 if change=='publisher':i['publisher_sha']='f'*40
 if change=='old':
  i['evidence']['admission']['old_sha']='f'*40;i['evidence_sha256']=m.digest(i['evidence']);c['evidence_sha256']=i['evidence_sha256']
 if change=='extra':(a.r.audit/'failed.json').write_text('{}')
 if change!='missing':(a.r.audit/'completed.json').write_text(json.dumps(c))
 (a.r.audit/'intent.json').write_text(json.dumps(i))
 with pytest.raises(m.LeaseBlocked):a.read_success()

def test_post_intent_health_or_evidence_change_never_removes():
 m=module();a=Adapter();expected=m.retire(a)['evidence_sha256'];original=a.inspection
 def changed():
  value=original()
  return {**value,'terminal':'changed'} if a.consumed else value
 a.inspection=changed
 with pytest.raises(m.LeaseBlocked,match='after retirement intent'):m.retire(a,expected)
 assert a.consumed and 'remove' not in a.events and 'completed' not in a.events
