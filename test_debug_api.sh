#!/bin/bash

# 测试 Debug API 功能

echo "🔍 测试运动前指导 Debug 模式"
echo "================================"
echo ""

# 注意：需要替换为有效的 token
TOKEN="YOUR_TOKEN_HERE"

echo "1. 测试不带 debug 参数（应该没有 debug 字段）"
echo "-------------------------------------------"
curl -s -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq 'has("debug")'

echo ""
echo ""

echo "2. 测试带 debug=true 参数（应该有 debug 字段）"
echo "-------------------------------------------"
curl -s -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq 'has("debug")'

echo ""
echo ""

echo "3. 查看 debug 信息结构"
echo "-------------------------------------------"
curl -s -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq '.debug | keys'

echo ""
echo ""

echo "4. 查看决策步骤"
echo "-------------------------------------------"
curl -s -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq '.debug.steps'

echo ""
echo ""

echo "✅ 测试完成"
