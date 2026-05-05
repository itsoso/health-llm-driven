# Mobile 产品地图 (Product Map)

> 单一事实源 — 修改任何 mobile 功能前先看这里。
> 维护规则：新加页面/intent/push 都要在本文档登记。

---

## 一、信息架构 (导航树)

```
认证: login → (tabs)

(tabs) — 5 个一级标签
├── index           主页 / Dashboard         — HomeHeader + dashboard cards + 聊天流
├── chat            AI 助手                  — 文字对话主页 (含 voice-chat 入口)
├── record          记录                     — 快捷录入 + readiness 入口
├── journal/        健康日志                 — 病史/症状/事件 时序
└── alerts          告警                     — anomaly_alert 列表

二级页 (push / button → router.push)
├── voice-chat                语音对话核心     — 多 intent 入口 (见 §三)
├── voice-style              语音风格设置     — 选私享女声等
├── workout-list / workout-detail   运动详情
├── sleep / sleep-spo2-*           睡眠相关
├── ai-profile               AI 画像 (Memory + Scorecard)
├── memory                   长期事实查看
├── notification-settings    推送 + L9 autonomy slider
├── notification-history     推送历史
├── family                   家庭健康 (G, MVP 只读)
├── medical-exams / medical-exam-detail
├── indicator-history        指标趋势
├── consultations            专家会诊
├── goals / directives / reminders
├── doctor-loop              医生回路
├── monthly-reports          月度复盘
├── trace/                   告警溯源 (deep_link /trace/anomaly_X)
├── specialist/              专家详情
├── settings                 设置总入口
└── diet                     饮食日志
```

---

## 二、关键页面职责 + 修改入口

| 页面 | 文件 | 谁会改这里 | 数据来源 |
|------|------|-----------|----------|
| 主页 | `app/(tabs)/index.tsx` + `components/dashboard/HomeHeader.tsx` | 加 dashboard 卡片 / 重排 hero metrics | `services/dashboard.ts`, `services/garmin.ts`, `services/environment.ts` |
| AI 助手 | `app/(tabs)/chat.tsx` + `services/chat.ts` (streamChat) | 改 LLM 流处理 / tool_result 渲染 | `/agent/stream` SSE |
| 记录 | `app/(tabs)/record.tsx` | 加快捷入口、QuickNavBtn | 各 record API |
| 告警列表 | `app/(tabs)/alerts.tsx` | 告警卡渲染、deep_link 行为 | `/anomaly-alerts/me` |
| **语音对话核心** | `app/voice-chat.tsx` + `hooks/useVoiceConversation.ts` | **加 intent 一定改这两个文件** | 见 §三 |
| 私享女声 | `services/cloudTts.ts` + `services/voiceStyle.ts` | TTS provider / voice id | `/tts/synthesize` |
| 运动详情 | `app/workout-detail.tsx` | 加指标 chip / AI 分析渲染 / "听一下" 按钮 | `/workout/me/{id}` + `/voice-coach` |
| AI 画像 | `app/ai-profile.tsx` | tier chip / scorecard | `/memory/facts` + `/scorecard/me` |
| 推送设置 | `app/notification-settings.tsx` | 加新 toggle / **L9 autonomy slider 在这** | `/notification/settings` |
| 家庭 | `app/family.tsx` | 家庭成员卡 / 邀请流 (TODO) | `/family/dashboard` |

---

## 三、voice-chat intent 总表 ⭐

**所有"语音功能"都通过 `voice-chat ?intent=*` 单一入口聚合。** 加新场景时复用这套机制。

| intent | 触发源 | 后端拉稿 | 行为 | 改进编号 |
|--------|--------|---------|------|----------|
| `(无)` | 用户主动点 voice-chat tab | - | 待用户点球开始 | MVP |
| `?autoStart=1` | Siri AppShortcut (HealthAnalysisOpenIntent) | - | 立即开始录音 | Layer 3 |
| `?intent=briefing` | 早 7:30 推送 (`send_morning_health_summary`) | `GET /v1/briefing/voice-script` | 私享女声播 60-90 字 → 进 listening | **A** |
| `?intent=clarify&alert_id=X` | anomaly_alert 推送 (mode=converse) | `GET /v1/clarification/opener?alert_id=X` | AI 主动开口问 follow-up → 接话 → 抽 fact | **D** |
| `?intent=weekly` | 周日 20:00 (`send_weekly_review_invite`) | `GET /v1/briefing/weekly-voice-script` | 本周回顾 + 询问下周计划 | **E** |
| `?intent=preworkout&workout_type=X` | record tab 按钮 | `GET /v1/briefing/preworkout-voice-script` | readiness 建议 + 接话 | **F** |

### voice-chat 加新 intent 4 步法
1. 后端建 `services/<场景>_voice_script.py` (类比 `briefing_voice_script.py`)
2. 后端建 `GET /v1/briefing/<场景>-voice-script` 端点 (在 `api/briefing.py` 加)
3. mobile `services/briefing.ts` 加 `fetch<场景>VoiceScript()` 函数
4. mobile `app/voice-chat.tsx` 加一个 `useEffect` block + `<场景>TriggeredRef` (复制现有 pattern)

