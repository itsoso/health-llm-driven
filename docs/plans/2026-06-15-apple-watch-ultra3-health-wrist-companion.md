# Apple Watch Ultra 3 Health Wrist Companion 规划

> 日期: 2026-06-15
> 目标: 把 Apple Watch Ultra 3 从“可穿戴数据源”升级为 Health OS 的腕上执行器, 用低摩擦输入、智能提醒、恢复判断和饮食记录, 持续推动用户变健康。
> 结论: 应做 Watch 版本, 但不是完整聊天型 App。第一阶段做轻量 companion Watch App + Smart Stack + App Intents, 重点是语音食物记录、行动确认和状态提醒。
> 边界: Watch 不做主大脑、不做诊断、不做处方、不做长对话。Backend/iPhone/Mac 仍是推理、记录、复盘和证据系统的主路径。

---

## 0. Executive Summary

Apple Watch Ultra 3 对当前 Health OS 的最大价值不是“多一个屏幕”, 而是把健康系统放到用户最容易执行和反馈的位置:

```text
刚吃完 -> 抬腕说一句 -> 自动结构化饮食 -> 饭后提醒走路
准备运动 -> 看恢复状态 -> 自动降级或推进训练
收到提醒 -> 双指/按钮确认 -> 形成执行证据
睡前窗口 -> 轻触提醒 -> 减少夜宵和晚餐过晚
```

当前项目已经具备基础:

- Mobile 已有 HealthKit 原生同步, 可以把 Apple Watch / RingConn / Oura / Withings 等写入 HealthKit 的数据按来源导入后端。
- Backend 已有多源合并和设备优先级, Apple Watch 适合作为活动量、步数、心率、运动记录的高优先级来源。
- 已有 `DietRecord`、`/diet/records`、饮食统计、食物图片/文本估算、Mac 结构化记录。
- Mobile 插件里已有 App Intent 能力雏形: `HealthCommandIntent` 支持“语音快速记录饮食、饮水、运动等健康数据”。
- Daily Operating Plan、Outcome Proof、Health Guardrail、Operating Review 已经开始形成闭环。

因此下一阶段不应从零做“Watch 聊天机器人”, 而应做一个 **Health Wrist Companion**:

1. 用 Watch 做即时输入: 饮食、症状、饮水、补剂、情绪、疲劳、运动 RPE。
2. 用 Watch 做即时确认: 今日行动完成、跳过、调整、稍后提醒。
3. 用 Watch 做即时保护: 恢复差时阻止高强度, 异常风险时提示复查或观察。
4. 用 Watch 做即时提醒: 饭后步行、晚餐截止、药物/补剂、睡前窗口。
5. 用后端做长期复盘: 哪些行为真的改善体重、腰围、HRV、RHR、睡眠、血压、血脂、血糖。

---

## 1. 产品定位

### 1.1 Watch 的角色

| Surface | 角色 | 不做什么 |
|---|---|---|
| Backend | 大脑和事实源: Twin、Agent、计划、证据、审计、长期复盘 | 不依赖 Watch 在线才能工作 |
| iPhone App | HealthKit 桥、主要录入/编辑、照片、推送、复杂确认 | 不把所有即时输入都压到手机 |
| Mac App | 工作台: 深度分析、导入、长对话、文档、复盘 | 不承担外出执行 |
| Apple Watch | 腕上执行器: 低摩擦输入、确认、提醒、运动中反馈 | 不做完整 Agent、不做长病历浏览 |

### 1.2 应做 Watch App 吗?

结论: **做, 但做轻量 companion, 不做完整 Health OS。**

推荐的第一阶段 Watch App 只有 3 个主屏:

1. **今日状态**
   - 恢复颜色: green / yellow / red
   - 今日最重要行动: 只显示一件
   - 同步新鲜度: 最近 Watch 数据是否已进入后端

2. **一键记录**
   - 语音记录食物
   - 记录饮水 / 补剂 / 症状 / 疲劳 / 情绪
   - 快速选择常用食物或常用动作

