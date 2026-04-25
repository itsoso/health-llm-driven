#!/usr/bin/env python3
"""
数据库序列检查脚本
用于检查所有表的主键序列是否与实际数据同步

使用方法:
    cd /opt/health-app/backend
    source venv/bin/activate
    python3 scripts/check_sequences.py

返回值:
    0 - 所有序列正常
    1 - 发现序列问题
    2 - 检查失败
"""

import sys
from sqlalchemy import text, inspect
from app.database import SessionLocal, engine


def check_all_sequences():
    """检查所有表的序列状态"""
    db = SessionLocal()

    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        print('=' * 80)
        print('数据库序列健康检查')
        print('=' * 80)
        print()

        critical_issues = []  # 序列 < 最大ID
        warnings = []  # 序列 == 最大ID
        normal = []  # 序列 > 最大ID 或表为空

        for table in sorted(tables):
            try:
                # 检查表是否有 id 列
                columns = [col['name'] for col in inspector.get_columns(table)]
                if 'id' not in columns:
                    continue

                seq_name = f'{table}_id_seq'

                # 获取序列当前值
                try:
                    seq_result = db.execute(text(f"SELECT last_value FROM {seq_name};"))
                    seq_value = seq_result.scalar()
                except:
                    # 序列不存在，跳过
                    continue

                # 获取表中最大 id
                max_result = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table};"))
                max_id = max_result.scalar()

                # 获取记录数
                count_result = db.execute(text(f"SELECT COUNT(*) FROM {table};"))
                count = count_result.scalar()

                # 判断状态
                if seq_value < max_id:
                    status = '❌ 异常'
                    critical_issues.append({
                        'table': table,
                        'seq_value': seq_value,
                        'max_id': max_id,
                        'count': count
                    })
                elif seq_value == max_id and count > 0:
                    status = '⚠️  临界'
                    warnings.append({
                        'table': table,
                        'seq_value': seq_value,
                        'max_id': max_id,
                        'count': count
                    })
                else:
                    status = '✅ 正常'
                    normal.append(table)

                print(f'{status} {table:40s} | 序列: {seq_value:6d} | 最大ID: {max_id:6d} | 记录数: {count:6d}')

            except Exception as e:
                print(f'⚠️  {table:40s} | 检查失败: {str(e)[:50]}')

        print()
        print('=' * 80)
        print('检查结果汇总')
        print('=' * 80)
        print()

        if critical_issues:
            print(f'🔴 发现 {len(critical_issues)} 个严重问题（序列 < 最大ID）:')
            for issue in critical_issues:
                print(f'   - {issue["table"]:40s} | 序列: {issue["seq_value"]:6d} < 最大ID: {issue["max_id"]:6d}')
            print()

        if warnings:
            print(f'⚠️  发现 {len(warnings)} 个警告（序列 == 最大ID，下次插入可能失败）:')
            for warning in warnings:
                print(f'   - {warning["table"]:40s} | 序列: {warning["seq_value"]:6d} = 最大ID: {warning["max_id"]:6d}')
            print()

        print(f'✅ {len(normal)} 个表状态正常')
        print()

        if critical_issues:
            print('=' * 80)
            print('🔧 修复建议:')
            print('   运行修复脚本: python3 scripts/fix_sequences.py')
            print('=' * 80)
            return 1
        elif warnings:
            print('=' * 80)
            print('💡 建议:')
            print('   临界状态的表在下次插入时可能失败')
            print('   建议运行修复脚本: python3 scripts/fix_sequences.py')
            print('=' * 80)
            return 0
        else:
            print('=' * 80)
            print('🎉 所有序列状态正常！')
            print('=' * 80)
            return 0

    except Exception as e:
        print(f'❌ 检查失败: {e}')
        import traceback
        traceback.print_exc()
        return 2
    finally:
        db.close()


if __name__ == '__main__':
    exit_code = check_all_sequences()
    sys.exit(exit_code)
