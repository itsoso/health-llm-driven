# 健康助理 4 条优化点 — 需求分析 + 规划

> **2026-05-04 写就**. 待与另一个 CLI 的输出做对比 + 综合分析.
>
> 用户原始需求 (4 条):
>
> 1. TTS 语音可以选择林志玲
> 2. 跑步详情页面可以一键分享到微信，且美化
> 3. 增加跑步中根据心率步频实时指导的能力
> 4. TTS 语音文字显示页面是 markdown，需要渲染为容易人类阅读的格式

---

## 0. 一句话总结

| # | 需求字面 | 真实需求拆解 | 我的判断 |
|---|---|---|---|
| **1** | TTS 选林志玲 | "我希望 voice 是温柔有亲和力的女声" | **不能直接做** (肖像权红线), 改为"语音风格库 + 温柔台湾女声" |
| **2** | 跑步页分享 + 美化 | "我跑完了想发朋友圈炫耀, 现在没法分享" | **直接做**, 但"美化"要量化为分享卡设计 |
| **3** | 跑步中实时指导 | "我希望 App 是教练不是日记本" | **产品方向决策**, 不是单纯加功能, 需要先确定场景 |
| **4** | markdown 渲染 | "voice-chat 看到的是裸 markdown, 不好看" | **直接做**, 是 bug 不是 enhancement, 0.5 天 |

---

## 1. 需求 1: TTS 选择林志玲

### 1.1 现状

- 当前 TTS 实现: `expo-speech` (`mobile/hooks/useVoiceConversation.ts:53`)
  ```typescript
  Speech.speak(text, { language: 'zh-CN', rate: 1.0, pitch: 1.0, ... })
  ```
- expo-speech 在 iOS 走 `AVSpeechSynthesizer` — 用 Apple 系统内置语音
- 中文语音可选: Tingting (普通话女)、Sin-Ji (粤语女)、Mei-Jia (台湾普通话女)、Yu-shu (普通话女)
- 没指定 voice identifier — 系统按 locale 自动选默认
- iOS 16+ 加了 "Personal Voice" 但只能克隆**自己**的声音, 不能克隆他人

### 1.2 "选择林志玲" 的合规判断 — **不能直接做**

**法律风险**:
- 中国《民法典》第 1023 条: 自然人对其声音享有保护权, 参照肖像权规则
- 未经本人许可使用真人声音 = 侵权
- "林志玲" 这种知名艺人, 风险等级是商业级 (经纪公司必告)
- 即便用户在前端看到的是"林志玲"按钮, 后端实际用其他人声音, 也涉嫌**虚假宣传**

**技术风险**:
- 即便绕过法律, "克隆林志玲声音" 的技术现实:
  - Apple 系统 TTS 没有 — 只有几个内置 voice
  - 商用 TTS API (阿里云/腾讯云/讯飞/Microsoft Azure/ElevenLabs) 都不会有"林志玲"的官方授权 voice
  - 自己用 SVC / VITS 训练: 工程量巨大且违法
  - 第三方"明星声音克隆" 平台 (RVC 模型库等) 全是侵权站, 不能商用接入

### 1.3 真实需求 — 拆解

用户想要的不是"林志玲"这个具体人, 是 **"温柔有亲和力的女声, 让健康助理感觉是个值得信任的人, 不是冷冰冰的机器"**.

证据:
- 林志玲在公众认知里 = 温柔台腔女声的代表
- 用户提到的是 voice **风格**而非 voice **身份**

### 1.4 推荐方案: 语音风格库

**3 档替代方案** (ROI 从高到低):

#### 方案 A: 切换 iOS 内置 Mei-Jia (台湾普通话) — **0.5 天 / 0 成本 / 0 风险**

```typescript
// 直接指定 voice identifier
Speech.speak(text, {
  voice: 'com.apple.ttsbundle.Mei-Jia-compact',  // 系统内置台湾女声
  language: 'zh-TW',
  rate: 0.95,    // 略慢一点显温柔
  pitch: 1.05,   // 略高一点
});
```

UI: 设置页加 "语音风格" 选项 — 默认 / 温柔台腔 / 北京普通话 / 粤语
存到 AsyncStorage, useVoiceConversation 读取.

