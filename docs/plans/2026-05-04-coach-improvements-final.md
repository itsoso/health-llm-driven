# 健康助理 5 项优化 — 最终规划

> **2026-05-04 写就**. 综合三份调研 (my plan / CLI-B / CLI-C) 后的融合版.
> 决策人: itsoso. 执行人: Claude + itsoso.
>
> **原始 4 条需求 + 自生 1 条**:
> 1. TTS 语音可以选择 "林志玲"
> 2. 跑步详情一键分享微信 + 美化
> 3. 跑步中根据心率步频实时指导
> 4. voice-chat 页 markdown 渲染
> 5. **(CLI-C 加) Garmin 数据深度解读** — 经 itsoso 确认要做

---

## 0. 一句话总定位

> **"Garmin 记录, 我们当教练"** — 把 Garmin 8 天/周的数据用得比 Garmin 自己还好; 跑中有陪伴有保护, 跑后有决策.

三件事: **看得懂 (MD渲染+数据解读) → 愿意晒 (分享美化) → 跑得安全 (实时指导)**.

---

## 1. 关键决策 (已定)

| 决策 | 选择 | 理由 |
|---|---|---|
| TTS "林志玲" 字面 | ❌ 不做, UI 用"温柔知性女声" | 民法典 1023 条 + App Store 5.2.1 |
| TTS 首版 | iOS 内置 `Mei-Jia-compact` (台湾普通话女) + 语音风格库 | 0 成本 0 风险覆盖 80% 需求 |
| Cloud TTS | 留作 v2 升级 | 等用户反馈 "系统音还不够温柔" 再做 |
| 微信分享 | 先 `expo-sharing` 截图系统分享 | 不要企业资质, 不 prebuild, Expo 托管流不破 |
| 微信原生 SDK | v2 再做 | 企业开放平台资质 + eas build, 暂缓 |
| 跑步实时指导 | HealthKit live HR MVP, 默认 "标准教练" 模式 | Garmin API 硬约束实时流, Apple Watch/iPhone HealthKit 是唯一实时路径 |
| Garmin 实时方案 (Connect IQ / BLE 广播) | ❌ 暂不做 | Monkey C 投入大, BLE 广播依赖用户手动开 |
| **#5 Garmin 深度解读** | ✅ 做 (W4-5) | itsoso 确认, 绕开实时流硬约束, 差异化硬核 |
| 分享隐私 | **给用户可选项**, 默认模糊前后 200m, 可关 | 家庭住址泄露风险, 但不一刀切 |
| 实时指导 L1/L2/L3 分级 | 默认 "标准教练", 加静默/比赛/教练三档可选 | 怕语音唠叨, 也不能默认静默 (那就白做了) |
| 跑步中后台 audio session | 走 iOS `UIBackgroundModes: audio` + AVAudioSession | 1h+ 跑步 TTS 持续播报必须 |
| 跑者分层 | 用户首次设置: 初跑者 / 进阶 / 精英 | 决定 KPI (Z2 vs 心率漂移 vs TSS) |

---

## 2. 总排期 (6 周单兵 + OTA 节奏)

单兵开发不按 Sprint, 按 "周内 ship 小件, 月级 ship 大件". 每周末一次 OTA, 每 2-3 周一次 EAS Build (有 native 改动时).

| 周 | 主攻 | 可 ship 件 | 构建类型 |
|---|---|---|---|
| **W1** | #4 MD渲染 + #1A 台腔女声 | voice-chat 渲染修好, 设置页加"语音风格" | OTA (纯 JS) |
| **W2** | #2 Phase 1 截图分享 + 美化 | workout-detail Hero 卡 + 路径色彩 + 分享海报 | OTA |
| **W3** | #3 过渡: 跑后教练推送 + 合规免责声明 | 跑后 Garmin 同步触发 specialist 推送决策 | 后端 + OTA |
| **W4** | #5 Garmin 深度解读 V1 — CTL/ATL/TSB/ACWR | 运动分析页加训练负荷卡 | 后端 + OTA |
| **W5** | #5 V2 — rTSS + 心率漂移率 + 个性化 LT (Dmax 估算) | 详情页 + weekly 报告补强 | 后端 + OTA |
| **W6** | #3 实时指导 MVP | HealthKit live HR + Karvonen + 三级提醒 + 模式切换 | **EAS Build** (HealthKit entitlement) |