3. **行动确认**
   - 做到了
   - 跳过
   - 调整
   - 稍后提醒

不建议第一阶段做:

- Watch 上的完整聊天。
- Watch 上的大仪表盘。
- Watch 上浏览体检/基因/文档。
- Watch 本地 LLM 推理。
- Watch 后台常驻监听。

---

## 2. 语音记录食物

### 2.1 这是 Watch 最值得做的输入场景

饮食记录的问题不是“有没有数据库”, 而是“用户能不能持续记录”。手表最适合解决刚吃完的低摩擦输入:

```text
用户: 午饭, 半碗米饭, 一份青椒牛肉, 两个鸡蛋, 一杯无糖拿铁

系统结构化:
餐次: lunch
食物: 米饭, 青椒牛肉, 鸡蛋, 无糖拿铁
份量: 半碗, 一份, 两个, 一杯
估算: 约 680 kcal, 蛋白 38g, 碳水 55g, 脂肪 28g
标签: 蛋白充足, 碳水中等, 无甜饮
置信度: medium

Watch 确认:
午餐约 680 kcal, 蛋白 38g。记录?
[确认] [改份量] [稍后]
```

### 2.2 第一版不追求营养师级精确

中餐、外卖和家庭餐很难精确到克。第一阶段目标是建立稳定行为数据:

- 今天是否记录饮食。
- 大概热量区间。
- 蛋白是否达标。
- 晚间碳水/油脂/酒精/甜饮是否偏高。
- 夜宵是否出现。
- 饭后是否运动。
- 饮食行为与体重、腰围、睡眠、HRV、RHR、尿酸、血脂、血糖的长期关系。

因此 v1 只要求:

- 餐次识别准确。
- 食物列表可读。
- 热量区间合理。
- 蛋白估算能用于“够/不够”的判断。
- 低置信度时最多追问 1 个问题。

### 2.3 输入方式

| 方式 | 用途 | 说明 |
|---|---|---|
| Siri / App Intent | 免打开 App 快速记录 | 基于现有 `HealthCommandIntent` 扩展为结构化饮食路径 |
| Watch App 录入 | 需要确认、改份量、看结果 | 第一阶段核心入口 |
| Smart Stack Widget | 饭点前后推荐“记录这餐” | 不强打扰, 作为上下文入口 |
| Complication | 显示今日饮食记录状态 | 例如“2/3 餐已记”或“蛋白还差 42g” |
| iPhone 照片 | 复杂餐食补充 | Watch 没摄像头, 照片仍交给 iPhone |

### 2.4 低置信度追问策略

Watch 上不能多轮盘问。追问必须少而准:

| 场景 | 追问 |
|---|---|
| “一份牛肉”不清楚 | “牛肉约一掌心还是两掌心?” |
| “米饭”无份量 | “米饭半碗还是一碗?” |
| “拿铁”无糖不明 | “无糖还是加糖?” |
| “火锅/烧烤/自助”复杂 | “按正常量还是吃多了?” |
| “喝酒” | “大约几杯?” |

如果用户不回答, 也记录原始文本, 但打 `confidence=low`。

### 2.5 食物语音协议

建议新增一个明确协议, 不再让食物记录长期走通用 chat 自动补录:

```text
FoodVoiceCapture
  raw_text
  captured_at
  device_source = apple-watch | siri | mobile
  meal_type
  foods[]
    name
    quantity_text
    normalized_quantity
    calories_estimate
    protein_g
    carbs_g
    fat_g
    confidence
  total_calories
  total_protein_g
  risk_tags[]
  confidence
  confirmation_state = pending | confirmed | edited | discarded
  linked_diet_record_id
```

v1 可以不建完整新表, 先通过后端解析服务写入 `DietRecord`, 并把原始文本、置信度、设备来源放入 `notes` 或扩展字段。v2 再拆出 `food_voice_captures` 作为可审计事实流。

---

## 3. 智能提醒

### 3.1 提醒原则

