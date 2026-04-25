#!/usr/bin/env python3
"""
合并用户脚本 - 将Natalie用户的数据合并到liyan微信用户
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.services.user_merge import UserMergeService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_users():
    """查找Natalie和liyan用户"""
    db = SessionLocal()
    try:
        # 查找Natalie用户
        natalie = db.query(User).filter(User.name.ilike('%Natalie%')).first()
        if not natalie:
            # 尝试通过用户名查找
            natalie = db.query(User).filter(User.username.ilike('%Natalie%')).first()

        # 查找liyan用户（微信用户）
        liyan = db.query(User).filter(
            (User.name.ilike('%liyan%')) |
            (User.username.ilike('%liyan%')) |
            (User.email.ilike('%liyan%'))
        ).filter(User.wechat_openid.isnot(None)).first()

        if not liyan:
            # 如果没有找到微信用户，查找所有包含liyan的用户
            liyan_users = db.query(User).filter(
                (User.name.ilike('%liyan%')) |
                (User.username.ilike('%liyan%')) |
                (User.email.ilike('%liyan%'))
            ).all()
            if liyan_users:
                print("找到多个liyan用户，请选择:")
                for i, u in enumerate(liyan_users):
                    print(f"  {i+1}. ID: {u.id}, 用户名: {u.username}, 姓名: {u.name}, 邮箱: {u.email}, 微信openid: {u.wechat_openid}")
                return None, None

        return natalie, liyan
    finally:
        db.close()


def merge_users(source_user_id: int, target_user_id: int):
    """执行用户合并"""
    db = SessionLocal()
    try:
        result = UserMergeService.merge_users(
            db=db,
            source_user_id=source_user_id,
            target_user_id=target_user_id
        )
        return result
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("用户合并脚本")
    print("=" * 60)

    # 查找用户
    natalie, liyan = find_users()

    if not natalie:
        print("❌ 未找到Natalie用户")
        sys.exit(1)

    if not liyan:
        print("❌ 未找到liyan微信用户")
        sys.exit(1)

    print(f"\n找到源用户 (Natalie):")
    print(f"  ID: {natalie.id}")
    print(f"  用户名: {natalie.username}")
    print(f"  姓名: {natalie.name}")
    print(f"  邮箱: {natalie.email}")
    print(f"  微信openid: {natalie.wechat_openid}")

    print(f"\n找到目标用户 (liyan):")
    print(f"  ID: {liyan.id}")
    print(f"  用户名: {liyan.username}")
    print(f"  姓名: {liyan.name}")
    print(f"  邮箱: {liyan.email}")
    print(f"  微信openid: {liyan.wechat_openid}")

    # 确认合并
    print(f"\n⚠️  警告: 这将把用户 {natalie.id} (Natalie) 的所有数据合并到用户 {liyan.id} (liyan)")
    print("合并后，Natalie用户将被删除，所有数据将迁移到liyan用户")

    confirm = input("\n确认执行合并? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ 已取消合并")
        sys.exit(0)

    # 执行合并
    try:
        print("\n开始合并...")
        result = merge_users(natalie.id, liyan.id)

        print("\n✅ 合并成功!")
        print(f"源用户ID: {result['source_user_id']}")
        print(f"目标用户ID: {result['target_user_id']}")
        print("\n合并统计:")
        stats = result['stats']
        for key, value in stats.items():
            print(f"  {key}: {value}")

    except Exception as e:
        print(f"\n❌ 合并失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
