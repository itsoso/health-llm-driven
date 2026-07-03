# Dossier: 手机号一体化登录注册

| 字段 | 值 |
|---|---|
| slug | `phone-first-auth` |
| 创建日期 | 2026-07-03 |
| 当前阶段 | G4 安全闸 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | backend tests + mobile Jest + doc drift; deployment not run in this slice |

## S0 · 用户需求(逐字)

> 在注册登录上业界有没有最佳实践，一期先做手机号方式登录注册，后续再考虑其他方式。
> 开干

- 谁用 / 解决什么: 新用户和日常用户，减少账号密码注册摩擦，让移动端更快进入健康执行主路径。
- 锚点用户相关性: 移动端是日常健康执行入口，登录摩擦会阻断 Today / 阿衡 / 记录等主路径。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/api/auth.py`: 已有 JWT 登录、注册、密码修改、`/auth/me`。
  - `backend/app/services/auth.py`: 已有密码哈希、用户认证和 token 生成依赖。
  - `mobile/services/auth.ts`: 已有 token 存储与账号密码登录。
  - `mobile/app/login.tsx`: 已有登录 UI。
- 缺什么:
  - phone 字段和 verified 时间。
  - 一次性验证码模型、验证码发放/消费服务、生产短信通道。
  - 手机号登录/注册 API、移动端 phone-first UI、账号安全设置密码入口。
- 硬约束 / 安全边界:
  - 认证和手机号是 privacy-sensitive，生产不能回显验证码。
  - 验证码必须单次、限时、限尝试、哈希存储。
  - 生产短信未配置必须 fail-loud。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `ExecutionEvent`, `WriteIntent`
- core_loop_step: Mobile 登录入口 -> authenticated health execution loop
- target_surface / safety_level / autonomy_tier: Backend + Mobile / privacy_sensitive / none
- spec_required(§8.1): yes
- smallest_end_to_end_slice: request code -> verify code -> auto-register/login -> set/change password
- stale_surface_to_remove: none; account/password fallback kept
- **裁决**: PASS —— 这是降低核心日常入口摩擦的认证基础能力。

## S2 · PRD / Spec

- 链接: `docs/specs/active/2026-07-03-phone-first-auth.md`
- 边界(不做): 社交登录、微信登录、passkeys、MFA 策略、后台账号管理。
- 验收 Gate: backend phone auth tests, mobile auth/login/settings tests, generate-types, system-map doc drift.
- 未决问题: none.

## S3 · 规划

- 分阶段:
  - Backend: schema + migration + phone code lifecycle + login/register/password endpoints.
  - Mobile: auth service + phone-first login + account security settings.
  - Governance: generated types, system map, doc drift.
- 反馈环路由: 本次是代码与测试切片；上线/OTA 另走发布 Gate。

## G2 · 可行性 + 安全压测

- 评审方式: Codex challenge + safety-gate rules read.
- 硬阻断: 生产短信不可假成功，已通过 fail-loud 和 Aliyun SMS provider seam 处理。
- **裁决**: PASS。

## S4 · 研发任务分解

- 任务表:
  - [x] T1 Backend phone auth schema/migration/service/API.
  - [x] T2 Mobile auth service/login/settings UI.
  - [x] T3 Tests and generated contracts.
  - [ ] T4 Deploy / OTA / production smoke if requested.

## S5 · 实现

- 分支: `main`
- Commit: pending.

## G3 · 测试闸

- Backend: PASS, `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai pytest backend/tests/test_phone_auth.py backend/tests/test_auth_secrets.py backend/tests/test_users.py -q` -> 14 passed.
- Mobile: PASS, `npm test -- --runInBand services/__tests__/auth.test.ts app/__tests__/login.test.tsx app/__tests__/settings.test.tsx` -> 36 passed.
- TypeScript: PASS, `cd mobile && npx tsc --noEmit`.
- Type generation: PASS, `cd mobile && npm run generate-types`.
- Dossier/doc drift: PASS, `check_dossier_consistency.py`, `dump_system_map.py`, `check_doc_drift.py`.
- Hygiene: PASS, `git diff --check`.
- **裁决**: 绿。

## G4 · 安全闸

- 触发: 认证 + privacy-sensitive。
- 安全处理:
  - phone masked in logs;
  - code hashed with HMAC;
  - one-time consume, TTL, attempt limit, resend cooldown;
  - production SMS unconfigured returns 503.
- Review notes:
  - Fixed direct phone logging in new-user registration; logs now use `mask_phone`.
  - Restricted API `purpose` to `login` for this phase to avoid advertising unimplemented reset/bind flows.
- **裁决**: GO for code merge; deploy/OTA remains a separate release Gate.

## S6 · 部署

- 路由: not run in this slice.
- 序: backend deploy -> mobile generate-types already included -> mobile OTA/QR if requested.

## S7 · 上线验证

- Not run.

## S8 · 沉淀

- Updated spec + dossier.
- Updated system map generated snapshot and architecture drift counts.
