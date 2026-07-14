# Dossier: 对话建议先加入今天，验证周期渐进展开

| 字段 | 值 |
|---|---|
| slug | `chat-today-action-progressive-plan` |
| 创建日期 | 2026-07-14 |
| 当前阶段 | S7 上线验证 |
| 状态 | shipping |
| 负责 | Codex |
| 反馈环 | Backend deploy -> Mobile production OTA -> iOS Simulator / 真机 |

## Correct Course

- [x] Correction Block
  - 触发: 用户点击“加入今天计划”后，系统反而先展示完整 7 天验证卡；未来日默认全部展开，真正的执行按钮落在首屏之外。
  - 旧基线: `runtime_agenda` 可以在 Chat 完整展开；“加入今天计划”通过二次 Prompt 交给 Agent 处理。
  - 新基线: 今日行动与验证周期分层；加入今天直接走受控确认写入，只有明确周期意图才展示未来节奏，且默认折叠。
  - 回退阶段: S2 / S3。
  - 需重跑 Gate: G2 / G3 / G4 / G5 / G6。
  - 用户确认(若 scope/风险变):☑ 用户已用真机截图明确要求优化。

## S0 · 用户需求(逐字)

> 这个七天验证节奏，无论UI还是实际可执行性上都有很大问题，想办法优化，前一个prompts是加入计划，但上来就是七天计划，也不是很合理

- 谁用 / 解决什么 / 现在怎么绕过: Mobile 小巴用户希望把一条建议加入今天并立即执行；当前必须先阅读一张很长的七天卡，再滚动寻找动作。
- 锚点用户相关性: 高频健康执行需要最低打扰和一手可达，不能要求用户先理解完整干预周期。

## S1 · Discovery(现状勘察)

- `mobile/components/chat/ChatBubble.tsx`:“加入今天计划”被重新发送为含“计划”的自然语言 Prompt。
- `backend/app/services/inline_cards.py`:`_is_runtime_agenda_query` 只要匹配“计划/安排/下一步”就附加 7 天卡，无法区分“写入今天”和“查看周期”。
- `mobile/components/chat/cards/RuntimeAgendaCard.tsx`:未来日默认全部渲染，通用动作栏位于整张卡底部。
- `mobile/components/actions/InterventionDraftSheet.tsx` + `mobile/services/interventionDraft.ts`:已有受控的今日行动确认页，可复用而不新建写入体系。
- `backend/app/api/action_card.py`:创建和接受是两个动作；需支持一次人工确认后的原子 accepted 创建，避免创建成功、接受失败造成半完成状态。
- 硬约束:不改变健康建议本身；写入仍为 `manual_confirm`；未来日不能伪装成已经确定的处方式计划。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`LeverageAction`, `HealthAgendaItem`, `ExecutionEvent`, `InterventionCycle`, `WriteIntent`。
- core_loop_step:小巴建议 -> 用户确认今日行动 -> 今日执行 -> 验证窗口 -> 后续重排。
- target_surface / safety_level / autonomy_tier:Mobile + Backend / low + write-path / `manual_confirm`。
- spec_required:是，改变用户可见行为并收紧既有写入语义。
- smallest_end_to_end_slice:加入今天不再触发七天卡；确认后原子创建 accepted 行动；运行时卡默认只显示今天。
- stale_surface_to_remove:二次 Prompt 加入计划、默认展开的未来 7 天列表、无来源时的禁用“完成”按钮。
- **裁决:PASS。** 用户已明确确认纠偏方向。

## S2/S3 · PRD 与规划

- 链接:`docs/plans/2026-07-14-chat-today-action-progressive-plan.md`。
- 引用权威对象:governance §4 核心循环、§5 一等对象、§6 可执行行动优先与写自治。
- 边界:不新建 Agenda 数据模型，不自动接受模型建议，不改语音输入框，不把未来日写死。
- 未决问题:无。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 硬阻断:必须由按钮点击打开确认页；accepted 只能随这次显式确认原子写入；失败必须可见；周期视图不能隐藏医疗边界。
- 待拍板分叉:无。
- **裁决:PASS。** 复用现有 ActionCard、InterventionDraftSheet、manual-confirm 卡片动作和 `/agenda` 页面。

## S4 · 研发任务分解

- 跨端 API 契约:`ActionCardCreate.accepted: boolean = false`，仅在用户确认提交时传 `true`；后端同事务写 `user_decision=accepted` 与 `decided_at`。
- 任务表:
  - [x] T1 分流加入今天 / 当前行动 / 明确周期三种意图。
  - [x] T2 接回今日行动确认页并原子创建 accepted ActionCard。
  - [x] T3 将运行时卡收敛为今天优先、验证摘要、未来折叠。
  - [x] T4 让完成/调整动作在首屏可达并补失败回归。
  - [x] T5 后端部署、types 生成与 Mobile OTA；真机路径验证留在 G6 人在环确认。
