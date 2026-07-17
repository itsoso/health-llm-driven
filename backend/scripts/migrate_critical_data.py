#!/usr/bin/env python3
"""
关键数据迁移脚本 - 专注于核心健康数据
"""

import sys
import os
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

SQLITE_DB = "/opt/health-app/backend/health.db"
POSTGRES_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
if not POSTGRES_URL:
    raise RuntimeError("POSTGRES_URL or DATABASE_URL must be set; no database credential is embedded in this script")

print("=" * 80)
print("🚀 关键数据迁移: SQLite → PostgreSQL")
print("=" * 80)

# 连接数据库
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

pg_engine = create_engine(POSTGRES_URL)
PgSession = sessionmaker(bind=pg_engine)
pg_session = PgSession()

print("\n✅ 数据库连接成功")

# 获取已存在的用户 ID
print("\n1️⃣ 获取已迁移的用户 ID...")
result = pg_session.execute(text("SELECT id FROM users"))
valid_user_ids = set([row[0] for row in result])
print(f"   ✅ 找到 {len(valid_user_ids)} 个有效用户 ID: {sorted(valid_user_ids)}")

def migrate_garmin_data():
    """迁移 Garmin 数据"""
    print("\n2️⃣ 迁移 garmin_data...")

    # 获取数据
    sqlite_cursor.execute("SELECT * FROM garmin_data")
    rows = sqlite_cursor.fetchall()
    columns = [desc[0] for desc in sqlite_cursor.description]

    print(f"   📊 SQLite 中有 {len(rows)} 条记录")

    # 获取 PostgreSQL 表的列
    result = pg_session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'garmin_data' ORDER BY ordinal_position")
    )
    pg_columns = [row[0] for row in result]
    common_columns = [col for col in columns if col in pg_columns]

    print(f"   📋 共同列: {len(common_columns)} 个")

    # 清空表
    pg_session.execute(text("TRUNCATE TABLE garmin_data RESTART IDENTITY CASCADE"))
    pg_session.commit()

    success = 0
    failed = 0

    for row in rows:
        try:
            row_dict = dict(zip(columns, row))

            # 检查用户是否存在
            if row_dict['user_id'] not in valid_user_ids:
                failed += 1
                continue

            # 只使用共同的列
            insert_data = {}
            for col in common_columns:
                value = row_dict[col]

                # 处理 None 值
                if value is None:
                    insert_data[col] = None
                # 处理布尔值
                elif isinstance(value, int) and col in ['has_sleep_data', 'has_hrv_data', 'has_stress_data']:
                    insert_data[col] = bool(value)
                else:
                    insert_data[col] = value

            # 插入
            cols = ', '.join(common_columns)
            placeholders = ', '.join([f':{col}' for col in common_columns])
            sql = f"INSERT INTO garmin_data ({cols}) VALUES ({placeholders})"

            pg_session.execute(text(sql), insert_data)
            pg_session.commit()
            success += 1

            if success % 100 == 0:
                print(f"   ... 已迁移 {success} 条")

        except Exception as e:
            failed += 1
            pg_session.rollback()
            if failed <= 3:
                print(f"   ⚠️  失败: {str(e)[:150]}")

    print(f"   ✅ 成功迁移 {success} 条，失败 {failed} 条")

def migrate_workout_records():
    """迁移运动记录"""
    print("\n3️⃣ 迁移 workout_records...")

    sqlite_cursor.execute("SELECT * FROM workout_records")
    rows = sqlite_cursor.fetchall()
    columns = [desc[0] for desc in sqlite_cursor.description]

    print(f"   📊 SQLite 中有 {len(rows)} 条记录")

    result = pg_session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'workout_records' ORDER BY ordinal_position")
    )
    pg_columns = [row[0] for row in result]
    common_columns = [col for col in columns if col in pg_columns]

    print(f"   📋 共同列: {len(common_columns)} 个")

    pg_session.execute(text("TRUNCATE TABLE workout_records RESTART IDENTITY CASCADE"))
    pg_session.commit()

    success = 0
    failed = 0

    for row in rows:
        try:
            row_dict = dict(zip(columns, row))

            # 检查用户是否存在
            if row_dict['user_id'] not in valid_user_ids:
                failed += 1
                continue

            insert_data = {}
            for col in common_columns:
                value = row_dict[col]

                if value is None:
                    insert_data[col] = None
                elif isinstance(value, int) and col in ['has_gps_data']:
                    insert_data[col] = bool(value)
                else:
                    insert_data[col] = value

            cols = ', '.join(common_columns)
            placeholders = ', '.join([f':{col}' for col in common_columns])
            sql = f"INSERT INTO workout_records ({cols}) VALUES ({placeholders})"

            pg_session.execute(text(sql), insert_data)
            pg_session.commit()
            success += 1

        except Exception as e:
            failed += 1
            pg_session.rollback()
            if failed <= 3:
                print(f"   ⚠️  失败: {str(e)[:150]}")

    print(f"   ✅ 成功迁移 {success} 条，失败 {failed} 条")

def migrate_diet_records():
    """迁移饮食记录"""
    print("\n4️⃣ 迁移 diet_records...")

    sqlite_cursor.execute("SELECT * FROM diet_records")
    rows = sqlite_cursor.fetchall()
    columns = [desc[0] for desc in sqlite_cursor.description]

    print(f"   📊 SQLite 中有 {len(rows)} 条记录")

    result = pg_session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'diet_records' ORDER BY ordinal_position")
    )
    pg_columns = [row[0] for row in result]
    common_columns = [col for col in columns if col in pg_columns]

    print(f"   📋 共同列: {len(common_columns)} 个")

    pg_session.execute(text("TRUNCATE TABLE diet_records RESTART IDENTITY CASCADE"))
    pg_session.commit()

    success = 0
    failed = 0

    for row in rows:
        try:
            row_dict = dict(zip(columns, row))

            # 检查用户是否存在
            if row_dict['user_id'] not in valid_user_ids:
                failed += 1
                continue

            insert_data = {}
            for col in common_columns:
                value = row_dict[col]

                if value is None:
                    insert_data[col] = None
                elif isinstance(value, int) and col in ['ai_recognized']:
                    insert_data[col] = bool(value)
                else:
                    insert_data[col] = value

            cols = ', '.join(common_columns)
            placeholders = ', '.join([f':{col}' for col in common_columns])
            sql = f"INSERT INTO diet_records ({cols}) VALUES ({placeholders})"

            pg_session.execute(text(sql), insert_data)
            pg_session.commit()
            success += 1

        except Exception as e:
            failed += 1
            pg_session.rollback()
            if failed <= 3:
                print(f"   ⚠️  失败: {str(e)[:150]}")

    print(f"   ✅ 成功迁移 {success} 条，失败 {failed} 条")

# 执行迁移
try:
    migrate_garmin_data()
    migrate_workout_records()
    migrate_diet_records()
except Exception as e:
    print(f"\n❌ 迁移失败: {str(e)}")
finally:
    sqlite_conn.close()
    pg_session.close()

print("\n" + "=" * 80)
print("✅ 关键数据迁移完成！")
print("=" * 80)

# 验证
pg_session = PgSession()
print("\n5️⃣ 验证迁移结果...")
for table in ["users", "garmin_data", "workout_records", "diet_records"]:
    result = pg_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
    count = result.scalar()
    print(f"   {table}: {count} 条记录")
pg_session.close()

print("\n✅ 迁移完成！")
