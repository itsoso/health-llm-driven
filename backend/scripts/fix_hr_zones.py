"""
批量修复运动记录的心率区间数据
对于有心率数据但心率区间为空的记录，从心率时间序列计算心率区间
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from typing import List, Dict
from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord
from app.models.user import User

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_hr_zones_from_samples(
    hr_samples: List[Dict[str, int]],
    max_hr: int = 180
) -> List[int]:
    """
    从心率采样数据计算心率区间时长

    Args:
        hr_samples: 心率采样数据 [{"time": seconds, "hr": bpm}, ...]
        max_hr: 最大心率（用于计算区间）

    Returns:
        [zone1_seconds, zone2_seconds, zone3_seconds, zone4_seconds, zone5_seconds]
    """
    if not hr_samples:
        return [0, 0, 0, 0, 0]

    # 心率区间定义（基于最大心率百分比）
    zone_thresholds = [
        (0, max_hr * 0.60),              # Zone 1: 50-60%
        (max_hr * 0.60, max_hr * 0.70),  # Zone 2: 60-70%
        (max_hr * 0.70, max_hr * 0.80),  # Zone 3: 70-80%
        (max_hr * 0.80, max_hr * 0.90),  # Zone 4: 80-90%
        (max_hr * 0.90, max_hr * 1.2),   # Zone 5: 90-100%+
    ]

    zone_seconds = [0, 0, 0, 0, 0]

    # 计算每个采样点所在的区间
    for i in range(len(hr_samples)):
        hr = hr_samples[i]["hr"]

        # 计算该采样点代表的时长（到下一个采样点的时间）
        if i < len(hr_samples) - 1:
            duration = hr_samples[i + 1]["time"] - hr_samples[i]["time"]
        else:
            # 最后一个点，使用前一个间隔
            if i > 0:
                duration = hr_samples[i]["time"] - hr_samples[i - 1]["time"]
            else:
                duration = 1  # 只有一个点，假设1秒

        # 确定心率所在区间
        for zone_idx, (min_hr, max_hr_threshold) in enumerate(zone_thresholds):
            if min_hr <= hr < max_hr_threshold:
                zone_seconds[zone_idx] += duration
                break

    return zone_seconds


def fix_workout_hr_zones(db, user_id: int = None, dry_run: bool = False):
    """
    修复运动记录的心率区间数据

    Args:
        db: 数据库会话
        user_id: 用户ID（可选，如果不指定则处理所有用户）
        dry_run: 是否为试运行（不实际更新数据库）
    """
    # 构建查询
    query = db.query(WorkoutRecord).filter(
        WorkoutRecord.heart_rate_data.isnot(None),
        WorkoutRecord.heart_rate_data != '',
        WorkoutRecord.avg_heart_rate.isnot(None),
        WorkoutRecord.avg_heart_rate > 0
    )

    if user_id:
        query = query.filter(WorkoutRecord.user_id == user_id)

    records = query.all()

    logger.info(f"找到 {len(records)} 条有心率数据的运动记录")

    fixed_count = 0
    skipped_count = 0
    error_count = 0

    for record in records:
        try:
            # 检查是否需要修复
            total_zone_seconds = sum([
                record.hr_zone_1_seconds or 0,
                record.hr_zone_2_seconds or 0,
                record.hr_zone_3_seconds or 0,
                record.hr_zone_4_seconds or 0,
                record.hr_zone_5_seconds or 0
            ])

            if total_zone_seconds > 0:
                logger.debug(f"运动记录 {record.id} 已有心率区间数据，跳过")
                skipped_count += 1
                continue

            # 解析心率数据
            try:
                hr_samples = json.loads(record.heart_rate_data)
            except json.JSONDecodeError:
                logger.warning(f"运动记录 {record.id} 心率数据格式错误")
                error_count += 1
                continue

            if not hr_samples or not isinstance(hr_samples, list):
                logger.warning(f"运动记录 {record.id} 心率数据为空或格式错误")
                error_count += 1
                continue

            # 计算心率区间
            max_hr = record.max_heart_rate or 180
            zone_seconds = calculate_hr_zones_from_samples(hr_samples, max_hr)

            logger.info(
                f"运动记录 {record.id} ({record.workout_name}): "
                f"计算心率区间 = {zone_seconds}, "
                f"总时长 = {record.duration_seconds}s, "
                f"区间总和 = {sum(zone_seconds)}s"
            )

            # 验证计算结果的合理性
            if record.duration_seconds:
                zone_total = sum(zone_seconds)
                diff_ratio = abs(zone_total - record.duration_seconds) / record.duration_seconds
                if diff_ratio > 0.2:  # 差异超过20%
                    logger.warning(
                        f"运动记录 {record.id} 心率区间总和与运动时长差异较大: "
                        f"{zone_total}s vs {record.duration_seconds}s (差异 {diff_ratio*100:.1f}%)"
                    )

            # 更新数据库
            if not dry_run:
                record.hr_zone_1_seconds = zone_seconds[0]
                record.hr_zone_2_seconds = zone_seconds[1]
                record.hr_zone_3_seconds = zone_seconds[2]
                record.hr_zone_4_seconds = zone_seconds[3]
                record.hr_zone_5_seconds = zone_seconds[4]
                db.commit()
                logger.info(f"✓ 运动记录 {record.id} 心率区间已更新")
            else:
                logger.info(f"[试运行] 运动记录 {record.id} 将更新心率区间")

            fixed_count += 1

        except Exception as e:
            logger.error(f"处理运动记录 {record.id} 失败: {e}", exc_info=True)
            error_count += 1
            if not dry_run:
                db.rollback()

    logger.info(f"\n{'='*60}")
    logger.info(f"修复完成:")
    logger.info(f"  - 已修复: {fixed_count} 条")
    logger.info(f"  - 已跳过: {skipped_count} 条")
    logger.info(f"  - 失败: {error_count} 条")
    logger.info(f"{'='*60}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='批量修复运动记录的心率区间数据')
    parser.add_argument('--user-id', type=int, help='用户ID（可选）')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不实际更新数据库')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.user_id:
            user = db.query(User).filter_by(id=args.user_id).first()
            if not user:
                logger.error(f"用户 {args.user_id} 不存在")
                return
            logger.info(f"开始修复用户 {user.email} (ID: {user.id}) 的运动记录")
        else:
            logger.info("开始修复所有用户的运动记录")

        if args.dry_run:
            logger.info("【试运行模式】不会实际更新数据库")

        fix_workout_hr_zones(db, args.user_id, args.dry_run)

    except Exception as e:
        logger.error(f"修复失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
