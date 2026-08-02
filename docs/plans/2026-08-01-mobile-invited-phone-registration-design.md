# Mobile 邀请制手机号注册设计

> Status: approved
> Updated: 2026-08-01
> Owner: Codex
> Related spec: `docs/specs/active/2026-08-01-mobile-invited-phone-registration.md`
> Related dossier: `docs/dossiers/2026-08-01-mobile-invited-phone-registration.md`

## 1. 决策

Reva Mobile 保留已注册用户的无邀请码手机号验证码登录，但关闭陌生手机号自动建号。
管理员必须先创建一个绑定目标手机号、单次使用、可撤销、有限期的注册邀请；新用户同时
证明邀请码和手机号所有权后，系统才原子地创建账号、核销邀请并进入现有 onboarding。

管理员创建邀请本身即代表准入批准，不再追加第二轮人工审核。邀请默认通过短信发送
“深链 + 8 位手工邀请码”，管理员后台可复制链接或邀请码作为短信失败时的兜底。

## 2. 现状与问题

- `POST /auth/phone/login` 当前在验证码正确且手机号不存在时直接创建最小账号，是否通过
  审批只依赖 `auth_phone_registration_auto_approve`；因此陌生手机号可触发注册。
- `mobile/app/login.tsx` 把手机号主按钮写成“登录 / 注册”，没有邀请状态或深链恢复。
- Backend 已有通用 `InvitationCode`、管理员邀请码页和邮箱申请流，但邀请码不绑定手机，
  且与家庭邀请码、旧 Web 申请语义混杂，不能直接充当 Mobile 注册安全边界。
- 已注册用户依赖手机号验证码登录，不能因为收紧新用户注册而被要求重复提供邀请码。

## 3. 方案比较

### 3.1 绑定手机号的一次性邀请（采用）

管理员预先填写手机号；邀请码只能被该手机号核销。泄露或转发后不能注册其他手机号，
同时保留手工输入兜底。

### 3.2 通用一次性邀请码（不采用）

实现简单，但持码者可以绑定任意手机号，管理员无法证明实际注册者是邀请对象。

### 3.3 只有签名邀请链接（不单独采用）

体验最短，但跨设备、短信客户端深链失败和人工转发恢复较弱。其自动填充体验作为方案
3.1 的增强，手工邀请码仍是必要后备路径。

## 4. 边界架构

Backend 是注册资格、手机号验证、邀请核销和用户创建的唯一真源。Mobile 只承载输入、
深链和状态展示；管理员 Web 只发起创建、发送、重发和撤销命令，不自行判断资格。

新增独立 `RegistrationInvitation`，不复用家庭邀请码，也不继续依赖默认邀请码：

```yaml
RegistrationInvitation:
  id: bigint
  code_digest: keyed HMAC-SHA256
  link_token_digest: keyed HMAC-SHA256
  phone_ciphertext: encrypted normalized phone, only for SMS delivery/resend
  phone_hmac: keyed HMAC-SHA256, for equality matching
  phone_masked: admin display only
  created_by: admin user id
  note: optional, max 200
  status: created | sent | send_failed | consumed | revoked | expired
  expires_at: default 7 days
  consumed_by: nullable user id
  consumed_at: nullable timestamp
  send_attempt_count: integer
  last_send_error_code: bounded enum, nullable
  created_at: timestamp
  updated_at: timestamp
```

同一手机号最多一个有效邀请。邀请码明文和深链 token 只在创建响应及短信投递瞬间存在；
列表接口只返回脱敏手机号、状态、过期时间和审计元数据。

## 5. Mobile 用户链路

```text
启动 / 邀请深链
  -> 输入或确认手机号
  -> 获取短信验证码
  -> 验证手机号
     ├─ 已注册用户：直接签发登录 token，不检查或消耗邀请
     └─ 新手机号：签发短时、单次 verified_phone_ticket
          -> 自动填充或手工输入邀请码
          -> 后端匹配 ticket 手机号与邀请手机号
          -> 原子创建用户 + 核销邀请 + 签发 token
          -> 现有 Reva onboarding
```

### 5.1 手机号页