**优点**: 0 成本, 0 风险, 立即可用
**缺点**: 仍然是机器音质, 跟"林志玲"差距大

#### 方案 B: 接入 ElevenLabs / Azure Cloud TTS — **3-4 天 / $5-10/万字符 / 合规**

ElevenLabs 有现成的"温柔亚洲女声"语音库 (Sarah / Rachel 中文 fork), 音质接近真人.
Azure Cognitive Services 中文 voice 有 `zh-CN-XiaoxiaoNeural` (晓晓, 温柔成年女声) 和 `zh-CN-XiaohanNeural` (晓涵, 知性女声).

**实施**:
- backend 加 `/api/v1/tts/synthesize` endpoint, 调 cloud TTS 返回 mp3 stream
- mobile 改 useVoiceConversation: 从 expo-speech 切到 expo-av 播放 mp3
- 风险: 网络延迟 + 流量成本 + offline 不可用

**适用**: 如果产品愿意为"听感"付费

#### 方案 C: Personal Voice — **iOS 17+ 用户能克隆自己声音**

让用户用 iOS 系统的 Personal Voice 功能录自己的样本, 然后在 App 里用 `voice: 'com.apple.voice.personal'`.

**适用场景**: 用户希望 AI 用自己的声音 (类似日记)
**不适用**: 林志玲这种"他人声音"

### 1.5 最终推荐

**A 立刻做** + **B 留作 v2 升级路径**.

工时:
- A (语音风格库 + 设置页 toggle): 0.5 天
- B (Cloud TTS 接入): 3-4 天 + 长期成本

**关键沟通**: 跟产品 owner 明确告知 — UI 上的 label 只能是"温柔台腔女声" / "亲和女声", 不能是"林志玲". 否则 App Store 审核也会挂 (Guideline 5.2.1 IP).

---

## 2. 需求 2: 跑步详情页分享微信 + 美化

### 2.1 现状

- `mobile/app/workout-detail.tsx` 352 行, 已有:
  - MapView + Polyline (运动轨迹)
  - MetricTile × N (时长 / 卡路里 / 心率 / 距离)
  - HealthCard 容器
  - Markdown 渲染 (post-analysis)
- 没有: 任何 share 按钮 / SDK / 截图 / 微信集成
- iOS Info.plist 没有微信 URL Scheme

### 2.2 微信分享技术调研

