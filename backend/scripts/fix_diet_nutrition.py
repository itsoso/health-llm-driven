#!/usr/bin/env python3
"""
修复饮食记录的营养成分数据
根据食物名称和热量估算蛋白质、碳水、脂肪含量
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.daily_health import DietRecord
from sqlalchemy import and_

# 常见食物的营养成分比例（基于热量）
FOOD_NUTRITION_RATIOS = {
    # 主食类 (高碳水)
    '米饭': {'protein_ratio': 0.08, 'carbs_ratio': 0.75, 'fat_ratio': 0.03},
    '面条': {'protein_ratio': 0.10, 'carbs_ratio': 0.70, 'fat_ratio': 0.05},
    '馒头': {'protein_ratio': 0.08, 'carbs_ratio': 0.72, 'fat_ratio': 0.02},
    '包子': {'protein_ratio': 0.12, 'carbs_ratio': 0.50, 'fat_ratio': 0.15},
    '饺子': {'protein_ratio': 0.15, 'carbs_ratio': 0.45, 'fat_ratio': 0.18},
    '水饺': {'protein_ratio': 0.15, 'carbs_ratio': 0.45, 'fat_ratio': 0.18},
    '面包': {'protein_ratio': 0.09, 'carbs_ratio': 0.65, 'fat_ratio': 0.08},
    
    # 肉类 (高蛋白)
    '鸡胸肉': {'protein_ratio': 0.75, 'carbs_ratio': 0.0, 'fat_ratio': 0.05},
    '牛肉': {'protein_ratio': 0.60, 'carbs_ratio': 0.0, 'fat_ratio': 0.20},
    '猪肉': {'protein_ratio': 0.45, 'carbs_ratio': 0.0, 'fat_ratio': 0.35},
    '鱼': {'protein_ratio': 0.65, 'carbs_ratio': 0.0, 'fat_ratio': 0.10},
    '虾': {'protein_ratio': 0.70, 'carbs_ratio': 0.0, 'fat_ratio': 0.05},
    '午餐肉': {'protein_ratio': 0.35, 'carbs_ratio': 0.10, 'fat_ratio': 0.40},
    
    # 蔬菜类 (低热量，高纤维)
    '黄瓜': {'protein_ratio': 0.15, 'carbs_ratio': 0.60, 'fat_ratio': 0.05},
    '西红柿': {'protein_ratio': 0.15, 'carbs_ratio': 0.65, 'fat_ratio': 0.05},
    '青菜': {'protein_ratio': 0.20, 'carbs_ratio': 0.50, 'fat_ratio': 0.05},
    '菠菜': {'protein_ratio': 0.25, 'carbs_ratio': 0.50, 'fat_ratio': 0.05},
    '木耳': {'protein_ratio': 0.30, 'carbs_ratio': 0.50, 'fat_ratio': 0.05},
    '胡萝卜': {'protein_ratio': 0.10, 'carbs_ratio': 0.70, 'fat_ratio': 0.03},
    
    # 水果类 (高碳水)
    '苹果': {'protein_ratio': 0.02, 'carbs_ratio': 0.90, 'fat_ratio': 0.02},
    '香蕉': {'protein_ratio': 0.05, 'carbs_ratio': 0.85, 'fat_ratio': 0.02},
    '蓝莓': {'protein_ratio': 0.05, 'carbs_ratio': 0.80, 'fat_ratio': 0.03},
    '黑莓': {'protein_ratio': 0.08, 'carbs_ratio': 0.75, 'fat_ratio': 0.03},
    
    # 饮品类
    '果汁': {'protein_ratio': 0.03, 'carbs_ratio': 0.90, 'fat_ratio': 0.01},
    '牛奶': {'protein_ratio': 0.25, 'carbs_ratio': 0.35, 'fat_ratio': 0.25},
    
    # 默认值（混合餐）
    'default': {'protein_ratio': 0.25, 'carbs_ratio': 0.50, 'fat_ratio': 0.20},
}


def estimate_nutrition(food_items: str, calories: float):
    """
    根据食物名称和热量估算营养成分
    
    Args:
        food_items: 食物名称
        calories: 热量（大卡）
    
    Returns:
        dict: {protein: float, carbs: float, fat: float}
    """
    if not food_items or not calories or calories <= 0:
        return None
    
    # 查找匹配的食物类型
    ratios = None
    for food_key, food_ratios in FOOD_NUTRITION_RATIOS.items():
        if food_key in food_items:
            ratios = food_ratios
            break
    
    # 如果没有匹配，使用默认值
    if not ratios:
        ratios = FOOD_NUTRITION_RATIOS['default']
    
    # 计算营养成分（克）
    # 1g 蛋白质 = 4 大卡
    # 1g 碳水化合物 = 4 大卡
    # 1g 脂肪 = 9 大卡
    
    protein_calories = calories * ratios['protein_ratio']
    carbs_calories = calories * ratios['carbs_ratio']
    fat_calories = calories * ratios['fat_ratio']
    
    protein = round(protein_calories / 4, 1)  # 蛋白质（克）
    carbs = round(carbs_calories / 4, 1)      # 碳水（克）
    fat = round(fat_calories / 9, 1)          # 脂肪（克）
    
    return {
        'protein': protein,
        'carbs': carbs,
        'fat': fat
    }


def fix_diet_nutrition():
    """修复饮食记录的营养成分"""
    db = SessionLocal()
    
    try:
        # 查询所有营养成分为空但有热量的记录
        records = db.query(DietRecord).filter(
            and_(
                DietRecord.calories.isnot(None),
                DietRecord.calories > 0,
                DietRecord.protein.is_(None)
            )
        ).all()
        
        print(f"找到 {len(records)} 条需要修复的记录")
        
        updated = 0
        skipped = 0
        
        for record in records:
            # 估算营养成分
            nutrition = estimate_nutrition(record.food_items or '', record.calories)
            
            if nutrition:
                record.protein = nutrition['protein']
                record.carbs = nutrition['carbs']
                record.fat = nutrition['fat']
                
                print(f"✅ ID={record.id}, 食物={record.food_items[:30]}, "
                      f"热量={record.calories}, "
                      f"蛋白质={nutrition['protein']}g, "
                      f"碳水={nutrition['carbs']}g, "
                      f"脂肪={nutrition['fat']}g")
                
                updated += 1
            else:
                skipped += 1
        
        # 提交更改
        db.commit()
        
        print(f"\n✅ 修复完成:")
        print(f"   - 更新: {updated} 条")
        print(f"   - 跳过: {skipped} 条")
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    print("=" * 60)
    print("修复饮食记录的营养成分数据")
    print("=" * 60)
    
    fix_diet_nutrition()
    
    print("\n✅ 全部完成!")
