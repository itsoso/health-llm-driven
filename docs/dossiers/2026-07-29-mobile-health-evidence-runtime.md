# Dossier: Mobile 健康证据运行时与跨端能力统一

| 字段 | 值 |
|---|---|
| slug | `mobile-health-evidence-runtime` |
| 创建日期 | 2026-07-29 |
| 当前阶段 | G4 安全闸 |
| 状态 | implementation-complete / release-blocked |
| 负责 | product owner + Codex |
| 反馈环 | backend deploy → Mobile OTA → Mobile/Mac 真实路径对照 |

## Correct Course

- [x] Correction Block
  - 触发: 最终安全审计发现自然语言红旗/否定词漏判、单侧进行性无力未公开，
    以及新增 Guardian 规则未被 feature flag 完整关闭。
  - 旧基线: 测试措辞可通过，但“不是排尿困难”、新发漏尿/尿意消失、常见中英
    同义词会误判或漏判；flag off 仍可能改变既有 Guardian 消费面。
  - 新基线: 补充高频中英 adversarial、独立 urgent detected label、已回答项不重复
    询问，并将新规则纳入同一 disabled feature gate。
  - 回退阶段: S5
  - 需重跑 Gate: G3、G4
  - 用户确认(若 scope/风险变):不改变已确认 scope，继续执行

## S0 · 用户需求(逐字)

> “你做下对比，确保mobile的能力要赶上乃至于超越mac”
>
> “从第一性原理出发，思考最优的解决方案。重新审视整体的架构设计，确保符合我的这个理念：暂时还不需要微调，微调医疗数据不一定有效果，模型足够强，知识库和个人的上下文，包括之前说的：基因、可穿戴、检查\体检报告、饮食等差不多够了。分析的时候要有足够多的上下文，以及能够路由到足够权威的知识库，结合dedao-kbase项目，如何实现我的这个诉求。”
>
> “按照规划实施”

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1): 需要个性化健康建议的用户；Mobile
  当前只能接受泛化长答案，关键个人证据、权威来源和症状补问未形成闭环；用户需切到
  Mac 或手工补充上下文。
- 锚点用户相关性(35–55 慢病中年男 + Ultra3/RingConn/Garmin): 高；该用户的药物、
  慢病、可穿戴、化验、基因和近期症状会改变安全边界和建议可信度。

## S1 · Discovery(现状勘察)

- 已有可复用(file:line):
  - `backend/app/services/agent_executor.py`: Mobile/Mac 共用 `/agent/stream` 与
    `AgentExecutor`，已有 `TurnSnapshot`、System KB 检索和 done/meta。
  - `backend/app/twin/schema.py`: `HealthTwin` 覆盖症状、问题、药物、补剂、化验、
    基因、饮食、可穿戴和 freshness。
  - `backend/app/services/personal_evidence_matrix.py`: 可将多类 Twin 数据归一成候选
    signal 和 gap。
  - `backend/app/services/health_advice_verifier.py`: 已有部分药物、诊断、红旗、PGx、
    化验规则，可复用到自由文本最终闸。
  - `backend/app/services/system_knowledge_service.py`: 已有 reviewed/non-archived
    System KB 多路融合。
  - `mobile/components/chat/cards/SystemKnowledgeEvidenceCard.tsx`: 已有证据卡渲染基础。
- 缺什么:
  - query-specific personal context contract；
  - authority/freshness/license/applicability hard gate；
  - reviewed-only runtime boundary；
  - final free-form answer verifier；
  - truthful selected-evidence trace；
  - Mobile symptom clarification affordance。
- 硬约束 / 平台·安全边界(越早暴露越便宜):
  - 不微调、不诊断、不处方、不自动写健康数据；
  - raw Dedao/付费文本不得进入 runtime；
  - private packet 不出服务端、不进日志；
  - failed partition 不得当作无数据；
  - backend 是临床契约真源，client 只渲染。
