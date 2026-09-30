#!/usr/bin/env python3
"""对账 体检 / medical_indicators → biomarker_observations (幂等, 自愈)。

对每个用户执行与 POST /chronic/biomarker-sync 相同的 sync_indicators_to_biomarkers:
  1. 每张体检 ingest_exam: 补上入库时漏接的体检、删除旧映射写错的行 (VLDL-C 当 LDL 等)、
     同一报告重复导入只留一行、exam 行覆盖同一次测量的 indicator_sync 行;
  2. 全部指标对账 indicator_sync 行: 每次测量 (code, 日, 值) 至多一行, 删除旧映射/重复行。

默认 dry-run: 整个对账在一个外层事务里执行 (服务函数里的 commit 只释放 SAVEPOINT), 结束时回滚,
只打印将发生的变更 —— id / code / 日期 / 来源 / 通用项目名, 不打印化验数值。每条删除都标注原因:
  superseded by #id      同一次测量由另一行保留
  mapping invalid: …     源项目现在被拒收 (名字不是该指标 / 单位量纲不符 / 数值不合理)
  remapped to …          源项目现在归到另一个指标
  source … gone          源 exam item / 指标已不存在
  DROPPED                以上都不是 —— 值会从标准层消失; --apply 遇到它会拒绝提交, 除非 --allow-dropped
--apply 才提交, 并让 Twin 缓存失效。

用法:
    python scripts/reconcile_biomarkers.py --user 3            # dry-run
    python scripts/reconcile_biomarkers.py --user 3 --apply    # 提交
    python scripts/reconcile_biomarkers.py --all               # 全部用户 dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.biomarkers.definitions import resolve_code  # noqa: E402
from app.biomarkers.normalize import rejection_reason  # noqa: E402
from app.models.biomarker_observation import BiomarkerObservation  # noqa: E402
from app.models.medical_exam import MedicalExamItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.biomarker_service import as_date  # noqa: E402
from app.services.biomarker_sync import sync_indicators_to_biomarkers  # noqa: E402


def _snapshot(db: Session, user_id: int) -> dict:
    rows = db.query(BiomarkerObservation).filter(BiomarkerObservation.user_id == user_id).all()
    return {
        r.id: {
            "code": r.code, "day": as_date(r.observed_at), "source": r.source, "item_id": r.source_exam_item_id,
            "value": r.value, "normalized_value": r.normalized_value, "flag": r.flag,
        }
        for r in rows
    }


def _measurement(row: dict) -> tuple:
    return row["code"], row["day"], row["normalized_value"]


def _explain_delete(db: Session, user_id: int, row: dict, after: dict) -> tuple[str, str, bool]:
    """(原因, 通用项目名, 是否 DROPPED)。"""
    for rid, other in after.items():
        if _measurement(other) == _measurement(row):
            return f"superseded by #{rid}", "", False
    if row["item_id"] is not None:
        item = db.get(MedicalExamItem, row["item_id"])
        if item is None:
            return "source exam item gone", "", False
        sources = [(item.item_name or item.item_code, item.value, item.unit)]
    else:
        found = db.execute(text(
            "SELECT name, value, unit, record_date FROM medical_indicators "
            "WHERE user_id = :uid AND value = :value"
        ), {"uid": user_id, "value": row["value"]}).fetchall()
        sources = [(name, value, unit) for name, value, unit, d in found if as_date(d) == row["day"]]
        if not sources:
            return "source indicator gone", "", False
        # 同日同值的别的指标不能把真丢失标成 remapped: 有名字属于本 code 的源时只看它们
        own = [src for src in sources if resolve_code(src[0] or "") == row["code"]]
        sources = own or sources
    for name, value, unit in sources:
        reason = rejection_reason(name, value, unit)
        if reason:
            return f"mapping invalid: {reason}", name or "", False
        code = resolve_code(name or "")
        if code != row["code"]:
            return f"remapped to {code}", name or "", False
    return "DROPPED", sources[0][0] or "", True


def run(
    conn: Connection, user_ids: list[int] | None, *, apply: bool, allow_dropped: bool = False,
) -> tuple[list[dict], bool]:
    """在 conn 上对账。返回 (每个用户的变更计划, 是否已提交)。

    apply=False 整体回滚; apply=True 但存在 DROPPED 且未 allow_dropped → 回滚 (拒绝提交)。
    """
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        if user_ids is None:
            user_ids = [uid for (uid,) in db.query(User.id).order_by(User.id).all()]
        plans = []
        for uid in user_ids:
            before = _snapshot(db, uid)
            result = sync_indicators_to_biomarkers(db, uid)
            after = _snapshot(db, uid)
            deleted = {}
            for rid in sorted(set(before) - set(after)):
                reason, item_name, dropped = _explain_delete(db, uid, before[rid], after)
                deleted[rid] = {**before[rid], "reason": reason, "item_name": item_name, "dropped": dropped}
            plans.append({
                "user_id": uid,
                "result": result,
                "deleted": deleted,
                "inserted": {i: after[i] for i in sorted(set(after) - set(before))},
                "changed": {i: (before[i], after[i]) for i in sorted(set(before) & set(after))
                            if before[i] != after[i]},
                "rows_before": len(before),
                "rows_after": len(after),
            })
    except Exception:
        db.close()
        outer.rollback()
        raise
    db.close()
    any_dropped = any(row["dropped"] for plan in plans for row in plan["deleted"].values())
    commit = apply and (allow_dropped or not any_dropped)
    if commit:
        outer.commit()
    else:
        outer.rollback()
    return plans, commit


def _row(row: dict) -> str:
    return f"{row['code']:<18} {row['day']} source={row['source']} item={row['item_id']}"


def _print_plan(plan: dict) -> None:
    print(f"user {plan['user_id']}: rows {plan['rows_before']} → {plan['rows_after']}  sync={plan['result']}")
    for rid, row in plan["deleted"].items():
        name = f" [{row['item_name']}]" if row["item_name"] else ""
        print(f"  - delete #{rid:<6} {_row(row)}{name} — {row['reason']}")
    for rid, (old, new) in plan["changed"].items():
        note = f"code {old['code']} → {new['code']}" if old["code"] != new["code"] else "value/flag refreshed"
        print(f"  ~ update #{rid:<6} {_row(new)}  ({note})")
    for rid, row in plan["inserted"].items():
        print(f"  + insert #{rid:<6} {_row(row)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--user", type=int, help="只对账该 user_id")
    target.add_argument("--all", action="store_true", help="对账全部用户")
    ap.add_argument("--apply", action="store_true", help="提交变更; 缺省 dry-run (回滚)")
    ap.add_argument("--allow-dropped", action="store_true", help="即使有 DROPPED 删除也提交 (需人工确认过)")
    args = ap.parse_args()

    from app.database import engine

    with engine.connect() as conn:
        plans, committed = run(
            conn, None if args.all else [args.user], apply=args.apply, allow_dropped=args.allow_dropped,
        )
    for plan in plans:
        _print_plan(plan)
    dropped = sum(row["dropped"] for plan in plans for row in plan["deleted"].values())

    if not args.apply:
        print(f"dry-run: 已回滚, 未写入任何变更 (DROPPED={dropped}; 加 --apply 提交)")
        return 0
    if not committed:
        print(f"refused: {dropped} 条 DROPPED 删除会让值从标准层消失; 核对后加 --allow-dropped 才提交。已回滚。")
        return 2
    from app.twin.cache import invalidate_twin
    for plan in plans:
        invalidate_twin(plan["user_id"])  # 失败自带 warning 日志; 5 分钟 TTL 兜底
    print("applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
