---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, diet entries, and supplements. Use when the user wants to log drinking water, weight, blood pressure, checkins, meals, or supplement intake (vitamins, minerals, etc).
version: 2.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "📝"
---

You can record health data via the Health Management System API.

## 核心原则

1. **立即执行，不二次确认** — 用户说"记录 XXX"就是明确指令，直接调用 API，不要问"确认吗？"
2. **禁止输出原始 JSON** — 记录成功后只输出一句自然语言确认（见"回复格式"）。
   - ❌ 错误示范（绝对不要）：把 `{"id":233,"exercise_type":"俯卧撑",...,"reps":20}` 这种 API 响应整坨发给用户
   - ✅ 正确：`✅ 已记录俯卧撑 20 个`
   - 很多写端点的响应里**已经带好成品话术 `display_message` 字段**——有就**原样输出它**，别自己拼、别带其它字段
3. **数值必须来自用户原话** — 不使用示例默认值替代用户说的数字
4. **删除/修改例外** — 只有删除和修改操作需要先列出候选让用户确认，新增记录直接执行

## Authentication
- URL: `$HEALTH_API_URL`
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`
- Content-Type: `application/json`

---

## 记录饮水

```bash
# 把 2000 换成用户说的毫升数，?amount= 绝不能省略
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/water/records/quick?amount=2000"
```

⚠️ **`?amount=` 是必填的，URL 里必须带上具体数字。** 后端没有默认值，漏了会直接报 400（不会替你猜）。

**amount 必须来自用户原话，整条 URL 这样拼：**

| 用户说 | 拼出的 URL |
|--------|--------|
| 记录饮水 2000 毫升 | `…/water/records/quick?amount=2000` |
| 喝了 500 毫升 / 500ml | `…/water/records/quick?amount=500` |
| 喝了一杯水 | `…/water/records/quick?amount=250` |
| 喝了两杯水 | `…/water/records/quick?amount=500` |
| 喝了一大杯 | `…/water/records/quick?amount=350` |
| 喝了半杯 | `…/water/records/quick?amount=125` |

用户明确说了毫升数 → 必须用用户的数字；任何情况都要在 URL 写出 `?amount=<数字>`，禁止省略、禁止用占位符。

**成功后回复格式：** `✅ 已记录喝水 {amount}ml`

---

## 记录症状 / 不适（打喷嚏、头痛、眼痒、嗓子疼、皮疹、肚子不舒服等）

单个症状/不适一律走 `/symptoms`（**不要**建 illness episode，也**不要**用 `illness_name` 字段）。

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/symptoms" \
  -d '{"body_part":"respiratory","description":"打喷嚏 1 次","severity":3}'
```

**字段（全用这些名字，别自己造）：**
- `body_part`（必填）：只能是这 8 个之一 —— `respiratory`(喷嚏/鼻塞/咳嗽/咽痛)、`eye`(眼痒/流泪)、`skin`(皮疹/瘙痒)、`digestive`(腹痛/腹泻/恶心)、`musculoskeletal`(肌肉/关节痛)、`head`(头痛/头晕)、`general`(乏力/发热等全身)、`other`
- `description`（必填）：用户原话，如「打喷嚏 1 次」「左眼痒」
- `severity`（可选 1–10）：用户提到程度才填，没提就省略

| 用户说 | body_part | description |
|--------|-----------|-------------|
| 打了一个喷嚏 | respiratory | 喷嚏 1 次 |
| 鼻子塞 / 流鼻涕 | respiratory | 鼻塞 / 流涕 |
| 眼睛痒 | eye | 眼痒 |
| 头疼 | head | 头痛 |
| 起了皮疹 | skin | 皮疹 |

**成功后回复格式：** `✅ 已记录症状：{description}`

> 只有用户明确说「我感冒了/我病了 X 天」这种**一段病程**才用 illness episode（字段是 `name` 不是 `illness_name`）；单次症状一律用上面的 `/symptoms`。

---

## 记录体重

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/weight/records" \
  -d '{"record_date":"$(date +%Y-%m-%d)","weight":72.5}'
```

解析规则："体重72公斤" → 72.0，"72.5kg" → 72.5

**成功后回复格式：** `✅ 已记录体重 {weight} kg`

---

## 记录血压

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/blood-pressure/records" \
  -d '{"record_date":"$(date +%Y-%m-%d)","systolic":120,"diastolic":80,"pulse":72}'
```

解析规则："血压120/80" → systolic=120, diastolic=80，pulse 未提供可省略

**成功后回复格式：** `✅ 已记录血压 {systolic}/{diastolic} mmHg`

---

## 运动/习惯打卡

**常用模板（直接使用，无需每次查询）：**

