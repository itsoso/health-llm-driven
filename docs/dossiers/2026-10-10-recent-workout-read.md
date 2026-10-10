# 刚才运动查询误判为他人记录

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 本地验证通过，安全复审 GO，未发布 |

## G1 准入

裁决：PASS。修复已有本人运动查询，不扩展健康写入或他人数据权限。依据用户截图原句「分析刚才的运动」及错误「这次查询未执行。只能查询当前登录用户本人的记录。」Router：quick_fix + safety overlay；不使用已禁用的 superpowers。

## 原因与实现

主体解析把「刚才」作为非本人所有者；时间解析同时缺少这个完整读取命令的绑定。新增完整受限命令证明，识别分析/查看/复盘刚才或刚刚的运动、锻炼、训练；引用、取消、他人、额外日期及限制不能被擦除。没有全局放开时间词或松绑所有权。

只按认证账号和时区冻结当天运动候选窗口，复用实际运动读取器。身份无效直接拒绝，不得退回旧七天默认查询；暴露层与 dispatch 都只允许该范围的读取工具。不会同步、创建运动或调用可能越界的通用分析/specialist。

统一提示明确：当天已保存记录只是候选，不能证明就是刚才那次；未自动同步，无记录不能拿旧运动替代，多条记录不能合并冒充单次。跨午夜前一天的运动不在本次候选范围内，不能据空结果断言没有运动。

## 验证与安全

- RED：新增正例 5 个全部失败，截图原句稳定复现；负例 16 个通过。安全审查补例再次复现身份 fallback 和宽工具旁路，修复后通过。
- 初轮 33 项回归通过，含真实 Pi/gateway/实际读取器、隔离 PostgreSQL 的有记录和无记录两条执行链；仅模型输出使用合成 provider。断言本人当日记录、排除其他用户及昨日记录、落库回复、不产生运动写入/写回执。
- 独立 reviewer 首轮 NO-GO 的三项问题均修复；复审 30 项独立安全断言通过并裁定 GO，包括账号错位、bool/零身份、batch、全部 specialist、观察句、时区换日及实际工具暴露。
- 最终完整回归：`SKIP_DB_INIT=1 TEST_DATABASE_URL=<isolated-postgresql> venv/bin/python3.12 -m pytest tests/test_recent_workout_read_regression.py tests/test_longitudinal_read_scope_policy.py tests/test_agent_composed_read_completion.py tests/test_agent_kernel_capability_policy.py tests/test_garmin_workout_review_scope.py -q --show-capture=no --cov-report= --cov-report=json:/tmp/recent-workout-coverage.json`：2560 passed，6 条既有依赖弃用 warning，退出码 0。日志 `/tmp/recent-workout-regression.log`，执行耗时 134.64 秒。最终版还验证模型未主动附限制提示时，落库回复仍包含候选/未确定声明，以及真实模型工具列表没有宽查询工具。
- System Map 中央检查与限定 diff whitespace 检查通过，未改架构生成结构。Ruff 未安装，未取得 lint 通过证据。全仓 Dossier 检查仍被其他任务的 `2026-10-10-external-agent-record-grants.md` 缺状态/阶段/G1 阻断，本 dossier 不在失败列表内。

## 交付边界

仅本地修复。没有 commit、push、部署或线上原句验收；共享 main 的其他任务变更保留。当前授权路径候选查询通过不等同于对某次运动身份和分析结论的真实模型验收。
