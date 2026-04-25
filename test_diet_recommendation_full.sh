#!/bin/bash

# 智能饮食推荐系统完整测试脚本

API_BASE="https://health.westwetlandtech.com/api"

echo "========================================="
echo "智能饮食推荐系统测试"
echo "========================================="
echo ""

# 1. 登录获取 token
echo "1. 登录获取 token..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=liqiuhua&password=Lqh19850604")

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ 登录失败，请检查用户名和密码"
  echo "响应: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ 登录成功"
echo ""

# 2. 测试饮食推荐 API
echo "2. 测试饮食推荐 API..."
echo "========================================="

RECOMMENDATION=$(curl -s -X GET "$API_BASE/diet-recommendation/me" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$RECOMMENDATION" | python3 -m json.tool 2>/dev/null

if echo "$RECOMMENDATION" | grep -q "success"; then
  echo ""
  echo "✅ API 测试成功"
  echo ""

  # 3. 提取关键信息
  echo "3. 关键信息摘要"
  echo "========================================="

  echo "$RECOMMENDATION" | python3 << 'EOF'
import json
import sys

try:
    data = json.load(sys.stdin)

    if data.get('success'):
        print(f"✅ 推荐生成成功\n")

        # 用户信息
        user_info = data.get('user_info', {})
        print(f"👤 用户信息:")
        print(f"   年龄: {user_info.get('age')}岁")
        print(f"   性别: {'男' if user_info.get('gender') == 'male' else '女'}")
        print(f"   身高: {user_info.get('height_cm')}cm")
        print(f"   体重: {user_info.get('current_weight_kg')}kg")
        print(f"   目标: {user_info.get('weight_goal')}")
        print()

        # 代谢信息
        metabolism = data.get('metabolism', {})
        print(f"🔥 代谢信息:")
        print(f"   BMR: {metabolism.get('bmr')} kcal/天")
        print(f"   TDEE: {metabolism.get('tdee')} kcal/天")
        print()

        # 营养目标
        daily_target = data.get('daily_target', {})
        print(f"📊 每日营养目标:")
        print(f"   热量: {daily_target.get('calories')} kcal")
        print(f"   蛋白质: {daily_target.get('protein_g')} g")
        print(f"   碳水: {daily_target.get('carbs_g')} g")
        print(f"   脂肪: {daily_target.get('fat_g')} g")
        print()

        # 今日摄入
        today_intake = data.get('today_intake', {})
        print(f"🍽️ 今日摄入 ({today_intake.get('meals_count')}餐):")
        print(f"   热量: {today_intake.get('calories')} kcal")
        print(f"   蛋白质: {today_intake.get('protein_g')} g")
        print(f"   碳水: {today_intake.get('carbs_g')} g")
        print(f"   脂肪: {today_intake.get('fat_g')} g")
        print()

        # 进度
        progress = data.get('progress', {})
        print(f"📈 完成进度:")
        print(f"   热量: {progress.get('calories_percent')}%")
        print(f"   蛋白质: {progress.get('protein_percent')}%")
        print(f"   碳水: {progress.get('carbs_percent')}%")
        print(f"   脂肪: {progress.get('fat_percent')}%")
        print()

        # 健康状态
        health_status = data.get('health_status', {})
        if health_status:
            print(f"💪 健康状态:")
            if 'sleep_score' in health_status:
                print(f"   睡眠评分: {health_status.get('sleep_score')}/100")
            if 'body_battery' in health_status:
                print(f"   身体电量: {health_status.get('body_battery')}/100")
            if 'stress_level' in health_status:
                print(f"   压力水平: {health_status.get('stress_level')}/100")
            print()

        # 警告
        warnings = data.get('warnings', [])
        if warnings:
            print(f"⚠️ 重要提醒 ({len(warnings)}条):")
            for warning in warnings:
                print(f"   {warning}")
            print()

        # 提示
        tips = data.get('tips', [])
        if tips:
            print(f"💡 健康提示 ({len(tips)}条):")
            for tip in tips:
                print(f"   {tip}")
            print()

        # 食物推荐
        food_recommendations = data.get('food_recommendations', [])
        if food_recommendations:
            print(f"🍽️ 食物推荐 ({len(food_recommendations)}类):")
            for rec in food_recommendations:
                print(f"   [{rec.get('priority')}] {rec.get('category')}")
                print(f"      理由: {rec.get('reason')}")
                print(f"      推荐: {', '.join(rec.get('foods', [])[:3])}...")
            print()

        # 科学依据
        scientific_insights = data.get('scientific_insights', {})
        if scientific_insights.get('available'):
            print(f"🔬 科学依据: 可用")
        else:
            print(f"🔬 科学依据: {scientific_insights.get('reason', '不可用')}")
        print()

    else:
        print(f"❌ 推荐生成失败: {data.get('error')}")

except Exception as e:
    print(f"❌ 解析失败: {e}")
    sys.exit(1)
EOF

else
  echo "❌ API 测试失败"
  echo "响应: $RECOMMENDATION"
  exit 1
fi

echo ""
echo "========================================="
echo "测试完成"
echo "========================================="
