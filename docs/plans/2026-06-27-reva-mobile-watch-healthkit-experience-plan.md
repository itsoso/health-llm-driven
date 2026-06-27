# Reva Mobile / Watch / HealthKit 体验实施规划(融合版)

> **For Claude:** 实施时用 `superpowers:executing-plans` 逐任务执行。
>
> **状态**:2026-06-27 融合定稿。**本文 = Codex 初版计划 ⊕ Claude discovery 工作流(5 份代码现状图 + 3 份跨家族对抗评审:平台可行性 / 安全合规 / 范围排序)**。Codex 提供 5 阶段骨架、现状勘探、视觉方向、平台边界;Claude 工作流叠加了 ① 四问 + ASCII 数据流(项目必需格式)② 逐目标安全硬阻断(对抗评审实证)③ 平台事实精确化 ④ 重排序(数据底座先行)⑤ 准入 Gate 逐目标核对 ⑥ 关键现状发现。
>
> **权威依赖**(本文不重述,只引用):
> - 产品范围/北极星/一等对象:`docs/prd/reva-personal-health-os-prd.md`(唯一权威 PRD,R4/R5/R6/R15/R18)
> - 竞品/PRD 批判吸收:`docs/reports/2026-06-27-competitive-benchmark-and-prd-critique.md`
> - 准入 Gate / 不变量:`docs/specs/reva-product-governance-spec.md` §5/§6/§8
> - 视觉权威:`docs/design/reva/DESIGN-SYSTEM.md`
> - 工程硬规则:`AGENTS.md`;LLM Harness:`docs/HARNESS.md`

---

## 0. 这版相对 Codex 初版改了什么(融合 delta — 先读这段)

| # | 改动 | 依据 |
|---|---|---|
| 1 | **重排序:HealthKit 前台自动同步提到 Phase 0**(Codex 原排 Phase 3) | 范围评审:数据是底座,空环上的高级 UI「feel hollow」。先有新鲜数据,Home/Twin/卡片/专家全部立刻变实 |
| 2 | **每目标补「四问 + ASCII 数据流」** | `~/work/personal/PRACTICES/feature-plan.md`(项目新功能必跑) |
| 3 | **逐目标安全硬阻断嵌入为不可妥协前置** | 安全合规评审(发现真 PIPL 缺口 + 2 类 fail-open) |
| 4 | **平台事实精确化** | 平台可行性评审:Action Button(锚点用户 Ultra 3 有)才是「物理键说话」正解;HK 多数类型被 iOS 节流到 hourly/daily;`background-delivery` entitlement 缺失且会被 `withHealthKitCleanup` 误删 |
| 5 | **关键现状发现**(下面 §3 详述) | 5 份代码图:watch 已编译从未上设备;chat 卡片地基已在(13 类);单次 EAS 签名解锁 3/4 目标 |
| 6 | **Write 自治承重墙 doc/code 漂移澄清** | 治理图 + 安全图:别宣称「无人值守自治写已上线」覆盖敏感数据;只 `measurement_prompt` 自治 |
| 7 | **新增 Daily Artifact 作为 Mobile redesign 的中心对象** | 竞品调研:Whoop/Oura 留存靠每日复合工件;Reva 不能只靠季度外环,必须有日常仪式买 runway |
| 8 | **新增抗习惯化 + 5 分钟 on-ramp + Discoveries** | 竞品调研:HeartSteps/JITAI 习惯化风险、OpenHealth 分发证明、Oura Tags→Discoveries 可感反馈 |

---

## 1. 目标与北极星对齐

把 Reva Mobile 从「健康数据 App」升级为「高级感的个人 Health OS」。四件事:

1. **重设计 Mobile UI** —— 第一屏 / 对话页 / 记录入口 / 设备状态有高级感和一致系统气质,并围绕一个不可错过的 `Daily Artifact` 组织信息。
2. **Chat + 动态 UI 卡片融合** —— 大模型回复不只是文本,直接呈现记录 / 建议 / 风险 / 计划 / 证据 / 可执行动作。
3. **Apple Watch 低摩擦语音交互** —— 饮食/运动记录 + 大模型健康助理。
4. **iPhone HealthKit 自动同步** —— 授权后不再手动点同步。

**北极星对齐**(不替代 PRD,只说本轮怎么服务它):
- 结果北极星 = L3 主观精力 30 日均线 + L4 抗衰生化。这四件事**都是「让闭环更顺、数据更全、行动更易执行」的体验层杠杆**,不直接产生新医疗结论。
- 行为北极星 = WSCLA(每周安全+可验证+被安排+已执行+可验证的闭环数)。Goal 4(数据)和 Goal 2(卡片 action)直接提升闭环完成率;Goal 1/3 降低摩擦。
- 每日前门指标 = Daily Artifact D1/D7/D30 使用、top action 接受率、skip reason 覆盖率、行动接受率随周衰减、数据新鲜度达标率。**季度外环买护城河,每日工件买留存 runway。**
- **锚点用户(关键约束)**:35–55 高知中年男,糖前×脂肪肝×长期 PPI×多药;**同戴 Apple Watch Ultra 3 + RingConn Gen3 + Garmin Enduro 2**。→ 多源已是常态(`CrossSourceValidator` 已存在),且 **Ultra 3 有可编程 Action Button**(见 §4 表冠重构)。

---

## 2. 产品准入 Gate(逐目标过 `RequirementAdmission`)

按 `reva-product-governance-spec.md` §8。每目标必须映射 ≥1 一等对象、命中核心循环某步、声明安全级与自治档,否则 reframe 或不做。

| 目标 | first-class object | core_loop_step | target_surface | safety_level | autonomy_tier | spec_required(§8.1) |
|---|---|---|---|---|---|---|
| 1 premium UI + Daily Artifact | `HealthTwin`/`HealthAgendaItem`/`RealtimeHealthSignal`(渲染) | 感知→看见状态与今日行动→执行/skip | Mobile | none(除非渲新 claim) | none | **是**(新用户可见行为) |
| 2 chat 卡片融合 | `WriteIntent`/`HealthAgendaItem`/`InterventionCycle` | 行动+复盘(卡片可执行) | Mobile + Backend | medical_boundary | manual_confirm | **是**(新写路径 + 新跨端卡片契约) |
| 3 watch 语音+LLM | `ExecutionEvent`/`WriteIntent`/`SafetyGuardian` | 执行(低摩擦记录)+ 感知(简答) | Watch + Backend | medical_boundary / red_flag | manual_confirm | **是**(新安全行为 + 新写路径) |
| 4 HealthKit 自动同步 | `DataConnection`/`ConsentGrant`/`ProvenanceRecord`/`ExecutionEvent` | 感知(实时信号底座) | Mobile + Backend | privacy_sensitive | opt-in(默认关) | **是**(新数据采集路径 + 同意门) |