- 链接: health-harness run `8cf7ad14fa3e`;
  `docs/_generated/harness-runs/8cf7ad14fa3e.jsonl`（本地运行账本，不提交）。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `HealthProblem`, `HealthTwin`, `SafetyGuardian`, `LeverageAction`
- core_loop_step: `Data/Twin -> Safety Gate -> Action`
- target_surface / safety_level / autonomy_tier: Backend + Mobile + Mac /
  medical_boundary_and_privacy_sensitive / suggest
- spec_required(§8.1): yes
- smallest_end_to_end_slice: 低背痛分诊 + 个人证据编译 + 审核知识包 + 最终验证 +
  Mobile 补问卡
- stale_surface_to_remove: common `knowledge_search` 内 raw Dedao fallback
- **裁决**: PASS
  - ☒ PASS ☐ REFRAME ☐ REJECT —— 理由: 直接加强核心健康闭环、明确落到既有
  Health OS 对象、避免新增平行真源，并有可验证的跨端契约。
- 用户确认:☒

## S2 · PRD

- 链接:`docs/prd/2026-07-29-mobile-health-evidence-runtime.md`
- 引用的权威 R 号(不重 spec): R1–R8
- 边界(不做): 微调、诊断/处方、raw Dedao runtime、全医学域一次迁移、DB migration
- 验收 Gate: reviewed-only、cross-surface parity、red-flag golden、privacy projection、
  verifier、Mobile interaction
- 未决问题(进交付环前必清零,否则 G2 出口闸拦): 无阻断项

## S3 · 规划

- 链接:`docs/plans/2026-07-29-mobile-health-evidence-runtime.md`
- 分阶段 + 反馈环路由(OTA/EAS): P0 reviewed-only → P1 personal compiler → P2
  authority pack → P3 verifier → P4 Mobile；backend deploy 后走 Mobile OTA，无原生改动。
- 长杆 / spike: `AgentExecutor` 单一注入/出口 choke point；System KB authority metadata；
  Mobile follow-up choice 接现有发送链路。

## G2 · 可行性 + 安全压测

- 评审方式:☐ council-review ☒ codex challenge ☒ discovery critics
- 硬阻断(已焊进规划):
  - raw Dedao runtime route 无条件移除；
  - authority metadata 不完整即 fail closed；
  - mandatory context 只能 evidence-or-gap；
  - final verifier 失败即 deterministic safe fallback；
  - public manifest 做隐私投影；
  - `clarify`/`safe_fallback` 不调用模型；`sufficient` 也只发布已批准 claim summary；
  - low-back candidate pack 全量 serving hold + 新 Guardian 行为受同一 flag 门控；
  - backend-first deploy，旧 client 可忽略新增字段。
- **待拍板分叉(STOP 问人)**: 无；用户已确认“不微调、强模型 + 上下文 + 权威 KB”
  的架构边界。
- **裁决**: PASS
  - ☒ PASS ☐ 需 reframe —— 用户确认:☒

## S4 · 研发任务分解

- 跨端 API 契约(`_workspace/`): optional `health_evidence_manifest` in SSE done,
  persisted message meta, and `health_evidence` card descriptor.
- 任务表(每条链接回规划 task · OTA/EAS · 触及层 · 需 spec?):
  - [x] T1 reviewed-only knowledge boundary
  - [x] T2 evidence contracts + intent envelope
  - [x] T3 personal context compiler
  - [x] T4 authority router + held low-back candidate/eval pack
  - [x] T5 AgentExecutor single-turn integration
  - [x] T6 sufficiency + final verifier
  - [x] T7 Mobile evidence/clarification UI
  - [x] T8 parity/golden/integration/safety review
  - [ ] T9 backend deploy → Mobile OTA → production verification（G4 BLOCK）
- 并发检查(`git fetch` + `gh pr list`,没被抢先):☒
  - overlap noted: PR #221 claim honesty and PRs #214/#216 medical safety; this
    implementation avoids cherry-picking unrelated branches and will run overlap review.

## S5 · 实现

