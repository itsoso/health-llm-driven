"""添加管理员字段到用户表"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine, SessionLocal


def add_admin_field():
    """添加is_admin字段到users表"""
    db = SessionLocal()
    
    try:
        # 检查列是否存在
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'is_admin' not in columns:
            print("添加 is_admin 字段...")
            db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            db.commit()
            print("✅ is_admin 字段添加成功")
        else:
            print("ℹ️ is_admin 字段已存在")
        
        # 设置第一个用户为管理员（如果存在）
        result = db.execute(text("SELECT id, name, is_admin FROM users ORDER BY id LIMIT 1"))
        first_user = result.fetchone()
        
        if first_user:
            user_id, name, is_admin = first_user
            if not is_admin:
                db.execute(text(f"UPDATE users SET is_admin = 1 WHERE id = {user_id}"))
                db.commit()
                print(f"✅ 已将用户 '{name}' (ID: {user_id}) 设为管理员")
            else:
                print(f"ℹ️ 用户 '{name}' (ID: {user_id}) 已是管理员")
        else:
            print("ℹ️ 暂无用户，第一个注册的用户将自动成为管理员")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("添加管理员字段")
    print("=" * 50)
    add_admin_field()
    print("=" * 50)
    print("完成!")

