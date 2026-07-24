# Dossier: App Store iPhone First Release

| 字段 | 值 |
|---|---|
| slug | `app-store-iphone-first-release` |
| 创建日期 | 2026-07-14 |
| 当前阶段 | S7 上线验证 |
| 状态 | build_236_uploaded_apple_processing_pending_physical_g6 |
| 负责 | Codex |
| 目标版本 | iPhone App Store RC |

## S0 · 用户需求

> 思考我要提交到appstore ，产品上还有哪些需要改进，做出规划
>
> 按照你的规划执行

- 使用者:第一次从 App Store 安装小巴的 iPhone 用户。
- 核心问题:当前包同时暴露未完成的平台能力、启动即索取权限、隐私材料与实际二进制不完全一致，不能把历史 TestFlight 当成正式 RC。
- 核心闭环:`打开小巴 -> 文字/语音/拍照 -> 可编辑草稿 -> 用户确认 -> 数据写入 -> 今日状态刷新 -> 可撤销或修正`。

## S1 · Discovery

- 生产配置当前仍声明 iPad、多方向、Watch extension、Rokid、Siri、后台定位/音频/蓝牙。
- 通知在登录后自动请求系统权限；定位在第一次进入主界面约 1 秒后主动弹窗。
- App Store 截图是 2026-06-30 的旧 UI；最新 Store build 225 早于当前 `main`。
- `PrivacyInfo.xcprivacy` 尚未声明 App 自身收集的数据；账号删除只写审计日志，缺持久状态与运营闭环。
- 当前工作树另有“今日行动渐进式计划”WIP；本次不回退，纳入 Agent 核心链路回归。

## G1 · 准入

```yaml
RequirementAdmission:
  request: 把当前产品收敛为可提交 App Store 的可信 iPhone 首发版
  classification: release_trust_and_scope
  first_user_fit: yes
  core_loop_step: intake -> agent draft -> manual confirm -> persistence -> review
  first_class_objects: [WriteIntent, ExecutionEvent, ConsentGrant, ProvenanceRecord]
  target_surface: [Mobile, Backend, Privacy Web, Release Tooling]
  source_of_truth: [PostgreSQL, App Store release pack, iOS production config]
  safety_level: privacy_sensitive_and_medical_boundary
  prescription_or_causal_verdict: forbidden
  autonomy_tier: manual_confirm
  evidence_provenance: required_for_health_actions
  success_metric: core acceptance cases pass with no raw JSON, duplicate write, lost image, or permission-at-launch
  added_user_burden: permission prompts move to explicit feature actions
  burden_justification: contextual consent improves comprehension and review compliance
  non_goals: [iPad launch, Watch launch, Rokid launch, autonomous medical decisions]
  smallest_end_to_end_slice: iPhone portrait core Agent loop plus privacy and deletion controls
  stale_surface_to_remove_or_archive: [production Watch, production Rokid, production Siri, startup permission prompts]
  spec_required: yes
```

裁决: **PASS**。用户已确认采用 iPhone-first 规划。

## S2/S3 · PRD 与规划

- 产品依据:`docs/prd/reva-personal-health-os-prd.md`。
- 实施计划:`docs/plans/2026-07-14-app-store-iphone-first-release-plan.md`。
- 首发承诺:Agent Native、Mobile First、iPhone portrait；用户可在不授予通知、定位、麦克风、照片或 HealthKit 权限时使用文字对话。

## G2 · 可行性与安全压测

- iPad/Watch/Rokid/Siri 从标准 production 包移除，但保留显式独立 profile 供后续验证。
- HealthKit、相机、照片、麦克风、语音识别保留，因为属于核心记录入口；均只能由用户动作触发授权。
- 所有健康写入保持 `manual_confirm`；无法取得可验证回执时不得显示成功。
- 医疗输出继续限制为记录、解释和生活方式建议，不诊断、不处方、不调整剂量。
- 原生配置变化必须走新 EAS production build；旧 build 225 不可作为 RC。

裁决: **PASS**。无待拍板项。

## S4 · 研发任务

