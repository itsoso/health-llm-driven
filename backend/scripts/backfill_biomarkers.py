#!/usr/bin/env python3
"""回填历史化验 → BiomarkerObservation (PRD P1 接通 + P0③ 双源打通).

把已有数据归一化落库为标准观测,两源都补齐:
  - MedicalExam/MedicalExamItem(结构化体检项)
  - medical_indicators(OCR/图片/手动/CSV 的统一化验存储)
幂等可重跑(exam 按 source_exam_item_id 去重;indicators 按同 user+code+日历日 去重,
且让位于已有的结构化来源)。

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
from app.services.biomarker_sync import ensure_biomarkers  # noqa: E402


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

        total_exam = 0
        total_sync = 0
        for uid in user_ids:
            r = ensure_biomarkers(db, uid)
            total_exam += r["exam_observations"]
            total_sync += r["written"]
            if r["exam_observations"] or r["written"]:
                print(
                    f"  user {uid}: exam={r['exam_observations']} "
                    f"indicators_written={r['written']} skipped={r['skipped']}"
                )
        print(
            f"backfill done: exam={total_exam} indicators={total_sync} "
            f"observations across {len(user_ids)} users"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
