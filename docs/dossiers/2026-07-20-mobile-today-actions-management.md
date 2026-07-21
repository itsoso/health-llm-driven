# Dossier: Mobile 今日行动管理闭环

| 字段 | 值 |
|---|---|
| slug | `mobile-today-actions-management` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S8 上线验证（反馈环 5） |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | Mobile Jest / iOS Simulator / production OTA |

## S0 · 用户需求（逐字）

> 点击管理活动会跳转到第二张图片，但是无法跳回来，另外列表也有问题，无法管理，重新梳理这个链路，优化。

- 用户从小巴的今日行动卡进入管理页，需要处理今天要做的事并可靠返回对话。
- 当前只能进入全量行动/告警列表，无法形成完成闭环。

## S1 · Discovery

- 后端 `backend/app/services/inline_cards.py` 将今日管理入口写成 `/alerts`。
- `/alerts` 位于隐藏 Tab，`headerShown=false`，页面无返回入口。
- `mobile/app/(tabs)/alerts.tsx` 查询全部 active action cards 和 safety alerts，不是今日议程。
- `mobile/app/agenda.tsx` 已有 `/agenda/today` 和 `/agenda/complete` 能力，但页面信息重复、缺少返回和完整管理操作。

## G1 · RequirementAdmission

- classification: `bugfix + product_change`
- first_class_objects: `LeverageAction`, `AgendaItem`, `EvidenceEvent`
- core_loop_step: `recommend -> act -> measure`
- target_surface: `Mobile`
- source_of_truth: `/agenda/today`, `/agenda/complete`
- safety_level: `medical_boundary`
- autonomy_tier: `manual_confirm`
- smallest_end_to_end_slice: 小巴卡片进入今日议程，完成/跳过写回，返回小巴并刷新。
- stale_surface_to_remove: 今日管理不再进入 `/alerts`；安全告警页继续独立保留。
- **裁决：PASS**。用户已确认方案 A。

## S2/S3 · 设计与规划

- 设计：`docs/plans/2026-07-20-mobile-today-actions-management-design.md`
- 实施：`docs/plans/2026-07-20-mobile-today-actions-management.md`
- 非目标：不新增自动执行、不修改药物剂量、不重做语音输入、不删除安全告警页。
- 未决问题：无。

## G2 · 可行性与安全压测

- 复用已有接口，无新 schema、无新原生能力，Mobile 可 OTA。
- 所有健康写入保持用户确认；失败不显示成功。
- **裁决：PASS**。用户选择方案 A。

## S4 · 研发任务

- [x] T1 动态卡片路由改为 `/agenda`
- [x] T2 今日事项分组与文案纯函数
- [x] T3 完成/跳过写回与缓存刷新
- [x] T4 今日行动管理页面与返回闭环
- [x] T5 模拟器验证、文档、提交、OTA

## G3 · 测试闸

- PASS: 后端动态卡片与今日视图回归 `44 passed`。
- PASS: Mobile 今日行动、写回 Hook、Agenda service 和动态卡片注册回归 `81 passed`。
- PASS: `/agenda` 页面补充双行提交锁定验证，页面专项 `6 passed`。
- PASS: `npx tsc --noEmit`。
- PASS: 本批文件 ESLint 无错误。
- PASS: `npm run design:check`，设计 token 未新增漂移。
- PASS: `python3 scripts/check_doc_drift.py`，代码派生系统地图一致。
- PASS: 从提交 `63db2494f` 重建 iPhone 17 Pro 模拟器原生壳，Xcode build 成功（0 errors）。
- PASS: 模拟器真实深链打开 `/agenda`；空态、紧凑标题栏和无底部 Tab 的页面结构正确。
- PASS: 空态“返回小巴”和顶部返回键均实际点击验证，可回到原小巴对话；冷启动深链也有确定回退路径。
- 主干首次运行的旧 `v-z + services` 超大分片连续两次超过 600 秒进程时限；没有断言失败，但 Gate 仍按失败处理。已拆为 `voice-watch`、`wearable-reports`、`workday-workout`、`write-z`、`services` 五个隔离进程，并增加工作流合同测试。
- PASS: 新分片本地按 CI 参数完整覆盖原 360 项：`159 + 63 + 61 + 68 + 9 passed`；工作流合同 `7 passed`。
- 后续主干运行又暴露旧 `agent-a-h` 单进程包含数百项测试、偶发耗尽两次 600 秒的问题；已按 agent core / executor 文件族拆成五个隔离进程。
- PASS: agent 新分片本地按 CI 参数完整覆盖 `577` 项：`30 + 21 + 152 + 322 + 52 passed`；工作流合同扩展后 `8 passed`。
- 同轮还发现旧 `a-b-rest` 通过扫描整个 tests 目录构建超大进程；已拆为 `a-early`、`a-late`、`b`，并保持 agent 与 App Store demo 独立。
- PASS: a/b 新分片本地按 CI 参数完整覆盖 `701` 项：`265 + 252 + 184 passed`。
- 后续主干运行确认旧 `c-d` 与 `n-o` 仍会因测试增长触发 600 秒重试；已按实际慢组拆为 `c`、`d`、`n`、`o`，避免无关文件族共享进程状态和时限。
- PASS: 四个单字母分片按 CI 参数本地完整通过：`572 passed`、`341 passed + 1 skipped`、`150 passed`、`338 passed`；工作流合同扩展后 `9 passed`。
- 真实账号当日无行动，因此有数据的分组、行级锁定和操作菜单由页面组件测试覆盖，不为视觉验收伪造健康行动。
- **裁决：PASS。**

