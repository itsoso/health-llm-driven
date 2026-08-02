# Feature Spec: Mobile 邀请制手机号注册

> Status: approved_definition
> Owner: Codex
> Updated: 2026-08-01
> Related design: `docs/plans/2026-08-01-mobile-invited-phone-registration-design.md`
> Related code: `backend/app/api/auth.py`, `backend/app/api/invitation.py`, `mobile/app/login.tsx`

## 1. Decision

已注册手机号继续无邀请码登录；陌生手机号只有在管理员预先创建了绑定该手机号的单次邀请，
并同时通过短信验证码后才允许创建账号。

## 2. Problem

Mobile 当前把验证码登录和注册合并，陌生手机号在验证码正确后会自动创建账号。已有通用
邀请码不绑定手机号，也没有接入 Mobile 手机号路径。继续保持现状会让邀请制形同虚设，
增加未授权账号、短信滥用、用户枚举和健康数据租户边界的攻击面。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 管理员发出绑定手机号的邀请码后，新用户才能手机号注册；老用户照常登录
  classification: security + infrastructure + new_product_behavior
  first_user_fit: 保护首批高敏感健康数据用户的受控准入与服务容量
  core_loop_step: 核心循环之前的身份与租户安全边界
  first_class_objects: none; identity-perimeter infrastructure exception, no health object semantics changed
  target_surface: Mobile primary login + Web admin + Backend auth source of truth
  source_of_truth: PostgreSQL RegistrationInvitation + Backend auth transaction
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: admin-authenticated invitation audit + verified phone ownership
  claim_hedging: n/a
  verification_window: immediate registration result + 7-day rollout observation
  success_metric: 0 uninvited new accounts; no increase in existing-user login failure
  added_user_burden: invited new user enters/opens one invitation credential; existing users unchanged
  burden_justification: closes unrestricted registration while keeping one-session onboarding
  non_goals: self-service applications, referral growth, family invitations, health questionnaire gating
  smallest_end_to_end_slice: admin binds phone and sends invite -> phone OTP -> atomic consume/create -> onboarding
  stale_surface_to_remove_or_archive: remove Mobile “登录/注册” ambiguity and unknown-phone auto-create path
  spec_required: yes
```

G1 裁决：`PASS`。该需求不引入 Health OS 一等对象，按认证安全基础设施例外准入；它不得
被扩成社交增长系统，也不得把邀请码作为健康 WriteIntent。

## 4. Non-Goals

- 不限制已注册用户的日常手机号登录。
- 不复用或改变家庭邀请码。
- 不做用户自助申请、邀请裂变或联系人导入。
- 不在注册 Gate 收集健康问卷。
- 不依赖 LLM 做身份、邀请码或审批决策。

## 5. Product Object Mapping

本功能是核心循环之前的身份安全基础设施，不改变 Health OS 一等对象或健康状态语义。

## 6. User Flow

```text
admin confirms masked phone
  -> backend creates and sends bound invitation
  -> user verifies phone OTP
  -> existing user logs in OR new phone receives one-time verified ticket
  -> backend matches invitation and phone in one transaction
  -> user created + invitation consumed + token issued
  -> Mobile onboarding
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 手机号、OTP、邀请深链/手工码和恢复状态 | 不自行判断资格；只按 Backend outcome 路由 |
| Web | 管理员创建、发送、重发、撤销和列表 | 仅管理员；只显示脱敏手机号与状态 |
| Backend | 准入真源、加密、匹配、核销、建号、token、审计 | PostgreSQL 原子事务；失败显式 |

## 8. Data Contract

```yaml
apis:
  - POST /admin/registration-invitations
  - GET /admin/registration-invitations
  - POST /admin/registration-invitations/{id}/resend
  - POST /admin/registration-invitations/{id}/revoke
  - POST /auth/phone/verify
  - POST /auth/invitations/inspect
  - POST /auth/invited-registration
events:
  - invitation_created
  - invitation_send_terminal
  - invitation_consumed
  - invited_registration_terminal
models:
  - RegistrationInvitation
enums:
  - created
  - sent
  - send_failed
  - consumed
  - revoked
  - expired
backward_compatibility: existing phone users continue to authenticate without invite
migration: additive PostgreSQL managed migration; no emergency down migration
```

## 9. Safety, Privacy, And Medical Boundary

- 手机号密文用于投递，keyed HMAC 用于匹配，后台只返回掩码。
- 邀请码、deep-link token、OTP 和 verified ticket 不进入日志、遥测、错误详情或普通存储。
- 邀请操作和核销写审计日志；审计只保存资源 ID、actor、状态枚举和手机号掩码。
- 管理员权限由 Backend 强制，Mobile/Web UI 隐藏不构成授权。
- 无健康数据、药物、诊断或医疗结论；不需要 SafetyGuardian 医疗规则。
- 实现提交必须按项目 `safety-gate` 做独立认证/隐私复核，`GO` 后才能部署。

## 10. AI Behavior

无 LLM 参与。任何邀请资格、手机号匹配、核销和注册结果均为确定性 Backend 逻辑。

## 11. Acceptance Criteria

```gherkin
Given an existing active approved phone user
When the user verifies a valid OTP without an invitation
Then the backend issues a login token and consumes no invitation

Given a verified phone that has no user and no matching invitation
When registration is attempted
Then no user is created and REGISTRATION_INVITATION_REQUIRED is returned

Given an admin-created active invitation bound to a phone
When that phone proves OTP ownership and submits the invitation
Then exactly one user is created, the invitation is consumed once, and onboarding starts

Given two concurrent requests for the same invitation
When both attempt registration
Then at most one creates a user and no duplicate phone account exists

Given a non-admin caller
When invitation administration is attempted
Then the backend returns 403 and writes no invitation mutation
```

## 12. Verification Plan

```bash
# Backend focused PostgreSQL auth/invitation/concurrency tests
# OpenAPI regeneration and client type drift
# Mobile login/invite/deep-link/SecureStore tests + TypeScript
# Frontend admin invitation tests + build
# Repo doc drift + dossier consistency + git diff --check
# iOS real-device OTP autofill, deep link, invited registration, old-user login
```

## 13. Rollout And Rollback

使用 server-side enforcement flag 分阶段上线：Backend additive schema/API → Admin → Mobile OTA →
覆盖率确认 → 禁止陌生手机号自动建号 → 移除默认邀请码旁路。回滚时关闭新用户注册，保留
老用户手机号登录；绝不以重新开放无邀请注册作为自动回滚。

## 14. Open Questions

无阻塞问题。国际短信国家范围、邀请默认有效期是否按租户配置属于后续增量。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-01 | Approved definition | 用户确认绑定手机号、短信+手工兜底、发邀即审批 |