- 标题“登录小巴”，副标题“使用手机号继续”。
- 默认 `+86`，支持国际区号和规范化。
- 主按钮“获取验证码”；辅助入口“我有邀请码”。
- 固定说明“首次使用需获得管理员邀请”。
- 邀请深链进入时展示“已获得邀请”，但不在 URL 或页面暴露完整手机号。

### 5.2 验证码页

- 显示脱敏手机号，支持 iOS `oneTimeCode` 自动填充、倒计时重发和修改手机号。
- Backend 决定“老用户登录”或“新用户需要邀请”，客户端不得用本地缓存猜测账号存在。
- 新手机号验证成功后返回短时、单次 `verified_phone_ticket`。它可在 SecureStore 短暂保存
  以恢复“等待邀请码”状态；不得写入 AsyncStorage、日志或遥测，过期后必须重验短信。

### 5.3 邀请码页

- 深链自动带入不透明 link token；手工路径接受 8 位邀请码。
- 文案：“小巴目前采用邀请制，请输入管理员发送的邀请码。”
- 手机号不匹配时显示：“该邀请码不是发送给当前手机号的，请确认手机号或联系管理员。”
- 验证码过期只清理 ticket，不清理用户已输入的手机号；邀请码明文不持久化。

### 5.4 完成与兼容

- 注册成功页只显示“邀请验证成功，欢迎加入小巴”和“开始设置我的健康档案”。
- 不要求用户名、邮箱或密码；系统生成内部 username，用户以后可设置名称或密码。
- 账号密码登录保留二级入口。
- 已注册手机号从邀请链接进入时仍直接登录，且不消耗邀请。

## 6. 管理员链路

管理员后台新增“邀请注册”视图：

1. 输入手机号、可选备注和有效期（默认 7 天）。
2. 二次确认脱敏手机号后点击“创建并发送邀请”。
3. Backend 创建邀请并调用现有短信 provider adapter 的注册邀请模板。
4. 页面展示 `发送成功 / 发送失败 / 已使用 / 已撤销 / 已过期`。
5. 发送失败可重试同一邀请或复制邀请码/链接；重试不得生成第二个有效邀请。
6. 未核销邀请可以撤销；已核销邀请不可恢复。

短信建议文案：

> 小巴邀请：你已获得注册资格。点击安全链接继续，或在 App 输入邀请码 ABCD2E7K。
> 邀请 7 天内有效。请勿转发。

短信不包含健康状态、管理员备注或其他用户数据。

## 7. API 契约

```yaml
admin:
  POST /admin/registration-invitations
  GET /admin/registration-invitations
  POST /admin/registration-invitations/{id}/resend
  POST /admin/registration-invitations/{id}/revoke

public_auth:
  POST /auth/phone/code                  # 保留现有验证码发送
  POST /auth/phone/verify                # token 或 verified_phone_ticket outcome union
  POST /auth/invitations/inspect         # 深链预览；只返回有效性、掩码和过期时间
  POST /auth/invited-registration        # ticket + code/token；原子注册
```

`POST /auth/phone/verify` 返回判别联合：

```yaml
existing_user:
  outcome: authenticated
  access_token: string
  user: UserResponse

new_phone:
  outcome: invitation_required
  verified_phone_ticket: opaque one-time token
  expires_in_seconds: integer
```

旧 `/auth/phone/login` 在 rollout 初期保持兼容；最终 enforcement 后只允许已存在用户登录，
陌生手机号返回稳定错误码 `REGISTRATION_INVITATION_REQUIRED`，不得再创建用户。

## 8. 原子性、幂等与失败语义

- `invited-registration` 在一个 PostgreSQL 事务中锁定邀请行，重新验证状态、过期时间、
  手机号 HMAC、ticket 和用户唯一性，然后创建用户、写 `consumed_by/at` 并签发 token。
- 邀请验证或 inspect 不增加使用次数；只有用户创建成功才核销。
- 同一请求携带客户端幂等键。超时后客户端查询权威结果，不自动重复核销。
- 两台设备并发使用同一邀请时只能一个创建；另一请求若已创建同手机号用户则返回可恢复
  的幂等登录路径，否则返回 `INVITATION_ALREADY_USED`。
