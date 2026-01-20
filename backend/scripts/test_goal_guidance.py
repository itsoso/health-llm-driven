#!/usr/bin/env python3
"""
测试目标智能引导功能

验证张展晖课程知识库整合是否正常工作
"""

import sys
import os
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.goal import GoalType
from app.services.goal_guidance import goal_guidance_service


def test_goal_guidance(user_id: int = 1):
    """测试目标引导服务"""
    
    print("=" * 80)
    print("测试目标智能引导功能")
    print("=" * 80)
    
    db: Session = SessionLocal()
    
    try:
        # 测试不同类型的目标
        test_cases = [
            {
                "goal_type": GoalType.WEIGHT_LOSS,
                "goal_description": "希望在3个月内减重10公斤",
                "target_value": 10.0
            },
            {
                "goal_type": GoalType.RUNNING,
                "goal_description": "准备半程马拉松",
                "target_value": 21.0975
            },
            {
                "goal_type": GoalType.CARDIO,
                "goal_description": "提升心肺功能",
                "target_value": None
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'='*80}")
            print(f"测试案例 {i}: {test_case['goal_type'].value}")
            print(f"描述: {test_case['goal_description']}")
            print(f"{'='*80}\n")
            
            # 调用服务
            guidance = goal_guidance_service.generate_goal_guidance(
                db=db,
                user_id=user_id,
                goal_type=test_case['goal_type'],
                goal_description=test_case['goal_description'],
                target_value=test_case['target_value']
            )
            
            # 打印结果
            if guidance.get("success"):
                print("✅ 生成成功！\n")
                
                # 心率区间
                if guidance.get("heart_rate_zones"):
                    print("📊 心率区间:")
                    hr_zones = guidance["heart_rate_zones"]
                    print(f"  最大心率: {hr_zones['max_hr']} bpm")
                    for zone_name, zone_data in hr_zones.items():
                        if isinstance(zone_data, dict) and 'min' in zone_data:
                            print(f"  {zone_name}: {zone_data['min']}-{zone_data['max']} bpm ({zone_data['description']})")
                    print()
                
                # 训练计划
                if guidance.get("training_plan"):
                    print("📅 训练计划:")
                    plan = guidance["training_plan"]
                    print(f"  频率: {plan.get('frequency', 'N/A')}")
                    print(f"  时长: {plan.get('duration', 'N/A')}")
                    
                    if plan.get("intensity_distribution"):
                        print("  强度分配:")
                        for key, value in plan["intensity_distribution"].items():
                            print(f"    {key}: {value}")
                    
                    if plan.get("weekly_structure"):
                        print("  周训练结构:")
                        for day in plan["weekly_structure"][:3]:  # 只显示前3天
                            print(f"    {day}")
                        if len(plan["weekly_structure"]) > 3:
                            print(f"    ... (共 {len(plan['weekly_structure'])} 天)")
                    print()
                
                # 知识要点
                if guidance.get("knowledge_points"):
                    print("💡 课程知识要点:")
                    for point in guidance["knowledge_points"][:3]:  # 只显示前3个
                        print(f"  • {point}")
                    if len(guidance["knowledge_points"]) > 3:
                        print(f"  ... (共 {len(guidance['knowledge_points'])} 个要点)")
                    print()
                
                # 个性化建议
                if guidance.get("recommendations"):
                    print("🎯 个性化建议:")
                    for rec in guidance["recommendations"][:3]:  # 只显示前3个
                        print(f"  • {rec}")
                    if len(guidance["recommendations"]) > 3:
                        print(f"  ... (共 {len(guidance['recommendations'])} 条建议)")
                    print()
                
                # 课程引用
                if guidance.get("course_references"):
                    print("📚 课程引用:")
                    for ref in guidance["course_references"][:2]:  # 只显示前2个
                        print(f"  • {ref.get('title', 'N/A')} (相关度: {ref.get('relevance', 0):.2f})")
                    if len(guidance["course_references"]) > 2:
                        print(f"  ... (共 {len(guidance['course_references'])} 个引用)")
                    print()
                
            else:
                print(f"❌ 生成失败: {guidance.get('error', '未知错误')}")
                print(f"   消息: {guidance.get('message', 'N/A')}")
            
            print()
        
        print("=" * 80)
        print("✅ 测试完成！")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试目标智能引导功能")
    parser.add_argument("--user-id", type=int, default=1, help="用户ID (默认: 1)")
    
    args = parser.parse_args()
    
    test_goal_guidance(user_id=args.user_id)