**W1-W3 共 3 次 OTA**, **W4-W5 再 2 次 OTA**, **W6 一次 EAS Build**. 可独立砍尾: W3 见效后可暂停推进 W4 而先观察.

---

## 3. 分项详细方案

### #4 voice-chat Markdown 渲染 (W1, 0.5 天)

**定位**: bug, 不是 feature.

**改动**:
- `mobile/app/voice-chat.tsx:108` — `<Text>{t.text}</Text>` 替换为 assistant 走 `<Markdown style={createMdStylesChat(c)}>`, user 仍走 `<Text>` (白字 on brand bg)
- `mobile/hooks/useVoiceConversation.ts:61` — `enqueueSentences` 之前加 `stripMarkdown(chunk)`:
  ```ts
  function stripMarkdown(s: string): string {
    return s.replace(/\*\*/g, '')
      .replace(/^#+\s*/gm, '')
      .replace(/^[-*]\s+/gm, '')
      .replace(/^\d+\.\s+/gm, '')
      .replace(/`/g, '')
      .replace(/\|/g, ' ');
  }
  ```
  不然 TTS 会把 `**加粗**` 念成"星星加粗星星".

**验收**: 发一句带 `**粗体** # 标题 - 列表` 的测试, voice-chat 气泡渲染正确 + TTS 念出来干净.

---

### #1 TTS 音色选择 — 台腔女声 + 风格库 (W1, 0.5 天)

**范围**: MVP 只上 iOS 内置, 不上 cloud.

**UI**: Settings 加 "语音风格" 行, 单选:
- **温柔台腔** (Mei-Jia, rate 0.95, pitch 1.05) — 默认
- **标准普通话** (Tingting, rate 1.0, pitch 1.0)
- **iOS 系统默认** — 不指定 voice

存 `AsyncStorage` key `tts_voice_style`.

**改动**:
- `mobile/hooks/useVoiceConversation.ts:53` — `Speech.speak` 读 `AsyncStorage`, 映射:
  ```ts
  const voiceMap = {
    gentle_tw: { voice: 'com.apple.ttsbundle.Mei-Jia-compact', language: 'zh-TW', rate: 0.95, pitch: 1.05 },
    standard_cn: { voice: 'com.apple.ttsbundle.Tingting-compact', language: 'zh-CN', rate: 1.0, pitch: 1.0 },
    system: { language: 'zh-CN', rate: 1.0, pitch: 1.0 },
  };
  ```
- 新建 `mobile/app/settings/voice-style.tsx` 选项页 + Settings 入口行
- 启动时用 `Speech.getAvailableVoicesAsync()` 校验 Mei-Jia 存在, 不存在降级到 system

**红线**:
- UI label 不得出现 "林志玲" / "志玲" / "明星" / 具体艺人名
- App Store 描述也不得暗示"林志玲同款"

**v2 路径 (暂不做)**: 后端 `POST /api/v1/tts/synthesize` 代理 MiniMax / 阿里云, 返回 mp3 流, mobile 用 `expo-av` 播放.

---

### #2 跑步分享 + 美化 (W2, 4-5 天)

**Phase 1 (本周)**: `expo-sharing` 截图分享. **Phase 2 (v2)**: `react-native-wechat-lib`, 暂缓.

#### 2.1 workout-detail 美化 (3 天)

当前 `mobile/app/workout-detail.tsx` 352 行, 改造:

| 区块 | 当前 | 改后 |
|---|---|---|
| 顶部 Hero | 无 | 大字距离 + 配速 + 时长, brand 渐变背景 |
| 心率 | avg_heart_rate 单值 | 心率曲线图 (victory-native `VictoryLine`), 标 HR zone 横线 |
| 配速 | 无 | 公里分段配速柱状图 (可选: 标 LT 阈值线) |
| 轨迹 | 单色 polyline | 速度渐变 polyline (绿快红慢), 起终点标 icon |
| AI 分析 | 流水 markdown | 保持 markdown + emoji + tag chip (已有基本够用) |
| 右上角 | 无 | Share icon button |