Watch 不是通知轰炸器。提醒必须符合三条:

1. **少**: 每天 3-5 个关键触点。
2. **准**: 基于状态、饭点、位置/时间、计划和最近记录。
3. **可执行**: 每条提醒能直接确认、延后、跳过或修改。

### 3.2 推荐提醒触点

| 时机 | 触发 | Watch 文案方向 | 行动 |
|---|---|---|---|
| 起床后 | 睡眠/HRV/RHR/SpO2 已同步 | “今天恢复偏黄, 运动降一级” | 查看今日计划 |
| 早餐后 | 未记录早餐或蛋白不足 | “早餐蛋白可能不足, 要补记吗?” | 记录/跳过 |
| 午饭后 20-40 分钟 | 午餐碳水较高或久坐 | “走 10 分钟, 把餐后波动压下来” | 开始计时/完成 |
| 下午 | 饮水/步数落后 | “还差 900ml 水或 3000 步” | 记录/提醒稍后 |
| 运动前 | readiness 黄/红 | “今天不做高强度, Zone 2 即可” | 接受降级 |
| 晚餐前 | 蛋白不足/热量剩余 | “晚餐优先蛋白, 主食减半” | 查看建议 |
| 21:00-22:00 | 晚餐过晚/夜宵风险 | “进入睡眠保护窗口” | 确认 |
| 异常 | 低血氧/胸闷/高心率/血压风险 | “先观察/复测/必要时就医” | 记录症状/升级 |

### 3.3 提醒分类

| 类型 | 目标 | 是否需要强提醒 |
|---|---|---|
| Safety | 避免风险, 如低血氧、胸痛、异常高心率 | 是, 但文案必须有医疗边界 |
| Recovery | 根据 HRV/RHR/睡眠降级训练 | 中等 |
| Behavior | 饭后走路、喝水、记录饮食、睡前窗口 | 轻触即可 |
| Evidence | 提醒补数据, 如体重/腰围/BP | 低频 |
| Review | 每周复盘和 outcome proof | 不在 Watch 上展开 |

---

## 4. Watch App 功能范围

### 4.1 v1 功能

| 功能 | 说明 |
|---|---|
| Today Status | 显示 green/yellow/red 恢复状态、今日最重要行动 |
| Food Voice Capture | 一句话记录饮食, 结构化后确认 |
| Quick Record | 饮水、补剂、症状、疲劳、情绪、运动 RPE |
| Action Feedback | 对 Daily Plan action 进行 done / skip / adjust / remind later |
| Smart Stack Widget | 当前最该做的一件事 |
| Complication | 今日状态或饮食/行动进度 |
| Basic Notifications | 饭后、运动前、睡前、数据缺口提醒 |

### 4.2 v2 功能

| 功能 | 说明 |
|---|---|
| Workout Gate | 运动前根据 readiness 给强度上限 |
| Zone 2 Haptic | 运动中心率区间震动提示 |
| RPE Capture | 运动后 5 秒记录主观强度 |
| Food Follow-up | 常见食物一键复用、份量微调 |
| Medication / Supplement Confirm | 与现有补剂/药物计划联动 |
| Contextual Widget Relevance | 根据饭点、计划、状态提高 Smart Stack 出现概率 |

### 4.3 v3 功能

| 功能 | 说明 |
|---|---|
| Watch Workout App | 自己启动 workout session, 采集 live HR / zone / duration |
| Multidevice Workout | Watch 采集, iPhone/Mac 展示更详细实时视图 |
| Offline Capture Queue | 无网络时本地排队, iPhone 恢复后同步 |
| Doctor-ready Event Timeline | 把症状、饮食、运动、体征整理成可分享时间线 |

---

## 5. 系统架构

### 5.1 数据流