- 并发检查:当前工作树已有他人对 conversation opener 的修改；本切片不触碰、不暂存、不回退这些文件。

## S5 · 实现

- 点击“加入今天”直接打开可编辑确认页，不再发送含“计划”的二次 Prompt。
- 直接确认创建 accepted ActionCard；相同来源和标题的重试幂等返回原行动。
- 默认复盘窗口为次日；`verification_days` 写 `check_back_date`，与显式 `expires_at` 解耦。
- Chat、Today 与完整 Agenda 共用今天优先的运行时行动；未来日期默认折叠并标记为动态预测。
- accepted 行动提供 `daily_plan_action.complete`，复用既有事件接口写完成回执并同步来源卡片。
- 原子能力注册表仅放行受控的 route、agenda.complete 和 daily-plan completion，保持人工确认和用户隔离。
- 确认页默认折叠高级复盘设置，减少首次决策负担。
- accepted 写入增加 AdviceGuard；无“自行”字样的停药/停用/换药/加减量同样阻断。
- 药物上下文从共享 `drug_lexicon` 识别完整药名及文本位置，并结合药名前后动作窗口、中文剂量变化和子句安全语义判断；跨句咨询或前一子句“不要自行”不能放行当前具体变更，协调式安全警示仍可正常呈现。
- 药物动作窗口覆盖时间修饰、泛称药物、否定服用，以及加/减/少吃/多吃与片数单位的对称剂量变化；同时保留“服药期间不要吃辛辣”等非药物变更反例。
- ActionCard 增加 `accepted_create_key` 数据库唯一键及 managed migration，关闭多设备并发重复写入。
- Today 与 Chat 对 `requires_manual_confirm` 统一弹确认；完成事件增加数据库唯一幂等键，支持响应丢失和并发点击后的回放。
- 运行时意图改为正向健康语境 gate；仅保留少量精确上下文承接短句，避免为红烧肉、论文等对象持续维护黑名单。

## G3 · 测试闸

- Backend 扩大定向集成:179 个用例通过，覆盖 accepted 原子创建、数据库幂等、AdviceGuard、药名动作窗口/时间修饰/中文剂量/数量单位/多动作/否定与条件式组合、非药物反例、健康语境召回及复合词消歧、复盘/过期分离、Today 共用行动、managed migration 及 Daily Plan 完成/回放。
- 推送隐私回归:48 个用例通过；共享词库扩充没有造成敏感名泄漏或良性文案误泛化。
- Mobile:8 suites / 125 tests passed；TypeScript `--noEmit` 与选定 ESLint 通过。
- PostgreSQL:在真实测试库事务中执行 ActionCard 与 InterventionEvent 两条 managed migration，重复键均触发唯一约束后回滚。
- `check_doc_drift.py`、51 份 Dossier 一致性闸和 `git diff --check` 通过。
- 全量 Daily Plan 文件另有 2 个既存 PostgreSQL fixture 外键问题；本切片直接相关完成路径已单测通过，不以吞退出码方式掩盖。
- 最终干净主干复验待提交前回写。

## G4 · 安全闸

- 触发:写路径与对外健康行动呈现。
- 独立安全评审对停药、换药、加减量、数量单位、用户隔离、人工确认、回执及幂等路径做对抗复核；机制矩阵 11/11 符合预期。
- 非阻断残余风险:固定词法窗口对极少数复杂句可能 fail-safe 拒绝写入，后续纳入对抗语料 eval，不允许因此自动放宽安全边界。
- **裁决:PASS / GO。** 未发现当前发布路径中的 P0/P1 阻断。

## S6 · 部署

- 路由:Backend deploy -> generate-types -> Mobile production OTA。
- 主干提交:`32cfe6b3f fix(mobile): prioritize executable today actions`。
- Backend:`deploy.sh -b` 完成；managed migrations `20260714_170000` 与 `20260714_171000` 已应用。
- Mobile Production OTA:runtime `1.3.1`，update group `910f2356-6f53-431e-9d4c-6ff7650323ad`，iOS update `019f601c-c414-7409-a13d-64fd97b0daec`。

## G5 · 部署健康闸

- 生产运行提交:`32cfe6b3f`。
- `deploy.sh` 健康度:`60/60 PASS`；数据库、Redis、Celery 均 connected；本地与线上 skills manifest 均为 22。
- `/api/v1/action-cards` 未鉴权 GET 返回 `405` 而非 `404`，路由已加载；生产 `/health` 返回 healthy。
- **裁决:PASS。** 无自动回滚，Backend 与 OTA 均已发布。

## S7 · 上线验证

- 已完成生产服务和发布工件验证；设备需冷启动或后台 30 秒以上拉取 OTA。
- 待真机点击“加入今日计划”确认:直接出现可编辑确认页、默认明天复盘、不生成完整七天卡；仅明确询问七天/本周时显示折叠周期。

## G6 · 验证闸(人在环)

- **待用户真机确认。** 当前不提前宣称完整闭环完成。

## S8 · 沉淀

- 待回写。
