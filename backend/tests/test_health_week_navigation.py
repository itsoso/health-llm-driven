from datetime import date, datetime, timedelta, timezone
import pytest
from app.models.daily_operating_plan import DailyOperatingPlan
from app.models.intervention_event import InterventionEvent
from app.services.health_week_navigation import materialize_plan, record_source_event, build_health_week_navigation, resolve_action

NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)
DAY = date(2026, 10, 9)

def plan(db, user, day=DAY, key='movement.moderate_activity'):
    row = DailyOperatingPlan(user_id=user.id,plan_date=day,actions=[{'action_key':key,'title':'个人健康正文不外传','navigation_safety_state':'allowed'}])
    db.add(row); db.flush()
    materialize_plan(db,row,now=NOW);db.commit()
    return row

def test_unmaterialized_read_does_not_generate(db, auth_user_and_headers):
    user,_=auth_user_and_headers
    before=len(db.query(DailyOperatingPlan).all())
    out=build_health_week_navigation(db,user.id,now=NOW)
    assert out['availability']=='not_generated'
    assert len(db.query(DailyOperatingPlan).all())==before
    assert 'completion_rate' not in out['review']

def test_deterministic_minimal_projection_and_expiry(db,auth_user_and_headers):
    user,_=auth_user_and_headers;plan(db,user)
    a=build_health_week_navigation(db,user.id,now=NOW,audience='lifenav',view_id='a')
    b=build_health_week_navigation(db,user.id,now=NOW+timedelta(seconds=1),audience='lifenav',view_id='a')
    assert a['projection_revision']==b['projection_revision']
    assert '个人健康正文' not in str(a)
    assert a['actions'][0]['scheduling_mode']=='view_only'
    assert a['review_window']['start_date']=='2026-10-03'
    stale=build_health_week_navigation(db,user.id,now=NOW+timedelta(minutes=6))
    assert stale['actions'][0]['safety_state']=='unknown'
    assert stale['actions'][0]['requires_health_review']

def test_terminal_event_survives_disappearing_plan_and_repeat(db,auth_user_and_headers):
    user,_=auth_user_and_headers;p=plan(db,user)
    row=InterventionEvent(user_id=user.id,plan_id=p.id,plan_date=DAY,action_key='movement.moderate_activity',action_title='正文',feedback_status='completed',source='daily_plan')
    db.add(row);db.flush();record_source_event(db,row,now=NOW);db.commit()
    record_source_event(db,row,now=NOW);db.commit()
    p.actions=[];materialize_plan(db,p,now=NOW);db.commit()
    out=build_health_week_navigation(db,user.id,now=NOW)
    assert out['review']['completed_occurrences']==1
    assert out['actions'][0]['execution_status']=='completed'
    assert 'planned_occurrences' not in out['review']

def test_cross_day_key_and_withdrawn_status(db,auth_user_and_headers):
    user,_=auth_user_and_headers;p=plan(db,user)
    yesterday=plan(db,user,DAY-timedelta(days=1))
    refs=build_health_week_navigation(db,user.id,now=NOW)['actions']
    p.actions=[];materialize_plan(db,p,now=NOW);db.commit()
    assert build_health_week_navigation(db,user.id,now=NOW)['actions'][0]['execution_status']=='withdrawn'
    assert yesterday.id!=p.id

def test_foreign_reference_has_no_visibility(db,auth_user_and_headers):
    user,_=auth_user_and_headers;plan(db,user)
    out=build_health_week_navigation(db,user.id,now=NOW)
    ref=out['actions'][0]['action_ref']
    assert resolve_action(db,user.id+10000,ref,now=NOW) is None
    assert resolve_action(db,user.id,ref,now=NOW)['title']=='个人健康正文不外传'

def test_generated_empty_is_not_not_generated(db,auth_user_and_headers):
    user,_=auth_user_and_headers;p=plan(db,user);p.actions=[];materialize_plan(db,p,now=NOW);db.commit()
    # Withdrawal is historical visibility, not a missing plan.
    assert build_health_week_navigation(db,user.id,now=NOW)['availability']!='not_generated'

def test_changed_intensity_is_new_frozen_revision(db,auth_user_and_headers):
    user,_=auth_user_and_headers;p=plan(db,user)
    a=build_health_week_navigation(db,user.id,now=NOW)
    p.actions=[{**p.actions[0],'target_value':'new intensity'}];materialize_plan(db,p,now=NOW);db.commit()
    b=build_health_week_navigation(db,user.id,now=NOW)
    assert a['actions'][0]['action_revision']!=b['actions'][0]['action_revision']

