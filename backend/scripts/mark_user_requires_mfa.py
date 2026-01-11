#!/usr/bin/env python3
"""标记指定用户需要MFA两步验证"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User, GarminCredential

def mark_user_requires_mfa(email_or_name: str):
    """
    标记用户需要MFA验证
    
    Args:
        email_or_name: 用户邮箱或姓名
    """
    db = SessionLocal()
    
    try:
        # 查找用户
        user = db.query(User).filter(
            (User.email == email_or_name) | (User.name == email_or_name)
        ).first()
        
        if not user:
            print(f"❌ 未找到用户: {email_or_name}")
            return
        
        print(f"找到用户: ID={user.id}, 姓名={user.name}, 邮箱={user.email}")
        
        # 查找Garmin凭证
        credential = db.query(GarminCredential).filter(
            GarminCredential.user_id == user.id
        ).first()
        
        if not credential:
            print(f"❌ 用户 {user.name} 没有Garmin凭证")
            return
        
        print(f"Garmin邮箱: {credential.garmin_email}")
        print(f"当前MFA状态: {credential.requires_mfa}")
        
        # 更新MFA标志
        credential.requires_mfa = True
        db.commit()
        
        print(f"✅ 已标记用户 {user.name} 需要MFA两步验证")
        print(f"   该用户将不会被后台自动同步任务处理")
        
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python mark_user_requires_mfa.py <用户邮箱或姓名>")
        print("示例: python mark_user_requires_mfa.py 'liyan@Natalie'")
        sys.exit(1)
    
    email_or_name = sys.argv[1]
    mark_user_requires_mfa(email_or_name)
