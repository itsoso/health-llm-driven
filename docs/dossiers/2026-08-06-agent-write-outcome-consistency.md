# Dossier: Agent 健康写入终态一致性

| 字段 | 值 |
|---|---|
| slug | `agent-write-outcome-consistency` |
| 创建日期 | 2026-08-06 |
| 当前阶段 | S6 部署准备 |
| 状态 | building |
| 负责 | Codex + release owner |
| 反馈环 | Backend deploy + Web deploy + Mobile OTA/1.3.3 candidate |

## Correct Course

- [x] Correction Block
  - 触发:第二张生产截图证明早餐图片问题不是孤立 bug，旧用药/补剂卡与 Agent 终态也可互相矛盾。
  - 旧基线:只修早餐草稿外键顺序和无图 fallback。
  - 新基线:增加跨饮食/用药/补剂的终态卡片一致性闸，同时修复两条已证实根因。
  - 回退阶段:S1
  - 需重跑 Gate:G1、G2、G3、G4、G5、G6
  - 用户确认(若 scope/风险变):已确认，2026-08-06

## S0 · 用户需求(逐字)

> “保存早餐还是有问题”
>
> “类似的bug还不少”

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1):核心用户在 Agent 中记录饮食、用药或补剂；当前只能看到矛盾结果后重试或转到独立页面核对。
- 锚点用户相关性:低摩擦、可验证的健康写入是 Mobile Agent 正式版核心路径。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `agent_write_outcome.py` 与 `agent_turn_outcome.py` 已按执行事实分类写入/回合终态。
  - `medication_intake_batch.py` 已有服务端 `WriteIntent`、手动确认、回执和幂等执行。
  - `agent.py` 是最终 query 派生卡片的统一组合点。
  - `contextual_meal_photo_service.py` 已有草稿与资产的单事务保存入口。
- 缺什么:
  - 用药批次解析不支持单药“数量在药名前”。
  - Agent 主分类器与摄入分类器对同一句话结论不同。
  - route-only 用药/补剂卡被客户端当作 pending。
  - failed/blocked 回合仍可追加 query 派生摄入卡。
  - 图片父草稿与子资产没有显式 flush 顺序；失败后通用饮食写入未被阻断。
- 硬约束 / 平台·安全边界:
  - 用药永久 `manual_confirm`；受控药名；不猜药、不改剂量。
  - 只有回执可证明成功；图片与记录失败必须 fail loud。
  - 不记录真实健康文本到 telemetry。

## G1 · 准入裁决

- first_class_objects:`WriteIntent`, `ExecutionEvent`
- core_loop_step:execution -> confirmed event -> Health Twin
- target_surface / safety_level / autonomy_tier:Backend+Mobile+Web / medical_boundary / manual_confirm
- spec_required:是，涉及跨端卡片契约与健康写入安全语义。
- smallest_end_to_end_slice:两条生产原句 + 共享 terminal card suppression。
- stale_surface_to_remove:route-only 卡片的伪“待确认”展示。
- **裁决**:PASS —— 修复既有核心写入闭环，不扩大自治范围。
- 用户确认:已确认。

## S2 · PRD

- 链接:`docs/specs/active/2026-08-06-agent-write-outcome-consistency.md`
- 引用的权威 R 号:R5、R11、R12。
- 边界(不做):不做状态机大重写、DB migration、药物建议或营养算法重做。
- 验收 Gate:回执/真实 pending/失败三态与正文、卡片、数据库一致。
- 未决问题:无。

## S3 · 规划

- 链接:`docs/plans/2026-08-06-agent-write-outcome-consistency.md`
- 分阶段 + 反馈环路由:Backend RED/GREEN -> card choke point -> Web/Mobile presentation -> G3/G4 -> deploy -> prod smoke -> iOS release resume。
- 长杆 / spike:PostgreSQL 父子 flush 顺序与生产合成账号验证。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge + 两次生产根因取证。
- 硬阻断(已焊进规划):不用 LLM 作为写入真源；疑问/否定/历史/未知药名继续拒绝；失败不生成替代写入入口。
- 待拍板分叉:系统性小切片、单句热修或总状态机重写；用户选择系统性小切片。
- **裁决**:PASS —— 用户于 2026-08-06 确认 B 方案。

