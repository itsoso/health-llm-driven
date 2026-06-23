# Rokid + Reva 落地增量设计 + 最小可用计划

> 日期: 2026-06-23 · 状态: review 产出,可执行
> 本文是 [`2026-06-23-rokid-reva-end-to-end-architecture-redesign.md`](2026-06-23-rokid-reva-end-to-end-architecture-redesign.md)(下称「原设计」)的**落地增量版**。
>
> 原设计的**思想是对的**(四方解耦 / CustomView 显示态 / operation ledger / no-fake-success / glasses-first+fallback / §15 不变量),但按 **greenfield** 写。本文基于代码实勘把它改成「**还剩什么**」+「**最小可用边界**」,并补三条被漏的现实失败态。原设计 §15 不变量全部保留并 **+3**。

## 0. 一句话

原设计 Phase 0-4 **已落 ~60%**。把原文原样交给实现者会**重建已有的东西**。真正要补的是:① 统一 `operation_id`(**泛化现有 pushup 模型,非新建 17 列大表**)② 诊断上传端点 ③ **companion 抢占 BLE** + **眼镜网络出口** 两个被漏的现实失败态 ④ **native-call-timeout 升为不变量**。按飞轮:**食物拍照领头,俯卧撑最后**。

## 1. 已建,别重建(代码实勘)

| 能力 | 状态 | 证据 |
|---|---|---|
| `sdkLinked=false` 硬阻断 native 调试(原 Phase 0) | ✅ 已建 | `mobile/modules/rokid-bridge/index.ts:399-414`(nativeState='blocked')· `mobile/app/rokid-health.tsx:154-166, 2016-2021`(UI 阻断) |
| CustomView 降级为「显示态」,饮食/语音/运动不依赖它(原 Phase 0) | ✅ 已建 | `index.ts:474-490`(voiceState/captureState 独立)· `rokid-health.tsx:425-426, 595-598` |
| 食物拍照 photo 25s 超时 + 手机相机兜底(原 Phase 2) | ✅ 已建 | `rokid-health.tsx:305-326`(takeRokidPhotoBase64WithTimeout)· `rokidAmbient.ts`(source=iphone_camera_fallback) |
| **食物 draft+confirm(R4 合规,manual_confirm)** | ✅ 已建 | `ambient_wearables.py:451-460`("R4: AI vision never auto-confirms",默认 needs_confirmation)· `:141`(autonomy_tier=manual_confirm)。**原设计 invariant 3 代码已满足,应从「待建」移到「已建,守住别退化」** |
| phone-ASR 基线 + Rokid audio 增强(原 Phase 3) | ✅ 已建 | `rokid-health.tsx:1209-1269`(startPhoneVoiceFallback)· `RokidBridgeModule.swift:1209-1246`(audio_event_stream) |
| 语音白名单确定性 command router(原 Phase 3) | ✅ 已建 | `ambient_wearables.py:146-199`(route_rokid_voice_command) |
| 俯卧撑 session + 眼镜 APK + 事件回传(原 Phase 4) | ✅ 已建 | `backend/app/api/rokid.py:52-100`· `apps/rokid-pushup-glasses/.../RevaPushupEventClient.kt`· `rokid-pushup-coach.tsx:56` |
| 本地诊断时间线 + 复制(原 Phase 1 基础) | ⚠️ 部分 | `RokidBridgeModule.swift:107-108`(authDiagnosticTimeline)· `rokid-health.tsx:680-759`(buildRokidVoiceDebugText) —— 有本地复制,**无全局 operation_id、无上传端点** |

## 2. 真正缺口(排序)

1. **P0 · 统一 operation_id 账本**——唯一真正高价值的缺口。但**别 greenfield 17 列大表**:俯卧撑已有 `RokidPushupSession/RokidPushupEvent`(`backend/app/models/rokid_pushup.py:11-73`),**泛化它**成跨能力的 operation。v0 起 6-8 列;event 只补缺的 voice/photo/customview(pushup event 已有)。说清它和 `client_events`/`agent_audit_log` 的关系,**别建第三套并行事件系统**。
2. **P0 · 诊断上传端点**——现只本地复制(clipboard)。补 `POST /devices/rokid/diagnostics`(operation_id + 诊断文本;**绝不含原始 photo/audio**,只 hash/size/mime/source)。
3. **P1 · companion 抢 BLE central 建成一等失败态**——现实里第一大阻塞(Hi Rokid 抢 central,**强杀 companion 才通**)。代码有 UI 提示(`rokid-health.tsx:626-636, 673`)但 BLE 状态机没建模。加 `ble_blocked_by_companion` 态 + 自动诊断 +「iOS 一次一个 central」写进约束。
4. **P1 · 眼镜网络出口**——眼镜 POST 后端(G→S)但**无蜂窝**,要自己连 WiFi;设计和 `RevaPushupEventClient.kt` 都默认有网。加 `glasses_network_reachable` 前置/失败态;否则事件静默不到 **≠** 「ingest 失败」,会误导排障。
5. **P1 · native-call-timeout 普适化**——只 photo 做了(25s)。takePhoto/openCustomView/startRecord/installApp/queryApp 全要 JS 侧 `Promise.race` timeout + readResultOk(完成闭包在 BLE 掉线时永不来 → UI 永挂)。
6. **P2 · event 类型标准化**——voice/photo/customview 的 event_type/payload 对齐原设计 §6 的 **SUBSET**(不是全表),pushup 已实现可作模板。
7. **P2 · APK 安装文档**——原设计 §10 认可「CXR-L installApp 不可靠」但 `index.ts:886-911` 仍走 installBundledApp 无说明。写清已知限制 + fallback(manual ADB / 官方分发)。

