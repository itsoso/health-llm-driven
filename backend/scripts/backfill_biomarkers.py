#!/usr/bin/env python3
"""回填历史体检 → BiomarkerObservation (PRD P1 接通).

把已有 MedicalExam/MedicalExamItem 归一化落库为标准观测。幂等可重跑
(observe_exam_item 按 source_exam_item_id 去重更新)。

用法:
    python scripts/backfill_biomarkers.py            # 全部用户
    python scripts/backfill_biomarkers.py --user 3   # 单个用户
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.biomarker_service import backfill_user  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", type=int, default=None, help="只回填该 user_id; 缺省回填全部")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.user is not None:
            user_ids = [args.user]
        else:
            user_ids = [u.id for u in db.query(User.id).all()]

        total = 0
        for uid in user_ids:
            n = backfill_user(db, uid)
            total += n
            if n:
                print(f"  user {uid}: {n} observations")
        print(f"backfill done: {total} observations across {len(user_ids)} users")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
