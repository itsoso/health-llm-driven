# Dossier: Mobile 健康证据运行时与跨端能力统一

| 字段 | 值 |
|---|---|
| slug | `mobile-health-evidence-runtime` |
| 创建日期 | 2026-07-29 |
| 当前阶段 | replacement exact-SHA CI |
| 状态 | local G3/G4 GO；prod=`85fd0a69...`, flag=false、四服务稳定；exact-SHA CI 前 activation/OTA 继续阻断 |
| 负责 | product owner + Codex |
| 反馈环 | backend/Web → 受控 activation → semantic smoke → Mobile OTA → 跨端对照 |

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
- [x] Correction Block — integrated-main CI truth
  - 触发: 首轮 main CI run `30499545219` 出现四个已完成红灯；G3 立即拒绝，未进入
    部署。失败项为 `type-drift`、`backend-quality`、`backend-test-d` 和
    `backend-test-agent-executor-i-z`。
  - 旧基线:
    - client types 由本地陈旧 FastAPI/OpenAPI 依赖生成，与 CI 的锁定依赖输出不同；
    - 两组测试仍要求旧行为：原样释放未验证的历史健康回答，以及 env 直传/live
      restart/guard 前 seed；
    - 修改 `agent_executor.py` 后没有在提交记录里附上显式 live LLM 证据。
  - 新基线:
    - Mobile/Web types 均恢复为锁定依赖生成的同一 blob
      `031b9b775c269bfba6ba41cd7d250310d5c7c4c6`；
    - stale tests 改为锁定当前更严格契约：未验证历史健康回答必须撤销；env 先备份并
      只上传 root-only candidate；guard restart/contract/rollback floor 通过后才能
      seed；env-only 去激活必须逐 cgroup PID 证明 `flag=false`；
    - 显式 live gate 首次因本机生产 PostgreSQL role 不存在而在出网前失败，且
      OpenAI fallback 429；该次不算证据。按评测脚本声明的无 DB 边界改用
      `APP_ENV=development`，保持同一 TokenPlan 模型、prompt、数据集和 scorer，
      第二次真实调用通过：invariants 12/12、health-agent core 50/50、
      orchestrator 5/5（平均 0.94）、trajectory contract 12/12、goldens 9/9，
      无 regression。
  - 修复 commit: `f89ed2d5`；本地复验 agent-executor shard 329/329、d shard
    388 passed + 1 skipped、release transaction 69/69、双端 TypeScript 0 error、
    Ruff/diff check PASS。
  - 回退阶段: G3
  - 需重跑 Gate: G3 replacement CI；全绿后才可进入 G5/G6
  - replacement CI: run `30504712139` 对精确 main
    `6e449b176d3235d52a933968816396cc33c0089c` 全绿；临时 repo variable
    `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 在 CI 终态 success 后立即删除，随后
    `gh variable get` 返回 not found。
  - 当前状态: 已解决。
- [x] Correction Block — first-introduction flag bootstrap
  - 触发: 首次 production backend staged deploy 在完成数据库备份、234 表恢复演练
    与站外加密归档后，被 deactivation transaction 拒绝：
    `health-evidence 去激活结果不明确；无法证明服务已停止`。G5 立即停止；没有
    checkout、migration、KB import、服务重启、运行时激活或 OTA。
  - 现场证明: 远端仍为回滚提交 `ad85cd667cb415a3cc1dc298633c75998856f68e`；
    live `.env` 对新 flag 为 0 个 assignment，root-only candidate 唯一规范为
    `false`；socket/backend/worker/beat 全 active；durable authorization 与
    `/run` authorization 均 absent；发布锁与 stage 按设计保留。
  - 根因: 首次引入 flag 的旧生产版本没有该 assignment，但事务要求旧 live base
    必须已经显式 `false`，又只允许该事务原子安装 `false` candidate，形成
    pre-mutation bootstrap Catch-22。
  - 新基线: 只允许一次严格 legacy bootstrap：candidate 必须唯一 `false`、live
    必须完全 unset、每个 cgroup PID 也必须 unset、durable/runtime/drop-in（含
    dangling symlink）必须全部 absent。取得租约后先停 socket 与全部 writer 并
    复证，再原子安装/文件 fsync/目录 fsync 显式 `false`；rename 前后均重验租约。
    任一 candidate sync、lease、PID、授权或 symlink 检查失败，保持旧 env 且隔离
    全部服务。已有显式 `false` 路径继续保持先 revoke+fsync、后换 candidate。
  - 回归: deploy transaction 60/60、完整 deploy/activation/rollback 86/86；覆盖每个单点 durable/runtime/三 unit
    drop-in、dangling file/dir symlink、三 unit 主进程、同 cgroup child、显式
    `false` assignment、candidate sync 失败与 rename 前丢 lease。完整 release
    独立 crash-prefix 复审 GO；Shell syntax、Ruff、diff check、system-map 与
    92 份 Dossier consistency 均 PASS。replacement CI 待本修复提交后重跑。
  - 回退阶段: G5 → S5/G3/G4；禁止带 BLOCK 继续 activation/OTA。
- [x] Correction Block — production schema drift 与可恢复发布链
  - 触发: bootstrap 修复提交 `1eb8c2f8bcc904144b57beefceefc34cb8f40667`
    的 main CI run `30507073580` 43 个 job 全绿、临时
    `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 已确认删除后，正式 backend deploy 在
    guard health Gate 输出 `60/60 FAIL`；自动回滚随后被完整 runtime schema
    probe 拒绝，缺少 `plan_items.weather_condition_tag`，四个服务按设计保持
    inactive，发布锁与 stage 保留。
  - 根因拆分:
    - `weather_condition_tag` 自 `0908e9db6` 起同时存在于 ORM 与 legacy SQL，
      但 SQL 位于 `backend/migrations/`，而生产只执行
      `backend/migrations/managed/`；CI 使用 `Base.metadata.create_all` 建理想库，
      因而长期掩盖 production migration lineage drift；
    - `60/60 FAIL` 只能来自新增 `agent_runtime_circuit` 硬闸，但旧 deploy 日志只
      打印 total/pass，未保留当时的 circuit detail。恢复后用同一新评分逻辑复跑为
      `active:none:generation=4:ack=4`、`critical_failures=[]`、`60/60 PASS`，
      因此不把当时状态臆断成 paused 或 unavailable。
  - 受控恢复:
    - 保留 release lease 与全部 writer inactive；使用 root-only 独立 migration
      role 对仓库内 hash `ce1cdf78015f...` 的既有幂等 SQL 做单事务执行，新增
      nullable `VARCHAR(20)` 并确定性回填 2 行；
    - staged full schema probe 通过 199 表后才重跑 hash-verified rollback runner；
      得到精确哨兵 `ROLLBACK_OK commit=ad85cd66... kb_quarantine=passed
      schema_probe=passed auth_probe=passed services=active process_flag=false`；
    - 随后复证 health 200、auth 401、四服务 active、全部 writer PID 唯一
      `flag=false`、runtime-only targets 11/matched 0、circuit 4=4，并精确清理
      本次 stage/bundle/lock。生产恢复旧 SHA，新功能没有被激活或 OTA。
  - 持久修复:
    - PG/SQLite 成对 managed reconciliation migration，legacy 缺列升级、六类回填、
      ledger 与二次 skip 均有测试；
    - backup 后、任何 env/停服变更前，用 candidate stage 的 hash-verified probe
      验证当前生产回滚 SHA；只有 HEAD/clean/schema/lease 前后与精确 marker 全部
      通过才记录全局 rollback point，且不把 `.env` 当 shell source；
    - guard 顺序固定为 stop socket/writers → checkout/install → release-token recheck
      → managed migration → full runtime schema probe → release-token recheck → restart；
    - SSH 非零继续视为远端 transaction unknown，保留 delegated lease/stage，
      禁止并发 rollback；Agent circuit 将 query/session-close 异常统一收敛到有限、
      脱敏重试，paused/generation mismatch 仍立即硬失败，日志新增脱敏后的
      critical/detail。
  - 回归: release deploy/rollback/activation 92/92；managed migration +
    circuit + runtime schema 56/56；health-score 18/18；Shell syntax、Ruff、
    diff check PASS。
  - 回退阶段: G5 → S5/G3/G4；replacement CI 和重新部署全绿前继续禁止
    Web/activation/OTA。
