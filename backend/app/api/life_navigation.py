"""本人私人规划：读取无写入，显式保存、恢复和备份。"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.integration_lifenav import PrivateIntegrationRoute, _private, self_only
from app.database import get_db
from app.schemas.life_navigation import LifeBackup, LifeHistory, LifeImport, LifeRevisionRequest, LifeWorkspace, LifeWorkspaceWrite
from app.services import life_navigation as service

router = APIRouter(prefix='/life-navigation', tags=['life-navigation'], route_class=PrivateIntegrationRoute)


def owner(request: Request, user=Depends(self_only)):
    subject = request.headers.get('x-reva-ai-subject')
    if subject is not None and subject != str(user.id):
        raise HTTPException(409, '登录账号已变化，请刷新页面后重试')
    return user


@router.get('/workspace', response_model=LifeWorkspace)
def workspace(response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.get_workspace(db, user.id)


@router.put('/workspace', response_model=LifeWorkspace)
def save(payload: LifeWorkspaceWrite, response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.save_workspace(db, user.id, payload)


@router.get('/history', response_model=list[LifeHistory])
def history(response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.get_history(db, user.id)


@router.post('/restore/{revision}', response_model=LifeWorkspace)
def restore(revision: int, payload: LifeRevisionRequest, response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.restore_workspace(db, user.id, revision, payload.expected_revision)


@router.get('/backup', response_model=LifeBackup)
def backup(response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.get_backup(db, user.id)


@router.post('/import', response_model=LifeWorkspace)
def import_workspace(payload: LifeImport, response: Response, user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return service.import_backup(db, user.id, payload.expected_revision, payload.backup)