- 委托: health-harness-orchestrator contract + TDD + parallel discovery agents
- 分支(off origin/main)/ commit: `codex/mobile-health-evidence-runtime` off
  `origin/main@b3e15300c`;实现提交以该分支 head 为准，不代表已部署
- 实现边界:
  - 这是低背痛 golden safety slice + 可复用 runtime，不是全医学域完成；
  - low-back compiler 用症状/问题/用药/过敏/慢病安全核心和查询相关可穿戴，
    正确排除不相关基因、化验、饮食；其他域后续各自扩 pack；
  - 个人事实影响 risk/sufficiency/applicability/detected flags/补问，但本 slice
    不发布自由生成的个性化因果解释；
  - `sufficient` 模型输出只用于选择已批准 claim IDs，最终正文由 verifier
    确定性渲染 claim summaries；`clarify`/`safe_fallback` 绕过模型；
  - continuation 绑定父 assistant message + 可选 turn ID；malformed/stale 时保留
    当前用户文本，不静默替换；
  - candidate pack 为自动化官方来源校验结果，不是独立临床审核结论。

## G3 · 测试闸

- 集成闸(CI 模式 `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`,**不 `| tail`**):
  - 本轮 CI-mode health/knowledge/delivery suite: 268 passed；
  - 本轮 PostgreSQL broad related suite: 314 passed；
  - 最终 safety adversarial/runtime/context 子集: 125 passed；
  - 本轮 Mobile 相关回归: 174 passed；
  - TypeScript、Ruff、targeted ESLint（0 errors）、seed integrity、
    dossier consistency: PASS；
  - system map 已从冻结代码重生成；doc drift: PASS。
- main CI 真实色(`gh run list`): pending before deploy
- Codex 跨家族 capstone(高风险): 多 agent 独立 code/release/delivery audit 完成
- **裁决**:☒ 绿 ☐ 真红→回 S5 ☐ 假红(标注)

## G4 · 安全闸

- 触发(用药/基因/化验/消息/safety/认证/写路径)?: 症状、用药、基因、化验、个人健康
  context、医学知识、最终消息；不新增写路径
- 评审:☒ safety-gate ☒ safety-privacy-reviewer
- 技术安全复核: GO；raw Dedao fallback、持久化/replay/history 绕过、正文 SHA
  绑定、结构化 continuation、全包 hold、自然语言 adversarial 均已独立复验。
- 医学内容复核: 尚无独立、具资质临床专业人员签署。
- **裁决**:☐ GO ☒ BLOCK→停在 G4
  - 阻断项仅为独立临床 sign-off。feature flag 保持 OFF，low-back 的 claims/entity/
    evals 全量 serving hold，新 Guardian 规则在 flag OFF 时 inert。

## S6 · 部署

- 路由(获 G4 GO 后):☒ backend-deploy ☒ mobile-ota ☐ mobile-testflight(异步)
- 序:后端 deploy → generate-types(若改 schema)→ OTA
- 部署 SHA / 回滚点: 未执行；G4 BLOCK 禁止部署

## G5 · 部署健康闸

- 健康分(阈值 35,低于自动回滚): NOT RUN
- prod smoke(服务 active + 路由 200/401 + 启动日志无 error + 新表/列 ssh 实查): NOT RUN
- **裁决**:☐ PASS ☒ BLOCKED BY G4

## S7 · 上线验证

- 真实路径验证(curl / 健康分 / 真机 / anchor 视角): NOT RUN；不得绕过 G4
- 结果(相关非因果措辞): 无生产结果

## G6 · 验证闸(人在环)

- 需求在 prod 对 anchor 用户真成立?: 未验证
- 真机/发布用户确认:☐
- **裁决**:☐ PASS(回路闭合) ☒ BLOCKED BY G4

## S8 · 沉淀

- 新坑沉淀: clinical content workflow review 不等于 independent clinician
  release；feature flag 必须覆盖所有新行为而不只主 runtime。
- 文档同步(ARCHITECTURE.md / doc-drift EXPECTED / parity 表): 完成；
  system-map regenerate + drift check PASS
- 状态 → **shipped** only after G6