- [x] Correction Block — health-score 直接执行 import root
  - 触发: incident remediation `5df2cfde36b233eabcabde8d25cb313750e4212e`
    的 CI run `30510213024` 43/43 全绿后，backend deploy 完成数据保护、旧回滚点
    199 表兼容预检、managed reconciliation migration、启动前 schema probe 与
    exact-SHA 验证；部署健康硬闸随后精确报告
    `agent_runtime_circuit=unavailable:ModuleNotFoundError:attempts=3`。
  - 终态: 自动 rollback runner 返回精确
    `ROLLBACK_OK commit=ad85cd66... kb_quarantine=passed schema_probe=passed
    auth_probe=passed services=active process_flag=false`；生产仍为旧 SHA、flag=false，
    未继续 Web、activation 或 OTA。
  - 根因: `python scripts/system_health_score.py` 把 `backend/scripts` 而不是
    `backend` 作为首个 import root；旧评分维度仅用标准库，新增
    `app.services.agent_runtime_rollout` 后才暴露。pytest 的项目路径注入掩盖了真实
    direct-script 契约。
  - 修复: health-score executable 从自身绝对路径显式加入 `backend` 根目录；新增
    清空 `PYTHONPATH`、任意 cwd 直接执行的 subprocess 回归，已严格 RED 复现并
    GREEN，且继续断言电路 detail 不得降级为 ModuleNotFoundError。
  - 回归: migration + circuit + runtime schema 57/57、health-score 19/19；
    independent fresh review GO，Ruff、diff check、Dossier consistency PASS。
  - 回退阶段: G5 → S5/G3/G4；该最小修复本地闸门与精确 SHA CI 全绿前继续禁止
    重新部署、Web、activation/OTA。