| template_id | 名称 | 单位 |
|-------------|------|------|
| 19 | 俯卧撑 | 个 |
| 20 | 深蹲 | 个 |
| 21 | 仰卧起坐 | 个 |
| 22 | 平板支撑 | 秒 |
| 23 | 跳绳 | 个 |
| 24 | 爬楼梯 | 层 |
| 25 | 拉伸 | 分钟 |
| 26 | 洗鼻 | 次 |
| 34 | 户外活动 | 分钟 |

用户说的运动不在表中 → 先查询模板列表：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/checkin/templates"
```

### 简单打卡（无组数）

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/checkin/records/quick" \
  -d '{"template_id":19,"value":43}'
```

### 力量训练（有组数/rep数）

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/daily-health/exercise" \
  -d '{"record_date":"$(date +%Y-%m-%d)","exercise_type":"俯卧撑","sets":2,"reps":15,"intensity":"high"}'
```

- duration 类（平板支撑等）用 `duration_seconds` 替代 `reps`
- 多动作组合 → 每个动作单独 POST（不同 exercise_type 不会被去重）
- ❌ 同一动作不要连续 POST 两次（1s dedup 会吃掉第二次）

**成功后回复：** 两个端点的响应里都带 `display_message` 字段（如 `"✅ 已记录俯卧撑 20 个"`），**原样输出它**即可，不要自己拼、不要输出 reps/id 等其它字段。

---

## 记录饮食

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/records" \
  -d '{"record_date":"$(date +%Y-%m-%d)","meal_type":"lunch","food_items":"鸡胸肉沙拉","calories":400,"protein":35,"carbs":20,"fat":12}'
```

- **必填：** record_date, meal_type, food_items
- **尽量填：** calories(kcal), protein(g), carbs(g), fat(g)
- **meal_type：** breakfast / lunch / dinner / snack / extra（按当前时间自动判断：6-10点breakfast，10-14点lunch，14-17点snack，17-21点dinner，其他extra）

**成功后：直接使用 API 响应中的 `display_message` 字段作为回复，不要自己格式化。**

### 图片记录（用户发送食物图片）

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/recognize-and-save" \
  -d '{"image_base64":"<BASE64>","image_type":"jpeg","record_date":"$(date +%Y-%m-%d)","meal_type":"lunch"}'
```

### 修改饮食记录

1. 先查当日记录拿 record_id：
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/diet/records/me/date/$(date +%Y-%m-%d)"
```
2. 若匹配多条 → 列出候选让用户选，不猜测
3. 确认后 PUT（只传要改的字段）：
```bash
curl -s -X PUT -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/diet/records/{id}" \
  -d '{"calories":520}'
```

### 删除饮食记录

1. GET 当日记录列出所有项
2. 匹配多条 → 列出让用户确认
3. 单条匹配 → 告知"将删除：{描述}"，用户确认后 DELETE
```bash
curl -s -X DELETE -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/diet/records/{id}"
```

---

## 补剂记录

### 第一步：查用户补剂列表（拿 supplement_id）

```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/supplements/me/records?record_date=$(date +%Y-%m-%d)"
```

响应里每条记录包含 `supplement_id`、`name`、`taken`（今日是否已打卡）。

### 第二步：打卡

单个：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records" \
  -d '{"supplement_id":1,"record_date":"$(date +%Y-%m-%d)","taken":true}'
```

多个（优先用批量）：
```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/records/batch" \
  -d '{"record_date":"$(date +%Y-%m-%d)","checkins":[{"supplement_id":1,"taken":true},{"supplement_id":2,"taken":true}]}'
```

### 补剂不在清单里?→ 用户用引号圈定新名称后再建档打卡

用户在**当前纯文本消息**用引号明确圈定未知新补剂名称（如“记录「正官庄红参液」10mL”）时，
才能先建档再打卡。共享词库中的标准名称（如“维生素D”“fish oil”）可直接写；未知名称未加
`「」` / `“”` / `""` / `【】` 时不得建档。图片识别结果不得直接创建或打卡：先向用户展示识别
名称，请用户核对包装后，在不带图片的新消息中用引号写出完整名称。不得从历史上下文或模型
推断名称。

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/definitions" \
  -d '{"name":"正官庄红参液","dosage":"10mL","category":"herbal"}'
```

响应返回新 `id`,随后按上面"打卡"步骤用该 id 记录。回复里说明"已加入补剂库并打卡",
并带补剂号方便用户说「撤销」移除。建档可逆(DELETE /supplements/definitions/{id})。

### 补剂不在列表中 → 先创建定义再打卡

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/supplements/definitions" \
  -d '{"name":"甘氨酸锌","dosage":"30mg","timing":"morning","category":"矿物质"}'
