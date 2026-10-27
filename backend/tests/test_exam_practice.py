from datetime import date,datetime,timezone
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.services import exam_practice as service
from app.schemas.exam_practice import ExamAttemptWrite
from app.models.exam_practice import ExamAttemptRecord
from app.models.life_navigation import LifeNavigationWorkspace

@pytest.fixture
def catalog(monkeypatch):
    value={'catalog_version':'test-v1','questions':[
        {'id':qid,'version':1,'subject':subject,'topic':'基础论证','prompt':f'合成题 {qid}',
         'options':['甲','乙','丙','丁'],'answer':1,'explanation':'合成解析：依据题设选择乙。','source':'原创练习','difficulty':'基础'}
        for qid,subject in [('e01','英语'),('e101','英语'),('m101','数学'),('l101','逻辑')]]}
    monkeypatch.setattr(service,'load_catalog',lambda:service.Catalog.model_validate(value))
    monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,16,0,tzinfo=timezone.utc))
    return value

def payload(**kw):
    return ExamAttemptWrite.model_validate({'request_id':str(uuid4()),'question_id':'e101','question_version':1,'choice_index':0,'elapsed_seconds':60,**kw})

def test_practice_has_no_answer_and_get_never_creates_records(db,auth_user_and_headers,catalog):
    user,_=auth_user_and_headers
    result=service.practice(db,user.id,date(2026,10,28)).model_dump(mode='json')
    assert result['today']=='2026-10-28' and result['total_minutes']==120
    assert sum(p['minutes'] for p in result['plan'])==120
    assert all('answer' not in q and 'explanation' not in q for q in result['questions'])
    assert result['queue'] and result['progress']==[]
    assert db.query(ExamAttemptRecord).count()==0
    assert db.query(LifeNavigationWorkspace).count()==0

def test_append_retries_conflicts_and_server_grading(db,auth_user_and_headers,catalog):
    user,_=auth_user_and_headers;p=payload()
    first=service.submit(db,user.id,p)
    assert not first.correct and first.correct_index==1 and first.study_date==date(2026,10,28)
    assert service.submit(db,user.id,p).id==first.id
    with pytest.raises(HTTPException) as err:service.submit(db,user.id,p.model_copy(update={'choice_index':1}))
    assert err.value.status_code==409
    second=service.submit(db,user.id,payload(choice_index=1))
    assert second.id!=first.id and second.correct
    history=service.history(db,user.id,None,0,50)
    assert [r.id for r in history.items]==[second.id,first.id] and history.total==2
    progress=service.practice(db,user.id,date(2026,10,28)).progress[0]
    assert progress.attempt_count==2 and progress.ever_wrong and progress.latest_correct
    assert progress.next_review_date==date(2026,10,29)

def test_strict_payload_cannot_backdate_or_grade_itself():
    for field,value in [('correct',True),('study_date','2020-01-01'),('user_id',2),('elapsed_seconds',-1),('choice_index',True)]:
        with pytest.raises(ValidationError):payload(**{field:value})

def test_snapshot_survives_catalog_update_and_idempotent_retry(db,auth_user_and_headers,catalog):
    user,_=auth_user_and_headers;p=payload();first=service.submit(db,user.id,p)
    catalog['questions'][1].update(version=2,answer=2,explanation='新版解析',prompt='全新题干',options=['丁','丙','乙','甲'])
    assert service.submit(db,user.id,p).model_dump()==first.model_dump()
    assert service.history(db,user.id,None,0,50).items[0].explanation=='合成解析：依据题设选择乙。'
    saved = service.history(db,user.id,None,0,50).items[0]
    assert saved.question.prompt == '合成题 e101'
    assert saved.question.options == ['甲','乙','丙','丁']
    assert saved.question.version == 1
    assert 'answer' not in saved.question.model_dump()
    with pytest.raises(HTTPException) as err:service.submit(db,user.id,payload())
    assert err.value.status_code==409

def test_other_owner_cannot_read_attempts(db,auth_user_and_headers,catalog):
    from app.models.user import User
    user,_=auth_user_and_headers
    other=User(name='synthetic',is_active=True,is_approved=True);db.add(other);db.commit()
    request=payload();first=service.submit(db,user.id,request)
    assert service.history(db,other.id,None,0,50).total==0
    assert service.practice(db,other.id,date(2026,10,28)).progress==[]
    assert service.submit(db,other.id,request).id!=first.id

