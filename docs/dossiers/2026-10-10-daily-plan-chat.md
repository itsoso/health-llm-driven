# 聊天展示今日计划

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 本地统一整合；真实模型 G3 与固定候选 G4/CI/发布尚未通过 |

2026-10-10；primary controller: health-harness-orchestrator；overlay: safety-gate。

## G1 准入

裁决：PASS。用户明确要求今日计划应实际返回可用计划；不授权自动保存或执行。
用户截图“给我今日计划”被回成未完成数据查询并要求补日期。接入既有产品对象 DailyOperatingPlan 的本人当日只读展示，而不是放宽通用 health_query 权限。
- classification: 既有查询能力缺口修复；core_loop_step: 查看安排并开始行动。
- target_surface: Mobile/Mac/Web 共用 agent_executor 文本；source_of_truth: DailyOperatingPlan 本人当日已保存快照。
- safety_level: 个人健康计划展示；autonomy_tier: 用户明确请求；不做新的诊断、因果或处方裁决。
- success_metric: 有快照返回真实行动、来源和日期；无快照或故障明确区分；不改变健康业务数据。
- added_user_burden: 有快照无需补查询类别和日期；无快照不伪造；spec_required: 本 Dossier 记录完整局部契约。
- non_goals: 调用持久化生成器或保存新计划、创建提醒、读取其他人的计划、重新评估当前健康适用性。

## 原因与边界
GET /daily-plan/me 实际调用 build_daily_operating_plan，会 AdviceLedger、flush/commit、物化议程；commit=False 也不是只读。Today spine 也包含事件物化，均不复用。
只新增纯 SELECT helper，用 authenticated owner 和当前 turn 固定时间/时区绑定日期。完整匹配“给我今日计划”等封闭表达；引用、否定、其他人、写入与复合请求不进入该路径。无新 API/schema/依赖契约。
在用户输入持久化后、模型和程序配方之前确定性展示，保留会话读取证据；无计划写回执。读取失败为 error，不伪装无数据；成功重放复用已保存回答，不重读变更后的快照。非 active 不作为执行安排，损坏 actions 显式失败。
快照不等于新的医学评估，回复注明来源与边界。新增路径的执行器模型调用为零；不据此宣称整条线上链路耗时为零。

## 验证进度
- helper/请求范围 RED 11 failed，初步 GREEN 11；真实 run_stream 先失败再通过。
- 初步 SQLite 15、PostgreSQL 15 通过；增加 inactive/损坏快照/重试后持续最终验证，最终数字待补。
- 独立初审认为 owner/date/副作用边界无阻断，要求补 PostgreSQL、失败/重放、损坏快照测试。
- 新增真实 stream 覆盖健康证据 runtime 开/关，两种均通过。
- 标准 live LLM 闸已尝试，失败：当前本地没有模型凭据，orchestrator 为 recipient_not_disclosed，不能冒充真实模型验收。未改变同意保护、未读取 .env-online、未从生产导出凭据。已向用户和统一发布 owner 询问既有授权评测入口。
- 相邻轨迹回归、CI workflow 原样 release-invariants、最终 PostgreSQL 和固定提交 G4 尚待收口。

## 发布协调
“优化 README”线程 01a120c7-1ba0-75c3-9487-447bd5bfa28f 收到用户继续验证发布 OTA 的新指令，已重新接回唯一发布所有权。本线程只实现测试和交接，不 push/deploy/OTA。不混入它的 release tooling/dossier/receipt。
上批 5fe583bf 服务端成功而 OTA 38009227924 失败，禁止重发原候选。本批继承尚未交付的 Mobile 改动与新建开场 6810463e6，由 owner 统一新 SHA 的 CI、后端、OTA 和模拟器验收。

## 2026-10-10 本轮断点
- 线上只读查询通过截图 run 绑定唯一 owner，确认没有当日计划快照。因此纯快照读取只能解决“已有计划可展示”，不足以完整修复用户原请求。当前实现不提交、不纳入发布；下一批必须补无快照时的未保存草稿路径，或明确实现无副作用的草稿计算契约，不把缺失提示算完成。
- 相邻真实执行链/工具范围回归 127 passed，含 coverage（150.92s）；后续仅补损坏快照、runtime开关等测试及缺失文案收紧。
- 最终本地 PostgreSQL 25 passed（30.99s），覆盖本人/日期/零业务DML查询、缺失、故障、重放、失败重试、损坏actions、runtime开关。日志 /tmp/reva-daily-plan-final-fixed-pg.log。
- System Map、diff、已跟踪文件秘密扫描通过。未跟踪新源码仍需在后续提交前纳入完整扫描。
- 原样 release-invariants 在共享源码变动后主动中断（exit130），不算通过；固定候选发布集成验证由发布owner承担。
- 发布owner当前固定55653dd11（包含新建开场6810463e6），已明确冻结提交窗口。我的文件已仅unstage保留，未commit/push/deploy；待其收口释放后继续。此次G4仅是局部只读能力预审，不是完整用户目标GO。

