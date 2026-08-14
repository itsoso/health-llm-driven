# mobile/PRODUCT_MAP.md — 给代码 Agent 用的产品地图

> **本文档优先于代码探索**: 改 mobile 任何功能前先 grep 这里, 减少试错.
> 维护规则: 加 page / intent / push / 改进编号 必须在本文档登记.

## ⚡ 最快速查找

| 我想... | 看哪 |
|---|---|
| 加一个 voice-chat 触发场景 | §2 voice-chat intent SOP |
| 加一种推送类型 | §3 push registry |
| 改 push 点击跳转 | `mobile/hooks/useNotifications.ts` `handleNotificationResponse` |
| 加 dashboard 卡片 | `mobile/components/dashboard/HomeHeader.tsx`, `components/dashboard/TodayPlanPanel.tsx`, `components/dashboard/TrajectorySnapshotPanel.tsx` 或 `app/(tabs)/index.tsx` |
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
  (tabs)/index.tsx            主页 dashboard, Today Plan, 内嵌 chat 流
  (tabs)/chat.tsx             小巴健康参谋文字对话; header 含历史、语音、新建、删除入口
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
  chat.ts                     streamChat SSE 处理 (start/token/tool/done/error); start 提前携带 conversationId 供切页恢复
  dailyPlan.ts                ⭐ Daily Operating Plan 首页行动计划
  trajectory.ts               ⭐ Personal Health Trajectory Snapshot
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

mobile/components/chat/
  ConversationSheet.tsx       小巴对话历史 bottom sheet; 按简报/周报置顶, 选择后 loadConversation

mobile/components/
  dashboard/HomeHeader.tsx    主页 hero 卡片
  dashboard/TodayPlanPanel.tsx ⭐ 今日操作计划, 代谢健康 action 入口
  dashboard/TrajectorySnapshotPanel.tsx ⭐ 疾病上游健康轨迹入口
  workout/HrChart.tsx / PaceBars.tsx / HrZoneBar.tsx / HeroMetrics.tsx
  design-system/HealthCard.tsx
  chat/OpenerCard.tsx
  ...

backend/app/
  api/briefing.py             ⭐ 所有 voice-chat intent 后端短稿端点
  api/clarification.py        D 改进 (opener + extract-memory)
  api/workout.py              workout/me/{id}/voice-coach (听一下)
  api/family.py               家庭 CRUD + dashboard
  api/daily_plan.py           ⭐ GET /daily-plan/me 每日操作计划
  api/trajectory.py           ⭐ GET /trajectory/me 健康轨迹快照
  api/waist.py                ⭐ 腰围记录 CRUD + latest + stats
  api/notification.py         settings GET/PUT
  api/tts.py                  POST /tts/synthesize
  services/briefing_voice_script.py     A 晨间
  services/weekly_review_voice_script.py E 周聊
  services/preworkout_voice_script.py   F 跑前
  services/alert_clarification.py       D 告警澄清
  services/memory_dialog_extractor.py   D-L6 抽 fact
  services/memory_service.py            write_fact (去重/reinforce)
  services/agent_executor.py            ⭐ tool 执行 + L8 weight 确认
  services/daily_operating_plan.py      ⭐ Twin → 今日可执行计划
  services/health_trajectory.py         ⭐ Twin + genes + methylation gap → 轨迹快照
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
  models/waist.py                       waist_records
  models/daily_operating_plan.py        daily_operating_plans
  celery_app.py                         ⭐ beat_schedule (周日 20:00 加这里)
```

### §1.1 Today Plan / Daily Operating Plan 流

```
mobile/app/(tabs)/index.tsx
  ↓ React Query ['daily-plan','me']
mobile/services/dailyPlan.ts
  ↓ GET /api/v1/daily-plan/me
backend/app/api/daily_plan.py
  ↓
backend/app/services/daily_operating_plan.py
  ↓ build_twin(force_refresh=True)
backend/app/twin/builder.py + _collectors.fetch_waist_latest
  ↓
Postgres: daily_operating_plans / waist_records / weight / blood_pressure / Garmin
```

Daily Plan action 契约:

| field | 含义 |
|---|---|
| `evidence_tier` | `clinical_guideline` / `strong_behavioral` / `wearable_proxy` / `genetic_association` / `experimental` |
| `confidence` | `high` / `medium` / `low` |
| `claim_boundary` | 显式声明不替代医生诊断、处方或治疗, 并说明该行动不能推断什么 |

### §1.2 Trajectory Snapshot 流

```
mobile/app/(tabs)/index.tsx
  ↓ React Query ['trajectory','me']
mobile/services/trajectory.ts
  ↓ GET /api/v1/trajectory/me
backend/app/api/trajectory.py
  ↓
backend/app/services/health_trajectory.py
  ↓ build_twin + build_daily_operating_plan
