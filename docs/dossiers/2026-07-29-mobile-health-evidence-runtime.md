# Dossier: Mobile 健康证据运行时与跨端能力统一

| 字段 | 值 |
|---|---|
| slug | `mobile-health-evidence-runtime` |
| 创建日期 | 2026-07-29 |
| 当前阶段 | 本地 G3/G4 已通过 → 干净 main 集成验证与 CI |
| 状态 | release-candidate / not-deployed |
| 负责 | product owner + Codex |
| 反馈环 | backend deploy → Web deploy → Mobile OTA → Mobile/Mac 真实路径对照 |

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
- [x] Correction Block — release basis and serving scope
  - 触发: 用户明确要求不要因缺少额外临床签署而阻断已经知识库筛选的知识，
    随后确认保留 low-back 知识包与 `symptoms.cauda_equina_warning`，以权威
    知识筛选 + product-owner 确认为发布依据。
  - 用户原话: “不要阻断，这些知识是知识库经过筛选的，得到的知识是有保障的”
  - 澄清确认: Codex 明确复述“保留知识包/规则、取消仅因缺少独立临床签署而产生的
    发布阻断；保留 generic hold，只做 runtime-only 放行，并重跑 G4 后部署/OTA”；
    用户回复“是的”。
  - 旧基线: 整包通用 serving hold；G4 仅因没有独立临床 sign-off 而 BLOCK。
  - 新基线: 不宣称独立临床 sign-off；manifest 如实记录
    `reviewer_role=product_owner`、`clinical_signoff=not_claimed`。整包仍对通用
    搜索/详情/旧知识工具隔离，精确五条 claim 只在受控 health-evidence runtime
    通过 allowlist + T1 来源 + applicability + artifact + verifier + delivery
    全部检查后使用。
  - 审计发现后的附加修正: 分享节选必须提交服务端 durable message IDs，不能把
    系统健康答复压成 `/shared/create-text`；红旗措辞、ACR/WHO locator 和
    serious-cause 正负例必须在重新发布前原子修正。
  - 回退阶段: S2/S5
  - 需重跑 Gate: G2、G3、G4、G5、G6
  - 用户确认:☒
- [x] Correction Block — final privacy and temporal-safety review
  - 触发: fresh 独立审计发现两项 NO-GO：selected-agent share 的隐藏支持问题仍可
    经 `conversation.title` 泄露到公开正文/metadata；稳定既往排尿困难的跨片段
    regex 会吞掉“今天加重/现在尿不出来”等新发马尾风险。
  - 旧基线: 只过滤 `private_support` 消息正文；以宽泛跨片段替换消除既往泌尿
    症状。
  - 新基线: 所有 selection share 使用服务端中性标题，GET 同时中和历史快照标题；
    泌尿红旗按每次症状提及解析既往、已缓解、持续、复发、否定与当前状态。只有明确
    既往/已停止且没有后续当前变化的表述可排除；尿潴留、失禁、直接漏尿词形及
    新发/持续/复发始终覆盖既往描述。
  - 回退阶段: S5
  - 需重跑 Gate: G3、G4
  - 当前状态: 已解决。`2c5482d9b`；定向 206、PostgreSQL 跨层 417、独立
    intent/discriminator/Guardian 三方矩阵 109/109 全绿。
- [x] Correction Block — persisted personalized-risk projection
  - 触发: fresh spec→code 审计复现 query-only 为 medium、但冻结 Twin/Guardian 将
    生成 turn 提升为 high/emergency 后，历史/重放/分享/Mac 读取会因 exact risk
    equality 错误撤销这条有效安全答复。
  - 旧基线: 读取时只重算 `source_query` 风险，并要求与 sealed manifest 风险完全
    相等。
  - 新基线: query-only 风险是不可降级的下界；通过 manifest + verification digest
    密封的生成风险可以更高（来自同一 frozen Twin/SafetyGuardian），但不能低于
    当前 query 明示风险。artifact、正文 SHA、intent 和引用校验继续 fail closed。
  - 回退阶段: S5
  - 需重跑 Gate: G3、G4
  - 当前状态: 已解决。`b6a403aab`；query 风险为下界，sealed Twin/Guardian
    风险可更高但不可更低，未知/tampered/re-held 均 fail closed。