> Goal 3/4 是已 specced 的 **R4/R5/R6/R18** 的延伸(引用,不重 spec);Goal 1/2 是净新,触发 §8.1 必须各写一份 feature spec 再实现深层。

---

## 3. 当前代码基础(可复用 — 比初版更精确,file:line)

> **核心信号:四件事没有一件是从零起。最大障碍不是「不会写」,而是「连接已有 + 守住安全边界 + 过一次 EAS 设备签名」。**

### 3.1 视觉(Goal 1)—— token 已在,只是没接上
- **存在两套并行设计系统**(这本身是要消除的发现):
  - `mobile/constants/revaTheme.ts` = **真 Reva 系统**(忠实移植 Claude Design 交付:Manrope + IBM Plex Mono 等宽数字、focus 深绿 hero、绿调阴影、`revaMotion` 动效曲线)。**只被 Home + 休眠的 `/reva` 屏接入(~28 文件)**。
  - `mobile/constants/theme.ts` = **legacy「HealthPilot」token**(改了 hex 值但保留旧 token 名、**无字体族 → 全系统 PingFang/SF**)。**被 181 个文件引用 = 全 App 实际在跑这套**。
  - `mobile/constants/Colors.ts` = 死的 Expo 脚手架残留。
- `revaMotion`(`revaTheme.ts:127-133`,dur 240/420ms,easeOut 曲线)**定义了但全仓零消费**(grep 只命中定义)。`ReadinessRing`(`RevaKit.tsx:166-202`)是静态 SVG。
- `useRevaFonts()` 只在 `index.tsx`/`reva.tsx` 调用,**未在 app root** → 等宽数字(交付里的「核心签名」)在 ~100 屏缺席。
- **Home 可见接缝**:`app/(tabs)/index.tsx` 用 Reva 外壳,但内部 `ActivityRingBar`/`VitalsGrid`/`MedicationCheckin`/`BodyStatsRow` 四张子卡仍走 `useTheme()` legacy 系统字体。

### 3.2 Chat 卡片(Goal 2)—— 展示协议地基已在,缺「交织 + 编排桥 + action」
- **卡片协议已存在且跨端**:`mobile/components/chat/cards/`(`CardSpec<D>` + `ServerCardDescriptor{type,data}`、registry **未知类型安全降级为 null**`registry.tsx:106-108`、**13 类卡**:record/sleep/weight/bp/supplement/diet/workout/medical_report/system_knowledge_evidence/weather/score/vitals)。前端有同协议 + 测试(`frontend/src/components/assistant/inlineCards/`)。
- 卡片已在 chat 列表内联渲染(`ChatBubble.tsx:108-118`),但**只在终态 `done` 事件追加**(`useChatEngine.ts:448-462`)= **post-hoc 不交织**。
- **富编排输出被搁浅**:mobile chat 打 `/agent/stream`(OpenClaw executor),**不发** specialist / action_cards_created / safety_override;`stream_orchestrator` 全产出但**零 mobile 消费者**。
- 卡片**无 action 回调契约**(`CardSpec.render(data)` 无 `onAction`);`InterventionCard.tsx:76` 已证明 RN 内交互卡可行(有 `onComplete`/`onReview`),只是没接进 chat registry。
- `RevaAgentView.tsx:54` **把卡片过滤掉了**(一行可去)。

### 3.3 Watch(Goal 3)—— native 已编译,从未上设备
- `apps/watch/` = **native SwiftUI watchOS target**(SwiftPM + Ruby `xcodeproj` 注入器,经 `mobile/plugins/withWatchApp.js` 在 `expo prebuild` 注入 `ios/`,survive `--clean`)。**已编译「RevaWatch BUILD SUCCEEDED」watchOS 26.5**。
- `QuickRecordView.swift` 已有:饮食语音、症状语音、水、俯卧撑、跑步,且 **`.digitalCrownRotation` 调数值**(`:212-220`)。`WatchDictation.swift:16-22` 已封装系统听写。complication 已有(`RevaComplication.swift`)。
- watch 两个 backend allowlist(`WatchBackendRequest.swift:12-19`)**排除** `orchestrator/chat` + `openclaw/stream`(bridge 会拒 `WatchPhoneBridge.swift:118`);唯一合规语音裁决路径是 `/watch/symptoms`(`watch.py:268`,范本级:确定性裁决、不诊断、fail-loud、请求内禁 build_twin)。
- **EAS 签名部分预烘焙**(`inject_watch_target.rb`:`DEVELOPMENT_TEAM` 默认 `QA2U724DAN`、bundle id、`CODE_SIGNING_ALLOWED=NO` on resource bundles)。但 **watch 两 bundle id**(`…watchkitapp` + `…watchkitapp.watchkitextension`)需各自 App ID + provisioning profile 注册 → **凭据缺口只在第 4 层 EAS build 才冒**(memory `project_watch_companion_eas_build_signing`)。
- **决定性发现:仓库无任何证据表明 watch 曾上过真机**(只 compile-verified,scripts/docs 无 EAS/TestFlight 产物)。

### 3.4 HealthKit(Goal 4)—— 读取/上传/幂等已稳,后台未接 + 服务端无同意门
- `mobile/services/appleHealth.ts`:`react-native-health@1.19.0`(pinned),授权/读取/聚合/上传 `/devices/healthkit/import`;**`HKObserverQuery`/`enableBackgroundDelivery` 全仓零调用**(grep 确认)。当前**纯手动触发**(Settings 里 `AppleHealthRow` 点同步)。
- backend `device_adapters/healthkit.py` + `/api/v1/devices/healthkit/import`:**幂等已稳固** —— 日记录 upsert by `(user_id, record_date, data_source)`,点事件 by `(user_id, measured_at/recorded_at)`,per-record try/except。重叠窗口/重投安全,不双计。
- **真缺口**:`healthkit_import`(`devices.py:974`)只校验 `get_current_user_required` + batch cap,**服务端零 consent 校验**(不读 `ConsentGrant`/`DataConnection.sync_enabled`)。同意当前纯靠 iOS 端权限弹窗 = 客户端单方,服务端无法证明/审计/撤销。三个模型(`data_connection.py:17,41,83`)已存在但未接入 import 路径。
- `mobile/ios/` gitignored(CNG/prebuild),所有 native 改动走 `app.json`/config plugin。HealthKit entitlement `com.apple.developer.healthkit` 已设(`app.json:18-21`),但 **`com.apple.developer.healthkit.background-delivery` 未设(缺这把)**。

