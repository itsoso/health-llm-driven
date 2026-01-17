#!/usr/bin/env python3
"""
SQLite 到 PostgreSQL 数据迁移脚本 (改进版)

使用 SQLAlchemy 模型创建表结构，避免类型不兼容问题

使用方法:
    cd /opt/health-app/backend
    source venv/bin/activate
    POSTGRES_PASSWORD="your_password" python scripts/migrate_to_postgres.py
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
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


def create_tables_from_models(engine):
    """使用 SQLAlchemy 模型创建表结构"""
    logger.info("使用 SQLAlchemy 模型创建表结构...")
    
    # 导入所有模型
    from app.database import Base
    from app.models import (
        User, UserProfile, GarminCredential,
        GarminDailyData, HeartRateSample, WorkoutRecord, WeightRecord,
        CheckinRecord, CheckinTemplate, HabitDefinition, HabitRecord,
        Goal, GoalProgress, DietRecord, WaterIntake,
        SupplementDefinition, SupplementRecord, BloodPressureRecord,
        DiseaseTemplate, UserDiseaseProfile, DiseaseRecord, SymptomLog,
        MedicalExam, MedicalExamItem, HealthAnalysisCache,
        InvitationCode, UserApplication,
        Notification, UserNotificationSetting, WeChatDeviceToken, iOSDeviceToken,
    )
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    logger.info("✓ 表结构创建完成")


def get_all_tables(engine):
    """获取数据库中的所有表"""
    inspector = inspect(engine)
    return inspector.get_table_names()


def migrate_table_data(source_engine, target_engine, table_name):
    """迁移单个表的数据"""
    logger.info(f"迁移表数据: {table_name}")
    
    try:
        # 读取源数据
        with source_engine.connect() as source_conn:
            result = source_conn.execute(text(f"SELECT * FROM {table_name}"))
            rows = result.fetchall()
            columns = list(result.keys())
        
        if not rows:
            logger.info(f"  表 {table_name} 为空，跳过")
            return 0
        
        # 构建插入语句
        placeholders = ", ".join([f":{col}" for col in columns])
        columns_str = ", ".join([f'"{col}"' for col in columns])
        insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'
        
        # 写入目标数据库
        with target_engine.connect() as target_conn:
            # 先清空目标表
            target_conn.execute(text(f'DELETE FROM "{table_name}"'))
            target_conn.commit()
            
            # 分批插入数据
            batch_size = 500
            data_list = [dict(zip(columns, row)) for row in rows]
            
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]
                for row_data in batch:
                    # 处理特殊类型
                    for key, value in row_data.items():
                        # 处理 boolean 类型
                        if isinstance(value, int) and key.startswith('is_'):
                            row_data[key] = bool(value)
                    
                    try:
                        target_conn.execute(text(insert_sql), row_data)
                    except Exception as e:
                        logger.warning(f"  插入行失败: {e}")
                        continue
                        
                target_conn.commit()
            
            logger.info(f"  迁移 {len(rows)} 条记录")
        
        return len(rows)
        
    except Exception as e:
        logger.error(f"  迁移表 {table_name} 失败: {e}")
        return 0


def reset_sequences(target_engine, table_name):
    """重置 PostgreSQL 序列（自增ID）"""
    try:
        with target_engine.connect() as conn:
            # 获取当前最大ID
            result = conn.execute(text(f'SELECT MAX(id) FROM "{table_name}"'))
            max_id = result.scalar() or 0
            
            if max_id > 0:
                # 重置序列
                seq_name = f"{table_name}_id_seq"
                conn.execute(text(f"SELECT setval('{seq_name}', {max_id}, true)"))
                conn.commit()
                logger.info(f"  重置序列 {seq_name} 到 {max_id}")
    except Exception as e:
        logger.debug(f"  序列重置跳过 {table_name}: {e}")


def main():
    """主迁移流程"""
    logger.info("=" * 60)
    logger.info("SQLite → PostgreSQL 数据迁移 (改进版)")
    logger.info("=" * 60)
    
    # 创建数据库引擎
    logger.info(f"源数据库: {SQLITE_URL}")
    logger.info(f"目标数据库: postgresql://{POSTGRES_USER}:***@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    source_engine = create_engine(SQLITE_URL)
    target_engine = create_engine(POSTGRES_URL)
    
    # 测试连接
    try:
        with source_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("✓ SQLite 连接成功")
    except Exception as e:
        logger.error(f"✗ SQLite 连接失败: {e}")
        sys.exit(1)
    
    try:
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("✓ PostgreSQL 连接成功")
    except Exception as e:
        logger.error(f"✗ PostgreSQL 连接失败: {e}")
        sys.exit(1)
    
    # 使用模型创建表结构
    create_tables_from_models(target_engine)
    
    # 获取所有源表
    source_tables = get_all_tables(source_engine)
    target_tables = get_all_tables(target_engine)
    
    logger.info(f"源数据库: {len(source_tables)} 个表")
    logger.info(f"目标数据库: {len(target_tables)} 个表")
    
    # 定义迁移顺序（按外键依赖）
    priority_order = [
        "users",
        "invitation_codes", 
        "user_applications",
        "user_profiles",
        "garmin_credentials",
        "checkin_templates",
        "habit_definitions",
        "supplement_definitions",
        "disease_templates",
        "goals",
    ]
    
    # 排序表
    ordered_tables = []
    for t in priority_order:
        if t in source_tables and t in target_tables:
            ordered_tables.append(t)
    
    for t in source_tables:
        if t in target_tables and t not in ordered_tables:
            ordered_tables.append(t)
    
    # 迁移数据
    total_records = 0
    success_tables = []
    
    for table_name in ordered_tables:
        count = migrate_table_data(source_engine, target_engine, table_name)
        if count > 0:
            total_records += count
            success_tables.append(table_name)
            reset_sequences(target_engine, table_name)
    
    # 打印迁移结果
    logger.info("=" * 60)
    logger.info("迁移完成")
    logger.info("=" * 60)
    logger.info(f"成功迁移: {len(success_tables)} 个表")
    logger.info(f"总记录数: {total_records} 条")
    
    # 验证关键表
    logger.info("")
    logger.info("验证关键表数据:")
    with target_engine.connect() as conn:
        for table in ["users", "garmin_credentials", "garmin_data", "checkin_records"]:
            if table in target_tables:
                result = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                count = result.scalar()
                logger.info(f"  {table}: {count} 条记录")
    
    logger.info("")
    logger.info("下一步操作:")
    logger.info("1. 更新环境变量启用 PostgreSQL:")
    logger.info(f"   export POSTGRES_HOST={POSTGRES_HOST}")
    logger.info(f"   export POSTGRES_PORT={POSTGRES_PORT}")
    logger.info(f"   export POSTGRES_DB={POSTGRES_DB}")
    logger.info(f"   export POSTGRES_USER={POSTGRES_USER}")
    logger.info("   export POSTGRES_PASSWORD=<your_password>")
    logger.info("2. 重启后端服务: systemctl restart health-backend")


if __name__ == "__main__":
    main()