- [x] Correction Block — truthful continuation and context minimization
  - 触发: 续问组级 “yes” 被错误扩写成用户确认了全部红旗；普通腰痛无差别注入
    wearable，且紧急回合仍携带可选个人上下文。
  - 旧基线: 组级肯定生成具体症状合取；个人上下文按域宽泛注入。
  - 新基线: 组级肯定只保留“该组至少一项”为真的析取语义；普通/运动/恢复问题分别
    选择零、活动、恢复数据，缺口和冲突按 query 绑定；high/emergency 只保留安全
    核心，省略可选 wearable/gap/conflict。
  - 回退阶段: S5
  - 需重跑 Gate: G3、G4
  - 当前状态: 已解决。`dcc70eec0`、`8aa9e7733`、`1d0bcc943`、
    `3bbc3e1fa`、`2232ff2d8`；fresh G4 对普通/运动/恢复/泌尿/急症矩阵 GO。
- [x] Correction Block — PostgreSQL release-gate truth
  - 触发: fresh PostgreSQL G3 暴露 ORM 将 production `tsv` 声明成 Text、测试把
    SQLite FTS 表现硬编码到 PostgreSQL、46 字符审计 op 写入 `VARCHAR(40)` 返回
    500，以及共享 session 测试夹具制造 idle transaction。
  - 旧基线: SQLite 全绿但没有执行相同的 production 类型/长度/事务语义。
  - 新基线: `KBDocument.tsv` 在 PostgreSQL 编译为 `TSVECTOR`、SQLite 为 `TEXT`；
    FTS 测试先 reindex 并按方言验证；发布预演审计使用 27 字符 schema-safe 常量；
    compaction 测试使用独立 session 并真实关闭。
  - 回退阶段: S5
  - 需重跑 Gate: G3、G4
  - 当前状态: 已解决。`8c6f75a80`、`96dd7b352`；受影响 PostgreSQL 与 SQLite
    套件各 70/70，全套结束后 `idle in transaction=0`。
- [x] Correction Block — runtime-only KB 与持久激活事务
  - 触发: 发布演练发现仅靠进程内 feature flag、先写 live `.env`、SSH 失败后立即
    并发回滚，以及 frontend-only checkout 共享仓库，都可能让实际服务状态与发布
    工具声称的状态分叉；通用 System KB read surface 也没有共享一份精确 serving
    predicate。
  - 旧基线: generic/runtime 检索条件分散；导入和隔离可以交错；服务重启成功被近似
    当成全部进程已取得同一 flag；远端结果不明时本地清理锁并尝试第二个事务。
  - 新基线:
    - generic serving 统一为 active + reviewed + 排除完整 held pack；health-evidence
      runtime 统一为 active + reviewed + exact five-claim allowlist；
    - import/quarantine/verifier 共享 PostgreSQL mutation lock，导入在首次 DB 操作前
      取锁；semantic probe 以 `metadata.input` 为唯一可执行输入，逐 case 严格 top-1，
      并用 nested savepoint 保持外层 advisory transaction lock；
    - live base `.env` 永远是规范 `false`。受控激活先以 runtime-only systemd drop-in
      做 canary，再原子、fsync 地提交含 commit/guard hash 的 durable authorization，
      去掉 canary 后重启并逐 cgroup PID 证明 `true`；
    - 任意通用 mutation 先停 socket/backend/Celery，证明 inactive，再撤销 durable/
      runtime 授权并 fsync，最后才原子安装候选 `false` env、重启并逐 PID 证明
      `false`；所有 crash prefix 因而只能重启到完整旧文件或完整新文件且不会越过
      `false`；
    - 远端 SSH/HUP/INT/TERM 结果不明确时保留 release lease 与 stage，禁止并发回滚；
      rollback 只有在 schema/auth/quarantine 和全部 writer `flag=false` 终态证明后才
      输出成功哨兵；
    - frontend-only 只允许在服务器已是 exact expected SHA 且 checkout clean 时
      `npm ci`/build/PM2 restart，不 checkout、不触碰 backend/Celery/运行时授权。
  - 回退阶段: S3/S5
  - 需重跑 Gate: G3、G4、G5、G6
  - 当前状态: 已解决。`832d73256`；冻结发布事务 69/69，两个独立 G4 复审均 GO。

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
  authority pack → P3 verifier → P4 Mobile；backend 与 Web deploy 后走 Mobile OTA，
  无原生改动。
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
  - low-back pack 对通用 serving 全量隔离；精确五条 reviewed claim 仅由内部
    health-evidence runtime allowlist 放行；新 Guardian 行为受同一 flag 门控；
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
  - [ ] T9 backend deploy → Web deploy → Mobile OTA → production verification
    （local G3 与 G4 已通过；待干净 main 集成 CI）
