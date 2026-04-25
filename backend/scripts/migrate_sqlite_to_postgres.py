#!/usr/bin/env python3
"""
SQLite 到 PostgreSQL 数据迁移脚本

使用方法:
    python3 scripts/migrate_sqlite_to_postgres.py

功能:
    - 从 SQLite 数据库读取数据
    - 转换数据格式（处理 JSON、日期等）
    - 导入到 PostgreSQL 数据库
    - 保持数据完整性和关系
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import json
from datetime import datetime
from typing import List, Dict, Any
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


class SQLiteToPostgresMigrator:
    """SQLite 到 PostgreSQL 迁移器"""

    def __init__(self, sqlite_path: str = "health.db"):
        self.sqlite_path = sqlite_path
        self.sqlite_conn = None
        self.pg_conn = None

    def connect(self):
        """连接到两个数据库"""
        # 连接 SQLite
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row

        # 连接 PostgreSQL
        pg_url = settings.effective_database_url
        if not pg_url.startswith('postgresql'):
            raise ValueError("PostgreSQL 配置未设置")

        # 解析 PostgreSQL URL
        # postgresql://user:pass@host:port/db
        parts = pg_url.replace('postgresql://', '').split('@')
        user_pass = parts[0].split(':')
        host_port_db = parts[1].split('/')
        host_port = host_port_db[0].split(':')

        self.pg_conn = psycopg2.connect(
            host=host_port[0],
            port=int(host_port[1]) if len(host_port) > 1 else 5432,
            database=host_port_db[1],
            user=user_pass[0],
            password=user_pass[1]
        )

        print("✅ 数据库连接成功")

    def close(self):
        """关闭数据库连接"""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_conn:
            self.pg_conn.close()
        print("✅ 数据库连接已关闭")

    def get_table_count(self, table_name: str, db: str = 'sqlite') -> int:
        """获取表中的记录数"""
        if db == 'sqlite':
            cursor = self.sqlite_conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]
        else:
            cursor = self.pg_conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]

    def migrate_performance_metrics(self):
        """迁移性能指标数据"""
        table_name = "performance_metrics"

        # 检查源表数据量
        sqlite_count = self.get_table_count(table_name, 'sqlite')
        print(f"\n📊 {table_name}: SQLite 中有 {sqlite_count} 条记录")

        if sqlite_count == 0:
            print(f"⏭️  跳过 {table_name}（无数据）")
            return

        # 读取 SQLite 数据
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # 准备 PostgreSQL 插入语句
        pg_cursor = self.pg_conn.cursor()

        insert_sql = """
            INSERT INTO performance_metrics (
                user_id, session_id, platform, metric_type, metric_name,
                duration, start_time, end_time, details, meta_data,
                success, error_message, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # 转换并插入数据
        data_to_insert = []
        for row in rows:
            data_to_insert.append((
                row['user_id'],
                row['session_id'],
                row['platform'],
                row['metric_type'],
                row['metric_name'],
                row['duration'],
                row['start_time'],
                row['end_time'],
                json.loads(row['details']) if row['details'] else None,
                json.loads(row['meta_data']) if row['meta_data'] else None,
                row['success'],
                row['error_message'],
                row['created_at']
            ))

        # 批量插入
        execute_batch(pg_cursor, insert_sql, data_to_insert, page_size=100)
        self.pg_conn.commit()

        # 验证
        pg_count = self.get_table_count(table_name, 'postgres')
        print(f"✅ {table_name}: 成功迁移 {len(data_to_insert)} 条记录")
        print(f"   PostgreSQL 中现有 {pg_count} 条记录")

    def migrate_performance_alerts(self):
        """迁移性能告警数据"""
        table_name = "performance_alerts"

        # 检查源表数据量
        sqlite_count = self.get_table_count(table_name, 'sqlite')
        print(f"\n📊 {table_name}: SQLite 中有 {sqlite_count} 条记录")

        if sqlite_count == 0:
            print(f"⏭️  跳过 {table_name}（无数据）")
            return

        # 读取 SQLite 数据
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # 准备 PostgreSQL 插入语句
        pg_cursor = self.pg_conn.cursor()

        insert_sql = """
            INSERT INTO performance_alerts (
                alert_type, severity, platform, metric_name, metric_value,
                threshold, description, details, status, resolved_at,
                resolved_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # 转换并插入数据
        data_to_insert = []
        for row in rows:
            data_to_insert.append((
                row['alert_type'],
                row['severity'],
                row['platform'],
                row['metric_name'],
                row['metric_value'],
                row['threshold'],
                row['description'],
                json.loads(row['details']) if row['details'] else None,
                row['status'],
                row['resolved_at'],
                row['resolved_by'],
                row['created_at'],
                row['updated_at']
            ))

        # 批量插入
        execute_batch(pg_cursor, insert_sql, data_to_insert, page_size=100)
        self.pg_conn.commit()

        # 验证
        pg_count = self.get_table_count(table_name, 'postgres')
        print(f"✅ {table_name}: 成功迁移 {len(data_to_insert)} 条记录")
        print(f"   PostgreSQL 中现有 {pg_count} 条记录")

    def migrate_performance_summaries(self):
        """迁移性能汇总数据"""
        table_name = "performance_summaries"

        # 检查源表数据量
        sqlite_count = self.get_table_count(table_name, 'sqlite')
        print(f"\n📊 {table_name}: SQLite 中有 {sqlite_count} 条记录")

        if sqlite_count == 0:
            print(f"⏭️  跳过 {table_name}（无数据）")
            return

        # 读取 SQLite 数据
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # 准备 PostgreSQL 插入语句
        pg_cursor = self.pg_conn.cursor()

        insert_sql = """
            INSERT INTO performance_summaries (
                platform, metric_type, metric_name, date, hour,
                total_count, success_count, error_count,
                avg_duration, min_duration, max_duration,
                p50_duration, p90_duration, p95_duration, p99_duration,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        # 转换并插入数据
        data_to_insert = []
        for row in rows:
            data_to_insert.append((
                row['platform'],
                row['metric_type'],
                row['metric_name'],
                row['date'],
                row['hour'],
                row['total_count'],
                row['success_count'],
                row['error_count'],
                row['avg_duration'],
                row['min_duration'],
                row['max_duration'],
                row['p50_duration'],
                row['p90_duration'],
                row['p95_duration'],
                row['p99_duration'],
                row['created_at'],
                row['updated_at']
            ))

        # 批量插入
        execute_batch(pg_cursor, insert_sql, data_to_insert, page_size=100)
        self.pg_conn.commit()

        # 验证
        pg_count = self.get_table_count(table_name, 'postgres')
        print(f"✅ {table_name}: 成功迁移 {len(data_to_insert)} 条记录")
        print(f"   PostgreSQL 中现有 {pg_count} 条记录")

    def migrate_all(self):
        """迁移所有数据"""
        print("🚀 开始数据迁移...")
        print(f"📁 SQLite: {self.sqlite_path}")
        print(f"🐘 PostgreSQL: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

        try:
            self.connect()

            # 迁移性能监控表
            self.migrate_performance_metrics()
            self.migrate_performance_alerts()
            self.migrate_performance_summaries()

            print("\n🎉 数据迁移完成！")

        except Exception as e:
            print(f"\n❌ 迁移失败: {e}")
            if self.pg_conn:
                self.pg_conn.rollback()
            raise
        finally:
            self.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='SQLite 到 PostgreSQL 数据迁移')
    parser.add_argument(
        '--sqlite-db',
        default='health.db',
        help='SQLite 数据库文件路径（默认: health.db）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅检查数据量，不执行迁移'
    )

    args = parser.parse_args()

    if args.dry_run:
        print("🔍 Dry Run 模式：仅检查数据量")
        migrator = SQLiteToPostgresMigrator(args.sqlite_db)
        migrator.connect()

        for table in ['performance_metrics', 'performance_alerts', 'performance_summaries']:
            sqlite_count = migrator.get_table_count(table, 'sqlite')
            pg_count = migrator.get_table_count(table, 'postgres')
            print(f"📊 {table}:")
            print(f"   SQLite: {sqlite_count} 条")
            print(f"   PostgreSQL: {pg_count} 条")

        migrator.close()
    else:
        migrator = SQLiteToPostgresMigrator(args.sqlite_db)
        migrator.migrate_all()


if __name__ == '__main__':
    main()
