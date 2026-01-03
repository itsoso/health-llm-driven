#!/usr/bin/env python3
"""
调试Garmin数据获取脚本

用于查看Garmin Connect API实际返回的数据结构，帮助调试数据解析问题

使用方法:
    python debug_garmin_data.py <email> <password> [date]

示例:
    python debug_garmin_data.py user@example.com password123
    python debug_garmin_data.py user@example.com password123 2024-01-15
"""
import sys
import os
import json
from datetime import date, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from garminconnect import Garmin
except ImportError:
    print("❌ 错误: garminconnect库未安装")
    print("请运行: pip install garminconnect")
    sys.exit(1)


def debug_garmin_data(email: str, password: str, target_date: date = None):
    """调试Garmin数据获取"""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)  # 默认昨天
    
    print(f"正在连接Garmin Connect...")
    print(f"目标日期: {target_date}")
    print("="*60)
    
    try:
        # 登录
        garmin = Garmin(email, password)
        garmin.login()
        print("✅ 登录成功\n")
        
        # 1. 获取用户摘要
        print("1️⃣ 获取用户摘要 (get_user_summary):")
        print("-" * 60)
        summary = garmin.get_user_summary(target_date.isoformat())
        if summary:
            print(f"返回类型: {type(summary)}")
            if isinstance(summary, dict):
                print(f"数据键: {list(summary.keys())}")
                print("\n关键字段检查:")
                print(f"  - sleepScore: {summary.get('sleepScore')}")
                print(f"  - sleepScores: {summary.get('sleepScores')}")
                print(f"  - sleepTimeSeconds: {summary.get('sleepTimeSeconds')}")
                print(f"  - averageHeartRate: {summary.get('averageHeartRate')}")
                print(f"  - avgHeartRate: {summary.get('avgHeartRate')}")
                print(f"  - restingHeartRate: {summary.get('restingHeartRate')}")
                print(f"  - steps: {summary.get('steps')}")
            print(f"\n完整数据（JSON）:\n{json.dumps(summary, indent=2, default=str)[:2000]}...")
        else:
            print("❌ 未返回数据")
        print("\n")
        
        # 2. 获取睡眠数据
        print("2️⃣ 获取睡眠数据 (get_sleep_data):")
        print("-" * 60)
        sleep_data = garmin.get_sleep_data(target_date.isoformat())
        if sleep_data:
            print(f"返回类型: {type(sleep_data)}")
            if isinstance(sleep_data, dict):
                print(f"数据键: {list(sleep_data.keys())}")
                print("\n关键字段检查:")
                print(f"  - sleepScore: {sleep_data.get('sleepScore')}")
                print(f"  - overallSleepScore: {sleep_data.get('overallSleepScore')}")
                print(f"  - sleepTimeSeconds: {sleep_data.get('sleepTimeSeconds')}")
                print(f"  - duration: {sleep_data.get('duration')}")
                print(f"  - sleepTimeMillis: {sleep_data.get('sleepTimeMillis')}")
            print(f"\n完整数据（JSON）:\n{json.dumps(sleep_data, indent=2, default=str)[:2000]}...")
        else:
            print("❌ 未返回数据")
        print("\n")
        
        # 3. 获取心率数据
        print("3️⃣ 获取心率数据 (get_heart_rates):")
        print("-" * 60)
        hr_data = garmin.get_heart_rates(target_date.isoformat())
        if hr_data:
            print(f"返回类型: {type(hr_data)}")
            if isinstance(hr_data, dict):
                print(f"数据键: {list(hr_data.keys())}")
                print("\n关键字段检查:")
                print(f"  - averageHeartRate: {hr_data.get('averageHeartRate')}")
                print(f"  - avgHeartRate: {hr_data.get('avgHeartRate')}")
                print(f"  - avg: {hr_data.get('avg')}")
                print(f"  - restingHeartRate: {hr_data.get('restingHeartRate')}")
            elif isinstance(hr_data, list):
                print(f"返回的是列表，长度: {len(hr_data)}")
                if hr_data:
                    print(f"第一个元素: {hr_data[0]}")
            print(f"\n完整数据（JSON）:\n{json.dumps(hr_data, indent=2, default=str)[:2000]}...")
        else:
            print("❌ 未返回数据")
        print("\n")
        
        # 4. 获取身体电量
        print("4️⃣ 获取身体电量 (get_body_battery):")
        print("-" * 60)
        battery_data = garmin.get_body_battery(target_date.isoformat())
        if battery_data:
            print(f"返回类型: {type(battery_data)}")
            if isinstance(battery_data, list):
                print(f"返回的是列表，长度: {len(battery_data)}")
                if battery_data:
                    print(f"第一个元素: {battery_data[0]}")
            elif isinstance(battery_data, dict):
                print(f"数据键: {list(battery_data.keys())}")
            print(f"\n完整数据（JSON）:\n{json.dumps(battery_data, indent=2, default=str)[:1000]}...")
        else:
            print("❌ 未返回数据")
        print("\n")
        
        # 5. 获取压力数据
        print("5️⃣ 获取压力数据 (get_all_day_stress):")
        print("-" * 60)
        stress_data = garmin.get_all_day_stress(target_date.isoformat())
        if stress_data:
            print(f"返回类型: {type(stress_data)}")
            if isinstance(stress_data, list):
                print(f"返回的是列表，长度: {len(stress_data)}")
                if stress_data:
                    print(f"第一个元素: {stress_data[0]}")
            elif isinstance(stress_data, dict):
                print(f"数据键: {list(stress_data.keys())}")
            print(f"\n完整数据（JSON）:\n{json.dumps(stress_data, indent=2, default=str)[:1000]}...")
        else:
            print("❌ 未返回数据")
        print("\n")
        
        # 总结
        print("="*60)
        print("📊 数据提取建议:")
        print("-" * 60)
        
        if summary:
            print("\n✅ 从get_user_summary可以获取:")
            if summary.get('sleepScore') or summary.get('sleepScores'):
                print("  ✓ 睡眠分数")
            if summary.get('sleepTimeSeconds') or summary.get('sleepDurationSeconds'):
                print("  ✓ 睡眠时长")
            if summary.get('averageHeartRate') or summary.get('avgHeartRate'):
                print("  ✓ 平均心率")
            if summary.get('restingHeartRate'):
                print("  ✓ 静息心率")
            if summary.get('steps'):
                print("  ✓ 步数")
        
        if sleep_data:
            print("\n✅ 从get_sleep_data可以获取:")
            if sleep_data.get('sleepScore') or sleep_data.get('overallSleepScore'):
                print("  ✓ 睡眠分数")
            if sleep_data.get('sleepTimeSeconds') or sleep_data.get('duration'):
                print("  ✓ 睡眠时长")
        
        if hr_data:
            print("\n✅ 从get_heart_rates可以获取:")
            if isinstance(hr_data, dict):
                if hr_data.get('averageHeartRate') or hr_data.get('avgHeartRate'):
                    print("  ✓ 平均心率")
                if hr_data.get('restingHeartRate'):
                    print("  ✓ 静息心率")
            elif isinstance(hr_data, list) and hr_data:
                print("  ✓ 心率数据（需要从列表中提取）")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python debug_garmin_data.py <email> <password> [date]")
        print("\n参数:")
        print("  email     - Garmin Connect账号邮箱")
        print("  password  - Garmin Connect账号密码")
        print("  date      - 目标日期 (YYYY-MM-DD)，默认昨天")
        print("\n示例:")
        print("  python debug_garmin_data.py user@example.com password123")
        print("  python debug_garmin_data.py user@example.com password123 2024-01-15")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    target_date = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else None
    
    debug_garmin_data(email, password, target_date)

