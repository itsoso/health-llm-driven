# Rokid CXR-L 架构 Review · Codex 建议对抗裁定 · 终裁结论

> 日期: 2026-06-24 · 方法: adjudication(官方 SDK v1.0.3 能力矩阵 + 7 条对抗裁定 + 编排者 F1-F5 + council 结论四方对账)
> 裁定对象: Codex 6 条 claim + fix 顺序
> 前序: [SDK 文档×代码 review (F1-F5)](2026-06-24-rokid-sdk-doc-vs-code-architecture-review.md) · [council 结论](2026-06-23-rokid-reva-council-review-conclusion.md) · [delta 设计](2026-06-23-rokid-reva-delta-design-and-mvp-plan.md)
> 方法说明: 7 个独立 agent 逐行 Read/grep 实证每条 claim(默认 imprecise,主动抓夸大),再合成裁定。权威 = SDK 能力矩阵 > 代码自述/设计假设。

## 1. 终裁一句话

**Codex 的 review 经对抗核证整体成立——6 条无一被证伪,但只有 2 条配得上 P0,其余 4 条降级。** 对抗验证改变的是 **severity 与精度**,不是方向。Codex 把「松/盲发」当统一病症,核证后裂成两个不同缺陷(照片**完全无场景门控** vs 音频**门控但只认软证据**),对照 SDK 后**收敛成同一修复**。C5 gateway「误报 ready」属实但是 **cosmetic 标签乐观**(动作侧已被 timeout+readResultOk 守住);C6 APK「主流程」措辞被证夸大(已 bundle-first + 探测门控 + 二级 UI);C7 单 CustomApp 是**正确北极星、错误 v0 指令**。**真正的 P0 只有两条:session-mode 显式化(C1)+ 媒体 hard-evidence 门控(C2+C3+C4 合并)。**

## 2. 逐条裁定表

| Claim | 裁定 | 校正后真相(file:line) | Severity |
|---|---|---|---|
| **C1 singleton session mixed** | confirmed(带冷启动默认 caveat) | customView 锁**非无条件**:`preferredCxrSessionMode`(`RokidBridgeModule.swift:44` static 默认 nil)在 auth 时序下的冷启动默认值。`requestAuthorization:494`→`ensurePreferredCxrSessionInitialized:497`→nil 走 else `ensureCustomViewInitialized:2054`(`:1957` 设 mode=customView)。`ensureCustomAppInitialized:2002-2003` 在已 customView 时返 `failure_already_initialized:customView`、ready=false。`prepareCustomAppSession:589` 返 `relaunchRequired=true` + `rokid_cxrl_wrong_session_mode`。重启死路真实。Codex 引的 494 是入口,真决策点是 `:44 nil` + `:2054 else`。 | **P0** |
| **C2 photo gate loose** | confirmed(每个承重点精确) | `takePhotoBase64:762-807` 仅两道守卫 `auth:765`+`BLE:769`;`:780` 算 `sessionEvidence` **只插值进诊断字符串 `:781-784`,从不进 guard**;`:785` 无条件调 `takePhotoWithData`。对比 `startRecord:1125` 有第三道 `hasCustomViewMediaSession()`——photo **完全没有**=无场景门控盲发。 | **P1** |
| **C3 audio gate loose** | partially_confirmed(「音频无门控」被驳,底层关切成立) | `startRecord:1125` **确实**硬门控 `hasCustomViewMediaSession()`——Codex 字面被驳。**但**该 gate 认软证据:`:2474`=auth&&BLE&&`hasCustomViewSessionEvidence:2463`,后者四条件命中任一即 true,仅 `customViewRunning:2102-2105`(SDK `customViewRunningEventPublisher` 硬事件)是硬信号,另三条全软。**音频=门控了但证据不足**。 | **P1** |
| **C4 weak evidence as capability** | confirmed(行号+注释逐字全对) | `markCustomViewOpenUnconfirmedIfNeeded:1565` 在 callback 未到达但 BLE 连通时调 `markCustomViewSessionEvidence("open_callback_missing_ble_connected"):1581`,注释逐字「allow media APIs to attempt against the visible view」→ `customViewDisplayInferred=true:2485` → `hasCustomViewSessionEvidence` true → 媒体闸放行。**正是 SDK 矩阵「已鉴权+链路就绪 but 场景未构建→音频=否」那一行**。 | **P1** |
| **C5 gateway misreports ready** | partially_confirmed(派生过松属实,「坏动作」前提未证实) | `index.ts:547-554` `movementState='ready'` 当 `bridgeReady&&sdkLinked&&authorized&&customAppSupported`——不含 appInstalled/openApp-success,语义松弛**属实**。**但**唯一真实 consumer 是 `rokid-health.tsx:835-838 movementRouteLabel()` 纯 label,且 'ready'/'degraded' **同等对待**。盲发 openApp 的 `rokid-pushup-coach.tsx:835` **不 import gateway**;`openRokidApp:853-856` 自带 timeout+readResultOk+throw。**误报=cosmetic,不驱动坏动作**。 | **P2** |
| **C6 APK install daily path** | partially_confirmed(「主流程」夸大) | APK bundle 属实(`assets/rokid/*.apk` 20MB + `withRokidPushupApk.js`)。**但**「主流程」错:`:494` 是下载兜底;真入口 `installBundledOrDownloadedGlassesApp:595-613` **先试 bundle**,缺失才下载;install 非每次步骤(`ensureGlassesAppInstalled:762`→`installed 时 early-return:769`);UI 二级按钮、仅 `missing` 才提示。council 要求已基本落地。残留=应用内下载路由仍 ship(plan:425 自述应走官方分发/ADB)。 | **P2** |
| **C7 unify single CustomApp** | judgment_not_code(北极星对、v0 指令错) | mode 互斥真实(单例+`initialize` 每启动一次+`:2002 failure_already_initialized`)。食物 ~80% 在**手机侧**(`takePhotoBase64:762`→25s race→手机兜底→`submitRokidFoodDraft manual_confirm_required:1513` R4 草稿),**视觉服务端、不需眼镜端 App**。俯卧撑才是昂贵眼镜端 App(`apps/rokid-pushup-glasses` MediaPipe+CameraX)。把食物推进 CustomApp=抛弃已建手机侧+重建+不可靠 installApp。 | **P2** |

