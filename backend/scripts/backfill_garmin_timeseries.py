#!/usr/bin/env python3
"""
P1a 回填脚本：对指定用户回填最近 N 天的 Garmin 时序与扩展字段。

用途：
  - 新字段（training_readiness/status/endurance 等）上线后，历史数据需要补录
  - 新时序表（respiration/hrv/stress）上线后，历史时序数据需要 backfill

使用：
  python scripts/backfill_garmin_timeseries.py --user-id 3 --days 30
  python scripts/backfill_garmin_timeseries.py --user-id 3 --start 2026-04-01 --end 2026-04-23
  python scripts/backfill_garmin_timeseries.py --user-id 3 --days 7 --dry-run

注意：
  - 幂等：每个日期会 delete + bulk_save_objects，重跑安全
  - 失败续跑：某天失败会 warn，继续下一天
  - 进度逐日打印；可 Ctrl+C 中断
  - 依赖：用户必须已在 garmin_credentials 中有效凭据
"""
import argparse
import logging
import sys
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path

# 确保能 import app.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.auth import GarminCredentialService
from app.services.data_collection.garmin_connect import GarminConnectService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill Garmin timeseries for a user")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--days", type=int, default=None, help="最近 N 天（与 --start/--end 二选一）")
    parser.add_argument("--start", type=str, default=None, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="只打印会处理的日期，不实际同步")
    parser.add_argument("--sleep", type=float, default=1.0, help="每日间隔秒（避免 Garmin 限流）")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过 GarminData 已有训练就绪度的日期（仅补新字段时用）",
    )
    return parser.parse_args()


def resolve_dates(args) -> list[date]:
    if args.days is not None:
        end = date.today()
        start = end - timedelta(days=args.days - 1)
    else:
        if not args.start or not args.end:
            raise SystemExit("必须指定 --days 或 --start+--end")
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if start > end:
        raise SystemExit("start > end")
    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def main() -> int:
    args = parse_args()
    dates = resolve_dates(args)

    logger.info(f"[backfill] user_id={args.user_id} 共 {len(dates)} 天 "
                f"({dates[0]} → {dates[-1]}) dry_run={args.dry_run}")

    if args.dry_run:
        for d in dates:
            print(f"  would sync {d}")
        return 0

    db: Session = SessionLocal()
    try:
        cred = GarminCredentialService.get_decrypted_credentials(db, args.user_id)
        if not cred:
            logger.error(f"用户 {args.user_id} 没有可用的 Garmin 凭据（可能未录入/解密失败）")
            return 2

        service = GarminConnectService(
            email=cred["email"],
            password=cred["password"],
            is_cn=cred.get("is_cn", False),
            user_id=args.user_id,
        )

        success = 0
        failure = 0
        skipped = 0
        for i, d in enumerate(dates, 1):
            if args.skip_existing:
                from app.models.daily_health import GarminData
                existing = db.query(GarminData).filter(
                    GarminData.user_id == args.user_id,
                    GarminData.record_date == d,
                    GarminData.training_readiness_score.isnot(None),
                ).first()
                if existing:
                    skipped += 1
                    logger.info(f"[{i}/{len(dates)}] {d} 已有 training_readiness，跳过")
                    continue

            logger.info(f"[{i}/{len(dates)}] 同步 {d}...")
            try:
                result = service.sync_daily_data(db, args.user_id, d)
                if result:
                    success += 1
                    logger.info(f"[{i}/{len(dates)}] {d} ✓ "
                                f"TR={result.training_readiness_score} "
                                f"status={result.training_status} "
                                f"hydration={result.hydration_ml}")
                else:
                    failure += 1
                    logger.warning(f"[{i}/{len(dates)}] {d} 返回 None")
            except KeyboardInterrupt:
                logger.warning("用户中断，退出")
                break
            except Exception as e:
                failure += 1
                logger.exception(f"[{i}/{len(dates)}] {d} 失败: {e}")

            if args.sleep > 0 and i < len(dates):
                _time.sleep(args.sleep)

        logger.info(f"=== 完成 ===  成功:{success}  失败:{failure}  跳过:{skipped}")
        return 0 if failure == 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