## 3. 修订不变量(原 §15 八条全保留 + 3)

9. **每个 native bridge 调用必须 JS 侧 `Promise.race` timeout + `readResultOk`**——完成闭包在 BLE 掉线/眼镜崩时永不来,只 await 不查 ok = 假成功。(见 [[feedback_rokid_native_calls_need_js_timeout]])
10. **companion 抢 BLE central 是一等失败态**(`ble_blocked_by_companion`)——iOS 一次只能一个 central,Hi Rokid 占着时 Reva 收不到事件;诊断必须能识别并引导「完全退出 / 强杀 Hi Rokid」。(见 [[project_rokid_cxrl_transport_ble_plus_tcp]])
11. **眼镜端 POST 后端前确认 `glasses_network_reachable`**(眼镜无蜂窝→需 WiFi)——事件静默不到必须能和「ingest 失败」区分开。

## 4. 飞轮排序(原文等权对待是把力气投错)

| 能力 | 飞轮价值 | 工程成本 | 结论 |
|---|---|---|---|
| **食物拍照** | 最高(被动>主动,眼镜优先,喂因果账本) | 中(已 ~80%) | **领头**,先把它的 operation_id 闭环 + 诊断做扎实 |
| 语音 | 中(命令入口) | 低(phone-ASR 已通) | 跟随 |
| 俯卧撑 | 窄(单动作) | **最高**(眼镜 APK + 姿态 + ingest + 安装不可靠 + 眼镜网络) | **最后**,诚实标「最未验证」;别让它拖住前两个 |

## 5. 最小可用计划(1 天 / 3 天 / 1 周)

> 规则(承原设计 Prompt 3/6):不先做 UI 美化;native SDK/entitlement/Info.plist/framework/EAS profile 变更**不写成 OTA 可修**;食物和运动都优先走眼镜但必须有手机兜底;不再用截图作为主要排障。

### 1 天 —— 止血 + 可观测地基
- 泛化 `RokidPushupSession/Event` → 统一 `operation_id`(mobile 先本地串,后端表 v0 6-8 列)。
- `POST /devices/rokid/diagnostics`(operation_id + 文本,剥 photo/audio 原文)+ 诊断面板「上传本次操作诊断」。
- bridge 检测 `ble_blocked_by_companion` → 诊断面板明确「强杀 Hi Rokid 再连」。
- **验收**:任一失败能从 operation_id 还原链路;不再要用户截图。

### 3 天 —— 食物闭环可观测 + 眼镜网络
- 食物 capture 串 operation_id(已 draft+confirm,只补 ledger 线程 + 食物事件标准化)。
- 眼镜网络出口检查(`glasses_network_reachable`);俯卧撑/视觉事件不到时区分「眼镜没网」vs「ingest 失败」。
- native-call-timeout 普适化到所有 bridge 调用(invariant 9)。
- **验收**:一餐 → operation 时间线显示 source(rokid/iphone_fallback)+ draft 待确认;眼镜没网有明确诊断。

### 1 周 —— 俯卧撑链路补全(最后)+ APK 安装文档
- APK 安装写清 CXR-L 限制 + fallback 路线(manual ADB / 官方分发);别当正常用户流。
- 俯卧撑 session_url 验证 + 事件 ingest 端到端;iPhone 只从后端更新,不显示假本地计数(invariant 5)。
- **验收**:眼镜端 app 带 backend session URL 启动;后端收到 ≥1 个 session_state + pose/rep 事件;本地手动计数明确标 fallback。

## 6. v0 不做 / 砍

- **4-plane 全形式化**(control/media/execution/display 概念保留,但 v0 不建独立平面对象)。
- **17 列 `rokid_operations` 大表**——起 6-8 列,按需长。
- **截图调试**——替换为 operation_id 诊断。

---

*方法:原设计(四方解耦 / 状态机 / ledger / 不变量,思想正确)× 代码实勘 gap 分析(~60% 已建,别 greenfield)× 三条被漏的现实失败态(companion 抢占 / 眼镜网络 / native-call-timeout)× 飞轮排序(食物领头,俯卧撑最后)× 复杂度预算(最小 20% 先上)。*