- [x] R1 iPhone-only production scope 与配置回归测试。
- [x] R2 通知/定位改为场景触发授权。
- [x] R3 隐私清单、隐私政策、账号删除处理闭环。
- [ ] R4 Agent 核心写入、语音、拍照、分享和渲染回归（自动化与模拟器已过；真机待测）。
- [x] R5 安全、依赖、可访问性和审核材料 Gate。
- [x] R6 commit/push、前后端部署、新 EAS production build 与 TestFlight 上传。
- [ ] R7 在 Build 236 上完成真机 G6 并补齐 App Review 材料。

## Gate Ledger

| Gate | 状态 | 依据 |
|---|---|---|
| G1 准入 | PASS | iPhone-first 核心闭环与一等对象映射明确 |
| G2 可行性/安全 | PASS | 已冻结范围与医疗/隐私边界 |
| G3 测试 | PASS | 当前 `main`=`56875570b` 的 GitHub Actions run `29417247062` 28/28 jobs 通过；Mobile 245 suites / 1731 tests、Web 43 files / 243 tests、TypeScript、Lint、生产构建通过；Harness invariants 12/12、core 50/50、live orchestrator 5/5 通过 |
| G4 安全 | PASS | 生产包无后台录音/持续定位；账号删除、隐私清单、写入回执 fail-closed 已复核 |
| G5 部署健康 | PASS | 后端生产健康度 60/60；App Store Connect 中 version 1.3.2 Build 235 为 `VALID`、未过期且内部 `IN_BETA_TESTING` |
| G6 真机验证 | BLOCKED | 必须在同一 TestFlight Build 236 完成真实 iPhone 语音、切 App 恢复、草稿、滚动、拍照、图片/视频播放分享、微信/小红书跳转、写入纠正删除及账号删除证据 |

## Correction Block

- 旧基线:2026-06-29 dossier 记录“final-submit preflight passed”，且 Store build 225 已上传。
- 新证据:build 225 早于当前 `main`，截图和原生能力也已漂移。
- 新基线:只有从本 dossier 对应提交构建的新 production 包，完成 G3-G6 后才可提交审核。

## 2026-07-14 Verification Notes

- iOS production prebuild: iPhone-only (`TARGETED_DEVICE_FAMILY=1`)、portrait-only、deployment target 16.0。
- 最终 `Info.plist` 不含 `UIBackgroundModes`、`NSLocationAlwaysUsageDescription` 或 `NSLocationAlwaysAndWhenInUseUsageDescription`。
- 修复 Mobile 草稿恢复:SecureStore key 改为平台允许的字符集，避免应用重启或前后台切换时丢失输入草稿。
- 修复低质量主动开场:过滤“已记录/记录成功”类回执标题，不再生成“今天就是已记录的检验日，做到了吗”。
- 修复 Mac/Web 连续提醒链路:生产日志证明上下文历史已保留；失败来自 SmartReminder 的 `pending` 被误判为未写入，而非记忆缺失。
- 新增时间窗原子提醒:支持 `start_time + end_time + interval_minutes`，09:00–20:00 每 90 分钟确定性生成 8 个时点；同一用户重复提交幂等复用已有记录。
- 对“9点到20点”这类补充回答增加确定性上下文恢复：仅在当前消息明确给出时间范围时继承最近一轮已确认的频率，避免模型把整段计划收缩成单个 09:00 提醒。
- 生产部署:服务器 `main`=`16d0517f1`，API/数据库/Redis/Celery 均 healthy；提醒时间窗与账号删除路由均返回鉴权状态，账号删除表已执行幂等 PostgreSQL 迁移并验证存在。
- iOS production:App Version 1.3.1，Build 226，EAS Build ID `8ad0eea2-6c0f-45ba-98c0-1c0e682c306f`；IPA 构建成功并由 Submission `448c0120-fc37-49b8-aab6-bfcd6246abe6` 上传 App Store Connect，Apple 处理状态为 `VALID`，已绑定版本 1.3.1。
- 真机发现语音提交回执竞态：服务端已记录/开始回复，但客户端在缺少 `request_persisted` 或最终 `done` 时把同一请求误判为发送失败，保留转写并诱导重复提交。
- 修复后将“用户消息已被服务端接受”和“助手回复是否完整结束”拆成两个状态：新版继续优先使用 `request_persisted`，兼容链路允许带 `conversation_id` 的 `agent_start` 证明提交成功；后续流中断只标记回复可重试，不再弹发送失败或要求重复提交。
- 回归证据：`useChatEngine` 38 项、`ChatInputBar` 42 项、语音 hooks/router 27 项、SSE parser 18 项、ChatScreen 38 项及 TypeScript 检查通过。G6 仍需在 Build 226 + 最新 production OTA 上复测真实设备语音提交。
- 语音可靠性发布：前后端生产运行 `c26ddcebb`，部署健康度 60/60，公开健康接口返回 200，未登录 `/api/v1/auth/me` 返回 401；production OTA 更新组 `7e7512c2-c017-4ea0-8521-da5a532557ec`，iOS update `019f6376-4d6a-7f55-98b1-49503bae9eba`，runtime `1.3.1`。
- 真机复测标准：Build 226 冷启动或后台 30 秒后拉取 OTA，右侧麦克风只提交一次；消息被服务端接受后立即清空输入框且不弹“发送失败”，即使后续助手流中断也不得恢复同一语音草稿或诱导重复发送。
- 修复图片饮食识别后的对话纠正：明确的“修改早餐/午餐/晚餐为……”现在以用户原话中的日期、餐次和新食物定位原记录；恰好一条候选时转成 `health_manage update`，零条或多条候选只查询不写入，模型误发 `health_record` 也不会创建重复饮食。
- 裸露的 `health_manage` 参数不再被 `meal_type` 误判成新饮食；同参 `health_manage(operation=list)` 回合内只执行一次，`update/delete` 继续走写入回执状态机。食物变化后沿用饮食 API 的纠正规则，清空旧识别营养值与 AI provenance，并向用户明确回复“已更新早餐”。
- 发布证据：代码运行提交与生产均为 `bc9254e60`，后端部署健康度 60/60；重放远端并行提交后联合回归 348 项通过，Ruff 与 Python 编译通过。生产错误记录 `diet_records#821` 已按原请求修正为“一碗小米粥 一个蔬菜饼”，旧 730 kcal 与宏量营养估算已清空，`source=user_corrected`。