### 3.5 Write 自治承重墙 —— doc/code 漂移澄清(写 PRD 别踩)
- 自治写 allowlist 仅 `{measurement_prompt}`(良性可逆非医疗);**NEVER 集**(medication/dose/adherence/financial)永久封顶 `manual_confirm`,trust_elevator 无权提升。
- chat 内有自动确认快路 `_auto_confirm_fast_record_args`(`agent_executor.py:869`):`_prefer_fast_record_model=True` 时对 `health_record` 工具强制 `confirmed=True`,**白名单是隐式的**(靠 `health_record` 工具碰巧不收 medication/dose),非显式 fail-closed 断言 → **Goal 3 必须把它改显式**(见 §5.A)。
- ⚠️ 现状澄清:本 session 已把承重墙(`write_autonomy.py` `auto_execute_pending` + 后台 worker + 每日 cap≤4 + NEVER 硬集)**合入 main 并部署**;但 discovery 工作流读的是 `design/code-design-loop-scaffold` 分支(尚未含 B)。**无论哪个分支,PRD 的约束不变:只 `measurement_prompt` 自治,语音记录/卡片 action/医疗写全部 `manual_confirm`。别宣称无人值守自治写已覆盖敏感数据。**

---

## 4. 平台边界(诚实、精确 —— 不承诺平台不开放的交互)

### 4.1 Apple Watch「按住表冠说话」= 不可第三方实现 → 重构
**表冠长按是系统保留**(唤起 Siri / 回表盘),**无任何公开 watchOS API 让第三方 App 拦截表冠长按**(无 `WKInterfaceDevice` hook、无 SwiftUI gesture、无 entitlement)。**任何宣称「按住表冠说话」的文案都会被 App Review 拒。**

把用户诉求重构为(保真度降序):
1. **App 内「按住说话」大按钮** 驱动系统听写 —— `presentTextInputController(...allowedInputMode:.plain)`(**已接** `WatchDictation.swift`)。**今天就能做的「说话」主路径。**
2. **App Intent / Siri phrase** —— `AppIntents` + `AppShortcutsProvider`,「Hey Siri, 用 Reva 记录…」。**「按住表冠」的合法替身**(净新,watch 端未接;iPhone 有 `withIntentsExtension.js`)。
3. **Action Button(Apple Watch Ultra 专属,锚点用户有 Ultra 3)** —— 可绑 `AppIntent` shortcut。**这才是「按一个物理键就开口」对锚点用户的真解**;但 Ultra-only,不作通用主路径。
4. **complication / Smart Stack tap → 启动 App**(**已有** `RevaComplication.swift`)。
- `.digitalCrownRotation` 调数值(**已用**)保留。连续流式语音需 `WKExtendedRuntimeSession` + `SFSpeechRecognizer`(未用,有电量/运行预算成本)。

### 4.2 HealthKit 自动同步 = 可行但 best-effort,分两层
- **第一层(OTA 可落):前台/生命周期自动同步。** App 启动/回前台/进 Today 时若已授权且超冷却 → 自动 `syncRecentDays`。消除绝大部分「手动同步」体感,**零 native、零新 entitlement**。挂载点:`_layout.tsx:155-159` AppState「active」handler(现仅做 React Query focus)。
- **第二层(EAS,非 OTA):native 后台投递。** `HKObserverQuery` + `enableBackgroundDelivery` per type。`react-native-health@1.19` 暴露 observer API 但从不调用。**硬事实**:① iOS 只对**心率族**honor `HKUpdateFrequencyImmediate`,**多数 quantity 类型被节流到 ~hourly 甚至 daily**,与请求频率无关;② 投递不保证(iOS 按电量/使用批延/丢,Low Power Mode 完全停);③ 需加 `com.apple.developer.healthkit.background-delivery` entitlement,且 **必须确认 `withHealthKitCleanup.js` 不把这把新 key 一并剥掉**(它现在剥 `healthkit.access`),加 entitlement 会**强制新 provisioning profile**。→ **文案只能说「后台自动定期同步」,不能说「实时」。**

### 4.3 watch = 必须 native(RN 不编 watchOS)
**Expo/RN 没有 watchOS 渲染器,「watch 也用 RN 写」不可能。** 现有「native Swift target 经 config plugin 注入」是唯一正确路径,且已编译通过。watch app + complication 是 iOS app 的**嵌入 target**,随 iPhone IPA 一起提交 TestFlight(无独立 watch 上传)。**长杆 = 一次交互式 `eas build` 物化两个 watch bundle id 的凭据**(历史「烧过 10+ EAS build」),必须**异步**。

### 4.4 Chat 卡片 = 无平台障碍
纯 app 架构问题,RN 无阻碍,地基已在(§3.2)。长杆是**治理(R4)不是平台**:任何写卡片走 `manual_confirm`;任何对处方/激素指标(LDL/HbA1c/BP/TSH)的 claim 降级 `clinician_review`;card `type` 保持前端白名单(未知=no-op,已是)。

### 4.5 跨切关键洞察:**单次 EAS 设备签名解锁 3/4 目标**
Goal 3(watch 上设备)、Goal 4 第二层(HK 后台 entitlement)、Goal 3 的 watch AppIntent 验证 —— **都卡在同一根长杆:那次未验证的交互式 EAS 签名 + 凭据 loop + 真机 TestFlight**。→ **把这一个签名里程碑先 de-risk,后面所有「真机验证」的活叠在它后面。Goal 2(卡片)几乎全 OTA,不要被这根长杆挡住。**

---

## 5. 安全/隐私不变量(硬阻断 · 不可妥协 · 来自对抗评审)

> 每条都是「PRD 必须写死、实现必须满足」的前置。绿色=已稳,🔴=必须补门。

### A. 语音饮食/运动记录(watch/phone)—— 有条件 GO
- 🔴 **[阻断] 语音必须落到与 `/diet/voice/parse` 同一草稿出口**:parse 端点**只解析不写库**,产 `status="pending_confirmation"` 草稿,客户端确认后才 POST `/diet/records`。信任边界**在服务端**。PRD 写死「任何语音 parse 端点永不写终态表」。
- 🔴 **[阻断] `_auto_confirm_fast_record_args` 白名单从隐式改显式 fail-closed**:自动确认前显式断言 `record_type ∈ {water,weight,bp,diet,checkin,supplement}` 且 `∉ NEVER`,未知 kind → 退回 `manual_confirm`(对齐 `write_intent_service._execute` unknown-kind→ValueError fail-loud)。防弱模型把 supplement 误判处方剂量静默自动写。
- 🟡 supplement 经语音写,dose 只录用户口述值,**不带「基因型→具体剂量」**(R4 + `feedback_supplement_dose_nonprescriptive_ul_live`)。

### B. 表上 LLM 健康助手 —— **NO-GO 直到补门**(建议本轮先用 symptom 范式替代自由对话)
- 🔴 **[阻断] on-watch LLM 输出必须过与服务端同一条 SafetyGuardian 确定性门**(`evaluate_rules_with_status`,failed_count,critical→保守措辞+升级手机);不得因小屏/流式走简化路径。
- 🔴 **[阻断] 表上禁自由诊断对话,默认转手机**:只回短安全建议或「去 iPhone 看」;不长对话、不影像、不本地诊断、不常驻监听(R4/R18)。
- 🔴 **[阻断] 保守措辞 + 免责**:TTS 文本出口必须过 `guidance_validator` strip/soften(覆盖 `diet_prescription_red_line`/`movement_imperative_red_line`)。
- 🟡 若真要把 `orchestrator/chat` 加进 watch allowlist,属 §8.1 新写/新安全行为,必须配 feature spec + 对抗测试。

