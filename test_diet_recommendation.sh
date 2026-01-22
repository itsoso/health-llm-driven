#!/bin/bash

# 智能饮食推荐功能测试脚本

echo "========================================="
echo "智能饮食推荐功能测试"
echo "========================================="
echo ""

# API 基础地址
BASE_URL="https://health.westwetlandtech.com/api/v1"

# 测试用户 token（需要替换为实际的 token）
# 可以通过登录接口获取，或使用现有的 token
echo "请先登录获取 token..."
echo ""

# 提示用户输入 token
read -p "请输入您的 access_token: " TOKEN

if [ -z "$TOKEN" ]; then
    echo "错误: Token 不能为空"
    exit 1
fi

echo ""
echo "========================================="
echo "测试 1: 获取我的饮食推荐"
echo "========================================="
echo ""

curl -X GET "${BASE_URL}/diet-recommendation/me" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool

echo ""
echo ""
echo "========================================="
echo "测试 2: 获取详细调试信息"
echo "========================================="
echo ""

curl -X GET "${BASE_URL}/diet-recommendation/me?debug=true" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool

echo ""
echo ""
echo "========================================="
echo "测试完成！"
echo "========================================="
