"""Real PostgreSQL legacy DDL: wall times use an explicit compatibility basis.

The session timezone is a storage interpretation, not proof of the original
Garmin offset. Every test uses a private transactional schema and synthetic rows.
"""
from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.models.daily_health import WorkoutRecord
from app.services.agent_composed_read_completion import evaluate_composed_read_completion
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import CapabilityDecision, ToolExecutionResult
from app.services.agent_longitudinal_read import read_longitudinal_health_query
from app.services.agent_query_window import parse_query_window
from tests.test_recent_workout_read_regression import snapshot

BASIS = 'database_session_timezone_compatibility'


@pytest.fixture
def legacy_workout_db(db):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('Legacy timestamp semantics require isolated PostgreSQL')
    schema = 'test_legacy_workout_' + uuid4().hex
    try:
        db.execute(text(f'CREATE SCHEMA {schema}'))
        db.execute(text(f'CREATE TABLE {schema}.workout_records (LIKE public.workout_records INCLUDING ALL)'))
        db.execute(text(f'ALTER TABLE {schema}.workout_records ALTER COLUMN start_time TYPE timestamp without time zone USING start_time AT TIME ZONE \'UTC\''))
        db.execute(text(f'ALTER TABLE {schema}.workout_records ALTER COLUMN end_time TYPE timestamp without time zone USING end_time AT TIME ZONE \'UTC\''))
        db.execute(text(f'SET LOCAL search_path TO {schema}, public'))
        db.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
        assert db.execute(text('SHOW TimeZone')).scalar_one() == 'Asia/Shanghai'
        assert db.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema=:schema AND table_name='workout_records' AND column_name='start_time'"),{'schema':schema}).scalar_one() == 'timestamp without time zone'
        yield db
    finally:
        # DDL, SET LOCAL and rows all belong to this transaction; never leave
        # changed public DDL or connection timezone for another test.
        db.rollback()


@pytest.mark.parametrize('written_value',[
    datetime(2026,10,10,1,tzinfo=timezone.utc),  # aware GMT becomes 09:00 wall time
    datetime(2026,10,10,9),                  # legacy stored local wall time
])
def test_legacy_timestamp_reader_to_completion(legacy_workout_db,written_value):
    db=legacy_workout_db
    def row(stamp,owner=41,kind='running'):
        return WorkoutRecord(user_id=owner,workout_date=date(2026,10,9),
                             workout_type=kind,start_time=stamp,duration_seconds=1800)
    wanted=row(written_value)
    others=[row(datetime(2026,10,10,12)),row(datetime(2026,10,9,23,59)),
            row(datetime(2026,10,10,9),owner=42),row(datetime(2026,10,10,9),kind='cycling'),row(None)]
    db.add_all([wanted,*others]);db.flush()
    wanted_id=wanted.id
    # This proves real legacy DDL/driver semantics rather than a mocked row.
    stored=db.execute(text('SELECT start_time FROM workout_records WHERE id=:id'),{'id':wanted_id}).scalar_one()
    assert stored == datetime(2026,10,10,9) and stored.tzinfo is None
    db.expire_all()
    scope=resolve_owned_read_scope(snapshot('分析上午的跑步'))
    query=scope.query('workout')
    payload=read_longitudinal_health_query(db,41,'workout',parse_query_window(query),selection=scope.workout_selection)
    assert [entry['id'] for entry in payload['records']] == [wanted_id]
    record=payload['records'][0]
    assert datetime.fromisoformat(record['event_start_time']) == datetime(2026,10,10,1,tzinfo=timezone.utc)
    assert record['record_date']=='2026-10-10'
    assert record['event_time_basis']==BASIS
    assert record['event_storage_timezone']=='Asia/Shanghai'
    assert BASIS in payload['limitations']
    completion=evaluate_composed_read_completion(scope,[ToolExecutionResult('health_query',payload,
        decision=CapabilityDecision('allow','owned','health_query',query))])
    assert completion.complete
    assert completion.goals[0]['reason_code']=='query_verified'