def test_sensitive_only_has_no_external_counts_or_revision_activity(db,auth_user_and_headers):
    user,_=auth_user_and_headers;p=plan(db,user,key='intervention.card.12')
    a=build_health_week_navigation(db,user.id,now=NOW,audience='lifenav',view_id='x')
    e=InterventionEvent(user_id=user.id,plan_id=p.id,plan_date=DAY,action_key='intervention.card.12',action_title='药名',source='daily_plan',feedback_status='completed')
    db.add(e);db.flush();record_source_event(db,e,now=NOW);db.commit()
    b=build_health_week_navigation(db,user.id,now=NOW,audience='lifenav',view_id='x')
    assert a['actions']==b['actions']==[]
    assert a['review']==b['review']
    assert a['projection_sequence']==b['projection_sequence']
    assert a['source_as_of']==b['source_as_of']==None

@pytest.fixture
def enabled(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'health_navigation_enabled',True)

def live_plan(db,user):
    from app.utils.timezone import get_user_today
    today=get_user_today(db,user.id)
    return plan(db,user,day=today)

def test_native_route_confirm_is_atomic_and_idempotent(client,db,auth_user_and_headers,enabled,monkeypatch):
    import uuid
    from app.api import health_navigation
    user,headers=auth_user_and_headers;p=live_plan(db,user)
    materialize_plan(db,p);db.commit()
    def source_writer(db,user_id,plan_date,*,commit=True):
        assert commit is False
        materialize_plan(db,db.query(DailyOperatingPlan).filter_by(user_id=user_id,plan_date=plan_date).one())
    monkeypatch.setattr(health_navigation,'build_daily_operating_plan',source_writer)
    ref=client.get('/api/v1/health-navigation/summary',headers=headers).json()['actions'][0]['action_ref']
    detail=client.get('/api/v1/health-navigation/actions/'+ref,headers=headers).json()
    assert detail['can_confirm']
    body={'event_type':'completed','operation_id':str(uuid.uuid4()),'expected_revision':detail['action_revision']}
    first=client.post('/api/v1/health-navigation/actions/'+ref+'/events',headers=headers,json=body)
    assert first.status_code==200,first.text
    again=client.post('/api/v1/health-navigation/actions/'+ref+'/events',headers=headers,json=body)
    assert again.status_code==200,again.text
    assert again.json()['idempotent']
    assert db.query(InterventionEvent).filter_by(user_id=user.id).count()==1
    different=client.post('/api/v1/health-navigation/actions/'+ref+'/events',headers=headers,json={**body,'event_type':'skipped'})
    assert different.status_code==409

def test_native_route_rejects_changed_source_content(client,db,auth_user_and_headers,enabled,monkeypatch):
    import uuid
    from app.api import health_navigation
    user,headers=auth_user_and_headers;p=live_plan(db,user);materialize_plan(db,p);db.commit()
    ref=client.get('/api/v1/health-navigation/summary',headers=headers).json()['actions'][0]['action_ref']
    frozen=client.get('/api/v1/health-navigation/actions/'+ref,headers=headers).json()
    def changed_writer(db,user_id,plan_date,*,commit=True):
        assert commit is False
        row=db.query(DailyOperatingPlan).filter_by(id=p.id).one()
        row.actions=[{**row.actions[0],'target_value':'new dose'}]
        materialize_plan(db,row)
    monkeypatch.setattr(health_navigation,'build_daily_operating_plan',changed_writer)
    response=client.post('/api/v1/health-navigation/actions/'+ref+'/events',headers=headers,json={'event_type':'completed','operation_id':str(uuid.uuid4()),'expected_revision':frozen['action_revision']})
    assert response.status_code==409
    assert db.query(InterventionEvent).count()==0

def test_transactional_guard_rechecks_old_allowed_verdict(db,auth_user_and_headers,monkeypatch):
    from app.services.advice_guard import AdviceCandidate,AdviceDecision,AdviceGuard,guard_and_record_advice
    user,_=auth_user_and_headers
    candidate=AdviceCandidate(user_id=user.id,source='daily_plan',source_id='test',domain='movement',title='记录行动',body='记录行动',metric_key='custom',target_value='trend',evidence_tier='strong_behavioral',confidence='medium',claim_boundary='不证明医学因果',valid_for_date=DAY)
    monkeypatch.setattr(AdviceGuard,'evaluate',lambda self,c:AdviceDecision(allowed=True,reason='allowed',advice_key=c.advice_key))
    assert guard_and_record_advice(db,candidate).allowed
    monkeypatch.setattr(AdviceGuard,'evaluate',lambda self,c:AdviceDecision(allowed=False,reason='current_safety_block',advice_key=c.advice_key))
    assert not guard_and_record_advice(db,candidate,commit=False).allowed

