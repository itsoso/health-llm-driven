#!/usr/bin/env python3
"""生成加密密钥的辅助脚本

使用方法：
    python backend/scripts/generate_encryption_keys.py
"""
from cryptography.fernet import Fernet


def generate_keys():
    """生成加密密钥并打印环境变量配置"""
    garmin_key = Fernet.generate_key().decode()
    device_key = Fernet.generate_key().decode()

    print("=" * 60)
    print("加密密钥已生成！请将以下内容添加到 .env 文件中：")
    print("=" * 60)
    print()
    print(f"GARMIN_ENCRYPTION_KEY={garmin_key}")
    print(f"DEVICE_ENCRYPTION_KEY={device_key}")
    print()
    print("=" * 60)
    print("⚠️  重要提示：")
    print("1. 这些密钥用于加密敏感数据（如 Garmin 密码）")
    print("2. 请妥善保管密钥，丢失后无法解密已加密的数据")
    print("3. 生产环境和开发环境应使用不同的密钥")
    print("4. 不要将密钥提交到 Git 仓库")
    print("=" * 60)


if __name__ == "__main__":
    generate_keys()
