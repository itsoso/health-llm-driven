# Dossier: 原生版本兼容门

| 字段 | 值 |
|---|---|
| slug | `native-release-compatibility-gate` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | S7 上线验证 |
| 状态 | verified |
| 负责 | Codex |
| 关联能力 | 受控应用更新平面 |

## S0 · 用户需求

> Mobile OTA 负责快速迭代，原生发版负责安全和能力边界，Remote Config 负责控制，回滚系统负责生产稳定性。还需要做什么？
>
> 继续

本切片承接上一期 S8：原生 App Store 强制升级页进入下一期。当前先实现策略判断、可解释提示和安全商店入口，不假设 App Store 已经上架。

## S1 · 现状

- `mobile/services/remoteConfig.ts` 已有最低/推荐 native build 判断，但不满足最低版本时只返回 `idle`。
- `mobile/hooks/useAppUpdate.tsx` 没有向 UI 暴露原生升级原因。
- `AppUpdateBanner` 只处理 OTA ready/applying。
- 后端发布策略没有商店 URL 字段。

## G1 · 准入裁决

- first_class_objects：发布策略 + Mobile 更新状态。
- target_surface：Backend Admin/Remote Config + Mobile 更新提示。
- safety_level：L2 工程发布安全；不修改医疗规则。
- smallest_end_to_end_slice：策略写入官方链接 → 客户端判断 native build → 阻断不兼容 OTA → 显示并尝试打开官方商店。
- **裁决：PASS。**

## S2 · PRD

- 链接：`docs/prd/2026-07-16-native-release-compatibility-gate.md`
- **状态：完成。**

## S3 · 规划

- 链接：`docs/plans/2026-07-16-native-release-compatibility-gate.md`
- **状态：完成。**

## G2 · 可行性与安全压测

- Remote Config 仍是发布控制，不进入医疗规则。
- URL 需要 allowlist，客户端再次校验，避免错误配置打开任意站点。
- 没有 URL 时保留可见提示但不渲染假按钮。
- **裁决：PASS。** 后端与客户端均有 URL allowlist；没有商店链接时不渲染假按钮；原生门不修改医疗规则。

## S4 · 任务分解

- [x] T1 需求/PRD/Plan/Dossier
- [x] T2 后端字段、allowlist、migration、审计
- [x] T3 Mobile 原生门、状态和提示
- [x] T4 测试、类型、文档漂移验证
- [x] T5 部署和生产验证

## S5 · 实现

- 分支：`main`
- 代码提交：`5af4053a1`；并发提交以普通 merge 合入，最终生产主干为 `26fc7bb2d`，已推送 `origin/main`

## G3 · 测试闸

- Backend：策略/事件/观察聚合相关 76 passed；managed migration 15 passed。
- Mobile：更新相关 32 passed；TypeScript、ESLint 通过。
- `check_doc_drift.py`、`check_dossier_consistency.py`、`git diff --check` 通过。
- **裁决：PASS。** 原生门事件不进入 OTA 失败率分母。

## G4 · 安全闸

- Admin 写入保留鉴权、并发版本校验与审计；商店链接只允许官方 HTTPS host；事件仅记录 build、phase、duration 等无健康正文元数据。
- **裁决：PASS。**

## G5 · 部署健康

- `./deploy.sh -b -y` 完成；managed migration `20260716_210000_add_native_update_url` 已应用，随后从最终主干 `26fc7bb2d` 再次部署并确认已跳过该 migration。
- production `/api/v1/health` 返回 `healthy`，API/database/redis/celery 均正常；部署健康 `60/60 PASS`。
- 远程 `information_schema` 已确认 `native_update_url` 列存在。
- **裁决：PASS。**

## G6 · 上线验证

- Mobile OTA 已发布：runtime `1.3.1`，group `3ad04246-9480-4380-9e12-94ea1d553b7c`，iOS update `019f6afa-7f57-71dd-88c2-b582f05f79d2`。
- EAS `update:view` 返回 commit `5af4053a1f0400fd2cc111bfcd34104b90d4e464`，与生产 `main` 一致。
- **裁决：PASS。**
