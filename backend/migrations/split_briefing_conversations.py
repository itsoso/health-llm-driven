"""
将历史的「每日健康简报」单条对话按消息日期切分为每日独立对话.

背景:
  之前 _get_or_create_briefing_conversation 用唯一标题 "每日健康简报",
  导致一个用户从 03-31 起所有日报都堆在同一条 conversation,
  历史快照不可回溯, message 表无限膨胀.

操作:
  对每个 user_id, 找出所有 title='每日健康简报' (旧格式) 的对话,
  按 OpenClawMessage.created_at 的中国日期分组,
  每个日期新建一条 title='每日健康简报 · MM-DD' 的对话,
  把消息 reassign 到对应的新对话, 然后删掉旧的空对话.

幂等: 重复执行只会处理还残留旧标题的对话.

运行:
  ssh root@39.98.206.178
  cd /opt/health-app/backend && source venv/bin/activate
  python -m migrations.split_briefing_conversations  # dry-run
  python -m migrations.split_briefing_conversations --apply
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy import func

# Allow running as `python -m migrations.split_briefing_conversations` from backend/
sys.path.insert(0, ".")

from app.database import SessionLocal
from app.models.openclaw import OpenClawConversation, OpenClawMessage

CHINA_TZ = timezone(timedelta(hours=8))
OLD_TITLE = "每日健康简报"


def china_date(dt: datetime):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).date()


def split_for_user(db, user_id: int, apply: bool):
    legacy_convs = (
        db.query(OpenClawConversation)
        .filter(
            OpenClawConversation.user_id == user_id,
            OpenClawConversation.title == OLD_TITLE,
        )
        .all()
    )
    if not legacy_convs:
        return 0, 0

    total_msgs = 0
    new_convs_created = 0

    for legacy in legacy_convs:
        msgs = (
            db.query(OpenClawMessage)
            .filter(OpenClawMessage.conversation_id == legacy.id)
            .order_by(OpenClawMessage.created_at.asc())
            .all()
        )
        if not msgs:
            print(f"  [user={user_id}] legacy conv {legacy.id} 无消息, 删除")
            if apply:
                db.delete(legacy)
            continue

        # group by china date
        groups: dict = defaultdict(list)
        for m in msgs:
            d = china_date(m.created_at)
            groups[d].append(m)

        print(f"  [user={user_id}] legacy conv {legacy.id} 有 {len(msgs)} 条消息, 切为 {len(groups)} 天")

        for d, day_msgs in sorted(groups.items()):
            new_title = f"{OLD_TITLE} · {d.strftime('%m-%d')}"
            # 已存在则复用 (幂等)
            existing = (
                db.query(OpenClawConversation)
                .filter(
                    OpenClawConversation.user_id == user_id,
                    OpenClawConversation.title == new_title,
                )
                .first()
            )
            if existing:
                target = existing
                print(f"    {new_title}: 复用已存在 conv {existing.id}, 追加 {len(day_msgs)} 条")
            else:
                target = OpenClawConversation(user_id=user_id, title=new_title)
                if apply:
                    db.add(target)
                    db.flush()
                    # 把 created_at / updated_at 对齐到当天首条消息
                    target.created_at = day_msgs[0].created_at
                    target.updated_at = day_msgs[-1].created_at
                new_convs_created += 1
                print(f"    {new_title}: 新建 conv, 装入 {len(day_msgs)} 条")

            if apply:
                for m in day_msgs:
                    m.conversation_id = target.id
                total_msgs += len(day_msgs)

        if apply:
            # 旧对话清空后删除
            db.flush()
            remaining = (
                db.query(func.count(OpenClawMessage.id))
                .filter(OpenClawMessage.conversation_id == legacy.id)
                .scalar()
            )
            if remaining == 0:
                db.delete(legacy)
                print(f"  [user={user_id}] 删除空旧对话 {legacy.id}")
            else:
                print(f"  [user={user_id}] !!! 旧对话 {legacy.id} 仍有 {remaining} 条消息, 保留")

    if apply:
        db.commit()
    return new_convs_created, total_msgs


def main():
    apply = "--apply" in sys.argv
    if not apply:
        print("=== DRY RUN (使用 --apply 实际写库) ===\n")

    with SessionLocal() as db:
        user_ids = [
            uid for (uid,) in db.query(OpenClawConversation.user_id)
            .filter(OpenClawConversation.title == OLD_TITLE)
            .distinct()
            .all()
        ]
        if not user_ids:
            print("没有需要迁移的用户.")
            return
        print(f"待迁移用户: {user_ids}\n")

        total_new = 0
        total_msgs = 0
        for uid in user_ids:
            n, m = split_for_user(db, uid, apply)
            total_new += n
            total_msgs += m

        print(f"\n=== 完成 ===")
        print(f"用户数: {len(user_ids)}")
        print(f"新建对话: {total_new}")
        print(f"迁移消息: {total_msgs}")
        if not apply:
            print("\n上面是 dry-run, 重新加 --apply 执行.")


if __name__ == "__main__":
    main()
