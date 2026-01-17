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
from sqlalchemy import create_engine, text, inspect, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

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


def create_tables_from_models(target_engine):
    """使用 SQLAlchemy 模型创建表结构"""
    logger.info("使用 SQLAlchemy 模型创建表结构...")
    
    # 创建一个新的 Base 用于 PostgreSQL
    # 这样不会影响 app.database 中的 SQLite 连接
    from sqlalchemy.ext.declarative import declarative_base
    PostgresBase = declarative_base()
    
    # 从 SQLite 反射表结构，但用 PostgreSQL 兼容类型创建
    # 这里我们直接用 SQLAlchemy 的表反射和创建功能
    sqlite_engine = create_engine(SQLITE_URL)
    
    # 使用 MetaData 反射 SQLite 表结构
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)
    
    # 在 PostgreSQL 中创建表
    # 需要转换不兼容的类型
    for table in metadata.tables.values():
        try:
            # 创建表（如果不存在）
            table.create(bind=target_engine, checkfirst=True)
            logger.info(f"  创建表: {table.name}")
        except Exception as e:
            logger.warning(f"  创建表 {table.name} 跳过: {e}")
    
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
            
            inserted_count = 0
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
                        inserted_count += 1
                    except Exception as e:
                        logger.debug(f"  插入行失败: {e}")
                        continue
                        
                target_conn.commit()
            
            logger.info(f"  迁移 {inserted_count}/{len(rows)} 条记录")
        
        return inserted_count
        
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
                logger.debug(f"  重置序列 {seq_name} 到 {max_id}")
    except Exception as e:
        pass  # 序列可能不存在


