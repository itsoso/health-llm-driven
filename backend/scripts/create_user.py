#!/usr/bin/env python3
"""
创建新用户

使用方法:
    python create_user.py <name> <birth_date> <gender>
    
示例:
    python create_user.py "张三" "1990-01-01" "男"
"""
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User


def create_user(name: str, birth_date_str: str, gender: str):
    """创建新用户"""
    db = SessionLocal()
    try:
        # 解析日期
        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ 错误: 日期格式不正确，请使用 YYYY-MM-DD 格式")
            return
        
        # 检查用户是否已存在（根据姓名和出生日期）
        existing = db.query(User).filter(
            User.name == name,
            User.birth_date == birth_date
        ).first()
        
        if existing:
            print(f"⚠️  用户已存在:")
            print(f"  ID: {existing.id}")
            print(f"  姓名: {existing.name}")
            print(f"  性别: {existing.gender}")
            print(f"  出生日期: {existing.birth_date}")
            return existing
        
        # 创建新用户
        user = User(
            name=name,
            birth_date=birth_date,
            gender=gender
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print("✅ 用户创建成功!")
        print("="*50)
        print(f"用户ID: {user.id}")
        print(f"姓名: {user.name}")
        print(f"性别: {user.gender}")
        print(f"出生日期: {user.birth_date}")
        print("="*50)
        print(f"\n现在可以使用此user_id进行Garmin同步:")
        print(f"  python scripts/sync_garmin.py email password {user.id} 30")
        
        return user
        
    except Exception as e:
        db.rollback()
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python create_user.py <name> <birth_date> <gender>")
        print("\n参数:")
        print("  name       - 用户姓名")
        print("  birth_date - 出生日期 (格式: YYYY-MM-DD)")
        print("  gender     - 性别 (男/女)")
        print("\n示例:")
        print('  python create_user.py "张三" "1990-01-01" "男"')
        sys.exit(1)
    
    name = sys.argv[1]
    birth_date = sys.argv[2]
    gender = sys.argv[3]
    
    create_user(name, birth_date, gender)

