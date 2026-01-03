#!/usr/bin/env python3
"""
列出系统中的所有用户

使用方法:
    python list_users.py
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User


def list_users():
    """列出所有用户"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        if not users:
            print("系统中还没有用户")
            print("\n创建用户的方法:")
            print("1. 通过API: POST /api/v1/users")
            print("2. 使用脚本: python create_user.py")
            return
        
        print("="*60)
        print("系统中的用户列表")
        print("="*60)
        print(f"{'ID':<5} {'姓名':<20} {'性别':<10} {'出生日期':<15}")
        print("-"*60)
        
        for user in users:
            print(f"{user.id:<5} {user.name:<20} {user.gender:<10} {user.birth_date}")
        
        print("="*60)
        print(f"\n共 {len(users)} 个用户")
        print("\n使用user_id进行Garmin同步:")
        print(f"  python scripts/sync_garmin.py email password {users[0].id} 30")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    list_users()