def test_legacy_first_latest_are_read_only_and_not_invented_intermediate_attempts(db,auth_user_and_headers,catalog):
    from copy import deepcopy
    user,_=auth_user_and_headers;q=service.load_catalog().questions[0];day=date(2026,10,27)
    task={'id':service.legacy_task_id(day,'e01'),'date':str(day),'criterion':q.prompt,
          'result':'作答：A；正确答案：B。\n合成解析：依据题设选择乙。',
          'improvement':'作答：B；正确答案：B。\n合成解析：依据题设选择乙。','status':'done'}
    content={'weeks':{'2026-10-26':{'tasks':[task]}}}
    db.add(LifeNavigationWorkspace(user_id=user.id,revision=1,data=content,history=[],updated_at=service.utcnow()));db.commit()
    before=deepcopy(content)
    history=service.history(db,user.id,None,0,50)
    assert history.total==2 and {a.source for a in history.items}=={'legacy_first','legacy_latest'}
    assert all(a.answered_at is None and a.elapsed_seconds is None for a in history.items)
    progress=service.practice(db,user.id,date(2026,10,28)).progress[0]
    assert progress.ever_wrong and progress.latest_correct and progress.attempt_count==2
    assert db.query(ExamAttemptRecord).count()==0
    assert db.get(LifeNavigationWorkspace,user.id).data==before
    assert service.history(db,user.id,'m101',0,50).total==0
    # Replacing the old workspace does not erase the independent server ledger.
    submitted=service.submit(db,user.id,payload())
    row=db.get(LifeNavigationWorkspace,user.id);row.data={'weeks':{}};db.commit()
    assert [a.id for a in service.history(db,user.id,None,0,50).items]==[submitted.id]

def test_unproven_legacy_text_is_not_invented_as_server_history(db,auth_user_and_headers,catalog):
    user,_=auth_user_and_headers
    tasks=[{'id':str(uuid4()),'date':'2026-10-27','criterion':'合成题 e01','result':'作答：A；正确答案：B。\n合成解析：依据题设选择乙。','improvement':''},
           {'id':service.legacy_task_id(date(2026,10,27),'e01'),'date':'2026-10-27','criterion':'合成题 e01','result':'作答：A；正确答案：A。\n合成解析：依据题设选择乙。','improvement':''}]
    db.add(LifeNavigationWorkspace(user_id=user.id,revision=1,data={'weeks':{'2026-10-26':{'tasks':tasks}}},history=[],updated_at=service.utcnow()));db.commit()
    assert service.history(db,user.id,None,0,50).total==0

def test_review_spacing_counts_distinct_correct_days_and_keeps_queue_bounded(db,auth_user_and_headers,catalog,monkeypatch):
    user,_=auth_user_and_headers
    for day,expected in [(28,date(2026,10,29)),(29,date(2026,11,1)),(30,date(2026,11,6))]:
        monkeypatch.setattr(service,'utcnow',lambda d=day:datetime(2026,10,d,0,tzinfo=timezone.utc))
        service.submit(db,user.id,payload(choice_index=1));service.submit(db,user.id,payload(choice_index=1))
        progress=service.practice(db,user.id,date(2026,10,day)).progress[0]
        assert progress.next_review_date==expected
    queue=service.practice(db,user.id,date(2026,11,6)).queue
    assert 'e101' in queue and len(queue)<=18
    assert service.practice(db,user.id,date(2026,10,27)).progress==[]

def test_queue_is_deterministic_exhaustion_is_honest_and_due_mistakes_first(db,auth_user_and_headers,catalog):
    user,_=auth_user_and_headers
    initial=service.practice(db,user.id,date(2026,10,28))
    assert initial.queue==service.practice(db,user.id,date(2026,10,28)).queue
    for question in catalog['questions']:service.submit(db,user.id,payload(question_id=question['id'],choice_index=1))
    same=service.practice(db,user.id,date(2026,10,28))
    assert same.queue==[] and '没有到期或未做' in same.plan[0].instruction
    service.submit(db,user.id,payload(question_id='e101',choice_index=0))
    assert service.practice(db,user.id,date(2026,10,29)).queue[0]=='e101'