- 并发检查(`git fetch` + `gh pr list`,没被抢先):☒
  - overlap noted: PR #221 claim honesty and PRs #214/#216 medical safety; this
    implementation avoids cherry-picking unrelated branches and will run overlap review.

## S5 · 实现

- 委托: health-harness-orchestrator contract + TDD + parallel discovery agents
- 分支(off origin/main)/ commit: `codex/mobile-health-evidence-runtime` off
  `origin/main@b3e15300c`;release-hardening code head
  `832d7325615fdc810bc50112377cf774448a078f`，
  不代表已合入 main 或部署
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
  - claim release basis 为 T1 官方来源/边界审查 + product-owner 明确确认；
    `clinical_signoff=not_claimed`，不虚构独立临床审核结论；
  - 历史、模型上下文、Desktop、cloud facade、pregen 与公开 agent share 共用
    当前 release policy 投影；Mobile/Web 节选分享只提交 conversation/message IDs，
    不接受客户端上传 answer/proof/meta。

## G3 · 测试闸

- backend CI-equivalent SQLite:
  - 最新 20 文件相关矩阵 692 passed / 3 skipped / 190 warnings；
  - release policy / quarantine / Desktop / genetic refs / eval / mutation-lock
    提交前焦点复跑 63 passed / 3 skipped；
  - Dedao consumer 的 60 项因 sandbox 禁止 loopback bind，改在授权回环环境单独
    复跑全绿。
- backend PostgreSQL:
  - release-candidate 首轮 696/700；4 项真红回 S5；
  - 2 项为 FTS 方言/reindex 测试契约，2 项复现 `KBAudit.op VARCHAR(40)` 真实 500；
  - 修正后受影响 System KB + persisted-revocation 套件 70/70，且无遗留事务；
  - temporal intent/Guardian/authority 跨层套件 417/417；
  - runtime-only exact contract / semantic top-1 / mutation-lock 真实 PostgreSQL
    复验 10/10；向量 SQL 错误后外层 advisory lock 仍阻塞并发 importer。
- clients:
  - Mobile 8 suites / 202 tests；TypeScript 0 error；lint 0 error；
  - Web 2 suites / 20 tests；TypeScript 0 error；lint 0 error；
  - 无 native/plugin/SDK/lockfile diff，发布路由为 OTA。
- release transaction:
  - activation/deactivation/deploy/rollback 69/69；
  - `bash -n` 三个 shell 入口、Ruff、`git diff --check` PASS；
  - 两次独立复审前后六个冻结发布文件 SHA256 不变。
- static/data: Ruff、`git diff --check`、seed integrity
  （460 claims / 247 entities / 3318 relations）PASS。
- system-map/doc drift: 从当前冻结代码重新生成，`check_doc_drift.py` 与
  `check_dossier_consistency.py` 均 PASS。
- main CI 真实色: 待与最新 `origin/main` 集成、双端重新生成 OpenAPI types 后触发。
- **裁决**: local candidate ☒ 绿；最终 G3 ☐ 绿 ☒ PENDING integrated-main CI

