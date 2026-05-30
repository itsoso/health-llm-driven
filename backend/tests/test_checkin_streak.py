"""checkin /stats current_streak 计算回归测试.

之前 get_stats 把 current_streak 硬编码成 0 (app/api/checkin.py), 导致 mobile
首页"连续 N 天"永远显示 0 —— 假成功. 这里覆盖真实的连续天数计算:
今天打卡 → 以今天结尾; 今天没打但昨天打了 → 以昨天结尾不算断; 中间断一天 → streak 截断.
"""
from datetime import date, timedelta

from app.models.checkin import CheckinTemplate, CheckinRecord


def _make_template(db, user_id: int) -> CheckinTemplate:
    tmpl = CheckinTemplate(
        user_id=user_id,
        name="洗鼻",
        category="health",
        icon="✅",
        default_target=1.0,
        unit="次",
        is_active=True,
        is_archived=False,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


def _seed_checkins(db, user_id: int, template_id: int, days_ago: list[int]) -> None:
    """为指定的"几天前"各插一条打卡记录 (days_ago=[0,1,2] 即今天/昨天/前天)."""
    today = date.today()
    for d in days_ago:
        db.add(
            CheckinRecord(
                template_id=template_id,
                user_id=user_id,
                checkin_date=today - timedelta(days=d),
                value=1.0,
            )
        )
    db.commit()


def _get_streak(client, headers) -> tuple[int, int]:
    resp = client.get("/api/v1/checkin/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["current_streak"], data["best_streak"]


def test_streak_zero_when_no_checkins(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    _make_template(db, user.id)  # 有模板但无记录
    current, best = _get_streak(client, headers)
    assert current == 0
    assert best == 0


def test_streak_counts_consecutive_days_ending_today(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    tmpl = _make_template(db, user.id)
    _seed_checkins(db, user.id, tmpl.id, [0, 1, 2])  # 今天 + 昨天 + 前天
    current, best = _get_streak(client, headers)
    assert current == 3
    assert best >= 3


def test_streak_survives_when_today_not_yet_checked_in(client, auth_user_and_headers, db):
    """今天还没打卡, 但昨天+前天打了 —— streak 以昨天结尾, 仍为 2 (不算断)."""
    user, headers = auth_user_and_headers
    tmpl = _make_template(db, user.id)
    _seed_checkins(db, user.id, tmpl.id, [1, 2])  # 昨天 + 前天, 今天空
    current, _ = _get_streak(client, headers)
    assert current == 2


def test_streak_breaks_on_gap(client, auth_user_and_headers, db):
    """今天 + 昨天连续, 但前天断了 —— current_streak 只数到 2."""
    user, headers = auth_user_and_headers
    tmpl = _make_template(db, user.id)
    _seed_checkins(db, user.id, tmpl.id, [0, 1, 3, 4])  # 今天/昨天连续; 第2天断; 再往前不计入 current
    current, _ = _get_streak(client, headers)
    assert current == 2


def test_streak_is_zero_when_last_checkin_too_old(client, auth_user_and_headers, db):
    """最后一次打卡在前天 (今天和昨天都没打) —— 连续已断, current_streak=0.

    注: best_streak 取自 template.best_streak 字段 (由打卡写入路径 _update_streak
    维护), 本测试直接 seed CheckinRecord 不走该路径, 故 best 仍为 0 —— 这是诚实
    行为: /stats 不从历史回算 best, 只反映已落库的字段, 不假装更高.
    """
    user, headers = auth_user_and_headers
    tmpl = _make_template(db, user.id)
    _seed_checkins(db, user.id, tmpl.id, [2, 3, 4])  # 连续 3 天但都在 2 天前结束
    current, best = _get_streak(client, headers)
    assert current == 0
    assert best == 0
