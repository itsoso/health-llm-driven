"""
SQLite 到 PostgreSQL 数据迁移脚本

使用方法:
    python scripts/migrate_sqlite_to_postgres.py

功能:
1. 从 SQLite 读取所有数据
2. 在 PostgreSQL 中创建表结构
3. 迁移所有数据
4. 验证数据完整性
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from sqlalchemy import create_engine, inspect, MetaData, Table
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 数据库连接配置
SQLITE_URL = "sqlite:///./health.db"
POSTGRES_URL = "postgresql://health_user:health_password_2026@localhost:5432/health_db"


class DatabaseMigrator:
    """数据库迁移工具"""
    
    def __init__(self, source_url: str, target_url: str):
        self.source_url = source_url
        self.target_url = target_url
        
        logger.info(f"源数据库: {source_url}")
        logger.info(f"目标数据库: {target_url}")
        
        # 创建引擎
        self.source_engine = create_engine(source_url)
        self.target_engine = create_engine(target_url)
        
        # 创建会话
        SourceSession = sessionmaker(bind=self.source_engine)
        TargetSession = sessionmaker(bind=self.target_engine)
        
        self.source_session = SourceSession()
        self.target_session = TargetSession()
        
        # 元数据
        self.source_metadata = MetaData()
        self.target_metadata = MetaData()
    
    def get_table_names(self):
        """获取所有表名"""
        inspector = inspect(self.source_engine)
        tables = inspector.get_table_names()
        logger.info(f"发现 {len(tables)} 个表")
        return tables
    
    def create_tables(self):
        """在目标数据库创建表结构"""
        logger.info("正在创建表结构...")
        
        # 使用 SQLAlchemy 的模型定义来创建表
        from app.database import Base
        
        try:
            Base.metadata.create_all(self.target_engine)
            logger.info("✓ 表结构创建成功")
            return True
        except Exception as e:
            logger.error(f"✗ 表结构创建失败: {e}")
            return False
    
    def migrate_table(self, table_name: str) -> dict:
        """迁移单个表的数据"""
        logger.info(f"正在迁移表: {table_name}")
        
        try:
            # 反射表结构
            source_table = Table(
                table_name,
                self.source_metadata,
                autoload_with=self.source_engine
            )
            
            target_table = Table(
                table_name,
                self.target_metadata,
                autoload_with=self.target_engine
            )
            
            # 读取源数据
            source_conn = self.source_engine.connect()
            rows = source_conn.execute(source_table.select()).fetchall()
            source_conn.close()
            
            if not rows:
                logger.info(f"  表 {table_name} 无数据，跳过")
                return {"table": table_name, "count": 0, "status": "empty"}
            
            # 写入目标数据库
            target_conn = self.target_engine.connect()
            
            # 批量插入
            batch_size = 1000
            total_rows = len(rows)
            
            for i in range(0, total_rows, batch_size):
                batch = rows[i:i + batch_size]
                
                # 转换为字典列表
                data_dicts = [dict(row._mapping) for row in batch]
                
                target_conn.execute(target_table.insert(), data_dicts)
                
                logger.info(f"  已迁移 {min(i + batch_size, total_rows)}/{total_rows} 行")
            
            target_conn.commit()
            target_conn.close()
            
            logger.info(f"✓ 表 {table_name} 迁移完成: {total_rows} 行")
            return {"table": table_name, "count": total_rows, "status": "success"}
            
        except Exception as e:
            logger.error(f"✗ 表 {table_name} 迁移失败: {e}")
            return {"table": table_name, "count": 0, "status": "failed", "error": str(e)}
    
    def verify_migration(self, table_name: str) -> bool:
        """验证表迁移完整性"""
        try:
            # 获取源表行数
            source_table = Table(
                table_name,
                self.source_metadata,
                autoload_with=self.source_engine
            )
            source_conn = self.source_engine.connect()
            source_count = source_conn.execute(
                source_table.select().with_only_columns(source_table.c[0])
            ).rowcount
            source_conn.close()
            
            # 获取目标表行数
            target_table = Table(
                table_name,
                self.target_metadata,
                autoload_with=self.target_engine
            )
            target_conn = self.target_engine.connect()
            target_count = target_conn.execute(
                target_table.select().with_only_columns(target_table.c[0])
            ).rowcount
            target_conn.close()
            
            if source_count == target_count:
                logger.info(f"✓ 表 {table_name} 验证通过: {source_count} 行")
                return True
            else:
                logger.error(
                    f"✗ 表 {table_name} 验证失败: "
                    f"源 {source_count} 行 != 目标 {target_count} 行"
                )
                return False
                
        except Exception as e:
            logger.error(f"✗ 表 {table_name} 验证出错: {e}")
            return False
    
    def run(self):
        """执行完整迁移流程"""
        logger.info("=" * 60)
        logger.info("开始数据库迁移")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        # Step 1: 创建表结构
        if not self.create_tables():
            logger.error("表结构创建失败，迁移终止")
            return False
        
        # Step 2: 获取所有表
        tables = self.get_table_names()
        
        # Step 3: 迁移数据
        results = []
        for table in tables:
            result = self.migrate_table(table)
            results.append(result)
        
        # Step 4: 验证数据
        logger.info("")
        logger.info("=" * 60)
        logger.info("验证数据完整性")
        logger.info("=" * 60)
        
        verification_passed = True
        for table in tables:
            if not self.verify_migration(table):
                verification_passed = False
        
        # Step 5: 总结
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("迁移完成")
        logger.info("=" * 60)
        logger.info(f"总耗时: {duration:.2f} 秒")
        logger.info("")
        
        # 统计
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")
        empty_count = sum(1 for r in results if r["status"] == "empty")
        total_rows = sum(r["count"] for r in results)
        
        logger.info(f"表统计:")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {failed_count}")
        logger.info(f"  空表: {empty_count}")
        logger.info(f"  总行数: {total_rows}")
        logger.info("")
        
        if failed_count > 0:
            logger.error("部分表迁移失败:")
            for r in results:
                if r["status"] == "failed":
                    logger.error(f"  - {r['table']}: {r.get('error', 'Unknown error')}")
        
        if not verification_passed:
            logger.error("数据验证未通过，请检查迁移结果")
            return False
        
        logger.info("✓ 数据迁移和验证全部通过！")
        logger.info("")
        logger.info("下一步操作:")
        logger.info("1. 更新 .env 文件，确保 POSTGRES_* 配置正确")
        logger.info("2. 重启应用，使用 PostgreSQL 数据库")
        logger.info("3. 备份 SQLite 数据库: cp health.db health.db.backup")
        
        return True
    
    def close(self):
        """关闭连接"""
        self.source_session.close()
        self.target_session.close()
        self.source_engine.dispose()
        self.target_engine.dispose()


def main():
    """主函数"""
    # 检查 SQLite 数据库是否存在
    if not os.path.exists("health.db"):
        logger.error("错误: health.db 不存在")
        logger.error("请确保在 backend 目录下运行此脚本")
        sys.exit(1)
    
    # 检查 PostgreSQL 连接
    try:
        test_engine = create_engine(POSTGRES_URL)
        test_engine.connect()
        test_engine.dispose()
        logger.info("✓ PostgreSQL 连接测试成功")
    except Exception as e:
        logger.error(f"✗ PostgreSQL 连接失败: {e}")
        logger.error("请确保:")
        logger.error("1. PostgreSQL 服务已启动: pg_isready")
        logger.error("2. 数据库已创建: psql -U health_user -d health_db")
        logger.error("3. .env 配置正确")
        sys.exit(1)
    
    # 确认迁移
    print("")
    print("⚠️  警告: 此操作将清空目标数据库并重新导入数据")
    print("")
    response = input("确认继续? (yes/no): ")
    
    if response.lower() != "yes":
        logger.info("迁移已取消")
        sys.exit(0)
    
    # 执行迁移
    migrator = DatabaseMigrator(SQLITE_URL, POSTGRES_URL)
    
    try:
        success = migrator.run()
        migrator.close()
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("迁移被用户中断")
        migrator.close()
        sys.exit(1)
    except Exception as e:
        logger.error(f"迁移过程出错: {e}")
        migrator.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
