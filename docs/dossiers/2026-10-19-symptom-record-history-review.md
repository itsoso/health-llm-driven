# 症状背景下的多类历史记录查询

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | 本地实现、关联回归、PostgreSQL及独立安全审查通过；待统一发布 |
| 范围 | 有症状和用药持续时间背景的明确日期范围记录查询 |

## 准入与根因

裁决：PASS。修复既有个人健康记录问答，补齐明确授权的服药历史日志读取；不新增产品对象、外部接口、移动端交互或数据库结构。Router 为 quick_fix + safety；禁用的 superpowers 未加载。System Map 局部查询未索引，完整 system-map-check 通过后回查源码和邻近测试。

截图请求已经明确历史窗口和饮食、补剂、服药三个类别。现有纵向解析没有消耗症状/用药持续时间背景，也不支持 medication 历史维度；现有药品页复盘只允许当天在用列表与执行记录。不能把这类请求降为不查记录的通用建议，也不能只去掉失败提示。根因由合成失败回归和源码确认，未获取生产截图对应的 trace 或生产健康数据。

## 实现与边界

- 整句闭合语法独立解析当前症状、自述服药持续时间及明确记录查询。查询窗口为账号本地日期、包含今天的 1–31 天；中英文数字支持来自既有时间解析。未知附言、他人、引用、假设、额外日期、额外读写意图不被丢弃。
- 本轮认证账号与 envelope 账号必须一致；只授予显式列出的类别，日期在服务端冻结。模型不能追加 owner、状态筛选、其他类别或任意 days；单查询与 batch 经过同一 Gateway。
- 服药历史查询 MedicationLog，并连接 Medication 同时核验两边的 owner。保留已服用、跳过、延迟状态及非在用药物的历史日志；只读与日志匹配的名称，不读取在用药物定义列表冒充实际服用。超过 500 条显式失败，不截断或伪装空数据。
- 饮食与补剂复用既有日历/实际摄入适配器。完成证据要求精确日期、类别与 source_scope，旧药品页结果不能替代历史日志；某类失败时仍标记未完成，不从其他日期补齐。
- 普通和 panel 回复均使用服务器核验的记录摘要、日期分布、服药状态和有限解释。全部及部分查询都不发布模型自由生成的诊断、安慰或用药动作。自述持续时间不充当日志，日期重合不等于因果。症状发作时点未对齐日志时说明不能确定原因，并列出需要就诊说明的信息。
- 就医提示参考 [NHS stomach ache](https://www.nhs.uk/symptoms/stomach-ache/)（2026-10-19查阅），不新增药物副作用推断。没有推送、隐私公开面、schema 或 API 契约变化。

## 验证

- 范围 RED：6 failed / 20 passed；实现后26 passed。日志 `/tmp/reva-record-review-red.log`、`/tmp/reva-record-review-scope.log`。
- 实际执行 RED（修正夹具后）：5 failed / 4 passed，证明历史 medication 适配器缺失、真实 Gateway 返回失败。日志 `/tmp/reva-record-review-runtime-red2.log`。
- 首轮本地65 passed，包括已有药品页复盘、真实Pi/Gateway、跨账号及异常外键、窗口首尾、未服用状态、范围篡改、超限、普通及panel流与保存一致。日志 `/tmp/reva-record-review-green3.log`。
- PostgreSQL 首轮83 passed（57.55秒），日志 `/tmp/reva-record-review-pg.log`；额外天数参数兼容 RED为2 failed / 6 passed，随后仅接受与服务端冻结窗口一致的整数 days。包含该变更的 PostgreSQL 最终91 passed（57.70秒），日志 `/tmp/reva-record-review-pg-final.log`；测试仅使用合成账号与记录。独立临时数据库关闭时 checkpoint 超过 pg_ctl 默认等待时间，随后日志确认正常 shut down，status 确认 no server running，没有强制终止或重启。
- 授权摘要、Capability Policy 与新增范围回归3322 passed（58.23秒），日志 `/tmp/reva-record-review-capability.log`。
- 读取完成证据、普通/panel合成、纵向查询与适配器、范围对抗、工具曝光、旧药品页、症状问答及医疗输出边界扩展回归1978 passed（623.42秒），日志 `/tmp/reva-record-review-regression2.log`，真实退出码0。首个扩展命令引用了不存在的测试文件，未收集测试，不计为通过；上述修正后运行才是验证证据。
- System Map、差异空白、秘密扫描、Dossier一致性检查通过。

## 发布边界

本任务基于本地276ed4ccaefc9e00b4a6c46b226f3d69d3fca91c，包含上一轮症状补充修复。共享工作树存在其他任务的文档和性能改动，只提交本任务文件。

尚未 push、生产部署或模拟器验收。只读复核远端main仍为1ba724dcb62ac389a72e41eecf40fea7aaca27e3，另一个“优化 README”任务仍active并处理既有原生发布；其聊天状态和本地旧回执并不足以证明本修复上线。需核对其当前精确候选、CI和回执后再纳入本修复，不抢占或重放已有操作。本次无 Mobile 改动，不需单独 OTA；本地测试不代表生产已生效。

## G4 独立安全审查

本地实现提交41e8e67db3318ba8c721487e452afd9cb0c283fc。独立 reviewer `record_history_safety_review` 对固定提交只读审查给出 GO，重点核验整句授权、双 owner、实际历史日志、空数据/超限、普通/panel及部分查询的输出与持久化；旧药品页未回归。审查者独立SQLite合成测试91 passed（26.19秒），日志 `/tmp/reva-history-independent-review.log`。GO不替代精确CI、部署和上线验收。
