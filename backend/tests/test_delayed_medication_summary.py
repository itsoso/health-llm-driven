"""Quiet-hour catch-up is one delivery with every original slot auditable."""
import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from app.models.notification import NotificationLog
from app.services.notification.push_service import PushService
from tests.test_medication_reminder_single_delivery import _seed


def _queue(db, owner, times=('07:30', '08:00', '08:30'), day='2026-10-20'):
    rows = [NotificationLog(
        user_id=owner, notification_type='reminder', channel='multi', title='用药提醒',
        content=f'有用药事项到点了（{time}）', status='delayed',
        scheduled_at=datetime(2026, 10, 20, 9),
        data={'reminder_type': 'medication', 'medication_ids': [1],
              'scheduled_date': day, 'scheduled_time': time,
              'scheduled_timezone': 'Asia/Shanghai', 'deep_link': '/(tabs)/chat',
              'rule_id': f'medication_reminder.slot.{owner}.{day}.{time}'},
    ) for time in times]
    db.add_all(rows); db.commit()
    return rows


@pytest.mark.parametrize('channel_ok', [True, False])
def test_catchup_one_delivery_preserves_all_slots_and_result(db, channel_ok):
    users, _ = _seed(db)
    rows = _queue(db, users[0].id)
    captured = []
    def channel(*args):
        wire = args[-1]
        db.expire_all()
        assert all(db.get(NotificationLog, r.id).status == 'pending' for r in rows)
        assert 'full_content' not in wire
        assert 'coalesced_log_ids' not in wire
        assert 'coalesced_original' not in wire
        assert wire['reminder_type'] == 'medication_summary'
        assert wire['deep_link'] == f'/notification-history?detailId={rows[0].id}'
        captured.append(wire)
        return {'success': channel_ok}
    with patch('app.services.notification.push_service.get_china_now', return_value=datetime(2026, 10, 20, 9)), patch.object(PushService, '_send_ios', side_effect=channel) as send:
        result = asyncio.run(PushService(db).flush_delayed_pushes())
        assert send.call_count == 1
        asyncio.run(PushService(db).flush_delayed_pushes())
        assert send.call_count == 1
    db.expire_all()
    assert all(r.status == ('sent' if channel_ok else 'failed') for r in rows)
    assert result['succeeded' if channel_ok else 'failed'] == 3
    assert '3 个时段' in rows[0].content
    assert '延后' in rows[0].content and '到点了' not in rows[0].content
    for time in ('07:30', '08:00', '08:30'):
        assert time in rows[0].data['full_content']
    assert '2026-10-20' in rows[0].data['full_content']
    assert rows[1].data['coalesced_into'] == rows[0].id
    assert rows[1].data['scheduled_time'] == '08:00'
    assert rows[0].data['coalesced_original']['data']['scheduled_time'] == '07:30'
    assert rows[0].data['coalesced_original']['data']['medication_ids'] == [1]
    from app.services.notification.detail import read_notification_detail
    assert read_notification_detail(db, users[1].id, rows[0].id) is None
    detail = read_notification_detail(db, users[0].id, rows[0].id)
    assert detail['content'] == rows[0].data['full_content']
    from app.models.medication import MedicationLog
    assert db.query(MedicationLog).count() == 0


def test_catchup_never_groups_owners_dates_or_critical_alerts(db):
    users, _ = _seed(db)
    first = _queue(db, users[0].id)
    second = _queue(db, users[1].id)
    prior = _queue(db, users[0].id, ('07:30',), day='2026-10-19')
    alert = NotificationLog(user_id=users[0].id, notification_type='health_alert', channel='multi', title='紧急提醒', content='需要立即关注', status='delayed', scheduled_at=datetime(2026, 10, 20, 9), data={'severity': 'critical', 'rule_id': 'vitals.synthetic'})
    db.add(alert); db.commit()
    with patch('app.services.notification.push_service.get_china_now', return_value=datetime(2026, 10, 20, 9)), patch.object(PushService, '_send_ios', return_value={'success': True}) as send:
        asyncio.run(PushService(db).flush_delayed_pushes())
        assert send.call_count == 4
    assert first[0].data['coalesced_log_ids'] == [r.id for r in first]
    assert second[0].data['coalesced_log_ids'] == [r.id for r in second]
    assert 'coalesced_into' not in prior[0].data
    assert alert.status == 'sent'