## 2026-07-15 App Store Connect Readiness

- 从当前 `main` 构建 iPhone 17 Pro Release 模拟器包，确认正式包不包含开发环境浮动调试入口；使用 Computer Use 逐页验证小巴首页、今日行动、历史 Agent 对话、健康记录、档案导入和隐私政策。
- 使用演示账号生成无私人健康数据的 Build 226 截图候选；最终营销集合保留首页、今日行动、Agent 对话、健康记录、档案导入 5 张，均为 1290 x 2796，`privacy_status=demo`，截图 Gate 通过。含演示邮箱的设置页与隐私政策页未上传为营销截图。
- App Store Connect 版本 1.3.1 已绑定 Build 226；Build 状态 `VALID`，审核账号、密码、联系人和 Review Notes 均已填写；版本描述、关键词、支持 URL、营销 URL和推广文本均已填写。
- 5 张新截图已上传到 App Store Connect 的 `en-US / APP_IPHONE_67` 集合，并通过 API 回读确认数量为 5。Fastlane Precheck 在排除 API Key 暂不支持的 IAP 检查后全部通过，无占位文本、坏链接、竞品或未来功能承诺问题。
- 下载并检查实际 EAS IPA：版本 1.3.1、Build 226、iPhone-only、portrait-only、production APNs、HealthKit 和 `applinks:health.executor.life` entitlement 正常；无后台模式、始终定位说明，`PrivacyInfo.xcprivacy` 存在。
- App Review 登录路径的文字键盘修复已合入并推送 `main`=`2945e1b2d`，production OTA 更新组 `1a8a7aba-3281-4caa-a561-ff2edb88b12d` 已发布到 runtime 1.3.1；登录回归 2 项和 TypeScript 检查通过。
- 基础发布 Gate、截图 Gate、ASC 凭证 Gate 均通过。自动化严格最终 Gate 按预期仅剩三类阻断：材料仍标记 draft、Review Notes 尚未转 final、缺 Build 226 真实 iPhone 验收文件。
- App Privacy 的逐项回答不在 App Store Connect 公共 API Key 可读范围内；`privacy-nutrition-label.draft.json` 仍需在登录态页面逐项比对并确认已发布，作为最终人工 Gate，不能由本地隐私清单或 API 404 推断已完成。
- 当前已登记的 iPhone `suntice` 仍为 `unavailable`。因此 G6 继续 `BLOCKED`，不得用模拟器替代真实麦克风、相机/相册持久化、微信/小红书分享跳转、确认写入及账号删除状态验收，也不得点击 Submit for Review。

