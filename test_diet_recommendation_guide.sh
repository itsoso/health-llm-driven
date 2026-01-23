#!/bin/bash

# 饮食推荐 API 测试脚本

echo "=========================================="
echo "饮食智能推荐 API 测试"
echo "=========================================="
echo ""

# 配置
API_BASE="https://health.westwetlandtech.com/api/v1"
# 替换为你的实际 token
TOKEN="your_token_here"

echo "1. 测试获取饮食推荐（不指定餐次）"
echo "----------------------------------------"
curl -X GET "${API_BASE}/diet-recommendation/me" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | jq '.'

echo ""
echo ""

echo "2. 测试获取早餐推荐"
echo "----------------------------------------"
curl -X GET "${API_BASE}/diet-recommendation/me?meal_type=breakfast" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | jq '.'

echo ""
echo ""

echo "3. 测试获取午餐推荐"
echo "----------------------------------------"
curl -X GET "${API_BASE}/diet-recommendation/me?meal_type=lunch" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | jq '.'

echo ""
echo ""

echo "4. 测试获取晚餐推荐"
echo "----------------------------------------"
curl -X GET "${API_BASE}/diet-recommendation/me?meal_type=dinner" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | jq '.'

echo ""
echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
