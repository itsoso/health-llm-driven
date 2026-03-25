---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, diet entries, and supplements. Use when the user wants to log drinking water, weight, blood pressure, checkins, meals, or supplement intake (vitamins, minerals, etc).
version: 1.2.0
metadata:
  openclaw:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📝"
---

You can record health data via the Health Management System API.

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

## Available Actions

### 记录饮水（快速）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/quick?amount=250"
```
默认250ml，可修改 amount 参数。

### 记录体重
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/weight/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","weight":72.5}'
```

### 记录血压
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/blood-pressure/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","systolic":120,"diastolic":80,"pulse":72}'
```

### 快速打卡
先查询可用模板：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/templates"
```
然后打卡（用模板ID）：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/checkin/records/quick" \
  -d '{"template_id":1,"value":30}'
```

### 记录饮食（文字描述）
端点：`POST $HEALTH_API_URL/diet/records`
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/records" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","meal_type":"lunch","food_items":"鸡胸肉沙拉","calories":400,"protein":35,"carbs":20,"fat":12}'
```
**必填字段：** record_date, meal_type, food_items
**可选字段：** calories(kcal), protein(g), carbs(g), fat(g), fiber(g), notes, image_url
**meal_type 取值：** breakfast / lunch / dinner / snack / extra（必须小写）

### 记录饮食（图片识别 + 自动保存）
当用户发送食物图片时，使用此接口一键识别并保存：
端点：`POST $HEALTH_API_URL/diet/recognize-and-save`
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/recognize-and-save" \
  -d '{"image_base64":"<BASE64_IMAGE_DATA>","image_type":"jpeg","record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","meal_type":"lunch"}'
```
**必填字段：** image_base64, record_date, meal_type
**可选字段：** image_type(默认jpeg), notes
系统会自动 AI 识别食物并计算营养数据（热量、蛋白质、碳水、脂肪）后保存。

### 仅识别食物（不保存记录）
端点：`POST $HEALTH_API_URL/diet/recognize`
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/recognize" \
  -d '{"image_base64":"<BASE64_IMAGE_DATA>","image_type":"jpeg"}'
```
返回识别结果（食物列表、营养数据），但不写入数据库。

### 文字估算营养（不保存记录）
端点：`GET $HEALTH_API_URL/diet/estimate-nutrition?food_description=一碗米饭加红烧肉`
返回营养估算结果。

### 查询饮食记录
```bash
# 查询最近N天的记录
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/diet/records/me?days=7"
# 查询指定日期汇总
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/diet/records/me/date/2026-03-08"
# 查询饮食统计
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/diet/records/me/stats?days=30"
```

### 补剂记录

#### 1. 查询用户补剂列表（含今日打卡状态）
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/supplements/me/records?record_date=$(date +%Y-%m-%d)"
```

#### 2. 创建新补剂定义（如果用户要记录的补剂不在列表中）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/definitions" \
  -d '{"name":"甘氨酸锌","dosage":"30mg","timing":"morning","category":"矿物质"}'
```
- timing: morning / noon / evening / bedtime
- category: 维生素 / 矿物质 / 氨基酸 / 抗氧化 / 益生菌 / 中药 / 其他

#### 3. 补剂打卡（单个）
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records" \
  -d '{"supplement_id":1,"user_id":1,"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","taken":true,"notes":"早餐后服用"}'
```

#### 4. 补剂批量打卡
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records/batch" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","checkins":[{"supplement_id":1,"taken":true},{"supplement_id":2,"taken":true}]}'
```

#### 5. 查看补剂统计
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/supplements/me/stats?days=30"
```

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Parse natural language: "喝了一杯水" → 250ml, "喝了两杯" → 500ml
- Parse weight: "体重72公斤" → 72.0, "72.5kg" → 72.5
- Parse blood pressure: "血压120/80" → systolic=120, diastolic=80
- Always respond in Chinese
- **严格使用上面定义的 API 端点路径，不要自行猜测或构造其他路径**

### 饮食记录特殊规则
- 用户发送食物图片时，使用 `/diet/recognize-and-save` 一键识别并保存
- 用户用文字描述食物时，自行估算营养数据后使用 `/diet/records` 保存
- meal_type 根据当前时间自动判断：6-10点=breakfast，10-14点=lunch，14-17点=snack，17-21点=dinner，其他=extra
- 营养数据（calories, protein, carbs, fat）尽量填写，帮用户做好营养追踪

### 补剂特殊规则
- 记录补剂前，先查询用户补剂列表确认 supplement_id
- 如果用户提到的补剂不在列表中，先自动创建补剂定义，再打卡
- 多个补剂同时记录时，优先用批量打卡接口
- "吃了NAC两粒" → 找到NAC的supplement_id，记录taken=true
- "吃了甘氨酸锌" → 先查列表，不存在则创建定义，然后打卡

## 同步 Garmin 数据

当用户说"同步Garmin数据"、"更新运动数据"、"拉取最新数据"时，触发 Garmin 数据同步：

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/auth/garmin/sync" -d '{"days": 1}'
```
- `days`: 同步最近N天的数据（默认1天，最多730天）
- 返回同步成功的天数和运动记录数
- 如果返回404说明用户未配置 Garmin 凭证，提示去设置页面配置
- 同步完成后可以用 health-query 技能查询最新数据
