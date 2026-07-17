#!/usr/bin/env python3
"""
数据迁移脚本 - SQLite → PostgreSQL
立即执行版本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import sqlite3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

# 数据库连接配置
SQLITE_DB = "/opt/health-app/backend/health.db"
POSTGRES_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
if not POSTGRES_URL:
    raise RuntimeError("POSTGRES_URL or DATABASE_URL must be set; no database credential is embedded in this script")

print("=" * 80)
print("🚀 开始数据迁移: SQLite → PostgreSQL")
print("=" * 80)

# 连接数据库
print("\n1️⃣ 连接数据库...")
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

pg_engine = create_engine(POSTGRES_URL)
PgSession = sessionmaker(bind=pg_engine)
pg_session = PgSession()

print("✅ 数据库连接成功")

# 需要迁移的表（按依赖顺序）
TABLES_TO_MIGRATE = [
    # 基础表
    "users",
    "user_profiles",

    # 健康数据表
    "garmin_data",
    "workout_records",
    "diet_records",
    "weight_records",
    "blood_pressure_records",
    "water_intakes",
    "exercise_records",
    "basic_health_data",

    # 医疗相关
    "medical_exams",
    "medical_exam_items",
    "disease_records",
    "symptom_logs",

    # 补剂和习惯
    "supplement_definitions",
    "supplement_records",
    "supplement_intakes",
    "habit_definitions",
    "habit_records",

    # 目标和打卡
    "health_goals",
    "goals",
    "goal_progress",
    "checkin_templates",
    "checkin_records",
    "health_checkins",

    # 其他
    "invitation_codes",
    "user_applications",
    "garmin_credentials",
    "device_credentials",
    "reminder_configs",
    "notification_logs",
    "user_notification_settings",
    "daily_recommendations",
    "daily_reviews",
    "period_reviews",
    "health_analysis_cache",
]

def get_table_columns(cursor, table_name):
    """获取表的所有列名"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

def migrate_table(table_name):
    """迁移单个表"""
    try:
        print(f"\n📦 迁移表: {table_name}")

        # 检查 SQLite 表是否存在
        sqlite_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        if not sqlite_cursor.fetchone():
            print(f"   ⚠️  表不存在，跳过")
            return

        # 获取 SQLite 数据
        sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = sqlite_cursor.fetchone()[0]

        if count == 0:
            print(f"   ℹ️  表为空，跳过")
            return

        print(f"   📊 SQLite 中有 {count} 条记录")

        # 获取表结构
        columns = get_table_columns(sqlite_cursor, table_name)

        # 读取所有数据
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()

        # 检查 PostgreSQL 表是否存在
        result = pg_session.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)"),
            {"table": table_name}
        )
        if not result.scalar():
            print(f"   ⚠️  PostgreSQL 表不存在，跳过")
            return

        # 获取 PostgreSQL 表的列
        result = pg_session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :table ORDER BY ordinal_position"),
            {"table": table_name}
        )
        pg_columns = [row[0] for row in result]

        # 找到共同的列
        common_columns = [col for col in columns if col in pg_columns]

        if not common_columns:
            print(f"   ⚠️  没有共同的列，跳过")
            return

        print(f"   📋 共同列: {len(common_columns)} 个")

        # 清空 PostgreSQL 表（如果需要）
        pg_session.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
        pg_session.commit()

        # 插入数据
        success_count = 0
        error_count = 0

        for row in rows:
            try:
                # 构建插入语句
                row_dict = dict(zip(columns, row))

                # 只使用共同的列
                insert_data = {col: row_dict[col] for col in common_columns}

                # 处理特殊类型
                for key, value in insert_data.items():
                    # 处理 JSON 字段
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        try:
                            json.loads(value)  # 验证是否为有效 JSON
                        except:
                            pass
                    # 处理布尔值
                    if isinstance(value, int) and isinstance(key, str) and key.lower().startswith(('is_', 'has_', 'enabled', 'valid', 'active')):
                        insert_data[key] = bool(value)

                # 构建 SQL
                cols = ', '.join(common_columns)
                placeholders = ', '.join([f':{col}' for col in common_columns])
                sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

                pg_session.execute(text(sql), insert_data)
                success_count += 1

            except Exception as e:
                error_count += 1
                if error_count <= 3:  # 只显示前3个错误
                    print(f"   ⚠️  插入失败: {str(e)[:100]}")

        pg_session.commit()

        print(f"   ✅ 成功迁移 {success_count} 条记录")
        if error_count > 0:
            print(f"   ⚠️  失败 {error_count} 条记录")

    except Exception as e:
        print(f"   ❌ 迁移失败: {str(e)}")
        pg_session.rollback()

# 执行迁移
print("\n2️⃣ 开始迁移数据...")
print("-" * 80)

total_success = 0
total_failed = 0

for table in TABLES_TO_MIGRATE:
    try:
        migrate_table(table)
    except Exception as e:
        print(f"❌ 表 {table} 迁移失败: {str(e)}")

# 关闭连接
print("\n3️⃣ 清理资源...")
sqlite_conn.close()
pg_session.close()

print("\n" + "=" * 80)
print("✅ 数据迁移完成！")
print("=" * 80)

# 验证迁移结果
print("\n4️⃣ 验证迁移结果...")
print("-" * 80)

pg_session = PgSession()

for table in ["users", "garmin_data", "workout_records", "diet_records", "user_profiles"]:
    try:
        result = pg_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = result.scalar()
        print(f"   {table}: {count} 条记录")
    except:
        pass

pg_session.close()

print("\n✅ 迁移脚本执行完成！")
