"""Deterministic minimal projection over the source-owned occurrence index."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
from collections import Counter
import hmac
import json
from sqlalchemy.orm import Session
from app.config import settings
from app.models.health_navigation import HealthNavigationOccurrence, HealthNavigationDay
from app.models.user_profile import UserProfile
from app.utils.timezone import resolve_timezone_name

FRESHNESS = timedelta(minutes=5)
TERMINAL = {'completed','skipped','withdrawn'}
STATUS = {'done':'completed','verified':'completed','completed':'completed','skipped':'skipped','failed':'skipped','deferred':'deferred','accepted':'pending','adjusted':'pending'}
SHARE_TITLES = {
    'movement.moderate_activity':'查看今日活动安排',
    'movement.zone2_recovery':'查看今日恢复安排',
    'sleep.dinner_cutoff':'查看今日作息安排',
    'measurement.weight_waist_morning':'查看今日记录事项',
}
GENERIC = '到 Health 查看待处理事项'
BOUNDARY = '记录摘要与时序观察，不证明因果。'

def utc(value):
    if value is None: return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _now(now): return utc(now) if now else datetime.now(timezone.utc)

def _source_row(db,user_id,day,key):
    return db.query(HealthNavigationOccurrence).filter_by(user_id=user_id,source='daily_plan',plan_date=day,action_key=key).with_for_update().first()

def materialize_plan(db, plan, *, now=None):
    """Called inside the original planner's write transaction, never by a GET."""
    now=_now(now)
    db.flush()
    # Lock the source owner before the child index. This also records an
    # explicitly generated empty plan without turning GET into a backfill.
    db.refresh(plan,with_for_update=True)
    day=db.query(HealthNavigationDay).filter_by(user_id=plan.user_id,plan_date=plan.plan_date).first()
    if day is None:
        day=HealthNavigationDay(user_id=plan.user_id,plan_date=plan.plan_date,source_as_of=now)
        db.add(day)
    else:day.source_as_of=now
    rows=db.query(HealthNavigationOccurrence).filter_by(user_id=plan.user_id,source='daily_plan',plan_date=plan.plan_date).with_for_update().all()
    existing={r.action_key:r for r in rows}
    seen=set()
    for action in plan.actions or []:
        key=action.get('action_key')
        if not isinstance(key,str) or not key or len(key)>160: continue
        seen.add(key)
        safety=action.get('navigation_safety_state','unknown')
        if safety not in {'allowed','restricted'}: safety='unknown'
        title=str(action.get('title') or GENERIC)
        criterion=str(action.get('completion_criterion') or title)
        content_hash=sha256(json.dumps(action,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
        row=existing.get(key)
        if row is None:
            row=HealthNavigationOccurrence(user_id=plan.user_id,plan_id=plan.id,plan_date=plan.plan_date,action_key=key,title=title,completion_criterion=criterion,content_hash=content_hash,safety_state=safety,source_as_of=now)
            db.add(row)
        else:
            changed=row.content_hash!=content_hash
            if row.execution_status=='withdrawn':
                row.execution_status='pending';changed=True
            row.title=title;row.completion_criterion=criterion;row.content_hash=content_hash;row.safety_state=safety;row.source_as_of=now
            if changed:row.revision+=1
    for key,row in existing.items():
        if key not in seen and row.execution_status not in TERMINAL:
            row.execution_status='withdrawn';row.revision+=1;row.source_as_of=now
    db.flush()

def record_source_event(db,event,*,now=None):
    if event.source!='daily_plan':return
    row=_source_row(db,event.user_id,event.plan_date,event.action_key)
    if row is None:return  # Unmaterialized historical events are not guessed.
    if row.last_event_id and event.id<=row.last_event_id:return
    state=STATUS.get(event.feedback_status,'unknown')
    if row.execution_status=='completed' and state in {'pending','deferred'}:state='completed'
    row.last_event_id=event.id
    if row.execution_status!=state: row.execution_status=state;row.revision+=1
    db.flush()

def _ref(row,view_id):
    if not view_id:return row.id
    digest=hmac.new(settings.secret_key.encode(),f'{view_id}:{row.id}'.encode(),'sha256').hexdigest()
    return f'{view_id}.{digest}'

def _safety(row,now):
    return row.safety_state if now < utc(row.source_as_of)+FRESHNESS else 'unknown'

def _revision(row,now):
    return sha256(f'{row.id}:{row.revision}:{_safety(row,now)}'.encode()).hexdigest()

def _view(row,now,view_id=None):
    safety=_safety(row,now)
    ref=_ref(row,view_id)
    # No free-form source text ever enters summaries, including generic mode.
    return {'action_ref':ref,'action_revision':_revision(row,now),
        'share_title':SHARE_TITLES.get(row.action_key,GENERIC),
        'share_completion_criterion':'返回 Health 核对并记录执行结果',
        'execution_status':row.execution_status,'safety_state':safety,
        'requires_health_review':safety!='allowed' or row.action_key not in SHARE_TITLES,
        'scheduling_mode':'view_only','detail_ref':ref}

def _timezone(db,user_id):
    profile=db.query(UserProfile).filter_by(user_id=user_id).first()
    if profile:return resolve_timezone_name(profile.manual_timezone,profile.detected_timezone,profile.timezone)
    return resolve_timezone_name()

def build_health_week_navigation(db:Session,user_id:int,*,now=None,audience='health',view_id=None):
    now=_now(now)
    tz,tz_source=_timezone(db,user_id)
    end=now.astimezone(ZoneInfo(tz)).date();start=end-timedelta(days=6)
    rows=db.query(HealthNavigationOccurrence).filter(HealthNavigationOccurrence.user_id==user_id,HealthNavigationOccurrence.plan_date>=start,HealthNavigationOccurrence.plan_date<=end).order_by(HealthNavigationOccurrence.plan_date,HealthNavigationOccurrence.id).all()
    source_today=[r for r in rows if r.plan_date==end]
    generated=db.query(HealthNavigationDay).filter_by(user_id=user_id,plan_date=end).first() is not None
    hidden = audience=='lifenav' and any(r.action_key not in SHARE_TITLES for r in source_today)
    if audience=='lifenav':
        rows=[r for r in rows if r.action_key in SHARE_TITLES]
    today=[r for r in rows if r.plan_date==end]
    counts=Counter(r.execution_status for r in rows)
    days=len({r.plan_date for r in rows if r.last_event_id is not None})
    review={'recorded_days':days,'window_days':7,'coverage_status':'complete' if days==7 else 'partial' if days else 'missing',
        'completed_occurrences':counts['completed'],'skipped_occurrences':counts['skipped'],'deferred_occurrences':counts['deferred'],'unknown_occurrences':counts['unknown'],'claim_boundary':BOUNDARY}
    actions=[_view(r,now,view_id if audience=='lifenav' else None) for r in today]
    content={'schema_version':'health_week_navigation.v1','local_date':end.isoformat(),'timezone':tz,'timezone_source':tz_source,
        'availability':'not_generated' if not generated else 'partial' if hidden or any(a['safety_state']=='unknown' for a in actions) else 'ready',
        'review_window':{'start_date':start.isoformat(),'end_date':end.isoformat(),'days':7,'includes_today':True,'kind':'rolling'},
        'actions':actions,'review':review,'restrictions':[{'code':'check_in_health','message':GENERIC}] if hidden or any(a['requires_health_review'] for a in actions) else []}
    revision=sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    source=max((utc(r.source_as_of) for r in rows),default=None)
    # Source revisions include inactive historical rows so disappearing cards cannot
    # roll the cursor backward. The revision hash separately binds window and freshness.
    from sqlalchemy import func
    versions=db.query(func.coalesce(func.sum(HealthNavigationOccurrence.revision),0)).filter_by(user_id=user_id)
    if audience=='lifenav':versions=versions.filter(HealthNavigationOccurrence.action_key.in_(SHARE_TITLES))
    version=versions.scalar()
    expiry=min([now+FRESHNESS]+[utc(r.source_as_of)+FRESHNESS for r in today if utc(r.source_as_of)+FRESHNESS>now])
    return {**content,'projection_revision':revision,'projection_sequence':int(version),
        'generated_at':now.isoformat(),'source_as_of':source.isoformat() if source else None,'expires_at':expiry.isoformat()}

def resolve_action(db,user_id,ref,*,now=None):
    now=_now(now)
    if '.' in ref:
        view_id,digest=ref.split('.',1)
        from app.models.lifenav_grant import LifeNavGrant
        grant=db.query(LifeNavGrant).filter_by(id=view_id,user_id=user_id).first()
        if grant is None or grant.revoked_at or utc(grant.expires_at)<=now:return None
        rows=db.query(HealthNavigationOccurrence).filter_by(user_id=user_id).all()
        row=next((r for r in rows if hmac.compare_digest(_ref(r,view_id),ref)),None)
    else:row=db.query(HealthNavigationOccurrence).filter_by(id=ref,user_id=user_id).first()
    if row is None:return None
    safety=_safety(row,now)
    tz,_=_timezone(db,user_id);today=now.astimezone(ZoneInfo(tz)).date()
    return {'action_ref':ref,'action_revision':_revision(row,now),'title':row.title,'completion_criterion':row.completion_criterion,
        'execution_status':row.execution_status,'safety_state':safety,'requires_health_review':safety!='allowed',
        'scheduling_mode':'view_only','plan_date':row.plan_date.isoformat(),'action_key':row.action_key,
        'expires_at':(utc(row.source_as_of)+FRESHNESS).isoformat(),
        'can_confirm':row.plan_date==today and safety=='allowed' and row.execution_status in {'pending','deferred'}}
