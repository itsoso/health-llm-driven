# Dossier: 小巴补剂批量记录修复

| 字段 | 值 |
|---|---|
| slug | `agent-supplement-batch-repair` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | G5（Backend PASS；Mobile OTA BLOCKED） |
| 状态 | blocked |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mobile OTA + true-path verification |

## Correction Block 2 · 2026-09-07 冒号列表写入恢复

- 状态: S5 本地实现完成；G3 通过；最终固定 commit 的独立 G4 safety/privacy
  review、推送和部署尚未执行。
- 生产证据: 一次明确的三项补剂记录被正确分类为
  `write/supplement/create`，确定性构建器也生成了三次 `health_record`；
  ToolGateway 随后把三次调用全部以 `health_record_target_mismatch` 拦截，
  provider fallback 超时后展示通用“还没记下来”文案。日志只使用稳定 reason code，
  本 Dossier 不保存用户健康原文。
- 根因:
  1. `记录补剂：...` 的冒号被当成新的命令作用域边界，导致写动作与名称列表分离；
  2. 名称解析保留了首项前的通用“补剂”标签；
  3. Gateway 放行后，补剂适配器仍只接受规范词库或引号名称，未把明确的冒号列表
     视为服务端可验证的名称边界。
- 修复: 冒号延续补剂写目标；补剂名称解析剥离首部通用标签；适配器仅从已经通过
  `authorized_health_record_clauses` 的 `记录补剂：...` 片段绑定精确名称。转述、
  第三方所有权、撤销、假设语境和列表外名称继续在 dispatch 前 fail closed。
- 数量边界: 重复或冲突的粒数不写入 dosage。当前补剂事件只记录“已服用”状态，
  不把语音歧义猜成医学剂量。
- G3 证据: failure-first 三层 RED 均复现；相关作用域、Kernel policy、ToolGateway、
  确定性执行、流式终态和补剂适配器回归 `5346 passed / 0 failed`。真实用户语句仅作
  本地临时重放，结果为三项精确名称均 `allow + grounded`、列表外名称拒绝。
- LLM Gate: invariants `12/12`、health-agent core `50/50`、live orchestrator
  `5/5`（avg `0.92`）、trajectory contract `12/12`、trajectory golden `9/9`。
- 发布边界: 本轮不改客户端、schema 或 API 合同；只需 Backend release。未获得提交/
  部署指令前保持本地改动，不把本地验证冒充生产恢复。

## S0 · 用户需求（逐字）

> 优化这个页面 点击完成 无效 出现了英文
>
> 全部已服用
>
> 记录下来，刚才打了一个喷嚏。
>
> 记录下来，吃了一粒甘氨酸镁和一粒褪黑素。
>
> 修复

- 谁用 / 解决什么 / 现在怎么绕过: Mobile 小巴用户自然语言记录补剂；目前多补剂和全量确认无法完成，只能逐项手工记录。
- 锚点用户相关性: 补剂执行记录是 Health OS 的 `WriteIntent -> ExecutionEvent -> HealthTwin` 闭环。

## S1 · Discovery（现状勘察）

- 已有可复用:
  - `AgentExecutor` 的 verified receipt、写计划和回合终态。
  - `health_record(record_type=supplement)` 及其用户隔离的补剂定义/打卡流程。
  - capability policy 的健康目标授权和 server-owned provenance。
  - reminder continuation 的紧邻上下文收紧模式。
- 根因证据:
  - 意图分类正确识别 supplement write；目标解析却把“记录下来”残留的“下来”当作补剂名。
  - 补剂目标解析只返回一个名称；dispatch 投影固定选择第一个名称。
  - “全部已服用”当前轮没有显式目标，也没有服务端所有者范围内的上下文授权集合。
  - 模型零工具调用时，确定性简单记录兜底不覆盖 supplement，最终落入通用缺字段文案。
- 已排除:
  - 喷嚏记录在同一 UI 成功，说明移动端发送、通用健康写入和回执展示链路可用。
  - 顶部“上一轮未完成”是后端真实终态的展示，不是按钮点击事件失效。
- 链接: `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`

## G1 · 准入裁决

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `HealthTwin`
- core_loop_step: 用户确认执行 → 补剂事件 → verified receipt / Twin
- target_surface / safety_level / autonomy_tier: Backend, Mobile consumed / privacy-sensitive health write / unchanged
- spec_required: no — 聚焦现有写入能力的 bugfix，设计文档和 dossier 足够。
- smallest_end_to_end_slice: 两个显式补剂逐项写入 + 紧邻“全部已服用”写入活动补剂 + 无上下文负例。
- stale_surface_to_remove: 明确补剂写入后的通用“补充类型和值”回退。
- **裁决**: PASS —— 恢复既有主循环，不扩产品范围或医疗自治。
- 用户确认: ☑（用户明确要求“修复”）