### C. HealthKit 自动摄入 —— 幂等 GO,**同意 NO-GO(服务端必须补门)**
- ✅ 幂等已稳(§3.4),无需新增。
- 🔴 **[阻断] import 端点必须服务端校验分类型同意**(PIPL):import 前查 `ConsentGrant`(按 HK 数据类型粒度),无授权类型记录拒收;**撤销在服务端即时生效**。这是当前代码真缺口(`devices.py:974`),自动化后被放大 = 不可妥协前置。
- 🔴 **[阻断] 每样本写 `ProvenanceRecord` + data_source**(可审计「哪条来自哪设备、何时同意下读取」)。
- 🟡 后台自动同步**默认关、用户显式 opt-in**;前台 `syncRecentDays` 也须门控 `getHealthKitAuthorized()` + 服务端 consent。

### D. R15 通知预算 —— GO,带「零新增主动推送压力」
- 🔴 **[阻断] 自动同步/complication/主动卡不得绕过 R15 计数**:后台同步是静默拉取(不推通知);若同步触发「新数据→主动洞察卡→推送」,必须计入 `proactive_global_weekly_budget`。complication 被动 pull 不计;其驱动的 haptic/通知计。
- 🔴 **[阻断] watch 主动触达受 `proactive_weekly_budget=1` 封顶 + 跨端去重单计**(phone+watch 不各发一份)。
- 🟡 静默时段(就寝−90min)只放 P0;watch strong-haptic 尤其遵守 quiet hours。

---

## 6. 视觉设计方向

**气质**(Codex 定调,保留):安静、克制、可信赖;医疗级秩序感但不冰冷;像高级驾驶舱 —— 一眼看到身体状态 / 今天最重要动作 / 异常风险 / 下一步。卡片是可行动可验证可追踪的健康对象,不是装饰。

**视觉语言**(对齐 `DESIGN-SYSTEM.md`):近白/暖灰主背景(避免大面积黑或紫蓝渐变);石墨黑/深灰文本 + 少量冷绿作健康状态强调;琥珀=注意,红=仅明确风险;卡片小圆角(~8px,实际 Reva `lg:18`/`xl24` hero)细边轻阴(绿调阴影);动效只用于状态切换/语音录制/卡片出现/执行完成。状态用 dot/chip,**绝不 alarmist**(§6.12)。

**高级感的真功夫(关键纠偏)**:token **已经存在且够好**,「高级感不是换色」。真正的杠杆是 ——
1. **等宽数字 app-root 化**(签名):`useRevaFonts()` 提到 app root + legacy 数字 typography 指向 `IBMPlexMono`。单这一项就是「看起来像另一个更贵的 App」最大 delta。
2. **动 ReadinessRing**:消费已定义的 `revaMotion`,给静态 SVG 加一条 `withTiming` 420ms sweep。静→动是不成比例的质感跃升(~30 行)。
3. **关 Home 接缝**:四张 legacy 子卡(`ActivityRingBar`/`VitalsGrid`/`MedicationCheckin`/`BodyStatsRow`)迁到 `revaColors`+Reva 字体。
4. **Daily Artifact 中心化**:第一屏不是卡片墙,而是一个复合身体状态判断 + 一个 top action + 最多 3 个证据来源 + 完成/跳过/问 Reva。
5. **减焦点**:第一屏 ≤3 个主视觉焦点;低优先级建议折叠。
- **不在本轮**:Reva 系统的暗色模式(它没有,可延后)、`BlurView` chrome、把 100 屏全迁 —— 那是「全量重设计」,不 gate felt value。

---

## 7. 分阶段实施(重排序 · 四问 · ASCII · 验收 · 测试闸)

### Phase 0(本周 · 三条并行 · 全 OTA)—— 新鲜数据底座 + Daily Artifact 契约 + 最便宜的高级信号

> 重排序核心:**先让数据活起来 + 定死每日工件 + 最便宜的质感**,三者零平台风险、纯 OTA、当天可验。

#### 0A · HealthKit 前台自动同步
- **四问**:
  - *Why*:锚点用户从不每天进 Settings 点同步 → 时间线/Twin/专家全在跑陈旧稀疏数据 → 一切下游体验变薄。自动后:打开 App 今日步数/HR/HRV/睡眠**已在**,零操作。
  - *What NOT*:不做 native 后台投递(Phase 3);不动 backend(幂等已稳);不碰 consent 门以外的隐私改造(consent 门见 0 之外,但前台同步必须门控授权)。
  - *How(最简)*:`_layout.tsx:155-159` AppState「active」加 `if getHealthKitAuthorized() && 超冷却 → syncRecentDays(2)`;并发去重;失败静默降级 + 设备状态区展示。复用 `appleHealth.ts` + 已幂等的 import;同步结果写 freshness/provenance 摘要供 Daily Artifact 展示。
  - *Risk*:无 schema/native;唯一风险=重复打后端(冷却 + 幂等双保);无授权不弹错。
- **ASCII**:
  ```
  App 回前台 (AppState active)
      ↓  mobile/app/_layout.tsx:155-159
  getHealthKitAuthorized()? ──no──→ 跳过(不弹错)
      ↓ yes & 距上次 > 冷却
  appleHealth.syncRecentDays(2)
      ↓ POST /api/v1/devices/healthkit/import (已幂等 upsert)
  backend device_adapters/healthkit.py → 入库去重
      ↓
  React Query invalidate → Today/Twin 刷新(新鲜数据)
  ```
- **验收**:授权后打开 App 自动同步近 2 天;冷却内不重复打后端;无授权不弹错;同步失败不阻断 Today/Chat;Daily Artifact 能看到数据来源和最近同步时间。
- **反馈环**:本地 Sim(`npm run ios`)→ OTA。

#### 0B · 最小高级感(mono numerals app-root + 动 ring)
- **四问**:*Why* 第一眼质感跃升;*What NOT* 不迁 100 屏、不做暗色、不做 Blur;*How* `useRevaFonts()` 上提 app root + legacy 数字 typo 指 `IBMPlexMono` + `ReadinessRing` 加 withTiming sweep;*Risk* 纯视觉、OTA、可逆,小屏验证不溢出。
- **ASCII**:`app/_layout.tsx 根 useRevaFonts() → 全屏数字渲 IBMPlexMono` · `RevaKit.tsx ReadinessRing + revaMotion.withTiming`
- **验收**:全 App 数字等宽;ring 出现时 420ms sweep;小屏不溢出;无数据请求破坏。
- **反馈环**:本地 Sim → OTA。**(本人真机视觉验收我来做)**

