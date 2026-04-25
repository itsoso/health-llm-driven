"""更新用户认证相关的数据库字段"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from app.config import settings

DATABASE_URL = settings.database_url

def add_column_if_not_exists(engine, table_name, column_name, column_type):
    """如果列不存在则添加"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]

    if column_name not in columns:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            conn.commit()
            print(f"✅ 已添加列: {table_name}.{column_name}")
    else:
        print(f"⏭️ 列已存在: {table_name}.{column_name}")


def create_table_if_not_exists(engine, table_name, create_sql):
    """如果表不存在则创建"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if table_name not in tables:
        with engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
            print(f"✅ 已创建表: {table_name}")
    else:
        print(f"⏭️ 表已存在: {table_name}")


if __name__ == "__main__":
    print("开始更新用户认证相关数据库结构...")
    print(f"数据库: {DATABASE_URL}")

    engine = create_engine(DATABASE_URL)

    # 1. 更新 users 表，添加认证相关字段（SQLite不支持直接添加UNIQUE列，先添加普通列）
    print("\n📋 更新 users 表...")
    add_column_if_not_exists(engine, "users", "email", "VARCHAR")
    add_column_if_not_exists(engine, "users", "username", "VARCHAR")
    add_column_if_not_exists(engine, "users", "hashed_password", "VARCHAR")
    add_column_if_not_exists(engine, "users", "is_active", "BOOLEAN DEFAULT 1")

    # 2. 创建 garmin_credentials 表
    print("\n📋 创建 garmin_credentials 表...")
    create_table_if_not_exists(engine, "garmin_credentials", """
        CREATE TABLE garmin_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            garmin_email VARCHAR NOT NULL,
            encrypted_password TEXT NOT NULL,
            last_sync_at DATETIME,
            sync_enabled BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 3. 创建索引
    print("\n📋 创建索引...")
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_garmin_credentials_user_id ON garmin_credentials(user_id)"))
            conn.commit()
            print("✅ 索引创建完成")
    except Exception as e:
        print(f"⚠️ 创建索引时出现警告: {e}")

    print("\n✅ 数据库结构更新完成！")