## S2 · PRD

- 链接: 采用 focused design `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`，不新建重复 PRD。
- 验收:
  - 两个明确补剂名分别持久化且各有回执；
  - “全部已服用”仅在高置信紧邻上下文生效，目标来自当前用户活动定义；
  - 模型漏工具调用时仍能安全完成；
  - 无上下文继续澄清，药物与其他用户数据不受影响；
  - 完成态不再显示通用缺字段提示或内部英文枚举。
- 边界: 无 DB migration、无客户端合同、无药物批量写入、无提示词单点依赖。
- 未决问题: 无；用户已批准确定性修复方向。

## S3 · 规划

- 设计: `docs/plans/2026-08-11-agent-supplement-batch-repair-design.md`
- 实施计划: `docs/plans/2026-08-11-agent-supplement-batch-repair.md`。
- 路由: Backend TDD → policy/executor implementation → Mobile 可点击性修复 → safety review → main push → backend deploy + Mobile OTA → true-path verification。
- 长杆: 在不信任助手文本和模型字段的前提下传递“全部补剂”的 owner-scoped 授权集合。

## G2 · 可行性 + 安全压测

- 评审方式: Codex source trace + exact phrase reproduction。
- 硬阻断:
  - “全部”只能在紧邻明确补剂确认语境生效；
  - 名称只能来自当前用户活动补剂定义；
  - 每项必须走现有 gateway 和 verified receipt；
  - 不得把 supplement 扩成 medication 或直接绕过工具写库；
  - 部分失败不得宣称全部完成。
- 方案取舍: 采用解析器 + 服务端上下文授权 + 确定性兜底；拒绝 prompt-only 和 parser-only。
- **裁决**: PASS —— 可复用现有写入契约，无 schema 或跨端破坏性变更。
- 用户确认: ☑

## S4 · 研发任务分解

- [x] T1 修复多补剂目标解析和逐调用投影，补单元测试。
- [x] T2 增加收紧的全量补剂续接与 owner-scoped 授权集合。
- [x] T3 增加零工具调用时的一次性确定性补剂兜底。
- [x] T4 集成测试、静态/治理检查、独立安全评审。
- [x] T5 关闭首次 main CI 暴露的集成闸、再次 push、backend deploy。
- [ ] T6 EAS 资产处理恢复后重试 Mobile OTA，并由用户完成真机验证。

## S5 · 实现

- 分支: `main`（按项目默认工作流）。
- commits: `7fa4a3851`（设计）、`2331b5419`（计划）、`01cf9e856`（多目标解析）、`cf4cc6d9c`（上下文批量持久化）、`0e50779de`（安全加固）、`2e21330bf`（发布闸修复）、`88fe449d6`（锁定依赖生成客户端类型）；并通过 `3f568666b` 合并当时的 `origin/main`。
- 实现结果:
  - 显式多补剂语句按名称拆成独立、可去重的 `health_record(supplement)` 调用；不把单个剂量错误复制给多个目标。
  - “全部已服用”只在紧邻助手明确询问“是否全部记为已服用”时启用，目标由服务端按 `user_id + is_active` 查询补剂定义。
  - owner-scoped 名称通过 opaque provenance 进入既有 policy、gateway、planned write 和 verified receipt 链路；集合外名称在 dispatch 前阻断。
  - 模型未发工具或只发部分目标时，服务端一次性补齐确定性调用；已有写回执后不盲目重试，部分失败不会宣称全部成功。
  - 安全评审 fast-follow：全量确认必须锚定最后一问；计数目标使用独立实体边界，阻断 D/D3、D-3、铁/铁观音等短名吞长名；相似已登记名称先澄清，不自动创建重复定义。
  - 补剂打卡 INFO 日志仅记录用户 ID 和补剂定义 ID，不再输出完整补剂名称。
  - Mobile 小巴页顶部三个操作保持 18px 视觉图标，但点击目标恢复到 iOS 建议的 44×44，并扩大 hit slop；避免视觉紧凑导致实际难点。
  - 首次主干 CI 揭示的相邻真实入口一并收口：自然语言“登记”识别、容器量词饮水记录、illness canonical read registry；过期测试数据改为满足现行精确授权，不放宽生产 policy。

## G3 · 测试闸

