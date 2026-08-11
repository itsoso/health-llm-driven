# Dossier: iOS 1.3.3 App Store 正式发布

| 字段 | 值 |
|---|---|
| slug | `ios-1-3-3-app-store-release` |
| 创建日期 | 2026-08-05 |
| 当前阶段 | Build 256 已完成 EAS/ASC/TestFlight、精确 IPA、ASC 绑定、审核账号真实登录及物理 iPhone 6/6 安全自动子集；补剂/照片卡第四轮独立安全评审 BLOCK 已整改，并追加修复照片餐食确认失败时的安全可读错误提示；第五轮独立 G4 裁决前，App Review、production OTA、部署及错误记录撤销继续冻结 |
| 状态 | implementing |
| 负责 | product / mobile release / Codex |
| 反馈环 | EAS Store Build → TestFlight → App Store manual release |

## Correct Course

- [x] Correction Block（2026-08-05）：最新 `main` CI 在依赖审计处失败；在 T4 前插入 T3.5 修复 Python 锁文件漏洞并重验 Mobile advisory，禁止带红进入原生构建。
- [x] Correction Block（2026-08-10）：T7.5 首轮独立安全评审判定 `BLOCK`。旧基线“模型名称只要是当前消息任意子串即可信”可被“补剂/图/打卡”等通用词绕过；owner-bound photo token 又跳过整个 Mobile 非饮食闸，合法 token 配药名仍能进入提交。范围退回 S5：补剂只接受当前文本中动作绑定、去剂量后的具体实体完全匹配并拒绝通用类别/动作词；照片卡只豁免阿拉伯数字后的食物切片单位，药名/补剂名仍由 Mobile 与 Backend 词库双层拦截。重跑 G3 与新的独立 G4 前，禁止部署、OTA、App Review 和生产删除。
- [x] Correction Block（2026-08-10）：T7.5 第二轮独立安全评审仍判定 `BLOCK`。动作绑定提取仍接受含指令、指代、多实体或频率剂量的长串；Backend 在移除空格后破坏英文词边界，Mobile 的强信号词又未覆盖 `warfarin` / `aspirin` / `azithromycin` / `fish oil` / `omega-3`，导致合法照片 token 下仍可写为饮食。范围再次退回 S5：单补剂只接受无残余的有界实体；Backend 使用保留边界的共享药品/补剂名称检测并安全分隔紧邻剂量，Mobile 同步 fail-closed。第三轮独立 G4 GO 前继续禁止部署、OTA、App Review 和生产删除。
- [x] Correction Block（2026-08-10）：T7.5 第三轮独立安全评审仍判定 `BLOCK`。`+` / `plus`、遗漏指令/频率和多段剂量仍能成为补剂名；`coq10` / `b12` / `d3` 这类数字结尾名称紧邻数字剂量时又会被错误切分并穿透照片饮食保护。范围退回 S5：名称必须是完整 canonical alias 或满足受限单产品形态，拒绝结构连接符、多 canonical 实体和嵌入剂量；剂量边界改由词库 lookahead 识别而非改写名称，Mobile 同步完整 token 边界。新的 committed G3 与第四位独立 G4 GO 前继续禁止部署、OTA、App Review 和生产删除。
- [x] Correction Block（2026-08-10）：T7.5 第四轮独立安全评审仍判定 `BLOCK`。全角 ASCII、Unicode dash、零宽字符及下标数字可绕过 Mobile/Backend 名称检测；未加分隔的英文多补剂串仍能被当作单一名称；Mobile 对 `vitamin D1000IU` / `coq10200mg` 等紧邻剂量识别不足，造成发起 POST 后由 Backend 拒绝的“保存失败”体验。范围退回 S5：两端统一 NFKC、Unicode dash 与 invisible-character 规范化；共享词库检测紧邻剂量和连写多实体；取消任意未知产品名的开放形态，只有 canonical 名称可直接写入，未知新名称必须由用户在当前纯文本消息中用明确引号包围。第五位独立 G4 GO 前继续禁止部署、OTA、App Review 和生产删除。
- [x] Correction Block（2026-08-11）：照片餐食草稿确认仍出现“操作失败，请稍后重试”。新增回归覆盖 `胡萝卜 约3段 · 南瓜 约2块 · 红枣 约3颗 · 玉米 约1小段` 可确认入库、4xx 草稿业务错误可读、5xx/内部 DB 异常不得泄露到移动端 toast。后端 `POST /diet/records` 的内部异常 detail 改为通用文案，移动端仅展示安全 4xx `detail` 并对 token/stack/DB 关键词降级。第五位独立 G4 需同时审查该错误提示边界。

## S0 · 用户需求（逐字）

> 回到原始目标，本周要发布一个正式版本，review代码，思考还有哪些需要改进，以及如何通过appstore的审核，形成规划

