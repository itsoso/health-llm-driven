#!/usr/bin/env python3
"""测试健康分析缓存"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.services.health_analysis import HealthAnalysisService
import traceback

def test_health_analysis():
    """测试健康分析缓存"""
    db = SessionLocal()
    try:
        user_id = 1
        service = HealthAnalysisService()
        
        print("第一次调用（生成新分析）...")
        result1 = service.analyze_health_issues(db, user_id, force_refresh=False)
        print(f"状态: {'缓存' if result1.get('cached') else '新生成'}")
        print(f"分析日期: {result1.get('analysis_date')}")
        print(f"问题数量: {len(result1.get('issues', []))}")
        print(f"建议数量: {len(result1.get('recommendations', []))}")
        
        print("\n第二次调用（应使用缓存）...")
        result2 = service.analyze_health_issues(db, user_id, force_refresh=False)
        print(f"状态: {'缓存' if result2.get('cached') else '新生成'}")
        print(f"分析日期: {result2.get('analysis_date')}")
        
        print("\n强制刷新...")
        result3 = service.analyze_health_issues(db, user_id, force_refresh=True)
        print(f"状态: {'缓存' if result3.get('cached') else '新生成'}")
        
        return True
    except Exception as e:
        print(f"错误: {e}")
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = test_health_analysis()
    sys.exit(0 if success else 1)

