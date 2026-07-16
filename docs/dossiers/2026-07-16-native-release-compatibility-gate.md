# Dossier: 原生版本兼容门

| 字段 | 值 |
|---|---|
| slug | `native-release-compatibility-gate` |
| 创建日期 | 2026-07-16 |
| 当前阶段 | S2 PRD / S3 规划 |
| 状态 | in_progress |
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
- **状态：进行中。**

## G2 · 可行性与安全压测

- Remote Config 仍是发布控制，不进入医疗规则。
- URL 需要 allowlist，客户端再次校验，避免错误配置打开任意站点。
- 没有 URL 时保留可见提示但不渲染假按钮。
- **裁决：待实现后复核。**

## S4 · 任务分解

- [x] T1 需求/PRD/Plan/Dossier
- [ ] T2 后端字段、allowlist、migration、审计
- [ ] T3 Mobile 原生门、状态和提示
- [ ] T4 测试、类型、文档漂移验证
- [ ] T5 部署和生产验证

## S5 · 实现

- 分支：`main`
- 代码提交：待实现

## G3 · 测试闸

- 待实现。

## G4 · 安全闸

- 待实现：Admin 权限、URL allowlist、事件字段最小化。

## G5 · 部署健康

- 待实现。

## G6 · 上线验证

- 待实现。