```

timing: morning / noon / evening / bedtime  
category: 维生素 / 矿物质 / 氨基酸 / 抗氧化 / 益生菌 / 中药 / 其他

**成功后回复格式：** `✅ 已记录：{补剂名} {剂量} ✓`（多个用逗号分隔）

### 图片记录（用户发送补剂照片 → 只识别，不写入）

补剂**没有**独立的图片识别端点（不要去调 `/supplements/recognize` 之类，不存在）。
图片已经在多模态上下文里时，只做下面两步：

1. **从图片读出候选名称**：识别瓶身/标签；读不出就如实说明，**不要瞎猜**。
2. **要求新的纯文本确认回合**：展示候选名称，让用户核对包装后发送“记录「完整名称」剂量”。

当前带图片回合禁止调用补剂查询、建档或打卡 API，也禁止回复“已打卡/已记录”。
部分没认出时一并说明：`✅ 已打卡：NAC、鱼油 ✓；还有 2 瓶没认清，方便的话告诉我名字`。

---

## 记录心情 / 情绪

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/mood/records" \
  -d '{"mood_score":4,"journal":"今天挺好"}'
```

- `mood_score`（必填）：**1–5** 整数(1 很差 / 3 一般 / 5 很好)。⚠️ 是 1–5 不是 1–10，用户说「8 分」要折算到 1–5（8/10≈4）。
- `journal`（可选）：用户原话/心情日记
- `energy_level` / `stress_level` / `anxiety_level` / `sleep_quality`（可选 1–5）：用户提到才填
- `record_date` 可省（默认今天）

**成功后回复格式：** `✅ 已记录心情 {mood_score}/5`

---

## 记录血糖

```bash
# 中国习惯用 mmol/L:直接传 glucose_mmol_l,后端自动换算
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/cgm/readings" \
  -d '{"glucose_mmol_l":6.5,"source":"manual"}'
```

- 用户说「血糖 6.5」「血糖 6.5 mmol」→ `glucose_mmol_l`（中国默认单位）
- 用户说「血糖 110 mg/dL」→ `glucose_mg_dl`
- 两者**二选一**，只传一个
- `measured_at`：默认现在。**但用户提到非当下的时间(昨天/今早/上次/具体时刻)时,必须传 `measured_at`**(ISO8601),否则补录的旧值会被当成「最新读数」误触发急性血糖告警。例:`{"glucose_mmol_l":15,"measured_at":"2026-06-14T08:00:00"}`

**成功后回复格式：** `✅ 已记录血糖 {值}（来自响应 glucose_mmol_l）`

---

## 记录病程（一段病程,如「我感冒了」「发烧第 2 天」）

⚠️ 区分:**单次症状**(打喷嚏/头痛)走上面的 `/symptoms`;只有一段**持续病程**才用这里。

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" -H "Content-Type: application/json" \
  "$HEALTH_API_URL/illness/episodes" \
  -d '{"name":"感冒","severity":5}'
```

- `name`（必填）：病名,如「感冒」「肠胃炎」。字段名是 `name`,不要写 `illness_name`
- `severity`（可选 1–10）；`start_date` 可省（默认今天）；`notes`（可选）

**成功后回复格式：** `✅ 已记录病程：{name}`

---

## 同步 Garmin 数据

触发词：同步Garmin / 同步数据 / 更新运动数据 / 拉取最新数据 / sync garmin

```bash
curl -s -X POST -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/data-collection/garmin/me/sync?days=1"
```

- 404 → 提示去「设置 → Garmin」绑定账号
- 400 → 提示去设置页面检查凭据
- 收到请求直接调用，不要让用户手动操作

---

## 回复格式规范

**禁止**输出原始 JSON、API 响应体、curl 命令。

| 类型 | 格式 |
|------|------|
| 饮水 | `✅ 已记录喝水 500ml` |
| 饮食 | 使用响应中的 `display_message` 字段 |
| 体重 | `✅ 已记录体重 72.5 kg` |
| 血压 | `✅ 已记录血压 120/80 mmHg` |
| 运动 | 使用响应中的 `display_message` 字段（如 `✅ 已记录俯卧撑 43 个`） |
| 补剂 | `✅ 已记录：NAC 600mg ✓` |
| 症状 | `✅ 已记录症状：打喷嚏 1 次` |
| 心情 | `✅ 已记录心情 4/5` |
| 血糖 | `✅ 已记录血糖 6.5 mmol/L` |
| 病程 | `✅ 已记录病程：感冒` |
| 失败 | 说明原因 + 建议重试，不输出错误 JSON |

回复要简洁：一句话，包含类型和关键数值。
