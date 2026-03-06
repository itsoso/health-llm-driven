---
name: multi-model-analyze
description: 多模型分析工具。当用户说"多模型分析"或"multi-model analyze"时触发。将用户的问题发送到多模型分析API，获取多个AI模型的综合分析结果。
version: 1.2.0
metadata:
  openclaw:
    requires:
      env: [MULTI_MODEL_API_URL, MULTI_MODEL_API_KEY]
      bins: [curl]
    primaryEnv: MULTI_MODEL_API_KEY
    emoji: "🤖"
---

# 多模型分析

调用多个大模型同时分析问题，汇总各模型观点得出综合结论。

## API 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | ✅ | - | 分析内容或问题 |
| sites | ❌ | 全部8个模型 | 模型列表 |
| aggregator_site | ❌ | lb-gpt-5.1 | 汇总模型 |
| aggregator_template_id | ❌ | best_results | 汇总模板 ID |
| callback_url | ❌ | - | 完成后回调 URL |
| kim_user_id | ❌ | - | Kim 推送用户 ID |

### 预设模型列表
- `lb-gpt-5.1`
- `lb-gemini-3.1-pro`
- `lb-deepseek-r1-250528`
- `lb-kimi-k2.5`
- `lb-claude-sonnet-4.6`
- `lb-claude-4-sonnet-think`
- `lb-glm-5`
- `lb-qwen3.5-397b-a17b`

## 步骤

### Step 1: 提交分析

```bash
curl -s -X POST "$MULTI_MODEL_API_URL/api/openclaw/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "<用户的完整消息>",
    "sites": ["lb-gpt-5.1","lb-gemini-3.1-pro","lb-deepseek-r1-250528","lb-kimi-k2.5","lb-claude-sonnet-4.6","lb-claude-4-sonnet-think","lb-glm-5","lb-qwen3.5-397b-a17b"],
    "aggregator_site": "lb-gpt-5.1",
    "aggregator_template_id": "best_results",
    "api_key": "$MULTI_MODEL_API_KEY"
  }'
```

将 `<用户的完整消息>` 替换为用户实际发送的内容（去掉触发词后的部分）。
返回 `{"ok": true, "batch_id": "prompt_xxx"}`，记住 batch_id。

可选：通过 `sites` 参数指定部分模型，不传则使用全部预设模型。

### Step 2: 轮询状态（每10秒一次）

```bash
curl -s -H "X-API-Key: $MULTI_MODEL_API_KEY" \
  "$MULTI_MODEL_API_URL/api/openclaw/status/<batch_id>"
```

- status = "pending" / "processing" → 继续等待，10秒后再查
- status = "completed" / "partial" → 读取结果

### Step 3: 展示结果

从响应中读取：
- `model_results`: 各模型的独立分析（数组，每项有 site 和 content）
- `aggregation`: 综合汇总结果
- `status_url`: 状态页链接

格式化展示给用户：
1. 如果 `aggregation` 非空，直接展示综合分析结果
2. 如果有 `model_results`，按模型分别展示各自的分析
3. **必须附上状态页原始链接**供用户查看各模型原始回复

## 输出规则

- 结果中必须保留原始链接地址，方便用户点击查看各模型的原始回复
- 将结果直接在对话中格式化呈现给用户
- 如果请求失败，告知用户并显示错误信息
