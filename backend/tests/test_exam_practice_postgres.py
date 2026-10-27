"""Real PostgreSQL migration, per-owner concurrent submission and deletion semantics."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import os
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app.models.user import User
from app.models.life_navigation import LifeNavigationWorkspace
from app.models.exam_practice import ExamAttemptRecord
from app.schemas.exam_practice import Catalog, ExamAttemptWrite
from app.services import exam_practice as service
from app.services.managed_migrations import apply_managed_migrations

MIGRATION='20261028_120000_life_exam_attempts'
URL=os.getenv('EXAM_TEST_DATABASE_URL') or os.getenv('TEST_DATABASE_URL')


def install(engine,tmp_path,dialect):
    directory=tmp_path/dialect;directory.mkdir()
    source=Path(__file__).parents[1]/'migrations'/'managed'/f'{MIGRATION}.{dialect}.sql'
    (directory/source.name).write_text(source.read_text())
    first=apply_managed_migrations(engine,directory);again=apply_managed_migrations(engine,directory)
    assert [m.id for m in first.applied]==[MIGRATION]
    assert [m.id for m in again.skipped]==[MIGRATION]


def test_sqlite_migration_mirror_and_model_shape(tmp_path):
    engine=create_engine('sqlite:///:memory:')
    with engine.begin() as conn:conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
    install(engine,tmp_path,'sqlite')
    assert set(ExamAttemptRecord.__table__.c.keys())=={column['name'] for column in inspect(engine).get_columns('life_exam_attempts')}
    engine.dispose()


@pytest.fixture
def pg(tmp_path,monkeypatch):
    if not URL:pytest.skip('requires EXAM_TEST_DATABASE_URL or TEST_DATABASE_URL PostgreSQL')
    from sqlalchemy.engine import make_url
    url=make_url(URL)
    assert url.get_backend_name()=='postgresql' and 'test' in (url.database or '')
    schema='exam_'+uuid4().hex;admin=create_engine(URL);engine=None
    try:
        with admin.begin() as conn:conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine=create_engine(URL,connect_args={'options':f'-csearch_path={schema}'})
        User.__table__.create(engine);LifeNavigationWorkspace.__table__.create(engine)
        install(engine,tmp_path,'postgresql')
        sessions=sessionmaker(bind=engine)
        with sessions() as db:
            db.add_all([User(id=1,name='synthetic1',is_active=True,is_approved=True,is_managed=False),User(id=2,name='synthetic2',is_active=True,is_approved=True,is_managed=False)]);db.commit()
        catalog=Catalog.model_validate({'catalog_version':'pg-v1','questions':[{'id':'e101','version':1,'subject':'英语','topic':'test','prompt':'synthetic question','options':['a','b','c','d'],'answer':1,'explanation':'synthetic explanation','source':'original','difficulty':'basic'}]})
        monkeypatch.setattr(service,'load_catalog',lambda:catalog)
        monkeypatch.setattr(service,'utcnow',lambda:datetime(2026,10,27,16,0,tzinfo=timezone.utc))
        yield engine,sessions
    finally:
        if engine is not None:engine.dispose()
        with admin.begin() as conn:conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def request(**kw):
    return ExamAttemptWrite(request_id=uuid4(),question_id='e101',question_version=1,choice_index=0,elapsed_seconds=60,**kw)


def test_postgres_same_request_concurrent_retry_is_one_attempt(pg):
    engine,sessions=pg;barrier=Barrier(6);payload=request()
    def submit():
        with sessions() as db:
            barrier.wait(timeout=20)
            return service.submit(db,1,payload)
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda _:submit(),range(6)))
    assert len({r.id for r in results})==1
    with sessions() as db:assert db.query(ExamAttemptRecord).count()==1
    assert {c['name'] for c in inspect(engine).get_columns('life_exam_attempts')}==set(ExamAttemptRecord.__table__.c.keys())


def test_postgres_conflicting_request_serializes_without_overwrite(pg):
    from fastapi import HTTPException
    _,sessions=pg;barrier=Barrier(2);payload=request()
    def submit(choice):
        with sessions() as db:
            barrier.wait(timeout=20)
            try:return service.submit(db,1,payload.model_copy(update={'choice_index':choice}))
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[0,1]))
    assert sum(r==409 for r in results)==1
    with sessions() as db:
        row=db.query(ExamAttemptRecord).one()
        winner=next(r for r in results if r!=409)
        assert row.choice_index==winner.choice_index


def test_postgres_distinct_requests_remain_distinct_and_owner_isolated(pg):
    _,sessions=pg;barrier=Barrier(6)
    def submit(index):
        with sessions() as db:
            barrier.wait(timeout=20)
            return service.submit(db,1 if index<4 else 2,request())
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(submit,range(6)))
    assert len({r.id for r in results})==6
    with sessions() as db:
        assert service.history(db,1,None,0,50).total==4
        assert service.history(db,2,None,0,50).total==2
        assert all(r.answered_at.tzinfo is not None for r in service.history(db,1,None,0,50).items)
        assert all(str(r.study_date)=='2026-10-28' for r in results)


def test_postgres_constraints_snapshot_and_account_delete_cascade(pg):
    engine,sessions=pg
    with sessions() as db:
        answer=service.submit(db,1,request())
        row=db.query(ExamAttemptRecord).one()
        assert row.question_snapshot['options']==['a','b','c','d']
        assert row.question_snapshot['answer']==answer.correct_index
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:conn.execute(text('UPDATE life_exam_attempts SET correct = true WHERE user_id=1'))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:conn.execute(text('UPDATE life_exam_attempts SET elapsed_seconds=-1 WHERE user_id=1'))
    with engine.begin() as conn:conn.execute(text('DELETE FROM users WHERE id=1'))
    with sessions() as db:assert db.query(ExamAttemptRecord).count()==0
