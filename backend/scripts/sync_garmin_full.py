#!/usr/bin/env python3
"""
Garmin数据完整同步脚本

同步过去两年的所有Garmin数据到本地数据库

安装依赖:
    pip install garminconnect

使用方法:
    python sync_garmin_full.py <email> <password> <user_id> [years]

示例:
    python sync_garmin_full.py user@example.com password123 1 2
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


def sync_garmin_full_history(email: str, password: str, user_id: int, years: int = 2):
    """
    同步过去N年的完整Garmin数据

    Args:
        email: Garmin Connect账号邮箱
        password: Garmin Connect账号密码
        user_id: 系统中的用户ID
        years: 同步过去N年的数据（默认2年）
    """
    db = SessionLocal()
    try:
        # 验证用户存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ 错误: 用户ID {user_id} 不存在")
            return

        print("="*70)
        print(f"Garmin数据完整同步")
        print("="*70)
        print(f"用户: {user.name} (ID: {user_id})")
        print(f"同步范围: 过去 {years} 年")

        # 计算日期范围
        end_date = date.today()
        start_date = date(end_date.year - years, end_date.month, end_date.day)

        total_days = (end_date - start_date).days + 1

        print(f"开始日期: {start_date}")
        print(f"结束日期: {end_date}")
        print(f"总天数: {total_days} 天")
        print("="*70)
        print()

        # 创建Garmin Connect服务
        print("正在登录Garmin Connect...")
        service = GarminConnectService(email, password)
        print("✅ 登录成功")
        print()

        # 执行同步
        results = []
        errors = []
        current_date = start_date
        processed = 0
        start_time = time.time()

        print("开始同步数据...")
        print("-"*70)

        while current_date <= end_date:
            try:
                # 显示进度
                progress = (processed / total_days) * 100
                elapsed = time.time() - start_time
                if processed > 0:
                    avg_time = elapsed / processed
                    remaining = (total_days - processed) * avg_time
                    eta_minutes = int(remaining // 60)
                    eta_seconds = int(remaining % 60)
                    print(f"[{progress:.1f}%] {current_date} - 预计剩余: {eta_minutes}分{eta_seconds}秒", end=" - ")
                else:
                    print(f"[{progress:.1f}%] {current_date}", end=" - ")

                # 同步单日数据
                result = service.sync_daily_data(db, user_id, current_date)

                if result:
                    results.append({
                        "date": current_date.isoformat(),
                        "status": "success",
                        "data_id": result.id
                    })
                    print("✅ 成功")
                else:
                    errors.append({
                        "date": current_date.isoformat(),
                        "status": "no_data"
                    })
                    print("⚠️  无数据")

                processed += 1

            except Exception as e:
                error_msg = str(e)
                errors.append({
                    "date": current_date.isoformat(),
                    "status": "error",
                    "error": error_msg
                })
                print(f"❌ 错误: {error_msg[:50]}")

            current_date += timedelta(days=1)

            # 避免请求过快，添加延迟
            time.sleep(0.8)  # 稍微增加延迟，避免被限制

            # 每10天显示一次统计
            if processed % 10 == 0:
                print(f"\n📊 进度统计: 已处理 {processed}/{total_days} 天, 成功 {len(results)} 条, 失败 {len(errors)} 条\n")

        # 输出最终结果
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
        print(f"⏱️  总耗时: {total_minutes}分{total_seconds}秒")
        print(f"📈 平均速度: {total_days/total_time*60:.1f} 天/分钟" if total_time > 0 else "")
        print()

        # 显示错误详情（如果有）
        error_list = [e for e in errors if e['status'] == 'error']
        if error_list:
            print("错误详情（前10个）:")
            for error in error_list[:10]:
                print(f"  - {error['date']}: {error.get('error', 'unknown')[:60]}")
            if len(error_list) > 10:
                print(f"  ... 还有 {len(error_list) - 10} 个错误")
            print()

        # 显示无数据的日期（如果有）
        no_data_list = [e for e in errors if e['status'] == 'no_data']
        if no_data_list:
            print(f"无数据的日期: {len(no_data_list)} 天")
            if len(no_data_list) <= 20:
                dates = [e['date'] for e in no_data_list]
                print(f"  {', '.join(dates)}")
            else:
                print(f"  前10个: {', '.join([e['date'] for e in no_data_list[:10]])}")
                print(f"  ... 还有 {len(no_data_list) - 10} 天")
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
        print("用法: python sync_garmin_full.py <email> <password> <user_id> [years]")
        print("\n参数:")
        print("  email     - Garmin Connect账号邮箱")
        print("  password  - Garmin Connect账号密码")
        print("  user_id   - 系统中的用户ID")
        print("  years     - 同步过去N年的数据（默认2年）")
        print("\n示例:")
        print("  python sync_garmin_full.py user@example.com password123 1 2")
        print("  python sync_garmin_full.py user@example.com password123 1 1  # 只同步1年")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    user_id = int(sys.argv[3])
    years = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    print("⚠️  注意: 同步大量数据可能需要较长时间")
    print(f"   预计同步 {years} 年数据，约 {(date.today() - date(date.today().year - years, 1, 1)).days} 天")
    print("   按 Ctrl+C 可以随时中断")
    print()

    try:
        sync_garmin_full_history(email, password, user_id, years)
    except KeyboardInterrupt:
        print("\n\n⚠️  同步被用户中断")
        print("已同步的数据已保存，可以稍后继续同步剩余日期")
        sys.exit(0)