## 2026-07-15 Build 227 Release Candidate

- CI 先修复三项发布阻断：OpenAPI 生成类型漂移、orchestrator 测试桩的新参数兼容、健康建议安全分类基线；随后把 Linux 上会互相污染并超时的 timeline/today 测试拆成五个覆盖无遗漏的独立 shard。权威 run `29414534477` 在 `main`=`838bfa9bb` 上 28/28 jobs 成功。
- Live LLM 变更闸门在仓库根环境执行：invariants 12/12、health agent core 50/50、live orchestrator 5/5 通过；临时 CI 确认变量在验证后已删除，未留作永久绕过。
- App Store 预检与基础 release-pack gate 通过。EAS production 将远端 build number 从 226 自动递增为 227；Build ID `247e924c-3050-4981-b5b7-74e3e4e63545`，App Version 1.3.1，Git commit `838bfa9bb201491ce804ac48be789b96ffc16cfe`，构建状态 `FINISHED`。
- EAS Submission `16964993-cfdf-442d-8655-cf9104ca0235` 已成功上传；Apple 处理完成后通过 App Store Connect API 回读 Build 227 为 `VALID`，`expired=false`，`usesNonExemptEncryption=false`。版本 1.3.1 已从 Build 226 切换并绑定 Build 227，状态仍为 `PREPARE_FOR_SUBMISSION`；这不等于提交审核，未触发 Submit for Review。
- 下载并检查确切 Build 227 IPA：`CFBundleVersion=227`、`UIDeviceFamily=[1]`、仅 portrait、production APNs、HealthKit、`applinks:health.executor.life`、`get-task-allow=false`；无后台模式和始终定位能力。主 App `PrivacyInfo.xcprivacy` 包含健康、健身、邮箱、用户 ID、用户内容、照片/视频、精确位置、崩溃和性能数据声明，tracking=false。
- `Expo.plist` 指向 production channel，runtime 1.3.1，`EXUpdatesCheckOnLaunch=ALWAYS`。与 Build 226 不同，Build 227 已直接内嵌当前主干 Mobile 代码，首次启动不再依赖 OTA 才获得近期语音、流式 Markdown、图片和 UI 修复。
- 下一闸门保持 G6 `BLOCKED`：必须安装并验证确切 TestFlight Build 227；至少覆盖拒绝权限后的文字降级、右侧实时听写开/关及提交后关闭、左侧按住说话、照片持久化、微信/小红书分享、确认写入/纠正/删除、账号删除和前后台恢复。完成前不得点击 Submit for Review。

## 2026-07-15 Final Compliance Delta

- Apple 2026 年新增 Health & Fitness / Medical 类应用的受监管医疗器械声明。按小巴“不诊断、不预防或治疗疾病、不替代医疗器械、不处方或决定药物剂量”的发布边界，本版本应在 App Store Connect 选择 `Regulated Medical Devices: No`；若实际判断为 `Yes`，必须停止提交并进入独立法规审查。
- 最终发布检查新增两个人工确认：`APP_STORE_PRIVACY_RESPONSES_PUBLISHED=1` 只可在 App Privacy 全量答案与 `privacy-nutrition-label.draft.json` 对齐并点击 Publish 后设置；`APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no` 只可在 App Information 保存上述声明后设置。新增 7 项单测，发布包草稿 Gate 和 iOS 配置 Gate 均通过。
- 用 Build 227 运行严格 final-submit Gate，确认现有 `226-ready` 截图 manifest 会因 build 不一致被拒绝。Apple 要求截图准确反映当前核心体验；本项目继续采用更严格的同 Build 证据，不通过改 manifest 绕过，待真机可用后从 Build 227 重新确认或采集截图。
- App Store Connect 浏览器会话当前返回登录失败，未代替发布负责人登录或提交声明。已上传的 Build 227 保持 `VALID`、绑定 1.3.1 且未 Submit for Review。
- 当前剩余四项：Build 227 真实 iPhone G6、Build 227 截图证据、App Privacy 发布确认、受监管医疗器械状态 `No`。上述四项未完成前，submission pack 和 Review Notes 必须保持 Draft。