### voice-chat 关闭按钮做的事 (`app/voice-chat.tsx` onPress)
1. fire-and-forget `extractMemoryFromDialog(userTurns, alertId)` ← D-L6, 抽 fact 写 memory_facts
2. `voice.reset()` — 停 TTS / 清队列 / 切回 .playback / 清 silenceTimer
3. `router.back()`

---

## 四、推送 (APNs) 类型 + deep_link 总表 ⭐

| notification_type | 触发任务 | data.deep_link | 用户行为 |
|-------------------|---------|----------------|---------|
| `morning_briefing` | `send_morning_health_summary` (7:30) | `/voice-chat?intent=briefing` | A 改进 |
| `health_alert` (有 clarify 模板 + mode=converse) | `anomaly_detection_service.send_alerts` | `/voice-chat?intent=clarify&alert_id=X` | D 改进 |
| `health_alert` (其它) | 同上 | `/trace/anomaly_X` | 详情页 |
| `workout_analysis` | `auto_analyze_workout` (跑后) | `/workout-detail?id=X` | W3 |
| `ai_advice` (周聊) | `send_weekly_review_invite` (周日 20:00) | `/voice-chat?intent=weekly` | E 改进 |
| `reminder` | reminder schedule | `/reminders` | - |
| `goal_progress` | goal eval | `/goals` | - |

mobile 路由处理: `hooks/useNotifications.ts` `handleNotificationResponse` 优先 `data.deep_link`，否则 fallback `data.screen`。

---

## 五、L9 Autonomy Slider (告警反应档位)

**字段**: `UserNotificationSetting.alert_clarify_mode` ∈ `silent | notify | converse`

| mode | 行为 | 注意 |
|------|------|------|
| `silent` | 只写 alerts tab 不推送 | critical 级强制至少 notify (生命安全) |
| `notify` | 推送, deep_link 跳 trace 详情 | 不开口对话 |
| `converse` | 推送 + voice-chat 主动开口 (默认) | Agent Native 全闭环 |

修改入口: `app/notification-settings.tsx` 的 ClarifyModeRow 组件。

---

## 六、Memory 系统数据流 (Karpathy "anterograde amnesia" 解药)

```
用户语音对话
  ↓
voice-chat onClose: extractMemoryFromDialog(turns)
  ↓
POST /v1/clarification/extract-memory
  ↓
backend: memory_dialog_extractor.extract_facts_from_dialog(text)  ← LLM 抽 5 条结构化事实
  ↓
memory_service.write_fact (自动去重 → reinforce)
  ↓
memory_facts 表
  ↓
下次 build_twin → render_facts_for_prompt → AI 看到这些 fact → 更精准
```

### 触达点
- **写**: 对话 onClose / specialist findings / action_card_outcome / medical_exam / briefing entry
- **读**: 用户在 `/ai-profile` / `/memory` 页面看
- **删/纠正**: ai-profile 左滑 dismiss
- **衰减**: `tasks/memory_lifecycle.py` Celery task

---

## 七、版本演化时间线 (build 41 → 47+)

```
build 41-43: Siri Shortcuts MVP (3 层)
build 44:    Siri Swift 单文件合并修复
build 45:    voice-chat 流式 TTS + 自动接轮 (Layer 3 完成)
build 46:    cosyvoice-v3.5-plus 私享女声 + W3 跑后教练推送 + ai-profile UI fix
build 47:    A 晨间简报 + B Siri "今天怎么样" + C 跑后听一下 + 音量根因修复

build 47 后 OTA 累积 (按时间序):
  D 主动澄清对话 (clarify intent)
  voice 三修 (关闭即停 / TTS 不重叠 / 1.2s 静默自动发)
  L6 Memory 自动写入
  L7 tool schema 加厚 (LLM 选对 dimension)
  L8 weight 写前确认 (Karpathy "verification is the bottleneck")
  L9 autonomy slider (silent/notify/converse)
  E 周聊语音邀请 (周日 20:00)
  F 跑前 readiness 对话 (record tab 入口)
  G 家庭健康只读页 (settings → 家庭健康)
```

---

## 八、设计原则

1. **Mobile First**: 锁屏可读 + 一键听 + 一键回话
2. **Agent Native** (Karpathy):
   - LLM 有 anterograde amnesia → **必须**写 Memory (D-L6)
   - LLM 容易 jagged → **必须**有 verification (L8 weight 确认)
   - LLM 不要全自动 → **必须**有 autonomy slider (L9)
   - 为 agent 设计文档 (L7 tool schema)
3. **复用 voice-chat 单入口**: 任何"AI 主动找用户"的场景都走 `?intent=*`，不再造新页面
4. **私享女声为差异化锚点**: cosyvoice-v3.5-plus 复刻音色，是用户感知最强的差异
5. **数据闭环**: 推送 → 对话 → Memory → 下次推送更准

---

## 九、近期未做项 (Backlog)

- **G Phase 2**: 家庭邀请流 / 切换视角 / 跨成员告警路由
- **H 健康事件流 Timeline**: 主页改时间线，每条事件可点开互动
- **I 声音笔记 Voice Journal**: 用户语音"今天头疼" → LLM 解析归类录入
- **F Phase 2**: Garmin RHR 飙升自动检测 → 主动推 preworkout
- **L8 扩展**: 把"先确认"模式扩到 blood_pressure / illness / reminder
- **proximity 自动听筒**: 写 native module 实现贴脸切听筒 (expo-audio 当前不支持)