## G4 · 安全闸

- 今日列表只消费当前用户鉴权后的 `/agenda/today`，不新增跨用户查询。
- 完成和跳过继续复用 `/agenda/complete` 的显式人工确认；跳过必须选择原因。
- “稍后”只改变当前会话排序，并明确提示未写成完成，不伪造服务端回执。
- 写入失败保持原状态并显示错误，不做乐观成功声明。
- 未修改药物剂量、诊断逻辑、安全阈值或推送隐私出口。
- **裁决：GO。**

## S6 · 提交与集成

- 设计与计划：`42e67ae9a`。
- 实现：`63db2494f`。
- 反馈环 3：`5281eb82f`、`a542f94b1`、`e135100d6`、`72d4fa3ae`。
- 反馈环 4：`242a1cbf4`；合并最新主干后提交为 `416aaa946`。
- 同步并行后端 OpenAPI 到 Mobile/Web 生成类型：`1d97bb4c3`。
- 反馈环 5 持久化稍后/恢复：`2e3a3aa0c`；合并最新主干后为 `9362d1713`。
- CI 暴露并修复 Mobile 测试写死开发机时区的问题：`0fa40389b`。
- 最新主干 CI：运行 `29798138723`，`42/42` 作业成功。
- `main` 已推送到 `origin/main`；未纳入并行会话的无关工作树改动。

## G5 · 部署健康闸

- 后端从干净的 `origin/main` worktree 部署，生产提交为 `63db2494`。
- 部署健康度 `60/60 PASS`，skills manifest `22 = 22`。
- 生产 `/api/v1/agenda/today` 未鉴权返回 `401`，证明路由已加载；`/health` 返回 `200`。
- 后端近期日志未发现新的 error / critical / traceback / RLS superuser 告警。
- **裁决：PASS。**

## S7 · Mobile 发布

- production OTA runtime：`1.3.2`。
- EAS update group：`e04c34df-c835-496d-9ce3-76849f421217`。
- iOS update：`019f7dcf-af87-7780-ad69-c891ce6a7398`。
- 发布提交：`63db2494f1e8436e42517dc608756769da266b12`。
- 原生兼容性：`1.3.2` 生产壳已包含 `expo-video`；本切片没有新增原生模块，OTA runtime 匹配。

## G6 · 上线验证

- 生产后端、鉴权路由和 OTA 发布标识均已验证。
- 用户端需杀掉 App 后重新打开并应用更新，再从小巴行动卡点击“管理今日行动”完成最终真机验收。
- **裁决：PASS（技术上线）；真机用户体验纳入下一反馈环。**

## 反馈环 2 · 列表降噪与可逆操作

### 用户反馈

> 继续优化

### Correction Block

- 触发：方案 A 已解决错误跳转和无法返回，但普通建议与可直接完成的行动仍混在“现在做”；空分组占用屏幕；临时后移不可撤销。
- 旧基线：`现在做 / 稍后 / 已处理` 三组，所有未到未来时间窗的非终态事项都进入“现在做”。
- 新基线：`现在做 / 需要确认 / 稍后 / 已处理`。只有已有安全完成合同的事项进入“现在做”；建议、洞察等不可直接完成项进入“需要确认”。
- 安全边界：不新增自动完成、不持久化虚假的稍后提醒、不修改药物或补剂计划；“调整计划”仍由小巴在对话中确认。
- 回退阶段：S3/S5；沿用原 Feature Spec、路由和写回接口，不新增一等对象或跨端契约。

