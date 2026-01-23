#!/usr/bin/env python3
"""
数据库序列自动修复脚本
修复所有表的主键序列，使其与实际数据同步

使用方法:
    cd /opt/health-app/backend
    source venv/bin/activate
    python3 scripts/fix_sequences.py

参数:
    --dry-run: 只检查不修复
    --table TABLE_NAME: 只修复指定的表
"""

import sys
import argparse
from sqlalchemy import text, inspect
from app.database import SessionLocal, engine


def fix_all_sequences(dry_run=False, specific_table=None):
    """修复所有表的序列"""
    db = SessionLocal()
    
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if specific_table:
            if specific_table not in tables:
                print(f'❌ 表 {specific_table} 不存在')
                return 1
            tables = [specific_table]
        
        print('=' * 80)
        if dry_run:
            print('数据库序列检查（模拟模式）')
        else:
            print('数据库序列修复')
        print('=' * 80)
        print()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for table in sorted(tables):
            try:
                # 检查表是否有 id 列
                columns = [col['name'] for col in inspector.get_columns(table)]
                if 'id' not in columns:
                    continue
                
                seq_name = f'{table}_id_seq'
                
                # 检查序列是否存在
                try:
                    before = db.execute(text(f"SELECT last_value FROM {seq_name};")).scalar()
                except:
                    # 序列不存在，跳过
                    skip_count += 1
                    continue
                
                # 获取最大 id
                max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 1) FROM {table};")).scalar()
                
                # 判断是否需要修复
                if before >= max_id:
                    print(f'⏭️  {table:40s} | 序列正常，跳过 (序列: {before}, 最大ID: {max_id})')
                    skip_count += 1
                    continue
                
                if dry_run:
                    print(f'🔍 {table:40s} | 需要修复: {before:6d} → {max_id:6d}')
                    success_count += 1
                else:
                    # 修复序列
                    db.execute(text(f"""
                        SELECT setval('{seq_name}', (SELECT COALESCE(MAX(id), 1) FROM {table}));
                    """))
                    db.commit()
                    
                    # 验证修复
                    after = db.execute(text(f"SELECT last_value FROM {seq_name};")).scalar()
                    
                    if after >= max_id:
                        print(f'✅ {table:40s} | {before:6d} → {after:6d} (最大ID: {max_id})')
                        success_count += 1
                    else:
                        print(f'❌ {table:40s} | 修复失败: {before:6d} → {after:6d} (最大ID: {max_id})')
                        fail_count += 1
                
            except Exception as e:
                print(f'❌ {table:40s} | 修复失败: {str(e)[:50]}')
                fail_count += 1
                if not dry_run:
                    db.rollback()
        
        print()
        print('=' * 80)
        print('修复结果汇总')
        print('=' * 80)
        print()
        
        if dry_run:
            print(f'🔍 需要修复: {success_count} 个表')
            print(f'⏭️  无需修复: {skip_count} 个表')
            print()
            if success_count > 0:
                print('💡 运行以下命令进行实际修复:')
                print('   python3 scripts/fix_sequences.py')
        else:
            print(f'✅ 修复成功: {success_count} 个表')
            print(f'❌ 修复失败: {fail_count} 个表')
            print(f'⏭️  无需修复: {skip_count} 个表')
            print()
            
            if fail_count > 0:
                print('⚠️  部分表修复失败，请检查日志')
                return 1
            elif success_count > 0:
                print('🎉 所有序列已成功修复！')
                return 0
            else:
                print('✅ 所有序列状态正常，无需修复')
                return 0
        
        print('=' * 80)
        return 0
        
    except Exception as e:
        print(f'❌ 修复过程出错: {e}')
        import traceback
        traceback.print_exc()
        if not dry_run:
            db.rollback()
        return 2
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='修复数据库序列')
    parser.add_argument('--dry-run', action='store_true', help='只检查不修复')
    parser.add_argument('--table', type=str, help='只修复指定的表')
    
    args = parser.parse_args()
    
    exit_code = fix_all_sequences(dry_run=args.dry_run, specific_table=args.table)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
