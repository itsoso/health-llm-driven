"""Family push is a compact count; full details remain behind current grants."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.family_health import ReviewSchedule
from app.services.family_daily_check import run_family_daily_check, send_family_daily_brief
from app.services.notification.push_service import PushService
from tests.test_family_member_records import household


def test_multiple_overdue_items_are_counted_once_without_losing_detail(db, household):
    parent, child, _, outsider, membership, _ = household
    for i in range(5):
        db.add(ReviewSchedule(user_id=child.id, item_name=f'Synthetic review {i}', next_due_date=date.today()-timedelta(days=108)))
    db.add(ReviewSchedule(user_id=outsider.id, item_name='Private outsider', next_due_date=date.today()-timedelta(days=108)))
    db.commit()
    report = run_family_daily_check(db, parent.id)
    assert report['admin_alert_count'] == 5
    assert '5 项需关注' in report['admin_push_summary']
    assert '5 项复查已逾期' in report['admin_push_summary']
    assert '1 位成员' in report['admin_push_summary']
    assert len(report['admin_push_summary']) < 120
    for text in ('Child', '108', 'Synthetic review', 'Private outsider'):
        assert text not in report['admin_push_summary']
    assert len(next(r for r in report['member_reports'] if r['user_id'] == child.id)['alerts']) == 5
    membership.can_view = False; db.commit()
    assert run_family_daily_check(db, parent.id)['admin_alert_count'] == 0


@pytest.mark.asyncio
async def test_family_push_does_not_fallback_to_private_summary(db):
    report = {'admin_summary': 'Private diagnosis and review', 'member_reports': [], 'admin_alert_count': 2}
    send = AsyncMock(return_value={'success': True})
    with patch('app.services.family_daily_check.run_family_daily_check', return_value=report), patch.object(PushService, 'send_notification', send):
        await send_family_daily_brief(db, 7)
    assert 'Private' not in send.call_args.kwargs['content']
    assert send.call_args.kwargs['data']['deep_link'] == '/family'
