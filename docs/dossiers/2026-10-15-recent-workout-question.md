# 最近运动口语问句读取修复

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification / G4 review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

裁决: PASS。修复截图“刚才跑的怎么样？”的现有本人运动读取，不增加数据权限、同步或写入。用户要求定位反复失败的根因，并持续授权修复后的部署及 OTA；不备份、不进行真实模型评测。

## 根因与实现

基线 cb3ef7b8e。截图统一提示由 `AgentExecutor._unresolved_read_failure_notice` 的未恢复读取参数错误分支生成；身份不匹配属于独立的终止原因，不能从该提示推断 user ID 缺失。有效且一致的合成认证身份下，截图原句仍无法生成 OwnedReadScope，说明存在独立的语义解析缺陷。

原最近运动解析只覆盖前置“分析/查询”等命令句及正式运动名，漏掉“刚才跑的怎么样”这种带隐含本人、口语动作和后置评价问句的完整表达。模型选择工具后因无法形成明确的受限读取范围而被拒绝。已有回归偏向命令句，没有覆盖这一口语问句族。

新增完整问句语法并复用 RecentWorkoutSelection、OwnedReadScope 和现有 Gateway；同时共享问句与限制检测的动作词汇，避免拒绝变体落入旧查询路径。身份仍来自认证上下文且必须与 envelope 一致；仅查询用户当地当天及所述运动类型。引用、否定、其他人、额外时间限制及复合写入/同步不授予读取。没有匹配记录不补旧记录，不把当天候选认定为刚才的具体事件。

## 验证

- RED：新增六种口语问句均在有效认证身份下失败；十项拒绝反例通过。原始日志 `/tmp/reva-recent-run-red.log`。
- 初轮 GREEN：119 项通过，包含真实 Gateway、数据库读取与保存回复路径，模型传输为隔离合成输入，不是真实模型评测。
- 后续增加账号、模型参数、其他工具、时区及零/多条记录边界。测试提示分支的夹具最初缺少 executor current_user_id，已明确补齐，不据此认定产品身份缺陷；保留原失败记录。
- System Map 验证通过；LLM change gate `live_llm_required=false`。没有 schema、API、客户端契约或原生变更。
- 最终相邻回归 443 passed；独立本地 PostgreSQL 152 passed，测试库停止退出码 0。原始日志 `/tmp/reva-recent-run-related-final.log`、`/tmp/reva-recent-run-pg-final-tests.log`。没有连接真实账号或调用真实模型。
- 独立固定提交 G4、精确主干 CI、部署与 OTA 证据待完成后补充。不得将本地合成验证称为真实用户/手机验收。

## G4 收口

独立审查首候选 863c68424 为 GO；独立152项与19个额外边界探测通过。为避免短动词误匹配“旅游、跑腿、骑马”，新增三个直接负例先 RED，再将短动词限制为同一评价问句词尾，正式运动名的原限制检测不变。最终相邻446项通过，最终固定提交重新审查，不复用旧SHA裁决。先前完整能力/网关5772项通过；最终 PostgreSQL 和发布证据由交付回执单列。
