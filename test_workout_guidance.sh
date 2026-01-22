#!/bin/bash

# 测试运动指导 API

API_BASE="https://health.westwetlandtech.com/api"

# 测试用户登录（使用实际的测试账号）
echo "=== 测试登录 ==="
LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=test123")

echo "登录响应: $LOGIN_RESPONSE"

# 提取 token
TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "❌ 登录失败，无法获取 token"
  exit 1
fi

echo "✅ 登录成功，token: ${TOKEN:0:20}..."

# 测试获取目标列表
echo -e "\n=== 测试获取目标列表 ==="
GOALS_RESPONSE=$(curl -s "$API_BASE/goals/me?status=active" \
  -H "Authorization: Bearer $TOKEN")

echo "目标列表响应: $GOALS_RESPONSE"

# 测试生成运动指导
echo -e "\n=== 测试生成运动指导 ==="
GUIDANCE_RESPONSE=$(curl -s -X POST "$API_BASE/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "运动指导响应: $GUIDANCE_RESPONSE" | head -c 500
echo "..."

# 检查是否成功
if echo "$GUIDANCE_RESPONSE" | grep -q '"success":true'; then
  echo -e "\n✅ 运动指导生成成功"
else
  echo -e "\n❌ 运动指导生成失败"
  echo "完整响应: $GUIDANCE_RESPONSE"
fi
