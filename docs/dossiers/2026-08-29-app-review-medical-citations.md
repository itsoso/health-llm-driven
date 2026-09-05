# Dossier: App Review 医学信息可点击引用

| 字段 | 值 |
|---|---|
| slug | `app-review-medical-citations` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | 2026-09-03 增量 G4 已通过；新 Store 候选与 G6 精确物理 iPhone 验收待办 |
| 状态 | store_candidate_pending |
| 负责 | product / backend / mobile release |
| 关联提交 | 拒审 Submission `85f3224c-3688-4aae-9da1-c7e91f4facaa` / 当前候选 Version 1.3.3 (261) |

## S0 · 用户需求

> 确保我能一次性审核通过

不能保证 Apple 的最终裁决；可交付目标是消除已知 1.4.1 拒审原因，并让代码、审核说明、精确二进制和真机证据形成同一条可复核链。

## S1 · 已确认事实

- App Store Connect 当前状态：1.3.3 (256) 已拒绝，问题未解决。
- Guideline：1.4.1 Safety: Physical Harm。
- Apple 明确指出 AI chat 的医学计算与参考没有来源链接。
- 审核复现：输入“帮我算我的BMI”，回答展示公式、22.9 和正常范围，但无引用。
- Build 256 源提交：`75f61f694c4711a7b349eb63fb7af5e48d9f9012`。

## G1 · 准入

- 分类：已上线健康信息 surface 的安全合规修复。
- first_class_objects：`SafetyGuardian`, `ExecutionEvent`。
- source_of_truth：服务端受控来源目录 + 已准入健康证据 URL。
- 自治等级：只读；不产生诊断、处方、治疗或健康数据写入。
- **裁决：PASS**。

## G2 · 可行性与安全压测

- 后端终态 choke point 覆盖普通、确定性和多模型回答。
- 模型只接收服务端给出的来源范围，不能生成最终 URL。
- Backend/Mobile 双层只接受安全 HTTPS。
- 完成态引用写入 message meta，历史恢复与实时 SSE 保持一致。
- Build 256 不可复用；必须新建 production Store binary。
- **裁决：PASS**。

## S5 · 实现

- [x] 医学主题到权威来源的确定性策略。
- [x] BMI 使用国家卫生健康委员会和 CDC 来源。
- [x] 服务端预生成提示约束与 complete 终态补全。
- [x] assistant meta 持久化，查询带用户所有权过滤。
- [x] Mobile SSE/历史解析、安全 URL 过滤和默认展开引用面板。
- [x] 审核说明加入 Apple 原始 BMI 复现路径。
- [x] 真机模板加入引用可见与官方链接打开检查。
- [x] 公共目录引用前移到已鉴权 SSE 边界，在模型/工具工作前提供首批关键内容；终态仍由既有 choke point 重新计算和持久化。
- [x] 流式引用可独立点击和被 VoiceOver 访问；发送/附件补齐 button 语义，来源补齐机构、外部网站提示与动态字体。
- [x] 失败/中断清除提前引用；BMI 请求主题优先，不被回答中的附带健康词稀释。
- [x] 引用时延拆为 `citations_received` 与基于 React Native 首次布局的 `citations_painted`；`citations_visible` 仅保留为历史事件兼容，周报使用实际绘制分位数。
- [x] XCUITest 新增 BMI → NHC 官方域名检查，并对未登录、缺固定 Today 数据和并行执行 fail-closed。
- [x] 系统地图再生成与漂移验证。
- [x] 全量相关回归、lint、release pack 和安全 Gate。
- [x] 历史引用修复 commit / push / backend deploy / EAS production build。
- [x] 2026-09-03 本地加固已固定并完成独立 G4。
- [ ] 该增量的 push、backend deploy 与新 EAS production build 仍按独立发布 Gate 待办。
- [ ] 精确候选 Build 真机证据。
- [ ] 用户确认后回复 Apple 并重新提交。

## G3 · 测试