### 照片 vs 音频 — 关键调和(终裁)

三条 claim 实为**同一 SDK 不变量在两条媒体路径上的两种破法**:
- **照片(C2)**:`takePhotoBase64` **完全无**场景门控(连软证据都不查)→ 违反 SDK「拍照避免仅在已连接状态下触发」。
- **音频(C3+C4)**:`startRecord` **有**门控但认 `customViewDisplayInferred` 软证据(由 `:1581` 伪造)→ 违反 SDK「不要在场景未就绪时调用 startRecord」。

**塌缩成单一修复**:
> 建立 `mediaReady = hardSceneBuilt()`(仅 `customViewRunning==true` ‖ openApp 成功),**photo 与 audio 共用此闸**;软证据(displayInferred/notify/command-accepted)降级为「仅诊断/UI 文案」,绝不解锁能力。一条同时关掉 C2 零门控 + C3/C4 软门控。

### C5 — cosmetic 还是坏动作?终裁:**cosmetic**

`movementState='ready'` 既不被 pushup coach 启动路径读取、也不触发 openApp,唯一 consumer 是合并显示的 label。盲发 openApp 已被 `timeout+readResultOk+failure-throw` 守住(符合「不假装成功」)。Codex 在 label≠action 因果链上 over-stated severity → 降 P2「顺手收口」。

## 3. 与 F1-F5 / council 的关系

**Codex 带来的 NEW(超出 F1/F2/F4):**
- **C5** gateway `movementState='ready'` 语义松弛 — F1-F5/council 均未覆盖(虽降 P2,Codex 独有)。
- **C6** 残留具体到「下载路由 feature-flag off / 走官方分发」,比 council Week-1「写清限制」更细。
- **C1 精确根因** — F2 知道 mode 互斥,Codex 钉到 `:44 nil + :2054 else + :589 relaunchRequired` 确切机制,且指出**可直接用已发出的 `relaunchRequired` 信号**,非静默 ready=false。

**已覆盖(重述非新增):** C2/C3/C4 ⇆ F1+F4;C1 ⇆ F2(council Day-3);C6 ⇆ council Week-1②;C7 短期 hedge ⇆ council 飞轮排序。

**不冲突(7/7 verdict 一致):** 所有修复不触碰 `operation_id` 薄账本层(原生桥闸 ≠ 账本);不推翻 food-first-via-CustomView(媒体 hard-gate 反而**强化**「场景门控」物理约束);复杂度预算上 C2+C3+C4 合并是**拆 hard/soft 两档收口**(净复杂度持平),C5/C6 推荐**不加代码**(只调 label/flag)。

## 4. C7 单 CustomApp 裁定:北极星采纳 · v0 指令拒绝

**北极星(写进架构文档):** 一个 Reva Glasses CustomApp(food_capture/pushup/voice_control 模式)**确实**比「会重启的 session-coordinator」更干净地解掉 mode 互斥——整启动一个 mode、无重启舞蹈、解锁 `sendCustomCmd`(SDK 限 customApp)作统一控制通道。

**v0 指令拒绝——保护 council food-first + 复杂度预算:**
> **任何人不得在此阶段把食物路径推进眼镜端 CustomApp。** 食物 ~80% 已建在手机侧,移进 CustomApp=把**最便宜成熟**的能力变**最昂贵不可验证**(眼镜端 App + 视觉 + 已标记不可靠的 `installApp`)→ 违反 YAGNI / 「最小 20% 先上」/「别 greenfield」。

