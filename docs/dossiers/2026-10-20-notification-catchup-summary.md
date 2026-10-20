# 锁屏集中提醒与家庭日报摘要

Updated: 2026-10-20
Status: implementation verified locally; G4 pending; not deployed
Spec: `docs/specs/active/2026-10-20-notification-catchup-summary.md`
Workflow: quick_fix + safety overlay；System Map 按路径查询；未使用 superpowers。

## 故障与范围

截图中多个原计划时段用药提醒集中在 09:00 到达，家庭日报多行泛化后相同。代码确认既有 09:00 晨间地板会把早间提醒延期，flush 原先逐条发出；同日复查项目逐项删除名称后会显示相同句子。未读取生产健康记录或投递回执，不能从截图断定实际重复调度、重复复查记录或每条 APNs 到达时间。
G1 PASS：修复提醒展示与投递汇总，沿用 ExecutionEvent 与现有 NotificationLog，不增加健康写入授权。保留用户已有睡眠保护；已询问可选偏好，未收到答复时按减少集中刷屏推进。

## 实现

- 有界当前队列中，仅同用户、原日期、时区、延后投递时刻的 canonical 例行用药 slot 合并。不同账户/日期/时区、紧急健康提醒、旧未知载荷不合并；准时提醒不等待队列汇总。
- 整组条件更新认领，部分命中回滚；只有认领者发送。先保留 pending 及完整关联，再投递。未知中断不重发；共享投递结果写回原日志；去重按每个原 rule 保留。
- 汇总锁屏只给时段数，已有登录详情页显示原日期、时区与时间；原首条载荷保存在内部审计字段。完整正文与内部关联均从渠道载荷剔除。再次安静时段则还原全部原载荷并顺延。
- 家庭摘要给总事项/成员/逾期计数，跳转已有 `/family` 重新执行授权读取。全量家庭报告不写入通知。缺失推送摘要时只用泛化兜底，不退回原私密报告。

## 验证

- RED：用药新增 4 failed / 1 skipped；家庭新增 2 failed。日志 `/tmp/reva-lockscreen-red.log`、`/tmp/reva-family-summary-red.log`。
- 最终后端回归 **224 passed / 3 skipped**，未处理线程异常按失败；日志 `/tmp/reva-lockscreen-regression-final.log`。跳过项为必须 PostgreSQL 的并发/锁测试。
- 独立 PostgreSQL UTF8 库最终 **25 passed**，含整组重叠认领、原单条并发、advisory lock、账户/日期隔离、未知投递、失败、重复 flush、安静时段顺延；日志 `/tmp/reva-lockscreen-postgres-final.log`。
- 现有 Mobile 路由/历史/详情兼容及新汇总路由 **3 suites / 67 passed**；日志 `/tmp/reva-lockscreen-mobile-final.log`。无自动发送/服药写入；数据详情服务器按 owner 查询。
- System Map / mobile-nav / doc-drift 与 `git diff --check` 通过，无结构生成物变化。
- 合成 fixture / mocked transport；没有真实模型、健康记录或 APNs 调用。没有模拟器/真机通知展示验收。

## 发布边界

只读核实生产 HEAD `1ba724dcb62ac389a72e41eecf40fea7aaca27e3`，health-backend active；远端 main 为 `7cea49ce535785a2a76ee8e7e7edbb60b2db49c2`。
该 SHA 一次选定范围 CI `39280567085` success，但完整运行 `39280595751` failure（mobile-typecheck 的 isolated chat、ota-runner-startup 及 release-tests）。不能以前者覆盖完整失败。按 AGENTS §7 主干非绿停止外部写入；G5 精确修复完整 CI/CI-mode 与发布门禁未满足。
本任务未推送/部署；后端行为修改及 Mobile 测试不需要 OTA。保留共享目录其他工作；不备份、不重发既有失败发布或维护。
