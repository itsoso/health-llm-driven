<!--
  Dossier 模板 — 复制到 docs/dossiers/<YYYY-MM-DD>-<slug>.md
  这是一个 feature 的可追溯脊柱:任何 session 接手先读「当前阶段 + 状态」,从断点续。
  Gate 裁决必须如实写(REJECT/BLOCK 也写,不藏)。
-->

# Dossier: <feature 一句话标题>

| 字段 | 值 |
|---|---|
| slug | `<slug>` |
| 创建日期 | YYYY-MM-DD |
| 当前阶段 | S0 Intake · S1 Discovery · G1 · S2 PRD · S3 规划 · G2 · S4 分解 · S5 实现 · G3 · G4 · S6 部署 · G5 · S7 验证 · G6 · S8 沉淀 |
| 状态 | intake / defining / building / shipping / **shipped** / **rejected** / **parked** |
| 负责 | <human / agent> |
| 反馈环 | 本地 Sim / OTA / EAS / backend deploy |

## Correct Course
<!-- correct-course 时追加一条 Correction Block,不要覆盖旧计划。旧基线要保留,新基线要指向需重跑的 Gate。 -->
- [ ] Correction Block
  - 触发:
  - 旧基线:
  - 新基线:
  - 回退阶段:S0 / S1 / G1 / S2 / S3 / G2 / S4 / S5 / G3 / G4 / S6 / G5 / S7 / G6
  - 需重跑 Gate:
  - 用户确认(若 scope/风险变):☐

## S0 · 用户需求(逐字)
> <把用户原话粘这里,不改写>

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1):
- 锚点用户相关性(35–55 慢病中年男 + Ultra3/RingConn/Garmin):

## S1 · Discovery(现状勘察)
- 已有可复用(file:line):
- 缺什么:
- 硬约束 / 平台·安全边界(越早暴露越便宜):
- 链接:<discovery 工作流 run id / 报告>

## G1 · 准入裁决(governance §8 RequirementAdmission)
- first_class_objects:
- core_loop_step:
- target_surface / safety_level / autonomy_tier:
- spec_required(§8.1):
- smallest_end_to_end_slice:
- stale_surface_to_remove:
- **裁决**:☐ PASS ☐ REFRAME ☐ REJECT —— 理由:
- 用户确认:☐

## S2 · PRD
- 链接:`docs/prd/<date>-<slug>.md`
- 引用的权威 R 号(不重 spec):
- 边界(不做):
- 验收 Gate:
- 未决问题(进交付环前必清零,否则 G2 出口闸拦):
  - `[NEEDS CLARIFICATION: <写下拿不准的点,/clarify 解决后删>]`

## S3 · 规划
- 链接:`docs/plans/<date>-<slug>.md`
- 分阶段 + 反馈环路由(OTA/EAS):
- 长杆 / spike:

## G2 · 可行性 + 安全压测
<!-- 进 S4 前过「定义环一致性闸」: python backend/scripts/check_dossier_consistency.py(确定性)+ LLM 只读 /analyze(PRD↔Plan↔分解 语义自洽);不过回 S2/S3。 -->
- 评审方式:☐ council-review ☐ codex challenge ☐ discovery critics
- 硬阻断(已焊进规划):
- **待拍板分叉(STOP 问人)**:
- **裁决**:☐ PASS ☐ 需 reframe —— 用户确认:☐

## S4 · 研发任务分解
- 跨端 API 契约(`_workspace/`):
- 任务表(每条链接回规划 task · OTA/EAS · 触及层 · 需 spec?):
  - [ ] T1 …
  - [ ] T2 …
- 并发检查(`git fetch` + `gh pr list`,没被抢先):☐

## S5 · 实现
- 委托:health-harness-orchestrator
- 分支(off origin/main)/ commit:

## G3 · 测试闸
- 集成闸(CI 模式 `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`,**不 `| tail`**):passed/failed =
- main CI 真实色(`gh run list`):
- Codex 跨家族 capstone(高风险):
- **裁决**:☐ 绿 ☐ 真红→回 S5 ☐ 假红(标注)

## G4 · 安全闸
- 触发(用药/基因/化验/消息/safety/认证/写路径)?:
- 评审:☐ safety-gate ☐ safety-privacy-reviewer
- **裁决**:☐ GO ☐ BLOCK→回 S5(阻断项 + 整改):

## S6 · 部署
- 路由:☐ backend-deploy ☐ mobile-ota ☐ mobile-testflight(异步)
- 序:后端 deploy → generate-types(若改 schema)→ OTA
- 部署 SHA / 回滚点:

## G5 · 部署健康闸
- 健康分(阈值 35,低于自动回滚):/60
- prod smoke(服务 active + 路由 200/401 + 启动日志无 error + 新表/列 ssh 实查):
- **裁决**:☐ PASS ☐ 自动回滚→回 S5

## S7 · 上线验证
- 真实路径验证(curl / 健康分 / 真机 / anchor 视角):
- 结果(相关非因果措辞):

## G6 · 验证闸(人在环)
- 需求在 prod 对 anchor 用户真成立?:
- 真机/发布用户确认:☐
- **裁决**:☐ PASS(回路闭合) ☐ FAIL→回 S5/回滚

## S8 · 沉淀
- 新坑沉淀到(agent 定义 / skill / memory):
- 文档同步(ARCHITECTURE.md / doc-drift EXPECTED / parity 表):
- 状态 → **shipped**
