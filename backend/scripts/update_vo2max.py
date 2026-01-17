#!/usr/bin/env python3
"""
更新用户的 VO2Max 数据

用法:
    python scripts/update_vo2max.py --user-id 1 --days 7
    python scripts/update_vo2max.py --check  # 只检查，不更新
"""
import argparse
import sys
import os
from datetime import date, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models.daily_health import GarminDailyData
from app.models.user import User


def check_vo2max_data(db: Session, user_id: int, days: int = 30):
    """检查用户最近的 VO2Max 数据"""
    from app.models.daily_health import WorkoutRecord
    
    start_date = date.today() - timedelta(days=days)
    
    # 检查 Garmin 每日数据
    records = db.query(GarminDailyData).filter(
        GarminDailyData.user_id == user_id,
        GarminDailyData.record_date >= start_date
    ).order_by(GarminDailyData.record_date.desc()).all()
    
    print(f"\n用户 {user_id} 最近 {days} 天的 Garmin 每日数据 VO2Max:")
    print("-" * 60)
    
    has_vo2max = False
    for r in records:
        vo2_str = f"{r.vo2max_running:.1f}" if r.vo2max_running else "无"
        print(f"  {r.record_date}: 跑步VO2Max={vo2_str}")
        if r.vo2max_running:
            has_vo2max = True
    
    if not has_vo2max:
        print("\n⚠️ Garmin 每日数据中没有 VO2Max")
    
    # 检查运动记录中的 VO2Max
    workouts = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == user_id,
        WorkoutRecord.workout_date >= start_date
    ).order_by(WorkoutRecord.workout_date.desc()).all()
    
    print(f"\n用户 {user_id} 最近 {days} 天的运动记录 VO2Max:")
    print("-" * 60)
    
    workout_has_vo2max = False
    for w in workouts:
        vo2_str = f"{w.vo2max:.1f}" if w.vo2max else "无"
        print(f"  {w.workout_date} {w.workout_type}: VO2Max={vo2_str}, 名称={w.workout_name}")
        if w.vo2max:
            workout_has_vo2max = True
    
    if not workout_has_vo2max:
        print("\n⚠️ 运动记录中没有 VO2Max 数据")
    
    return records


def sync_vo2max_from_garmin(db: Session, user_id: int, days: int = 7):
    """从 Garmin 重新同步 VO2Max 数据"""
    from app.services.data_collection.garmin_connect import GarminConnectService
    from app.services.auth import GarminCredentialService
    
    # 获取凭证
    cred_service = GarminCredentialService()
    credentials = cred_service.get_decrypted_credentials(db, user_id)
    
    if not credentials:
        print(f"❌ 用户 {user_id} 没有 Garmin 凭证")
        return
    
    # 创建 Garmin 服务
    service = GarminConnectService(
        email=credentials['email'],
        password=credentials['password'],
        is_cn=credentials.get('is_cn', False)
    )
    
    print(f"\n正在从 Garmin 获取最近 {days} 天的 VO2Max 数据...")
    
    for i in range(days):
        target_date = date.today() - timedelta(days=i)
        try:
            # 获取 max_metrics
            max_metrics = service.get_max_metrics(target_date)
            
            if max_metrics:
                # 解析 VO2Max
                generic = max_metrics.get('generic', {})
                running = max_metrics.get('running', {})
                
                vo2max_run = (
                    generic.get('vo2MaxPreciseValue') or 
                    generic.get('vo2MaxValue') or 
                    running.get('vo2MaxPreciseValue') or
                    running.get('vo2MaxValue') or
                    max_metrics.get('vo2MaxPreciseValue') or
                    max_metrics.get('vo2MaxValue')
                )
                
                if vo2max_run:
                    print(f"  {target_date}: 获取到 VO2Max = {vo2max_run}")
                    
                    # 更新数据库
                    record = db.query(GarminDailyData).filter(
                        GarminDailyData.user_id == user_id,
                        GarminDailyData.record_date == target_date
                    ).first()
                    
                    if record:
                        record.vo2max_running = float(vo2max_run)
                        print(f"    ✓ 已更新数据库记录")
                    else:
                        print(f"    ⚠️ 数据库中没有该日期的记录")
                else:
                    print(f"  {target_date}: max_metrics 中没有 VO2Max")
                    print(f"    键: {list(max_metrics.keys())}")
            else:
                print(f"  {target_date}: 没有 max_metrics 数据")
                
        except Exception as e:
            print(f"  {target_date}: 获取失败 - {e}")
    
    db.commit()
    print("\n✓ 同步完成")


def main():
    parser = argparse.ArgumentParser(description='检查和更新 VO2Max 数据')
    parser.add_argument('--user-id', type=int, default=1, help='用户ID')
    parser.add_argument('--days', type=int, default=7, help='检查/同步的天数')
    parser.add_argument('--check', action='store_true', help='只检查，不同步')
    parser.add_argument('--sync', action='store_true', help='从 Garmin 同步')
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        # 检查用户
        user = db.query(User).filter(User.id == args.user_id).first()
        if not user:
            print(f"❌ 用户 {args.user_id} 不存在")
            return
        
        print(f"用户: {user.username or user.email or f'ID={user.id}'}")
        
        # 检查数据
        check_vo2max_data(db, args.user_id, args.days)
        
        # 同步
        if args.sync and not args.check:
            sync_vo2max_from_garmin(db, args.user_id, args.days)
            print("\n同步后的数据:")
            check_vo2max_data(db, args.user_id, args.days)
            
    finally:
        db.close()


if __name__ == '__main__':
    main()