- [x] Correction Block — transient systemd Git dubious ownership
  - 触发: import-root 修复 `1a831aa49670ef04859b30cb1b497166bc3187b6`
    的 CI run `30511389923` 43/43 全绿；backend 重部署通过两次 60/60、
    exact-SHA、199 表 probe、staged KB contract 与 skills 22/22，Web 73 页构建
    通过。受控 activation 随后在 transient systemd unit 内被 Git
    `detected dubious ownership in repository at '/opt/health-app'` 阻断；
    同一未显式声明 safe-directory 的 revision proof 也阻断自动 deadman recovery，
    runner 正确输出 BLOCKED 并隔离四服务、保留 lease/stage。
  - 现场与恢复: HEAD 仍为 candidate、工作树 clean、live flag 唯一 false，
    durable/runtime/drop-in 全 absent。保持既有 lease，用原 hash-verified staged
    runner `--recover-if-unverified` 并仅注入进程级
    `safe.directory=/opt/health-app`，得到精确
    `HEALTH_EVIDENCE_DEADMAN_RECOVERED commit=1a831aa4... flag=false
    health=passed contract=staged services=active`；未授权 feature。
  - 根因: SSH root 环境已有 Git trust，但 transient systemd 环境不继承该隐式全局
    配置；activation/recovery 的 revision proof 错把外部环境当作契约。
  - 安全压测修正:
    - 第一版只加 exact `safe.directory`；fresh review 用真实恶意
      `core.fsmonitor` 证明 root `git status` 会执行 repo-local 命令，REJECT。
    - 第二版清空进程环境并禁用 fsmonitor/hooks；fresh review 又以
      `.gitattributes` + repo-local `filter.<name>.clean` 实证篡改文件可被过滤器
      伪装为 clean，同时执行任意命令；且 production Git 2.34.1 不接受该版
      command-scope safe-directory，REJECT。
    - 生产只读 ownership 审计还确认 `/opt/health-app` 为
      `UID 501:staff:755`（`%U` 因无对应账户显示 `UNKNOWN`）；4,655 个 tracked
      path 中 274 个仍非 root，15,225 个工作树目录中 350 个非 root。仅检查
      `.git` 的方案无法闭合
      stat→Git/服务启动间 TOCTOU，REJECT。
    - 第三版虽隔离 repo-local config，却复制 live `.git/index`；fresh review
      实证 `assume-unchanged`、`skip-worktree` 和同尺寸 racy stat 均可让被篡改的
      tracked 文件返回 clean，REJECT。
  - 当前候选修复: staged runner 与 deploy 外层 proof 不再让 Git 读取真实
    `.git/config/index`。它们在 root-only 临时目录构造最小 Git metadata，用
    expected SHA 固定 HEAD，并以隔离 `read-tree` 从 expected commit 新建无
    semantic flag/stat cache 的 proof index；Git proof 禁止 optional write，
    引用 ownership 已验证的真实 object store，并通过 root-only global config
    声明 exact safe-directory；同时显式 `--git-dir/--work-tree`、
    禁用 system attributes/config、replace objects、optional lock、fsmonitor 与
    hooks。运行前要求 repo root、整个 `.git`、非 symlink tracked path 及其
    ancestors root-owned 且不可 group/world 写；tracked symlink 内容由无 filter
    status 校验，其 parent 不可写，checkout normalization 另以 `chown -h` 固定
    owner。proof 还拒绝 symlink metadata、worktree config 与 alternate object
    store。远端 checkout 只规范化 `.git`、tracked paths 及 ancestors，不递归
    改动 ignored `.env`/venv/runtime data。
  - 故障注入: 恶意 same-size clean filter 已严格 RED（误放行且 marker 被执行）→
    GREEN（70/BLOCK 且 marker absent）；`assume-unchanged`/`skip-worktree` 均
    RED→GREEN；fsmonitor、`core.worktree` clean alternate、writable config 和
    non-root repo 均有回归。可执行 target-recorder 证明 normalization 未触及
    `backend/.env`、uploads、tmp、node_modules。完整 release/activation 回归
    106/106、两路 fresh review、production Git 2.34.1 read-tree proof、Ruff、
    shell/diff/doc drift/Dossier consistency 均通过；exact-SHA main CI、重新部署、
    activation 与 OTA 仍待完成。
  - 回退阶段: G5 → S5/G3/G4；完整 activation/release 回归、fresh review 与新
    main CI 全绿前禁止再次 activation/OTA。