**依赖**:
- `victory-native` 或 `react-native-svg-charts` (二选一, 看 bundle size)
- Garmin `workout.heart_rate_samples` + `pace_samples` 时序数据 — **前提: 后端 API 必须返回**. 查 `backend/app/api/workout.py` 是否已有; 若无, 需补. 预估 +0.5 天

#### 2.2 截图分享 (1 天)

- 新增 `mobile/components/workout/ShareCard.tsx` — 独立竖版海报 View (9:16, 1080×1920):
  - 顶部: 用户头像 + 日期 + "健康助理" 品牌 watermark
  - 中部: 轨迹图 (可模糊起终点) + 核心数据 4 格大字
  - 底部: AI 精选 highlight 1-2 句 (取 post_analysis 首句)
- `react-native-view-shot` `captureRef(shareCardRef, { format: 'png', result: 'tmpfile' })` → 得到 uri
- `expo-sharing.shareAsync(uri, { mimeType: 'image/png', dialogTitle: '分享' })` → 拉起系统分享面板
- 用户在面板里选"微信" 发出

#### 2.3 隐私选项 (0.5 天)

Settings 加 "运动分享隐私":
- **模糊起点/终点 200m** (默认 ✅) — 截图时 polyline 头尾各切掉前后最近的几个点直到覆盖距离 ≥ 200m
- **隐藏具体心率数值** (默认 ❌)
- **隐藏昵称, 改为"跑者"** (默认 ❌)

存 `AsyncStorage` key `share_privacy_*`, ShareCard 渲染时读.

**验收**:
- 点击右上角 share → 2s 内弹出系统分享面板, 内含一张竖版海报
- 默认模糊起终点确实裁切了轨迹
- 分享到微信, 微信内图片显示正常

---

### #3 过渡: 跑后教练推送 (W3, 1-2 天)

**做这个是因为**: 实时指导 W6 才 ship, 先用 "跑完立刻给建议" 补位.

**链路**:
```
Garmin 同步 workout 入库 → Celery task trigger → MovementCoach + SafetyGuardian run →
  生成 next-step advice → 入 notification queue → APNs push
```

**改动**:
- `backend/app/tasks/garmin_sync.py` — workout insert 后触发 `evaluate_post_workout_advice(user_id, workout_id)` Celery task
- `backend/app/services/post_workout_advisor.py` (新) — 产出结构化 advice:
  ```python
  {
    "type": "post_workout_advice",
    "title": "今天 5km 配速 5'30\"",
    "body": "心率冲到 175 (max 92%) 略高 — 明天休 1 天, 后天慢跑 30min",
    "deep_link": "mobile://workout-detail?id=123"
  }
  ```
- 规则引擎 (类比 Safety Guardian 模式): HR > 90% max 持续 >10% 时长 → 休息建议; TRIMP 超周均 150% → 减量; 短跑距 & 高 HR → 间歇没跑透等
- `backend/app/services/notification/push_service.py` — 新类型 push, dedup 2h
- **合规红线 (必须)**:
  - ❌ "你心律失常" / "你血压高"
  - ✅ "心率较高, 建议降低强度; 如胸闷头晕请就医"
  - 首次推送前弹一次免责声明: "本建议仅用于运动健康管理, 不作为医疗诊断"

**验收**: 跑步完 Garmin 同步完成后 5 分钟内收到一条结构化推送.

---

### #5 Garmin 数据深度解读 (W4-5, 5-6 天)

**不抢 Garmin 实时流, 把它的历史数据用得比它自己更好**.

#### W4 (3 天): V1 — 训练负荷透明化

**核心指标** (体育科学标准):
- **TSS** (Training Stress Score): 单次训练负荷. 跑步用 **rTSS** = (duration_sec × NGP / FTP) × IF²
- **CTL** (Chronic Training Load): 42 天指数加权 TSS 均值 → "体能"
- **ATL** (Acute Training Load): 7 天指数加权 TSS 均值 → "疲劳"
- **TSB** (Training Stress Balance) = CTL − ATL → "状态" (+ 休整, − 疲劳)
- **ACWR** (Acute:Chronic Workload Ratio) = ATL / CTL → 伤病风险 (0.8-1.3 最佳, >1.5 预警)

