"""Dedicated LifeNav entrypoints; ordinary account credentials cannot read externally."""
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.deps import bind_authenticated_tenant, get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.health_week_navigation import HealthWeekNavigation
from app.schemas.lifenav_grant import LifeNavCodeExchange, LifeNavGrantCreate, LifeNavGrantCreated, LifeNavGrantView, LifeNavToken
from app.services import integration_grant_service as service

logger = logging.getLogger(__name__)

PRIVATE_HEADERS = {'Cache-Control': 'private, no-store', 'Pragma': 'no-cache', 'Referrer-Policy': 'no-referrer'}


class PrivateIntegrationRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                # Validation input may include authorization codes/client secrets.
                detail = [{'loc': error['loc'], 'type': error['type'], 'msg': error['msg']}
                          for error in exc.errors()]
                return JSONResponse(status_code=422, content={'detail': detail}, headers=PRIVATE_HEADERS)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **PRIVATE_HEADERS}
                raise
            except Exception as exc:
                logger.error("LifeNav request unavailable error_type=%s", type(exc).__name__)
                return JSONResponse(status_code=503, content={
                    'detail': 'LifeNav 连接暂不可用，请稍后重试'}, headers=PRIVATE_HEADERS)
        return handle


router = APIRouter(tags=['health-navigation'], route_class=PrivateIntegrationRoute)


def _private(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Referrer-Policy'] = 'no-referrer'


def self_only(request: Request, user: User = Depends(get_current_user_required)):
    if (getattr(request.state, 'auth_type', None) not in {'jwt', 'cookie'}
            or getattr(request.state, 'is_proxy_mode', False) or user.is_managed):
        raise HTTPException(status_code=403, detail='请使用本人 Health 登录管理连接')
    return user


@router.get('/health-navigation/grants', response_model=list[LifeNavGrantView])
def list_grants(response: Response, user: User = Depends(self_only), db: Session = Depends(get_db)):
    _private(response)
    # Listing/revocation remain available after disabling the external feature.
    return service.list_grants(db, user.id)


@router.post('/health-navigation/grants', response_model=LifeNavGrantCreated)
def create_grant(payload: LifeNavGrantCreate, response: Response,
                 user: User = Depends(self_only), db: Session = Depends(get_db)):
    _private(response)
    return service.create_grant(db, user, payload)


@router.delete('/health-navigation/grants/{grant_id}')
def revoke_grant(grant_id: str, response: Response, user: User = Depends(self_only), db: Session = Depends(get_db)):
    _private(response)
    service.revoke_grant(db, user.id, grant_id)
    return {'revoked': True}


@router.post('/integrations/lifenav/exchange', response_model=LifeNavToken)
def exchange_code(payload: LifeNavCodeExchange, request: Request,
                  response: Response, db: Session = Depends(get_db)):
    _private(response)
    if request.headers.get('origin') or request.headers.get('cookie'):
        raise HTTPException(status_code=403, detail='凭据仅供已核验的接收方服务端兑换')
    return service.exchange_code(db, payload)


def _audit_separately(bind, grant_id, request_id, outcome):
    # No health body, credentials, externally supplied request ID or URL is recorded.
    with Session(bind=bind) as audit_db:
        service.audit(audit_db, grant_id, outcome, request_id)
        audit_db.commit()


@router.get('/integrations/lifenav/summary', response_model=HealthWeekNavigation)
def get_summary(request: Request, response: Response,
                authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    _private(response)
    if request.query_params:
        raise HTTPException(status_code=400, detail='仅支持当前滚动七天，不接受字段或用户选择器')
    if request.headers.get('x-api-key') or request.headers.get('cookie') or request.headers.get('origin'):
        raise HTTPException(status_code=403, detail='仅允许 LifeNav 服务端专用凭据')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='需要 LifeNav 专用凭据')
    token = authorization.removeprefix('Bearer ')
    bind = db.get_bind()
    grant_id = None
    request_id = str(uuid.uuid4())
    try:
        # Authentication and projection share a fresh read-only business transaction.
        # Audit is persisted after rollback, using a distinct writable transaction.
        with Session(bind=bind, autoflush=False) as read_db:
            if bind.dialect.name == 'postgresql':
                read_db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            grant = service.authenticate_grant(read_db, token)
            grant_id = grant.id
            bind_authenticated_tenant(read_db, grant.user_id)
            from app.services.health_week_navigation import build_health_week_navigation
            payload = build_health_week_navigation(read_db, grant.user_id, audience='lifenav', view_id=grant.id)
            # The display validity cannot outlive the authorization.
            expires = payload.get('expires_at')
            if expires is not None:
                deadline = service.utc(datetime.fromisoformat(expires.replace('Z', '+00:00'))) if isinstance(expires, str) else service.utc(expires)
                payload['expires_at'] = min(deadline, service.utc(grant.expires_at)).isoformat()
            else:
                payload['expires_at'] = service.utc(grant.expires_at).isoformat()
            read_db.rollback()
    except HTTPException:
        _audit_separately(bind, grant_id, request_id, 'denied')
        raise
    except Exception:
        _audit_separately(bind, grant_id, request_id, 'unavailable')
        raise
    _audit_separately(bind, grant_id, request_id, 'read')
    return payload
