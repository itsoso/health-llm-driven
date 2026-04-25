#!/usr/bin/env python3
"""检查 Garmin 强度活动时间数据"""

from garminconnect import Garmin
from app.database import SessionLocal
from app.models.user import User
from app.services.auth import GarminCredentialService
from datetime import date

def main():
    db = SessionLocal()
    cred_service = GarminCredentialService()

    # 找到用户
    user = db.query(User).filter(User.email == 'itsoso@126.com').first()
    if not user:
        print("未找到用户")
        return

    credentials = cred_service.get_decrypted_credentials(db, user.id)
    if not credentials:
        print("未找到凭证")
        return

    print(f"用户: {user.name}, Garmin账号: {credentials['email']}")

    # 直接使用 garminconnect 库
    client = Garmin(credentials['email'], credentials['password'], is_cn=credentials.get('is_cn', False))
    client.login()

    # 获取昨天的原始数据（有运动记录）
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    print(f"\n获取 {yesterday} 的原始 Garmin 数据...")

    try:
        # 获取 daily summary
        summary = client.get_stats(yesterday.isoformat())

        print("\n=== 与强度活动相关的字段 ===")
        # 打印与强度活动相关的字段
        for k, v in sorted(summary.items()):
            if 'intensity' in k.lower() or 'minute' in k.lower() or 'active' in k.lower():
                print(f"{k}: {v}")

        print("\n=== 所有非空字段 ===")
        for k, v in sorted(summary.items()):
            if v is not None and v != 0:
                print(f"{k}: {v}")
    except Exception as e:
        print(f"获取数据失败: {e}")
        import traceback
        traceback.print_exc()

    db.close()

if __name__ == "__main__":
    main()