#### 0C · Daily Artifact 契约 + 抗习惯化埋点
- **四问**:*Why* Reva 的季度外环需要每日仪式买留存 runway;*What NOT* 不新增并列 dashboard,不做 vanity score;*How* 定义 `DailyArtifact` 前端类型和转换器,从现有 `agenda/today`、Twin freshness、HealthKit/Garmin sync 状态、safety 摘要组装;记录 impression/accepted/completed/skipped_reason/week_index;*Risk* 新指标不能制造医疗 claim,只表达观察状态和行动建议。
- **ASCII**:
  ```
  agenda/today + twin freshness + device sync + safety summary
      ↓ DailyArtifact presenter
  {state_label, top_action, evidence[<=3], confidence, freshness, safety_boundary, actions}
      ↓
  Today hero / Chat card / Watch summary 共用
      ↓
  impression + accept + complete + skip_reason + week_index
  ```
- **验收**:Daily Artifact 有稳定类型、mock、空状态和小屏布局;跳过必须有 reason;行动接受率可以按周聚合;不展示超过 1 个 top action。

---

### Phase 1 —— Home 驾驶舱无缝 + Chat 卡片 action 地基(两轨并行,主 OTA)

#### 1A · Home 第一屏升级为 Health OS 驾驶舱 + 关接缝
- 顶部:身份/日期/Twin 状态/数据新鲜度(含 HK/Garmin/Watch 最近同步时间)。中心:Daily Artifact,只保留**一个** top action。证据区:最多 3 个实时信号条(睡眠/HRV/心率/活动/体重/血氧/压力),带 freshness/provenance。操作区:完成 / 跳过并选 reason / 改时间 / 问 Reva。风险:仅有明确数据依据才进前景。
- 关接缝:四张子卡迁 `revaColors`+Reva 字体。**只换视觉层,不改数据契约 / React Query。**
- **验收**:小屏不溢出/不挤压;第一屏 ≤3 焦点;现有 Today 数据请求不破坏;Daily Artifact D1 使用、top action accept/skip/complete 都能记录;OTA 可发。

#### 1B · Chat 卡片 action 契约(为 Goal 2 与 Goal 3 共用打地基)
- **四问**:*Why* 卡片能「做事」(确认/完成/查依据/加入今天)才从装饰变可执行对象;*What NOT* 本阶段不做流式交织(Phase 2)、不路由到 orchestrator(先小);*How* 给 `CardSpec`/`ServerCardDescriptor` 加可选 action 契约 `{action,endpoint,payload}` + chat 侧 dispatcher 复用 `services/actionCompletion.ts`/`writeIntents.ts` + 去掉 `RevaAgentView.tsx:54` 的卡片过滤;*Risk* **R4:任何写卡片恒 `manual_confirm`,不诊断/不开方**。
- **ASCII**:
  ```
  卡片按钮(确认/完成)
      ↓ CardSpec.onAction
  chat dispatcher → services/writeIntents.ts (draft) / actionCompletion.ts
      ↓ POST /write-intents 或 /agenda/complete (manual_confirm 门)
  backend write_intent_service (kind 白名单 fail-loud) / complete_agenda_event (原子认领)
      ↓
  invalidate ['timeline','today'] → 卡片翻态
  ```
- **依赖洞察**:这条 action 契约**同时是 Goal 3 on-watch「卡片→可执行」的前置**。**只在 chat 里建一次(反馈环最快)。**
- **验收**:卡片确认走 WriteIntent 草稿;完成走 `/agenda/complete`;卡片渲染 + action 有 Jest 覆盖;未知卡片 no-op 不崩。
- 本阶段 slack 跑 **Spike A**(见 §8),为 Phase 3 的 HK 后台 go/no-go 提供依据。

#### 1C · 5 分钟 on-ramp(让深度可见)
- **四问**:*Why* OpenHealth 证明能跑、能看见、能理解比深度更先决定传播;*What NOT* 不做营销 landing,不引入假医疗承诺;*How* 新用户/访客模式提供示例报告或合成数据,60-300 秒内展示一次安全脑拦截、一次证据卡、一次 Daily Artifact top action;真实用户可从 HealthKit 授权直接进入同一体验;*Risk* 示例数据必须明显标注 demo,不能污染用户 Twin。
- **ASCII**:
  ```
  首次打开 → 选择 HealthKit / 示例报告 / 合成数据
      ↓
  生成 demo Twin + safety finding + Daily Artifact
      ↓
  Chat 展示证据卡 + 可执行草稿卡
      ↓
  用户看到 Reva 的安全脑与行动闭环,再决定连接真实数据
  ```
- **验收**:新用户 5 分钟内能看到安全规则/证据卡/top action 三件事;demo 与真实数据隔离;退出 demo 不留 PHI;不新增并列主路径。

---

### Phase 2 —— Chat 流式卡片融合 + watch 上设备(主 OTA + 一次 EAS)

#### 2A · 真·对话内融合(流式卡片)
- **四问**:*Why* 大模型回复中段直接长出可执行卡片 = 护城河(因果账本的 finding 变成对话里的可执行卡);*What NOT* 不让模型自由生成任意 UI(白名单 schema),不把 observation 包装成因果;*How* 新增流式 `card` SSE 事件带位置锚 + `useChatEngine` 插入逻辑 + **backend translator**:`SpecialistFinding`/`ProposedCard`/safety → `ServerCardDescriptor[]`(桥接搁浅的 orchestrator 输出);新增 `safety`/`proposed_card`/`discovery` 卡类;*Risk* 流式插入别 jank(`ChatBubble` 流式中降级纯 `<Text>`);**范围**:在 `/agent/stream` 做 translator 比把 mobile chat 整体路由到 `stream_orchestrator` 小,优先 translator。
- **ASCII**:
  ```
  用户问「为什么建议补镁」
      ↓ /agent/stream (SSE)
  backend translator: SpecialistFinding/evidence/discovery → ServerCardDescriptor (白名单 type)
      ↓ SSE event: {type:'card', anchor:pos, descriptor}
  useChatEngine 插入 → registry 渲染(未知=no-op)
      ↓ 卡片 action → §1B 契约(manual_confirm)
  ```
- **验收**:输入「吃了两个鸡蛋一杯牛奶」→ 文本总结 + 饮食卡 + 确认按钮(草稿);问「今天怎么练」→ 建议 + workout 卡 + 风险提醒;问「为什么补镁」→ 依据卡非长文;问「最近睡眠为什么变好」→ discovery 卡以 `observation/hypothesis/validated_effect` 分级展示,弱证据弱表达;卡片渲染单测覆盖;**处方/激素指标 claim 降级 clinician_review**。