### 验收

- [x] 分组和行按钮共用同一个可执行判定，避免展示与权限漂移。
- [x] 空分组不渲染，降低长列表噪声。
- [x] “稍后处理”改为更诚实的“移到稍后”，且提供当前会话内撤销。
- [x] 专项 Jest `16 passed`，TypeScript、ESLint 和设计 token 闸通过。
- [x] 模拟器完成新开发包安装并通过 `exp+health-pilot://agenda` 直达复核；真实账号数据呈现为 `现在做 2 / 需要确认 7`。
- [x] 修复模拟器复核发现的重复 source key：按完成写回身份去重，待处理总数由错误的 11 条恢复为 9 条，页面无重复键警告。
- [x] 最新 `origin/main`（`85606de94`）CI `41/41` 通过；production OTA 发布到 runtime `1.3.2`。
- [x] EAS update group `718748de-169b-4ab6-9c47-54dff39f75b0`，iOS update `019f7eb8-bf7a-7b12-aa57-f276246859db`。
- [ ] 用户真机杀掉 App 后重开并应用更新，完成最终触控验收。

### Gate 裁决

- G3 测试：PASS（专项 Jest `16 passed`、TypeScript、ESLint、design token、doc drift、`git diff --check`；最新主干 CI `41/41`）。
- G4 评审：PASS（不新增医疗写回路径；不可直接执行的建议仅允许“问小巴”）。
- G5 部署：PASS（production / iOS / runtime `1.3.2`，EAS 标识已回读验证）。
- G6 上线验证：PASS（技术上线）；真机触控反馈继续进入下一反馈环。

## 反馈环 5 · 可信的稍后与跨会话恢复

### 用户反馈

> 继续优化

### Correction Block

- 触发：反馈环 4 虽然让“移到稍后”可逆，但状态只存在页面内存；刷新、重启或换端后行动会立刻回来，与“稍后”语义不一致。
- 根因：Mobile 没有消费后端既有的 `HealthProtocolEvent.status=snoozed` 能力，也没有 Agenda surface 的持久化稍后/恢复合同。
- 新基线：可执行 `health_protocol` 通过 Agenda API 持久化 30 分钟稍后，普通 Agenda 投影返回 `snoozed_until`；用户可显式恢复。非协议来源和只读建议不展示无法兑现的稍后动作。
- 安全边界：稍后不等于完成或跳过，不写 MedicationLog/SupplementRecord，不修改协议剂量、频次和治疗计划；跨用户或终态事项必须失败。
- 回退阶段：S3/S5；复用现有 HealthProtocolEvent，不新增表，不扩大自动执行等级。

### 验收

- [x] 后端稍后/恢复合同覆盖成功、重试幂等、用户隔离、来源限制和终态保护；条件更新竞争测试证明不会覆盖 concurrent complete/skip。
- [x] Agenda 投影透传服务端稍后状态和到期时间，今日投影、完成、药物日志和 runtime/range 使用同一用户日期。
- [x] Mobile 不再用页面内存伪装持久稍后，写入失败不移动事项；当前来源写入中锁定整行操作。
- [x] 只有具备真实稍后合同的事项展示该操作，恢复后回到正确分组。
- [x] 专项测试、类型、设计、文档漂移和独立评审通过；合并后后端相关回归 `77 passed`。
- [x] Mobile 完整测试在 UTC 环境 `282 suites / 2014 tests passed`；主干 CI `42/42`。
- [x] production OTA 发布并回读验证。
- [ ] 用户真机完成跨重启稍后/恢复验收。

### Gate 裁决

- G3 测试：PASS（开发阶段后端相关回归 `147 passed`；合并后关键回归 `77 passed`；Mobile 专项 `38 passed`、完整 UTC 环境 `2014 passed`；TypeScript、ESLint、design token、ruff/py_compile、doc drift、dossier consistency、diff check 通过；主干 CI `42/42`）。
- G4 评审：三轮独立评审累计发现并修复终态并发覆盖、用户日期漂移、重复稍后延长、过期稍后刷新、用户本地提醒时钟、失败推送占位和多行写入锁定；最终复审结论 `GO`。
- G5 部署：PASS（从干净 `origin/main` worktree 部署提交 `0fa40389b`；数据库备份和 force-RLS 完整性校验通过；健康度 `60/60`，skills `22 = 22`；生产健康接口 `200`，Agenda 写接口未登录 `401`）。
- G6 上线验证：PASS（技术上线）。production OTA runtime `1.3.2`，update group `15c81741-e39d-4fb6-ab13-e1023ebbb9a3`，iOS update `019f82c0-ec81-7a5d-a2ef-3958fd6e7412`；真机跨重启触控验收保留为下一反馈。

