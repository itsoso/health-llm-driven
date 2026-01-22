#!/usr/bin/env python3
"""
修复 goals 表缺失的字段
添加 goal_period 和其他缺失的字段
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from sqlalchemy import text, inspect

def fix_goals_schema():
    """修复 goals 表结构"""
    print("=" * 60)
    print("修复 goals 表结构")
    print("=" * 60)
    
    with engine.connect() as conn:
        # 检查当前表结构
        inspector = inspect(engine)
        columns = {col['name']: col for col in inspector.get_columns('goals')}
        
        print(f"\n当前 goals 表有 {len(columns)} 列")
        
        # 需要添加的列
        missing_columns = []
        
        # 检查 goal_period
        if 'goal_period' not in columns:
            missing_columns.append({
                'name': 'goal_period',
                'sql': "ALTER TABLE goals ADD COLUMN goal_period VARCHAR(20) DEFAULT 'daily'"
            })
        
        # 检查 title
        if 'title' not in columns:
            missing_columns.append({
                'name': 'title',
                'sql': "ALTER TABLE goals ADD COLUMN title VARCHAR(200)"
            })
        
        # 检查 end_date
        if 'end_date' not in columns:
            missing_columns.append({
                'name': 'end_date',
                'sql': "ALTER TABLE goals ADD COLUMN end_date DATE"
            })
        
        # 检查 implementation_steps
        if 'implementation_steps' not in columns:
            missing_columns.append({
                'name': 'implementation_steps',
                'sql': "ALTER TABLE goals ADD COLUMN implementation_steps TEXT"
            })
        
        # 检查 target_unit
        if 'target_unit' not in columns:
            missing_columns.append({
                'name': 'target_unit',
                'sql': "ALTER TABLE goals ADD COLUMN target_unit VARCHAR(20)"
            })
        
        # 检查 notes
        if 'notes' not in columns:
            missing_columns.append({
                'name': 'notes',
                'sql': "ALTER TABLE goals ADD COLUMN notes TEXT"
            })
        
        if not missing_columns:
            print("\n✅ goals 表结构完整，无需修复")
            return
        
        print(f"\n发现 {len(missing_columns)} 个缺失的列:")
        for col in missing_columns:
            print(f"  - {col['name']}")
        
        # 添加缺失的列
        print("\n开始添加缺失的列...")
        for col in missing_columns:
            try:
                print(f"  添加 {col['name']}...", end=' ')
                conn.execute(text(col['sql']))
                conn.commit()
                print("✅")
            except Exception as e:
                print(f"❌ 失败: {e}")
                conn.rollback()
        
        # 更新现有记录的 goal_period
        if 'goal_period' in [col['name'] for col in missing_columns]:
            print("\n更新现有记录的 goal_period...")
            try:
                # 将现有记录设置为 'daily'
                result = conn.execute(text("UPDATE goals SET goal_period = 'daily' WHERE goal_period IS NULL"))
                conn.commit()
                print(f"  ✅ 更新了 {result.rowcount} 条记录")
            except Exception as e:
                print(f"  ❌ 更新失败: {e}")
                conn.rollback()
        
        # 更新现有记录的 title（从 name 复制）
        if 'title' in [col['name'] for col in missing_columns]:
            print("\n更新现有记录的 title...")
            try:
                result = conn.execute(text("UPDATE goals SET title = name WHERE title IS NULL"))
                conn.commit()
                print(f"  ✅ 更新了 {result.rowcount} 条记录")
            except Exception as e:
                print(f"  ❌ 更新失败: {e}")
                conn.rollback()
        
        # 更新现有记录的 target_unit（从 unit 复制）
        if 'target_unit' in [col['name'] for col in missing_columns]:
            print("\n更新现有记录的 target_unit...")
            try:
                result = conn.execute(text("UPDATE goals SET target_unit = unit WHERE target_unit IS NULL"))
                conn.commit()
                print(f"  ✅ 更新了 {result.rowcount} 条记录")
            except Exception as e:
                print(f"  ❌ 更新失败: {e}")
                conn.rollback()
        
        # 验证修复结果
        print("\n验证修复结果...")
        inspector = inspect(engine)
        new_columns = {col['name']: col for col in inspector.get_columns('goals')}
        print(f"  修复后 goals 表有 {len(new_columns)} 列")
        
        # 检查所有必需的列
        required_columns = ['goal_period', 'title', 'end_date', 'implementation_steps', 'target_unit', 'notes']
        all_present = all(col in new_columns for col in required_columns)
        
        if all_present:
            print("\n✅ 所有必需的列都已添加")
        else:
            missing = [col for col in required_columns if col not in new_columns]
            print(f"\n⚠️  仍有缺失的列: {', '.join(missing)}")
        
        print("\n✅ 修复完成!")


if __name__ == '__main__':
    try:
        fix_goals_schema()
    except Exception as e:
        print(f"\n❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
