# mobile/PRODUCT_MAP.md — 给代码 Agent 用的产品地图

> **本文档优先于代码探索**: 改 mobile 任何功能前先 grep 这里, 减少试错.
> 维护规则: 加 page / intent / push / 改进编号 必须在本文档登记.

## ⚡ 最快速查找

| 我想... | 看哪 |
|---|---|
| 加一个 voice-chat 触发场景 | §2 voice-chat intent SOP |
| 加一种推送类型 | §3 push registry |
| 改 push 点击跳转 | `mobile/hooks/useNotifications.ts` `handleNotificationResponse` |
| 加 dashboard 卡片 | `mobile/components/dashboard/HomeHeader.tsx` 或 `app/(tabs)/index.tsx` |
| 改 LLM tool 行为 | `backend/app/services/agent_executor.py` + `tool_schema_registry.py` |
| 加 settings 开关 | `app/notification-settings.tsx` + `services/notifications.ts` types + `backend/app/api/notification.py` |
| 改私享女声 | `services/voiceStyle.ts` (Voice 配置) + `backend/app/services/tts/cosyvoice.py` (云端) |
| Memory 写入怎么走 | §6 |
| 看产品改进编号对应啥 | §8 改进编号注册表 |

---

## §1 文件 → 职责映射 (高密度)

```
mobile/app/
  (tabs)/_layout.tsx          5 个一级 tab 的注册 (index/chat/record/journal/alerts)
  (tabs)/index.tsx            主页 dashboard, 内嵌 chat 流
  (tabs)/chat.tsx             AI 文字对话
  (tabs)/record.tsx           快捷录入 + QuickNavBtn (加跑前准备入口)
  (tabs)/alerts.tsx           anomaly_alert 列表
  (tabs)/journal/             健康日志/事件
  voice-chat.tsx              ⭐ 语音对话核心 (intent dispatcher)
  voice-style.tsx             选私享女声等
  workout-detail.tsx          运动详情 (指标 chip / AI 分析 / 听一下按钮)
  workout-list.tsx
  sleep.tsx                   睡眠详情
  sleep-spo2-analysis.tsx     夜间血氧分析
  sleep-spo2-longitudinal.tsx 夜间血氧时序
  ai-profile.tsx              ⭐ Memory + ActionCard scorecard
  memory.tsx                  长期事实只读
  notification-settings.tsx   ⭐ 推送 + L9 autonomy slider 在这
  notification-history.tsx    推送历史
  family.tsx                  ⭐ 家庭健康 (G, 只读 MVP)
  medical-exams.tsx
  medical-exam-detail.tsx
  indicator-history.tsx
  consultations.tsx
  consultations/[id].tsx
  goals.tsx / directives.tsx / reminders.tsx
  doctor-loop.tsx
  monthly-reports.tsx
  monthly-report/[year]/[month].tsx
  trace/                      告警溯源 deep_link target
  specialist/[name].tsx
  diet.tsx
  settings.tsx                设置入口树, 加 SettingRow 在这
  login.tsx

mobile/services/
  api.ts                      axios baseURL + auth interceptor
  chat.ts                     streamChat SSE 处理 (token/tool/done/error)
  briefing.ts                 ⭐ 所有 voice-chat intent 拉稿函数集中在这
  cloudTts.ts                 私享女声 cosyvoice 调用
  voiceStyle.ts               voice id 映射 + STORAGE_KEY 迁移
  notifications.ts            settings types (新加 toggle 在这加字段)
  workouts.ts                 含 getWorkoutVoiceCoach (听一下)
  family.ts                   家庭仪表盘
  ...

mobile/hooks/
  useVoiceConversation.ts     ⭐ 语音状态机 (listening/thinking/speaking)
                              speakDirect / silenceTimer (1.2s 自动发) / playback↔record session
  useNotifications.ts         ⭐ APNs 收到推送的路由分发 (handleNotificationResponse)

mobile/components/
  dashboard/HomeHeader.tsx    主页 hero 卡片
  workout/HrChart.tsx / PaceBars.tsx / HrZoneBar.tsx / HeroMetrics.tsx
  design-system/HealthCard.tsx
  chat/OpenerCard.tsx
  ...

backend/app/
  api/briefing.py             ⭐ 所有 voice-chat intent 后端短稿端点
  api/clarification.py        D 改进 (opener + extract-memory)
  api/workout.py              workout/me/{id}/voice-coach (听一下)
  api/family.py               家庭 CRUD + dashboard
  api/notification.py         settings GET/PUT
  api/tts.py                  POST /tts/synthesize
  services/briefing_voice_script.py     A 晨间
  services/weekly_review_voice_script.py E 周聊
  services/preworkout_voice_script.py   F 跑前
  services/alert_clarification.py       D 告警澄清
  services/memory_dialog_extractor.py   D-L6 抽 fact
  services/memory_service.py            write_fact (去重/reinforce)
  services/agent_executor.py            ⭐ tool 执行 + L8 weight 确认
  services/tool_schema_registry.py      ⭐ L7 tool description (LLM 选对靠这)
  services/anomaly_detection_service.py ⭐ alert 推送 + L9 mode dispatch + clarify deep_link
  services/exercise_recovery_service.py readiness score (F 用)
  services/notification/push_service.py 推送 + dedup + opt_out
  tasks/notifications.py                ⭐ Celery: morning_briefing/weekly_invite/...
  tasks/garmin_sync.py                  auto_analyze_workout (W3)
  tasks/memory_lifecycle.py             memory 衰减
  models/notification.py                NotificationType enum + UserNotificationSetting
  models/memory_fact.py                 memory_facts schema
  models/anomaly_alert.py               anomaly_alerts schema
  models/family.py                      family_groups + family_members
  celery_app.py                         ⭐ beat_schedule (周日 20:00 加这里)
```