```text
Apple Watch
  - voice transcript
  - action feedback
  - quick records
  - workout session signals
  - local notification response

        |
        | WatchConnectivity / REST / App Intent
        v

iPhone App
  - HealthKit bridge
  - token/session owner
  - confirmation UI
  - offline queue
  - photo capture fallback

        |
        v

Backend
  - structured food parser
  - DietRecord / Water / Supplement / Symptom records
  - DailyOperatingPlan
  - HealthTwin
  - Safety Guardian
  - Outcome Proof
  - Operating Review

        |
        v

Three Clients
  - Watch: execute and confirm
  - Mobile: edit and inspect
  - Mac/Web: review, analyze, plan
```

### 5.2 WatchConnectivity vs Direct REST

| 通道 | 适合 | 原则 |
|---|---|---|
| WatchConnectivity | token 不直接暴露给 Watch、需要 iPhone 参与确认和排队 | v1 首选 |
| Direct REST from Watch | Watch 独立联网、简单记录 | 仅用于低风险、低敏、已登录状态明确的请求 |
| App Intent | Siri/Shortcuts/Action Button 间接入口 | 用于快速记录和打开 App |
| Push Notification Action | 提醒后的确认/跳过 | 行为反馈主路径之一 |

### 5.3 Action Button 策略

不能假设第三方 App 可以强行接管 Ultra 的 Action Button。产品上应提供:

1. App Intent: `记录饮食`, `记录症状`, `记录饮水`, `查看今日状态`。
2. Shortcuts 配置说明: 用户可以把 Action Button 绑定到对应 shortcut。
3. Watch App 内固定入口: 即使 Action Button 未配置, 也能从 Complication / Smart Stack 打开。

推荐默认:

```text
Action Button -> Shortcut -> HealthCommandIntent("记录饮食")
```

如果用户更重视运动:

```text
Action Button -> Start Workout Gate / Zone 2 session
```

---

## 6. 与现有代码的关系

### 6.1 已有资产

| 资产 | 当前能力 | Watch 规划如何复用 |
|---|---|---|
| `mobile/plugins/withIntentsExtension.js` | App Intent 语音快速记录 | 扩展为食物结构化 Intent |
| `backend/app/api/diet.py` | `/diet/records`, `/diet/recognize-and-save`, stats, frequent foods | Watch 记录最终写入 DietRecord |
| `mobile/services/diet.ts` | 移动端饮食 CRUD 和常吃食物 | iPhone 编辑/确认复用 |
| `apps/mac/.../RecordClient.swift` | Mac 结构化记录 diet/water/supplement/vitals | 三端记录合同对齐 |
| `backend/app/services/device_source_priority.py` | Apple Watch 多源优先级 | Watch 状态和恢复判断使用同一合并口径 |
| `backend/app/services/daily_operating_plan.py` | 今日行动和恢复降级雏形 | Watch action feedback 接入 |
| `frontend/mobile/mac` health extras | Outcome / guardrail / review 摘要 | Watch 只显示最小状态, 复盘在大屏 |

### 6.2 需要新增/重构

| 项目 | 说明 |
|---|---|
| Food parser endpoint | `POST /diet/voice/parse` 或 `POST /quick-record/parse-food` |
| Confirm endpoint | `POST /diet/voice/confirm` 或直接 `POST /diet/records` |
| Voice capture audit | 记录 raw_text、device_source、confidence、parser_version |
| Watch action feedback | 统一写入 Daily Plan action feedback / InterventionEvent |
| Notification policy | 服务端生成可执行提醒, 客户端只负责投递和响应 |
| Watch models | Today status、Food draft、Action item、Quick record result |
| App Intent contracts | 明确 Siri phrase、参数、返回文案、错误降级 |

---

## 7. 语音食物解析策略

### 7.1 分层解析

| 层 | 作用 | 技术 |
|---|---|---|
| Rule parser | 餐次、时间、常见单位、常见中文食物、酒精/甜饮标签 | deterministic |
| User memory | 常吃食物、历史份量、中位营养素 | existing frequent foods |
| LLM parser | 复杂菜名、组合餐、模糊份量估算 | structured JSON |
| Nutrition estimator | 热量/蛋白/碳水/脂肪估算 | existing estimate service + food DB |
| Confidence grader | 判断是否可直接确认或需追问 | deterministic + thresholds |

