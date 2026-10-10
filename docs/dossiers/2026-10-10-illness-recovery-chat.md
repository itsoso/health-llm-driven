# 对话中更新本人病症恢复状态

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 SQLite 和 PostgreSQL 回归通过；固定候选独立安全审查待完成 |

2026-10-10；quick_fix，无 primary controller；safety-gate overlay。

## G1 准入

裁决：PASS。用户截图的两种本人恢复表达被回成无权限查询。本次修复既有 illness episode 状态更新的语言准入，复用当前用户查询、唯一目标绑定、真实 API 写入和验证回执；不新增疾病诊断、处方、自动判断康复或通用个人记录读取权限。仅记录用户本人明确报告的恢复，不把报告当成医学确诊。

成功标准：完整“我感冒痊愈了”和“更新我的感冒状态：已经痊愈”编译为本人 illness/update；先查询认证用户的候选，再更新唯一同名 active/improving 病程。旧 resolved 病程不得重写；零候选或多候选、引用、疑问、他人、条件、撤销、复发及复合命令不取得新授权。额外字段不得从模型补写，只有真实匹配写入回执才能报告已更新。没有 schema、迁移或客户端契约变化。

## G2 原因与实现边界

既有授权语法需要固定更新动词，状态更新不接受冒号；裸本人恢复陈述未编译为 mutation goal。模型选择 illness health_query 后被 health_query_not_requested 正确阻断。修复不是放宽查询权限：用同一个封闭本人恢复语法作为 classifier、目标编译和更新字段授权真源，现有 executor 将错误的首个 health_query 规范到受限本人 manage lookup，再沿原 Gateway 执行状态变更。

仅修改 write_intent_scope、utterance_intent_classifier、agent_kernel/goal_spec、agent_kernel/capability_policy。agent_executor 混合的今日计划及补剂照片改动不纳入本任务，保留他人工作。未修改任何生产用户病程数据。

## G3 验证

先补截图语义失败回归，原 classifier/goal 的四项正例失败；首轮额外四项是新测试用户缺 name 的夹具错误，不作为行为 RED。修正夹具和既有 lookup limit 契约后，唯一目标真实 Gateway/API 已通过；拒绝回执按真实结构化 clarification_required 验证，不用错误字符串推定。

新增旧已痊愈病程+唯一新病程、仅旧病程的四项 RED，修复候选绑定后相邻 write scope、goal、policy、Gateway、真实病症API合计6331 passed，exit 0。新回归34项覆盖病程重复、零目标、跨账号隔离及原结束日期保护。完整 classifier、真实 PostgreSQL 和最后冻结集成验证待记录；原授权封存/发布阶段阻断保留，不凭局部通过宣布线上修复。

## G4–G6

固定候选独立 safety 审查、精确 CI、后端部署和线上用户路径验证尚未完成。当前 main fa4703060 的 backend-quality 终态冲突是先前整合批次外部阻断，不通过重跑、换 SHA 或删记录绕过。此任务是新产品修复，可本地实现和审查，但不能在上游准入未明确时执行外部发布。

最终补验：classifier 878 passed，真实 UTF8 PostgreSQL17 本人恢复/真实API/病程读取46 passed、exit 0，测试库与服务器正常停止（/tmp/reva-cold-pg.log）。阻断名称/语法静态检查通过。新测试由既有h-j目录glob覆盖，无需新增CI分片或删覆盖。当前fa470的backend-quality已通过可信REST终态回读为completed/success（05:53:04Z），之前缺失终态原记录保留；尚未据此部署。本任务不触及混合executor，也不触及live-change高风险路径；不得将离线通过宣称真实LLM评测。