---

## §2 voice-chat intent — SOP 加新场景 ⭐⭐⭐

**所有"AI 主动找用户"的语音功能都通过 `voice-chat ?intent=*` 单一入口聚合**, 不要自建页面.

### 现有 intent 表
| intent | 触发源 | 后端拉稿 endpoint | 改进编号 |
|--------|--------|---------|------|
| `(无)` | 用户主动点 voice-chat tab | - | MVP |
| `?autoStart=1` | Siri AppShortcut | - | Layer 3 |
| `?intent=briefing` | 早 7:30 push (`send_morning_health_summary`) | `GET /v1/briefing/voice-script` | A |
| `?intent=clarify&alert_id=X` | anomaly push (mode=converse) | `GET /v1/clarification/opener?alert_id=X` | D |
| `?intent=weekly` | 周日 20:00 push (`send_weekly_review_invite`) | `GET /v1/briefing/weekly-voice-script` | E |
| `?intent=preworkout&workout_type=X` | record tab 按钮 | `GET /v1/briefing/preworkout-voice-script` | F |
| `?intent=journal` | record tab 按钮 (声音笔记) | (无, 客户端固定 opener) | I |

### 加新 intent 4 步法 (复制 pattern)
```
1. backend: 建 services/<场景>_voice_script.py
   函数签名: build_<场景>_voice_script(db, user_id, ...) -> str
   返回 60-150 字, 中文, 无 markdown, 末尾问句引导接话.

2. backend: api/briefing.py 加 GET /v1/briefing/<场景>-voice-script 端点
   复制现有 get_voice_script 函数, 改 build 调用.

3. mobile: services/briefing.ts 加 fetch<场景>VoiceScript() 函数
   复制 fetchBriefingVoiceScript pattern.

4. mobile: app/voice-chat.tsx 加一个 useEffect block
   - import fetch 函数
   - 文档注释 §"启动入口" 加一行
   - params 类型加新字段 (如 alert_id / workout_type)
   - 复制 weeklyTriggeredRef pattern, useEffect 检测 intent → speakDirect
```

### voice-chat 关闭按钮 (`app/voice-chat.tsx` close onPress)
1. fire-and-forget `extractMemoryFromDialog(userTurns, alertId)` — D-L6 抽 fact 写 memory_facts
2. `voice.reset()` — 停 TTS / 清队列 / 切回 .playback / 清 silenceTimer
3. `router.back()`

---

## §3 推送类型 + deep_link 注册表 ⭐