**实现**:
- `backend/app/services/training_load/` (新) — 纯函数计算模块
  - `compute_tss(workout)` — 跑步优先 rTSS, 其他运动回退通用 TSS
  - `compute_ctl_atl(user_id, date)` — 取前 42 天每日 TSS, 指数加权
  - `compute_acwr(user_id, date)`
- `backend/app/api/training_load.py` (新) — `GET /api/v1/training-load/me?days=90` → 每日 CTL/ATL/TSB/ACWR 时序
- Mobile 新 tab 或进运动详情加"训练负荷"卡:
  - CTL/ATL/TSB 三条线叠加图 (victory-native)
  - 今日 ACWR 值 + 颜色 (绿 0.8-1.3, 黄 0.5-0.8 或 1.3-1.5, 红 >1.5 或 <0.5)

**数据依赖**:
- 需要 HRmax, HRrest, FTP (跑步功能阈值配速 = LT 附近配速)
- 首版: HRmax = 220 − age, HRrest = 近 30d Garmin 静息心率中位数, FTP = 近 90d tempo+threshold 配速中位数 * 0.95 (粗估)
- W5 再做 Dmax 精算

#### W5 (2-3 天): V2 — rTSS NGP + 心率漂移率 + 个性化 LT

- **NGP** (Normalized Graded Pace): 按 `workout.route_data` 海拔坡度标准化配速, rTSS 更准
- **心率漂移率** (HR Drift): 下半段平均 HR / 上半段平均 HR, >5% 说明强度撑不住 / 脱水 / 体能不足
- **Dmax LT 估算**: 用近 3 月配速-心率散点, 在 HR 对 pace 曲线上找距 (最低点, 最高点) 连线最远的点 → 个性化 LT (比起 220-age 准多了)

**输出**:
- 运动详情页 "训练诊断" 板块: 本次 rTSS / 心率漂移 / LT 区间累计时长
- Weekly 报告 (若有) 补 "本周 CTL 变化 +3, 状态从疲劳转休整" 类叙事

**验收**:
- `GET /training-load/me` 返回合理时序, CTL/ATL/TSB 三者满足 CTL > ATL 时 TSB > 0 等数学恒等式
- 详情页训练负荷卡点进去能看懂
- 跑完一次后 ACWR 值变化可感

---

### #3 实时指导 MVP (W6, 5-7 天) — 本轮压轴

**前置条件**:
- Apple Watch 或 iPhone 健身 App 用户 (Garmin 用户本周不覆盖)
- iOS 本机 HealthKit 读 live HR 权限

#### 3.1 数据源

**HealthKit live workout** (`HKWorkoutSession` 间接):
- 用户用 iPhone Fitness App 或第三方 workout App (e.g. Nike Run Club) 启动跑步 → HealthKit 开始记录
- 我们 App 用 `HKAnchoredObjectQuery` 订阅 `HKQuantityTypeIdentifierHeartRate`, 每收到新 sample 触发指导逻辑
- **不自己开 workout session** — 避免双开与 Fitness App 冲突

**步频**: `CMPedometer.startPedometerUpdates` 实时 cadence

**配速**: `expo-location` `watchPositionAsync` 每 5s 一次

**依赖**:
- `react-native-health` (成熟 HealthKit wrapper)
- 加 `NSHealthShareUsageDescription` 到 `app.json` ios.infoPlist
- `UIBackgroundModes: ['audio', 'location']` — 让后台持续播报 + GPS

#### 3.2 指导逻辑

**跑前**: 用户选训练目标 (决定阈值):
- 轻松跑 (Z2 下限-上限)
- 减脂 (Z2-Z3 下限)
- 心肺提升 (Z3-Z4)
- 间歇 (Z4-Z5, 允许飙升)
- 长距离 (Z2, 不容漂移)

**Karvonen 储备心率**:
```
目标 HR = (HRmax − HRrest) × intensity% + HRrest
```
HRmax / HRrest 从 #5 的用户 profile 取.

