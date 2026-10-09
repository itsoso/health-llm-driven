# LifeNav 接入与回退

> 2026-10-09；本页描述 Health 接口交付，不代表外部接收端、线上发布或七天试点已经验收。

## 开关与接收方

默认 `HEALTH_NAVIGATION_ENABLED=false`、`LIFENAV_INTEGRATION_ENABLED=false`、`LIFENAV_RECIPIENTS_JSON={}`。先发布并验证本人导航，再在核验 LifeNav 的稳定实例、租户隔离、存储、缓存、备份及 AI 数据流后登记接收方。临时隧道站点不能作为身份凭据。

接收方配置以 recipient_id 为 key，值包含 `verified`、HTTPS `origin`、同源固定 `redirect_uri`、`client_secret_sha256`。原始接收方秘密由安全渠道生成和分发，只存接收端服务端；Health 配置保存 SHA-256。不得提交真实配置或秘密。改回调地址或秘密会使旧 grant 失效。

## 接收端实现协议

1. LifeNav 服务端生成高熵 state 与 PKCE verifier，绑定本人登录会话；verifier 保留服务端，challenge 使用 SHA-256 后 base64url 去填充。
2. 本人 Health 登录明确确认后 POST `/api/v1/health-navigation/grants`，提交 recipient_id、固定 redirect_uri、state、code_challenge；唯一 scope 为 `navigation:generic`，window_policy 为 `current_trailing7`，授权最长七天。
3. Health 返回固定回调 authorization_url；接收端验证 state 和本人会话，在五分钟内服务端 POST `/api/v1/integrations/lifenav/exchange`，提供 client_id/client_secret、code、redirect_uri、state、code_verifier。code 只能兑换一次。
4. 返回的专用 Bearer 凭据只保留接收端服务端；不进入浏览器存储、URL、日志、备份或 AI prompt。无刷新凭据。GET `/api/v1/integrations/lifenav/summary` 不传 query selector、Cookie、Origin 或通用 API Key；仅当前滚动七天泛化视图。
5. 接收端校验 schema_version、expires_at、projection_revision，按授权视图隔离。projection_sequence 是该可共享来源的累计 revision；窗口移动或安全有效期变化用 revision hash 判断。禁止按 sequence 相等延长有效期，过期必须清除并重新读取。撤权立即停止后续读取；已读数据的缓存/备份删除仍须接收端验收。
6. action_ref 是不含健康内容的 grant 绑定引用。可引导本人到 Health 对应 `/health-action/{ref}` 页面；当前已实现应用内路由，HTTPS universal link 需候选原生配置与独立验收，不能宣称已支持跨 App 自动回跳。LifeNav 不写事件、不代确认、不据此修改健康目标或计划。

## 本人路径

今日页 → 七天导航 → Health 详情 → 本人二次确认。确认带冻结 action_revision 与 UUID operation_id；超时保持原 operation_id 重试，409 重新核对。明确刷新走原 Health 计划安全校验。GET 不生成计划，未生成与已生成空计划分别显示。原始正文仅本人详情可见，投影只有固定泛化文案及记录计数；不输出完成率或因果结论。

## 发布验证与回退

迁移位于 `backend/migrations/managed/20261009_150100_lifenav_grants.*.sql` 和 `20261009_230000_health_navigation.*.sql`，跟随托管迁移入口；必须核验 PostgreSQL 实际回放与幂等性。接口类型同时生成 Mobile/Web；System Map 与 Mobile 导航图同步生成。

关闭外部开关后兑换和读取失败，列表与撤权仍可用。本人导航开关关闭会拒绝新导航操作；原日计划路径继续。应用回退保留新增表、审计及已确认事件，禁止通过删除表回退执行事实。

发布前另行取得干净候选、精确 SHA CI、后端部署回执、符合 OTA/原生边界的客户端发布以及模拟器验收。W6 记录连续七天实际使用、缺失/失效数据与撤权删除；W7 仅在试点价值验证后重新准入。
