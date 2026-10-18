"""One server reminder per owner/date/slot; local pushes are retired in Mobile."""
import asyncio
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest
from app.models.medication import Medication
from app.models.user import User
from app.models.notification import NotificationLog, UserNotificationSetting
from app.services.notification.push_service import PushService


def _seed(db):
    users = [User(username=f'single_med_{i}', email=f'single_med_{i}@example.invalid', name='Synthetic') for i in range(2)]
    db.add_all(users); db.commit()
    for user in users:
        db.add(UserNotificationSetting(user_id=user.id, enabled=True, reminder_enabled=True, ios_push_enabled=True, ios_device_token='synthetic', quiet_hours_start='22:00', quiet_hours_end='09:00'))
    meds = [Medication(user_id=users[0].id, name='Synthetic A', is_active=True, reminder_times=['18:30', '18:30', '19:00']), Medication(user_id=users[0].id, name='Synthetic B', is_active=True, reminder_times=['18:30']), Medication(user_id=users[1].id, name='Synthetic C', is_active=True, reminder_times=['18:30'])]
    db.add_all(meds); db.commit()
    return users, meds


def test_scans_group_same_slot_and_retries_do_not_send_again(db):
    from app.tasks.notifications import scan_medication_reminders
    users, meds = _seed(db)
    clock = datetime(2026, 10, 18, 18, 30)
    @contextmanager
    def session(): yield db
    @contextmanager
    def fake_lock(*args): yield True
    fn = scan_medication_reminders.run
    with patch.dict(fn.__globals__, {'SessionLocal': session, 'get_china_now': lambda: clock, 'run_async': asyncio.run, 'medication_dispatch_lock': fake_lock}), patch('app.services.notification.push_service.get_china_now', return_value=clock), patch.object(PushService, '_send_ios', return_value={'success': True}) as send:
        first = fn()
        second = fn()
        assert send.call_count == 2  # two owners, not three medications
        assert first['sent'] == 2 and second['sent'] == 0
        rows = db.query(NotificationLog).all()
        assert len(rows) == 2
        mine = next(row for row in rows if row.user_id == users[0].id)
        assert mine.data['medication_ids'] == [meds[0].id, meds[1].id]
        assert mine.data['scheduled_date'] == '2026-10-18'
        assert mine.data['scheduled_time'] == '18:30'
        assert mine.data['deep_link'] == '/(tabs)/chat'
        assert 'category' not in mine.data  # grouped reminder cannot mark a single dose taken
        assert 'Synthetic' not in mine.content
        clock = datetime(2026, 10, 18, 19, 0)
        fn()
        assert send.call_count == 3  # next dose is not swallowed


def test_overlapping_scanner_does_not_dispatch_when_owner_is_locked(db):
    from app.tasks.notifications import scan_medication_reminders
    _seed(db)
    @contextmanager
    def session(): yield db
    @contextmanager
    def locked(*args): yield False
    fn = scan_medication_reminders.run
    with patch.dict(fn.__globals__, {'SessionLocal': session, 'get_china_now': lambda: datetime(2026, 10, 18, 18, 30), 'medication_dispatch_lock': locked}), patch.object(PushService, 'send_notification') as send:
        assert fn()['sent'] == 0
        send.assert_not_called()


def test_postgres_dispatch_lock_survives_service_commit_and_releases(db):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL connection locks required')
    from app.services.notification.medication_reminders import medication_dispatch_lock
    from sqlalchemy.orm import Session
    with Session(db.bind) as second:
        with medication_dispatch_lock(db, 17) as acquired:
            assert acquired
            db.commit()
            with medication_dispatch_lock(second, 17) as duplicate:
                assert not duplicate
            with medication_dispatch_lock(second, 18) as other_owner:
                assert other_owner
        with medication_dispatch_lock(second, 17) as released:
            assert released


def test_postgres_two_flush_workers_send_same_delayed_dose_once(db):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL concurrent claim required')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    users, _ = _seed(db)
    clock = datetime(2026, 10, 18, 18, 30)
    db.add(NotificationLog(user_id=users[0].id, notification_type='reminder', channel='multi', title='用药提醒', content='Synthetic', status='delayed', scheduled_at=clock, data={'reminder_type': 'medication', 'rule_id': 'medication_reminder.slot.2026-10-18.18:30'}))
    db.commit()
    barrier, seen = Barrier(2), local()
    def snapshot_barrier(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('SELECT') and 'notification_logs.status =' in statement and 'notification_logs.scheduled_at <=' in statement and not getattr(seen, 'first', False):
            seen.first = True
            barrier.wait(timeout=10)
    event.listen(db.bind, 'after_cursor_execute', snapshot_barrier)
    def worker():
        with Session(db.bind) as session:
            return asyncio.run(PushService(session).flush_delayed_pushes())
    try:
        with patch('app.services.notification.push_service.get_china_now', return_value=clock), patch.object(PushService, '_send_ios', return_value={'success': True}) as send, ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
            assert send.call_count == 1
            assert sum(r['succeeded'] for r in results) == 1
    finally:
        event.remove(db.bind, 'after_cursor_execute', snapshot_barrier)


def test_dispatch_lock_discards_connection_when_acquisition_outcome_is_unknown():
    from unittest.mock import MagicMock
    from app.services.notification.medication_reminders import medication_dispatch_lock
    session = MagicMock()
    engine = session.get_bind.return_value
    engine.dialect.name = 'postgresql'
    connection = engine.connect.return_value.__enter__.return_value
    connection.scalar.return_value = True
    connection.commit.side_effect = RuntimeError('connection lost after acquisition')
    with pytest.raises(RuntimeError):
        with medication_dispatch_lock(session, 17):
            pytest.fail('must not dispatch after uncertain lock acquisition')
    connection.invalidate.assert_called_once()