**触发条件 (带防抖)**:
| 条件 | 持续 | 冷却 | 级别 | 话术模板 |
|---|---|---|---|---|
| HR 超目标上限 +5bpm | 45s | 3min | L2 | "心率偏高, 已超轻松跑区间 2 分钟, 建议降低 10-15s 配速" |
| HR 低于目标下限 -5bpm | 60s | 3min | L2 | "心率偏低, 如果是减脂目标建议加速" |
| HR 骤升 >15bpm/30s (非爬坡) | 即时 | 1min | L3 | "心率骤升, 请检查是否不适; 必要时减速" |
| HR > 95% HRmax | 30s | 无 | L3 | "心率已到极限区, 立即减速; 如胸闷头晕立即停止" |
| 步频 < 160 (初跑者) / <170 (进阶) | 2km | 5min | L1 | "步频偏低, 试试小步高频" |
| 公里配速偏离目标 ±15s | 1km | 2min | L1 | "本公里配速 X, 目标 Y, 微调" |

**话术三要素** (现状 + 计划偏离 + 具体动作):
```
❌ "您的心率是 168"
✅ "已进入 Z4 2 分钟, 超出轻松跑目标, 降低 10-15 秒配速"
```

#### 3.3 三模式切换

设置页 "教练模式":
- **标准教练** (默认) — L1 静默/震动, L2 语音, L3 语音+震动
- **静默** — L1/L2 只改屏幕颜色 + 震动, L3 语音+震动
- **比赛** — 全静默, 仅 L3
- **教练模式+** — L1 轻提示语音, 更高频

#### 3.4 合规

- 首次使用弹免责声明
- 心率/位置属敏感个人信息, 单独授权, 支持撤回
- 不出现 "心律失常" / "高血压" 等医疗化字样
- 连续发现 HR > 95% 不降 / 骤升不稳 → 提示"请考虑中止运动"但不报警 120

#### 3.5 UI (精简)

跑步中屏幕:
- 大字当前心率 + HR zone 颜色
- 小字步频 + 当前配速 + 已用时长
- 底部最新指导文本 (TTS 念出来同时显示)
- 长按屏幕暂停播报

**验收**:
- 用户用 iPhone Fitness 启动跑步, 我们 App 切后台, 1 分钟内收到第一条播报
- 心率超阈值 45s 触发 L2 播报
- 切静默模式, L2 不播报只变色
- 1h 跑完后 App 未被系统杀, 全程播报正常

---

## 4. 架构影响

### 后端新增模块
```
backend/app/services/training_load/        # #5 纯函数
  ├── rtss.py
  ├── ctl_atl.py
  ├── acwr.py
  └── lt_dmax.py
backend/app/services/post_workout_advisor.py  # #3 过渡
backend/app/api/training_load.py              # #5 API
backend/app/api/coaching.py                   # #3 实时 (如果需要 server-side 规则)
```

W6 实时指导**优先纯 mobile 本地规则**, 暂不新增后端 coaching API — 除非 prompt 生成需要 LLM, 那再接 `/orchestrator/chat` 轻量端点.

### Mobile 新增
```
mobile/app/settings/voice-style.tsx       # #1
mobile/app/settings/share-privacy.tsx     # #2
mobile/app/settings/coach-mode.tsx        # #3
mobile/app/running-live.tsx               # #3 实时页
mobile/components/workout/ShareCard.tsx   # #2
mobile/components/workout/HeroMetrics.tsx # #2
mobile/components/workout/HrChart.tsx     # #2
mobile/components/workout/PaceBars.tsx    # #2
mobile/components/training-load/          # #5 CTL/ATL/TSB 图
mobile/services/healthKit.ts              # #3
mobile/services/trainingLoad.ts           # #5
mobile/hooks/useLiveWorkout.ts            # #3
```

### 数据库
- **#5 不新表**. CTL/ATL/TSB 按需实时计算, 或 Celery daily job 预算后写 `user_training_load_daily` (user_id, date, tss, ctl, atl, tsb, acwr) — 二选一. 首版用实时计算, 量大了再预算.

### Celery
- `post_workout_advisor_task` — W3, workout insert 触发
- (可选) `compute_training_load_daily_task` — W4+, 如选预算方案

---