## S4 · 研发任务分解

- 跨端 API 契约:Agent SSE 继续使用现有字段；只为 route-only legacy card 增加可选 `presentation_state=suggestion`。
- 任务表:
  - [x] T1 用药生产原句 parser/intent/zero-LLM flow。
  - [x] T2 终态 query card suppression 与 suggestion contract。
  - [x] T3 Web/Mobile 真实展示。
  - [x] T4 早餐图片父子原子保存与 no-fallback guard。
  - [ ] T5 G3/G4/部署/生产验证/1.3.3 release gate。
- 并发检查:已 fetch `origin/main`；开放 PR 无相同范围；隔离 worktree 基线与 `origin/main` 一致。

## S5 · 实现

- 委托:当前 Codex 会话，未使用子 agent。
- 分支/commit:`codex/ios-1-3-3-app-store-release` / 当前 HEAD（G4 review candidate）。
- 实现摘要:
  - 单个受控药物支持“数量在药名前”的明确已服句式，仍走 durable `WriteIntent` 手动确认。
  - Agent 主分类器只把确定性解析成功的药名后缀表达提升为用药域；模型提议入口在创建 `WriteIntent` 前强制限定受控别名或用户已有药物。
  - 失败/阻断终态在 API 卡片组合点压制 query 派生卡。
  - route-only 用药/补剂卡显式标记 suggestion，Web/Mobile 展示“待核对/去记录”。
  - 图片父草稿先 flush，再插入资产；失败或待确认关闭通用 diet 写入适配器。

## G3 · 测试闸

- 已通过:
  - Backend 增量集成:419 passed（7 个相关测试文件，SQLite）。
  - Backend 图片执行器整套重跑:103 passed（实现整理后新鲜证据）。
  - G4 修复整组:216 passed（用药计划、Agent 完整流程、主意图分类、受控药物自动创建）。
  - PostgreSQL 16 真实语义:9 passed（未知药名拒绝、用户已有药物兼容、并发幂等、父子 FK/事务顺序与图片锁）。
  - Web:336 passed；production build 通过；全量 ESLint 0 error（33 个既有 warning）。
  - Mobile:2404 passed、1 skipped；TypeScript、design token gate 通过。
  - 结构/模型闸:secret scan、doc drift、101 dossiers、LLM live-change、12+50+12+9 个零成本回归全部通过。
  - 静态阻塞闸:Ruff F821/F822/E9 与 Python compileall 通过；`git diff --check` 通过。
- 集成闸:本地候选闸通过；等待 commit 后主干 CI 真实色。
- main CI 真实色:pending。
- 跨家族 capstone:pending。
- **裁决**:pending。

## G4 · 安全闸

- 触发:用药 + 健康写路径。
- 首次独立评审:commit `9c0921031`；reviewer 发现未知“药名样式”可被宽泛分类器和 LLM medication tool 带入 durable `WriteIntent`，裁决 **NO-GO**。
- 回上游修复:分类器只提升确定性受控药名；`propose_medication_intake_items` 只接受受控别名/规范名或该用户已有 Medication，并新增服务边界、分类器、完整 Agent 流程负例。
- 修复后自审:未知名称在创建 `WriteIntent` 前 fail closed，零 MedicationLog；用户已有药物与受控药物兼容路径保留。
- 独立复审:commit `70ab2a63d`，17 个定向用例及动态跨用户反例通过；Critical / Important / Minor 均无，工作树和 HEAD 完整性校验通过。
- **裁决**:PASS（`G4: GO`）。

## S6 · 部署

- 路由:backend-deploy + Web deploy + conditional Mobile OTA/1.3.3 candidate。
- 部署 SHA / 回滚点:pending。

## G5 · 部署健康闸

- 健康分:pending。
- prod smoke:pending。
- **裁决**:pending。

## S7 · 上线验证

- 真实路径验证:合成 QA 账号运行两条生产用例；真机核对卡片语义。
- 结果:pending。

## G6 · 验证闸

- 需求在 prod 对 anchor 用户真成立?:pending。
- 真机/发布用户确认:pending。
- **裁决**:pending。

## S8 · 沉淀

- 新坑沉淀:pending。
- 文档同步:本 spec/plan/dossier；必要时更新 release dossier。
- 状态:building。
