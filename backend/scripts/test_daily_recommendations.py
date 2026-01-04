#!/usr/bin/env python3
"""测试每日建议API"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.daily_recommendation import DailyRecommendationService
import traceback

def test_recommendations():
    """测试获取建议"""
    db = SessionLocal()
    try:
        user_id = 1
        service = DailyRecommendationService()
        
        print(f"测试用户 {user_id} 的建议生成...")
        result = service.get_or_generate_recommendations(db, user_id, use_llm=False)
        
        print(f"状态: {result.get('status')}")
        print(f"日期: {result.get('date')}")
        print(f"分析日期: {result.get('analysis_date')}")
        print(f"是否缓存: {result.get('cached')}")
        print(f"1天建议键: {list(result.get('one_day', {}).keys()) if result.get('one_day') else 'None'}")
        print(f"7天建议键: {list(result.get('seven_day', {}).keys()) if result.get('seven_day') else 'None'}")
        
        return True
    except Exception as e:
        print(f"错误: {e}")
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = test_recommendations()
    sys.exit(0 if success else 1)