def test_managed_navigation_migrations_replay_matches_models(db,tmp_path):
    from pathlib import Path
    from sqlalchemy import inspect
    from app.models.health_navigation import HealthNavigationOperation,HealthNavigationOccurrence,HealthNavigationDay
    from app.models.lifenav_grant import LifeNavGrant,LifeNavAccessAudit
    from app.services.managed_migrations import apply_managed_migrations
    engine=db.get_bind();db.rollback()
    for model in [HealthNavigationOperation,HealthNavigationOccurrence,HealthNavigationDay,LifeNavAccessAudit,LifeNavGrant]:model.__table__.drop(engine,checkfirst=True)
    src=Path(__file__).resolve().parents[1]/'migrations'/'managed'
    from uuid import uuid4
    namespace=uuid4().hex
    for p in src.glob('20261009_*nav*.sql'):(tmp_path/('test_'+namespace+'_'+p.name)).write_text(p.read_text())
    first=apply_managed_migrations(engine,tmp_path);second=apply_managed_migrations(engine,tmp_path)
    assert len(first.applied)==2 and not second.applied
    assert 'content_hash' in {c['name'] for c in inspect(engine).get_columns('health_navigation_occurrences')}
    assert inspect(engine).has_table('health_navigation_days')

def test_fresh_empty_plan_has_generated_marker(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    p=DailyOperatingPlan(user_id=user.id,plan_date=DAY,actions=[])
    db.add(p);db.flush();materialize_plan(db,p,now=NOW);db.commit()
    result=build_health_week_navigation(db,user.id,now=NOW)
    assert result['availability']=='ready'
    assert result['actions']==[]

def test_explicit_refresh_uses_fresh_transaction(client,db,auth_user_and_headers,enabled,monkeypatch):
    from app.api import health_navigation
    user,headers=auth_user_and_headers
    calls=[]
    def fresh_writer(session,user_id,plan_date,*,commit=True):
        assert commit is False
        calls.append(user_id)
        p=DailyOperatingPlan(user_id=user_id,plan_date=plan_date,actions=[])
        session.add(p);session.flush();materialize_plan(session,p)
    monkeypatch.setattr(health_navigation,'build_daily_operating_plan',fresh_writer)
    response=client.post('/api/v1/health-navigation/refresh',headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['availability']=='ready'
    assert calls==[user.id]

def test_native_confirmation_preserves_source_card_lifecycle(client,db,auth_user_and_headers,enabled,monkeypatch):
    from uuid import uuid4
    from app.api import health_navigation
    from app.models.action_card import ActionCard
    user,headers=auth_user_and_headers
    card=ActionCard(user_id=user.id,title='合成来源卡',content='合成说明',status='active')
    db.add(card);db.flush()
    p=live_plan(db,user)
    p.actions=[{**p.actions[0],'source_card_id':card.id,'target_value':'原目标','domain':'movement'}]
    materialize_plan(db,p);db.commit()
    monkeypatch.setattr(health_navigation,'build_daily_operating_plan',lambda session,user_id,plan_date,commit=False: materialize_plan(session,session.query(DailyOperatingPlan).filter_by(id=p.id).one()))
    ref=client.get('/api/v1/health-navigation/summary',headers=headers).json()['actions'][0]['action_ref']
    revision=client.get('/api/v1/health-navigation/actions/'+ref,headers=headers).json()['action_revision']
    response=client.post('/api/v1/health-navigation/actions/'+ref+'/events',headers=headers,json={'event_type':'completed','operation_id':str(uuid4()),'expected_revision':revision})
    assert response.status_code==200,response.text
    db.refresh(card)
    assert card.status=='completed'
    assert db.query(InterventionEvent).one().action_snapshot['target_value']=='原目标'
    assert db.query(InterventionEvent).one().action_domain=='movement'

def test_enabled_real_planner_keeps_projection_in_caller_transaction(db,auth_user_and_headers,enabled):
    from app.services.daily_operating_plan import build_daily_operating_plan
    from app.models.health_navigation import HealthNavigationDay,HealthNavigationOccurrence
    from app.utils.timezone import get_user_today
    user,_=auth_user_and_headers;user_id=user.id
    result=build_daily_operating_plan(db,user_id,plan_date=get_user_today(db,user_id),commit=False)
    assert result['id']
    assert db.query(HealthNavigationDay).filter_by(user_id=user_id).count()==1
    assert db.query(HealthNavigationOccurrence).filter_by(user_id=user_id).count()>0
    db.rollback()
    assert db.query(DailyOperatingPlan).filter_by(user_id=user_id).count()==0
    assert db.query(HealthNavigationDay).filter_by(user_id=user_id).count()==0
