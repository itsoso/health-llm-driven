#!/usr/bin/env python3
"""
修复运动记录的类型分类

根据活动名称重新分类被错误归为 "other" 的运动记录
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord

# 活动名称关键字映射
ACTIVITY_NAME_KEYWORDS = {
    "跑步": "running",
    "跑": "running",
    "run": "running",
    "慢跑": "running",
    "健跑": "running",
    "马拉松": "running",
    
    "骑行": "cycling",
    "骑车": "cycling",
    "单车": "cycling",
    "自行车": "cycling",
    "bike": "cycling",
    
    "游泳": "swimming",
    "swim": "swimming",
    
    "走路": "walking",
    "步行": "walking",
    "散步": "walking",
    "walk": "walking",
    
    "登山": "hiking",
    "徒步": "hiking",
    "爬山": "hiking",
    "hike": "hiking",
    "追踪": "hiking",
    
    "有氧": "cardio",
    "椭圆机": "cardio",
    "跳绳": "cardio",
    "跳操": "cardio",
    "舞蹈": "cardio",
    "滑雪": "cardio",
    "乒乓": "cardio",
    "羽毛球": "cardio",
    "网球": "cardio",
    "篮球": "cardio",
    "足球": "cardio",
    
    "力量": "strength",
    "举重": "strength",
    "健身房": "strength",
    "gym": "strength",
    "weight": "strength",
    
    "瑜伽": "yoga",
    "yoga": "yoga",
    "冥想": "yoga",
    "meditation": "yoga",
    "拉伸": "yoga",
    "放松": "yoga",
    "专注": "yoga",
    
    "hiit": "hiit",
    "间歇": "hiit",
    "高强度": "hiit",
}


def fix_workout_types():
    """修复运动记录类型"""
    db = SessionLocal()
    
    try:
        # 获取所有 "other" 类型的记录
        others = db.query(WorkoutRecord).filter(WorkoutRecord.workout_type == "other").all()
        
        print(f"找到 {len(others)} 条 'other' 类型的运动记录")
        
        fixed_count = 0
        for record in others:
            if not record.workout_name:
                continue
            
            name_lower = record.workout_name.lower()
            new_type = None
            
            for keyword, workout_type in ACTIVITY_NAME_KEYWORDS.items():
                if keyword in name_lower:
                    new_type = workout_type
                    break
            
            if new_type and new_type != "other":
                print(f"  修复: '{record.workout_name}' ({record.workout_date}) -> {new_type}")
                record.workout_type = new_type
                fixed_count += 1
        
        if fixed_count > 0:
            db.commit()
            print(f"\n✅ 成功修复 {fixed_count} 条记录")
        else:
            print("\n没有需要修复的记录")
        
        # 显示当前类型分布
        print("\n当前运动类型分布:")
        from sqlalchemy import func
        stats = db.query(
            WorkoutRecord.workout_type,
            func.count(WorkoutRecord.id).label('count'),
            func.sum(WorkoutRecord.duration_seconds).label('total_seconds')
        ).group_by(WorkoutRecord.workout_type).all()
        
        for wtype, count, total_seconds in stats:
            total_minutes = (total_seconds or 0) // 60
            print(f"  {wtype}: {count}次, 总时长 {total_minutes} 分钟")
            
    finally:
        db.close()


if __name__ == "__main__":
    fix_workout_types()
