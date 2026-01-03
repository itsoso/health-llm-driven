#!/usr/bin/env python3
"""
Garmin数据同步脚本

使用garminconnect库从Garmin Connect同步数据到本地数据库

安装依赖:
    pip install garminconnect

使用方法:
    python sync_garmin.py <email> <password> <user_id> [days]

示例:
    python sync_garmin.py user@example.com password123 1 30
"""
import sys
import os
from datetime import date, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_collection.garmin_connect import GarminConnectService
from app.database import SessionLocal
from app.models.user import User


def sync_garmin_data(email: str, password: str, user_id: int, days: int = 7):
    """同步最近N天的Garmin数据"""
    db = SessionLocal()
    try:
        # 验证用户存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"❌ 错误: 用户ID {user_id} 不存在")
            return
        
        print(f"开始同步用户 {user.name} (ID: {user_id}) 的Garmin数据...")
        print(f"同步最近 {days} 天的数据")
        
        # 创建Garmin Connect服务
        service = GarminConnectService(email, password)
        
        # 计算日期范围
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)  # 包含今天
        
        print(f"日期范围: {start_date} 到 {end_date}")
        
        # 执行同步
        result = service.sync_date_range(db, user_id, start_date, end_date)
        
        # 输出结果
        print("\n" + "="*50)
        print("同步完成!")
        print("="*50)
        print(f"✅ 成功: {result['success_count']} 条")
        print(f"❌ 失败: {result['error_count']} 条")
        
        if result['errors']:
            print("\n失败的日期:")
            for error in result['errors'][:10]:  # 只显示前10个
                print(f"  - {error['date']}: {error.get('error', error.get('status', 'unknown'))}")
            if len(result['errors']) > 10:
                print(f"  ... 还有 {len(result['errors']) - 10} 个失败项")
        
        return result
        
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
        print("用法: python sync_garmin.py <email> <password> <user_id> [days]")
        print("\n参数:")
        print("  email     - Garmin Connect账号邮箱")
        print("  password  - Garmin Connect账号密码")
        print("  user_id   - 系统中的用户ID")
        print("  days      - 同步最近N天的数据（默认7天）")
        print("\n示例:")
        print("  python sync_garmin.py user@example.com password123 1 30")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    user_id = int(sys.argv[3])
    days = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    
    sync_garmin_data(email, password, user_id, days)