def test_legacy_storage_zone_and_account_zone_are_distinct(legacy_workout_db):
    db=legacy_workout_db
    row=WorkoutRecord(user_id=41,workout_date=date(2026,10,10),workout_type='running',
                      start_time=datetime(2026,10,10,9))
    db.add(row);db.flush();wanted_id=row.id;db.expire_all()
    turn=snapshot('分析昨天晚上的跑步')
    turn=replace(turn,context=replace(turn.context,timezone='America/New_York',
                                     current_time=datetime(2026,10,10,16,tzinfo=timezone.utc)))
    scope=resolve_owned_read_scope(turn)
    payload=read_longitudinal_health_query(db,41,'workout',parse_query_window(scope.query('workout')),selection=scope.workout_selection)
    assert [r['id'] for r in payload['records']]==[wanted_id]
    assert payload['records'][0]['record_date']=='2026-10-09'
    assert payload['records'][0]['event_start_time']=='2026-10-09T21:00:00-04:00'
    assert payload['records'][0]['event_time_basis']==BASIS


@pytest.mark.parametrize('mutation', ['basis', 'zone', 'missing_zone', 'missing_limitation'])
def test_legacy_provenance_tampering_fails_completion(legacy_workout_db, mutation):
    db = legacy_workout_db
    db.add(WorkoutRecord(user_id=41, workout_date=date(2026, 10, 10),
                        workout_type='running', start_time=datetime(2026, 10, 10, 9)))
    db.flush()
    scope = resolve_owned_read_scope(snapshot('分析上午的跑步'))
    query = scope.query('workout')
    payload = read_longitudinal_health_query(db, 41, 'workout', parse_query_window(query),
                                            selection=scope.workout_selection)
    record = payload['records'][0]
    if mutation == 'basis':
        record['event_time_basis'] = 'original_device_offset'
    elif mutation == 'zone':
        record['event_storage_timezone'] = 'untrusted zone\n'
    elif mutation == 'missing_zone':
        record.pop('event_storage_timezone')
    else:
        payload['limitations'].remove(BASIS)
    completion = evaluate_composed_read_completion(scope, [ToolExecutionResult(
        'health_query', payload,
        decision=CapabilityDecision('allow', 'owned', 'health_query', query))])
    assert not completion.complete
    assert completion.goals[0]['reason_code'] == 'query_result_source_conflict'


def test_native_timestamptz_is_not_shifted_twice(legacy_workout_db):
    db = legacy_workout_db
    # Only the private, empty test table changes; the production-shaped public
    # schema remains untouched and the fixture rolls back this DDL too.
    db.execute(text("ALTER TABLE workout_records ALTER COLUMN start_time TYPE timestamp with time zone USING start_time AT TIME ZONE 'Asia/Shanghai'"))
    row = WorkoutRecord(user_id=41, workout_date=date(2026, 10, 9),
                        workout_type='running', start_time=datetime(2026, 10, 10, 1, tzinfo=timezone.utc))
    db.add(row)
    db.flush()
    scope = resolve_owned_read_scope(snapshot('分析上午的跑步'))
    query = scope.query('workout')
    payload = read_longitudinal_health_query(db, 41, 'workout', parse_query_window(query),
                                            selection=scope.workout_selection)
    assert len(payload['records']) == 1
    record = payload['records'][0]
    assert datetime.fromisoformat(record['event_start_time']) == datetime(2026, 10, 10, 1, tzinfo=timezone.utc)
    assert 'event_time_basis' not in record
    assert 'event_storage_timezone' not in record
    assert BASIS not in payload['limitations']
    completion = evaluate_composed_read_completion(scope, [ToolExecutionResult(
        'health_query', payload,
        decision=CapabilityDecision('allow', 'owned', 'health_query', query))])
    assert completion.complete
