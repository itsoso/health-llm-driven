# Reva Mobile / Watch / HealthKit Experience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

## 目标

在 Reva 现有代码基础上，重新设计 Mobile 端体验，让它从“健康数据 App”升级为“高级感的个人 Health OS”。本轮目标覆盖四件事：

1. 重新设计 Reva Mobile UI，让第一屏、对话页、记录入口、设备状态都有高级感和一致的系统气质。
2. 对话页面实现 Chat + 动态 UI 卡片融合，让大模型回复不只是文本，而能直接呈现记录、建议、风险、计划、证据和可执行动作。
3. Apple Watch 上实现低摩擦语音交互，用于饮食/运动记录和大模型健康助理交互。
4. iPhone 上实现 HealthKit 自动同步，授权后不再依赖用户手动点同步。

## 产品准入判断

本计划符合 `docs/specs/reva-product-governance-spec.md`：

- **使命映射**：不是做普通聊天机器人或健康 Dashboard，而是构建 Personal Health OS：感知身体状态，生成高杠杆行动，跟踪执行和结果。
- **首要用户**：35-55 岁高强度工作者，已有 iPhone / Apple Watch / HealthKit / 体检报告 / 可穿戴数据，愿意把 Reva 当作日常健康驾驶舱。
- **核心对象**：
  - `HealthTwin`：用户身体状态和风险画像。
  - `RealtimeHealthSignal`：HealthKit / Watch / wearable 实时或近实时数据。
  - `HealthAgendaItem`：今天应该做的健康行动。
  - `ExecutionEvent`：饮食、运动、补剂、用药、症状、睡眠等执行记录。
  - `WriteIntent`：AI 生成但需要用户确认的写入动作。
  - `InterventionCycle`：建议、执行、观测、复盘的闭环。
  - `DataConnection` / `ConsentGrant` / `ProvenanceRecord`：HealthKit 自动同步的授权、来源、审计。
- **Surface 分工**：
  - Mobile：Today / Chat / Capture / Review 的主体验。
  - Watch：低摩擦执行和语音记录，不承载复杂分析。
  - Backend：健康事实、导入、计划、卡片、审计、模型推断的来源。
- **安全边界**：大模型只做健康建议、记录归档、风险提示和就医建议；不做诊断替代，不直接改药，不绕过用户确认写入敏感数据。

## 当前代码基础

已经存在可复用能力：

- Mobile Today：`mobile/app/(tabs)/index.tsx` 已有 Reva Today 时间线、Hero、Vitals、Timeline、Quick Actions。
- Chat：`mobile/app/(tabs)/chat.tsx` 已有 `useChatEngine`、消息列表、输入栏、会话切换、分享、模型选择。
- 动态卡片：`mobile/components/chat/cards/registry.tsx` 已有 `record`、`sleep`、`weight`、`bp`、`supplement`、`diet`、`workout`、`medical_report`、`system_knowledge_evidence`、`weather`、`score`、`vitals` 等卡片注册。
- 语音对话：`mobile/app/voice-chat.tsx` 已支持自动开始、TTS、健康记录 intent、周报/晨报/preworkout 等上下文。
- Watch 快速记录：`apps/watch/WatchApp/QuickRecordView.swift` 已支持饮食语音、症状语音、水、俯卧撑、跑步，并用 Digital Crown 调整数值。
- Watch dictation：`apps/watch/WatchApp/WatchDictation.swift` 已封装系统听写。
- HealthKit：`mobile/services/appleHealth.ts` 已支持授权、读取、聚合、上传 `/devices/healthkit/import`，但当前主要由 UI 手动触发。
- Backend HealthKit：`backend/app/services/device_adapters/healthkit.py` 和 `/api/v1/devices/healthkit/import` 已承担导入与归一化。

## 平台边界

### Apple Watch 表冠

“按住表冠进行对话”不能按字面实现为第三方 App 接管系统 Digital Crown 长按。Digital Crown 长按属于系统/Siri 级交互，第三方 App 可用的是：

- 在 Watch App 内提供按住说话按钮。
- 使用 complication / Smart Stack widget 快速进入 Reva 语音。
- 使用 Siri / App Intents 触发 Reva 记录或打开 Reva 语音。
- 使用 Digital Crown rotation 调整数值，这一点现有 QuickRecord 已在用。

因此本计划把用户目标实现为：**在 Watch 上做到“抬腕进入、按住 Reva 麦克风说话、松手提交、必要时追问确认”；表冠长按如果平台不可用，则用 complication / Siri phrase / App Intent 作为系统入口。**

### HealthKit 自动同步

HealthKit 自动同步分两层：

- **第一层：JS/Expo 可快速落地**
  App 启动、回到前台、用户进入 Today / Chat / Settings 时，如果已授权且超过同步间隔，自动调用 `syncRecentDays`。这能消除大部分“手动同步”体验，但不是完整后台同步。
- **第二层：Native iOS 后台同步**
  需要 iOS 原生模块使用 `HKObserverQuery`、anchored query、background delivery，并配合 App 生命周期和上传队列。这不是 OTA 变更，需要 EAS build / TestFlight / App Store 流程。