### 7.2 结构化输出示例

```json
{
  "meal_type": "lunch",
  "food_items": "半碗米饭, 青椒牛肉一份, 鸡蛋两个, 无糖拿铁一杯",
  "foods": [
    {"name": "米饭", "quantity_text": "半碗", "calories": 130, "protein_g": 2.5, "confidence": 0.7},
    {"name": "青椒牛肉", "quantity_text": "一份", "calories": 320, "protein_g": 24, "confidence": 0.55},
    {"name": "鸡蛋", "quantity_text": "两个", "calories": 140, "protein_g": 12, "confidence": 0.9},
    {"name": "无糖拿铁", "quantity_text": "一杯", "calories": 90, "protein_g": 6, "confidence": 0.75}
  ],
  "total_calories": 680,
  "protein_g": 44.5,
  "risk_tags": ["protein_ok", "no_sugary_drink"],
  "confidence": 0.68,
  "followup_question": "青椒牛肉大概是一掌心还是两掌心?"
}
```

### 7.3 记录策略

| 置信度 | 行为 |
|---|---|
| `>=0.75` | Watch 显示摘要, 用户确认后直接保存 |
| `0.45-0.75` | 只追问一个最影响热量/蛋白的问题 |
| `<0.45` | 保存原始文本为待补全 draft, 引导到 iPhone 编辑 |

---

## 8. 恢复状态和行动提醒

### 8.1 Watch 上显示的状态

第一阶段只显示一个颜色和一句话:

| 状态 | 条件示例 | 文案 |
|---|---|---|
| Green | 睡眠够, HRV 正常, RHR 正常, 无安全告警 | “今天可以按计划活动” |
| Yellow | 睡眠不足/HRV 低/RHR 高/训练负荷偏高 | “今天运动降一级” |
| Red | 急性不适、明显低血氧、胸闷、严重疲劳或安全规则触发 | “今天先恢复, 必要时复测或就医” |

### 8.2 Watch 和 Daily Plan 的关系

Watch 不自己决定行动。它消费后端 Daily Plan:

```text
DailyOperatingPlan.state_summary -> Watch Today Status
DailyOperatingPlan.actions[0] -> Watch 下一步行动
Action feedback -> Backend InterventionEvent / action feedback
Outcome review -> Mobile/Mac/Web 展示
```

Watch 的目标是让计划闭环变得更真实:

- 不再依赖用户晚上回忆“我做没做”。
- 每次提醒都能形成事件。
- 未来 outcome grading 可以区分“建议错了”还是“没执行”。

---

## 9. 隐私和安全

### 9.1 隐私原则

- Watch 不常驻监听。
- 只有用户主动点击/抬腕/调用 Siri 时才录入。
- 食物、症状、药物、基因、体检都属于敏感健康上下文, 日志中必须脱敏。
- raw transcript 应可删除, 且能看到它是否被用于饮食记录。
- Watch 本地只缓存必要 draft 和展示数据, 不长期保存完整健康档案。

### 9.2 医疗边界

允许:

- 健康管理建议。
- 饮食/运动/睡眠行为提醒。
- 低风险 general wellness 目标。
- 风险提示和复测建议。
- 医生沟通材料。

不允许:

- Watch 上直接诊断疾病。
- 调整处方药剂量。
- 对高血压/睡眠呼吸暂停/心律异常作确定性诊断。
- 用消费级传感器替代医疗检测。

### 9.3 提醒安全

高风险提醒必须有明确边界:

```text
如果胸痛、明显气促、晕厥、持续心悸或症状加重, 不要只依赖 App, 应及时就医。
```

---

## 10. 分期路线

### Phase 0: 对齐现有记录合同 (1 周)

目标: 不做 Watch App 也先让语音食物记录走结构化路径。

