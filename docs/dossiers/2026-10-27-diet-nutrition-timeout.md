# 饮食记录营养估算超时恢复

| 字段 | 值 |
|---|---|
| 状态 | shipped |
| 当前阶段 | G6 后端回执核验；登录态重试未观察 |

## G1 准入

裁决：PASS。修复明确饮食新增请求在营养估算超时后直接中断的问题，不新增读写权限，不降低营养完整性、认证用户隔离或保存回执要求。

## 诊断和实现

- 用户反馈明确晚餐记录没有完成。当前线上 `3dd357f9067ad57a938973e3cdb80c6ade503ede` 的对应时段脱敏运行日志显示：第一轮模型约 28 秒后给出需补全的饮食工具请求，辅助营养估算约 11 秒后超时，`agent_executor:10073` 抛出 TimeoutError，整轮约 40 秒未取得保存回执。只提取错误类别、源码位置和计时，未读取真实健康记录。
- 食物和数量解析本身正常；合成测试使用相同语法验证普通保存、原请求恢复与同 client turn 回放。
- 辅助估算超时现在记录诊断并将原不完整请求交回既有校验与有界修复流程。估算只尝试一次；原营养校验仍在实际派发前拒绝缺失数据。模型补全同一餐后方可保存；补全失败停止并明确未保存。
- 补全后的食物、餐次、日期仍受当前回合目标约束；不把其他食物的营养挪到本餐，不猜测前一天晚餐，不对截图补写记录。
- 补齐既有 perf 字段中的营养估算次数、耗时与超时标志。无 schema、API 或客户端改动。

## 验证证据

- 修复前以真实 Pi 循环和模拟估算超时复现两例失败：`/tmp/reva-dried-dates-red-corrected.log`。最初测试夹具属性名错误已纠正，重新在原实现复现，未把夹具失败当行为证据。
- 新测试覆盖超时后的成功补全、不完整补全、食物身份改变、午夜本地日期和相同 turn 重放。所有健康数据均为隔离测试数据；线上记录未更改。
- 相关回归、PostgreSQL、独立安全审查、真实模型闸、精确 SHA CI 与生产发布待完成。

## G4–G6 发布结果

- 独立 Safety GO：`d47aea05be1d5c77632a52636776b0b478dd1fdd`；reviewer 214 项测试通过，另验取消传播、暂停跳过和一次估算。
- 本地相关回归 460 passed / 1 skipped，最终定向 10 passed；隔离 PostgreSQL 最终 265 passed，进程退出与数据库停止均为 0。
- 真实模型闸通过：orchestrator 5/5（平均评分 0.96），invariants 12/12，health_agent_core 50/50，trajectory contracts/goldens 通过；仅合成数据与内存测试库。不能据此宣称截图对应线上模型响应已复测。
- 完整精确 SHA CI `40358356587` success；CI-mode 发布集成检查 4710 passed / 47 skipped / 127 subtests passed。System Map、secret scan 和 Dossier 检查通过。
- 发布前 validate `40360963520` success；后端发布 `40361139424` success。生产版本、SUCCEEDED 回执、COMMITTED/finalized/code-only-no-backup、三个 active 服务、无发布租约及公网 health 200 / 匿名 POST diet API 401 均独立回读。详见本任务 release receipt。
- 首次短期只读 GitHub token mint 响应超时，发生在远程 SSH 前；旧凭据与生产状态未变。保留可能存在未返回短期 token 的不确定性。新的固定 attempt2 经独立 GO 后续期成功，未重放原操作。
- 无 Mobile/Web 代码变更，OTA 不适用。未创建备份、未补写截图记录、未读写真实健康记录。手机登录态下重新发送或点击重试的验收未执行，不冒充已替用户保存。