## 5. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Mei-Jia 在部分老 iOS 设备不存在 | TTS 回退 system default | `getAvailableVoicesAsync` 启动校验, 降级 + 告警 |
| expo-sharing 在国内微信分享成功但无法精准发朋友圈 | 用户需多一步操作 | 接受; 后续做 Phase 2 SDK |
| iOS 后台 audio session 跑步 1h+ 被系统杀 | #3 核心体验挂 | 充分测试; 配 `UIBackgroundModes: ['audio', 'location']` + 长声明 + 保持 location updates 活 |
| HealthKit live HR 延迟 (samples 每 5-10s 一次, 不是真 1Hz) | 防抖窗口可能要调 | 实测后调整 45s 阈值 |
| 跑步中语音打断用户听歌 → 卸载 | 体验灾难 | 默认标准模式 + 显眼入口到"静默"模式 + 首次引导 |
| ACWR / CTL 算错 → 给错建议 → 用户受伤 | 合规+信任双毁 | W4 写 `tests/test_training_load.py` 覆盖至少 5 组业界公认算例 |
| 分享海报泄露住址 | 隐私事故 | 默认开起终点模糊 200m |
| Karvonen 需要 HRrest, 首次用户没 Garmin 数据 | 算法跑不起来 | 降级 220-age max + 60 rest 缺省值, 提示用户补数据 |

---

## 6. 不做清单

| ❌ | 原因 |
|---|---|
| "林志玲" 字面 UI/宣传 | 声音权 + App Store 挂 |
| AI 克隆明星声音 | 违法 |
| Garmin Connect IQ 伴侣 App (Monkey C) | 工时 25 天, 用户基数小, 不值 |
| 微信原生 SDK (本轮) | 企业资质 + prebuild, 先看 Phase 1 数据 |
| Cloud TTS (MiniMax/Azure) (本轮) | 先看 Mei-Jia 够不够, 不够再升 |
| Apple Watch 配套 App (本轮) | 另一个平台, 单兵 6 周塞不下 |
| 实时跑步医疗化判断 (心律失常/血压风险) | 合规红线 |
| 跑步 AI 计划 (自动排周训练) | v3 方向, 当前基础不够 |
| BLE 心率带接入 | W6 后如用户反馈需要再加 |
| Android | 本项目移动端只做 iOS |

---

## 7. 触发点 & 反馈闭环

**W3 完成后**检查:
- 用户收到跑后推送的互动率 (打开率 / deep link 点击率) — 低于 20% 说明推送价值不够, 调整话术或延缓 W6

**W5 完成后**检查:
- 训练负荷卡的打开率 — 低于 15% 说明用户不看这些数据, W6 实时指导价值存疑

**W6 完成后** 2 周访谈 (N≥3, itsoso 自己 + 至少 2 个身边健身朋友):
- "教练模式"用了多少次? 关了没?
- 静默模式会不会被开启?
- "林志玲" 真需求还在吗? 还是台腔女声够了?

按反馈决定:
- Cloud TTS 要不要做 (若反馈 "台腔女声不够好")
- 微信原生 SDK 要不要做 (若 Phase 1 分享数据 >30% 用户分享过)
- Apple Watch App 要不要做 (若 "iPhone 在裤兜看不到屏幕" 被反复提)

---

## 8. 合规与红线 (跨需求)

| 红线 | 落地 |
|---|---|
| 不得出现医疗诊断性语言 | specialist prompt + 本地规则双拦截, 加自动化测试 |
| TTS 明星声不得使用/暗示 | UI / App Store 描述 / 文案 review |
| 首次使用健康指导前弹免责声明 | `mobile/app/disclaimer-modal.tsx` 一次性确认, 存 AsyncStorage |
| 心率/位置数据单独授权, 支持撤回 | Settings 页加 "撤回授权" + Apple 系统授权指引链接 |
| 默认不把运动数据用于广告画像 | 本项目本就无广告, 文案写死 |
| 分享默认模糊起终点 | ShareCard 默认开, 可关 |

---

## 9. 修订日志

- **2026-05-04 18:10** 写就. 融合 my plan (首轮) + CLI-B (对方擅长的产品批判) + CLI-C (擅长的运动科学指标). 决策人 itsoso 同意 #5 要做, 隐私可选项, 实时指导默认标准教练模式.
- 核心判断: **"Garmin 记录, 我们当教练"**, W1-W3 先修硬伤 + 补位, W4-W5 建差异化壁垒, W6 上实时指导 MVP.

---

## 10. 下一步

等 itsoso 确认本文件后, 从 **W1 / #4 voice-chat Markdown 渲染** 开始动手, 这是最小且最确定的第一块.
