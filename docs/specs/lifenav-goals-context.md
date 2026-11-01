# LifeNav 晨读目标只读上下文

2026-11-01：用户要求解决晨读读取本人目标时的 403。现有晨读用 API Key 请求完整
`/life-navigation/workspace`，该接口要求本人 JWT/cookie，拒绝是预期权限边界。

新增 `GET /api/v1/life-navigation/goals-context`，允许有效本人 JWT/cookie 或具有
`read` scope 的本人 API Key。拒绝家庭代理、代管账号、停用/未批准账号、缺失 read
scope；管理员没有跨账号特权。用户身份仅由认证决定，拒绝所有 query 参数以及
不匹配的 `X-Reva-AI-Subject`。既有 workspace/history/backup 和所有写入权限不变。
这是对现有 read scope 的明确、有界扩展，不赋予 API Key 本人网页会话权限。

响应 `life_navigation.goals.v1` 包含 owner_id、workspace revision/updated_at、用户
本地日期/时区、strategy（vision/annual_goal/primary_question）、当前季度的
strategy/decomposition/plan、本周 tracks。日期由服务器按用户时区计算，不能指定
历史日期。缺失层级写入 missing_horizons；当前模型没有 monthly 字段，始终标为缺失。
空白 workspace 返回 revision=0 和空目标，不创建数据。年度目标是现有无年份字段，
不声称已经核验为当年重新确认的目标。

不返回任务、完成情况、笔记、日记、历史版本、机会、Health 记录或健康摘要。
响应 private/no-store，并按 Authorization、X-API-Key、Cookie 区分；审计只记本人 ID、
认证类型和 workspace revision，不记正文或凭据。调用方固定可信 HTTPS origin、限制
响应大小、校验绑定 owner_id/日期/schema 后才将字段送入晨读专题上下文。

验证覆盖：本人 read key 成功、write-only key 拒绝、完整 workspace 仍拒绝 key、保存
仍拒绝 key、另一账号和管理员隔离、匿名/代理/代管/停用拒绝、日期/用户选择器拒绝、
当前季度/周边界、缺失目标、排除私有笔记与任务、只读后 revision 不变。
