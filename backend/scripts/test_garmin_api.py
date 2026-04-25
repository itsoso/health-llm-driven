#!/usr/bin/env python3
"""
测试Garmin API返回的数据

用于调试为什么数据同步显示 no_data
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


def test_garmin_api(email: str, password: str, days: int = 7):
    """测试Garmin API"""
    print(f"正在连接Garmin Connect...")
    print("="*60)

    try:
        # 登录
        garmin = Garmin(email, password)
        garmin.login()
        print("✅ 登录成功\n")

        # 获取用户信息
        print("获取用户信息...")
        try:
            user_profile = garmin.get_full_name()
            print(f"用户: {user_profile}")
        except Exception as e:
            print(f"获取用户信息失败: {e}")

        print("\n" + "="*60)
        print(f"测试最近 {days} 天的数据获取")
        print("="*60)

        # 测试每一天
        for i in range(days):
            target_date = date.today() - timedelta(days=i)
            print(f"\n📅 {target_date}:")

            # 测试 get_user_summary
            try:
                summary = garmin.get_user_summary(target_date.isoformat())
                if summary:
                    print(f"  ✅ get_user_summary: 返回 {type(summary).__name__}")
                    if isinstance(summary, dict):
                        # 打印所有键
                        print(f"     所有键: {list(summary.keys())}")
                        # 打印一些关键字段
                        print(f"     - steps: {summary.get('steps')}")
                        print(f"     - totalSteps: {summary.get('totalSteps')}")
                        print(f"     - dailyStepGoal: {summary.get('dailyStepGoal')}")
                        print(f"     - totalKilocalories: {summary.get('totalKilocalories')}")
                        print(f"     - activeKilocalories: {summary.get('activeKilocalories')}")
                        print(f"     - bmrKilocalories: {summary.get('bmrKilocalories')}")
                        print(f"     - restingHeartRate: {summary.get('restingHeartRate')}")
                        print(f"     - averageHeartRate: {summary.get('averageHeartRate')}")
                        print(f"     - maxHeartRate: {summary.get('maxHeartRate')}")
                        print(f"     - minHeartRate: {summary.get('minHeartRate')}")
                        print(f"     - 数据键数量: {len(summary.keys())}")
                    elif isinstance(summary, list):
                        print(f"     - 列表长度: {len(summary)}")
                        if summary:
                            print(f"     - 第一个元素类型: {type(summary[0]).__name__}")
                else:
                    print(f"  ❌ get_user_summary: 返回 None 或空")
            except Exception as e:
                print(f"  ❌ get_user_summary 错误: {e}")

            # 测试 get_sleep_data
            try:
                sleep = garmin.get_sleep_data(target_date.isoformat())
                if sleep:
                    print(f"  ✅ get_sleep_data: 返回 {type(sleep).__name__}")
                    if isinstance(sleep, dict):
                        print(f"     所有键: {list(sleep.keys())}")
                        # 打印常见的睡眠字段
                        for key in ['sleepScore', 'overallScore', 'qualityScore', 'sleepTimeSeconds',
                                   'sleepTimeInSeconds', 'totalSleepTimeInSeconds', 'awakeSleepSeconds',
                                   'deepSleepSeconds', 'lightSleepSeconds', 'remSleepSeconds',
                                   'dailySleepDTO', 'sleepMovement', 'sleepLevels']:
                            if sleep.get(key) is not None:
                                val = sleep.get(key)
                                if isinstance(val, dict):
                                    print(f"     - {key}: dict with keys {list(val.keys())[:10]}")
                                elif isinstance(val, list):
                                    print(f"     - {key}: list with {len(val)} items")
                                else:
                                    print(f"     - {key}: {val}")
                else:
                    print(f"  ❌ get_sleep_data: 返回 None 或空")
            except Exception as e:
                print(f"  ❌ get_sleep_data 错误: {e}")

            # 测试 get_heart_rates
            try:
                hr = garmin.get_heart_rates(target_date.isoformat())
                if hr:
                    print(f"  ✅ get_heart_rates: 返回 {type(hr).__name__}")
                    if isinstance(hr, dict):
                        print(f"     - restingHeartRate: {hr.get('restingHeartRate')}")
                else:
                    print(f"  ❌ get_heart_rates: 返回 None 或空")
            except Exception as e:
                print(f"  ❌ get_heart_rates 错误: {e}")

            # 小延迟避免请求过快
            import time
            time.sleep(0.5)

        print("\n" + "="*60)
        print("测试完成")
        print("="*60)

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python test_garmin_api.py <email> <password> [days]")
        print("\n示例:")
        print("  python test_garmin_api.py user@example.com password123")
        print("  python test_garmin_api.py user@example.com password123 14")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 7

    test_garmin_api(email, password, days)
