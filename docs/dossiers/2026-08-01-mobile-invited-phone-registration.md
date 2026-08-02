# Dossier: Mobile 邀请制手机号注册

| 字段 | 值 |
|---|---|
| slug | `mobile-invited-phone-registration` |
| 创建日期 | 2026-08-01 |
| 当前阶段 | S3 设计已确认，待实施规划 |
| 状态 | definition_approved |
| 负责 | Codex |
| 反馈环 | Backend PostgreSQL auth tests / Mobile Jest + TypeScript / Web tests / iOS real device |

## S0 · 用户需求（逐字）

> 要支持基于邀请码注册，不能随意注册，管理员发送邀请码之后，才能手机号登录，设计这个链路，在手机上

已确认决策：

- 邀请只限制新手机号首次注册；已注册用户以后手机号登录无需邀请码。
- 邀请必须预绑定目标手机号。
- 默认由系统短信发送“邀请链接 + 8 位邀请码”，管理员复制凭证作为兜底。
- 管理员创建并发送邀请即代表审批通过，不再二次人工审核。

## S1 · Discovery

- `backend/app/api/auth.py` 的手机号验证码路径会对陌生手机号自动创建用户。
- `mobile/app/login.tsx` 当前主路径文案为“登录 / 注册”，没有邀请输入或深链状态。
- Backend 有通用 `InvitationCode` 和 Web 管理界面，但邀请码不绑定手机号；家庭邀请码是
  不同业务对象，不能混用。
- 可复用现有 SMS provider、手机号规范化、OTP、防重用户索引、SecureStore token 持久化、
  管理员权限和审计基础设施。
- 硬约束：PostgreSQL；认证/手机号为 privacy-sensitive；失败必须 fail loud；老用户登录
  不得回归；邀请码核销和用户创建必须原子化。

## G1 · 准入

- classification：security + infrastructure + new product behavior。
- target surface：Mobile 登录、Web 管理员、Backend auth source of truth。
- safety：privacy-sensitive；manual confirm；无医疗结论。
- 身份安全基础设施例外：不引入 Health OS 一等对象，不得伪映射为健康 WriteIntent。
- smallest slice：管理员绑定手机号发邀 → OTP → 邀请核销/建号 → onboarding。
- **裁决：PASS**。用户已确认全部准入决策。

## S2 · PRD / Feature Spec

- Feature Spec：`docs/specs/active/2026-08-01-mobile-invited-phone-registration.md`
- 产品决策：老用户零新增摩擦；新用户只增加一次邀请凭证；Backend 决定所有资格。
- 非目标：自助申请、裂变、联系人导入、家庭邀请码、注册健康问卷。

## S3 · 设计

- 设计：`docs/plans/2026-08-01-mobile-invited-phone-registration-design.md`
- 实施计划：`docs/plans/2026-08-01-mobile-invited-phone-registration.md`
- 采用绑定手机号的一次性邀请；邀请链接自动填入，8 位码手工兜底。
- 新 `RegistrationInvitation` 保存手机号密文 + HMAC、凭证 digest、状态和审计元数据。
- 邀请核销、用户创建和 token 签发在一个 PostgreSQL 事务边界内完成。
- 用户逐节确认架构、Mobile 动线、管理员/API 和异常/上线设计。

## G2 · 可行性 + 安全压测

- 平台可行性：现有 OTP、SMS provider、Mobile SecureStore、管理员鉴权和 PostgreSQL 可复用。
- 已前置约束：不复用家庭邀请码；不存明文凭证；不因回滚开放任意注册；并发核销行锁；
  老用户兼容；稳定错误码；SMS 失败显式。
- 实现仍需项目 `safety-gate` 独立认证/隐私评审；当前定义环不冒充代码安全 `GO`。
- **裁决：PASS（定义环）**。无待拍板阻塞项，可以进入实施规划。

## S4 · 需求分解

- [ ] Managed PostgreSQL migration + `RegistrationInvitation` model/repository
- [ ] 管理员创建/列表/重发/撤销 API 与审计
- [ ] SMS 注册邀请模板与失败语义
- [ ] Phone verify outcome + verified ticket + invited registration transaction
- [ ] Mobile 邀请深链、手机号/OTP/邀请码状态机与 SecureStore 恢复
- [ ] Web 管理员邀请视图
- [ ] OpenAPI/client types、focused/concurrency/privacy tests
- [ ] 分阶段 enforcement、OTA、生产 smoke 与真机 G6

## G3 · 测试闸

`PENDING`：尚未实现。

## G4 · 安全闸

`PENDING`：认证改动实现提交后必须独立 safety/privacy reviewer `GO`。

## G5 · 部署健康闸

`PENDING`：尚未部署。

## G6 · 验证闸

`PENDING`：需真机证明老用户登录、无邀请拒绝、受邀注册和邀请不可二次使用。

## S8 · 沉淀

定义完成后将 Mobile 登录/注册与管理员邀请流同步到 system-map product/mobile nav map；
架构计数只能由生成器更新，不手写。