| notification_type | 触发任务 | data.deep_link | 改进 |
|-------------------|---------|----------------|------|
| `morning_briefing` | `send_morning_health_summary` (7:30) | `/voice-chat?intent=briefing` | A |
| `health_alert` (有 clarify + mode=converse) | `anomaly_detection_service.send_alerts` | `/voice-chat?intent=clarify&alert_id=X` | D |
| `health_alert` (其它) | 同上 | `/trace/anomaly_X` | - |
| `workout_analysis` | `auto_analyze_workout` 跑后 | `/workout-detail?id=X` | W3 |
| `ai_advice` (周聊) | `send_weekly_review_invite` (周日 20:00) | `/voice-chat?intent=weekly` | E |
| `reminder` | reminder schedule | `/reminders` | - |
| `goal_progress` | goal eval | `/goals` | - |

mobile 路由处理: `hooks/useNotifications.ts` `handleNotificationResponse` 优先 `data.deep_link`.

---

## §4 L9 Autonomy Slider — 告警反应档位

`UserNotificationSetting.alert_clarify_mode` ∈ `silent | notify | converse`

| mode | 行为 | 例外 |
|------|------|------|
| silent | 只写 alerts tab 不推送 | critical 强制至少 notify |
| notify | 推送, deep_link 跳 trace 详情 | - |
| converse (默认) | 推送 + voice-chat 主动开口 | - |

UI: `app/notification-settings.tsx` ClarifyModeRow 组件
后端 dispatch: `services/anomaly_detection_service.py` `send_alerts` 里读 `alert_clarify_mode`

---

## §5 L8 写库前确认 (Karpathy "verification is the bottleneck")

`backend/app/services/agent_executor.py` `_exec_health_record` weight 分支:
- 第一次调用 → return `[NEEDS_CONFIRMATION] 我准备记: 体重 X kg ...`
- 第二次调用带 `data.confirmed=true` → 真写 POST /weight/records

**扩展到其它 record_type**: 复制 weight 的 confirmed 检查模式 (blood_pressure / illness / reminder 候选).

**注意**: water / diet / mood / supplement 不需要确认 (噪音容忍高).

---

## §6 Memory 数据流 (D-L6, Karpathy "anterograde amnesia" 解药)

```
用户语音对话
  ↓
voice-chat onClose: extractMemoryFromDialog(turns, alertId)        [mobile/app/voice-chat.tsx]
  ↓
POST /v1/clarification/extract-memory                              [backend/app/api/clarification.py]
  ↓
memory_dialog_extractor.extract_facts_from_dialog(text)            [services/memory_dialog_extractor.py]
  LLM 抽 5 条结构化事实 (subject/predicate/object_value/conf)
  ↓
memory_service.write_fact (自动去重 → reinforce)                    [services/memory_service.py]
  ↓
memory_facts 表
  ↓
下次 build_twin → render_facts_for_prompt → AI 看到这些 fact 更精准
```

### 触达点
- 写: 对话 onClose / specialist findings / action_card_outcome / medical_exam / briefing
- 读: `/ai-profile` / `/memory` 页面
- 删/纠正: ai-profile 左滑 dismiss
- 衰减: `tasks/memory_lifecycle.py` Celery task

---

## §7 私享女声链路

```
mobile speakDirect(text)                     [hooks/useVoiceConversation.ts]
  ↓
cloudTts.synthesize(text, voiceKey)          [services/cloudTts.ts]
  ↓
POST /tts/synthesize                         [backend/app/api/tts.py]
  ↓
cosyvoice.synthesize → DashScope SDK         [backend/app/services/tts/cosyvoice.py]
  voice_id 前缀决定 model:
    cosyvoice-v3.5-plus-bailian-* → cosyvoice-v3.5-plus (复刻)
    longjiayi_v2 等                → cosyvoice-v2 (官方音色)
  ↓
mp3 bytes → mobile expo-audio createAudioPlayer 播
```

**voiceStyle.ts**: STORAGE_KEY = `tts_voice_style_v3`, 默认 `cloud_cloned_private_female` (新用户) / 老用户从 v2 自动迁移.

**iOS Audio Session** (修了音量小 bug):
- 默认 `.playback` (allowsRecording: false) → 外放正常音量
- startListening 切 `.playAndRecord` (allowsRecording: true) → 录音
- stopListening / onSpeechEnd / onSpeechError 切回 `.playback`