- targeted/integration/static/doc checks:
  - 初始相关全量集成：`2479 passed, 7 warnings`（224.27s，0 failed）。
  - 合并远端主干后关键锚点：`11 passed, 6 warnings`（2.14s，0 failed）。
  - 安全修复后的最终相关集成：`2487 passed, 7 warnings`（105.95s，0 failed）。
  - 首次 main push：CI run `31560724255` 如实失败；失败项包含主干既存的 Mobile 44pt 合同、OpenAPI 类型漂移、中文“登记”、自然饮水量词和若干已被精确写入授权淘汰的测试场景，未进入部署。
  - CI 定向复核：agent f-h `297 passed`；voice/watch `162 passed`；Mobile Jest `295 suites / 2574 tests passed`；Mobile TypeScript 与 design token gate 通过。
  - 最大 Agent i-z 分片第一次复核如实暴露 1 个过期测试目标（`6295 passed / 1 failed / 3 skipped`）；改为显式、可授权药名后第二次全量复核 `6296 passed / 3 skipped / 0 failed`（356.34s）。
  - Frontend production build 通过；ESLint `0 errors`（33 个既存 warnings）；OpenAPI 两端类型由当前 schema 重新生成。
  - 高风险 LLM live gate：invariants `12/12`、health agent core `50/50`、真实 orchestrator model `5/5`（avg score `0.92`）、trajectory contract `12/12`、trajectory goldens `9/9`，exit 0。
  - Ruff：`All checks passed!`。
  - 文档漂移：架构一致；dossier consistency：`105 份 dossier 全自洽`；`git diff --check`：通过。
- main CI: run `31563459784`，44/44 jobs 完成，结论 `success`。
- **裁决**: PASS。

## G4 · 安全闸

- 触发: 健康数据写入、上下文授权、用户数据隔离。
- reviewer / findings: 独立 safety/privacy review；首轮发现并阻断 3 个 P1（混合语境误授权、子串匹配写错对象、部分失败误报完成）和 1 个日志隐私 P2，均已修复。后续对 10 组末问句、重叠名、Unicode/内部标点边界做对抗复核；最终无可达、可复现 P0/P1。
- 复核证据: 对抗矩阵符合预期；审查定向测试 `9 passed`，`git diff --check` 通过；owner scope、短名澄清、精确分流和部分失败终态均保持有效。
- **裁决**: GO。

## S6 · 部署

- 路由: 后端标准 deploy + Mobile production OTA（纯 TS/UI 点击目标修复）。
- Backend: 从干净主干部署精确 SHA `88fe449d6d903135dac2135beb46f2736100afc9`；发布后远端主干增加的 `0d26c23cf` / `d2b187a99` 只有文档，不改变运行包。
- Backend 回滚点: `ab0a07d93eba5eaf43bfa8f2097c498195c7a3ee`，部署前 schema probe 通过。
- Mobile OTA: production/runtime `1.3.3`。Hermes 首次上传、一次自动重试、no-bytecode fallback 和一次独立强制 no-bytecode 重试均被 EAS 资产处理超时拒绝；没有生成 group/update ID，manifest 与生产锚点未改写。
- Mobile 当前已知可用回滚锚点: group `08d4b60a-19c2-4420-8e18-d92011ad8797` / iOS update `019ff3c1-413c-7c6d-851c-975617ecdc09`（commit `a0e9b3199a3c100f682f537464685272e4853ef7`）。

## G5 · 部署健康闸

- Backend: 42MB 数据库备份、Force-RLS 完整性、237 表恢复演练、站外 age 归档哈希/HMAC 真实性全部通过；managed migrations 无新增。
- Backend: 精确 SHA 核验，三轮健康度 `60/60 PASS`，runtime-only KB guard/staged contract 通过，906 文档/向量重建，Skills `22 = 22`，backend socket/service 与 Celery worker/beat 均 active。
- External smoke: `/api/v1/health` 返回 200 healthy；未鉴权 admin system-map 与 voice write 均返回 401。
- Mobile: EAS asset processing 连续超时，未形成可发布 artifact；旧 update 保持可用。
- **裁决**: BLOCK —— Backend 子闸 PASS，但完整 release 的 Mobile OTA 未完成；回到 S6 等待 EAS 恢复后重试，不带红进入 G6。

## S7 · 上线验证

- 锚点路径: “记录下来，吃了一粒甘氨酸镁和一粒褪黑素”与紧邻上下文后的“全部已服用”。
- 工具侧结果: Backend 路由在线且写入口保持鉴权；没有使用真实用户健康数据做自动 smoke，也没有产生待清理记录。
- 真机结果: pending；等待 Mobile OTA 后由用户在真实账号验证。

## G6 · 验证闸（人在环）

- production true path / 真机确认: pending。
- **裁决**: BLOCKED by G5 Mobile OTA；尚未进入。

## S8 · 沉淀