## 设计方向

### 视觉原则

Reva Mobile 不做营销页，不做花哨渐变，不做普通健身 App 的彩色卡片堆叠。整体气质是：

- 安静、克制、可信赖。
- 有医疗级秩序感，但不冰冷。
- 像高级驾驶舱：用户一眼看到身体状态、今天最重要动作、异常风险和下一步。
- 卡片不是装饰，而是可行动、可验证、可追踪的健康对象。

### 视觉语言

- 主背景：近白 / 暖灰，避免大面积黑色或紫蓝渐变。
- 文本：石墨黑、深灰、少量冷绿色作为健康状态强调。
- 风险色：琥珀用于注意，红色只用于明确风险。
- 卡片：小圆角、细边框、轻阴影或无阴影，以信息层级取胜。
- 动效：只用于状态切换、语音录制、卡片出现、执行完成，不做无意义漂浮。

### Mobile 信息架构

第一屏应从“内容堆叠”改成“Health OS 工作台”：

1. 顶部：身份、日期、Health Twin 状态、数据新鲜度。
2. 中心：今天的 1-3 个高杠杆行动，不展示过多低优先级建议。
3. 下方：实时信号摘要，如睡眠、HRV、心率、活动、体重、血氧、压力。
4. 持久入口：语音记录、Chat、快速记录、设备同步状态。
5. 风险/异常：只在有明确数据依据时进入视觉前景。

## 实施计划

### Phase 1：Mobile 视觉系统和 Today 第一屏

目标：先让用户打开 App 的第一感觉明显升级。

任务：

1. 建立 Reva Mobile 视觉 token：
   - 颜色：背景、文本、边框、状态、风险、成功、弱化信息。
   - 间距：页面 gutter、卡片 padding、模块间距。
   - 字体层级：标题、指标数字、正文、caption。
   - 组件半径：控制在 8px 左右，避免过度圆润。
2. 重构 Today 第一屏：
   - 保留现有数据源和 React Query。
   - 将 Hero 改为 Health Twin cockpit。
   - 将 Timeline 改为“今日行动轨道”。
   - 将 Vitals 改为“实时信号条”。
   - 将 Quick Actions 改为底部命令区。
3. 增加数据新鲜度和连接状态：
   - HealthKit / Garmin / Apple Watch 最近同步时间。
   - 数据过期时明确提示，但不打断主流程。

验收：

- iPhone 小屏不会出现文本溢出或卡片挤压。
- 第一屏不超过 3 个主要视觉焦点。
- 现有 Today 数据请求不被破坏。
- 可通过 OTA 发布。

### Phase 2：Chat + 动态 UI 卡片融合

目标：让 Chat 成为真正的健康操作系统入口，而不是纯文本问答。

任务：

1. 重构消息渲染：
   - assistant 文本和 `serverCards` / `uiCards` 在同一个时间线中出现。
   - 卡片不作为消息附属装饰，而是作为可执行对象。
2. 统一卡片样式：
   - 复用 `mobile/components/chat/cards/registry.tsx`。
   - 让 `record`、`diet`、`workout`、`sleep`、`vitals`、`evidence` 卡片视觉统一。
   - 对未知卡片保持 no-op，不崩溃。
3. 增加卡片动作：
   - 确认记录。
   - 编辑记录。
   - 标记完成。
   - 查看依据。
   - 加入今天行动。
4. 引入“动态 UI 片段”模式：
   - 大模型可以返回文本 + 卡片 schema。
   - 前端只渲染白名单卡片。
   - 敏感写入必须走 `WriteIntent` 确认。

验收：

- 用户输入“我刚吃了两个鸡蛋一杯牛奶”，Chat 返回文本总结 + 饮食记录卡片 + 确认按钮。
- 用户问“今天怎么练”，Chat 返回建议 + workout card + 风险提醒。
- 用户问“为什么建议补镁”，Chat 返回依据卡片，而不是只输出长文本。
- 卡片渲染有单元测试覆盖。

### Phase 3：HealthKit 前台自动同步

目标：先消除用户手动同步的主要痛点。

任务：

1. 新增 HealthKit auto-sync service：
   - 读取 `healthkit_authorized_v1`。
   - 读取 `healthkit_last_sync_v1`。
   - 根据冷却时间自动调用 `syncRecentDays`。
   - 避免并发重复同步。
   - 失败时静默降级，并在设备状态区展示。
2. 接入 App 生命周期：
   - App 启动。
   - 回到前台。
   - 进入 Today。
   - 进入 Chat 前可轻量触发最近数据刷新。
3. UI 调整：
   - Settings 中保留手动同步作为 fallback。
   - Today 中展示“自动同步已开启 / 最近同步时间 / 数据来源”。

验收：

- 用户授权后，打开 App 自动同步最近数据。
- 同步冷却时间内不会重复打后端。
- 无授权时不弹无意义错误。
- sync 失败不会阻断 Today/Chat。
- 可通过 OTA 发布。

### Phase 4：Watch 语音助理 MVP