## 2026-07-24 Build 235 Reliability Baseline

- EAS 只读核验显示最新标准 production 构建为 version 1.3.2 Build 235，EAS build ID `d6b5f7de-1208-488d-8799-4b6f8a76b011`，源提交 `371dacc60ba3f218edec4b367ea61472798904a2`。
- App Store Connect API 回读 Build 235：`VALID`、`expired=false`、内部测试状态 `IN_BETA_TESTING`；外部测试状态为 `READY_FOR_BETA_SUBMISSION`，尚未进入外部 Beta Review。
- 修复联网状态误判：连接存在但 `isInternetReachable=false` 时显示离线；探测中的 `null` 保持最近可信状态，避免前后台切换时在线/离线闪烁。
- OTA 应用前新增统一保存闸门。聊天输入框会同步落盘当前文字和图片草稿；保存失败时停止重载并提示稍后重试，禁止以更新成功为由丢失用户输入。
- 真机证据模板从 12 项扩展到 20 项，并强制记录 app version、production profile、EAS build ID 和 source commit。新增流式 Markdown、外部音频打断、图片保存分享、视频播放不二次生成、写入纠正删除幂等、前台恢复、草稿保留和最新消息定位。
- production OTA 已从提交 `a9bb9b8752d3313722c8d2deca70220e12b70b6f` 发布到 runtime `1.3.2`：update group `c96503a6-91f3-467c-9051-a9e18bd8b2a6`，iOS update `019f92f8-6957-7a4c-a8fe-71689563d8c6`。
- 当前仍不可提交审核：Build 235 真机 20 项证据、同 Build 截图复核、App Privacy 发布确认和受监管医疗器械状态 `No` 均未完成。发布材料继续保持 Draft。

## 2026-07-24 Final Gate Recheck

- 当前代码基线为 `main=670984598`，工作区干净；基础 release-pack 与 iOS submission preflight 均通过。
- 在加载发布机密钥并允许联网后，严格 final-submit gate 不再报告 App Store Connect 凭证、Review 演示账号或联系人缺失，证明这些发布机配置和演示登录链路可用。
- 历史 `226-ready` 截图集本身通过尺寸、隐私和素材完整性检查，但严格门禁按预期拒绝其用于 Build 235：manifest 中 `build_id=226`，与目标 `235` 不一致。不得通过改写 manifest 绕过同 Build 复核。
- CoreDevice 仍能识别已配对的 iPhone 17 Pro Max `suntice`，但状态为 `unavailable`；因此无法执行 Build 235 的 20 项物理 iPhone 验收，模拟器不得代替外部音频打断、真实语音、相机/相册、微信/小红书跳转和前后台恢复证据。
- 严格门禁的真实剩余阻断仍为四项：Build 235 真机验收文件、Build 235 截图证据、App Privacy 已发布确认、受监管医疗器械状态 `No`。submission pack 与 Review Notes 的 Draft 标记是上述阻断的保护结果，不应提前移除。

## 2026-07-24 Build 236 TestFlight Release

- 从干净源码提交 `d1a5e8aa83cf7409728fd72fe5efe89b3e9fda1a` 执行 iOS production 构建；App Version `1.3.2`，Build `236`，runtime `1.3.2`，production channel，App Store distribution。
- 发布前基础 release-pack、App Store Connect 凭证预检、TypeScript、设计约束和 lint 均通过；Mobile 全量回归为 285 suites / 2103 passed / 1 skipped / 1 snapshot passed。Jest 存在既有异步句柄未退出提示，使用 `--forceExit` 取得明确 exit 0，断言无失败。
- EAS Build ID `d405e79a-ea2e-4b4a-b14d-de5304a893be` 状态为 `FINISHED`；EAS Submission ID `251e1432-694c-411d-a7c9-e3b88af57f5e` 已成功把二进制上传至 App Store Connect。
- Apple 已接收 Build 236，当前处于 TestFlight processing；只有 App Store Connect 后续显示该 Build 可用于内部测试，才可判定 TestFlight 可安装。
- G6 继续 `BLOCKED`：真机验收和同 Build 截图目标从 Build 235 切换为 Build 236；App Privacy 发布确认及受监管医疗器械状态 `No` 仍未完成，禁止据此提交 App Review。