Postgres: genetic_variants / waist_records / weight / blood_pressure / labs / Garmin
```

Trajectory Snapshot 只做疾病上游轨迹识别和优先级排序, 不做诊断。三个首期 domain:

| domain | 含义 | 当前数据 |
|---|---|---|
| `metabolic_health` | 代谢健康轨迹 | 腰围/BMI/BP/血糖血脂/疾病风险基因 |
| `recovery_capacity` | 恢复能力轨迹 | 睡眠/HRV/readiness/恢复敏感基因 |
| `aging_pace` | 衰老速度轨迹 | 甲基化暂为 data gap, 后续接入长期反馈 |

每条 `trajectory_risks[]` 必须带 `evidence_tier/confidence/claim_boundary`。甲基化相关字段当前固定为 `experimental/low`, 只作为长期代理指标和 data gap, 不能作为“个体短期抗衰有效”的承诺。

UI 路由规则在 `openPlanAction`:

| action domain | 跳转 |
|---|---|
| `nutrition` | `/diet-plan` |
| `movement` | `/movement-plan` |
| `sleep` | `/sleep` |
| `measurement` | `/record` |
| `source_card_id` | `/card/[id]` |
| fallback | 首页 chat |

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

**聊天气泡朗读**: `components/chat/ChatBubble.tsx` 右下角 `语音播报` 走 `services/speakWithUserVoice.ts`, 按用户在语音风格页选择的 provider 播放。cloud provider 会先用 `utils/ttsText.ts` 把长回复切成 <=480 字分段, 再串行调用云端 CosyVoice, 避免后端 500 字限制触发 422 后退回 iOS 系统音色。点击前会把 audio session 切回 `.playback`, 启动失败会恢复按钮状态, 且有时长兜底防止系统回调丢失后一直卡在“停止播报”。

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
| J | Daily Operating Plan | api/daily_plan.py + services/daily_operating_plan.py + TodayPlanPanel | ✅ Phase 0 |
| J-AdviceLedger | 建议一致性账本 | models/advice_ledger.py + services/advice_guard.py + daily_plan/push_service 接入 | ✅ Phase 1 |
| J-Waist | 腰围代谢指标 | api/waist.py + twin/_collectors.fetch_waist_latest | ✅ Phase 0 |
| J-BodyEntry | 体重腰围一屏录入 | mobile/app/body-measurements.tsx + services/bodyMeasurements.ts | ✅ Phase 1 |
| K | Personal Health Trajectory Snapshot | api/trajectory.py + services/health_trajectory.py + TrajectorySnapshotPanel | ✅ Phase 0 |
| K-Guardrail | 科学边界契约 | trajectory risks + daily actions 的 evidence_tier/confidence/claim_boundary | ✅ Phase 1 |

---

## §9 Backlog (按价值排序)

- **G Phase 2**: 家庭邀请流 / 切换视角 / 跨成员告警路由
- **H Phase 2**: Timeline 上主页 (取代部分 dashboard 卡片), 需要先看用户停留时长数据
- **I Phase 2**: 声音笔记结束后 show "已记录" summary card (review 用户接受度)
- **F Phase 2**: Garmin RHR 飙升自动检测 → 主动推 preworkout
- **L8 扩展**: 把"先确认"模式扩到 blood_pressure / illness / reminder
- **J Phase 2**: Today Plan action completion 写回 outcome; native build 接 HealthKit / Health Connect 自动同步 body measurements
- **K Phase 1**: methylation report model/import/parser, 将甲基化年龄/衰老速度写入 trajectory `epigenetic_feedback`
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

## §11 本地 build / release 只读速查

```bash
# 只读 release routing / validation
./scripts/release.sh plan --base <observed-baseline> --target origin/main
./scripts/release.sh validate --base <observed-baseline> --target origin/main

# Existing IPA -> offline metadata/report only; no install manifest/QR or archive/signing
./scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>
```

Mobile 反馈只用本地 Metro、iOS Simulator 和测试。`npm run ios` 固定走 Simulator
wrapper，不得向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator UDID，
物理 iOS repo CLI、连接/安装/验收冻结。bare
`--no-upload` 会触发 archive/export，故同样冻结；禁止自动 signing/provisioning、
`mobile-fast-device.sh`、`mobile-local-device.sh` 与 `-allowProvisioningUpdates`。EAS
channel→branch mapping 可能漂移或共用，不能证明 preview/development 不触达 production；
因此所有 OTA/rollback channel、server production、production native/EAS/ASC、Mac writer
与历史旁路全部 exit 78。任何 Mobile 发布请求进入 manual Gate 后记录 BLOCK，而不是转
direct CLI。
Android 尚非 shipped/audited Mobile surface；`npm run android`/`expo run:android` 会自动
native generation、debug signing 与 ADB install，因此 repo entry earliest exit 78，无
Android native CLI 例外。
标准 `production` 不包含 Watch；Watch 使用独立 `watch-production` profile 和独立
dossier/Gate。未来重新启用后，原生入口也只创建候选，build selection、TestFlight
验收与 App Review submission 不得合并成一步；远端响应不明时按原交易唯一证据恢复，
禁止盲重跑。

冻结根因是 same-UID writable repo 可通过 Git replace、info attributes+filter、隐藏
untracked import、`BASH_ENV`、`PYTHONPATH`/`sitecustomize` 越过 repo 内 guard。解冻需
repo-external root-owned launcher（fixed interpreter、`env -i`、canonical archive/tree
仓库外 materialization）+ 新 dossier/独立 G4。当前 G5/G6/App Store submission 均 BLOCK。

---

## §12 当前已知 bug / 限制

- expo-audio 不支持 proximity / .defaultToSpeaker → 贴耳听筒还做不到
- LLM 偶尔把 weight 放在顶层 args (已加 L8 兜底 + L7 schema 提示)
- voice-chat onSpeechEnd iOS 慢 2-3s → 已用 silenceTimer 1.2s 解决
- TTS estMs 必须比真实播放长, 否则段落重叠 (已 fix: text.length * 280 + 8s)