#### 2B · 把已编译的 watch app 真正上设备(诚实文案)
- **四问**:*Why* watch 已编译从未上真机,这是整个 watch 程序的长杆;*What NOT* **不承诺表冠长按说话**(系统保留);不做表上自由诊断对话;*How* 一次**交互式 `eas build`(iOS internal/preview,异步)**物化两 watch bundle id 凭据 → TestFlight → 真机配对验证;文案重构为「**点 Reva / 说 Siri 短语**」;新增 watch 端 AppIntent + AppShortcutsProvider;Action Button(Ultra 3)绑 AppIntent;*Risk* 凭据 loop(memory `project_watch_companion_eas_build_signing`);`withHealthKitCleanup` 交互(若同 build 加 HK entitlement)。
- **ASCII**:
  ```
  Watch「按住说话」按钮 / Siri 短语 / Action Button(Ultra)
      ↓ WatchDictation.present() / AppIntent
  意图分类: 饮食|运动|症状  ──→  现有 /watch/* 记录管线(草稿 manual_confirm)
                              └─ 健康问答 → 默认转手机(本轮不接自由 LLM,见 §5.B / §8 Spike B)
  ```
- **验收**:表上说「晚饭吃了牛肉面」→ 手机出现待确认饮食草稿;说「刚跑 20 分钟」→ 运动记录;**不声称第三方已接管表冠长按**;QuickRecord 既有水/俯卧撑/跑步/饮食/症状不回归。

---

### Phase 3(条件触发,非本周)—— HK native 后台 + watch LLM(由 Spike 决定)

- **3A · HK native 后台投递 + Signal Contract** —— **仅当 Spike A 证明它比前台同步多出的新鲜度值一个 EAS cycle**:加 `background-delivery` entitlement(防 `withHealthKitCleanup` 误删)+ `HKObserverQuery` + `enableBackgroundDelivery` per type + 本地上传队列;第一批 steps/HR/RHR/HRV/sleep/activeEnergy/weight,第二批 BP/SpO2/体温/VO2/ECG。配 §5.C 的服务端同意门 + provenance;同时补 `SeriesType` 式契约(固定单位、聚合语义、source priority、coverage matrix、freshness),避免 AI 在同名不同义的信号上推理。EAS build + TestFlight 真机验证。文案「后台自动定期同步」。
- **3B · watch LLM 一次性短答** —— **由 Spike B 决定 scope**(大概率落「one-shot 短安全建议或『去 iPhone 看』」,非对话)。必须满足 §5.B 三条阻断。

---

## 8. 长杆与 Spike(先 de-risk,别盲目投 EAS)

- **单次 EAS 设备签名里程碑**(§4.5):解锁 watch ship(2B)+ HK 后台 entitlement(3A)+ watch AppIntent 真机验证。**先 de-risk 这一个,后续真机活叠在它后面。** 需用户(真 Apple ID/设备)配合。
- **Spike A(HK 后台,timebox 1–2 天,de-risk 一个 L)**:证明 ① `enableBackgroundDelivery`+`HKObserverQuery` 能在 ~秒级唤醒窗内 `syncRecentDays(1–2)`;② 新 entitlement 过 `withHealthKitCleanup` 且拿到合法 profile;③ 诚实期望:多数类型 iOS 节流 → **若比前台同步只多边际新鲜度则推迟**。
- **Spike B(watchOS LLM 流式,timebox M,de-risk 一个 L + 防过度承诺)**:证明 SSE 能否在 `WKExtendedRuntimeSession`/电量/短运行约束下消费;大概率结论 = **scope 成 one-shot 短答**。
- **不需要 Spike**:watch native target 已编译、语音记录已接、EAS 签名部分预烘焙 —— 剩的是「有没有真的签名上过设备」的 build 任务,不是 spike。

---

## 9. 我们不承诺什么(诚实声明 —— 文案红线)

- ❌ **不承诺「按住表冠说话」** —— 系统保留,第三方拿不到。文案用「点 Reva / Siri 短语 / Action Button(Ultra)」。
- ❌ **不承诺 HK 实时后台同步** —— iOS 对多数类型节流到 hourly/daily,best-effort。文案用「后台自动定期同步」。
- ❌ **不承诺表上自由诊断对话** —— R4/R18:表上只短安全建议或转手机。
- ❌ **不承诺无人值守自治写敏感数据** —— 承重墙只 `measurement_prompt` 自治;语音记录/卡片 action/医疗写全 `manual_confirm`。
- ❌ **不承诺「换个配色就高级」** —— token 已在;高级感靠 mono numerals + 动效 + 减焦点 + 关接缝。

---

## 10. 待你拍板(open decisions)

1. **on-watch LLM:本轮推迟,先用 symptom 范式 one-shot 短答?**(推荐:是。自由对话 NO-GO 直到补 §5.B 三门 + spec + 对抗测试。)
2. **HK native 后台:先只发前台自动同步(Phase 0),Spike A 证明值得再投 EAS?**(推荐:是。前台同步已消除绝大部分手动痛点,后台是边际收益。)
3. **watch 上设备的交互式 EAS 签名:何时跑?**(需你真机/Apple ID 配合;它 de-risk 3/4 目标。建议 Phase 2 异步跑一次。)
4. **Daily Artifact 是否命名为 Reva Today / Readiness / Today Action?**(推荐:先用中性 `Daily Artifact` 内部名,UI 文案用「今日状态」+「今日最重要行动」,避免过早固化 vanity score。)
5. **本轮范围:是否就锁定 Phase 0 + Phase 1(全 OTA、零平台风险、当天可验),Phase 2/3 下一轮?**(推荐:是。felt value 最高、风险最低。)

---

## 11. 测试与验证矩阵

| 层 | 闸门 |
|---|---|
| Mobile | `cd mobile && npx tsc --noEmit --pretty false`;Daily Artifact presenter 单测(空状态/一个 top action/最多 3 证据/skip reason);Chat 卡片渲染 + action + discovery 证据分级 Jest;HK auto-sync service 单测(未授权不同步 / 冷却内不重复 / 回前台触发 / 失败不阻断 UI);真机小屏+大屏+深浅色 |
| Watch | Xcode build watch target;真机 dictation;QuickRecord 既有水/俯卧撑/跑步/饮食/症状不回归 |
| Backend | HK import 既有测试通过;**新增**:import 服务端分类型同意门测试 + provenance 写入测试;卡片 schema 白名单 + WriteIntent 权限/草稿测试;语音 parse 永不写库的对抗测试;`_auto_confirm` 显式 fail-closed 白名单红绿测试 |
| 集成闸 | 部署前全增量测试 CI 模式(`DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`)合跑 + 查 main CI 真色;敏感面(语音写/同意门/watch)过一次 Codex 跨家族 capstone |

---

## 12. 第一批实现入口(Phase 0,精确到文件)

