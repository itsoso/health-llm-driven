# Dossier: Mobile 邀请制手机号注册

| 字段 | 值 |
|---|---|
| slug | `mobile-invited-phone-registration` |
| 创建日期 | 2026-08-01 |
| 当前阶段 | G5 部分完成；后端已 dormant 部署，等待生产邀请配置后继续 |
| 状态 | shipping · backend deployed fail-closed, OTA/enforcement pending |
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

- [x] Managed PostgreSQL migration + `RegistrationInvitation` model/repository
- [x] 管理员创建/列表/重发/撤销 API 与审计
- [x] SMS 注册邀请模板与失败语义
- [x] Phone verify outcome + verified ticket + invited registration transaction
- [x] Mobile 邀请深链、手机号/OTP/邀请码状态机与 SecureStore 恢复
- [x] Web 管理员邀请视图
- [x] OpenAPI/client types、focused/concurrency/privacy tests
- [ ] 分阶段 enforcement、OTA、生产 smoke 与真机 G6

## S5 · 实现

- Backend 新增绑定手机号的单次邀请、短时 verified-phone grant、原子核销建号、管理端发送/重发/撤销和无敏感数据聚合观测。
- Mobile 实现 OTP outcome 分流、邀请深链/手工码、SecureStore 恢复、onboarding 衔接与防残留凭据复活的 logout tombstone。
- Web 管理面板实现手机号脱敏确认、有效期、发送终态、一次性凭据展示和 legacy 邀请码分区。
- Rollout 四态已收口：旧版兼容窗、完全强制、安全回滚关闭新注册、本地 legacy-only。手机号、微信、旧邀请、管理员创建/审批和账号合并旁路均已 fail-closed。
- 实现提交为 `e2ad25fa..e966281c`；已进入 `main`，生产后端以 rollout/enforcement 均关闭的 dormant 模式部署。

## G3 · 测试闸

- Backend 扩大认证/邀请/安全集：`222 passed, 6 skipped`；条件跳过项后续在真实 PostgreSQL 专项中通过。
- 阻塞 CI 的真实 PostgreSQL job：`149 passed, 0 skipped`，覆盖双 session 邀请注册、OTP grant、错误尝试计数、grant 核销、同源账号合并竞争和 migration 重放约束；CI 静态契约防止节点被移除后假 skip。
- Mobile 全量：`292/292 suites`，`2382 passed, 1 skipped`；TypeScript 通过，Expo lint `0 errors`。
- Web 全量：`57 files / 335 tests passed`；TypeScript 通过，lint `0 errors`，production build `73/73` 页面通过。
- OpenAPI 用 CI 固定版 `openapi-typescript@7.13.0` 临时生成，Mobile/Web 类型均逐字节一致。Doc drift、dossier consistency 和 `git diff --check` 通过。
- **裁决：PASS。** 相关全集与生产数据库语义均为绿，允许进入 G4。

## G4 · 安全闸

- 独立 safety/privacy reviewer 对未知用户旁路、用户枚举、OTP/grant/invite replay、并发双建号、PII/凭据泄漏、非管理员写入、rollout fail-open、旧客户端兼容、深链与本地存储进行多轮攻击性审查。
- 所有 NO-GO 项已返回上游加 RED 测试并修复：严格密文读取 fail-closed、OTP provider 异常脱敏、管理员/微信/旧注册旁路封闭、幂等恢复过期限制、自助账号合并停用、管理员合并锁/原子终态审计/never-throw 失败边界，以及 Mobile 两阶段 logout tombstone 与 epoch 竞态隔离。
- 最终独立复审结论：**GO**，未发现剩余代码级安全/隐私阻断项。
- 非阻断运营风险：iOS 卸载时 AsyncStorage 与 Keychain 生命周期不同，后续宜增加服务端 token 撤销或 Keychain 同生命周期 generation marker；PostgreSQL 连接中断仍有 commit 结果不确定窗口，运维重试前必须先查 `admin_user_merge_completed` 终态审计。
- **裁决：PASS / GO。** 允许进入 G5，不代表已部署。

## G5 · 部署健康闸

**PARTIAL / BLOCKED**：2026-08-02 已用根目录 `deploy.sh -b` 将 `e966281cd50b45bbf98bd623923705b9b2cce2c0` 部署到生产，保持 registration invitation rollout/enforcement 默认关闭。

- 发布前数据库备份、234 表恢复演练、站外加密归档哈希/HMAC 校验均通过；旧备份按保留 7 份策略清理。
- managed migration `20260801_230000_registration_invitations` 已应用，完整 runtime schema probe 通过。
- 发布事务已 `COMMITTED` / `finalized`，远端 SHA 两次核验一致，部署后健康分三次均为 `60/60 PASS`。
- 后端进程为 `active (running)`，`GET /api/v1/health` 返回 200；公开无凭据探测 `POST /api/v1/auth/invitations/inspect` 返回 `403 REGISTRATION_CLOSED`，证明路由已部署且新注册 fail-closed。
- 当前生产配置缺少稳定的 `REGISTRATION_INVITATION_DIGEST_KEY`、独立审核的 `REGISTRATION_INVITATION_SMS_SIGN_NAME` 与 `REGISTRATION_INVITATION_SMS_TEMPLATE_CODE`。按安全约束不得复用 OTP 模板或虚构配置，因此管理员真实发邀 smoke、Mobile OTA 和 enforcement 尚未执行。
- 2026-08-03 用户明确要求发布 production OTA；发布源为干净 `main` 提交 `d19c536032f3e815cf20649734eb73fd45804543`，CI 全绿且发布前 Mobile TypeScript 复验通过。iOS bundle 三次均成功导出（Hermes 两次、官方 `--no-bytecode + --skip-bundler` 兜底一次），但 EAS 对唯一 launch asset 的服务端 processing 全部超时，命令在生成 update group/ID 前 fail loud。production channel 查询仍指向上一已知可用 runtime `1.3.2`、group `5ae84fdf-0e71-4121-a34a-86dd6a747f51`、iOS update `019fc0af-ce41-7259-8800-1d3451bb3682`；没有半发布或错误切换。该故障与 Garmin dossier 已记录的 EAS per-asset processing 故障一致，重复同哈希上传已有失败证据，因此不继续无界重试。
- **裁决：G5 尚未 PASS。** 配置就绪后必须按 rollout=true/enforcement=false → 受控手机号管理员发邀 smoke → Mobile OTA → 覆盖率确认 → enforcement=true 的顺序继续。

## G6 · 验证闸

**PENDING**：需真机证明老用户登录、无邀请拒绝、受邀注册、邀请不可二次使用，以及注销后残留 token/pending registration 不复活。

## S8 · 沉淀

- 系统结构快照已通过 `scripts/dump_system_map.py` 重新生成，架构计数继续以代码派生文件为唯一真源。
- G5 已回填 dormant 后端部署、迁移与健康分；配置就绪后继续回填管理员 SMS smoke、OTA 标识、enforcement 和真机证据。
