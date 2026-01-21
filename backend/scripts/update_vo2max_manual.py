#!/usr/bin/env python3
"""
手动更新用户的 VO2Max 数据（从运动记录同步到每日数据）
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord, GarminData
from app.utils.timezone import get_china_today

def update_vo2max_for_user(user_id: int, days: int = 30):
    """更新指定用户的VO2 max数据"""
    db = SessionLocal()
    try:
        end_date = get_china_today()
        start_date = end_date - timedelta(days=days)
        
        # 查找最近有 VO2Max 数据的跑步记录
        workout_with_vo2max = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_date,
            WorkoutRecord.vo2max.isnot(None)
        ).order_by(WorkoutRecord.workout_date.desc()).first()
        
        if workout_with_vo2max and workout_with_vo2max.vo2max:
            latest_vo2max = workout_with_vo2max.vo2max
            print(f"✓ 找到VO2Max数据: {latest_vo2max} (来自 {workout_with_vo2max.workout_date} 的 {workout_with_vo2max.workout_type} 运动)")
            
            # 更新最近的 Garmin 每日数据
            garmin_records = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= start_date
            ).all()
            
            updated_count = 0
            for record in garmin_records:
                if record.vo2max_running != latest_vo2max:
                    record.vo2max_running = latest_vo2max
                    updated_count += 1
                    print(f"  - 更新 {record.record_date} 的记录: {record.vo2max_running} -> {latest_vo2max}")
            
            if updated_count > 0:
                db.commit()
                print(f"\n✓ 成功更新了 {updated_count} 条记录的VO2Max")
            else:
                print("\n⚠ 没有需要更新的记录（可能已经是最新值）")
        else:
            print(f"⚠ 最近 {days} 天没有找到包含 VO2Max 的运动记录")
            
    except Exception as e:
        print(f"✗ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    print(f"更新用户 {user_id} 的VO2Max数据（最近 {days} 天）...")
    update_vo2max_for_user(user_id, days)