**唯一合法近期动作**:session-mode 当 App 级显式决策(council F2)。**触发点 = 俯卧撑 customApp 与食物 customView 物理碰撞时,才评估并入——不是现在。** `operation_id` 账本 `type`(capture_food=customView / pushup_session=customApp)已记所需 mode,是门控位置。

## 5. 校正后的统一修复顺序

### P0 — 必修(部署前)

**P0-1 · session-mode 显式化(C1 / F2)** — Swift + JS,**需 EAS**
- `RokidSessionCoordinator`:`requestAuthorization` 前显式设 `preferredCxrSessionMode` + packageName,消除 nil 冷启动默认锁。
- 俯卧撑流程:**接已发出的 `relaunchRequired=true` + `rokid_cxrl_wrong_session_mode` 到 UX**(「切换眼镜会话模式需重启 App」),不再静默 ready=false。
- ⚠️ 改 `CxrClient.initialize` 时序属 native,必须 EAS 真机验(Sim 测不出 mode 互斥)。

**P0-2 · 媒体 hard-evidence 门控(C2+C3+C4 合并 / F1+F4)** — Swift-only,**需 EAS**,**先写测试**
- 新增 `hardSceneBuilt()` = `auth && BLE && customViewRunning`(仅 `customViewRunningEventPublisher.isRunning` ‖ openApp 成功)。
- `startRecord:1125`:`hasCustomViewMediaSession()` → `hardSceneBuilt()`。
- `takePhotoBase64`:**新增**同一 `hardSceneBuilt()` 闸(当前零门控);无 scene → `recommendedSurface='mobile'` 直走手机,省 25s 空等。
- `markCustomViewOpenUnconfirmedIfNeeded:1581`:改为**只记诊断字符串**,不置 `customViewDisplayInferred=true`。
- 保留「unconfirmed 乐观尝试」为**显式、默认关闭、失败 fail-loud**(权衡 CXR-L 1.0.1 渲染不回 callback 的硬件现实)。
- **先写测试**:无 hard scene → 媒体闸 not_ready / captureState 不暗示眼镜;还原旧版必红。

> P0-1 + P0-2 都 native → **同一次 EAS build 真机验**,避免两轮等待。

### Deferred — P2 顺手收口(后续 PR / OTA)

- **D-1 · gateway movementState 收紧(C5)** — JS-only,**OTA-able**,先写测试。`:547-554` 收紧到「有 openApp 成功证据」,无则封顶 'degraded';`movementRouteLabel` 给 'ready'/'degraded' 不同文案。非阻断(动作侧已守)。
- **D-2 · APK 下载路由收口(C6)** — JS-only,**OTA-able**。`:1139` 文案标「beta/临时兜底」;考虑 non-beta build feature-flag off 下载按钮。**不要重构 bundle-first**(`:595-613` 已对)。
- **D-3 · operation timeline 作主调试面** — 复用既有 `rokid_operations` 薄账本,不新建。
- **D-4 · native-call-timeout 普适化(F5 / council Day-1)** — Swift + JS,需 EAS。`queryApp/openApp/startRecord/installApp/updateCustomView` 沉到 bridge wrapper 统一 `withRokidAppOpTimeout`。

### 文档动作

- **DOC-1 · C7 北极星入档**(本文 §4 已记)— 写「最终一个 Reva CustomApp + sendCustomCmd 统一控制通道」为北极星,显式标 v0 不动食物路径,触发点 = 两 mode 物理碰撞时。

## 6. 残留分歧 / 未决

1. **「unconfirmed 乐观拍照」取舍(P0-2 内)** — 软证据不该解锁连续音频(一致),但 photo 是否保留一个「默认关闭、fail-loud」乐观盲发口以应对 CXR-L 1.0.1 渲染不回 callback,需**真机实测 running event 到达率**后定。
2. **C5 收紧的「openApp 成功证据」具体信号未定** — 方向 `status.customAppLaunched` / openApp ok 事件,D-1 落地现勘。
3. **C6 残留改 flag 还是仅改文案** — 取决于 beta 分发渠道(官方分发 / ADB)成熟度,本轮未核证。
4. **C1 修法二选一** — (a) auth 前显式设 preferred mode 让俯卧撑直接 customApp;(b) 保 food 领头 customView、俯卧撑 gate 在干净重启。**v0 建议 (b)**(不动已验证 food 路径,与 council 排序一致);若长期走单 CustomApp 则 (a) 更顺。

---

*裁定方法:官方 SDK v1.0.3 能力矩阵(权威)× 7 条对抗 verdict(逐行 file:line 实证)× F1-F5 × council 四方对账。最高置信项 = 照片/音频/软证据三 claim 对照 SDK「场景未构建→媒体=否」那一行(塌缩成 mediaReady-hard-evidence 单一修复)。降级动作均有 consumer 追踪或代码结构实证(C5 label≠action、C6 bundle-first+probe-gated、C7 食物 ~80% 手机侧)。*
