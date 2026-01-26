#!/usr/bin/env python3
"""一次性密码重置脚本"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.services.auth import AuthService


def reset_password(email: str, new_password: str):
    """重置用户密码"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"错误: 邮箱 {email} 对应的用户不存在")
            return False

        hashed_password = AuthService.get_password_hash(new_password)
        user.hashed_password = hashed_password
        db.commit()

        print(f"成功: 已重置用户 {user.name} ({email}) 的密码")
        return True
    except Exception as e:
        print(f"错误: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python reset_password.py <email> <new_password>")
        sys.exit(1)

    email = sys.argv[1]
    new_password = sys.argv[2]

    success = reset_password(email, new_password)
    sys.exit(0 if success else 1)