- SMS 发送失败必须进入 `send_failed` 并返回可操作错误，不得静默显示“已发送”。
- 稳定错误码包括：`INVITATION_INVALID`、`INVITATION_PHONE_MISMATCH`、
  `INVITATION_EXPIRED`、`INVITATION_REVOKED`、`INVITATION_ALREADY_USED`、
  `VERIFIED_PHONE_TICKET_EXPIRED` 和 `REGISTRATION_INVITATION_REQUIRED`。

## 9. 安全、隐私与审计

- 手机号属于私密联系信息；邀请记录使用加密密文满足重发，使用 keyed HMAC 满足等值匹配，
  后台和日志只展示掩码。
- 验证码、邀请码、link token、verified ticket 不写日志、错误正文、分析事件或 crash report。
- 邀请尝试按 IP、手机号 HMAC、邀请码 digest 和设备维度限流；错误响应不暴露管理员备注。
- link token 使用至少 128 bit 随机值；8 位手工码排除易混淆字符并配合严格限流。
- 创建、发送、重发、撤销、核销和拒绝原因写审计日志，但 details 只保存资源 ID、状态枚举、
  手机号掩码和 actor，不保存凭证。
- 只有管理员可创建、列表、重发和撤销；用户创建后仍受既有 owner scope 和 session 安全约束。
- 本功能不触碰健康数据，也不产生医疗结论；安全风险集中在身份冒用、开放注册、凭证泄露、
  用户枚举和并发重复建号。

## 10. 异常与恢复

| 场景 | 用户/管理员行为 |
|---|---|
| 邀请无效 | 检查后重试；不透露是否曾存在 |
| 手机号不匹配 | 修改手机号或联系管理员 |
| 已使用 | 已有账号则直接手机号登录；否则联系客服 |
| 已撤销/过期 | 联系管理员重新发邀 |
| 验证码过期 | 保留手机号，重新获取验证码 |
| 短信发送失败 | 后台保留邀请，允许重发或复制凭证 |
| App 被终止 | SecureStore ticket 未过期则恢复等待邀请；否则重验短信 |
| 网络不确定 | 查询权威注册结果，不猜测成功、不重复核销 |

## 11. 验收矩阵

- 老用户无邀请码可以正常手机号登录。
- 新手机号即使短信验证码正确，没有邀请也不能创建账号。
- 正确邀请码与错误手机号、过期、撤销、已使用邀请均拒绝。
- 正确手机号和邀请只创建一个用户、只核销一次。
- 两设备并发核销仅一个成功，另一个得到幂等或明确冲突结果。
- 管理员与非管理员权限隔离；列表和审计无明文凭证或完整手机号。
- 深链、手工邀请码、App 重启恢复、短信失败重发和 onboarding 跳转均覆盖。
- iOS 真机验证短信自动填充、深链唤起、邀请核销和新用户 onboarding。

## 12. 上线与回滚

1. 先部署 migration、Backend 新接口和 feature flag，旧登录行为暂不收紧。
2. 上线管理员发邀页面并完成创建、发送、重发、撤销 smoke。
3. 发布 Mobile OTA，确认支持新联合响应和邀请深链。
4. 达到设定版本覆盖率后打开 server-side enforcement，禁止陌生手机号自动建号。
5. 删除生产默认邀请码旁路并关闭 `auth_phone_registration_auto_approve`。
6. 真机验证老用户登录、无邀请拒绝、受邀注册、二次使用拒绝。
7. 观察 7 天的发邀成功率、邀请到注册转化、短信失败、错绑/过期和老用户登录失败率。

回滚优先关闭新用户注册入口，而不是重新开放任意手机号自动建号。Backend 保留老用户登录；
管理员可以继续查看和撤销已创建邀请。migration 采用向前兼容，不在紧急回滚中删表。

## 13. 非目标

- 用户自助申请邀请码。
- 邀请裂变、多级关系或联系人批量导入。
- 用邀请码替代老用户每次登录凭证。
- 修改家庭邀请码语义。
- 把健康问卷塞进注册 Gate；健康资料仍在 onboarding 收集。