## G2 下一步实现方案
裁决：PASS（仅设计，尚未实现）。独立 reviewer 建议无快照时直接给经过评审的通用今日草稿，不要求用户重复请求。
- daily_plan_chat.py 增加纯草稿渲染，输入只含冻结本地时间与明确请求，无数据库/模型/工具调用。提供有条件、可选择的日常安排，不给训练强度、营养/饮水剂量或用药指令，不假设用户无禁忌。
- agent_executor.py 区分 saved_snapshot、generic_draft、read_error。无记录才展示未保存草稿；数据库错误仍为错误，绝不降级。草稿声明本轮仅查询今日计划快照，未读取其他健康记录和未做个性化评估；不能写成未查询任何个人记录。
- tests/test_daily_plan_chat.py 增加无快照真实流直接产出草稿、冻结时间/晚间不要求补早晨任务、成功重放一致、PG无业务写入、禁用builder/agenda/Twin/LLM的反例。已有计划继续只展示快照。
- 当前三文件只读局部能力的G4预审GO与PG25不覆盖此尚未实现草稿，不得据此发布完整修复。


## 2026-10-10 局部解冻后的草稿实现
- 发布 owner 明确仅解除本任务三份源码/测试和本 Dossier 的本地编辑冻结。e278a0afa 仍为独立发布候选，本任务不暂存、提交、推送、部署或 OTA；不改其 receipt/ledger。
- 无当日快照时，直接返回带日期的“今日计划草稿（未保存）”：当前重点、后续日常安排、收尾回顾；当地晚间改为记录、休息前准备与次日重点，不要求补做白天事项。
- 模板是纯函数，仅使用 turn 固定本地时间。无模型、planner、议程物化调用；有快照继续展示快照，数据库错误仍为 read_error，不能当作无记录生成草稿。
- 先新增 4 个失败测试，再实现；SQLite 29 通过。独立预审指出前置聊天流程可能读历史消息，来源声明不可写“整轮未读取其他健康记录”；补 3 个失败文案测试后，改为草稿不依据病史、用药或设备读数制定，未做个性化健康评估。
- 加强真实流全部 INSERT/UPDATE/DELETE 目标白名单，只允许 agent_conversations/agent_messages；跨日重放验证原消息和内容不变；读取错误验证没有草稿。
- 最终 SQLite 29 通过（/tmp/reva-daily-draft-final-unit.log）；首轮真实 PostgreSQL 29 通过，文案和测试收紧后的 PG 及相邻回归仍待收口。早期缺 TEST_DATABASE_URL 的运行仅为 SQLite，不计作 PG 证据；缺 DATABASE_URL 的启动失败亦不计通过。
- 独立 reviewer 文件复审 GO，非固定 SHA G4。源码 SHA256：daily_plan_chat.py 172923f6aa5a7b78b9b14c07840541a573ca8bf8ff1a107afe3f3f764a7c9342；agent_executor.py 6bb9acb5e9ccd12b2546f3b15f7b4b4d26f52850080b25bd75f2fedbafa53873；test_daily_plan_chat.py e0d4df5bfb5651c64af599a15d9de1c1673f7f438a3d6313a562071b92e3efbc。
- 真实模型闸仍缺已授权评测入口；不反复失败重试、不读取生产秘密、不绕过 consent。固定 SHA G4、精确完整 CI、部署和线上用户路径验证尚未完成。
- 最终补充验证：真实 PostgreSQL 29 passed（15.96s，/tmp/reva-daily-draft-final-pg.log）；相邻执行链回归 135 passed、含 coverage（139.76s，/tmp/reva-daily-draft-regression.log）。相邻回归启动早于来源措辞和测试断言收紧，最终 SQLite/PG 29 覆盖这些最后修改。
- 测试 PostgreSQL 已正常停止。diff 检查通过。全库 Dossier 检查当前被他人进行中的 2026-10-10-external-agent-record-grants.md 缺状态/阶段/G1 段阻断；未修改其文件，不将全库文档闸记为通过。

## 统一整合窗口（2026-10-10）

用户再次明确授权“修复之后全部session的代码都合并到main然后发布”，统一发布 owner 收口本任务本地代码；此授权解除旧编辑窗口的暂存/提交冻结，不豁免真实模型或发布闸。最终当日计划 29 项及相邻/模拟器等组合定向验证 254 passed；真实 PostgreSQL 组合验证 77 passed。真实模型闸仅尝试一次：离线 invariants/core/trajectory/goldens 全通过，orchestrator 0/5 recipient_not_disclosed，当前正常配置的 TokenPlan/OpenAI/vision 凭据均不存在。已请求安全凭据文件路径或现有授权评测环境，不读取 .env-online，不设置虚假 live 确认。

无快照时通用未保存草稿已实现；图片补剂改动仅改善失败提示，完整视觉候选、数量匹配、预览确认和写入链未实现。生产原失败637批次仍 NEEDS_OPERATOR，存在未决Run与回执关联待审；本地整合不代表已推送或发布。
