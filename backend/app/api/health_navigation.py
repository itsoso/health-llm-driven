"""本人周导航：GET只读，刷新和执行只接受本人显式操作。"""
import json
from datetime import datetime, timezone
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.integration_lifenav import PrivateIntegrationRoute, _private, self_only
from app.config import settings
from app.database import get_db
from app.api.deps import bind_authenticated_tenant
from app.models.daily_operating_plan import DailyOperatingPlan
from app.models.health_navigation import HealthNavigationOccurrence, HealthNavigationOperation
from app.models.intervention_event import InterventionEvent
from app.schemas.health_week_navigation import HealthWeekNavigation, NavigationEventRequest, NavigationActionDetail, NavigationEventReceipt
from app.services.health_week_navigation import build_health_week_navigation, resolve_action, record_source_event
from app.services.daily_operating_plan import build_daily_operating_plan
from app.utils.timezone import get_user_today

router=APIRouter(prefix='/health-navigation',tags=['health-navigation'],route_class=PrivateIntegrationRoute)

def enabled():
    if not settings.health_navigation_enabled:raise HTTPException(503,'健康周导航暂未启用')

def read_session(db):
    session=Session(bind=db.get_bind(),autoflush=False)
    if session.bind.dialect.name=='postgresql':session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
    return session

@router.get('/summary',response_model=HealthWeekNavigation)
def summary(response:Response,user=Depends(self_only),db:Session=Depends(get_db)):
    enabled();_private(response)
    with read_session(db) as read_db:
        bind_authenticated_tenant(read_db,user.id)
        result=build_health_week_navigation(read_db,user.id)
        read_db.rollback()
    return result

@router.post('/refresh',response_model=HealthWeekNavigation)
def refresh(response:Response,user=Depends(self_only),db:Session=Depends(get_db)):
    enabled();_private(response)
    build_daily_operating_plan(db,user.id,plan_date=get_user_today(db,user.id),commit=False)
    db.commit()
    return build_health_week_navigation(db,user.id)

@router.get('/actions/{ref}',response_model=NavigationActionDetail)
def detail(ref:str,response:Response,user=Depends(self_only),db:Session=Depends(get_db)):
    enabled();_private(response)
    if len(ref)>160:raise HTTPException(404,'行动引用不存在或已失效')
    result=resolve_action(db,user.id,ref)
    if result is None:raise HTTPException(404,'行动引用不存在或已失效')
    return result

@router.post('/actions/{ref}/events',response_model=NavigationEventReceipt)
def confirm(ref:str,payload:NavigationEventRequest,response:Response,user=Depends(self_only),db:Session=Depends(get_db)):
    enabled();_private(response)
    if len(ref)>160:raise HTTPException(404,'行动引用不存在或已失效')
    target=resolve_action(db,user.id,ref)
    if target is None:raise HTTPException(404,'行动引用不存在或已失效')
    private_ref=ref
    if '.' in ref:
        from app.services.health_week_navigation import _ref
        view_id=ref.split('.',1)[0]
        candidates=db.query(HealthNavigationOccurrence).filter_by(user_id=user.id).all()
        private_ref=next((r.id for r in candidates if _ref(r,view_id)==ref),None)
    row=db.query(HealthNavigationOccurrence).filter_by(id=private_ref,user_id=user.id).first()
    if row is None:raise HTTPException(404,'行动引用不存在或已失效')
    # Source plan then occurrence: consistent lock ordering with source writes.
    from app.models.user import User
    # NO KEY UPDATE serializes confirmations without blocking source FK KEY SHARE.
    actor=db.query(User).filter_by(id=user.id).populate_existing().with_for_update(key_share=True).one()
    if not actor.is_active or not actor.is_approved:raise HTTPException(403,'账户已失效')
    db.query(DailyOperatingPlan).filter_by(id=row.plan_id,user_id=user.id).populate_existing().with_for_update().one()
    row=db.query(HealthNavigationOccurrence).filter_by(id=row.id,user_id=user.id).populate_existing().with_for_update().one()
    op_id=str(payload.operation_id)
    fingerprint=sha256(json.dumps({'ref':private_ref,'event':payload.event_type,'revision':payload.expected_revision},sort_keys=True).encode()).hexdigest()
    receipt=db.query(HealthNavigationOperation).filter_by(user_id=user.id,operation_id=op_id).first()
    if receipt:
        if receipt.payload_hash!=fingerprint:raise HTTPException(409,'同一操作编号的内容发生变化')
        return {**receipt.receipt,'idempotent':True}
    if row.plan_date!=get_user_today(db,user.id):raise HTTPException(409,'历史行动仅可查看，请返回 Health 更正记录')
    # Fresh deterministic source checks; changed/withdrawn action cannot pass
    # with the old displayed revision. The planner is the existing Health owner.
    build_daily_operating_plan(db,user.id,plan_date=row.plan_date,commit=False)
    # Serialize all operation IDs for this owner, including conflicting keys
    # aimed at different actions. Recheck receipt after fresh source evaluation.
    row=db.query(HealthNavigationOccurrence).filter_by(id=private_ref,user_id=user.id).populate_existing().with_for_update().one()
    receipt=db.query(HealthNavigationOperation).filter_by(user_id=user.id,operation_id=op_id).first()
    if receipt:
        if receipt.payload_hash!=fingerprint:raise HTTPException(409,'同一操作编号的内容发生变化')
        return {**receipt.receipt,'idempotent':True}
    if '.' in ref:
        from app.models.lifenav_grant import LifeNavGrant
        db.query(LifeNavGrant).filter_by(id=ref.split('.',1)[0],user_id=user.id).populate_existing().with_for_update().first()
    target=resolve_action(db,user.id,ref)
    if target is None or target['action_revision']!=payload.expected_revision or not target['can_confirm']:
        raise HTTPException(409,'行动或安全状态已变化，请重新核对')
    source_plan=db.query(DailyOperatingPlan).filter_by(id=row.plan_id,user_id=user.id).populate_existing().one()
    source_action=next((a for a in source_plan.actions if a.get('action_key')==row.action_key),None)
    if source_action is None:raise HTTPException(409,'源行动已变化，请重新核对')
    from app.api.daily_plan import _action_execution_snapshot, _sync_source_card_lifecycle
    snapshot=_action_execution_snapshot({**source_action,'event_type':payload.event_type},row.action_key)
    event=InterventionEvent(user_id=user.id,plan_id=row.plan_id,plan_date=row.plan_date,action_key=row.action_key,action_title=row.title,action_domain=source_action.get('domain'),source='daily_plan',feedback_status=payload.event_type,event_idempotency_key=sha256(f'nav:{user.id}:{op_id}'.encode()).hexdigest(),action_snapshot=snapshot)
    db.add(event);db.flush();record_source_event(db,event)
    _sync_source_card_lifecycle(db,user_id=user.id,action=source_action,status=payload.event_type)
    result={'action':resolve_action(db,user.id,ref),'idempotent':False}
    db.add(HealthNavigationOperation(user_id=user.id,occurrence_id=row.id,operation_id=op_id,payload_hash=fingerprint,receipt=result,created_at=datetime.now(timezone.utc)))
    db.commit()
    return result