def test_custom_quiet_hours_redelay_all_original_slots_then_send_once(db):
    users, _ = _seed(db)
    rows = _queue(db, users[0].id)
    svc = PushService(db)
    settings = svc.get_user_settings(users[0].id)
    settings.quiet_hours_end = '12:00'; db.commit()
    clock = datetime(2026, 10, 20, 9)
    with patch('app.services.notification.push_service.get_china_now', side_effect=lambda: clock), patch.object(PushService, '_send_ios', return_value={'success': True}) as send:
        result = asyncio.run(svc.flush_delayed_pushes())
        assert result['redelayed'] == 3
        send.assert_not_called()
        assert all(r.status == 'delayed' and r.data['reminder_type'] == 'medication' for r in rows)
        clock = datetime(2026, 10, 20, 12)
        asyncio.run(svc.flush_delayed_pushes())
        assert send.call_count == 1


def test_uncertain_group_delivery_is_not_retried_or_marked_sent(db):
    class DeliveryInterrupted(BaseException):
        pass
    users, _ = _seed(db)
    rows = _queue(db, users[0].id)
    with patch('app.services.notification.push_service.get_china_now', return_value=datetime(2026, 10, 20, 9)), patch.object(PushService, '_send_ios', side_effect=DeliveryInterrupted) as send:
        with pytest.raises(DeliveryInterrupted):
            asyncio.run(PushService(db).flush_delayed_pushes())
        db.expire_all()
        assert all(r.status == 'pending' and r.sent_at is None for r in rows)
        asyncio.run(PushService(db).flush_delayed_pushes())
        assert send.call_count == 1


def test_existing_receipt_is_excluded_before_catchup_group_is_built(db):
    users, _ = _seed(db)
    rows = _queue(db, users[0].id)
    db.add(NotificationLog(user_id=users[0].id, notification_type='reminder', channel='multi', title='用药提醒', status='sent', sent_at=datetime(2026, 10, 20, 9), data=dict(rows[0].data)))
    db.commit()
    with patch('app.services.notification.push_service.get_china_now', return_value=datetime(2026, 10, 20, 9)), patch.object(PushService, '_send_ios', return_value={'success': True}) as send:
        result = asyncio.run(PushService(db).flush_delayed_pushes())
        assert send.call_count == 1
        assert result['deduped'] == 1
        assert result['succeeded'] == 2
    assert rows[0].error_message == 'dedup'
    assert rows[1].data['coalesced_log_ids'] == [rows[1].id, rows[2].id]
    assert '07:30' not in rows[1].data['full_content']


@pytest.mark.parametrize('override', [
    {'severity': 'critical'}, {'severity': 'high'},
    {'scheduled_date': '2026-02-30'}, {'scheduled_time': '25:00'},
    {'scheduled_timezone': 'invalid/timezone'}, {'medication_ids': [True]},
    {'medication_ids': []}, {'rule_id': 'untrusted'},
    {'reminder_type': 'pre_event'},
])
def test_unknown_and_nonroutine_payloads_never_join_summary(override):
    from types import SimpleNamespace
    from app.services.notification.push_service import _delayed_medication_group_key
    data = {'reminder_type': 'medication', 'medication_ids': [1],
            'scheduled_date': '2026-10-20', 'scheduled_time': '07:30',
            'scheduled_timezone': 'Asia/Shanghai',
            'rule_id': 'medication_reminder.slot.7.2026-10-20.07:30'}
    log = SimpleNamespace(user_id=7, notification_type='reminder', data={**data, **override}, scheduled_at=datetime(2026, 10, 20, 9))
    assert _delayed_medication_group_key(log) is None


def test_postgres_overlapping_group_claims_deliver_only_once(db):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL concurrent compare-and-set required')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    users, _ = _seed(db)
    _queue(db, users[0].id)
    barrier, seen = Barrier(2), local()
    def synchronized_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('SELECT') and 'notification_logs.scheduled_at <=' in statement and not getattr(seen, 'first', False):
            seen.first = True
            barrier.wait(timeout=15)
    event.listen(db.bind, 'after_cursor_execute', synchronized_snapshot)
    def worker(_):
        with Session(db.bind) as session:
            return asyncio.run(PushService(session).flush_delayed_pushes())
    try:
        with patch('app.services.notification.push_service.get_china_now', return_value=datetime(2026, 10, 20, 9)), patch.object(PushService, '_send_ios', return_value={'success': True}) as send, ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
            assert send.call_count == 1
            assert sum(r['succeeded'] for r in results) == 3
    finally:
        event.remove(db.bind, 'after_cursor_execute', synchronized_snapshot)