目标：Watch 上能快速记录饮食、运动，并能向 Reva 健康助理提问。

任务：

1. 新增 Watch Voice Assistant 页面：
   - 大按钮按住说话或点按开始听写。
   - 支持三类 intent：饮食记录、运动记录、健康助理问答。
   - 显示处理中、成功、需要手机继续、风险提醒状态。
2. 复用现有 Watch dictation：
   - `WatchDictation.present()` 作为第一版输入。
   - 后续再接入更连续的录音/语音流。
3. 扩展 Watch store / API：
   - 饮食、运动、症状继续进入现有记录管线。
   - 健康助理问题进入 phone/backend agent 管线。
4. 添加入口：
   - Watch 首页增加 Reva Voice。
   - complication / Smart Stack 后续作为快捷入口。

验收：

- Watch 上说“晚饭吃了牛肉面”，手机/后端出现待确认饮食记录。
- Watch 上说“刚跑了 20 分钟”，出现运动记录。
- Watch 上问“我今天适合高强度训练吗”，返回简短安全建议或提示到 iPhone 查看详情。
- 不声称第三方 App 已接管 Digital Crown 长按。

### Phase 5：HealthKit Native 后台同步

目标：把“打开 App 自动同步”升级为更接近真实后台自动同步。

任务：

1. 增加 iOS native HealthKit background bridge：
   - Observer query。
   - Anchored object query。
   - Background delivery。
   - 本地上传队列。
2. 数据范围：
   - 第一批：steps、heartRate、restingHeartRate、HRV、sleep、activeEnergy、weight。
   - 第二批：bloodPressure、oxygenSaturation、bodyTemperature、VO2 max、ECG。
3. 隐私和审计：
   - 所有 HealthKit 数据写入 `ProvenanceRecord`。
   - 用户可查看同步来源和最近同步类型。
   - 用户可关闭自动同步。
4. 发布：
   - 需要 EAS native build。
   - TestFlight 验证后再正式发布。

验收：

- HealthKit 新数据写入后，Reva 能在后台或下一次系统唤醒时入队同步。
- 重复样本不重复写入。
- 用户关闭自动同步后不再读取 HealthKit。
- native build 在真机验证通过。

## 今日建议执行顺序

今天不建议四条线同时深入改代码。推荐顺序：

1. **先做 Phase 1 + Phase 2 的 OTA 范围**：Mobile 高级 UI + Chat 卡片融合，这是用户体感最大、风险最低、最容易快速验证的部分。
2. **随后做 Phase 3**：HealthKit 前台自动同步，先让用户“不需要手工同步”的主要体验成立。
3. **Watch 先做 MVP 设计和入口**：实现 App 内 Reva Voice，不承诺 Digital Crown 长按。
4. **最后开 native 分支做 Phase 5**：HealthKit 后台同步和 Watch 更深入口需要 EAS/TestFlight，不能混在 OTA 改动里。

## 测试与验证

### Mobile

- `cd mobile && npx tsc --noEmit --pretty false`
- Chat 卡片渲染相关 Jest 测试。
- HealthKit auto-sync service 单元测试：
  - 未授权不同步。
  - 冷却时间内不重复同步。
  - 回前台触发同步。
  - 失败不阻断 UI。
- 真实设备检查：
  - iPhone 小屏。
  - iPhone Pro 大屏。
  - 深色/浅色模式如当前 App 支持。

### Watch

- Xcode build Watch target。
- 真机验证 dictation。
- 验证 QuickRecord 既有水、俯卧撑、跑步、饮食、症状不回归。

### Backend

- HealthKit import 既有测试保持通过。
- 如果 Chat 卡片 schema 或 WriteIntent 有后端变更，增加 schema 白名单和权限测试。

## 风险

- **表冠长按不可控**：如果用户坚持字面表冠长按，需要先做 Apple 平台可行性确认；产品文案不能承诺系统不开放的交互。
- **HealthKit 后台同步不是 OTA**：纯 JS 只能做到前台/生命周期自动同步；真正后台同步需要 native build。
- **Chat 卡片安全**：不能让模型自由生成任意 UI；必须白名单 schema，敏感写入走确认。
- **高级感不是只换颜色**：需要减少视觉焦点、统一对象模型、优化信息密度，否则会变成另一套卡片堆叠。

## 下一步实现入口

第一批代码改动建议：

1. 新增或重构 `mobile/design/revaTokens.ts`。
2. 提取 Today 第一屏组件：
   - `mobile/components/reva/RevaCockpitHeader.tsx`
   - `mobile/components/reva/HealthActionRail.tsx`
   - `mobile/components/reva/RealtimeSignalStrip.tsx`
   - `mobile/components/reva/RevaCommandDock.tsx`
3. 改造 `mobile/app/(tabs)/index.tsx`，只替换视觉层，不改数据契约。
4. 改造 Chat 消息渲染，让 `renderServerCards` 和 assistant 消息进入同一视觉时间线。
5. 新增 `mobile/services/appleHealthAutoSync.ts`，先做前台自动同步。