## 反馈环 3 · 写回能力对齐与渐进披露

### 用户反馈

> 继续优化

### Correction Block

- 触发：真实账号存在 7 条“需要确认”事项，首屏全部铺开仍然形成长队列；同时旧 Mobile 判定允许 `daily_plan_action` 直接完成，并给所有复核事项提供“跳过”，但后端 `/agenda/complete` 只接受 `health_protocol`、`medication`、`supplement`，点击后必然失败。
- 根因：客户端可执行判定比服务端写回合同更宽，操作菜单又只按固定下标处理，没有根据事项能力生成。
- 新基线：只有服务端明确支持且处于 `pending` 的三类来源展示“完成/跳过”；其余复核事项只提供“稍后再看 / 调整计划 / 问小巴”。“需要确认”默认展示前三项，用户可显式展开其余事项。
- 安全边界：没有扩大后端写入类型；没有用本地成功态掩盖服务端失败；“稍后再看”仍只改变当前会话排序，避免制造跨设备已排期的假象。
- 回退阶段：S3/S5；沿用原页面与接口，不新增医疗自动化行为。

### 验收

- [x] 先补失败测试，确认 `daily_plan_action` 误判、长复核队列全展开和复核菜单错误三个回归点。
- [x] 可执行判定收紧到后端支持的 `health_protocol / medication / supplement`。
- [x] 菜单改为能力驱动，复核事项不再暴露无效“跳过”写入。
- [x] 7 条复核事项首屏只展示 3 条，并显示“查看其余 4 项”；支持展开和收起。
- [x] 专项 Jest `19 passed`，TypeScript 与变更文件 ESLint 通过。
- [x] iPhone 17 Pro 模拟器使用开发 bundle 和真实账号数据验证：`现在做 3 / 需要确认 7`，复核区默认三条，布局无重叠。
- [x] 独立代码审查无高/中风险；补齐 VoiceOver 展开状态、Android 安全菜单、收起操作和 supplement 来源回归测试。
- [x] 首轮最新主干 CI 暴露 Watch 提醒测试在北京时间 23:50 后必然跨日的假红；固定测试时钟后，目标用例 `2 passed`、完整 Watch 摘要 `18 passed`，生产提醒逻辑未改。
- [x] 同轮发现睡眠跨夜测试的固定日期会随时间被日期守门正确纠偏；注入固定参考时间后，完整 tool validator `84 passed`，生产日期校验逻辑未改。
- [x] design token、doc drift、diff check 通过；最新主干 CI `41/41`，聚合结论为 `success`。
- [x] production OTA 已从干净的 `72d4fa3ae` 发布并回读：runtime `1.3.2`，update group `05175fc9-8a39-4fb2-ae39-91ba0681228f`，iOS update `019f8054-7665-7a96-bcda-568cafd3822f`。
- [ ] 用户真机应用更新后完成最终触控验收。

### Gate 裁决

- G3 测试：PASS（专项 Jest `19 passed`、TypeScript、ESLint、design token、doc drift、diff check；Watch 摘要 `18 passed`、tool validator `84 passed`；最新主干 CI `41/41`）。
- G4 评审：PASS（客户端权限收紧，不新增医疗写入路径）。
- G5 部署：PASS（production / iOS / runtime `1.3.2`，EAS 标识已回读验证）。
- G6 上线验证：PASS（技术上线）；真机触控反馈继续进入下一反馈环。

## 反馈环 4 · 主操作唯一与稍后可逆

### 用户反馈

> 继续优化

### Correction Block

