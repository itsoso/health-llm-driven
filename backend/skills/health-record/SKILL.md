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

### 运动/习惯打卡
先查询可用模板获取 template_id：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/templates"
```

常用模板（直接用 template_id 打卡，无需每次查询）：
| template_id | 名称 | 单位 | 默认目标 |
|-------------|------|------|---------|
| 19 | 俯卧撑 | 个 | 20 |
| 20 | 深蹲 | 个 | 30 |
| 21 | 仰卧起坐 | 个 | 20 |
| 22 | 平板支撑 | 秒 | 60 |
| 23 | 跳绳 | 个 | 100 |
| 24 | 爬楼梯 | 层 | 10 |
| 25 | 拉伸 | 分钟 | 10 |
| 26 | 洗鼻 | 次 | 1 |
| 34 | 户外活动 | 分钟 | 30 |

打卡（用模板ID + 实际完成值）：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/checkin/records/quick" \
  -d '{"template_id":19,"value":43}'
```
**必须参数：** template_id（整数）, value（数字，实际完成量）
**示例：** 用户说"俯卧撑43个" → template_id=19, value=43
**示例：** 用户说"深蹲50个" → template_id=20, value=50

**重要：当用户说"记录运动"时，必须调用此打卡接口，不要只是口头确认。**

### 力量训练详细记录（带 sets/reps）
当用户描述带"组数"的力量训练（例：俯卧撑两组每组 15 个 / 深蹲三组每组 10 个）时，
**必须**用此端点而非上面的 quick 打卡，因为它能保留 sets/reps 结构：

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/daily-health/exercise" \
  -d '{"record_date":"'"'"'$(date +%Y-%m-%d)'"'"'","exercise_type":"俯卧撑","sets":2,"reps":15,"intensity":"high"}'
```

**关键：sets 字段一次表达多组**
- 用户说"两组俯卧撑 一组15个" → 一次 POST `{exercise_type:"俯卧撑", sets:2, reps:15}`
- 用户说"做了 3 组深蹲" → 一次 POST `{exercise_type:"深蹲", sets:3, reps:10}` (问用户每组多少, 不知则估10)
- ❌ **不要** 同一动作连续 POST 两次 (会被 1s dedup 视为双击吃掉)

**duration 类训练 (倒立/平板支撑等)** 用 duration_seconds 字段:
```bash
-d '{"record_date":"...","exercise_type":"平板支撑","sets":1,"duration_seconds":60,"intensity":"high"}'
```

**多动作组合** (例: "俯卧撑两组 + 深蹲两组") → **多次 POST**, 每个 exercise_type 一次:
```bash
# 第 1 次: 俯卧撑
curl ... -d '{"exercise_type":"俯卧撑","sets":2,"reps":15,...}'
# 第 2 次: 深蹲 (不同 exercise_type, 不会被 dedup)
curl ... -d '{"exercise_type":"深蹲","sets":2,"reps":10,...}'
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
- **执行后验证**: 每次记录操作后，调用对应的查询接口验证数据已保存。如果验证失败，告知用户并建议重试。不要假设操作成功。

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

## 执行验证

记录完成后，必须调用查询接口确认数据已保存：

### 验证饮水记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/water/records/me/daily-summary?date=$(date +%Y-%m-%d)"
```
检查 total_amount 是否增加了。

### 验证饮食记录
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/diet/records/me/date/$(date +%Y-%m-%d)"
```
检查是否有新增的记录。

### 验证规则
- 如果验证失败（数据未增加），告知用户记录可能未成功，建议重试
- 不要假装记录成功 — 必须通过验证确认

## 同步 Garmin 数据

当用户说"同步Garmin"、"同步Garmin数据"、"同步数据"、"更新运动数据"、"拉取最新数据"、"sync garmin"时，**必须立即调用此 API**，不要让用户手动操作：

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/data-collection/garmin/me/sync?days=1"
```

参数说明：
- `days`: 同步最近N天的数据（默认1天），通过 URL query 参数传递
- 返回同步结果，包含同步的天数和记录数

错误处理：
- 404: 用户未绑定 Garmin 账号，提示去「设置 → Garmin」页面绑定
- 400: Garmin 同步已禁用或凭据无效，提示去设置页面检查
- 成功后告知用户数据已同步，并简要说明同步了哪些数据

**重要**：收到同步请求后必须直接调用 API 执行同步，不要回复"请手动操作"。