- system map / contracts / release notes: 系统现状与功能/架构图已在同一主干的 System Map 系列提交更新；本切片无新架构计数，只更新 dossier。
- 状态: Backend shipped；Mobile OTA blocked，保留可重试断点与回滚锚点。

## 2026-09-07 · 冒号补剂列表生产修复

- 生产现象: `记录补剂：...` 的列表目标被冒号拆断，gateway 将逐项调用判为 `health_record_target_mismatch`，用户最终收到未写入回退。修复恢复冒号后目标作用域、去除首项通用“补剂”标签，并把列表中的显式名称交给执行层精确 grounding；测试只使用合成名称，不沉淀用户健康原文。
- 首轮提交: `add0203a9e57abe5aacdb23836c0edc8a09d5781`。相关集成 `5346 passed`，真实 provider 编排门槛 5/5、总分 0.92；但提交前独立安全审查对该精确提交裁决 **NO-GO**，因此未 push、未部署。
- 首轮安全发现: 列表内否定/假设片段可能被当作名称；同一补剂出现冲突数量时可能选择首个剂量；一个子句的冒号可能放宽另一无冒号子句。三项均可在自动建档前到达，属于发布阻断。
- 修复: 按列表项过滤非授权语气；冲突数量只保留“已服用”事实、不绑定剂量；冒号名称按强子句边界单独授权，并在 policy 与 executor 共用同一解析结果。最终策略契约递增至 `agent-capability-policy-v48`，目标绑定契约递增至 `authorized-target-set-v34`。
- TDD 证据: 新增 13 条回归用例先得到 10 failed / 3 passed，修复后 13/13；完整相关六文件集成 `5357 passed, 7 warnings, 0 failed`。阻断级 Ruff 与 `git diff --check` 通过。
- 第二轮审查: 对精确提交 `135af3d4a` 的独立只读探针继续发现“没吃/可能吃”列表项、换行或同句二次写动作的冒号越界，以及被拒项/跨子句元数据污染；均按 NO-GO 处理，提交未 push、未部署。审查器在形成最终文本前因工作树进入下一轮修复而中止，已保留可复现探针结果，不把该轮记为 GO。
- 第二轮修复: 扩展否定与不确定性项过滤；冒号解析按换行/强标点及每个 `记录补剂` 动作保留局部来源；确定性调用复用同一局部目标集；被拒项不能向肯定项提供剂量/时间，跨子句冲突元数据也只保留服用事实。新增对抗集扩至 26 条并全部通过；最终完整相关六文件集成 `5370 passed, 7 warnings, 0 failed`。
- 第三轮审查: 对精确提交 `21416737d1c1cb8f81d6bf58420722f3b591e5df` 的独立 safety/privacy 复核仍裁决 **NO-GO**：否定/假设语气出现在名称后缀时仍可成为可写名称；首个被拒条目的剂量与时间可污染后续肯定项；多条目或同名冲突时间会猜测绑定到单项。该提交未 push、未部署。
- 第三轮修复: 将补剂条目授权判断收敛为统一函数，在剥离写动作、通用标签、剂量和时间后同时检查前缀及后缀残留；任一被拒条目存在时不绑定元数据；只有单一目标且唯一明确时间时才写入 timing。新增用例先复现 `7 failed`，修复后三文件集 `2261 passed`，完整相关六文件集 `5379 passed, 7 warnings, 0 failed`。
- 第四轮审查: 对精确提交 `d6e568c28f38d588a312b76adf810e47a7fa46d7` 的独立 safety/privacy 复核确认第三轮解析风险已关闭，但继续以 **NO-GO** 阻断三个执行层问题：异常补剂列表响应会被当作空库继续自动建档；打卡响应显式 `status=failed` 且带 ID 时会被包装成 verified 成功；上游错误详情可能把健康名称带入 warning 日志。该提交未 push、未部署。
- 第四轮修复: 补剂定义查询只接受列表或 `data` 列表且逐项验证对象结构，异常时在写入前拒绝；自动建档后的打卡响应复用统一写结果校验并要求可验证记录 ID，明确失败与无法验证均返回 `verified=false`；查询、建档和打卡日志只记录用户 ID、稳定原因与响应类型，不记录上游异常文本。新增 3 条用例先得到 `3 failed`，修复后定向 `3 passed`，完整相关六文件集 `5382 passed, 7 warnings, 0 failed`。
- 第五轮审查: 对精确提交 `4dcbb8b1e23266e8cd976961686c492a9e9c8f5c` 的独立 safety/privacy 复核以 **NO-GO** 发现：名称后缀“没吃/只是假设”可在尾部动词清洗或授权切句中丢失后被写入；带 `data: []` 的外层错误响应仍可继续建档；打卡响应声明其他资源类型时会被强制改写为 `supplement_log`；列表或零值 ID 虽不能形成 verified receipt，工具结果仍会显示完成文案。该提交未 push、未部署。
- 第五轮修复: 列表项先以原始文本检查非授权语气再清理尾部动词，冒号名称提取保留原始片段；定义列表解析拒绝外层失败状态与错误字段；回执身份仅接受正整数或非零字符串，并要求打卡资源类型为空或精确为 `supplement_log`，错误类型、冲突/列表/零值 ID 均返回 `verified=false` 且不再宣称完成。新增对抗定向 `34 passed`，包含通用回执身份测试的七文件集 `5435 passed, 7 warnings, 0 failed`。
- 第六轮审查: 对精确提交 `578f70b4a9fea61a321023fcf253caae4b1c2aef` 的独立 safety/privacy 复核继续以 **NO-GO** 发现：后缀“不吃/不曾吃”仍可被清洗成新名称后写入；仅有通用 `id`、负数或小数字符串的打卡响应仍可显示完成或形成回执；`errors` / `error_code` 响应仍可能被视为成功。该提交未 push、未部署。
- 第六轮修复: 扩展否定、未来、疑问和撤销语气的条目级过滤；NFC 打卡必须携带正整数 `record_id`，通用 `id` 不再替代打卡身份；统一写结果校验拒绝非空 `error`、`errors`、`error_code`；补剂列表逐项要求合法 ID、非空名称和布尔活动状态，自动建档响应也必须无错误状态且有合法定义 ID。新增用例先得到 `7 failed`，修复后定向 `46 passed`，最终七文件集 `5453 passed, 7 warnings, 0 failed`。
- 第七轮审查: 对精确提交 `d20cf62f853cbb3d425773c04ff28f0729a489aa` 的独立 safety/privacy 复核继续以 **NO-GO** 阻断：同一列表里“记录乙、不记录甲”会因选择最后一个通用写动作而误写甲；“不想再吃/以后吃/能吃吗”等非已发生语气可能被清洗成名称；已登记补剂分支未复用严格 NFC 回执校验，且 `success: 0`、`ok: "false"` 或冲突身份字段仍可能被接受。该提交未 push、未部署。
- 第七轮修复: 冒号列表始终以显式 `记录补剂:` 标签为局部起点，不再选择列表内后续通用“记录”；补剂分隔仅在“再”后确有新动作时切分，统一阻断否定、未来、意愿与疑问条目；新增单一 NFC 打卡回执校验器，同时覆盖已有定义与自动建档分支，要求顶层正整数 `record_id`、一致且合法的身份字段、精确资源类型，并只接受布尔真值的 `success` / `ok`。新增定向集 `61 passed`，最终七文件相关集成 `5471 passed, 7 warnings, 0 failed`。
- 第八轮审查: 对精确提交 `40de302b960ae51ce239c135c3f56a6d8b4d6606` 的独立只读复核以 **NO-GO** 复现三类 P1：未来/停用/不记录语义仍可生成当天写入；嵌套 `data/result` 或列表中的失败、非法状态和错误资源类型可被包装成 verified 回执；自动建档响应的名称、用户、资源类型及嵌套身份不一致仍可继续打卡。50 种响应矩阵在已有定义和自动建档两条分支均完成重放；未发现跨用户 API 绕过或日志健康内容泄漏。该提交未 push、未部署。
- 第八轮修复: 冒号列表使用收紧的当前事实语法，阻断未带完成式的服用动作、未来时间、停用和二次记录指令，且不影响普通“剂量 + 服用时间”定义；写结果递归检查 `resource/record/data/result` 字典与列表 envelope，并严格验证状态和资源类型；补剂定义列表拒绝重复 ID、行级失败、错误 owner/类型，多个同名活动定义要求先消歧；自动建档要求返回名称、当前用户、定义 ID 和资源类型一致后才可打卡。对抗定向 `119 passed`，最终七文件相关集成 `5532 passed, 7 warnings, 0 failed`。
- 第九轮审查: 对精确提交 `ba1d26c951d83b2448d19677a15a93cb3cb1d7c4` 的独立只读复核以 **NO-GO** 发现：深层字典/列表中的冲突记录 ID 仍未与顶层 `record_id` 比对；“明早/昨晚”会被当天打卡；无独立补剂名的顿号后缀（如未来剂量、频次、英文指令、仅供参考或暂停本次）会被丢弃后仍写入前一项。该提交未 push、未部署。
- 第九轮修复: 每个递归身份字段必须与顶层打卡 ID 完全一致，且 NFC 成功必须有明确终态；补充非今天日期边界；增加悬空修饰检测，只有被拒片段清除时序、动作、剂量、频次和指代后仍有独立名称时，才允许保留同列表的肯定项。策略/目标绑定契约递增至 `agent-capability-policy-v49` / `authorized-target-set-v35`。新增端到端对抗测试真实穿过 Gateway、MockTransport、执行器和回执构建，完整语义与恶意响应矩阵 `89 passed`；阶段性八文件相关集成 `5654 passed, 7 warnings, 0 failed`。
- 第十轮审查: 对精确提交 `d7a8c2e03e6fc9e0cf42b8091dbab0359312c3fd` 的独立只读复核以 **NO-GO** 发现：逗号后的“打算明天再吃”和顿号后的“只是举个例子”仍能写前一项；create/lookup 响应中的深层 owner、name、active 或双类型冲突仍未全部保持与顶层一致。审查执行 632 次额外 mock 探针，API owner 鉴权和日志隐私未发现绕过。该提交未 push、未部署。
- 第十轮修复: 悬空修饰清理补齐打算、示例、演示与参考语义；定义列表和自动建档对每个递归 source 的 owner、名称、活动状态及 `resource_type/type` 分别做一致性校验。端到端对抗文件扩至 `93 passed`；最终八文件相关集成 `5663 passed, 7 warnings, 0 failed`。
- 第十一轮审查: 对精确提交 `11d5fb6761393bc1619b33d4ec4fa9186fca6c64` 的独立只读复核继续以 **NO-GO** 发现六组可写绕过：中文示例指代、下星期计划、英文未服用、中文频次计划、暂停指代和上周已服。审查复跑提交内八文件 `5663 passed` 并完成 1058 次额外探针；递归响应冲突、缺失成功终态、API owner 鉴权与日志隐私没有新增 P1。该提交未 push、未部署。
- 第十一轮修复: 非授权语义按英文意图、相对日期、频次和指代类别补齐，并将悬空修饰判定从“清洗后字符长度”收紧为“必须存在明确补剂名称证据”；未知修饰语会阻断整句，带独立补剂名称的否定项仍可保留相邻肯定项。新增精确六例、两组未知修饰语和品牌补剂否定项回归；定向端到端矩阵 `145 passed`，最终八文件相关集成 `5674 passed, 7 warnings, 0 failed`。
- 第十二轮审查: 对精确提交 `ec34bfc4a8975b4acf9c80bcc324ff8725098dc5` 的独立只读复核以 **NO-GO** 复现七类新的悬空片段误写：泛称营养素的否定/暂停/示例、上个月历史、明日未来、间隔频次及英文缩写否定；existing-definition 与 auto-create 两路径共 14/14 实际落下当天记录并生成 verified 回执。八文件 `5674 passed`，另完成 122 条语义变体与 2315 次执行/响应探针；用户隔离和日志隐私通过，但打卡 owner/definition 及列表外层字段冲突仍有九次被接受。该提交未 push、未部署。
- 第十二轮修复: 冒号列表除首个目标外，每个分项默认必须具备明确补剂名称证据或仅包含合法的当前事件剂量元数据；任何未知修饰、时态、泛称或英文片段均失败关闭并要求澄清。泛称名称证据显式排除指代、任意和产品类别表达；NFC 回执新增当前用户与补剂定义一致性校验，定义列表 envelope 拒绝冲突 owner、单项身份和错误资源类型。原评审 122 条语义变体重放误写为 `0`，2315 次响应/执行探针未再发现响应完整性缺口；定向两文件 `287 passed`，补充精确回归 `126 passed`，最终八文件相关集成 `5696 passed, 7 warnings, 0 failed`。五组复杂具名否定表达会保守澄清而不写入，作为已知 P2 安全取舍保留。
- 第十三轮审查: 对精确提交 `21fb41f91bddd891a5931924ff124ec6483d3e80` 的全新独立只读复核以 **NO-GO** 复现两类 P1：上述/前述/同款等泛称指代仍可让相邻肯定项落库，首项中的历史或否定残留仍可整体成为新补剂名称；四组真实 JWT/API/隔离 PostgreSQL 双路径共 8/8 落库并产生 verified 回执。八文件 `5696 passed`；独立 160 条语义 fuzz、320 个双路径场景和 386 次 Gateway 调用发现 18 条/36 场景误写。另发现定义列表旁支 `result` 的 owner/type 冲突未参与校验。该提交未 push、未部署。
- 第十三轮修复: 取消混合授权列表的部分成功语义，冒号列表成为原子授权单元，只要任一分项含否定、假设、非当前或写入冲突，整组均不写；名称证据只基于原始分项，除剂量与明确服用时点外不再先清洗修饰词后猜名称，首项也必须满足同一结构约束。定义查询只接受单一 `data` 列表 envelope，拒绝旁支 resource/record/result；tap、create、lookup 行统一收紧成功终态、owner、定义身份、资源类型及跨资源 ID。复用独立审查器重放 160 条语义 fuzz，`0` 个 unsafe path；1268 次响应矩阵仅接受两次合法的任意正整数新 record ID，create/lookup/tap 冲突与缺失终态均为 `0`；日志敏感命中 `0`。定向两文件 `305 passed`，最终八文件相关集成 `5709 passed, 7 warnings, 0 failed`。
- 第十四轮审查: 对精确提交 `161eeb18450c20fcab7e419344d9a0efc7f08f43` 的全新独立只读复核仍以 **NO-GO** 阻断两类 P1：否定、历史、频次、泛称和带引号的语义残留仍可整体成为补剂名；分号或换行后的历史、未来及英文限定语会被丢弃后写入前项。独立新语料覆盖 218 条消息和 1520 个场景，其中 117 条拒写预期消息发生派发、306 个场景生成 verified 写入。9 组最小案例在 existing-definition / auto-create 双路径通过真实 JWT、本地完整 API 与隔离 PostgreSQL 共 18/18 落库。递归响应矩阵 27479 个场景未接受身份或状态冲突；15 项用户隔离 API 检查、4 项正反控制和六份日志隐私扫描通过。该提交未 push、未部署。
- 第十四轮修复: 明确名称只允许受控的产品/营养素形态，并在原始分项上拒绝否定、摄取动作、相对或绝对日期、未来计划、频次、泛称、引用/测试及中英文语法标记；冒号授权后的任一未标注强标点片段均使整批失败关闭。新增 `定期`、`一星期三回`、`同一款` 及其混合列表回归，保持列表原子语义。复用第十四轮独立审查的 218 条新语料重放 1308 个执行场景，unsafe dispatch / verified write / exception 均为 `0`，日志敏感命中 `0`；相关八文件回归合计 `5715 passed, 7 warnings, 0 failed`，阻断级 Ruff、Python 编译与 `git diff --check` 通过。
- 第十五轮审查: 对精确提交 `ad01c51e17132310e647a71e269617dda67e2981` 的全新独立只读复核继续以 **NO-GO** 阻断：`绝非`、`毋须` 等否定前缀，往昔/旧时、拟用/待用、按需/规律、泛称和转述语法仍可整体伪装为新补剂名；另一个带冒号的显式 `记录补剂：未服...` 子句会被跳过，导致同句前项继续写入。独立 225 条新语料、900 次 existing / auto-create 执行中有 84 条消息派发、250 个场景产生 verified 回执；隔离 PostgreSQL + 真实 JWT/API 的 7 组最小案例双路径 14/14 落库并产生 16 个 verified 回执。递归到 10 层的 1368 个响应矩阵未接受 owner、definition、resource、status 或 identity 冲突，用户隔离 15/15 和合成隐私标记扫描通过。该提交未 push、未部署。
- 第十五轮修复: 名称证据在 NFKC 后移除 Unicode 格式控制字符，并拒绝否定、历史/未来、频率、泛称、引用/转述等名称前语法及内部结构助词；多个显式冒号补剂命令按单一授权单元处理，任一局部命令未授权或无明确名称时整句不写。新增 14 个跨类别与强标点回归先得到 `14 failed`，修复后与局部多命令正例合计 `109 passed`；重放该轮独立 225 条语料、900 次执行后 unsafe dispatch 为 `0`，728 个响应样本只接受合法新 record ID 及不匹配 lookup 后安全建档；最终相关八文件回归合计 `5729 passed, 7 warnings, 0 failed`，阻断级 Ruff、Python 编译与 `git diff --check` 通过。
- 第十六轮审查: 对精确提交 `30cf80cdac72b345a6f893ff83a79c9071e961e9` 的全新独立只读复核仍裁决 **NO-GO**（P0 0 / P1 2 / P2 0）：新的否定、待定、频次、泛称和引用词仍可拼接成未知名称；多显式命令中，后项问号被强边界切分丢弃后会先写前项、再拒绝后项，破坏整句原子性。176 条全新负向语料中 59 条发生写入，并在 existing / auto-create 的 118 个真实 PostgreSQL + JWT/API 场景全部复现。提交内八文件 `5729 passed`；响应矩阵、用户隔离和日志敏感标记扫描通过。该提交未 push、未部署。
- 第十六轮修复: 未加引号的未知补剂名收紧为最多 6 个字符的紧凑名称，较长品牌需显式引用或先存在于用户补剂库，从结构上阻止两字以上语法前缀与五字成分名一起自动建档；显式 `记录补剂:` 作用域内出现问号时整句拒绝。补充 `复合维B` 和 2–8 位大写补剂缩写的安全名称支持，覆盖原始问题中的 PQQ / MNAC，不以放宽任意英文短语换取可用性。新增 8 条失败优先回归，修复后定向 `115 passed`；复用第十六轮审查器重放 176 条负例 / 720 次双路径执行，unsafe dispatch 为 `0`，1140 个响应样本无新增异常接受；最终相关八文件 `5737 passed, 7 warnings, 0 failed`。
- 第十七轮审查: 对精确提交 `0d2fea43b26a1f281c4e081baa32efee68fc88d0` 的全新独立只读复核仍裁决 **NO-GO**（P0 0 / P1 2 / P2 0）。128 条新合成消息中 8 个“待定短验...”变体仍会写入；四种引号包裹的长名称则被分类为读取而无法记录，与“长品牌显式引用后可写”的产品约定不符。提交内定向回归 `245 passed`，负向与正向语料合计 `116 passed / 13 failed`；该提交未 push、未部署。
- 第十七轮修复: `待定` 纳入未授权语法；显式引用名称在 intent、reported-speech scope、policy、deterministic plan 与 gateway grounding 全链路保持原子名称，并携带用户明确给出的单项目剂量/时间。引号只放宽长度和名称内部的普通形态词，`引用/示例/待定/计划` 等高置信语法即使被引号包裹仍拒绝。重放审查器 32 个正例、96 个负例后 unsafe negative 为 `0`；5 个未加引号的合成短名称保守拒写，用户可通过引号明确授权，作为 P2 安全取舍保留。新增回归覆盖八个待定名称、四类引用名称及引用内语法拒绝；相关八文件回归 `3430 passed, 6 warnings, 0 failed`。
- 第十八轮审查: 对精确提交 `206d357f20169062dee29d503af193136df832d6` 的独立归档复核在扩展语料中发现 `暂定`、`预留`、`待议` 及引号内同类表达仍可到达查询、自动建档和 NFC 打卡，因此裁决 **NO-GO**。该 revision 未 push、未部署；PostgreSQL/JWT 双路径在发现发布阻断后停止，不把未执行项记为通过。
- 第十八轮修复: 将 `暂定/预留/待议` 同时加入普通名称语法和引用名称的高置信拒绝集，新增未加引号与引号内六类端到端拒写回归。修复后须重新生成精确提交并从 G4、preflight、真实 LLM 与 main CI 起完整重验。
- 第十九轮审查: 对精确提交 `f6b7f845be0636008458cc7626e3c2dfc17ac661` 的新归档复核确认第十八轮词项已关闭，但新边界 `记录补剂：一粒“候补复核甲硒”。` 仍会计划写入，G4 再次 **NO-GO**。该 revision 未 push、未部署。
- 第十九轮修复: 不再逐个只补最小词项；新增保守的待定前缀门禁，并把候补、暂缓、搁置、尚待及复核/审核/核验/确认/讨论/咨询等流程语义统一纳入普通与引用名称拒绝规则。显式引用仍只豁免长度及真实产品名中的普通单字，不能豁免流程、草稿或待办语义。扩展回归覆盖八类直接语法与三类引号内流程名称；须在新精确提交上重跑独立语料与双路径安全验证。
- 第十九轮补充修复: 同轮复核还发现 `【核心长名称合成补剂02甲乙】` 等方头括号名称会先丢失引用边界，再把名称内“补”误判成服用动作。解析改为保留方头括号直到整体引用识别完成；待定前缀也前移到所有名称路径，使 `预备/留待` 等不再只依赖 gateway 防御。新增方头括号正例及两类直接负例，四种引用格式继续保持对称。
- 最终 G4 复审: 独立 reviewer 对精确源码提交 `37c316bda61ac3fbf54a2bed4b9e778cf0a0a4bc` 使用全新 `git archive` 完成只读审计，裁决 **GO**（P0 0 / P1 0 / P2 5）。回放 268 条语料（前轮 60 + 核心 128 + 时态 40 + 全新边界 40），全部负例零 planner write；existing-definition / auto-create 的伪造匹配调用均零出站、零回执。四类引用长名称含方头括号正例均可写并保留原始单项剂量；193 项补剂对抗回归通过。真实 UTF-8 PostgreSQL + JWT 证明跨用户无法读取或打卡他人定义，所有者可正常写入，动态日志未出现合成补剂名称或剂量。五个未引用任意短合成名称继续保守拒写，引用后可达，作为 P2 取舍接受。
- 当前 Gate: G3 PASS；G4 GO。仅剩精确 main CI、部署健康和线上 revision 核验，完成前不得宣称发布。