1. `mobile/app/_layout.tsx:155-159` —— AppState「active」加前台 HK 自动同步(门控 `getHealthKitAuthorized()` + 冷却)。
2. `mobile/services/appleHealthAutoSync.ts`(新)—— 冷却/去重/失败降级封装,读 `healthkit_authorized_v1`/`healthkit_last_sync_v1`,调 `appleHealth.syncRecentDays`。
3. `mobile/app/_layout.tsx`(根)`useRevaFonts()` 上提 + `mobile/constants/theme.ts` 数字 typography 指 `IBMPlexMono`。
4. `mobile/components/reva/RevaKit.tsx:166-202` —— `ReadinessRing` 加 `revaMotion` withTiming sweep。
5. `mobile/components/reva/DailyArtifact.tsx`(新) + presenter/mock/test —— 组装状态判断、一个 top action、≤3 证据、confidence/freshness/safety boundary、complete/skip/ask actions。
6.(Phase 1)`mobile/components/chat/cards/{types.ts,registry.tsx}` —— 加 action 契约 + `discovery` 卡;`mobile/hooks/useChatEngine.ts` chat 侧 dispatcher;`mobile/components/reva/RevaAgentView.tsx:54` 去掉卡片过滤;四张子卡(`ActivityRingBar`/`VitalsGrid`/`MedicationCheckin`/`BodyStatsRow`)迁 `revaColors`。
7.(Phase 1)`mobile/app/onboarding.tsx` 或现有 onboarding 入口 —— 增加示例数据/示例报告 demo path,只展示安全脑+证据卡+Daily Artifact,不得写入真实 Twin。

> 改完任何 backend request/response schema 后必须 `cd mobile && npm run generate-types` 并提交(防静默漂移)。

---

## 13. Watch 实施细化(Code 直接照做 · 已拍板)

> **本节是给编码 agent 的 task-by-task 实现 spec。** 用户已拍板:**① 对话 = 一问一答短答(过安全门 + 复杂转手机);② 先验通 EAS 设备签名,再叠对话功能。**
>
> **不可妥协前置(每个 task 都受约束,违反即 reject)**:
> - **R4**:不诊断/不开方/不给剂量;表上答复保守措辞、可转手机。
> - **写恒 draft+confirm**:任何语音记录走草稿出口,服务端 draft-by-default,绝不静默自动写。承重墙只 `measurement_prompt` 自治,语音记录/医疗写永远 `manual_confirm`。
> - **安全门 fail-loud**:LLM 答复出屏/TTS 前必须过 SafetyGuardian 确定性门;评估失败/部分失败绝不静默当安全。
> - **合规范本** = `backend/app/api/watch.py` 的 `/watch/symptoms`(`record_symptom`):flush-not-commit、**禁 build_twin**(用极简 `HealthTwin()`)、`_fill_problem_red_lines(..., raise_on_error=True)`、`evaluate_rules_with_status` 查 `failed>0 → evaluation_failed`、user_id 取自 token、单次 commit。**`/watch/ask` 必须照抄这套骨架。**
> - **从 origin/main build**(watch 代码在 main,design 分支零净改动);改 backend schema 后 `cd mobile && npm run generate-types`。
> - **不碰 rokid/mac**(`apps/rokid-*`、`apps/mac`、`mobile/modules/rokid-bridge`、`backend/app/api/rokid.py` 由其它 session 活跃开发)。

### 任务依赖图
```
W0 (签名 de-risk, 用户驱动) ──gate──▶ W3/W4/W5 (watch native, EAS)
W1 (/watch/ask 后端安全门) ─┐  纯后端, 不卡 W0, 先做
W2 (语音写 fail-closed 白名单)┘  纯后端, 不卡 W0, 先做
W1 ─▶ W3 (watch 对话 UI 调 /watch/ask)
```
**先做 W1+W2(纯后端,独立部署,不卡签名),W0 通过后再做 W3/W4/W5。**

---

### W0 · 签名 de-risk(用户驱动 · gate · 非代码)
- **目标**:证明现有已编译 watch app 能装上真机、Reva 表盘 App 真出现。**这是 W3+ 的前置闸。**
- **做什么**:从干净 `origin/main` worktree 起一次**异步** iOS build(watch 已嵌入)→ TestFlight/internal → 装机。命令:`./scripts/mobile-local-archive.sh`(用户一键,本地归档+altool 上传,需根 `.env` 的 `APP_STORE_CONNECT_*`)或 `eas build -p ios --profile production`(远端异步)。**不等**(15–25min)。
- **验收(用户在真机确认 4 点)**:① 手表出现 Reva App;② 点开进主界面(TodayStatus/QuickRecord);③ 现有语音记录可用(「喝了一杯水」→ 手机出现记录);④ 表冠 rotation 调数值可用。
- **已本地确认**:watch 核心 `cd apps/watch && swift build` = Build complete;withWatchApp 自 06-16 挂载,06-21~23 多个 iOS 生产 build FINISHED → 签名极可能已通。**4 点全绿 → 解锁 W3/W4/W5。**

---

### W1 · 后端 `/watch/ask` 一问一答安全门(纯后端 · 先做 · 独立部署)
- **目标**:腕上一句健康提问 → 后端出**一句短安全建议**,危险/复杂 → 「去 iPhone 看详情」。
- **文件**:
  - `backend/app/api/watch.py` —— 新增 `POST /watch/ask`(照抄 `record_symptom` 安全骨架)。
  - `backend/app/services/guidance_validator.py` —— 复用 strip/soften 覆盖答复文本出口。
  - `backend/tests/test_watch_ask.py`(新)。
- **端点设计(逐步,严格按合规范本)**:
  1. 入参 `WatchAskIn{ text: str }`;`text` 空/超长(沿用 `_SYMPTOM_MAX_LEN`)→ 400;user_id **取自 token**。
  2. **先跑安全态闸**(不依赖 LLM):极简 `HealthTwin()` + `_fill_problem_red_lines(db, uid, twin, set(), raise_on_error=True)`(失败 → `evaluation_failed=True`,**不 return**)+ `evaluate_rules_with_status(twin)`;`failed>0` → `evaluation_failed=True`。
  3. **LLM 短答**:走 orchestrator lite/单轮(复用现有 provider failover);**prompt 强约束**:≤2 句、保守、不诊断/不开方/不给剂量、中文。**禁请求内 build_twin**(同范本)。LLM 失败 → 走 escalate 兜底,不抛 500。
  4. **答复必过 `guidance_validator`**(strip/soften 量化/命令式饮食处方 + 命令式训练指令);命中 red_line → 改投保守措辞。
  5. **escalate 决策**:`evaluation_failed` 为真 **或** 安全闸命中 CRITICAL **或** 问题涉处方/剂量/影像/诊断意图 → **不返回自由答复**,返回 `{ answer: <短安全提示>, escalate_to_phone: true, requires_medical_attention: <bool> }`;否则返回 `{ answer: <短答>, escalate_to_phone: false }`。
  6. **fail-loud**:`evaluation_failed` 时答复体必须含「本次未能完成自动安全筛查,请勿据此判断为安全;不适请就医,紧急拨 120」(照抄范本 evaluation_failed advisory),`requires_medical_attention=True`。
  7. **单次 commit**(若落了 AskLog/审计);可选落一条 `client-events`/审计行,不写任何健康事实表。