- Backend Agent/健康证据/系统知识/完成态/引用/发布包相关回归：293 passed。
- Mobile 引用策略、SSE、历史恢复、组件与 ChatBubble：48 passed。
- TypeScript `tsc --noEmit`：PASS；Expo lint `--quiet`：PASS。
- System Map 生成与漂移：PASS；App Store release pack：PASS；iOS submission preflight：PASS。
- Python 编译与 `git diff --check`：PASS。
- 2026-09-03 新鲜增量证据：Mobile 6 suites / 237 tests、Backend/API/事件/引用策略与 harness 共 140 tests、TypeScript、Mobile lint、Python compile、diff hygiene、离线 LLM invariants 12/12 + health-agent core 50/50 + trajectory 12/12 + golden 9/9、System Map、基础 release pack 与 iOS submission preflight 均 PASS；14/14 个目录官方 HTTPS 来源在线返回 2xx。
- 当前未提交源码已构建并安装为本地 Release 模拟器 `小巴健康 1.3.3 (262)`，0 error；由于重装后没有审核账号会话，fail-closed 套件为 1 个登录入口 PASS、6 个 `ownerLoginRequired` FAIL。该结果证明门禁语义正确，不构成登录后功能或物理 iPhone G6 通过证据。
- **裁决：PASS**。

## G4 · 安全评审

- 来源准确性：BMI 的 NHC/CDC 来源与 claim scope 对齐；目录内 11 个官方 HTTPS URL 于 2026-08-29 实测 HTTP 200。
- URL 安全：Backend 拒绝 HTTP、带凭据 URL、localhost、`.local` 和非公网 IP；Mobile 再拒绝同类 URL 及 IPv6 literal。
- 用户隔离：持久化查询同时限定 assistant message 与 `AgentConversation.user_id`，跨用户回归通过。
- 失败语义：仅 `completion_status=complete` 附引用；error/interrupted 不声称已经提供来源；外链打不开时明确提示用户重试。
- 医疗边界：只增加只读证据展示，不新增诊断、处方、剂量调整或健康数据写入；模型不能决定最终 URL。
- **历史引用修复裁决：PASS（本变更为只读证据展示；未扩大既有医疗自治或写入权限）**。
- **2026-09-03 增量裁决：PASS**。2026-09-05 对固定候选重新执行高置信密钥扫描、医疗引用/失败语义/无正文客户端事件/owner guard 与图片饮食相关 427 个 Backend 用例，以及分享编辑 42 个、Chat 54 个 Mobile 用例，均通过；本增量没有让模型决定最终 URL，也未扩大医疗自治或用户数据范围。

## G5 · 部署健康

- 修复提交 `048583dd62e456fd392d27e39acbf5a00e1d271b` 已进入 `main`；候选构建源为包含该修复的 `b171923e3de66ac56212d387177cf7e709245a28`。
- GitHub Actions：`33238235849` 与候选主干 `33238797747` 均 SUCCESS。
- Backend：生产部署到 `b171923e3de66ac56212d387177cf7e709245a28`；API、PostgreSQL、Redis、Celery 健康检查均 connected/running。
- EAS production Store Build：`9d51b003-c5a5-4afe-8868-79efcefb7c72`，1.3.3 (257)，source、runtime、bundle id 与 production channel 对齐，状态 FINISHED。
- EAS Submit：`431726be-0f23-4ce1-835c-f8ec41f5292a`，状态 FINISHED；App Store Connect processing state `VALID`，TestFlight internal state `IN_BETA_TESTING`。
- 精确 IPA：SHA-256 `5d867fc34ca208e6305c57023c19b4ec15f34577d6a180dfa75b4e6852e3d7e0`；`CFBundleIdentifier=life.executor.health`、`CFBundleShortVersionString=1.3.3`、`CFBundleVersion=257`、`DTXcode=2620`、`DTPlatformVersion=26.2`；strict codesign 通过，production APNs / HealthKit entitlement 与根 PrivacyInfo.xcprivacy 存在。
- 当前标准 production 候选已升级为 Build 260：EAS `12726ec9-3e37-4a76-aad6-f1ac1a5cbff5`、Submit `250b8d79-3d64-45c1-9f47-d59df7dd128c`、source `3e3d1f9d4e1ccd4433f75735c420dbc98ab0a850`，ASC `VALID / IN_BETA_TESTING`。精确 IPA SHA-256 `b98eb85c33db3b504fec41dc3bf25b3fb218c2f325f91c63d2789019edf68d48`；版本 1.3.3（260）、`CFBundleDisplayName=小巴健康`、`DTXcode=2620`、`DTPlatformVersion=26.2`、MinimumOSVersion 16.0、strict codesign、production APNs / HealthKit / Universal Link 与根 PrivacyInfo.xcprivacy 均通过，且未包含 Rokid、Watch、Siri 或后台定位能力。
- 当前标准 production 候选已升级为 Build 261：EAS `dd6a2c0f-b167-47b9-a796-61ce8ec0c335`、Submit `4761bfae-3f4c-457a-9415-5f8847e0c23d`、source `21576b80ec4c968ada4ea005e8bfde633bc24f27`；Apple processing 已完成，TestFlight `1.3.3 (261)` 状态“准备提交”，已加入 `Team (Expo)` 与“内部测试”两个内部群组。精确 IPA SHA-256 `597a601f8e54b834ef6d31f8022df99b8d8d21cf6462023dd86ed660c1398fc1`；版本 1.3.3（261）、`CFBundleDisplayName=小巴健康`、`DTXcode=2620`、`DTPlatformVersion=26.2`、MinimumOSVersion 16.0、strict codesign、production APNs / HealthKit / Universal Link 与根 PrivacyInfo.xcprivacy 均通过，iPhone-only 且未包含扩展或后台模式。
- **历史引用修复裁决：PASS**。
- **2026-09-03 增量裁决：pending**。G4 已通过，但本地 Release 模拟器构建仍不等于部署或 Store 候选；完成 push、Backend 部署、新 EAS Store Build 和目标 revision CI 核验前，不得把 Build 261 标为本轮通过。

