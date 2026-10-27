"""本人私人规划：读取无写入，显式保存、恢复和备份。"""
from datetime import date
from app.schemas.exam_practice import ExamAttempt, ExamAttemptWrite, ExamHistory, ExamPractice, QuestionId
from app.services import exam_practice
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import Query
from app.api.deps import get_authenticated_relay_token
from app.schemas.life_morning_readings import MorningReadingList, MorningReadingDetail
from app.services import life_morning_readings
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


@router.get('/morning-readings', response_model=MorningReadingList)
def morning_readings(request: Request, response: Response, offset: int = Query(0, ge=0, le=100_000),
                     user=Depends(owner)):
    _private(response)
    return life_morning_readings.list_readings(user.id, get_authenticated_relay_token(request, user), offset)


@router.get('/morning-readings/{report_id}', response_model=MorningReadingDetail)
def morning_reading(report_id: UUID, request: Request, response: Response, user=Depends(owner)):
    _private(response)
    return life_morning_readings.get_reading(user.id, get_authenticated_relay_token(request, user), str(report_id))


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


@router.get('/exam/practice', response_model=ExamPractice)
def exam_practice_view(response: Response, day: date | None = None,
                       user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return exam_practice.practice(db, user.id, day)


@router.post('/exam/attempts', response_model=ExamAttempt)
def exam_submit(payload: ExamAttemptWrite, response: Response,
                user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return exam_practice.submit(db, user.id, payload)


@router.get('/exam/attempts', response_model=ExamHistory)
def exam_attempts(response: Response, question_id: QuestionId | None = None,
                  offset: int = Query(0, ge=0, le=100_000), limit: int = Query(50, ge=1, le=100),
                  user=Depends(owner), db: Session=Depends(get_db)):
    _private(response)
    return exam_practice.history(db, user.id, question_id, offset, limit)