#### 选项 A: react-native-wechat-lib (现役主流)
- 维护活跃, 支持 RN 0.70+
- 需要微信开放平台注册 App ID (https://open.weixin.qq.com)
- 注册需要企业资质 + 100 元审核费 + 1-3 工作日
- iOS 配置: Info.plist 加 URL Scheme + LSApplicationQueriesSchemes + Universal Links

#### 选项 B: iOS 原生 ShareSheet (UIActivityViewController)
- React Native 内置 `Share.share()` API
- 用户点 → 系统分享面板 → 用户选微信
- **不需要微信 SDK / App ID**
- 限制: 只能分享 URL / Text / 文件, 不能分享小程序卡片或专门的"朋友圈卡片"

#### 选项 C: 生成图片 + Save to Photos / 系统分享
- `react-native-view-shot` 把 workout-detail 的成绩部分截图成 PNG
- 用户长按保存或走系统分享发到微信
- **零审核风险, 实施最简**

### 2.3 推荐方案: C → 长期升级到 A

#### Phase 1 (1-2 天): 截图 + 系统分享
- 用 react-native-view-shot 把成绩区域 (METRICS + ROUTE) 截图
- 调 `Share.share({ url: tempPngPath })` 走 iOS ShareSheet
- 用户在 ShareSheet 里选"微信"完成分享
- 0 native config 改动, 0 审核风险

#### Phase 2 (3-4 天): 微信 SDK + 朋友圈卡片
- 注册微信开放平台 App ID (需要企业资质 — 阻塞项)
- 集成 react-native-wechat-lib (eas build, 不是 OTA)
- 实现"分享到朋友圈" + "分享给朋友" 两选项
- 只在 Phase 1 验证了"用户真在分享" 后才做 Phase 2

### 2.4 "美化" 的量化拆解

"美化" 是模糊词. 拆成具体设计语言:

| 当前 | 改进 |
|---|---|
| MetricTile 单调列表 | **Hero 卡**: 顶部一张卡显示核心数据 (距离/配速/时长) + brand 渐变背景 |
| 心率单值 (avg_heart_rate) | 心率曲线图 (recharts / victory-native), 标 zone |
| 配速单值 | 配速分布 + km 分段配速柱状图 |
| 路径地图 | 起点/终点标 + 标速色彩渐变 polyline (绿快红慢) |
| Markdown 分析 | 标题 + emoji + tag chip, 不是流水文字 |
| 分享按钮缺 | 顶部右侧 share icon + 截图卡片专门 layout (4:5 比例适合微信朋友圈) |

### 2.5 工时

- Phase 1 截图分享: 1.5 天
- 美化 (Hero 卡 + 心率曲线 + 配速分布 + 路径色彩): 3-4 天
- Phase 2 微信 SDK: 3-4 天 (含等开放平台审核)

**总计**: Phase 1 + 美化 = 4-5 天, 立即能 ship; Phase 2 后续

---

## 3. 需求 3: 跑步中实时心率步频指导 — **产品方向级决策**

### 3.1 这不是单纯加功能

当前产品定位 (CLAUDE.md): "AI 健康操盘手" — 数据聚合 + 长期分析 + 主动提醒. **没有"运动中陪伴"场景**.

加这个功能 = 产品方向从"数据分析师" → "运动教练". 涉及:
- 用户关闭 App 后实时数据采集
- 后台音频 session (跑步中 TTS 念出来)
- 真实用户场景: iPhone 在臂带 / 口袋, 不一定能看屏幕

**这跟 1, 2, 4 不同 — 1, 2, 4 是产品改进, 3 是产品扩张.**

### 3.2 关键场景判断

**问题 1: 实时心率从哪来?**

| 数据源 | 可行性 | 限制 |
|---|---|---|
| Apple Watch + HealthKit `HKLiveWorkoutBuilder` | ✅ 最佳 | 需要 watchOS 配套 App, 当前没有 |
| iPhone 内置加速计 + GPS (无心率) | ⚠️ 部分 | 没有心率, 只有步频/配速 |
| Garmin Connect 实时数据 | ❌ 不可行 | Garmin API 不开放实时 stream, 跑完后 30-60s 才同步 |
| 第三方蓝牙心率带 (Polar H10 等) | ⚠️ 可行 | 需要 BLE 集成 + 用户买带 |

**当前用户主要用 Garmin 手表** (生产数据: Garmin 数据 8/8 天连续). Garmin 不能实时给数据 = **iPhone 单端跑步指导基本做不了真实心率部分**.

**问题 2: 跑步中 App 状态**

iOS 后台限制:
- Background mode `audio` + AVAudioSession 才能持续 TTS
- React Native 默认会被挂起, 需要 expo-background-fetch (限制大) + Foreground Service-like 方案
- 5-10 分钟跑步可能 OK, 1 小时跑步会被系统终止

### 3.3 三条可行路径 (按工时排)

#### 路径 A: iPhone 单端 — 步频 + 配速 + GPS (无心率)
- CMPedometer 取实时步频 (170-180 spm 推荐区间)
- expo-location 取实时配速
- 无心率 → 指导仅基于步频/配速
- TTS 每公里播报 + 异常时插播
- **工时**: 5-7 天
- **价值**: 中等 — 没心率就不是真"教练"

#### 路径 B: + 蓝牙心率带支持
- 集成 react-native-ble-plx
- 读 Polar H10 / 类似设备的标准 BLE 心率服务 (UUID 0x180D)
- 实时心率 + 步频 + 配速 → 完整指导
- **工时**: 8-10 天 (含 BLE pairing UX)
- **价值**: 高 — 但目标用户必须买心率带 (产品 owner 已有 Garmin)

#### 路径 C: 写 watchOS 配套 App
- 用 SwiftUI / WatchKit 写 Apple Watch App
- 用 HKLiveWorkoutBuilder 实时心率 + 步频
- watchOS ↔ iOS 通过 WatchConnectivity 同步
- **工时**: 15-25 天 (Apple Watch 是另一个完整平台)
- **价值**: 最高 — 真正的"运动伴侣" — 但工时巨大且产品 owner 不一定用 Apple Watch

### 3.4 我的判断

**不应立即做 — 应先回答 3 个问题**:

1. **产品 owner 跑步时戴什么**? Garmin / Apple Watch / 只 iPhone?
2. **痛点是什么**? 当前跑完导入 Garmin 数据是事后回看, 真痛点是哪一段?
   - "跑得快了不知道" → 实时配速提示 (路径 A 解决)
   - "心率冲太高没察觉" → 实时心率告警 (必须路径 B 或 C)
   - "动作不对没人提醒" → 这超出当前能力 (需要计算机视觉)
3. **跑步是核心使用场景吗**? 7d 数据看, 用户 0 次进 record tab 打卡, OpenClaw 22 条/天主要在打卡饮食 — **跑步不是当前 daily driver**.

**如果跑步不是 daily driver → 路径 A 都嫌奢侈**. 应先做 Phase 1 (workout-detail 美化 + 分享), 让"跑完后"体验对齐, 再考虑"跑步中".

### 3.5 推荐: 暂缓, 但做一个"跑后教练"过渡品

不是真"跑步中实时指导", 而是"跑完后立即的下一阶段教练":
- 用户跑完 → Garmin 同步 → AI 推送: "今天 5km 配速 5'30", 心率冲到 175 (max 92%) 略高 — 明天休 1 天 + 后天慢跑 30min"
- 这是 P2 推送故事化 (2026-05-04 已 ship) 的延伸
- 不需要新技术, 只需要 specialist 触发器
- **工时**: 1-2 天

让"实时跑步指导" 成为 6 个月后的功能, 当前先做 80% 的价值.

---

## 4. 需求 4: voice-chat 页 markdown 渲染 — **是 bug, 不是 enhancement**

### 4.1 现状 — 真问题

`mobile/app/voice-chat.tsx:108`:
```tsx
<Text style={[txt.bubbleText, t.role === 'user' && { color: '#fff' }]}>
  {t.text}
</Text>
```

LLM 输出可能是:
```markdown
你昨晚睡得**不错**。
- 睡眠 7.5h ✓
- HRV 55ms (基线 +5%)

建议:
1. 今晚再保持
2. 训练强度可以适度
```

但渲染成纯 Text — 用户看到:
```
你昨晚睡得**不错**。
- 睡眠 7.5h ✓
- HRV 55ms (基线 +5%)

建议:
1. 今晚再保持
2. 训练强度可以适度
```

**`**` 和 `-` 都暴露给用户, 体验极差**.

### 4.2 现有资源

`react-native-markdown-display` 已经在项目里用 (5 处), 包括:
- ChatBubble.tsx (chat tab)
- workout-detail.tsx
- journal/[id].tsx
- consultations/[id].tsx
- InterventionCard.tsx

唯独 voice-chat.tsx 没用 — **是遗漏**.

### 4.3 实施

**0.5 天**:
1. voice-chat.tsx 引入 Markdown
2. user role 仍走 Text (用户输入是纯文本, 不需要 markdown)
3. assistant role 走 Markdown 包装 + 复用 createMdStylesChat (已有 dark mode 适配)
4. 注意: TTS 输入的文字应该已经是 markdown stripped 版本 — 当前 useVoiceConversation 直接 Speech.speak(sentence) 把 `**` `#` 念出来, 这是同一类 bug 但**另一处**:
   - 解决: enqueueSentences 之前先 strip markdown
   - 用简单正则 `/\*\*|##|^- |^\d+\. /gm` 清掉

### 4.4 这个改动连带修了一个 P2 推送故事化没修的伴生问题

P2 (2026-05-04 已 ship) 是改了推送 body 的语气, 但 voice-chat 的 TTS 仍念裸 markdown. 一并修.

---

## 5. 综合规划 — 按 ROI 排序

| Order | 需求 | 工时 | 风险 | 立刻可 ship 吗 |
|---|---|---|---|---|
| **1** | 需求 4 (markdown 渲染) | 0.5 天 | 0 | ✅ 立刻 |
| **2** | 需求 1 方案 A (台湾女声 + 风格库) | 0.5 天 | 0 (零成本/零风险) | ✅ 立刻 |
| **3** | 需求 2 Phase 1 (截图分享) + 美化 | 4-5 天 | 低 (无 native 改) | ✅ 1 周内 |
| **4** | 需求 3 替代方案 ("跑后教练" 推送) | 1-2 天 | 低 | ✅ 1 周内 |
| **5** | 需求 1 方案 B (Cloud TTS) | 3-4 天 | 中 (流量成本) | ⚠️ 2 周内 |
| **6** | 需求 2 Phase 2 (微信 SDK) | 3-4 天 | 中 (开放平台审核 + eas build) | ⚠️ 1 个月内 |
| **7** | 需求 3 路径 A (iPhone 单端实时) | 5-7 天 | 高 (后台 session 限制) | ❌ 触发条件: 用户证明跑步是 daily driver |
| **8** | 需求 3 路径 B/C (BLE / watchOS) | 8-25 天 | 高 | ❌ 暂不做 |

### 第 1 周可 ship (Order 1-4) — 6-8 天

这一周做完, **4 条需求的"真实需求"都解决了 80%**:

- ✅ Markdown 渲染 (需求 4 完成)
- ✅ 温柔台腔女声 (需求 1 真需求 80%, "林志玲"字面留欠款)
- ✅ 一键分享 + 美化 (需求 2 完成 80%)
- ✅ 跑后教练推送 (需求 3 真需求 60%, 实时部分留欠款)

### 第 2-4 周 (Order 5-6) — 6-8 天

- Cloud TTS (听感升级)
- 微信原生 SDK (朋友圈卡片)

### 6 个月后 (Order 7-8) — 触发条件后才做

- 实时跑步指导 — 需先验证用户跑步是 daily driver

---

## 6. 关键决策点 (需要 product owner 确认)

| 决策 | A 选项 | B 选项 | 我的倾向 |
|---|---|---|---|
| **TTS "林志玲" 字面 vs "温柔女声"** | UI 写"林志玲" (违法) | UI 写"温柔台腔女声" | **B**, 必须避雷 |
| **跑步分享走系统 vs 微信 SDK** | 系统 ShareSheet (1.5 天) | 微信 SDK (3-4 天) | **先 A 再 B** |
| **实时跑步指导优先级** | 立即做 | 暂缓, 先看 daily driver 数据 | **B** — 7d 数据显示用户当前不是跑步重度 |
| **TTS Cloud API vs 系统** | 用 ElevenLabs/Azure ($) | 系统内置 (免费) | **先系统, 用户反馈再升 Cloud** |

---

## 7. 不做清单 / 风险项

| ❌ 不做 | 原因 |
|---|---|
| 直接克隆林志玲声音 | 法律红线 + App Store 审核挂 |
| 无授权使用第三方 RVC 声音模型 | 同上 |
| 不经 product owner 同意就接入微信 SDK | 需要企业资质 + 1 次 eas build, 不是 OTA |
| 实时跑步指导一步到位 (路径 C) | 工时 25 天, 当前 ROI 算不过来 |
| 用 Garmin "实时数据" 做指导 | Garmin API 不开放实时 stream, 是技术不可行 |

---

## 8. 工程债务连带修复

借这次机会, 顺手清:

1. **voice-chat.tsx TTS 念裸 markdown** — 同 4.4, 加 stripMarkdown helper
2. **useVoiceConversation 没有 voice 参数化** — 加 setting → AsyncStorage 配合 1.5
3. **workout-detail.tsx Hero 区不够突出** — 配合需求 2 美化

---

## 9. 修订日志

- **2026-05-04 17:30 写就**. 待与另一 CLI 输出对比.
- 关键判断: 4 条需求里, **2 条是 bug 性质 (4 + 1B)**, **1 条是产品扩张 (3)**, **1 条是常规改进 (2)**.
  按 ROI: 4 → 1A → 2 → 3 替代方案 → 1B → 2B → 3 实时.
- 必须避雷: "林志玲" 字面用法.
