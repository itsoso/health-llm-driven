# Feature Spec: 手机号自主注册与管理员 Telegram 通知

> Status: implementing
> Owner: Codex
> Updated: 2026-09-29
> Related: 2026-08-01-mobile-invited-phone-registration.md

## Decision and admission

允许新用户主动注册：手机号通过短信验证后创建已验证账号，进入首次设置；同时保留手机号/邮箱密码登录。
属于认证基础设施，改善进入 Health OS 核心循环前的身份准入，不新增健康对象或医疗行为。
Mobile 是主入口，Backend 是账号与注册资格真源。风险为 privacy_sensitive；不引入 LLM。
新增用户与管理员通知事件在同一数据库事务提交；每个账号只有一个注册通知事件。

## Contract

- `AUTH_PHONE_SELF_REGISTRATION_ENABLED=true` 默认开放自主注册，优先于旧邀请准入；设为 false 可回退到已有邀请策略。
- `/auth/phone/code` 开放未知手机号发码，保留已有格式、频率、冷却和尝试限制；被禁用或未审核账号不能借注册重新获取资格。
- `/auth/phone/verify` 返回既有 `authenticated` 结果，`is_new_user=true`；旧手机号仍登录原账号。
- 旧 `/auth/phone/login` 与邀请注册成功时也写同一通知事件；重复登录不重复创建通知。
- Mobile 清楚显示手机号验证后注册，首次创建进入欢迎/档案设置；兼容服务端仍返回 invitation_required 的回退模式。
- Telegram 复用 `TELEGRAM_BOT_TOKEN`、管理员 `TELEGRAM_ALERT_CHAT_ID` 与现有代理配置。不得发送到医生/顾问 chat。
- 消息仅含用户编号、脱敏手机号、上海时间；不含姓名、邮箱、完整手机号、密码、验证码、令牌或健康数据。
- 后台每分钟检查持久待发事件，串行限量发送；失败记录枚举原因并退避重试。未配置也记失败待重试，不伪装成功。
- Telegram 外部网络不在注册请求内执行。通知投递为至少一次：发送成功后进程崩溃可能重发；消息包含稳定事件编号便于识别。

## Data and safety

新增 `registration_admin_notifications` 表，user_id 唯一并关联 users；账号删除级联删除通知。
账号创建、OTP 消耗、通知入队原子化。PostgreSQL worker 使用 SKIP LOCKED 避免并发重复发送，失败只保存安全原因。
纯确定性消息经现有 push privacy backstop，内容被标为敏感时泛化。Telegram 服务不得记录 Bot URL、异常原文或响应正文。
保留已认证用户隔离、审核与禁用规则；不允许手机号直接登录，不新增未验证邮箱注册。

## Acceptance and verification

- 未知手机号没有邀请也能发码，正确 OTP 创建一个用户与一条通知；错误/过期/replay 不建号。
- 老用户登录不重复通知；通知事务失败不留半成品用户或消耗 OTP。
- Mobile 自主注册进入欢迎与档案设置，老用户正常登录；密码登录回归通过。
- 通知成功、Telegram 拒绝/超时/未配置、失败重试、脱敏、隐私泛化正反例均可验证。
- PostgreSQL 验证迁移重复执行、唯一/FK 约束、事务回滚与并发领取；SQLite 只作兼容性检查。
- 运行相关 Backend/Mobile tests、TypeScript、独立安全复核、System Map 与 diff check。

## Rollout / rollback

发布需先迁移，再后端+worker+beat，再 Mobile。须单独验证真实短信、Telegram 管理员接收和新用户路径。
用户已于 2026-09-29 明确授权提交、发布和部署；部署完成与真实通知送达必须以发布回执单独证明。回退到邀请制需设置 `AUTH_PHONE_SELF_REGISTRATION_ENABLED=false`、
`REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=true`、`REGISTRATION_INVITATION_ROLLOUT_ENABLED=true`。
关闭全部新注册则把最后一个 rollout 开关也设为 false；不可只关闭自主注册却保留旧 legacy 开放模式。
已注册账号继续登录，通知 worker 继续处理历史事件。
迁移为新增表，应用回滚保留表及待发事件；禁止为回滚删除未发送通知。

## Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-09-29 | Initial | 用户授权开放自主注册并通知 Telegram 管理员 |

## Local evidence (2026-09-29)

- Source baseline: `1d7981692`; isolated worktree preserves unrelated shared edits.
- Initial Backend matrix: 105 passed (auth policy, OTP privacy, invitation rollback, Telegram transport, self-registration).
- PostgreSQL: 15 passed (self-registration, outbox lock, migration and invitation concurrency); extended orphan-FK negative case also passed.
- Mobile: 142 passed; TypeScript and changed-file ESLint passed.
- Extra SQLite migration/Celery wiring/Telegram timeout checks: 3 passed.
- Independent safety review: initial NO-GO for registration flush/SQL error propagation; fixed safe 409/500 handlers, rollback and suppressed exception chains; re-review GO.
- Final auth/OTP/privacy regression: 39 passed, including both endpoints’ IntegrityError and OperationalError redaction/rollback tests.
- API clients regenerated from the locked backend environment; subsequent Mobile TypeScript passed. System Map and `git diff --check` passed.
- Generated System Map refreshed; no raw health data or credentials added.
- Production read-only check confirmed both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALERT_CHAT_ID` are configured; values were not printed. Production and latest main both matched `623407d6d41d72b8f130aa2db765b2cbc6fba132` before release. No real registration notification or deployment has yet been performed.
