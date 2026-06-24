# Rokid CXR-L 官方 SDK 文档 × 当前代码 · 架构一致性 Review

> 日期: 2026-06-24
> 依据: Rokid AR Platform · CXR-L SDK 文档 v1.0.3(知识库 33 篇,~3000 行)—— **官方权威**
> 对象: `mobile/modules/rokid-bridge/`(iOS native + JS gateway)· `mobile/app/rokid-health.tsx` · `backend/app/api/rokid.py`
> 关系: 在 [delta 设计](2026-06-23-rokid-reva-delta-design-and-mvp-plan.md) + [council 结论](2026-06-23-rokid-reva-council-review-conclusion.md) 之上,用**官方 SDK 文档**校准架构假设(前两篇靠代码实勘 + 真机经验,本篇靠 SDK 规范)。

## 一句话

代码工程质量高(防御态、诊断完备、BLE 门控扎实),但**有一条核心架构假设与 SDK 规范直接冲突**,且**一条 SDK 硬约束被当成偶发 lazy-init 而非一等决策**。两条都不是 bug,是「按文档该怎么搭」的结构问题。

---

## SDK 规定的能力门控(权威矩阵,逐字)

来源 `03-开发流程与状态机.md` + `iOS/03-连接与会话.md` 能力可用矩阵:

| 状态 | 音频 | 拍照 | 自定义指令 |
|---|---|---|---|
| 已鉴权、链路就绪、**场景未构建** | 否 | 否 | 否 |
| customView **且视图已运行** | 是 | 是 | **否** |
| customApp **且应用已拉起** | 是 | 是 | 是 |

SDK 三处明确警告(拍照/音频/指令各一篇):
- 拍照:「**避免仅在「已连接」状态下触发拍照**」(`iOS/07-拍照.md`)
- 音频:「**不要**在仅完成连接、场景未就绪时调用 `startRecord` / `feedAudio`」(`iOS/06-音频.md`)
- 指令:「**不得在仅链路连通、应用尚未拉起时发送自定义指令**」「**仅 customApp**」(`iOS/08-自定义指令.md`)

**关键结论:音频/拍照不是「可选地依赖 CustomView」,是 SDK 层强依赖「场景构建完成」(= customView 视图运行 或 customApp 拉起)。**

---

## F1 ·【核心矛盾】拍照路径没按 SDK 做「场景构建」门控,与设计自述冲突

**SDK 要求**:`takePhotoWithData` 须在 customView 运行 / customApp 拉起后调用。

**代码实况**:
- `startRecord`(音频)**正确**硬门控 `hasCustomViewMediaSession()` → 无场景返回 `rokid_audio_session_not_ready`(`RokidBridgeModule.swift:1099+`)。✅
- `takePhotoBase64`(拍照)**只**门控 `isAuthenticated()` + `iosBleConnected()`;scene evidence 仅写进诊断字符串,**不门控**,直接盲发 `takePhotoWithData`(`RokidBridgeModule.swift:760+`)。❌
- JS gateway 同构:`captureAttemptReady = bridgeReady && sdkLinked && (!ios || (authorized && bleReady))` —— **不要求 `customViewRunning`**(`index.ts:556`)。无场景时 `captureState='degraded'`(非 blocked),UI 仍让用户「主动触发」拍照(`rokid-health.tsx:2078`)。

**后果**:无场景时 `takePhotoWithData` 的 callback 可能永不到 → 靠 JS 侧 25s `Promise.race` 超时(`takeRokidPhotoBase64WithTimeout`)→ 落手机兜底。**即「眼镜拍照大概率 25s 空等后兜底,真正在跑的是手机相机」**。

**这跟 delta/council 的「CustomView 降级为显示态,饮食不依赖它」直接冲突**:按 SDK,眼镜拍照**恰恰依赖** CustomView running(显示态那个 view 本身就是解锁拍照的 scene)。「不依赖」作为**韧性姿态**对(CustomView 失败别阻塞手机兜底);作为**「眼镜拍照不需要 scene」的理解**错。

**修正**(二选一,推荐 A):
- **A(对齐 audio)**:`takePhotoBase64` 加 `hasCustomViewMediaSession()` 门控;食物流程在拍照前确保 `openCustomView` 已 running(显示态 view = scene)。无场景 → 不空等眼镜,`captureState` 在无 scene evidence 时 `recommendedSurface='mobile'`,直接走手机,省掉 25s。
- **B(显式承认兜底优先)**:保留盲发,但把「眼镜拍照前必须先 openCustomView」写进流程 + 文档,且 UI 不暗示「走眼镜」直到 scene evidence 为 hard。

---

## F2 ·【硬约束被动发现】CxrClient 单例一次只能一个 session mode,应升为一等决策

**SDK**:`03-状态机` 的 `SessionType{CustomView | CustomApp}` 是**二选一**;iOS 在 `RGCxrClientInitializationOptions` + `CxrClient.initialize(mode:)` 时定 mode(`iOS/03-连接与会话.md`)。