## G4 · 安全闸

- 触发(用药/基因/化验/消息/safety/认证/写路径)?: 症状、用药、基因、化验、个人健康
  context、医学知识、最终消息；不新增健康数据写路径
- 先前裁决: 技术安全 GO、仅因没有独立临床 sign-off 而 BLOCK。
- 产品修正: product owner 明确接受 T1 权威知识筛选作为本次窄域发布依据；
  不要求也不宣称独立临床签署。该产品决策不豁免代码、来源、适用性、隐私、
  撤销或红旗测试。
- fresh safety/privacy review:
  - `2c5482d9b` 对 generic hold/runtime-only allowlist、五 claim
    T1/artifact/applicability、风险下界、全 read-surface 撤销、分享标题/IDs、
    truthful continuation、上下文最小化和 109 组红旗时态给出 GO；
  - `96dd7b352` exact-delta 复审确认只缩短 schema-safe audit op、删除未使用变量并
    修正测试方言/事务，不改变 clinical/privacy 语义。
  - `832d73256` 的 frozen semantic review 与 release/activation 双重复审均 GO；
    query-agnostic 全五 claim falsification 被 4/5 case 拒绝，未发现假绿、并发
    rollback、非原子 env 替换、frontend-only 误停 backend 或 secrets/privacy 泄露。
- **裁决**:☒ GO ☐ NO-GO→回 S5

## S6 · 部署

- 路由(获 integrated-main CI 绿后):☒ backend-deploy（backend + Web） ☒ mobile-ota
  ☐ mobile-testflight
- 序:干净 main 集成 → Mobile/Web OpenAPI types 与 system map 重生成 →
  integrated verification/CI → 以 base flag=false 部署后端 → Web deploy →
  Linux systemd/cgroup 故障演练 → `--activate-health-evidence` 受控持久启用 →
  production semantic smoke → OTA
- TestFlight 判断: 当前仅 Python/JSON/TS/TSX/API 变更，无 native/plugin/SDK/runtime
  变更；按发布契约走 OTA，不浪费 TestFlight build。若最终 diff 出现原生变更再改路由。
- 部署 SHA / 回滚点: 未执行；等待干净 main 集成与 CI

## G5 · 部署健康闸

- 健康分(阈值 35,低于自动回滚): NOT RUN
- prod smoke(服务 active + 路由 200/401 + 启动日志无 error + 新表/列 ssh 实查): NOT RUN
- Linux 实机硬条件: systemd drop-in precedence、cgroup v2 全部 uvicorn/Celery/beat
  子进程 flag 一致性、durable commit/revoke/candidate rename 断电前缀、SSH/HUP
  断连租约、生产文件系统 `sync -f`/`mv -fT`/目录 fsync 与 rollback 终态证明均
  NOT RUN
- **裁决**:☐ PASS ☒ NOT RUN

## S7 · 上线验证

- 真实路径验证(curl / 健康分 / 真机 / anchor 视角): NOT RUN
- 结果(相关非因果措辞): 无生产结果

## G6 · 验证闸(人在环)

- 需求在 prod 对 anchor 用户真成立?: 未验证
- 真机/发布用户确认:☐
- **裁决**:☐ PASS(回路闭合) ☒ NOT RUN

## S8 · 沉淀

- 新坑沉淀: clinical content workflow review 不等于 independent clinician
  sign-off，release record 必须如实写实际批准角色；feature flag 必须覆盖所有新
  synthesis 行为，但历史/分享撤销校验不能被 flag 关闭；系统生成健康答复不得走
  无 provenance 的 plain-text share。高风险运行时启用不是“把 `.env` 改成 true”
  而是独立、持久、可恢复的事务；远端结果不明确时必须保留租约和现场，不能用第二个
  rollback 猜测第一个事务的状态。
- 文档同步(ARCHITECTURE.md / doc-drift EXPECTED / parity 表): 已完成；system-map
  从冻结代码重新生成，doc drift 与 Dossier consistency 均 PASS
- 状态 → **shipped** only after G6