def create_postgres_tables_manually(target_engine):
    """手动创建 PostgreSQL 表（使用兼容类型）"""
    logger.info("手动创建 PostgreSQL 表结构...")
    
    # 核心表创建 SQL（PostgreSQL 兼容）
    tables_sql = [
        # users 表
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            birth_date DATE,
            gender VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            email VARCHAR(255) UNIQUE,
            username VARCHAR(100) UNIQUE,
            hashed_password VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            is_admin BOOLEAN DEFAULT FALSE,
            wechat_openid VARCHAR(255) UNIQUE,
            wechat_unionid VARCHAR(255),
            wechat_session_key VARCHAR(255),
            avatar_url TEXT,
            phone VARCHAR(50),
            is_approved BOOLEAN DEFAULT FALSE,
            invite_code VARCHAR(50)
        )
        """,
        
        # garmin_credentials 表
        """
        CREATE TABLE IF NOT EXISTS garmin_credentials (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            email VARCHAR(255) NOT NULL,
            encrypted_password TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            last_sync_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            garth_session TEXT,
            session_expires_at TIMESTAMP
        )
        """,
        
        # invitation_codes 表
        """
        CREATE TABLE IF NOT EXISTS invitation_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(32) UNIQUE NOT NULL,
            created_by INTEGER REFERENCES users(id),
            note VARCHAR(200),
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # user_applications 表
        """
        CREATE TABLE IF NOT EXISTS user_applications (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            name VARCHAR(100) NOT NULL,
            phone VARCHAR(50),
            invitation_code_id INTEGER REFERENCES invitation_codes(id),
            health_questionnaire TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            reviewed_by INTEGER REFERENCES users(id),
            reviewed_at TIMESTAMP,
            review_note TEXT,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            hashed_password TEXT
        )
        """,
        
        # user_profiles 表
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES users(id),
            gender VARCHAR(20),
            birth_date DATE,
            height_cm REAL,
            blood_type VARCHAR(10),
            current_weight_kg REAL,
            target_weight_kg REAL,
            body_fat_percentage REAL,
            occupation VARCHAR(100),
            work_style VARCHAR(50),
            diet_preference VARCHAR(50),
            exercise_preference VARCHAR(50),
            sleep_schedule VARCHAR(50),
            health_conditions TEXT,
            allergies TEXT,
            medications TEXT,
            family_history TEXT,
            health_goals TEXT,
            fitness_level VARCHAR(50),
            daily_water_goal_ml INTEGER,
            daily_calorie_goal INTEGER,
            daily_steps_goal INTEGER,
            preferred_exercise_time VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # garmin_data 表
        """
        CREATE TABLE IF NOT EXISTS garmin_data (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            record_date DATE NOT NULL,
            steps INTEGER,
            distance_km REAL,
            active_calories INTEGER,
            total_calories INTEGER,
            floors_climbed INTEGER,
            stress_level_avg INTEGER,
            stress_level_max INTEGER,
            body_battery_high INTEGER,
            body_battery_low INTEGER,
            body_battery_current INTEGER,
            resting_heart_rate INTEGER,
            hrv_weekly_avg INTEGER,
            hrv_last_night INTEGER,
            sleep_score INTEGER,
            sleep_start_time VARCHAR(20),
            sleep_end_time VARCHAR(20),
            total_sleep_duration INTEGER,
            deep_sleep_duration INTEGER,
            light_sleep_duration INTEGER,
            rem_sleep_duration INTEGER,
            awake_duration INTEGER,
            respiration_avg INTEGER,
            spo2_avg INTEGER,
            intensity_minutes_moderate INTEGER,
            intensity_minutes_vigorous INTEGER,
            vo2max_running REAL,
            vo2max_cycling REAL,
            training_readiness INTEGER,
            training_load_7day REAL,
            raw_data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE (user_id, record_date)
        )
        """,
        
        # workout_records 表
        """
        CREATE TABLE IF NOT EXISTS workout_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            workout_date DATE NOT NULL,
            workout_type VARCHAR(50) NOT NULL,
            workout_name VARCHAR(255),
            duration_minutes INTEGER,
            distance_km REAL,
            calories_burned INTEGER,
            avg_heart_rate INTEGER,
            max_heart_rate INTEGER,
            avg_pace VARCHAR(20),
            elevation_gain_m INTEGER,
            training_effect_aerobic REAL,
            training_effect_anaerobic REAL,
            vo2max REAL,
            garmin_activity_id BIGINT UNIQUE,
            has_gps_data BOOLEAN DEFAULT FALSE,
            gps_data JSON,
            raw_data JSON,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # checkin_templates 表
        """
        CREATE TABLE IF NOT EXISTS checkin_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            description TEXT,
            icon VARCHAR(20),
            default_target INTEGER DEFAULT 1,
            unit VARCHAR(20),
            is_system BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # checkin_records 表
        """
        CREATE TABLE IF NOT EXISTS checkin_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            template_id INTEGER REFERENCES checkin_templates(id),
            checkin_date DATE NOT NULL,
            completed_count INTEGER DEFAULT 1,
            target_count INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, template_id, checkin_date)
        )
        """,
        
        # diet_records 表
        """
        CREATE TABLE IF NOT EXISTS diet_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            record_date DATE NOT NULL,
            meal_type VARCHAR(20) NOT NULL,
            food_items TEXT,
            calories INTEGER,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            fiber_g REAL,
            notes TEXT,
            image_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # water_intakes 表
        """
        CREATE TABLE IF NOT EXISTS water_intakes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            record_date DATE NOT NULL,
            amount_ml INTEGER NOT NULL,
            intake_time TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # weight_records 表
        """
        CREATE TABLE IF NOT EXISTS weight_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            record_date DATE NOT NULL,
            weight REAL NOT NULL,
            body_fat_percentage REAL,
            muscle_mass_kg REAL,
            notes TEXT,
            source VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, record_date)
        )
        """,
        
        # blood_pressure_records 表
        """
        CREATE TABLE IF NOT EXISTS blood_pressure_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            record_date DATE NOT NULL,
            systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL,
            pulse INTEGER,
            notes TEXT,
            measured_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # goals 表
        """
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            category VARCHAR(50) NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            target_value REAL,
            current_value REAL DEFAULT 0,
            unit VARCHAR(20),
            start_date DATE,
            target_date DATE,
            status VARCHAR(20) DEFAULT 'active',
            priority INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # goal_progress 表
        """
        CREATE TABLE IF NOT EXISTS goal_progress (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER REFERENCES goals(id),
            record_date DATE NOT NULL,
            value REAL NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # supplement_definitions 表
        """
        CREATE TABLE IF NOT EXISTS supplement_definitions (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            description TEXT,
            dosage VARCHAR(100),
            benefits TEXT,
            is_system BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # supplement_records 表
        """
        CREATE TABLE IF NOT EXISTS supplement_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            supplement_id INTEGER REFERENCES supplement_definitions(id),
            record_date DATE NOT NULL,
            taken_count INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # habit_definitions 表
        """
        CREATE TABLE IF NOT EXISTS habit_definitions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            description TEXT,
            frequency VARCHAR(20) DEFAULT 'daily',
            target_count INTEGER DEFAULT 1,
            icon VARCHAR(20),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # habit_records 表
        """
        CREATE TABLE IF NOT EXISTS habit_records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            habit_id INTEGER REFERENCES habit_definitions(id),
            record_date DATE NOT NULL,
            completed_count INTEGER DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, habit_id, record_date)
        )
        """,
        
        # medical_exams 表
        """
        CREATE TABLE IF NOT EXISTS medical_exams (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            exam_date DATE NOT NULL,
            exam_type VARCHAR(100),
            hospital VARCHAR(200),
            summary TEXT,
            file_path VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # medical_exam_items 表
        """
        CREATE TABLE IF NOT EXISTS medical_exam_items (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER REFERENCES medical_exams(id),
            item_name VARCHAR(100) NOT NULL,
            value VARCHAR(100),
            unit VARCHAR(50),
            reference_range VARCHAR(100),
            is_abnormal BOOLEAN DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # health_analysis_cache 表
        """
        CREATE TABLE IF NOT EXISTS health_analysis_cache (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            analysis_date DATE NOT NULL,
            cache_type VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            metadata JSON,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, analysis_date, cache_type)
        )
        """,
        
        # disease_templates 表
        """
        CREATE TABLE IF NOT EXISTS disease_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50),
            description TEXT,
            symptoms TEXT,
            treatments TEXT,
            daily_care TEXT,
            warning_signs TEXT,
            is_system BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # user_disease_profiles 表
        """
        CREATE TABLE IF NOT EXISTS user_disease_profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            disease_id INTEGER REFERENCES disease_templates(id),
            diagnosis_date DATE,
            severity VARCHAR(20),
            current_status VARCHAR(50),
            notes TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # symptom_logs 表
        """
        CREATE TABLE IF NOT EXISTS symptom_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            disease_profile_id INTEGER REFERENCES user_disease_profiles(id),
            log_date DATE NOT NULL,
            symptom_type VARCHAR(100),
            severity INTEGER,
            duration_minutes INTEGER,
            triggers TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # user_notification_settings 表
        """
        CREATE TABLE IF NOT EXISTS user_notification_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES users(id),
            enable_push BOOLEAN DEFAULT TRUE,
            enable_email BOOLEAN DEFAULT FALSE,
            quiet_hours_start VARCHAR(5),
            quiet_hours_end VARCHAR(5),
            reminder_drink_water BOOLEAN DEFAULT TRUE,
            reminder_exercise BOOLEAN DEFAULT TRUE,
            reminder_sleep BOOLEAN DEFAULT TRUE,
            reminder_supplements BOOLEAN DEFAULT TRUE,
            alert_heart_rate BOOLEAN DEFAULT TRUE,
            alert_blood_pressure BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        
        # notification_logs 表
        """
        CREATE TABLE IF NOT EXISTS notification_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            notification_type VARCHAR(50) NOT NULL,
            title VARCHAR(200),
            body TEXT,
            channel VARCHAR(20),
            status VARCHAR(20),
            sent_at TIMESTAMP,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    
    with target_engine.connect() as conn:
        for sql in tables_sql:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                logger.debug(f"  表创建跳过: {e}")
    
    logger.info("✓ 表结构创建完成")


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
    
    # 使用手动 SQL 创建表结构
    create_postgres_tables_manually(target_engine)
    
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
        for table in ["users", "garmin_credentials", "garmin_data", "checkin_records", "workout_records"]:
            if table in target_tables:
                try:
                    result = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                    count = result.scalar()
                    logger.info(f"  {table}: {count} 条记录")
                except:
                    pass
    
    logger.info("")
    logger.info("下一步操作:")
    logger.info("1. 更新 .env 文件启用 PostgreSQL:")
    logger.info(f"   POSTGRES_HOST={POSTGRES_HOST}")
    logger.info(f"   POSTGRES_PORT={POSTGRES_PORT}")
    logger.info(f"   POSTGRES_DB={POSTGRES_DB}")
    logger.info(f"   POSTGRES_USER={POSTGRES_USER}")
    logger.info("   POSTGRES_PASSWORD=<your_password>")
    logger.info("2. 重启后端服务: systemctl restart health-backend")


if __name__ == "__main__":
    main()