- **安全不变量**:不诊断(给方向+就医动作,不给病名)、保守措辞、评估失败 fail-loud、user_id 取 token、禁 build_twin。
- **验收**:① 「我今天适合高强度训练吗」→ 短答 + escalate_to_phone=false(若安全态正常);② 「我这个胸痛是不是心梗」→ escalate_to_phone=true + requires_medical_attention=true,**不给诊断**;③ 安全规则注入失败 → answer 含 fail-loud advisory;④ 答复永不含命令式剂量/饮食处方(guidance_validator 测试)。
- **测试**(`test_watch_ask.py`):正常短答 / 处方意图转手机 / `evaluation_failed` fail-loud / guidance_validator 覆盖答复出口 / user_id 取 token 不信客户端。
- **反馈环**:纯后端 → `deploy.sh -b`。**不卡 W0。**

---

### W2 · 语音写 fail-closed 白名单(纯后端 · 先做)
- **目标**:消除 `_auto_confirm_fast_record_args` 的隐式白名单 fail-open(弱模型把 supplement 误判处方剂量会静默自动写)。
- **文件**:`backend/app/services/agent_executor.py`(`_auto_confirm_fast_record_args`,约 `:869`);`backend/tests/test_agent_executor.py` 或新 `test_watch_voice_record_failclosed.py`。
- **做什么**:自动确认前**显式断言** `record_type ∈ {water,weight,bp,diet,checkin,supplement}` 且 `∉ NEVER 集`(medication/dose/adherence/financial);未知/越界 kind → **退回 `manual_confirm`**(不静默放行),对齐 `write_intent_service._execute` unknown-kind → ValueError fail-loud 模式。
- **安全不变量**:语音记录恒走草稿出口(`/diet/voice/parse` 只解析不写库 → 客户端确认后 POST `/diet/records`);NEVER 类永不经语音偷渡自动写。
- **验收**:① 正常 6 类 fast-record 行为零变化;② 构造 `record_type='medication'`/`'dose'` 的自动确认请求 → **不自动写、退 manual_confirm**(对抗测试,换回隐式白名单必红);③ 未知 kind → manual_confirm。
- **反馈环**:纯后端 → `deploy.sh -b`。**不卡 W0。**

---

### W3 · Watch 对话 UI(native SwiftUI · W0 通过后)
- **目标**:点开 Reva 表 App → 大「按住说话」按钮 → 系统听写 → POST `/watch/ask` → 渲染短答 / 「去 iPhone 看详情」。
- **文件**:
  - `apps/watch/WatchApp/` 新增 `RevaVoiceAssistantView.swift`(对话页)。
  - `apps/watch/Sources/WatchCompanionCore/WatchBackendRequest.swift` —— `allowedRoutes` 加 `"/watch/ask": ["POST"]`(`:13-20`)。
  - 复用 `WatchDictation.swift`(`present()` 系统听写)+ `WatchDirectAPIClient`/`WatchBackendRequest`。
  - `apps/watch/Tests/WatchCompanionCoreTests/` 加 request 构造测试。
- **做什么**:
  1. 主入口卡:大「按住说话」按钮(`WatchDictation.present()` 一版)。
  2. 意图三分:**饮食/运动/症状** → 现有 `/watch/*` 记录管线(草稿 manual_confirm,不变);**健康问答** → `POST /watch/ask`。
  3. 状态机:处理中 / 成功(短答)/ **需转手机**(escalate_to_phone=true 时显「详情已发到 iPhone」+ 不展开长文)/ 风险提示(requires_medical_attention)。
  4. **每次原生网络调用 Promise/closure 必带超时 + 查 ok**(memory `feedback_rokid_native_calls_need_js_timeout` 的镜像:闭包不来要兜底,失败置 failed 状态不假成功)。
- **安全不变量**:表上**不展开自由诊断长对话**;escalate 时只显短提示 + 转手机;答复来自 W1(已过安全门),UI 不自行加医疗结论。
- **验收**:表上「我今天适合高强度训练吗」→ 短答;「这个胸痛…」→ 「详情已发 iPhone」+ 风险提示;记录类仍走草稿。
- **反馈环**:Xcode watch target build → **EAS build(异步)** → 真机(W5)。

---

### W4 · 入口(表冠 / Action Button / Siri · W0 通过后)
- **目标**:把「按一个就开口」做到平台允许的极致(诚实文案)。
- **文件**:`apps/watch/WatchApp/`(App Intent + AppShortcutsProvider)、`RevaComplication.swift`(已存在,tap→launch)、`RevaVoiceAssistantView`(crown rotation)。
- **做什么**:
  1. **App Intent + AppShortcutsProvider**(watch 端净新)→ 「Hey Siri,用 Reva 记录/问一下…」;表冠长按本就唤 Siri = 间接「表冠」路径。
  2. **Action Button(Ultra 3)** 绑该 AppIntent → **「按一个物理键就开口」对锚点用户的真解**。
  3. **表冠 rotation** 在对话/记录页选项/调数值(`.digitalCrownRotation`,QuickRecord 已用,扩到对话页选意图)。
  4. complication tap → 直接进 RevaVoice(已有 complication,接 deeplink)。
- **安全/文案红线**:**绝不写「按住表冠说话」**(系统独占);文案用「点 Reva / 说 Siri 短语 / Action Button」。
- **验收**:Action Button 唤起 Reva 录入;Siri 短语可触发;表冠 rotation 选意图/调值;complication tap 进对话页。
- **反馈环**:EAS build → 真机(Siri/AppIntent/Action Button 需真机 + Apple ID 验)。

---

### W5 · EAS build + 上设备(异步 · W3/W4 完成后)
- **目标**:把对话+入口随 iOS app 嵌入 watch target 发到 TestFlight,真机验证。
- **做什么**:从干净 origin/main(已含 W3/W4)起**异步** `eas build -p ios --profile production` 或 `./scripts/mobile-local-archive.sh` → TestFlight → 真机。**不等。**
- **验收**:真机走完 W3/W4 全部验收点;QuickRecord 既有水/俯卧撑/跑步/饮食/症状不回归。
- **风险**:watch 两 bundle id 凭据(若 W0 已通则已建);`withHealthKitCleanup` 交互(若同 build 含 HK entitlement)。

---

### Watch 测试与闸门汇总
| 层 | 闸 |
|---|---|
| 后端 | `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai pytest tests/test_watch_ask.py tests/test_watch*.py -q`(直读 passed/failed,**不 `\| tail`**);W1/W2 对抗测试换回旧行为必红 |
| watch native | `cd apps/watch && swift build`(核心)+ Xcode watch target build;真机 dictation + Siri/AppIntent |
| 部署序 | W1/W2 先 `deploy.sh -b`(纯后端)→ `npm run generate-types` 若改 schema → W3/W4 随 W5 EAS build 上设备 |
| 安全复审 | `/watch/ask` 属新安全行为(§8.1)→ 必过 safety-privacy-reviewer + 一次 Codex 跨家族 capstone |
