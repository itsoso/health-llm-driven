#!/usr/bin/env python3
"""
SQLite 到 PostgreSQL 数据迁移脚本

使用方法:
    python scripts/migrate_to_postgres.py

环境变量:
    POSTGRES_HOST=localhost
    POSTGRES_PORT=5432
    POSTGRES_DB=health_db
    POSTGRES_USER=health_user
    POSTGRES_PASSWORD=your_password
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SQLite 源数据库
SQLITE_URL = "sqlite:///./health.db"

# PostgreSQL 目标数据库
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "health_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "health_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

if not POSTGRES_PASSWORD:
    logger.error("请设置 POSTGRES_PASSWORD 环境变量")
    sys.exit(1)

POSTGRES_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


def get_all_tables(engine):
    """获取数据库中的所有表"""
    inspector = inspect(engine)
    return inspector.get_table_names()


def migrate_table(source_engine, target_engine, table_name, metadata):
    """迁移单个表的数据"""
    logger.info(f"迁移表: {table_name}")
    
    # 反射源表结构
    source_table = Table(table_name, metadata, autoload_with=source_engine)
    
    # 在目标数据库创建表（如果不存在）
    source_table.create(target_engine, checkfirst=True)
    
    # 读取源数据
    with source_engine.connect() as source_conn:
        result = source_conn.execute(source_table.select())
        rows = result.fetchall()
        columns = result.keys()
    
    if not rows:
        logger.info(f"  表 {table_name} 为空，跳过")
        return 0
    
    # 写入目标数据库
    with target_engine.connect() as target_conn:
        # 先清空目标表（如果需要全新迁移）
        target_conn.execute(source_table.delete())
        target_conn.commit()
        
        # 批量插入数据
        data_list = [dict(zip(columns, row)) for row in rows]
        
        # 分批插入，每批1000条
        batch_size = 1000
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            target_conn.execute(source_table.insert(), batch)
            target_conn.commit()
        
        logger.info(f"  迁移 {len(rows)} 条记录")
    
    return len(rows)


def reset_sequences(target_engine, table_name):
    """重置 PostgreSQL 序列（自增ID）"""
    try:
        with target_engine.connect() as conn:
            # 获取表的主键列
            result = conn.execute(f"""
                SELECT pg_get_serial_sequence('{table_name}', 'id')
            """)
            seq_name = result.scalar()
            
            if seq_name:
                # 获取当前最大ID
                result = conn.execute(f"SELECT MAX(id) FROM {table_name}")
                max_id = result.scalar() or 0
                
                # 重置序列
                conn.execute(f"SELECT setval('{seq_name}', {max_id + 1}, false)")
                conn.commit()
                logger.info(f"  重置序列 {seq_name} 到 {max_id + 1}")
    except Exception as e:
        logger.warning(f"  无法重置序列 {table_name}: {e}")


def main():
    """主迁移流程"""
    logger.info("=" * 60)
    logger.info("SQLite → PostgreSQL 数据迁移")
    logger.info("=" * 60)
    
    # 创建数据库引擎
    logger.info(f"源数据库: {SQLITE_URL}")
    logger.info(f"目标数据库: postgresql://{POSTGRES_USER}:***@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    source_engine = create_engine(SQLITE_URL)
    target_engine = create_engine(POSTGRES_URL)
    
    # 测试连接
    try:
        with source_engine.connect() as conn:
            logger.info("✓ SQLite 连接成功")
    except Exception as e:
        logger.error(f"✗ SQLite 连接失败: {e}")
        sys.exit(1)
    
    try:
        with target_engine.connect() as conn:
            logger.info("✓ PostgreSQL 连接成功")
    except Exception as e:
        logger.error(f"✗ PostgreSQL 连接失败: {e}")
        sys.exit(1)
    
    # 获取所有表
    tables = get_all_tables(source_engine)
    logger.info(f"发现 {len(tables)} 个表: {', '.join(tables)}")
    
    # 创建元数据对象
    metadata = MetaData()
    
    # 迁移每个表
    total_records = 0
    success_tables = []
    failed_tables = []
    
    # 定义迁移顺序（考虑外键依赖）
    # 先迁移没有外键依赖的表，再迁移有依赖的表
    priority_tables = [
        "users", "invitation_codes", "user_applications",
        "user_profiles", "garmin_credentials"
    ]
    
    # 按优先级排序
    ordered_tables = []
    for t in priority_tables:
        if t in tables:
            ordered_tables.append(t)
    for t in tables:
        if t not in ordered_tables:
            ordered_tables.append(t)
    
    for table_name in ordered_tables:
        try:
            count = migrate_table(source_engine, target_engine, table_name, metadata)
            total_records += count
            success_tables.append(table_name)
            
            # 重置 PostgreSQL 序列
            reset_sequences(target_engine, table_name)
            
        except Exception as e:
            logger.error(f"✗ 迁移表 {table_name} 失败: {e}")
            failed_tables.append(table_name)
    
    # 打印迁移结果
    logger.info("=" * 60)
    logger.info("迁移完成")
    logger.info("=" * 60)
    logger.info(f"成功迁移: {len(success_tables)} 个表")
    logger.info(f"总记录数: {total_records} 条")
    
    if failed_tables:
        logger.warning(f"失败表: {', '.join(failed_tables)}")
    
    logger.info("")
    logger.info("下一步操作:")
    logger.info("1. 验证数据完整性")
    logger.info("2. 更新环境变量启用 PostgreSQL:")
    logger.info(f"   POSTGRES_HOST={POSTGRES_HOST}")
    logger.info(f"   POSTGRES_PORT={POSTGRES_PORT}")
    logger.info(f"   POSTGRES_DB={POSTGRES_DB}")
    logger.info(f"   POSTGRES_USER={POSTGRES_USER}")
    logger.info("   POSTGRES_PASSWORD=<your_password>")
    logger.info("3. 重启后端服务")


if __name__ == "__main__":
    main()