**代码已撞上**:`ensureCustomAppInitialized` 里——已 customView 初始化后请求 customApp → `failure_already_initialized:customView`、`ready=false`、`relaunchRequired=true`(`RokidBridgeModule.swift:1993+`)。**证明:食物/语音(customView)与俯卧撑(customApp)在同一次 App 启动内互斥。**

**问题**:当前 mode 由「谁先点谁 lazy-init」决定(`ensureCustomViewInitialized` / `ensureCustomAppInitialized` 在各能力入口被动触发),把全局唯一的 mode 决策交给了**偶然的点击顺序**。用户先拍食物(锁 customView)再进俯卧撑 → 被 `rokid_cxrl_wrong_session_mode` 挡,需重启 App,而 UX 没把这条讲清。

**修正**:
- session-mode 升为 **App 级显式状态**:进入俯卧撑前若已 customView,明确提示「切换眼镜会话模式需重启 App」(`relaunchRequired` 已在诊断里,接到 UX 即可)。
- 这条**直接强化 council 的「食物领头、俯卧撑最后」**——不只是飞轮排序,是 **SDK 物理约束**:两个 mode 不能同活。
- `operation_id` 账本的 `type`(`capture_food`/`voice_command` ⇒ customView;`pushup_session` ⇒ customApp)天然标了所需 mode → 可作「本次启动锁定哪个 mode」的判据,**账本设计与 SDK 约束在此咬合**。

---

## F3 · 自定义指令仅 customApp —— 当前隐式遵守,记一笔约束

**SDK**:`sendCustomCmd` **仅 customApp**,customView 下禁用(`iOS/08-自定义指令.md`)。

**代码**:俯卧撑事件走眼镜端 Android APK **直接 POST 后端**(G→S,`RevaPushupEventClient.kt`),不经 `sendCustomCmd` → **没踩雷**。但若将来想用 `sendCustomCmd` 给眼镜端 App 下发指令,必须 customApp + `openApp` 成功 + 场景构建后,且与 customView 互斥(见 F2)。无需改动,记入约束清单。

---

## F4 · 「场景构建完成」判据是软证据,媒体门控该只认 hard 证据

**SDK**:用 `customViewRunningEventPublisher` 判 running(`iOS/04-眼镜端自定义View.md`)。

**代码**:真机上 running 事件不稳,故用多信号推断 `hasCustomViewSessionEvidence()` / `displayInferred` / 2s settle 后 `markCustomViewOpenUnconfirmed`(`RokidBridgeModule.swift:612+`)。工程上合理,但**软证据(`customViewDisplayInferred`)被 audio 的 `hasCustomViewMediaSession()` 当 scene-built 放行** → 场景其实没建好时 `startRecord` 仍 resolve ok,录音其实没数据。

**修正**:evidence 分级——**hard**(open callback success / typed running notify)vs **soft**(displayInferred / settle 推断)。媒体能力(audio/photo,见 F1)门控**只认 hard**;soft 仅用于 UI 文案,不用于解锁能力。

---

## F5 · native-call-timeout 仍未普适(council day-1,复述对齐)

SDK 各能力都是「调用 → 异步 callback」。BLE 掉线 / 眼镜崩时 callback 永不来。现状:只有 `takePhotoBase64` 在 JS 侧有 `Promise.race`(25s);`openCustomView` 在 swift 侧有 2s settle 兜底;`queryApp/openApp/startRecord/installApp/updateCustomView` 仍**裸调**。与 [council day-1](2026-06-23-rokid-reva-council-review-conclusion.md) 「native-call-timeout 普适化到 5 个 bridge wrapper」一致,无新增。

---

## 与既有结论的关系

- **不推翻** delta/council 的任何已定结论(非 greenfield、operation_id 薄账本、飞轮排序、+3 不变量)。
- **新增** SDK 文档校准出的两条结构修正(F1 拍照门控、F2 session-mode 一等决策)+ 一条加固(F4 evidence 分级)。
- **F2 给 council 的飞轮排序补了物理依据**:食物/俯卧撑分属两个互斥 mode,不只是「先做谁」,是「一次只能活一个」。

## 建议落地顺序(承 council,最小改动)

1. **F1-A**(高价值低风险):`takePhotoBase64` + JS `captureState` 对齐 audio 的 scene 门控;无 scene 直接走手机,省 25s 空等。**先写测试**(无 scene evidence → captureState 不暗示眼镜 / 不空等)。
2. **F4**:evidence 分级,媒体门控只认 hard。与 F1 同一 PR。
3. **F2**:session-mode 升 App 级显式状态 + relaunch 提示接 UX;与 operation_id 账本 type→mode 映射一起做(council day-3)。
4. **F5/F3**:随 council day-1/day-3 既定计划,无新增。

---

*方法:官方 SDK v1.0.3 能力矩阵(权威)× 代码逐函数核(takePhotoBase64 / startRecord / ensure*Initialized / index.ts captureState)× 与既有 delta/council 结论对账(只增不翻)。最高置信项 = SDK 文档逐字警告 vs 代码门控的直接比对(F1 拍照、F2 mode 互斥)。*