- 梳理现有 `HealthCommandIntent`、quick record、diet records、recognize-and-save。
- 设计 `FoodVoiceDraft` 合同。
- 新增后端解析服务的测试用例: 中文饭菜、份量、甜饮、酒精、夜宵。
- 明确哪些字段写 `DietRecord`, 哪些进入 notes/raw metadata。
- 更新 Web/Mobile/Mac 对饮食记录的展示, 支持 `source=voice_watch/siri`。

验收:

- “午饭半碗米饭一份牛肉两个鸡蛋”能解析为 meal + food_items + calories + protein draft。
- 低置信度不会直接污染高置信饮食统计。

### Phase 1: Watch Companion MVP (2-3 周)

目标: 真正在 Watch 上完成“记录食物 -> 确认 -> 入库”。

- 新建 watchOS companion target。
- Today Status 页面。
- Food Voice Capture 页面。
- 一键确认/改份量/稍后。
- WatchConnectivity 同步到 iPhone, iPhone 调后端。
- Smart Stack Widget 显示“记录这餐”或“下一步行动”。
- 基础通知 action: done / skip / remind later。

验收:

- 用户不用打开手机, 能在 Watch 上完成一餐记录。
- 记录进入 `/diet/records` 并被 Today/Diet/Mac dashboard 看到。
- Watch 上能看到今日最重要行动, 并能反馈完成/跳过。

### Phase 2: 智能提醒和恢复降级 (2-4 周)

目标: Watch 提醒不只是闹钟, 而是基于状态和计划。

- 后端输出 `wrist_next_action` 和 `notification_policy`。
- 根据 HealthKit/Watch 数据新鲜度、HRV、RHR、睡眠、SpO2、Daily Plan 生成 green/yellow/red。
- 饭后步行提醒与饮食记录联动。
- 运动前 readiness gate。
- 睡前窗口提醒与晚餐/咖啡因/夜宵联动。

验收:

- 黄/红恢复日不推高强度训练。
- 午餐碳水偏高后, Watch 推饭后步行提醒。
- 用户每条提醒都能反馈, 反馈进入 Operating Review。

### Phase 3: Workout 和 Zone 2 (4-6 周)

目标: 让 Watch 在运动时提供最小但有效的实时反馈。

- 支持启动 workout gate。
- 读取 live heart rate / zone。
- Zone 2 偏离时震动提示。
- 运动后记录 RPE 和恢复建议。
- 和 existing workout / post workout analysis / MovementCoach 连接。

验收:

- Watch 能提示“太快了, 回到 Zone 2”。
- 运动后自动生成训练负荷和明日恢复建议。
- Daily Plan 能根据上一日 workout + 睡眠恢复调整第二天。

### Phase 4: Personal Outcome Loop (持续)

目标: 证明 Watch 真的让人变健康。

- 统计 Watch 食物语音记录率。
- 统计饭后步行执行率。
- 关联体重、腰围、睡眠、HRV、RHR、血压、血脂、血糖趋势。
- 在 Mobile/Mac/Web 展示“哪些腕上提醒对你有效”。

验收:

- 4 周内能展示: 哪类提醒被执行最多, 哪类和指标改善相关。
- 12 周内能展示: 饮食记录完整度提升是否带来体重/腰围/睡眠改善。

---

## 11. 成功指标

| 指标 | 目标 |
|---|---|
| Food voice capture success | 80% 以上语音能生成可确认 draft |
| One-tap confirmation rate | 60% 以上食物 draft 不需要打开手机编辑 |
| Daily diet logging coverage | 核心用户 7 天内记录 >= 5 天 |
| Meal timing coverage | 早餐/午餐/晚餐餐次识别准确率 >= 85% |
| Protein target visibility | 每天能显示“蛋白还差多少” |
| Reminder action rate | Watch 提醒后有 done/skip/snooze 反馈 >= 50% |
| Plan adherence evidence | Daily Plan 中至少 3 类行动可被 Watch 反馈 |
| Recovery safety | 黄/红恢复日不生成高强度默认行动 |
| Outcome proof | 4 周内能看到执行行为和至少 1 个代理指标的关系 |

---

## 12. 风险和取舍