---

## §8 改进编号注册表

| 编号 | 名称 | 关键文件 | 状态 |
|------|------|---------|------|
| A | 晨间语音简报 | services/briefing_voice_script.py | ✅ |
| B | Siri "今天怎么样" | mobile/ios/HealthPilot/SiriIntents/HealthPilotSiri.swift TodayBriefingIntent | ✅ build 47 |
| C | 跑后听一下按钮 | api/workout.py voice-coach + services/workout_coach_copy.py | ✅ |
| D | 主动澄清对话 | services/alert_clarification.py + api/clarification.py | ✅ |
| D-L6 | Memory 自动写入 | services/memory_dialog_extractor.py | ✅ |
| L7 | tool schema 加厚 | services/tool_schema_registry.py | ✅ |
| L8 | weight 写前确认 | services/agent_executor.py weight 分支 | ✅ |
| L9 | autonomy slider | models/notification.py alert_clarify_mode + UI | ✅ |
| E | 周聊 | services/weekly_review_voice_script.py + celery 周日 20:00 | ✅ |
| F | 跑前 readiness 对话 | services/preworkout_voice_script.py + record tab 按钮 | ✅ |
| G | 家庭健康 (MVP) | mobile/app/family.tsx + services/family.ts | ✅ 只读 |
| H | 健康事件流 Timeline | api/timeline.py + services/events_timeline_service.py + mobile/app/timeline.tsx | ✅ 独立页 |
| I | 声音笔记 Voice Journal | voice-chat ?intent=journal + record tab 按钮 | ✅ MVP |
| W3 | 跑后教练推送 | tasks/garmin_sync.py auto_analyze_workout | ✅ |

---

## §9 Backlog (按价值排序)

- **G Phase 2**: 家庭邀请流 / 切换视角 / 跨成员告警路由
- **H Phase 2**: Timeline 上主页 (取代部分 dashboard 卡片), 需要先看用户停留时长数据
- **I Phase 2**: 声音笔记结束后 show "已记录" summary card (review 用户接受度)
- **F Phase 2**: Garmin RHR 飙升自动检测 → 主动推 preworkout
- **L8 扩展**: 把"先确认"模式扩到 blood_pressure / illness / reminder
- **proximity 自动听筒**: 写 native module 实现贴脸切听筒 (expo-audio 当前不支持)
- **medication 高级**: 手动添加药物 UI (目前只能对话添加)

---

## §10 设计原则 (Karpathy Software 3.0)

1. **Mobile First**: 锁屏可读 + 一键听 + 一键回话
2. **Agent Native**:
   - LLM 有 anterograde amnesia → 必须写 Memory (D-L6)
   - LLM 容易 jagged → 必须 verification (L8 weight 确认)
   - 不要全自动 → 必须 autonomy slider (L9)
   - 为 agent 设计文档 (L7 tool schema 加厚)
3. **复用 voice-chat 单入口**: 任何"AI 主动找用户"都走 `?intent=*`
4. **私享女声为差异化锚点**: cosyvoice-v3.5-plus 复刻
5. **数据闭环**: 推送 → 对话 → Memory → 下次更准

---

## §11 build / OTA 发布速查

```bash
# 后端
bash deploy.sh -b                            # 后端部署 (executor.life)

# Mobile OTA (preview channel)
cd mobile && eas update --branch preview --environment preview \
  --message "..." --non-interactive

# Mobile native build (需要改 native module / Siri 才用)
cd mobile && eas build --platform ios --profile production --auto-submit \
  --non-interactive --message "build N: ..."
```

OTA 能下: pure JS/TS 改动, 包括 Siri 之外的 mobile 业务.
build 必须发: native iOS 改动 (Siri Intent / AVAudioSession 原生层 / expo-audio 升级).

---

## §12 当前已知 bug / 限制

- expo-audio 不支持 proximity / .defaultToSpeaker → 贴耳听筒还做不到
- LLM 偶尔把 weight 放在顶层 args (已加 L8 兜底 + L7 schema 提示)
- voice-chat onSpeechEnd iOS 慢 2-3s → 已用 silenceTimer 1.2s 解决
- TTS estMs 必须比真实播放长, 否则段落重叠 (已 fix: text.length * 280 + 8s)