- 谁用 / 解决什么 / 现在怎么绕过：小巴 iPhone 用户需要一个可公开下载、可稳定登录、能记录和解释健康数据且不越过医疗边界的正式版本；当前依赖内部 Build/OTA，送审材料和精确包证据未闭环。
- 用户选择：2026-08-05 确认 1.3.3 + 新 Build 241+；选择“审核优先、功能冻结”；依次确认三部分设计。
- 锚点用户相关性：连接 HealthKit/Garmin 的健康管理用户；不要求审核员持有穿戴设备。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/app.json`：iPhone-only、HealthKit、隐私清单、按用途权限文案。
  - `mobile/app.config.ts` / `mobile/config/releaseCapabilities.ts`：production 实验能力关闭。
  - `mobile/app/settings.tsx`：隐私政策、账号删除及状态入口。
  - `scripts/check_app_store_release_pack.py` / `scripts/check_ios_app_store_submission.py`：基础与最终送审闸门。
  - `docs/release/app-store/*`：提交包、审核说明、隐私标签、截图和真机验收模板。
- 代码风险：`mobile/components/dashboard/RhinitisCard.tsx` 对所有用户展示两种处方药和固定剂量，缺失时自动创建，写失败被静默吞掉。
- 材料缺口：提交包和审核说明仍指向 1.3.2 Build 237 且为 Draft；缺审核账号/电话、当前截图、真机证据、已发布隐私标签、年龄分级确认和 ASC 凭据。
- 构建事实：最新 Store Build 240（EAS `a62a4dc5-f542-4cfe-bc87-8eb0d84a7ff4`）完成于 2026-07-29；IPA 为 Xcode 26.2 / iOS 26.2 SDK，但不嵌入当前主干代码。
- 基线验证：Mobile 292 suites / 2,399 tests PASS；TypeScript PASS；lint 0 errors / 92 warnings；依赖无 high/critical；基础 App Store 闸门 PASS；严格 final-submit 按预期 FAIL 于外部材料。
- 生产可用性：隐私政策 HTTP 200；健康检查报告 API、PostgreSQL、Redis、Celery healthy。
- 平台/安全硬约束：2026-04-28 起上传须使用 Xcode 26 / iOS 26 SDK；健康数据、账号删除、完整演示账号、发布后的 App Privacy 和医疗器械声明必须准确；审核期间不得用 OTA 改变精确包行为。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `SafetyGuardian`, `HealthTwin`
- core_loop_step: Data In → Health Twin → Daily Plan → Execution → Review/Learn
- target_surface / safety_level / autonomy_tier: Mobile + App Store + Backend / medical_boundary + privacy_sensitive / manual_confirm
- source_of_truth: Backend for health/account facts; App Store Connect for submission metadata; EAS/IPA for binary evidence
- spec_required (§8.1): yes（改变用药记录安全行为并涉及正式跨系统发布）
- smallest_end_to_end_slice: 移除产品自带处方 → 精确 Build 验收 → 材料闭环 → 提交 → 手动发布验证
- stale_surface_to_remove: 鼻炎卡硬编码药物/剂量、Build 237/1.3.2 送审文案
- **裁决**: PASS —— 恢复/加固既有健康记录与执行闭环，不增加诊断、治疗或新自治写路径。
- 用户确认: ☑ 2026-08-05

## S2 · PRD / Feature Spec

- PRD: `docs/prd/2026-08-05-ios-1-3-3-app-store-release.md`
- Feature Spec: `docs/specs/active/2026-08-05-ios-1-3-3-app-store-release.md`
- 引用的权威边界：R4 身体状态/安全边界、R15 失败透明、HealthKit/隐私/写入承重墙。
- 边界：不新增功能；不诊断、开药、调整剂量；不以 OTA 代替 Store Build；不保证 Apple 审核完成时间。
- 验收 Gate：G3 全绿、G4 GO、G5 精确包/TestFlight/服务健康、G6 公开版本真机确认。
- 未决问题：无阻塞性未决问题。

## S3 · 规划

- Design: `docs/plans/2026-08-05-ios-1-3-3-app-store-release-design.md`
- Implementation: `docs/plans/2026-08-05-ios-1-3-3-app-store-release.md`
- 发布前聊天视觉层级 Design: `docs/plans/2026-08-06-mobile-chat-visual-hierarchy-design.md`
- 发布前聊天视觉层级 Implementation: `docs/plans/2026-08-06-mobile-chat-visual-hierarchy.md`
- Provider 流总时限 Design: `docs/plans/2026-08-09-provider-stream-total-deadline-design.md`
- Provider 流总时限 Implementation: `docs/plans/2026-08-09-provider-stream-total-deadline-implementation.md`
- 补剂写入证据与照片卡保存 Design: `docs/plans/2026-08-10-grounded-supplement-and-photo-card-save-design.md`
- 补剂写入证据与照片卡保存 Implementation: `docs/plans/2026-08-10-grounded-supplement-and-photo-card-save.md`
- 分阶段：功能冻结 → 医疗风险修复 → 发布闸补强 → 材料 → G3/G4 → EAS Build → 精确包真机 → 提交 → 手动发布/G6。
- 反馈环路由：本地/Jest → EAS Store Build（原生版本变更）→ TestFlight → App Store；审核期间 production OTA 冻结。
- 长杆：Apple 审核时长、TestFlight 处理、审核账号稳定、截图/隐私/年龄分级人工确认。

## G2 · 可行性 + 安全压测

- 评审方式: Codex code/config challenge + Apple primary-source review + 用户逐节确认
- 硬阻断（已焊进规划）：
  - 不提交 Build 240；新包必须嵌入当前审定代码。
  - 移除硬编码处方/剂量和静默失败。
  - 年龄分级、App Privacy、医疗器械 `No`、审核联系人和账号必须完成。
  - 同一 Build 完成真机/截图/工具链证据。
  - 审核期间冻结 production OTA。
- 待拍板分叉：无；用户已选择审核优先方案。
- **裁决**: PASS —— 用户确认 2026-08-05。

## S4 · 研发任务分解

- 跨端 API 契约：无 schema/API 变更；用药写入继续使用现有用户确认路径。
- 任务表：
  - [x] T0 干净 origin/main 基线、并发检查、冻结声明
  - [x] T1 鼻炎卡医疗安全 TDD 修复
  - [x] T2 版本 1.3.3 与配置测试
  - [x] T3 年龄分级/OTA 冻结/IPA 工具链最终闸
  - [x] T3.5 主干依赖审计修复与 CI 复绿
  - [x] T4 审核账号与虚构数据验收
  - [x] T5 提交材料与 App Store Connect 字段
  - [x] T6 G3 全量 + 独立 G4
  - [x] T7 EAS Store Build / IPA / TestFlight（Build 241 历史证据；已被纠正回执变更取代）
  - [x] T7.1 Build 242+ EAS Store Build / IPA / TestFlight（Build 245 已构建、上传、通过精确 IPA 二进制闸并进入内部 TestFlight）
  - [x] T7.2 紧凑聊天头部候选归档 / IPA / ASC 上传（Build 253 已完成本地 Xcode 正式归档、精确 IPA 闸和上传；Apple processing 尚待确认）
  - [x] T7.3 Build 254 本地 Xcode 候选 / ASC / TestFlight / 物理 iPhone 自动验收（6/6 PASS；因无 EAS Build ID，仅作功能与二进制证据，不替代最终 EAS 候选）
  - [ ] T7.4 照片发送 provider 流总时限 Backend 修复 / 部署 / Build 256 复验（代码、本地回归与生产部署已完成；真机终态待完成）
  - [ ] T7.5 无证据补剂写入阻断 / owner-bound 照片卡保存 / 错误记录受控撤销（第四轮独立安全评审 BLOCK 已整改；新增 Unicode 兼容形式、隐藏字符、连写多实体、紧邻剂量、未知名称显式引号、照片餐食 3段/2块/3颗/1小段保存与安全错误提示回归已通过，待第五位 reviewer GO；部署和线上纠错尚未开始）
  - [ ] T8 精确 Build 真机与截图
  - [ ] T9 final-submit / App Review
  - [ ] T10 手动发布 / production G6
- 并发检查：2026-08-05 已检查开放 PR 与 `origin/main` 最近提交；未发现其他变更占用鼻炎用药 surface 或 1.3.3 发布配置。1.3.3 仅接收审核阻断修复，其他请求进入 1.3.4。

## S5 · 实现

- 执行方式：用户选择全局隔离 worktree；未使用含用户未提交文件的主工作区构建、测试或暂存。
- Worktree：`/Users/liqiuhua/.config/superpowers/worktrees/health-llm-driven/ios-1-3-3-app-store-release`
- 分支 / base：`codex/ios-1-3-3-app-store-release` / `dddff6ee1f3e6487fc22b8742aba030f2e587b5b`（当时最新 `origin/main`）。
- 已完成：
  - `4d6ba5b25`：移除鼻炎卡内置处方药、固定剂量、自动建药/记录及静默失败；保留洗鼻/喷嚏观察和通用用药管理入口。
  - `7ffd2e048`：production 版本升为 1.3.3，保持 `appVersion` runtime 和窄能力面。
  - `43c73a621`：final-submit 新增年龄分级、production OTA 冻结、精确 app/build、`DTXcode` / `DTPlatformVersion` 证据闸。
  - `588110a22`：新增鼻炎安全测试保持 lint-neutral。
  - `a8bf8f0b6`：升级 `aiohttp 3.14.3`、`cryptography 50.0.0`、`postcss 8.5.23` 和分 major 的 `brace-expansion` 安全版本，重生成 Linux x86_64 Python exact lock 与 Mobile lock，清空 npm audit 例外。
  - `e0c2a1e08`：同步 Python 与 Mobile 依赖安全契约测试，并显式锁定 `aiohttp 3.14.3` 契约。
  - `23e095ff1`：关闭依赖审计子闸并记录独立兼容性/安全评审证据。
  - `55f2ca457`：把 ASC 草稿升级为 1.3.3 后，同步审核材料、T4/T5 部分验收和人工阻塞项。
  - `ac1695445`：补齐云端语音转写和 linked Product Interaction 隐私披露，更新 Web/Mobile 政策并加固 release-pack 漂移闸。
  - `4af790ecc` / `2a7577c3a`：冻结发布前聊天视觉层级设计与实施计划，范围仅限标题、第一排焦点条、助手身份和输入栏的层级/间距。
  - `38186b9fe` / `c8736d717` / `7af1d1b3f` / `0182e9c2f`：按“舒展易读”方案完成聊天界面视觉优化；保持正文 15/23、44pt 触控目标、业务行为、API、健康数据与写入流程不变。
  - `9d8416b11`：清理新增测试的 lint warning，保持 Mobile 既有 92 warnings 基线不增长。
  - `2677a4d44`：真机验收改为人工预登录、禁止 XCUITest 接收审核凭据；live gate 要求固定简报是默认最新且只有精确两条消息；新增 revision/发布锁约束的非敏感生产重置入口。
  - `140bd788a`：补齐 AudioData、DeviceID、ProductInteraction 和 UserID Analytics；把 iOS preflight 加固为固定 12 类 inventory、草稿↔manifest 精确集合、linked/tracking/purposes 逐项一致及 schema/unknown/duplicate fail-closed。
  - `0da9ddd0b` / `b8c318157` / `a26477b30`：冻结紧凑聊天头部规格，补强确定性真机验收；将头像收至 24pt、标题收至 21/26、标题箭头收至 13pt，同时保留 44pt 触控目标和既有行为。
  - `a1d6f7d16` / `30fdc3f90` / `27f9d458c`：冻结照片发送卡流修复设计与实施计划；为主 streaming provider 和 streaming stable fallback 分别增加 120 秒 wall-clock 总时限。主 provider 未发正文时复用既有稳定降级；已发正文时只 error finish、不换模型重复回答；fallback 再卡住时也必须终止并释放回合。Mobile、数据库、健康写入与回执契约均未改变。
- 2026-08-09 Build 256 人工照片验收中间证据：系统相机入口 PASS；照片草稿及发送文案在强制终止/冷启动后仍保留，证明图片资产与用户 turn 已持久化。生产侧内容最小化证据显示 vision 已完成、上游 streaming 请求已返回 HTTP 200，但模型流在持续非终态分片后未结束，直到外层约五分钟 deadline 才释放；后续同会话发送在此期间按设计返回 409。用户消息和图片已持久化，助手终态缺失，故根因不是上传或本地草稿丢失。
- 根因修复选择经用户确认采用服务端方案 A：HTTP per-read timeout 只能约束相邻字节的空闲时间，不能约束持续 keepalive/reasoning 的总迭代时间；`27f9d458c` 在 executor 的两个 streaming 边界统一加入独立总预算。该改动不需要新 iOS Build 或 production OTA，部署与同一 Build 256 真机复验完成前仍视为发布阻断。
- 2026-08-10 生产补剂/饮食卡复验：补剂 turn `9081` 本轮 `has_image=false` 且用户未写出补剂名，模型却供应“维生素D”；Backend 随后成功创建 definition `73` 和 record `1073`，verified receipt 证明这是无证据成功误写，不是回执误报。随后 owner-bound 餐食照片卡的两次确认只产生 `card_action_failed` 客户端事件，Backend 没有收到 `/diet/records`；精确 payload 的“胡萝卜约3片”命中 Mobile 将任意“片”视作药片的宽启发式，同时 Mobile 丢弃已有 `photo_draft_token`。用户确认采用安全方案：补剂名必须出现于当前纯文本回合，附件回合只识别不写；照片饮食卡保留 owner-bound 草稿 token，由 Backend 所有者/过期/饮食分类闸继续裁决。代码已完成，错误生产记录保持原状直到 committed diff 通过独立安全评审后再走 owner-scoped API 撤销。
- 当前断点：后端与生产合成审核数据均已恢复；Build 245 的精确 IPA / TestFlight 子闸虽已通过，但已被紧凑聊天头部源码 `a26477b3000b9b44c53e8c20fc0f19904b3a7f03` 取代。Build 253 已通过本地 Xcode 26.5 正式归档、精确 IPA 哈希/验签/版本/能力/12 类隐私语义闸，并由 Organizer 上传 Apple；Apple processing、内部 TestFlight 和精确候选物理 iPhone T8 尚未确认。开发签名的同源码 Build 253 已在物理 iPhone 启动并完成紧凑头部视觉预验；安全自动子集 5/6，通过项不替代精确候选证据。以上证据未全绿前 App Review 继续冻结。
- 2026-08-09 Build 254 精确候选复验：ASC processing 完成并进入内部 TestFlight；物理 iPhone 安装后由应用诊断确认 1.3.3（254）、embedded production runtime，未被旧 OTA 覆盖。首次 4 PASS / 1 FAIL / 1 SKIP 的根因不是代码或审核数据：手机仍登录另一账号，该账号访问的会话不属于受控审核账号；切换到受控审核账号后，最新固定简报和 Today 上下文均出现，完整安全自动子集 6/6 PASS、0 failure、0 skip。原始结果包仅保留本机，不上传；档案只记录非敏感汇总。
- 2026-08-07 Build 241 物理 iPhone 自动子集第二轮共 7 项：6 PASS、1 FAIL。安装包版本/Build 与候选一致；双冷启动登录态、Agent 入口、Today 打开/关闭、未发送草稿前后台保留、隐私和账号删除入口均通过。唯一失败是默认打开了审核账号中更新的普通会话，而不是固定简报；Mobile 按服务端 `updated_at` 打开最新会话属于正确产品行为，根因是 live gate 只证明固定会话存在、未证明它是默认最新且未被追加消息。
- 同轮发现 XCUITest 自动输入正式审核密码会把输入保留在 Xcode 控制台/结果包。该方式立即停用：自动子集改为仅接受人工预登录态，并在发现审核凭据环境变量时 fail closed；固定会话 live gate 改为校验未过滤会话列表首项和精确两条消息；生产重置新增受发布锁和精确 revision 约束的 `deploy.sh --reset-app-store-review` 模式，不轮换密码且只输出非识别性验证结果。正式审核密码须在 App Review 前由发布负责人轮换并重新手工登录，旧密码不得再用于最终证据。
- T4 物理 iPhone（历史 1.3.2 Build 240，仅作预验）执行 7 项自动子集：5 passed / 2 failed。双冷启动首次失败于第二次恢复登录超过 30 秒，隔离重跑 1/1 PASS，判定为一次性恢复超时；会话用例稳定失败，因为设备保留旧 conversation 且生产 19 个会话里不存在最新固定演示会话。服务端 live gate 先前只验证今日计划/每日工件非空，错误放过了这个缺口。语音、相机、分享、写入/纠正/删除仍须在 T8 对同一 1.3.3 候选人工验收。
- T5 ASC 已保存年龄分级问卷（结果 16+，无分级覆盖）、`Regulated Medical Devices: No` 和审核通过后手动发布。App Privacy 已按 checked-in JSON 发布 12 个数据类型，产品页预览可见；公开隐私政策已部署并验证 2026-08-05、云端语音音频和 linked 客户端事件文案。未添加构建、未提交审核。
- T5 App Privacy 复核发现旧的“未收集数据”与生产事实不符，立即停止发布。根因是隐私 taxonomy 漂移闸只覆盖饮食照片，未绑定 `/chat/transcribe` 的云端音频出口和持久化的认证客户端事件。已按 TDD 增加跨代码/声明/政策防漂移闸并发布更正答案。
- 2026-08-05 T4/T5 进行中证据（`2026-08-05T11:25:22Z`）：
  - 审核账号凭证仅存在受控发布环境，未复制进 worktree 或 Git；production live gate 验证账号密码登录、`/auth/me` 身份、今日计划和每日工件均 PASS。
  - 虚构数据 seeder 契约 4/4 PASS；生产 seeder 与评审版本 SHA-256 一致，但真机证据证明“无需重置正式审核账号”的旧判断错误：固定演示会话未进入 production 最新列表，必须重跑 seeder 并把这项事实焊进 live gate；无需轮换密码。
  - 单独创建随机合成 QA 账号并发起删除申请；创建、查询、7 天处理窗口、重复提交幂等、pending 状态继续登录及正式审核账号隔离均 PASS。账号/密码、用户 ID、删除请求 ID 未输出或提交，删除申请留给既有受控运维清单处理。
  - 物理 iPhone 后续恢复 available 并完成上述 7 项自动子集；不得用 API 或历史 Build 替代 T8 精确候选验收。
  - App Store Connect 1.3.3 状态仍为 `PREPARE_FOR_SUBMISSION`；en-US 元数据、审核联系人/账号/备注和手动发布设置已复核保存，未绑定 Build、未创建 review submission。
  - 1.3.3 是首个 Store 版本，Apple 在当前状态拒绝 `whatsNew`，故首次提交保持该字段为空；年龄分级、App Privacy 和医疗器械人工项已完成并写入发布机开关。
  - 2026-08-06 T4 收口：release checker 现在从受控 fixture 读取固定简报标题和精确消息对，登录后按当前用户查询会话并 fail closed；聚焦测试 45/45、线上只读 live gate 和基础 release-pack checker 均 PASS，未输出账号或密码。

## G3 · 测试闸

- 预实现基线：Mobile 292/292 suites、2,399/2,399 tests PASS；TypeScript PASS；lint 0 errors / 92 warnings；Mobile 依赖 high/critical=0。
- 2026-08-05 首批集成：
  - Mobile 293/293 suites、2,403 passed / 1 skipped（2,404 total）；TypeScript PASS。
  - Mobile lint 0 errors / 92 warnings，与基线一致；changed files 未新增 warning。
  - Mobile production audit PASS，无 high/critical advisory。
  - `backend/tests/test_app_store_release_pack.py`：36/36 PASS。
  - App Store release pack、iOS submission preflight、doc drift 均 PASS。
- 主干 CI 失败证据：run `30984698027`（base `dddff6ee1`）及修复前最新 run `30993466431`（commit `926f40639`）均 FAIL；后者其余测试/构建 jobs 通过，失败集中在审计：
  - Python：`aiohttp 3.14.2` / `PYSEC-2026-3545`（修复 3.14.3），`cryptography 49.0.0` / `PYSEC-2026-3552`（修复 50.0.0）。
  - Mobile 当次远端审计报告 `brace-expansion` / `minimatch` 的 `GHSA-rgw5-rvv9-x895`；当前本地同一 Gate 已 PASS，仍须以新远端 CI 复验，不能仅凭本地推断 advisory 已撤回或解析变化。
- 2026-08-05 T3.5 复验：
  - 官方 npm registry 完整与 production-only audit 均为 0 vulnerabilities；audit policy gate PASS，exceptions 为空。
  - Python 3.12 exact hashed lock 安装与 `pip-audit --require-hashes` PASS；Garmin / Fernet / HKDF / 加密确认相关回归 75 passed / 2 skipped。
  - 依赖契约测试 21/21 PASS；Mobile 293/293 suites、2,403 passed / 1 skipped；App Store release pack 36/36 PASS，checker 与 iOS submission preflight PASS。
  - 独立代码评审 `Ready to merge: Yes`，无 Critical / Important / Minor；独立依赖安全评审 `GO`，旧 Fernet 密文解密、HKDF 字节一致性和篡改 `InvalidToken` fail-closed 均 PASS。
  - 主干 CI run `30998114422`（commit `e0c2a1e084829abc0340b329b1a81e82e9812eaa`）`completed/success`，44/44 jobs 成功。
- 2026-08-05 T6 全量闸（`2026-08-05T11:50:54Z`）：
  - Mobile Jest 293/293 suites、2,403 passed / 1 skipped（2,404 total）；TypeScript PASS；lint 0 errors / 92 baseline warnings；npm full / production audit 与 policy gate 均 PASS、0 vulnerabilities。
  - App Store release-pack 测试 41/41 PASS；基础 checker、iOS submission preflight、doc drift 和 `git diff --check` PASS。
  - 主干 CI run `31003555856`（commit `642740f3729bd81ba599d94eefced38d2a1241be`）`completed/success`，44/44 jobs 成功，0 failed；包含 G4 隐私/精确构建整改及 41 项 release-pack 测试。
- 2026-08-05 T5 隐私漂移整改：先新增云端语音和客户端事件漏报回归测试并确认红灯，再更新声明、Web/Mobile 隐私政策和机器闸；针对性 4/4、release-pack 43/43、基础 checker 与 `git diff --check` PASS。主干 CI run `31067249388`（commit `ac1695445666658863d8ef5935820b0a2329cf18`）`completed/success`，44/44 jobs 成功，0 failed。
- 2026-08-06 发布阻断热修复本地证据：媒体授权对抗聚焦集 280 passed；餐食图片领域/工具裁剪/Agent food vision 路由广集 1057 passed；用药与 release gate 聚焦集 126 passed；基础 release-pack checker 及审核账号 live gate PASS。新提交的主干 CI 真实色仍待取得。
- 2026-08-06 AIGC 外发确认整改最终证据：后端确认/令牌/API/网关/能力/force 聚焦集 660 passed，分类器广集 579 passed；Mobile 卡片与通用 action 115 passed，Web 卡片 40 passed 且无 jsdom 网络噪声；release-pack 48 passed。Backend Ruff、Mobile/Web TypeScript、两端 lint（0 errors）、基础 App Store checker/preflight 和 `git diff --check` 均 PASS。generated OpenAPI types 已同步到 Mobile/Web 并由 worktree venv 临时全量重生成逐字节复核；主干 CI 真实色仍待取得。
- 2026-08-07 聊天视觉层级优化证据：相关 Mobile Jest 197/197 PASS；完整 `scripts/mobile-fast-test.sh --all` PASS，TypeScript PASS，lint 0 errors / 92 baseline warnings，设计漂移检查 PASS。iPhone 17 Pro Max / iOS 26.5 模拟器 Release 构建成功并完成安装、冷启动到登录页，无启动崩溃；本地 QA 仅通过 `SENTRY_DISABLE_AUTO_UPLOAD=true` 关闭无发布凭据的符号上传，未修改或弱化正式归档配置。模拟器无审核账号登录态，且物理 iPhone 当前不可用，因此登录态聊天页视觉烟测与同一精确 Store 候选验收仍保持 pending。
- 2026-08-07 主干 CI run `31169318136`（commit `1767cfd7b52678fcca8a8290da14a91e1cbce797`）`completed/failure`：44 jobs 中 39 success、5 failure；实质红灯为 `backend-quality` 的 `h2 4.3.0 / CVE-2026-71554`、`mobile-typecheck` 的 `js-yaml / GHSA-5p4m-2wfm-xmqj`，以及两个 agent-executor 分片各 1 条回归，汇总 job 随之失败。G3 据此保持 pending，未启动 EAS。
- 2026-08-09 最新主干 CI run `31305757302` 重跑后 `completed/success`；本地 Mobile 全量以 `--maxWorkers=2` 复验 293/293 suites、2,443 passed / 1 skipped，前一次 `useAuth` 单点失败隔离复验 33/33 PASS，确认属于 CI 抖动而非源码回归。
- 2026-08-09 账号密码登录错误提示热修复：生产审核凭据直连 `/auth/login/json` 与 `/auth/me` 均成功，排除账号、密码和后端故障；根因是账号模式 catch 已设置 `inlineError`，但 JSX 只在手机号/邀请分支渲染该状态。先新增失败回归并确认红灯，再在账号表单内渲染无障碍 `alert`；聚焦 23/23 与 Mobile 全量 293/293 suites（2,444 passed / 1 skipped）、TypeScript、lint 0 errors / 92 baseline warnings、`git diff --check` 全部 PASS。
- 2026-08-07 CI 整改本地证据：`h2` 精确锁定 4.4.1，`js-yaml` 两条兼容 major 分别锁定 3.15.1 / 4.3.1；Python hashed lock audit、Mobile full/production audit 与空例外策略闸均为 0 known vulnerabilities。复杂来源图片创作仍保持 G4 审定的通用工具集且不强制外发，但媒体生成意图在更早阶段明确跳过餐食识别；两个原失败 CI 分片 340/340、329/329 PASS，G4 分类/能力矩阵 1184/1184 PASS，依赖契约 21/21、完整 Mobile gate PASS。新修复提交的主干 CI 真实色仍待取得。
- 2026-08-07 修复提交 CI run `31175721526`（commit `0116165bdd809c8e1262b3882f480c6fb1f32164`）44 jobs 中 42 success、2 failure：原有依赖与两个 agent-executor 红灯均已转绿；唯一实质失败为 `backend-quality` 按设计阻断 `agent_executor.py` 运行时改动缺少一次性 live-eval 确认，`backend-tests` 仅为汇总失败。未绕过该闸，未启动 EAS。
- 2026-08-07 真实 LLM 评测证据：`APP_ENV=test DATABASE_URL=sqlite:///:memory: backend/venv/bin/python scripts/harness_llm_regression_gate.py --include-live-llm --json` exit 0；`invariants` 12/12、`health_agent_core` 50/50、真实 `orchestrator` 5/5，平均分 0.94，相对 `main` 无 regression；轨迹契约 12/12、金标 9/9。实际模型为 `MiniMax-M2.5`；临时 SQLite 未建 usage telemetry 表产生非生产旁路告警，但真实模型生成、LLM judge 与 Gate 结果均成功。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 只允许用于承载本证据的下一轮 CI，终态后必须删除并复证不存在。
- 2026-08-07 证据提交 CI run `31179125236`（commit `561b01c2750580b3e4a57943a85211c376915cde`）`completed/success`：44/44 jobs success、0 failure。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 已在终态后删除，仓库变量按名称复证为 0 条；后续 LLM 高风险改动重新默认阻断。
- 2026-08-07 G3 收口提交 CI run `31180977412`（commit `c109e934c4b2c633979bd5c0a7cd97a8f62e570d`）`completed/success`：44/44 jobs success、0 failure；该 commit 是 Build 241 的精确 EAS source commit。
- 2026-08-07 T8 流程整改本地证据：真机验收/部署脚本 135/135 PASS；审核账号/发布包 55/55 PASS；Ruff、shell/Ruby 语法、基础 release-pack、doc drift 与 `git diff --check` PASS。线上新 live gate 在重置前按预期 FAIL 1 项，证明旧检查的假绿已被关闭。
- 2026-08-09 登录失败提示热修复：账户密码分支原先只写入 `inlineError`，但 JSX 未渲染该状态；新增 `accessibilityRole="alert"` 的内联提示并按 TDD 先确认回归用例失败、再修复为通过。聚焦登录测试 23/23、Mobile 全量 293/293 suites（2,444 passed / 1 skipped）、TypeScript、lint 0 errors / 92 baseline warnings、App Store release pack、doc drift 和 `git diff --check` 均 PASS；主干 CI run `31325643220` 在 commit `75f61f694c4711a7b349eb63fb7af5e48d9f9012` 上 44/44 jobs success。
- 2026-08-07 提交 `2677a4d44` 的 CI run `31234249896` 出现新的 registry advisory 红灯：Frontend `nanoid <3.3.17` 高危及旧 PostCSS 链，Mobile 同源依赖审计失败；按 Gate 停止部署。两个树已统一锁定到兼容 patch `nanoid 3.3.18`、`postcss 8.5.26`；完整及 production audit 均为 0，审计策略 4/4、版本契约 18/18 PASS。Mobile 全量 293/293 suites、2,407 passed / 1 skipped，TypeScript 与 lint（0 errors / 92 baseline warnings）PASS；Frontend 57/57 files、338/338 tests PASS，production build/TypeScript/73 个静态页面与 lint（0 errors / 33 baseline warnings）PASS。Frontend 首轮全量有 1 条异步加载测试波动，隔离 10/10 及第二轮全量均 PASS，未修改该非相关 surface。待新主干 CI 复绿。
- 2026-08-07 提交 `a9bbc1d65` 的 CI run `31234813565` 在 Frontend/Mobile 安装依赖阶段 FAIL：两份锁文件仅有新补丁包的 4 条 `resolved` URL 被本机 npm 配置写成不可公开访问的内网镜像，GitHub runner 因 DNS `ENOTFOUND` 终止；不是代码、类型或新 advisory 红灯。已将 4 条 URL 校正到公共 npm registry，逐项核对上游 integrity 与锁文件一致，并新增锁文件不得包含内网或明文 HTTP 源的回归契约；两端从公共源完整 `npm ci` 与显式高危审计 exit 0。新主干 CI 复绿前继续禁止部署。
- 2026-08-07 提交 `20fbf83fc` 的 CI run `31235170596` 证明公共源修复有效：Frontend 全流程 PASS，Mobile 成功安装后被新更新的 `image-size` 两条高危无限循环 advisory（`GHSA-w3rx-r6r6-pgpr`、`GHSA-5p2g-fcmc-qvqq`）阻断。上游截至本次核验没有已发布修复版本；该包仅由 Expo/Metro 构建工具链传递使用，不进入 iPhone 运行时。已对 ICNS 与 JXL/HEIF 零长度解析路径打最小本地补丁并用恶意输入子进程超时测试验证，干净 `npm ci` 证明 `patch-package` 自动应用；审计策略仅为这两个 GHSA 设置至 2026-08-14 的短期到期例外，未知、缺失和过期 advisory 继续 fail closed，npm 10.9.8（与 CI 一致）复验通过 11 条传递路径。补丁对抗测试 2/2、审计策略测试 5/5、Mobile 串行全量 293/293 suites（2,407 passed / 1 skipped）、TypeScript 与设计 token 闸均 PASS。新主干 CI 复绿前继续禁止部署。
- 2026-08-07 安全修复提交 `5e7ce5651` 的 CI run `31235742871` `completed/success`：44/44 jobs success、0 failure；Mobile 新增恶意图片防死循环测试、短期审计策略、TypeScript、设计闸与 Jest 全部通过，Frontend、Mac、PostgreSQL 与全部后端分片同步通过。
- 2026-08-07 后端部署证据：精确 commit `5e7ce5651` 通过正式 `deploy.sh` 上线；发布前数据库备份、237 表恢复演练、站外加密归档哈希/HMAC、回滚 schema、远端 revision 均通过，部署中/后多轮健康度 60/60，runtime-only KB guard/staged、Skills 22/22 通过，feature flag 继续为 false。部署脚本按保留 7 份策略自动淘汰 1 份最旧备份。
- 2026-08-07 审核账号重置首次执行按 Gate FAIL 并回滚：生产已有 `medical_exam_items` 引用体检主记录，旧 seeder 先删父记录触发 PostgreSQL 外键保护，未留下半重置数据。修复按子→父顺序清理审核账号专属的体检明细、运动分析/心率区间与计划反馈；新回归先红后绿，审核账号 6/6、release-pack 50/50、部署脚本 125/125、Ruff PASS，并将该用例加入真实 PostgreSQL 16 CI 语义闸。新主干 CI、重部署与生产重置成功前继续阻断 T8/G5。
- 2026-08-07 重置外键修复提交 `5d9283335` 的 CI run `31239215094` `completed/success`：44/44 jobs success、0 failure；包含真实 PostgreSQL 16 的审核账号子→父清理回归。随后精确 commit 通过正式 `deploy.sh --backend --yes` 上线：新数据库备份、237 表恢复演练、站外加密归档哈希/HMAC、回滚 schema、远端 revision、runtime-only KB guard/staged、Skills 22/22 和多轮健康度 60/60 全部 PASS，feature flag 继续为 false；备份轮换按保留 7 份策略自动淘汰 1 份最旧备份。
- 2026-08-07 `deploy.sh --reset-app-store-review` 在精确 revision 与发布锁保护下成功；仅输出非敏感结果。生产 live gate 随后 PASS，证明审核账号登录、身份、每日计划、每日工件及默认最新固定简报均符合审核 fixture；未输出或提交账号、密码、令牌和合成健康内容。
- 2026-08-07 发布证据提交 `01a45d9e8` 的 CI run `31241371975` `completed/success`：44/44 jobs success、0 failure。
- 2026-08-07 真机验收安全说明漂移整改：runner 与 XCUITest 已正确禁止审核凭据，但 README 仍残留旧的 source 凭据、临时 scheme 注入说明和设备标识示例；现统一改为人工预登录及非识别性占位符，并新增文档回归防止高风险说明或设备 ID 回归。验收 harness 聚焦测试 11/11 PASS。
- 2026-08-08 健康纠正原子性阻断：审核用合成账号的一条饮水纠正轨迹暴露 `health_manage.update.data` 被模型写成 JSON 字符串后，模型错误尝试以 delete/recreate 兜底；旧实现允许错误 delete 穿过分发边界，已删除的合成记录未能恢复，最终回复和通用“已写入”回执也未准确表达实际动作。事件仅记录审核用户序号和资源序号 `#718`，未把账号、密码、令牌或健康原文写入仓库。
- 2026-08-08 修复链：`b8f2976a6` / `b6286ac3b` 安全归一化对象形 JSON 且拒绝非有限常量；`a92e09526` 至 `152f030bd` 把更新/删除意图与操作锁定，并将删除授权收紧为用户原话中的唯一类型 + 精确正整数 ID 双匹配；`7fd8e0fa3` / `42319786b` 对齐旧测试契约；`b46032557` / `caee793e1` 增加生产轨迹与 mutation-proof 逐轮证据；`f00ad1fc4` / `1b2629b90` 增加并加固 create/update/delete 回执动作与 Mobile“已更新/已删除”显示。Build 241 无法显示新 action，已被 Build 242+ 取代；本变更禁止通过 production OTA 送达。
- 2026-08-08 独立双评审：Task 2 spec GO（网关矩阵 16/16、相关 1,004），quality GO（策略 40/40、真实 Executor 11/11、相关 973，Critical/Important/Minor 均 0）；Task 3 spec GO（focused 6/6、相关 274），quality GO（focused 5/5、相关 274，两次强制放行 mutation 均按预期失败，Critical/Important/Minor 均 0）；Task 4 spec GO（Backend 52、runtime 4、Mobile 111、TypeScript PASS），quality GO（Backend 262、runtime + write adapter 244、Mobile 111、存储恢复 48、TypeScript PASS，Critical/Important/Minor 均 0）。
- 2026-08-08 G3 本地合跑：Agent 安全/行为 11 文件在 CI 模式下 1,392 passed；分支补充 2 文件 48 passed；Mobile 6 suites 235/235；TypeScript、doc drift、基础 release-pack 和 iOS submission preflight 均 PASS。真实模型闸使用固定合成数据通过：invariants 12/12、health_agent_core 50/50、orchestrator 5/5（平均 0.94）、trajectory 12/12、goldens 9/9，模型 `MiniMax-M2.5`；一次性确认只在本地进程使用，未写入远端变量。
- 2026-08-08 主干整合复验：无冲突合并 `origin/main` 的 TokenPlan 模型目录提交；后端模型目录 + 参数校验 + capability/gateway + 回执 884/884、Mobile 模型目录 + 回执 + ChatBubble 114/114、TypeScript 与 doc drift 均 PASS。首次合并后 live-eval 因命令未显式覆盖 `.env` 的本地 PostgreSQL 连接而 fail-closed，orchestrator 0/5；改用 `APP_ENV=test DATABASE_URL=sqlite:///:memory:` 后真实 TokenPlan `MiniMax-M2.5` 复验 PASS：invariants 12/12、health_agent_core 50/50、orchestrator 5/5（平均 0.96）、trajectory 12/12、goldens 9/9。本地一次性确认的 live-change gate PASS，未设置远端变量。
- 2026-08-08 G4 整改后组合 G3：后端策略/校验/回执/运行时 15 文件 1,386/1,386，Mobile 回执/ChatBubble/模型目录与 ChatScreen 202/202，TypeScript、Ruff、py_compile、doc drift、基础 release-pack、iOS submission preflight 和 `git diff --check` 均 PASS。严格 final-submit 继续按设计 FAIL 于 Build 242+、精确 EAS/source/IPA、物理 iPhone、ASC 人工确认和截图材料。首次最终树 live-eval 为 4/5（平均 0.91），定位为回答明确使用“就诊”且 LLM judge 5/5、旧关键词却只认“医”的评测假阴性；`0037d23e5` 以红灯测试增加等价医疗转介表达的任一命中语义。修正后 eval 聚焦 68/68，最终真实模型闸 PASS：invariants 12/12、health_agent_core 50/50、orchestrator 5/5（平均 0.90）、trajectory 12/12、goldens 9/9；live-change gate PASS。本地非生产 SQLite 缺 usage telemetry 表仅产生已知旁路告警，不改变 Gate 裁决，未设置远端确认变量。
- 2026-08-08 最终 G4 树真实模型复验：`APP_ENV=test DATABASE_URL=sqlite:///:memory:` 下 live regression exit 0；invariants 12/12、health_agent_core 50/50、orchestrator 5/5（平均 0.94）、trajectory 12/12、goldens 9/9，且 `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 的本地 change gate PASS。非生产临时 SQLite 缺 usage telemetry 表只产生旁路告警；模型调用、语义 judge 和最终 Gate 均真实完成。
- 2026-08-08 发布阻断：严格 final-submit checker 仍按设计 FAIL，缺少 Build 242+ 的 EAS/source/IPA、同一精确候选物理 iPhone、ASC 人工确认与最终截图材料。App Review 保持冻结，新提交远端 CI 与以上发布材料未全绿前不得提交审核。
- 2026-08-09 provider 流总时限 TDD：新增三条异步回归。旧代码下“只有 reasoning、无终态”和“已发部分正文后持续非终态”均由测试看门狗按预期判红；实现后主 provider 无正文超时→稳定降级、已有正文超时→不降级只收尾、fallback 自身超时→单一 error finish 三项全部 PASS。完整 `test_agent_executor_failover_gate.py` 13/13 PASS；更广 Backend 闸与生产部署证据仍待本轮后续补齐。
- 2026-08-10 补剂证据/照片卡 TDD：Backend 两条新回归在旧代码下均因拿到成功 payload 而按预期 RED，证明模型推断名称与附件回合仍会触达补剂 API；Mobile 生产餐食原句在旧代码下精确 RED 为 `invalid_diet_food_items_non_diet`。最小实现后 Backend 补剂/正向查找/回执相关 46/46 PASS，Mobile card action / diet guard / ChatBubble receipt 130/130 PASS；`npx tsc --noEmit`、changed-file ESLint 与 Ruff 全部 exit 0。新增 malformed photo token、文本补剂/药物仍拦、管理/指标即使带 photo token 仍拦的反例保持 fail-closed。G3 仍需 committed-diff 评审及发布前集成闸，不因聚焦测试绿而提前 PASS。
- 2026-08-10 首轮 G4 BLOCK 后的整改 TDD：通用名称对抗矩阵先在已提交实现上 5/5 失败并实际进入 API 路径，随后裸 `维生素` 反例也先红；Backend `阿司匹林 1片` 先被判 `unknown`；Mobile 合法 owner-bound token 下药物/补剂 7 个真实路径断言先失败并走到提交。整改后补剂名称改为当前纯文本中“记录/服用”等动作绑定的具体实体完全匹配，去除前后剂量且拒绝通用类别/指代/动作词；Backend 复用完整药名词库，Mobile 只去除数字切片单位后复跑强信号。最终扩展回归 Backend 339/339、Mobile 222/222、App Store 发布包 54/54 PASS；`npx tsc --noEmit`、changed-file ESLint、Ruff、doc drift、101 份 Dossier 一致性闸及 `git diff --check` 全部 exit 0。重新独立 G4 尚未执行，当前仍为 pending，GO 前禁止进入 S6。
- 2026-08-10 第二轮 G4 BLOCK 后的整改 TDD：补剂指令/指代/多实体长串在已提交实现上 3/4 实际进入 lookup/create/tap；英文具名药与补剂的 spaced/unspaced dose 12/13 被判 `unknown`；带合法照片草稿 token 的 REST no-row 用例在测试环境配置纠正后固定验证。整改新增共享完整补剂名检测、保留 ASCII 词边界的剂量分隔、Mobile 中英文强信号和长串实体残余拒绝。自查继续发现 4 个英文指令/多实体长串会进入成功路径，追加测试先 RED 后 8/8 GREEN。最终本地 G3：Backend 写入/分类/回执/饮食 288/288、Mobile card/client/guard/ChatBubble 191/191、App Store 发布检查 72/72 PASS；TypeScript、changed-file ESLint、Ruff、doc drift、Dossier 一致性闸及 `git diff --check` 全部 exit 0。最终 commit 与第三轮独立 G4 尚未完成，当前仍为 BLOCK。
- 2026-08-10 第三轮 G4 BLOCK 后的整改 TDD：评审实际复现 `维生素D+鱼油`、`vitamin D plus fish oil`、遗漏指令/频率、多段剂量会 lookup/create/tap，且 `coq102粒` / `b122粒` / `d32粒` 可穿透权威饮食分类。真实路径测试先 RED：Backend 分类/词库出现 4 项失败，Mobile guard/card 出现 6 项失败。整改改为 exact canonical alias 或受限单产品形态，拒绝结构连接符、多个 canonical 名称及嵌入剂量，并以剂量 lookahead 保留数字结尾名称；Mobile 同步边界且增加良性子串反例。最终本地 G3：Backend 写入/分类/回执/饮食 320/320、Mobile card/client/guard/ChatBubble 201/201、App Store 发布检查 72/72 PASS；TypeScript、changed-file ESLint、Ruff、doc drift、Dossier 一致性闸及 `git diff --check` 全部 exit 0。commit 与第四轮独立 G4 尚待完成，当前仍为 BLOCK。
- 2026-08-10 第四轮 G4 BLOCK 后的整改 TDD：评审在真实写入路径复现 `Ｄ３2粒`、`ＣｏＱ１０2粒`、Unicode dash/零宽字符/下标数字等 8 个变体可创建记录；`vitaminDfishoil`、`d3-fish-oil` 等连写多实体及宽松未知名称形态仍可取得写入权限；Mobile 对标准 ASCII 紧邻剂量会先 POST 再收到 Backend 400。对抗用例先 RED，整改后 Backend/Mobile 统一做 NFKC、dash 与 invisible-character 规范化，词库识别紧邻剂量和连写多实体；写入权限改为 canonical 名称可直写、未知新名称必须显式引号确认，图片回合只能提示用户在新纯文本回合确认。用户追加早餐照片卡“胡萝卜/南瓜/红枣/玉米”保存失败截图后，补充段/块/颗/小段份量确认回归，并把卡片失败 toast 改为展示后端 `detail` 的安全截断文案，避免只显示“操作失败”。最终本地 G3：Backend 写入/分类/饮食聚焦集 258/258、Mobile card/guard/ChatBubble 聚焦集 207/207、App Store 发布测试 50/50 与 release/preflight 脚本 PASS；TypeScript、changed-file ESLint、Ruff、doc drift、Dossier 一致性闸及 `git diff --check` 全部 exit 0。最终 commit 尚待完成，第五轮独立 G4 前仍为 BLOCK。
- 2026-08-09 部署前 CI 复盘：首次承载提交 `e6bc777f0` 的 CI `31347865871` 因两项历史测试时间边界和预期的 live-change 确认闸失败，未进入部署。Frontend 注册邀请测试写死的 `2026-08-09T20:00` 到期时间已改为稳定未来值，聚焦测试 21/21 PASS；WSCLA 聚合测试在 UTC 周一凌晨把 `now - 2h` 错算到上周，已改用相对 `week_start` 的确定性本周时间，聚焦测试 PASS。真实模型回归在 `APP_ENV=test DATABASE_URL=sqlite:///:memory:` 下 exit 0：invariants 12/12、health_agent_core 50/50、真实 orchestrator 5/5（平均 0.98）、trajectory 12/12、goldens 9/9，且无 regression；实际模型为 `MiniMax-M2.5`。临时 SQLite 未建 usage telemetry 表只产生已知旁路告警，不影响真实模型生成、judge 或 Gate 结果。远端一次性确认变量只允许覆盖承载本证据的下一轮 CI，终态后必须删除并复证不存在。
- **裁决**：实现级 G3、真实模型回归与独立 G4 均 PASS；发布级 final-submit / T7.1 保持 BLOCK。下一步依次取得远端主干 CI、后端部署与生产恢复证据，再生成 Build 242+，不能据此直接提交 App Review。

## G4 · 安全闸

- 触发：用药、健康写入、隐私、认证审核路径。
- T3.5 依赖安全评审：`GO`，无阻断项；未修改用户数据、认证逻辑、医疗建议边界或 App Store 产品行为。
- 2026-08-10 T7.5 首轮独立安全评审：`BLOCK`（High 1 / Medium 1）。High：任意子串依据允许模型把“补剂/图/打卡”等通用词创建为补剂；Medium：owner-bound photo token 关闭整个 Mobile 非饮食闸，且 Backend 当时把 `阿司匹林 1片` 判为 unknown。已按 Correction Block 逐条整改并加入零 dispatch/零 post 对抗测试；必须由新的独立 reviewer 审当前 committed diff，GO 前不得进入 S6 或删除 definition `73` / record `1073`。
- 2026-08-10 T7.5 第二轮独立安全评审：`BLOCK`（High 2 / Medium 1）。High：`维生素D并且帮我打卡`、`这个补剂维生素D`、`维生素D和鱼油` 等残余长串仍可成为补剂名；合法照片 token 下 `warfarin` / `aspirin` / `azithromycin` 及 `fish oil` / `omega-3` / `magnesium` 的剂量文本仍可能落成饮食。Medium：线上清理前置条件必须断言 definition `73` 的 owner-scoped record-id 精确集合为 `{1073}`，有额外记录或 owner 不符即中止。整改与聚焦测试已完成；第三位 reviewer 必须审最终 committed tree 并给出 GO，之前不得进入 S6 或执行清理。
- 2026-08-10 T7.5 第三轮独立安全评审：`BLOCK`（High 2）。High：`+` / `plus`、遗漏的确认/频率词与多段剂量仍能实际写入伪补剂；`coq10` / `b12` / `d3` 等数字结尾名称紧邻数字剂量时被边界改写破坏，合法照片 token 下可能落成饮食。其余附件闸、草稿 owner/expiry/idempotency、隐私 telemetry、良性词边界及精确 `{1073}` 清理方案通过只读复核。已再次退回实现；第四位 reviewer 必须审新的最终 committed tree 并给出 GO，之前不得进入 S6 或执行清理。
- 2026-08-10 T7.5 第四轮独立安全评审：`BLOCK`（High 2 / Medium 1）。High：兼容全角、Unicode dash、零宽字符、下标数字可绕过两端补剂/药名边界，且宽松未知名称形态允许指令前缀或连写多实体取得写入权限；Medium：Mobile 漏识别标准 ASCII 名称紧邻剂量，导致请求发出后 Backend 400。评审确认附件闸、草稿 owner/expiry/idempotency、telemetry、回执与精确 `{1073}` 清理前置条件无新增阻断。已再次退回实现；第五位 reviewer 必须审新的最终 committed tree 并给出 GO，之前不得进入 S6 或执行清理。
- 2026-08-05 完整 release diff 独立评审首轮：`NO-GO`，无 Critical，2 个 Important BLOCK：
  1. App Privacy 草稿错误声明未发布的 `strict_local` / `local_first` 与端上餐食推理，而 production 会把用户选择的图片上传到认证服务。
  2. final-submit 仅校验 EAS build ID / source SHA 格式，未把真机证据绑定到候选 EAS metadata。
- S5 整改：删除错误的 device-only 声明；把 `User Content -> Photos or Videos`、图片上传/草稿/记录用途写入隐私草案，并增加跨 release notes、Mobile `/diet/recognize` 数据流的防漂移测试。final-submit 新增 `APP_STORE_EAS_BUILD_ID` / `APP_STORE_GIT_COMMIT_HASH`（或等价 CLI 参数），要求与真机证据精确匹配，源码 SHA 必须为完整 40 位。
- G4 第一次复评仍 `NO-GO`：发现旧 device-only 声明的拒绝依赖 Review Notes 英文原句，改写文案可绕过。第二轮整改将旧 `strict_local` / `local_first` / 餐食照片 / 端上推理 markers 直接绑定 production `/diet/recognize` 上传事实；Review Notes 缺无本地模型边界或代码无法识别图片上传流时均 fail-closed。7 个针对性测试及 release-pack 41/41 PASS。
- 首轮其余评审项均 GO：鼻炎卡无内置处方/剂量/自动写入，production 无 Watch/Rokid/Siri/background，secret pattern scan 无命中，npm/pip audit 为 0，人工项保持 fail-closed pending。
- G4 第三轮独立复评：`GO`，Critical / Important / Minor 均无；实际重放 Review Notes 文案漂移与无法识别图片上传流两种绕过，均 fail-closed。release-pack 41/41、基础 checker、iOS preflight、Ruff、`git diff --check` PASS；错误 EAS UUID / 完整 source SHA 均被拒绝。
- T5 ASC 人工复核补充发现两条未声明的数据出口：录音经认证 API 发送到云端 ASR，客户端交互事件按 `user_id` 持久化。整改后声明新增 `Audio Data`（linked / App Functionality）和 `Product Interaction`（linked / App Functionality + Analytics），诊断数据仅保留 unlinked Crash/Performance；全部类型均为 not tracking。对应防漂移测试直接绑定 production 代码路径，避免再次回退为“未收集数据”。
- 2026-08-06 热修复首次独立复评:`G4: NO-GO`，无 Critical，4 个 Important：普通/既成图片记录与否定生成仍可误授权 AIGC 草稿；审核 API 基址可使用 HTTP，默认重定向可跨 origin 转发 Bearer。整改后只有未否定的显式生成 reason 可进入 AIGC 工具集；live gate 在基础 URL 与每次请求双层强制 HTTPS、拒绝 URL 凭证/片段并禁止全部重定向。对抗测试与完整聚焦集已绿，等待同一 reviewer 复审。
- 同一 reviewer 二次复评仍 `G4: NO-GO`，无 Critical：常见口语否定和动作后置否定仍可绕过，且邻近子串会误伤“分别/别的”、跨分句新命令与取消旧任务后的重新授权。现已改为显式否定短语、分句边界和局部重新授权关联，并追加“取消重新生成”和后句无关否定边界；53 个对抗用例、830 项路由广集及 126 项用药/发布闸均 PASS，等待第三次独立复评。
- 第三次独立复评继续 `G4: NO-GO`，无 Critical：`不希望/没打算/不再/不应/不该/避免` 及 provider 确认表达仍可强制 AIGC 工具；“分别生成早餐图和午餐图”被误归饮食域。整改已把完整评审矩阵加入测试，收紧后置否定对象并补充受控图片简称；64 个聚焦用例、841 项路由广集及 126 项用药/发布闸均 PASS，等待同一 reviewer 对最终 diff 继续复核。
- 同一轮扩展对抗先以 2 Important `G4: NO-GO` 推动 command-frame 架构重构；新一轮独立复评仍 `G4: NO-GO`（4 Important、无 Critical/Minor）：冒号引用归属、provider 撤销/veto、AI/模型内容约束和 prompt 内容/跨问句最后意图仍有漏洞。现已保留冒号归属，独立追踪 provider veto，补齐口语撤销，禁止把 AI/provider/model 当安全内容约束，只检查最终输出目标后的命令尾部并隔离 prompt 内嵌动作；144 个聚焦对抗、921 项路由广集及 126 项用药/发布闸均 PASS，等待独立复评。
- 最新独立复评仍 `G4: NO-GO`（4 Important、2 类 Minor，无 Critical）：跨标点通用转述、sticky provider veto、确认后的事实限定及动作名词/事实谓词仍有同构绕过。现已逐条落入 24 个安全反例与 11 个正向反例，并用跨分句状态机收紧：转述上下文需明确当前用户转折重领；provider 确认被任何非明确新媒体命令后继失效；上传/分享/外部服务 veto 仅由后续明确 provider 确认解除；prompt 内容与控制动作隔离。220 个聚焦对抗、997 项路由广集、126 项用药/发布闸及静态/结构闸均 PASS，等待同一 reviewer 再复评。
- 后续复评仍 `G4: NO-GO`（4 Important、3 类 Minor，无 Critical）：reporting/出站/动作名词同义词仍可绕过，中文引号内的转折被错当当前用户 reclaim，确认后的元描述因 attribution 早退而未失效。现已改成引号 payload 屏蔽、未知前导默认 attribution、严格裸命令对象语法、create-to-final-output payload span 以及先失效后归因的 provider 状态机；27 个新安全反例、25 个新正向反例及 8 个开放词汇变体均落测。最新 280 focused、1057 route-wide、126 medication/release 与静态闸全部 PASS，等待再次独立复评。
- 最新安全评审给出 `CONDITIONAL GO`：阻断条件是 provider 确认必须使用闭合语法且取消词在任意位置优先；owner GET 必须返回与实际外发逐字节一致的解密 prompt、短时 owner/confirmation/provider/model/prompt-version 绑定 token 并设置 no-store；POST 无 token/篡改/跨确认/过期/版本变化均须在 provider 前 fail closed；Mobile/Web 初始禁用并显示完整纯文本 prompt；通用 Mobile action 不得绕过；复杂源图片指令保持 general toolset，但 provider veto 必须由 gateway 阻断。上述条件现已全部落入代码、生成契约和回归，等待同一 reviewer 最终裁决。
- 其后最终复评返回 `G4: NO-GO`（Critical 0 / Important 2 / Minor 2）：闭合语法删除换行导致分行确认仍被 force；gateway 漏掉“必须断网/只在手机上/不得交由服务商/禁止传到云上”；token 在过期整秒仍可用；生成类型需证明无非预期漂移。现已先补红灯复现，再拒绝闭合语法中的任意空白、扩展 local-only 出站词法、把 token 边界改为严格 `exp > now`，并用临时 OpenAPI 全量重生成与两端 tracked types 逐字节比较。聚焦 9/9、完整相关集 616/616、分类器 576/576、Ruff 与 diff-check PASS，等待下一轮 G4。
- 最终复评确认 provider 授权语法闭合且与 force 共用；空白注入 fail closed；复杂来源图片合法正例保留；capability 最终闸拒绝本地/离线、设备驻留、禁止外发/上云及固定中英混输隐私表达。review token 绑定与整秒过期边界、客户端先审阅后确认链、通用 action 防绕过和 OpenAPI 类型均通过独立重放；Critical / Important / Minor 均为 0。
- 2026-08-08 健康纠正原子性与回执真值变更已完成各任务 spec/quality 双评审；删除只允许用户明确的类型 + ID 精确目标，错误操作在分发前拒绝且无回执，正确同目标重试才清除可恢复拒绝；Mobile 回执正规化拒绝显式非法状态、继承字段和对象 ID，危险资源键安全回退。该证据用于请求本轮独立 G4，不复用此前发布差异的 GO 代替本轮裁决。
- 本轮首次独立 G4：`NO-GO`（Critical 0 / Important 3 / Minor 0）。阻断项为：`shadow`/非法 policy mode 仍可能派发已经拒绝的 destructive 操作；health_manage verified receipt 未绑定请求与结果的精确 record ID；合法 JSON 指数溢出 `±1e309` 可形成非有限 float 并穿过 update data 校验。评审同时确认精确删除 grammar、cross-user 所有权、生产恢复方案、Mobile 真值边界、内容最小化日志和 Build 241 supersession 未发现其他阻断。
- G4 整改提交：`e3d91e518` 将 operation mismatch 与不明确整条删除在 enforce/shadow 下均 hard-block，并在配置和 gateway 双层拒绝非法 mode；`6f5dafee2` 将 health_manage update/delete 的结果 canonical ID 绑定请求 record ID，错误目标不产生 verified receipt、不恢复旧阻断且 runtime replay 保持 reconciliation required；`c6f3877a7` 对字符串 JSON 与已解析对象递归拒绝 NaN/±Inf/指数溢出，同时保留有限指数与 bool。三条均按 TDD 先红后绿并独立提交。
- G4 扩展对抗随后发现并关闭三类同构风险：`eaf7f25c4` 禁止 update 失败后以 create 影子重建；`8f2ebd4f6` 在健康写入服务边界拒绝经字符串/类型强制产生的非有限测量值；回执请求/结果错配、非法 policy mode 与 destructive denial 均由前述整改保持 fail closed。医疗转介评测的开放式正则在否定、疑问、证据不足和条件转介上无法可靠收敛，最终由 `eb62e15ed` / `9757f808f` / `8a0323ddc` 改为结构化 LLM 语义断言：每个硬断言必须返回显式布尔 true，缺失、false、judge 错误或畸形 verdict 均失败，只有断言而没有最低分配置时也不能绕过；真实独立模型正反金标 10/10。
- 同一独立 reviewer 最终复评：`G4: GO`（Critical 0 / Important 0 / Minor 1）；医疗转介 fail-closed 对抗矩阵 12/12，明确/健康条件触发的就医动作通过，否定/询问/不确定表达被拒绝，断言-only 路径不可绕过。唯一非阻断 Minor：配置可读取 `llm_judge_model`，但 `_call_judge` 尚未把该可选 override 传给 provider；当前数据集不使用该字段，登记为发布后 backlog，不在 GO 后扩大本轮变更。
- 2026-08-08 Build 244 精确二进制隐私复评：IPA `18cd5357aaa5c57a02bfb23db741ae0889f84108e2fc5c676501f433f2c9fc10` 的主 App PrivacyInfo 仅 9 类，缺 AudioData、DeviceID、ProductInteraction，UserID 还缺 Analytics purpose；这些分别绑定实际云端 ASR、APNs device token 和认证客户端事件数据流。独立 G4 判定 Important/BLOCK、`Build 244: NO-GO`。源码整改补齐 12 类及 UserID Analytics，并将 iOS preflight 改为固定 production inventory、草稿↔manifest 精确集合、linked/tracking/purposes 逐项一致及 unknown/duplicate/schema fail-closed；变异测试覆盖双方同删、双方同翻 tracking、目的增删/重复等假绿路径。源码复评 `GO`，但必须用新原生 Build 再验包内 manifest，不能 OTA 修复或沿用 244。
- 2026-08-08 Build 245 精确二进制复验：EAS 元数据绑定 source `140bd788a722cbcf25c203552444b72a9f010bc5`；IPA SHA-256 `bb355a4a4c9dea5de30d60468c5844e551f18c693a82636cbbb414b1dae85180`，主 App PrivacyInfo SHA-256 `2f3b255686e1a62f95eb7d85a889a12c77eb4ea0dd0efecfc4255d4c7e1251ae`。同一语义 helper 对包内 12 类数据、linked/tracking/purposes 与 checked-in App Privacy 草稿逐项校验返回零失败；版本 1.3.3（245）、bundle ID、iPhone-only arm64、production APNs、HealthKit、Universal Link、beta reports、`get-task-allow=false` 和严格验签全部 PASS。Build 244 的二进制隐私阻断已由新原生包消除。
- **当前裁决**：pending（T7.5 第四轮 `BLOCK` 已整改，并追加照片餐食保存失败安全提示修复，等待第五位 reviewer）；历史 `Build 256 G4: GO` 仍只覆盖当时的精确二进制与登录修复，不能覆盖本次健康写入新 diff。新的独立 reviewer 给出 GO 前，不得部署、OTA、删除生产记录或提交 App Review。Build 244 继续 `NO-GO` 且不得绑定 App Review。

## S6 · 部署

- 路由：EAS production Store Build → TestFlight → App Store manual release。
- production OTA：Build 241 启动后已冻结；本轮 Mobile 回执标签变更不得 OTA，必须进入 Build 242+；App Review 和 G6 完成前不得发布新的 production OTA。
- 2026-08-08 主干 CI run `31278043177`（commit `f65c4055d1efb8f4a4b8ec0126763377e215e1f4`）`completed/success`：44/44 jobs success、0 failure；包含真实模型 change gate、Agent/回执安全回归、Mobile、Frontend、Mac、PostgreSQL、类型漂移和发布不变量。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 仓库变量在 CI 终态后已删除并复证不存在。
- 2026-08-08 隐私二进制整改主干 CI run `31282612080`（commit `140bd788a722cbcf25c203552444b72a9f010bc5`）`completed/success`：44/44 jobs success、0 failure；覆盖 Mobile 全量、iOS submission preflight 语义变异、Backend、Frontend、Mac、PostgreSQL、类型漂移和发布不变量。
- 2026-08-09 Build 253 上传证据主干 CI run `31294359807`（commit `6a54bd05482cedc58153372dbc43aa6da2e32574`）`completed/success`：44/44 jobs success、0 failure；Build 253 的 UI 源码 commit `a26477b3000b9b44c53e8c20fc0f19904b3a7f03` 对应前一主干 CI run `31290995824` 同为 44/44 success。
- 2026-08-08 后端部署：从新建的干净 `main` 副本用正式 `deploy.sh --backend --yes` 发布精确 commit `f65c4055d`；新数据库备份、237 表恢复演练、站外加密归档哈希/HMAC、回滚 schema、远端 revision、runtime-only KB guard/staged、Skills 22/22 和多轮健康度 60/60 全部 PASS，feature flag 保持 false。备份轮换按保留 7 份策略淘汰 1 份最旧备份。
- 审核账号凭据轮换后，旧发布秘密源首次登录返回 401，未执行任何健康写入。新随机密码已无回显地保存到 macOS 钥匙串并同步回权限 0600 的发布秘密源；正式 env-only 部署完成服务器对齐。随后 revision/发布锁约束的 `deploy.sh --reset-app-store-review` PASS，固定简报恢复为精确两条；完整生产 live gate PASS。原删除记录 `#718` 不通过数据库手段复活，改用认证应用 API 创建合成恢复记录 `#727`，只读复验 350ml 恰好 1 条、300ml 为 0；未输出或提交账号、密码、令牌和健康原文。
- T5 法务材料部署：commit `ac1695445` 通过根 `deploy.sh --all` 发布；数据库备份、恢复演练、站外加密归档、schema probe、runtime-only KB、skills manifest、精确 revision 均通过，连续后端健康分 60/60；前端 Next.js production build/TypeScript/73 个静态页面生成 PASS。线上 `/privacy` 和 `/api/v1/health` 已独立验证。
- EAS production Store Build：ID `5112d291-68d3-4a81-ab1b-c4048cec133a`，版本 1.3.3（241），runtime 1.3.3，source commit `c109e934c4b2c633979bd5c0a7cd97a8f62e570d`，fingerprint `071e439a159a94ec1c529e94a1b7e1c2f6b19476`；2026-08-07 `FINISHED`。
- ASC/TestFlight 上传：EAS Submit ID `72225022-0bf2-4aef-bc6e-35b47aac3ed8`，`FINISHED`；App Store Connect processing `VALID`，内部状态 `IN_BETA_TESTING`，外部状态 `READY_FOR_BETA_SUBMISSION`。这里只完成二进制上传与 TestFlight 处理，尚未创建或提交 App Review。
- Build 244：EAS Build `592cee0c-9e02-4c02-95be-3e7d7f6dc406`、Submit `4b8aee9e-a5b4-4e4e-babb-3ed47422c10a` 均完成；版本 1.3.3（244）、runtime 1.3.3、source `e8958ee090224aa310f159bec5512239f6d1172c`、fingerprint `e533a1945819e3610a14e187e4f1ed6b4c80286e`。二进制已上传 ASC 但因包内隐私 manifest NO-GO 被取代，不得绑定 App Review。
- Build 245：EAS Build `6f0d3a1b-4868-4f43-86f5-7c50d84e15ae` `FINISHED`，Submit `ef2f1e7d-5d8f-432b-a97d-7b3bd5c0fb5f` 已成功上传 ASC；版本 1.3.3（245）、runtime 1.3.3、source `140bd788a722cbcf25c203552444b72a9f010bc5`、fingerprint `03d3930fa5c8fb16f03bfcbcc465dfadaad460bb`。ASC Build `a77058f7-768c-45b9-958a-c5e00dadd07f` 已 `VALID`、未过期，内部状态 `IN_BETA_TESTING`、外部状态 `READY_FOR_BETA_SUBMISSION`；尚未绑定 App Review。
- Build 253：source `a26477b3000b9b44c53e8c20fc0f19904b3a7f03` 与 `origin/main` 精确一致；Xcode 26.5 / iOS 26.5 SDK 本地正式归档与导出成功。IPA SHA-256 `55c1072d1d3437aef703a7e772b698baef3af472b73f457a9defcce6b74bca5f`，主 App PrivacyInfo SHA-256 `2f3b255686e1a62f95eb7d85a889a12c77eb4ea0dd0efecfc4255d4c7e1251ae`；版本 1.3.3（253）、iPhone-only arm64、MinimumOSVersion 16.0、production channel/APNs、HealthKit、Universal Link、beta reports、`get-task-allow=false`、严格验签和 12 类隐私语义 helper 均 PASS。Xcode Organizer 显示 Build 253 `Uploaded to Apple`；上传仅报告 React / ReactNativeDependencies / Hermes 三个预编译框架缺 dSYM 的非阻断警告。ASC processing / TestFlight 尚未从已登录会话复证；该本地归档没有 EAS Build ID，严格 final-submit 的候选绑定契约在改为等价本地归档证据前保持 BLOCK，禁止伪造 EAS ID。
- Build 254：source commit `359d6b819caf8e04a9b8531b9f2441f36fecc1bb`，随后只增加发布工具兼容提交 `db1faad7dea1fcea479be88d008b9fd528a5c7e2`；Xcode 26.5 / iOS 26.5 SDK 本地正式归档，IPA SHA-256 `a21f263fb157545a7943b1ab84cf6f5b0f4666161b73b56c1f42ba2c78d659c0`，版本 1.3.3（254），严格验签与 production 能力闸 PASS。ASC Build `47b7c6b5-526d-491b-80c2-e88b1b5ad53c` 已完成 processing 并进入内部 TestFlight；审核账号物理 iPhone 安全自动子集 6/6 PASS。该包没有 EAS Build ID，严格 final-submit 的候选绑定契约仍 BLOCK；EAS 255 作为最终候选重试中。
- EAS 255 上传前归档整改：两次尚未创建远端 Build 的上传分别在 12.8/50.8MB 与 50.6/50.8MB 处 `EPIPE`。`eas build:inspect` 证明 EAS 以 monorepo 根目录归档，原 `mobile/.easignore` 未能排除仓库级内容；新增根 `.easignore`（完整继承 `.gitignore`）后，检查归档由 144MB 降至 19MB，精确排除 `.git`、105MB `htmlcov`、后端/网页/无关 App、原生生成目录和 20MB Rokid APK，同时保留 `apps/watch`。契约测试与精确归档检查 PASS；远端 Build 号须先回置 254，再由 `autoIncrement` 创建唯一 Build 255。
- Build 255：EAS Build `c7e11863-40c5-4717-a853-04b902aa88fa` 与 Submit `b9cbcd59-1e2e-4282-8657-f6c34d237a8e` 均完成；版本 1.3.3（255）、runtime 1.3.3、source `bb00e9dd0711537de3b9c5d49cb62390f7778ae8`。精确 IPA 签名/能力/12 类隐私语义、ASC processing/TestFlight、物理 iPhone 安全自动子集 6/6 及 ASC 版本绑定均 PASS，且未点击提交审核。随后人工登录失败路径发现账号表单未显示已有错误状态；该发布阻断必须进入新 Store Build，production OTA 继续冻结，Build 255 不得送审。
- Build 256：EAS Build `f43f71df-2d12-4a5e-a0a0-64995bbcc654` 与 Submit `065bde9d-81d4-48dc-bfe0-ea09555dce88` 均 `FINISHED`；版本 1.3.3（256）、runtime 1.3.3、source `75f61f694c4711a7b349eb63fb7af5e48d9f9012`、fingerprint `000a731cb304b5da1d8eddfe8c707b59c129c565`。ASC Build `c2349268-3b14-4ad5-aaad-3698e1ebb71e` processing 完成并进入内部 TestFlight；版本页已移除 Build 255、绑定并保存 Build 256。审核信息保持“需要登录”，用户名与受控审核账号一致，ASC 密码与线上验证成功的钥匙串秘密逐字节一致；页面保存按钮为禁用态、“添加以供审核”为可用态，未点击提交。精确 IPA SHA-256 `2064483bd16a107601b8e27d4275a7bf9f829c0d2d9e32025753f0766e72e051`，PrivacyInfo SHA-256 `2f3b255686e1a62f95eb7d85a889a12c77eb4ea0dd0efecfc4255d4c7e1251ae`；严格验签、版本/Build/bundle、iPhone-only arm64、MinimumOSVersion 16.0、production APNs、HealthKit、Universal Link、beta reports、`get-task-allow=false` 与 12 类隐私语义全部 PASS。
- 回滚点：上一 Store Build 240（EAS `a62a4dc5-f542-4cfe-bc87-8eb0d84a7ff4`）；App Review 尚未提交，当前无需执行回滚。

## G5 · 部署健康闸

- IPA toolchain/version/build/commit：PASS。Build 241 精确 IPA SHA-256 `1a7f23ad4586922b8f6d07161bf4a56c404ceaa812064a05468954fdc07d0e12`；display name 小巴，bundle ID `life.executor.health`，版本 1.3.3（241），Xcode 26.2（17C52）/ iOS 26.2 SDK，MinimumOSVersion 16.0，iPhone-only、Mach-O arm64。`codesign --verify --deep --strict` PASS；production APNs、HealthKit、`applinks:health.executor.life`、beta reports entitlements 存在，`get-task-allow=false`。
- TestFlight processing：PASS。Build 241 已 `VALID` 并进入 `IN_BETA_TESTING`，未过期；EAS Build/Submit 均 `FINISHED`，版本、Build、runtime、source commit 与 fingerprint 一致。
- Build 245 TestFlight processing：PASS。ASC API 只读复验 Build 245 为 `VALID`、`IN_BETA_TESTING`、未过期，外部状态 `READY_FOR_BETA_SUBMISSION`；EAS source/build/runtime 与精确 IPA 证据一致。
- backend health：commit `f65c4055d` 已经正式部署；数据库备份、237 表恢复演练、站外加密归档、回滚 schema、精确 revision、runtime-only KB、Skills 22/22 与多轮健康度 60/60 PASS。审核密码轮换、秘密源对齐、生产重置、固定简报 live gate 及 `#727` 350ml 正常 API 恢复均 PASS；后端子闸完成。
- 照片发送 provider 流总时限 Backend 部署：PASS。候选 `f229e46c2b85ffdef8ef6393e4e13da144887977` 的主干 CI `31350335613` 44/44 success；一次性 live-change 确认变量在 CI 终态后已删除并复证不存在。`./deploy.sh -b -y` exit 0：生产备份约 42MB（0600）、237 表恢复演练、站外 age 加密归档哈希/HMAC、旧版本 `db1faad7d` 回滚 schema、候选 202 表 schema、精确 revision、runtime-only KB guard/staged、Skills 22/22 和多轮健康度 60/60 均 PASS，运行时 feature flag 保持 false。独立部署后复查确认公开 health 的 API/PostgreSQL/Redis/Celery 全 healthy，Backend/Worker/Beat 均 active，远端工作树干净且 revision 精确匹配。
- physical iPhone：设备已恢复连接并确认安装小巴 1.3.3（241）。自动子集第二轮 7 项中 6 PASS、1 FAIL；失败根因对应的生产固定会话新鲜度现已由重置及 live gate 修复，但必须在密码轮换和人工预登录后以不接收凭据的安全版自动子集复验。语音、相机与照片持久化、分享、健康写入/纠正/删除等人工项仍未完成，不能以历史 Build 240、模拟器或旧的部分通过替代。
- evidence security：第二轮原始 Xcode 结果包记录了自动输入的审核凭据并含合成健康内容，不得作为发布证据或上传；仅保留本 Dossier 的非敏感计数与根因。审核密码已轮换并进入钥匙串/受控秘密源，代码整改和生产固定会话重置已完成；Build 242+ 上使用新密码人工预登录和安全版自动重验完成前，T8/G5 保持阻断。
- Build 241 supersession：健康纠正原子性后端变更与 action-aware Mobile 回执均晚于 Build 241；该包不再是可提交候选。后续 IPA、TestFlight、真机与 ASC 证据必须全部绑定 Build 242+ 的同一 source commit，不得沿用 Build 241 的通过项代替。
- Build 244 supersession：精确 IPA 的版本、签名、Xcode 26.2 / iOS 26.2、iPhone-only、production APNs、HealthKit、Universal Link 与 `get-task-allow=false` 均 PASS，但主 App PrivacyInfo 与已发布 App Privacy 不一致，helper 精确报出 3 个缺失类型和 UserID purpose 差异。该原生隐私 manifest 无法 OTA 修正；新 Build 的 IPA 必须重新下载、哈希、验签并用同一语义 helper 返回零失败。
- Build 245 exact IPA：PASS。EAS source SHA 与主干精确提交一致；IPA/PrivacyInfo 哈希已记录，版本 1.3.3（245）、bundle ID `life.executor.health`、iPhone-only Mach-O arm64、MinimumOSVersion 16.0、严格验签、production APNs、HealthKit、Universal Link、beta reports 和 `get-task-allow=false` 全部通过。包内 12 类隐私清单与 App Privacy 草稿做精确集合和逐项语义校验返回零失败，Build 244 的阻断项已消除。
- Build 245 supersession：紧凑聊天头部变更晚于 Build 245，该包不再是当前可提交候选；不得复用它的物理 iPhone、截图或 ASC 证据代替 Build 253。
- Build 253 exact IPA：二进制子闸 PASS；精确 source、版本、包能力、严格验签和隐私语义证据见 S6。Apple processing / TestFlight 和等价本地归档候选绑定仍待闭环，因此尚未满足完整 G5。
- Build 254 exact IPA / TestFlight / physical iPhone：PASS。ASC processing、embedded production runtime、6/6 安全自动验收均已闭环；首次错误/跳过由设备登录错账号造成，切换到受控审核账号后同一包复验全绿。该事实证明功能候选可用，但本地归档缺少严格 final-submit 要求的 EAS Build UUID / source 绑定，因此仍不允许提交审核。
- 物理 iPhone UI 预验：开发签名的同源码 Build 253 已安装并启动；真机截图确认 24pt 头像、21/26 标题和 13pt 箭头形成紧凑品牌组，44pt 触控目标由源码/自动测试保持。安全自动子集 5/6：双冷启动登录态、草稿前后台保留、入口、Today、隐私与账号删除通过；固定审核简报用例失败，因为实际可访问层级中不存在预期的“今天优先完成两件事”消息。原始结果包含合成健康内容与测试草稿，只保留本地、不上传；最终须在受控审核账号重置后对 TestFlight 精确 Build 253 重跑，开发签名预验不替代 T8。
- 本地原生预验：iOS 26.5 Release 模拟器构建、安装和启动 PASS；该产物为 development 变体且禁用本地 Sentry 符号上传，只证明当前原生工程可编译/启动，不替代 production Store Build、TestFlight、精确 commit/Build 绑定或 T8 物理真机证据。
- Build 256 exact IPA / TestFlight / physical iPhone 自动子闸：PASS。真机确认安装 1.3.3（256）；审核账号真实登录在生产日志返回 200，随后首页、会话和时间线接口均为 200。首次安全自动子集 5/6 的唯一失败是人工使用后普通会话成为默认最新；受部署 revision/发布锁保护的审核演示数据重置恢复精确两条固定会话后，同一包复验 6/6 PASS、0 failure、0 skip，覆盖双冷启动登录态、固定会话、未发送草稿前后台保留、入口、Today 打开/关闭、隐私政策与账号删除入口。结果包只保留本机，不上传。
- Build 256 人工相机 / 照片持久化子闸：PARTIAL PASS。系统相机、照片草稿和冷启动恢复已通过；发送后的助手终态曾因 Backend provider 流总时限缺口失败。修复现已完成生产部署且健康闸全绿，但照片终态、后续无 409 循环及再次冷启动回读尚未在同一真机 Build 复验，因此该子闸仍 BLOCK。
- **裁决**：pending（既有 BLOCK 范围已缩小）—— Build 256 的 EAS/IPA/ASC/TestFlight、真实登录、安全自动子闸、照片本地持久化及 Backend 修复部署均通过；T7.5 尚未部署，且仍须完成照片终态复验，并对同一包完成人工语音、分享、健康写入/纠正/删除及最终截图。完成前继续冻结 production OTA 和 App Review 提交。

## S7 · 上线验证

- App Store 公开安装、版本核对、登录/文字 Agent、隐私/删除、鼻炎卡、服务健康：待执行。

## G6 · 验证闸（人在环）

- 真机/发布用户确认：待 Apple 批准和手动发布后请求。
- **裁决**：pending。

## S8 · 沉淀

- 新坑：年龄分级和审核期间 OTA 冻结已进入 final-submit 机器闸；精确 IPA 工具链和 app/build 对齐也已 fail-closed。
- 本地 iOS 构建若只配置 macOS 系统代理，CocoaPods/Expo 子进程仍可能因 shell 无代理变量而误报依赖不可解析；先验证代理出口并显式传递 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`。无 Sentry 发布凭据的本地模拟器 QA 可用 `SENTRY_DISABLE_AUTO_UPLOAD=true`，但正式 Store 归档不得沿用该临时设置。
- EAS archive 上传可能在大包和代理链路下持续数十分钟；必须用当前 EAS CLI、保留精确 source commit，并在确认远端 Build 已创建前安全处理中断/重试，避免误把本地上传中断记为可用候选。
- 真机验收前必须确认设备登录的是受控审核账号；“已登录”只证明有会话，不能证明账号身份。应先用 owner-scoped、无健康原文的身份/资源归属探针确认，再运行固定简报与 Today 验收，避免把账号错位误判为客户端或 seeder 缺陷。
- 新坑：发布规划文档提交也会触发实时依赖 advisory；必须把最新主干 CI 颜色作为预构建 Gate，锁文件安全修复不得延后到构建后。
- 文档同步：若架构计数未变化，无 system-map 生成物变更；最终以 doc-drift 为准。
- 状态：待 shipped。