## G6 · 上线验证

- 2026-09-04：在正确的 review fixture 与审核演示账号下，本地 Release Simulator Build 262 完整验收 `7/7 PASS`；BMI 来源约 17 秒可见，NHC 链接可点击并在 Safari 到达 `nhc.gov.cn`，返回 App 后聊天面可恢复。该证据只证明当前本地源码的模拟器行为，不替代精确 Store Build 的物理 iPhone 验收。
- 2026-09-03 本地 Release 模拟器构建已验证 App 名、版本和 Build 为 `小巴健康 1.3.3 (262)`；审核套件已修复“未登录仍因 skip 返回成功”的假绿。受控 review fixture reset 因本机缺少 `.env` 未执行，未读取用户未跟踪的 `.env-online`；模拟器重装后停在登录页，因此登录后 BMI/NHC、Today、草稿、隐私和冷启动用例均按预期失败。该本地产物未上传，不是 TestFlight 候选。
- 2026-09-01 独立模拟审核裁决：`NO-GO`。代码与 Build 261 二进制层为 conditional GO；提交层因精确候选真机审核账号登录/BMI 引用与外链证据、`261-ready` 同包截图缺失而阻断。只读核对 ASC 还发现 1.3.3 绑定已拒绝的 Build 256，名称与提交文案仍有旧品牌，审核备注缺少 BMI 复现步骤且审核联系人电话为空；App Privacy、年龄分级与“非受监管医疗设备”声明已发布/保存并保持通过。此次模拟审核没有修改 ASC 表单、选择 Build 261 或提交审核。
- 同日新鲜 Mobile 定向回归 6 suites / 85 tests PASS，覆盖医学引用、SSE/历史恢复、引用组件与登录错误分类。Backend 本地定向 pytest 因 `localhost:5432` PostgreSQL 未运行而在 collection 前失败，不能记为新鲜通过；精确 source `21576b80ec4c968ada4ea005e8bfde633bc24f27` 仍以 GitHub CI run `33510985890` 全绿为提交候选证据。
- pending。精确 Build 261 必须真机输入“帮我算我的BMI”，看到默认展开来源并能打开 NHC/CDC 官方链接。
- 2026-09-01 从精确 source `3e3d1f9d4e1ccd4433f75735c420dbc98ab0a850` 以 Release / iOS Simulator 26.5 无签名构建 1.3.3 (260) 成功并安装；`CFBundleDisplayName=小巴健康`，启动登录页品牌显示“小巴健康”。模拟器没有审核账号会话，因此未生成聊天/医学引用商店截图；此证据只验证 Release UI 与品牌，不替代物理 iPhone G6。
- 2026-08-29 检查到登记 iPhone `suntice` 当前 offline；未用模拟器或旧 Build 代替精确二进制证据。
- 在这项验收通过、外部证据文件补齐且 final-submit gate 通过前，不回复 Apple、不重新提交审核。

## Rollback

- 任一来源、隐私、真机或安全 Gate 失败：停止重新提交并回到 S5。
- 审核期间禁止 production OTA；不得用 OTA 改变待审包行为。
