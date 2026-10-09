"""Synthetic owner/calendar/latest-running selection tests."""
from datetime import datetime, date, timezone
import pytest
from app.models.daily_health import WorkoutRecord
from app.services.health_read import read_latest_garmin_running_review


def add(db, owner, *, hour=2, day=9, kind='running', source='garmin', timed=True, distance=3000):
    row = WorkoutRecord(user_id=owner, workout_date=date(2026,10,day), workout_type=kind,
        source=source, external_id=f'{owner}-{day}-{hour}-{kind}-{source}',
        start_time=datetime(2026,10,day,hour,tzinfo=timezone.utc) if timed else None,
        end_time=datetime(2026,10,day,hour,30,tzinfo=timezone.utc) if timed else None,
        duration_seconds=1800,distance_meters=distance)
    db.add(row);db.commit();return row


def read(db, owner):
    return read_latest_garmin_running_review(db, owner,
        reference_now=datetime(2026,10,9,8,tzinfo=timezone.utc), timezone='Asia/Shanghai',
        reported_distance_km=3)


def test_selects_only_today_owned_garmin_running(db, auth_user_and_headers):
    user,_=auth_user_and_headers
    add(db,user.id,day=8);add(db,user.id,hour=3,kind='cycling')
    add(db,user.id,hour=4,source='manual');add(db,user.id,hour=10)
    expected=add(db,user.id,hour=2)
    result=read(db,user.id)
    assert result['availability']=='available'
    assert result['record']['id']==expected.id
    assert result['selection']=='latest_recorded_running_today'
    assert result['freshness']=='existing_record_not_sync_proof'
    assert result['matches_reported_distance'] is True
    assert read(db,user.id+10000)['availability']=='no_data'


def test_unknown_timestamp_cannot_fall_back_to_older_run(db,auth_user_and_headers):
    user,_=auth_user_and_headers;add(db,user.id,hour=2);add(db,user.id,hour=3,timed=False)
    result=read(db,user.id)
    assert result['availability']=='ambiguous'
    assert result['record'] is None


def test_empty_day_cannot_reuse_yesterdays_run(db,auth_user_and_headers):
    user,_=auth_user_and_headers;add(db,user.id,day=8)
    assert read(db,user.id)['availability']=='no_data'


@pytest.mark.parametrize('zone,start,stored_day', [
    ('Asia/Shanghai', datetime(2026,10,8,16,30,tzinfo=timezone.utc), date(2026,10,8)),
    ('America/Los_Angeles', datetime(2026,10,10,1,30,tzinfo=timezone.utc), date(2026,10,10)),
])
def test_absolute_start_selects_local_day_despite_utc_fallback_date(db,auth_user_and_headers,zone,start,stored_day):
    from datetime import timedelta
    user,_=auth_user_and_headers
    row=WorkoutRecord(user_id=user.id,workout_date=stored_day,workout_type='running',
        source='garmin',start_time=start,end_time=start+timedelta(minutes=30),distance_meters=3000)
    db.add(row);db.commit()
    reference=(datetime(2026,10,9,2,tzinfo=timezone.utc) if zone=='Asia/Shanghai'
               else datetime(2026,10,10,3,tzinfo=timezone.utc))
    result=read_latest_garmin_running_review(db,user.id,reference_now=reference,timezone=zone)
    assert result['availability']=='available'
    assert result['record']['id']==row.id
    assert result['start_date']=='2026-10-09'
    assert result['record']['record_date']=='2026-10-09'


def test_stored_local_day_does_not_authorize_outside_absolute_day(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    row=add(db,user.id,day=8,hour=15)
    row.workout_date=date(2026,10,9);db.commit()
    assert read(db,user.id)['availability']=='no_data'


def test_missing_end_with_utc_fallback_date_is_ambiguous(db,auth_user_and_headers):
    user,_=auth_user_and_headers
    row=add(db,user.id,day=8,hour=17)
    row.end_time=None;db.commit()
    assert read(db,user.id)['availability']=='ambiguous'