### 12.1 技术风险

| 风险 | 处理 |
|---|---|
| Watch 输入体验不稳定 | v1 使用系统 dictation/TextField/App Intent, 不做后台常驻录音 |
| Action Button 配置受系统限制 | 通过 Shortcuts/App Intents 暴露入口, 不假设强绑定 |
| Watch 网络不稳定 | 首选 WatchConnectivity 到 iPhone, 失败进入队列 |
| 食物解析误差大 | 置信度 + 用户确认 + 常吃食物记忆 |
| 通知过多 | 每天限制关键提醒数量, 每条必须可执行 |
| HealthKit native 改动需要构建 | 纯 JS 不可 OTA, Watch target 属 native 变更, 需 EAS/dev build/TestFlight |

### 12.2 产品风险

| 风险 | 处理 |
|---|---|
| 用户嫌烦 | Watch 每天只推 3-5 个关键触点 |
| 用户不信估算 | 明确“估算区间”, 支持快速改份量 |
| 记录变成负担 | 常吃食物、历史份量、餐次自动推断 |
| 健康建议过度医疗化 | 坚持 wellness + 复测/医生沟通边界 |
| 做成小屏复杂 App | Watch 只做状态、记录、确认 |

---

## 13. Office Hour 决策

### 13.1 已定方向

1. 做 Watch 版本, 但定位为腕上执行器。
2. 首个核心功能是语音记录食物。
3. 食物语音必须结构化确认, 不能长期依赖通用 chat 自动补录。
4. Watch 提醒必须和 Daily Plan、恢复状态、Outcome Proof 连接。
5. Watch 不做主 Agent, 不做长聊天。

### 13.2 待确认问题

1. Action Button 默认绑定什么?
   - 推荐: 记录饮食。
   - 备选: 查看今日状态 / 开始运动 gate。

2. Watch App 第一个版本是否只服务个人使用?
   - 推荐: 是。先做个人闭环, 再考虑公开用户。

3. 食物营养估算要不要接外部 food database?
   - 推荐: v1 先用现有估算 + 常吃食物记忆, v2 再接更完整数据库。

4. Watch 通知由谁调度?
   - 推荐: 服务端输出策略, iPhone/Watch 负责本地投递和响应。

5. 是否先做 Siri/App Intent 而非完整 Watch App?
   - 推荐: Phase 0 先强化 App Intent 结构化食物记录, Phase 1 再 Watch App。

---

## 14. 推荐下一步

如果进入实现, 建议按以下顺序拆计划:

1. 写 `FoodVoiceDraft` 合同和后端解析测试。
2. 把现有 `HealthCommandIntent` 的饮食记录从通用 agent path 分流到结构化 food voice path。
3. Mobile 端增加 food draft 确认/编辑能力。
4. 三端展示饮食记录来源和置信度。
5. 新建 watchOS companion target, 只做 Food Voice Capture + Today Status。
6. 接入 Smart Stack Widget 和基础 notification actions。
7. 把 action feedback 写入 Daily Plan / InterventionEvent。
8. 再做 workout gate 和 Zone 2 haptic。

---

## 15. References

- Apple Watch Ultra 3 technical specifications: https://www.apple.com/apple-watch-ultra-3/specs/
- Apple Watch Ultra 3 announcement: https://www.apple.com/newsroom/2025/09/introducing-apple-watch-ultra-3/
- watchOS 26 announcement: https://www.apple.com/newsroom/2025/06/watchos-26-delivers-more-personalized-ways-to-stay-active-and-connected/
- Smart Stack guide: https://support.apple.com/guide/watch/see-widgets-in-the-smart-stack-apdecf142fb9/watchos
- Apple Watch dictation/text input: https://developer.apple.com/documentation/watchkit/wkinterfacetextfield
- Apple Speech framework: https://developer.apple.com/documentation/speech/
- Watch Connectivity: https://developer.apple.com/documentation/watchconnectivity
- App Intents: https://developer.apple.com/documentation/appintents

