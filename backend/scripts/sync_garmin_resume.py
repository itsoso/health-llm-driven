#!/usr/bin/env python3
"""
Garmin数据断点续传同步脚本

检查已有数据，只同步缺失的日期

使用方法:
    python sync_garmin_resume.py <email> <password> <user_id> [years]
"""
import sys
import os
from datetime import date, timedelta
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_collection.garmin_connect import GarminConnectService
from app.database import SessionLocal
from app.models.user import User
from app.models.daily_health import GarminData


def sync_missing_dates(email: str, password: str, user_id: int, years: int = 2):
    """
    只同步缺失的日期

    Args:
        email: Garmin Connect账号邮箱
        password: Garmin Connect账号密码
        user_id: 系统中的用户ID
        years: 检查过去N年的数据（默认2年）
    """
    db = SessionLocal()
    try:
        # 验证用户存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ 错误: 用户ID {user_id} 不存在")
            return

        print("="*70)
        print(f"Garmin数据断点续传同步")
        print("="*70)
        print(f"用户: {user.name} (ID: {user_id})")

        # 计算日期范围
        end_date = date.today()
        start_date = date(end_date.year - years, end_date.month, end_date.day)
        total_days = (end_date - start_date).days + 1

        print(f"检查范围: {start_date} 到 {end_date} ({total_days} 天)")
        print()

        # 检查已有数据
        print("正在检查已有数据...")
        existing_dates = db.query(GarminData.record_date).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= start_date,
            GarminData.record_date <= end_date
        ).distinct().all()

        existing_dates_set = {d[0] for d in existing_dates}
        print(f"✅ 已有数据: {len(existing_dates_set)} 天")

        # 找出缺失的日期
        missing_dates = []
        current_date = start_date
        while current_date <= end_date:
            if current_date not in existing_dates_set:
                missing_dates.append(current_date)
            current_date += timedelta(days=1)

        if not missing_dates:
            print("🎉 所有数据已同步，无需同步")
            return

        print(f"📋 需要同步: {len(missing_dates)} 天")
        print(f"   预计耗时: 约 {len(missing_dates) * 0.8 / 60:.1f} 分钟")
        print()

        # 询问确认
        response = input("是否开始同步缺失的数据? (y/n): ")
        if response.lower() != 'y':
            print("已取消")
            return

        # 创建Garmin Connect服务
        print("\n正在登录Garmin Connect...")
        service = GarminConnectService(email, password)
        print("✅ 登录成功")
        print()

        # 执行同步
        results = []
        errors = []
        start_time = time.time()

        print("开始同步缺失的数据...")
        print("-"*70)

        for idx, target_date in enumerate(missing_dates, 1):
            try:
                progress = (idx / len(missing_dates)) * 100
                elapsed = time.time() - start_time
                if idx > 1:
                    avg_time = elapsed / idx
                    remaining = (len(missing_dates) - idx) * avg_time
                    eta_minutes = int(remaining // 60)
                    eta_seconds = int(remaining % 60)
                    print(f"[{progress:.1f}%] {target_date} ({idx}/{len(missing_dates)}) - 剩余: {eta_minutes}分{eta_seconds}秒", end=" - ")
                else:
                    print(f"[{progress:.1f}%] {target_date} ({idx}/{len(missing_dates)})", end=" - ")

                result = service.sync_daily_data(db, user_id, target_date)

                if result:
                    results.append({
                        "date": target_date.isoformat(),
                        "status": "success",
                        "data_id": result.id
                    })
                    print("✅ 成功")
                else:
                    errors.append({
                        "date": target_date.isoformat(),
                        "status": "no_data"
                    })
                    print("⚠️  无数据")

            except Exception as e:
                errors.append({
                    "date": target_date.isoformat(),
                    "status": "error",
                    "error": str(e)
                })
                print(f"❌ 错误: {str(e)[:50]}")

            # 延迟
            time.sleep(0.8)

            # 每10条显示一次统计
            if idx % 10 == 0:
                print(f"\n📊 进度: {idx}/{len(missing_dates)}, 成功 {len(results)}, 失败 {len(errors)}\n")

        # 输出结果
        total_time = time.time() - start_time
        total_minutes = int(total_time // 60)
        total_seconds = int(total_time % 60)

        print()
        print("="*70)
        print("同步完成!")
        print("="*70)
        print(f"✅ 成功: {len(results)} 条")
        print(f"⚠️  无数据: {len([e for e in errors if e['status'] == 'no_data'])} 天")
        print(f"❌ 错误: {len([e for e in errors if e['status'] == 'error'])} 天")
        print(f"⏱️  耗时: {total_minutes}分{total_seconds}秒")
        print()

        return {
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors
        }

    except ImportError as e:
        print("❌ 错误: garminconnect库未安装")
        print("请运行: pip install garminconnect")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python sync_garmin_resume.py <email> <password> <user_id> [years]")
        print("\n参数:")
        print("  email     - Garmin Connect账号邮箱")
        print("  password  - Garmin Connect账号密码")
        print("  user_id   - 系统中的用户ID")
        print("  years     - 检查过去N年的数据（默认2年）")
        print("\n说明:")
        print("  此脚本会检查已有数据，只同步缺失的日期")
        print("  适合用于断点续传或补充缺失数据")
        print("\n示例:")
        print("  python sync_garmin_resume.py user@example.com password123 1 2")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    user_id = int(sys.argv[3])
    years = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    sync_missing_dates(email, password, user_id, years)