- 触发：待确认事项同时展示“问小巴”主按钮和菜单中的同名操作；事项移入“稍后”后仍显示“移到稍后”，缺少直接恢复；顶部把未来事项和已后移事项一并计入“待处理”，不能回答用户此刻该处理多少项。
- 根因：页面菜单只按事项可写能力生成，没有结合当前分组和本地后移状态；标题摘要使用所有非终态事项的总和。
- 新基线：每行只保留一个显性主操作；待确认事项的菜单不重复“问小巴”；本次后移事项提供“移回现在”；顶部只展示“现在 / 待确认”两个即时决策数字。
- 安全边界：恢复只撤销当前会话内的本地后移，不新增服务端写入；完成、跳过和调整计划的安全合同不变。
- 回退阶段：S3/S5；沿用当前页面和 Dossier，不新增一等对象、后端接口或自治行为。

### 验收

- [x] 失败测试覆盖即时摘要、去重菜单、稍后恢复、未来事项菜单和复核事项恢复文案；实现前分别确认预期失败，修复后页面专项 `14 passed`。
- [x] 本次后移事项可一键移回，且菜单不再提供无效的重复后移。
- [x] 三组专项 Jest `23 passed`，TypeScript、变更文件 ESLint、design token、doc drift 和 diff check 通过。
- [x] iPhone 17 Pro 模拟器使用真实账号验证完整可逆动线：`现在 1 → 稍后 1 → 移回现在 → 现在 1`；标题摘要同步变化，布局无重叠。
- [x] 独立评审发现复核事项实际回到“需要确认”却统一提示“移回现在”的 P2 误导；已按原分组分别显示“移回现在 / 移回待确认”并补回归测试，复审结论 GO，无高/中风险。
- [x] 最新主干 `1d97bb4c3` CI `41/41` 通过，运行 `29793087152` 聚合结论为 `success`；并行后端 schema 引起的 Mobile/Web 类型漂移已同步，`type-drift` 闸通过。
- [x] production OTA 已从干净的 `origin/main` 发布并回读：runtime `1.3.2`，update group `7bd526a7-dffa-4172-8d90-990257701371`，iOS update `019f8258-d69d-7a21-a816-5a05e7d4baf9`。
- [ ] 用户真机应用更新后完成最终触控验收。

### Gate 裁决

- G3 测试：PASS（专项 Jest `23 passed`、TypeScript、ESLint、design token、doc drift、diff check；最新主干 CI `41/41`）。
- G4 评审：PASS（本地后移/恢复不写服务端；完成/跳过权限未扩大；P2 文案误导修复后独立复审 GO）。
- G5 部署：PASS（production / iOS / runtime `1.3.2`，EAS 标识已回读验证）。
- G6 上线验证：PASS（技术上线）；真机触控反馈继续进入下一反馈环。

## 反馈环 6 · 低打扰默认视图

### 用户反馈

> 继续

### Correction Block

- 触发：反馈环 5 已把“稍后/恢复”做成服务端持久状态，但行动管理页仍会把未来或稍后事项直接铺开；用户当前只想知道“现在还有什么需要处理”，长列表会继续造成压力。
- 根因：页面把 `later` 分组当成普通待处理列表渲染，没有区分“当前决策”和“后续安排”；当 `now/review=0` 时也缺少明确的清空状态。
- 新基线：`现在做` 和 `需要确认` 仍默认展开；`稍后` 默认只显示分组标题和数量，用户点开才查看/恢复/管理；如果当前决策为 0，页面先提示“当前没有需要你立刻决策的行动”。
- 安全边界：只改变展示默认状态，不改变 `/agenda/complete`、`/agenda/snooze`、`/agenda/resume` 写入合同；稍后项仍需用户展开后显式恢复或管理。
- 回退阶段：S5；沿用当前页面和 Agenda API，不新增一等对象或后端 schema。

### 验收

- [x] 先补失败测试，确认未来行动直接铺开、稍后区没有展开状态、当前决策为 0 时没有清空提示三个问题。
- [x] `稍后` 默认折叠并提供 VoiceOver 展开/收起状态；展开后仍保留恢复、跳过、调整、问小巴等既有安全菜单。
- [x] 当前没有 `now/review` 时显示清空提示，避免用户误以为仍有一堆立即待办。
- [x] 专项页面测试 `20 passed`；Agenda 页面、hook、service 相关回归 `34 passed`。
- [x] Mobile TypeScript `npx tsc --noEmit` 通过。

### Gate 裁决

- G3 测试：PASS（专项 Jest、相关 Agenda 回归和 TypeScript 通过）。
- G4 评审：PASS（展示层降噪，不扩大医疗写入或自动执行权限）。
- G5/G6：待本轮提交后随下一次 Mobile OTA/发布验证。