def test_pagination_and_utc_taipei_day_boundary(db,auth_user_and_headers,catalog,monkeypatch):
    user,_=auth_user_and_headers
    monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,15,59,59,tzinfo=timezone.utc))
    before=service.submit(db,user.id,payload());assert before.study_date==date(2026,10,27)
    monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,16,0,tzinfo=timezone.utc))
    after=service.submit(db,user.id,payload());assert after.study_date==date(2026,10,28)
    page=service.history(db,user.id,'e101',1,1)
    assert page.total==2 and page.items[0].id==before.id
    assert service.history(db,user.id,'e101',2,1).items==[]

@pytest.fixture
def private_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.life_navigation import router
    from app.database import get_db
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    def request_db():
        try:yield db
        except Exception:db.rollback();raise
    app.dependency_overrides[get_db]=request_db
    with TestClient(app) as client:yield client

def test_api_privacy_owner_header_and_rejected_grading_fields(private_client,auth_user_and_headers,catalog):
    user,headers=auth_user_and_headers;path='/api/v1/life-navigation/exam'
    response=private_client.get(path+'/practice',headers=headers)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert 'explanation' not in response.json()['questions'][0]
    response=private_client.post(path+'/attempts',headers={**headers,'X-Reva-AI-Subject':str(user.id+1)},json=payload().model_dump(mode='json'))
    assert response.status_code==409
    response=private_client.post(path+'/attempts',headers=headers,json={**payload().model_dump(mode='json'),'correct':True,'private_marker':'do-not-echo'})
    assert response.status_code==422 and 'do-not-echo' not in response.text
    response=private_client.post(path+'/attempts',headers=headers,json=payload().model_dump(mode='json'))
    assert response.status_code==200 and response.json()['correct'] is False
    assert private_client.get(path+'/attempts?limit=0',headers=headers).status_code==422
    assert private_client.get(path+'/attempts',headers=headers).json()['total']==1

def test_api_key_and_managed_cannot_submit(private_client,db,auth_user_and_headers,catalog):
    from app.models.user_api_key import UserApiKey
    from hashlib import sha256
    user,headers=auth_user_and_headers;path='/api/v1/life-navigation/exam/attempts'
    raw='synthetic-exam-key';db.add(UserApiKey(user_id=user.id,name='test',scopes='read,write',api_key=sha256(raw.encode()).hexdigest()));db.commit()
    assert private_client.post(path,headers={'X-API-Key':raw},json=payload().model_dump(mode='json')).status_code==403
    user.is_managed=True;db.commit()
    assert private_client.post(path,headers=headers,json=payload().model_dump(mode='json')).status_code==403

def test_cross_midnight_retry_preserves_receipt_but_new_id_uses_server_today(db,auth_user_and_headers,catalog,monkeypatch):
    user,_=auth_user_and_headers;request=payload()
    monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,15,59,59,tzinfo=timezone.utc))
    old=service.submit(db,user.id,request)
    monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,16,0,1,tzinfo=timezone.utc))
    assert service.submit(db,user.id,request).model_dump()==old.model_dump()
    new=service.submit(db,user.id,payload())
    assert str(old.study_date)=='2026-10-27' and str(new.study_date)=='2026-10-28'
    assert service.history(db,user.id,None,0,50).total==2

def test_real_reviewed_catalog_loads_public_questions_without_answers(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    catalog=service.load_catalog()
    assert len(catalog.questions)>=80
    assert all(len(q.options)>q.answer>=0 for q in catalog.questions)
    view=service.practice(db,user.id,date(2026,10,28))
    assert len(view.queue)<=18 and len(set(view.queue))==len(view.queue)
    assert len(view.questions)==len(catalog.questions)
    assert all(set(q.model_dump())=={'id','version','subject','topic','prompt','options','source','difficulty'} for q in view.questions)
    for q in catalog.questions:
        if service.legacy_task_id(date(2026,10,27),q.id) is not None:
            assert q.version==1