- [x] Correction Block — Celery Beat 可变状态越过 immutable checkout 边界
  - 触发: isolated-Git 修复 `85fd0a69adf9e9cf1ee6010e416b4e4039e1cc2a`
    的 exact-SHA CI run `30515848406` 43/43 全绿，临时 repo variable
    `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 在 CI success 后已删除。backend deploy
    随后完成约 41 MB backup、234 表恢复演练、站外加密归档、199 表 schema probe、
    两次 60/60、exact SHA、KB 11/11 与 skills 22/22，脚本报告成功；但独立
    postdeploy 复查发现 `celery-beat` 正处于每约 8 秒重启一次的 crash loop。
    因此脚本成功不构成 G5 PASS，立即 REJECT，未进入 activation/OTA。
  - 根因: ownership normalization 把 tracked `backend/data` 从运行账号专有目录
    收紧为 `root:root:0700`，旧 unit 又把 Celery Beat shelf 写在
    `backend/data/celerybeat-schedule`。这既让 beat 得到 `PermissionError`，也让
    health-app 无法读取同目录内受版本控制的基因/System KB seeds；原终态证明只在
    crash loop 的短暂 active 窗口采样，未跨越 unit 的 `RestartSec=5s`，形成假绿。
  - 即时恢复: 保持 production exact SHA 与 base flag=false，把
    `backend/data` 临时恢复为 `health-app:health-app:0700` 后重启 beat，并跨越
    RestartSec 证明 PID/restart count 稳定。feature 从未授权；该临时权限不作为
    最终架构，必须由 replacement backend deploy 覆盖。
  - 新基线:
    - checkout 内 tracked 目录统一 `root:root:0755`，tracked 文件按 Git mode
      确定为 `0644`/`0755`；ignored runtime 文件不被 normalization 触碰；
    - Celery Beat shelf 迁到 systemd `StateDirectory` 管理的
      `/var/lib/health-app/celery-beat`，runtime drop-in 与候选 commit 一起 hash
      staging、systemd 249 verify、原子安装并校验 effective `ExecStart`；
    - 只迁移/清理精确 allowlist 的 shelf 后缀，拒绝 symlink 与 group/world
      writable 文件；必须先在新目录看到 health-app-owned state，再删除 legacy；
    - deploy、activation、deactivation 与 rollback 的服务终态证明均跨 7 秒双采样
      `ActiveState/SubState/Result/MainPID/NRestarts/ActiveEnterTimestampMonotonic`
      和 cgroup flag；PID、restart count 或 activation timestamp 有任何变化即
      fail closed。
  - 回归: 新测试先 RED 复现 tracked seed 不可读与 delayed restart 假绿，再
    GREEN；候选 unit 已在 production 同版本 systemd 249 通过离线 verify。
    replacement release 全套、fresh review、exact-SHA CI 和二次 backend deploy
    全绿前，继续禁止受控 activation 与 Mobile OTA。
  - 同一 replacement 修复已把 legacy vectorstore、gene registry 与 Dedao review
    workspace 的生产写路径迁到 `/var/lib/health-app/runtime` 和
    `/var/lib/health-app/dedao-kbase/workspace`；生产配置若指回 checkout 会启动失败，
    legacy Chroma API/定时 rebuild 默认关闭。gene registry 写入使用同目录临时文件、
    file fsync、atomic replace、parent fsync，并按同一 FD 的 inode/signature 重载。
  - 发布事务新增 root-only 持久 journal 与 boot gate：在 mutation 前同时封存
    old/candidate env、runtime/beat/Dedao/drop-in/enablement preimage；SSH 断线只允许
    用原 token 接管原 immutable stage。candidate floor 后禁止回到旧代码；System KB
    与 skills 完成后还要重新跨稳定窗口证明，再 finalize 清理快照。old rollback
    同时恢复旧 env，不能留下新路径配旧 systemd 的潜伏写入故障。
  - Fresh write-path audit 又发现 uploads 与 Skills Hub cache 仍写 checkout。修复后
    backend/worker/beat 的 effective writable set 分别精确收敛到
    `{uploads, cache, runtime, Dedao}`、`{uploads, Dedao}`、`{beat state}`，不存在
    `/opt/health-app` 后代。最终安全审计以单权威契约取代旧的任意 union 口径：
    old writers 指向 legacy 时，非空 external 因来源不可证明会在 preflight
    fail closed；prepare 后只接受 sealed legacy 的逐路径、同 kind/hash 拷贝子集。
    destination 完整复证后才退役 source，且每次退休重入都要求剩余 source 是封存
    manifest 的 deletion-only 子集并保持 uid/gid/mode、kind 与文件 hash；任何
    新增、改写、类型/权限漂移都保留现场并 BLOCK。old-SHA rollback 把完整 external
    （含 candidate-window 新增与删除）精确复制回 legacy 后退役 external；若旧
    writers 已指向 external，则保持 external 权威。
    cache 固定为 `/var/cache/health-app/skills-hub`；生产 install/uninstall 在任何
    fetch/path/write 前显式返回 `hub_skill_mutation_disabled`。
  - Activation 接管也改为 immutable resume：第一次 systemd RPC 前先持久化并 fsync
    `launch-intent`；接管只能只读验证 sealed candidate/guard 与 terminal outcome。
    已终结只做 exact proof；仅 state dir 为空时允许复用原工件 launch；intent
    存在但 outcome 缺失时保留 stage/lease。所有 release mode 的 terminal success
    统一清理接管状态，delegated/unknown 结果仍保留现场。
  - 回退阶段: G5 → S5/G3/G4；禁止带红继续。
- [x] Correction Block — systemd socket ready-state portability
  - 触发: state-boundary replacement CI run `30544779284` 对精确
    `294f8c6761a46b37c8aecb19475165164dc56657` 的 44 个 job 全部 success、
    0 non-success；临时 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 随即删除并按名称复证
    计数为 0。backend deploy 的 41 MB backup、234 表恢复演练、站外 age
    hash/HMAC 真实性与旧 SHA 199 表 schema probe 均通过；去激活事务也输出精确
    `HEALTH_EVIDENCE_DEACTIVATED flag=false services=active`，但独立终态 proof
    随后失败，G5 立即 REJECT，未 checkout、migration、KB import 或激活。
  - 根因: 三条稳定性 proof 把 `health-backend.socket` 的合法 SubState 只写成
    `listening`。生产 systemd 249 对同一 active、success、已绑定
    `127.0.0.1:8000` 且列在 `list-sockets` 的 socket 报告 `running`，因此
    deploy proof、rollback runner 与 activation runner 都会把真实健康状态误判为
    BLOCK；单测 mock 只返回 `listening`，掩盖了跨版本契约。
  - 安全处置: 保留原 release lease/stage，不并发部署或回滚；复证旧 SHA
    `85fd0a69...`、candidate=live、唯一 canonical false、全部 cgroup PID=false、
    durable/runtime/drop-in absent、四服务 active/success 且 restart count=0。
    用修正后的 proof 跨 7 秒重验 PID/restart/timestamp/socket SubState 不变后，
    只删除本次 PID 23162 的精确 stage、bundle 与 lease；生产仍为旧 SHA、
    flag=false，运行数据与备份未触碰。
  - 新基线: socket ready state 明确兼容 systemd 的 `listening|running`，但不把
    两者当作可在窗口中切换：record/compare 必须逐字相等；ActiveState=active、
    Result=success、writer PID/NRestarts/enter timestamp 与全部 cgroup flag 的原
    硬闸不变。三个生产路径的测试 fixture 改为 systemd 249 的 `running`，均先
    RED 后 GREEN；CI 原样七文件 release-invariants 260/260（756.58 秒）、
    Bash 语法、diff/doc drift/Dossier 闸与 fresh P0/P1 复审均 GO。replacement
    exact-SHA CI 全绿后才能再次部署。
  - 回退阶段: G5 → S5/G3/G4；禁止带红继续。
- [x] Correction Block — ExecStart 稳态契约与 rollback env ownership
  - 触发: socket-state 修复提交
    `c9e21068904de9aa6b963aa18d9d51bcc7c85bd0` 的 exact-SHA CI run
    `30549606506` 44/44 success 后再次 backend deploy。41 MB backup、234 表
    恢复演练、站外 age hash/HMAC、旧 SHA 199 表 schema probe、去激活与四服务
    inactive proof 均通过；持久事务随后以
    `effective config changed while preparing transaction` BLOCK。生产未
    checkout、migration、KB import、activation 或 OTA。
  - 根因一: `systemctl show ExecStart` 同一条命令同时返回静态
    `path/argv[]/ignore_errors` 和运行态
    `start_time/stop_time/pid/code/status`。停用 socket/writers 后，systemd 249
    合法地把后五项清为 n/a/0；事务比较整个 raw 字符串，因运行态元数据变化把
    未变化的有效配置误判成静态漂移。
  - 恢复中的第二根因: 第一次 formal rollback 已恢复 code/runtime/schema，但把
    root-only staged `.env` 以 `root:root:0600` 安装到 live。backend/worker/beat
    以 `health-app` 运行，Pydantic Settings 在降权后读取 `.env`，因此三个进程均
    `PermissionError`，健康闸正确保持服务 inactive，回滚没有输出成功哨兵。
  - 安全处置:
    - 原 sealed stage 保留不变；新建完整 hash-sealed recovery stage，在同一
      release token 下完成一次性人工 handoff 后才运行修正 runner/rollback；这是
      本次已结束事故处置的历史事实，不是可复用发布工具契约；
    - 第二次 formal rollback 输出 `runtime_state=restored`、
      `ROLLBACK_SCHEMA_PROBE_OK tables=199`、
      `release-gate=RESTORE_FINALIZED` 与 `ROLLBACK_OK`；
    - 独立 proof 确认 terminal `RESTORE_FINALIZED`、gate unarmed/released、
      old exact SHA、clean tree、health=200、auth=401、
      `.env=root:health-app:640`，四服务跨 7 秒 PID/restart/state 不变；
    - 仅随后精确清理两个 recovery stage、bundle 与 lease。生产终态仍为
      `85fd0a69...`、base flag=false，无 release lock/stage。
  - 新基线:
    - `ExecStart` 只忽略同一命令记录的五个运行态字段；严格保留
      `path/argv[]/ignore_errors`，未知字段、多记录、缺失/乱序或静态漂移全部
      fail closed；
    - legacy raw `ARMING + gate_armed=true` journal 在 mutation 前严格验证并
      canonicalize，`PREPARED` 持久化三字段 canonical 值；畸形 journal 在
      restore 数据变化前拒绝；
    - candidate backend/worker/beat 三个 unit 共用严格解析并比较精确静态命令；
      rollback 安装 live `.env` 时强制并终验 `root:health-app:640`；
    - fresh 审计进一步关闭 stage provenance、Python import shadow、
      symlink/directory env target、post-rename fsync、RT signal status、snapshot
      publish crash 与畸形 metadata/snapshot 延迟失败：rollback shell 和 runtime
      helper 双重绑定 `lock/stage`，正常工具禁止 rebind；journal 的全部
      restore-relevant 结构在任何 mutation 前精确校验；
    - 第二路测试审计关闭 lease fixture 假绿：lock/token/stage pointer 使用真实
      0700/0600/0600，fake helper 校验 exact pointer/owner/mode；shell 在任何停服前
      同时验证 owner/mode、单链接和包含唯一结尾换行的精确字节，错误 metadata、
      hardlink、少/多换行均保持服务 untouched；
    - runtime transaction 完整文件 110/110、rollback 完整文件 36/36、
      完整七文件 release-invariants 305/305 已通过；fresh test-contract 与
      release-security 复核均 GO（P0=0、P1=0）。新 exact-SHA CI 仍待完成。
  - 回退阶段: G5 → S5/G3/G4；禁止带红继续。

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
- 边界(不做): 微调、诊断/处方、raw Dedao runtime、全医学域一次迁移或 feature
  domain schema migration；历史 schema drift 的受控运维 reconciliation 例外
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
    （生产已正式回滚到 `85fd0a69...`、flag=false、四服务稳定且无 release
    lock/stage；当前 ExecStart/rollback ownership 加固尚待完整 local G3/G4、
    提交/CI、backend redeploy、activation、OTA 与 prod 验证）
- 并发检查(`git fetch` + `gh pr list`,没被抢先):☒
  - overlap noted: PR #221 claim honesty and PRs #214/#216 medical safety; this
    implementation avoids cherry-picking unrelated branches and will run overlap review.

## S5 · 实现

- 委托: health-harness-orchestrator contract + TDD + parallel discovery agents
- 历史实现分支/commit: `codex/mobile-health-evidence-runtime` off
  `origin/main@b3e15300c`;release-hardening code head
  `832d7325615fdc810bc50112377cf774448a078f`，
  integrated main merge `0d674fa28b503d006d133de9b7107dca2e06936f`，
  regenerated client types `ab300686f5c14f05bd3f32a951ebe5eb6cfa223e`，
  integrated-CI remediation `f89ed2d5`。
- 生产回滚点: `85fd0a69adf9e9cf1ee6010e416b4e4039e1cc2a`（backend，
  runtime flag=false）；正式 rollback、schema/auth/health、跨 RestartSec 服务稳定、
  env ownership 与 terminal cleanup 均已独立证明。
- 当前工作候选: Celery Beat external state + deterministic tracked modes +
  restart-stable release proof + stable ExecStart journal + service-readable rollback
  env；local G3/G4、fresh review、exact-SHA main CI 与 replacement backend deploy
  仍待完成。
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
  - feature candidate Mobile 8 suites / 202 tests；
  - integrated Mobile + main medical-import overlap 12 suites / 297 tests；
    TypeScript 0 error；lint 0 error；
  - Web 2 suites / 20 tests；TypeScript 0 error；lint 0 error；
  - 无 native/plugin/SDK/lockfile diff，发布路由为 OTA。
- 历史 release transaction 基线:
  - activation/deactivation/deploy/rollback 69/69；
  - `bash -n` 三个 shell 入口、Ruff、`git diff --check` PASS；
  - 两次独立复审前后六个冻结发布文件 SHA256 不变。
- 当前 isolated-Git delta:
  - clean-filter + assume-unchanged + skip-worktree 3/3；
  - ownership normalization static + executable target-recorder 2/2；
  - deploy/activation/release-lock/rollback 完整套件 106/106；
  - 两路 fresh release-security review GO；production Git 2.34.1 exact
    read-tree proof 通过；
  - bash syntax、Ruff、`git diff --check`、doc drift、92 份 Dossier consistency
    均 PASS；exact-SHA main CI 仍待跑。
- 历史 static/data 基线: Ruff、`git diff --check`、seed integrity
  （460 claims / 247 entities / 3318 relations）PASS。
- 历史 system-map/doc drift: 从当时冻结代码重新生成，`check_doc_drift.py` 与
  `check_dossier_consistency.py` 均 PASS；当前候选冻结后必须重跑。
- clean-main local integration:
  - 合入最新 `origin/main@684823494`，无冲突；Mobile/Web OpenAPI types 从合并后
    backend 重新生成；
  - feature 20 文件 backend 矩阵 692 passed / 3 skipped，main 新增
    `test_medical_exams.py` 20/20，release transaction 69/69；
  - doc drift、Dossier consistency、Shell 语法、diff check 均 PASS。
- integrated-CI remediation:
  - 首轮 run `30499545219` 已有四个 completed failure，故 G3 拒绝且部署暂停；
  - 修复后 agent-executor CI shard 329/329，d shard 388 passed + 1 skipped，
    release transaction 69/69，Mobile/Web TypeScript 均 0 error；
  - health-harness run `8cf7ad14fa3e` 已记录一次不采信的环境失败和随后采信的 live
    TokenPlan PASS；只保留合成统计，不记录 prompt、回答、密钥或用户数据。
- bootstrap replacement CI:
  - run `30507073580` 对精确 main
    `1eb8c2f8bcc904144b57beefceefc34cb8f40667` 的 43 个 job 全绿；
  - `backend-quality` 在临时 repo variable 删除后仍通过；变量复查为 not found。
- G5 incident remediation:
  - release deploy/rollback/activation 92/92；
  - managed migration、Agent circuit、runtime schema 56/56，health-score 18/18；
  - Shell syntax、Ruff、`git diff --check` PASS。
- incident remediation CI: run `30510213024` 对精确
  `5df2cfde36b233eabcabde8d25cb313750e4212e` 43/43 success、0 skipped/failed。
- direct-script import-root 修复: 精确 subprocess RED→GREEN；57/57 定向回归、
  fresh review、Ruff、diff check 与 Dossier consistency PASS。
- import-root CI: run `30511389923` 对精确
  `1a831aa49670ef04859b30cb1b497166bc3187b6` 43/43 success。
- activation isolated-Git 修复: 真实 clean-filter exploit 已 RED→GREEN；
  fsmonitor、`core.worktree`、writable-config、non-root repo 故障注入通过；
  完整本地闸、两路 fresh review、production Git 2.34.1 staged proof 与 exact-SHA
  CI run `30515848406` 43/43 全绿；临时 live-eval repo variable 已删除并复证 absent。
- Celery Beat state-boundary 修复:
  - tracked seed mode/readability、external StateDirectory、exact unit staging、
    legacy shelf allowlist migration/cleanup 与 delayed restart failure 均有
    RED→GREEN；
  - production 同版本 systemd 249 候选 unit verify PASS；
  - 上传单权威事务 83/83、release/rollback/deploy/infra/CI contracts 146/146、
    external runtime paths 27/27；冻结快照按 CI 原样执行七文件
    `release-invariants` 为 258/258，耗时 752.51 秒，前后 hash 不变；
  - 精确 Python 3.12 锁定依赖下，健康证据/权威/System KB 442 passed /
    1 skipped，Dedao/System KB 117/117；Mobile TypeScript、设计 token、依赖
    audit policy 全绿，Jest 282 suites / 2184 passed / 1 skipped；
  - 两路独立 release/security review 与知识路由语义复审均 GO；Secret scan、
    OpenAPI 双客户端零漂移、LLM synthesis 12/12 + 50/50 + 12/12 + 9/9、
    Shell syntax、Ruff、Python compile、`git diff --check`、doc drift 与
    92 份 Dossier consistency 均 PASS。
- state-boundary replacement CI 首轮:
  - run `30543782762` 对精确 main
    `9c56d2d0f42fcdc2fdd6b113d93e3e1727d4fc05` 的 release-invariants、
    Mobile、Mac、frontend、PostgreSQL runtime、quality 与其余 backend shards
    均通过；`backend-test-d` 单项红灯，故 G3 按契约 REJECT，变量保留且未部署；
  - 根因是结构测试把“已终结事务的前置只读 staged 复证”误当成“KB 导入后的
    staged post-gate”。生产顺序仍为 migration → guard restart/contract →
    rollback floor → seed/import → staged post-gate；测试现从 importer 之后查找
    目标校验，不删除或放宽任何 Gate。定向文件 8/8 已通过，replacement
    exact-SHA CI 待重跑。
  - replacement run `30544779284` 对精确
    `294f8c6761a46b37c8aecb19475165164dc56657` 44/44 success、0
    non-success；`backend-test-d` 通过。临时 live-eval repo variable 在终态
    success 后立即删除并复证 absent。
- socket-state replacement CI:
  - run `30549606506` 对精确
    `c9e21068904de9aa6b963aa18d9d51bcc7c85bd0` 44/44 success、0
    non-success；临时 live-eval repo variable 保持 absent。
- ExecStart/rollback ownership incident remediation:
  - legacy raw ARMING journal、runtime metadata reset、静态 path/argv/ignore
    drift、unknown/multi-record、restore-before-mutation 与三 candidate unit
    exact-command 覆盖已 RED→GREEN；stage exact pointer、snapshot publish crash、
    RT signal 与 metadata/snapshot schema 也已闭环；runtime transaction
    110/110；
  - rollback live env `root:health-app:640`、nonregular target、exact rename、
    两段 fsync、stage metadata/allowlist/import shadow 静态与功能覆盖已
    RED→GREEN；rollback 完整文件 36/36；
  - 七文件 release-invariants 305/305、Ruff、Shell syntax、doc/dossier drift
    全绿；fresh test-contract 与 release-security review 均 GO，冻结哈希前后
    一致。
- **裁决**: incident remediation 本地完整 G3/G4 ☒ GO ☐ PENDING；
  replacement exact-SHA main CI ☐ GO ☒ PENDING。全部全绿前继续禁止
  G5/activation/OTA。

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
- 当前 release-security delta 曾连续发现 fsmonitor、clean-filter 与 live-index
  三个 P1，均已在 read-tree 候选中以故障注入闭环；两路 fresh review 未发现新
  P1/P2。历史 clinical/privacy GO 与当前 release-security GO 均有独立证据。
- Celery Beat incident 修复涉及 root-owned checkout、systemd drop-in 原子替换和旧
  state 精确清理；最终安全审计曾发现并关闭两项上传 P1：双树会复活已删除 PII，
  以及 retirement 崩溃重入会删除 divergent source。当前单权威事务对无来源
  non-empty external、source 新增/改写、类型/权限/hash 漂移全部保留现场并
  fail closed；83 项事务测试、独立复审与完整冻结 release 合跑均通过。
- 知识路由语义复审确认 reviewed PostgreSQL/System KB 与 Dedao 保持可路由，
  held/未审核 low-back 与 legacy Chroma/RAG 不进入通用 serving；急性 Safety
  Guardian 和确定性红旗判断未削弱，运行时无 fine-tuning/LoRA 依赖。
- 当前 ExecStart/rollback ownership delta 不改变 clinical/privacy 语义，但涉及
  root 权限、sealed recovery stage 与 systemd effective config fail-closed
  边界；最终增量 release-security review 对冻结源码确认 P0=0、P1=0，并验证
  lease exact bytes/nlink、四个 isolated helper 调用、env symlink/rename/fsync
  fail-closed 与 staging/helper 职责边界。
- **裁决**:☒ GO ☐ PENDING

## S6 · 部署

- 路由(获 integrated-main CI 绿后):☒ backend-deploy（backend + Web） ☒ mobile-ota
  ☐ mobile-testflight
- 序:干净 main 集成 → Mobile/Web OpenAPI types 与 system map 重生成 →
  integrated verification/CI → 以 base flag=false 部署后端 → Web deploy →
  Linux systemd/cgroup 故障演练 → `--activate-health-evidence` 受控持久启用 →
  production semantic smoke → OTA
- TestFlight 判断: 当前仅 Python/JSON/TS/TSX/API 变更，无 native/plugin/SDK/runtime
  变更；按发布契约走 OTA，不浪费 TestFlight build。若最终 diff 出现原生变更再改路由。
- 部署 SHA / 回滚点:
  - 首次目标 `6e449b176d...` 在首次 flag bootstrap 的 mutation 前停止；
  - bootstrap 修复目标 `1eb8c2f8...` 已进入 guard，但 G5 hard veto 后回滚；
  - incident remediation 目标 `5df2cfde...` 完成 migration/probe 后被
    ModuleNotFoundError 硬闸阻断并成功回滚；
  - import-root 目标 `1a831aa4...` 已完成 backend/Web G5；activation 被
    systemd Git trust BLOCK 后由 staged deadman 恢复；
  - isolated-Git 目标 `85fd0a69...` 已通过 CI 与 backend deploy；部署脚本瞬时
    验证通过，但独立复查发现 beat crash loop，故 G5 REJECT。生产当前仍为该
    exact SHA、base flag=false、feature 尚未授权；
  - socket-state 目标 `c9e21068...` 在 runtime transaction prepare 被动态
    ExecStart metadata 误判阻断，随后 formal rollback 暴露 live env ownership
    问题；使用新 immutable recovery stage 的第二次 formal rollback 已完整恢复并
    清理。下一目标依次为 ExecStart/ownership 修复完整 local G3/G4 + fresh
    review、提交/CI、backend replacement deploy、受控 activation 与 smoke，
    最后才是 OTA。

## G5 · 部署健康闸

- 数据保护前置 Gate（已执行的 backend 尝试）: PASS —— 每次均有约 41 MB
  production backup、234 表临时库恢复演练、force-RLS 遗传原始文件/审计表
  完整性、站外 age 归档 hash + HMAC 真实性；state-boundary replacement SHA 尚未
  开始新一次备份。
- staged deploy:
  - 首次 BLOCK: legacy live env 缺首次 flag；mutation 前停止；
  - canonical-false bootstrap 修复 CI 全绿，事故锁经严格现场证明后精确清理，
    env-only bootstrap 返回 `HEALTH_EVIDENCE_DEACTIVATED flag=false services=active`；
  - 第二次 BLOCK: guard score `60/60 FAIL` 后 rollback schema probe 暴露历史缺列；
    服务 fail-closed inactive。受控 schema reconciliation + staged rollback 已恢复
    旧 SHA，未带红继续。
  - 第三次 BLOCK: `5df2cfde...` migration、启动前 probe 与 exact-SHA 均通过，
    health score 精确硬失败为 `unavailable:ModuleNotFoundError:attempts=3`；自动
    rollback exact marker 全通过，未带红继续。
  - backend/Web PASS: `1a831aa4...` 两次 60/60、exact SHA、199 表 schema、
    staged KB、skills 22/22、Web build/TypeScript/PM2 online 均通过。
  - activation BLOCK: transient systemd Git trust 缺失；mutation 前 live=false、
    durable/runtime/drop-in absent，随后 staged deadman 手工恢复 exact sentinel
    通过。feature 继续关闭，未带红继续。
  - backend script PASS / independent G5 REJECT: `85fd0a69...` 的 backup、schema、
    score、revision、KB 与 skills 检查均通过，但 beat 因 checkout state
    `PermissionError` 进入 crash loop；脚本仅命中短暂 active 窗口。已在 flag=false
    下恢复 beat，未继续 activation/OTA；replacement deploy 必须把 state 迁到
    `/var/lib` 并跨越 RestartSec 证明稳定。
  - socket proof BLOCK: `294f8c67...` 的 CI 44/44、backup/restore/offsite 与旧
    SHA schema probe 均通过；去激活事务已安装 canonical false candidate 并重启
    四服务，但 systemd 249 的 socket SubState=`running` 被仅接受 `listening` 的
    proof 误拒绝。部署在 checkout/migration 前停止，lease/stage 保留；经完整
    7 秒 patched proof 后只清理该次临时 artifacts。生产仍为 `85fd0a69...`、
    flag=false、四服务 stable，未激活或 OTA。
  - runtime prepare BLOCK: `c9e21068...` 的 CI 44/44，backup/restore/offsite、
    old-schema、deactivation 与 inactive proof 均通过；动态 ExecStart metadata
    被误认为静态漂移，checkout 前停止。第一次 formal rollback 又因 live `.env`
    被装成 `root:root:600` 使降权进程无法读取而保持 inactive；没有输出
    `ROLLBACK_OK`。新 sealed recovery stage 修复 ownership 后，formal rollback
    完成 runtime restore、199 表 schema、quarantine、health/auth、四服务稳定与
    `RESTORE_FINALIZED`；独立 proof 后精确清理 stages/bundle/lease。
- 健康分(阈值 35): 第二次 candidate 的 `60/60 FAIL` detail 因旧日志契约未保存；
  recovery 后 candidate scorer 为 `60/60 PASS`。第三次 candidate 同样总分 60，
  但 circuit import unavailable 按硬闸正确 veto，不把分数当作 PASS。
- prod recovery smoke: PASS（仅旧版本恢复）—— 当前 production exact SHA
  `85fd0a69...`、clean tree、base flag=false、health=200、auth=401、
  `.env=root:health-app:640`，四服务跨 RestartSec 保持相同
  PID/restart/state，terminal `RESTORE_FINALIZED` 且无 release lock/stage。该
  PASS 只证明旧版本安全恢复，不等于候选发布通过。
- Linux 实机硬条件: systemd drop-in precedence、cgroup v2 全部 uvicorn/Celery/beat
  子进程 flag 一致性、durable commit/revoke/candidate rename 断电前缀、SSH/HUP
  断连租约、生产文件系统 `sync -f`/`mv -fT`/目录 fsync 与 rollback 终态证明在
  recovery 路径已通过；isolated-Git 候选仍须重新 backend deploy（规范化
  ownership 并 stage 新 runner）后再跑 activation G5。
- **裁决**:☐ PASS ☒ BLOCK → 候选回 S5/G3/G4；旧版本恢复 PASS

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
- 文档同步: 历史 ARCHITECTURE/doc-drift/parity 已完成；当前
  isolated-Git/deploy governance delta 的 doc drift 与 92 份 Dossier consistency
  已在冻结候选重跑 PASS。
- 状态 → **shipped** only after G6
