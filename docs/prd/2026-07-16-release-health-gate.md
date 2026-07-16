# 小巴发布健康门 PRD

> 版本：v1.0
> 日期：2026-07-16
> 状态：P1 实施中
> 关联能力：Controlled App Update Plane

## 1. 背景

小巴已经具备 Remote Config 控制、稳定安装分组、OTA 生命周期埋点和人工回滚脚本。下一步必须回答一个生产问题：新版本发布后，是否正在正常启动和完成更新，是否应该继续放量。

当前只能看到更新检查和终态数量，不能把“启动来源”“更新失败”转成一个明确的运维判断。没有这个判断，灰度依赖人工看原始数据，容易出现发现晚、判断不一致和误回滚。

## 2. 产品目标

在 Admin 观察看板中提供发布健康门：

- 以固定窗口聚合 `app_update_launch` 和 `app_update_terminal`；
- 给出样本量、异常启动率、更新失败率和可解释的状态；
- 样本不足时明确标记 `observe`，不把“没有数据”误报为健康；
- 达到暂停阈值时给出 `pause_rollout`，但不自动修改策略或执行回滚；
- 全过程不读取、不存储用户健康正文。

## 3. 非目标

- 本期不自动调用 EAS rollback / republish；
- 本期不做原生 App Store 强制升级页；
- 本期不把异常启动等同于系统崩溃，`emergency` 只作为客户端启动自救信号；
- 不把用户 ID、消息正文、健康数据、设备序列号加入埋点。

## 4. 判定规则

### 4.1 输入

仅使用当前窗口内的客户端事件：

- `app_update_launch`：按 `launch_source` 统计 `ota`、`embedded`、`emergency`、`unknown`；
- `app_update_terminal`：按 `phase` 统计 `ready`、`failed` 等终态。

### 4.2 状态

| 状态 | 条件 | 含义 |
|---|---|---|
| `observe` | 更新启动样本 `< 20` | 样本不足，只观察，不做放量裁决 |
| `healthy` | 样本 `>= 20`，且紧急启动率 `< 5%`、更新失败率 `< 10%` | 可继续观察和放量 |
| `pause_rollout` | 样本 `>= 20` 且紧急启动率 `>= 5%`，或更新失败率 `>= 10%` | 建议管理员暂停放量，人工核验后决定回滚 |

分母定义：

- 紧急启动率 = `emergency / launches`；
- 更新失败率 = `failed / (ready + failed)`，没有完成或失败终态时为 `null`；
- 低于最小样本量时，即使比例异常也只能是 `observe`，防止单个设备误报全局。

### 4.3 结果结构

```json
{
  "status": "observe",
  "sample_sufficient": false,
  "thresholds": {
    "min_launches": 20,
    "emergency_rate_pct": 5.0,
    "terminal_failure_rate_pct": 10.0
  },
  "launches": 0,
  "emergency_launches": 0,
  "emergency_rate_pct": null,
  "terminal_attempts": 0,
  "terminal_failures": 0,
  "terminal_failure_rate_pct": null,
  "reasons": ["发布启动样本不足 20，继续观察"]
}
```

## 5. 交互与权限

- Admin 观察看板在 `client_events.app_update.release_health` 展示结果；
- `pause_rollout` 必须显示原因和原始计数，不能只显示颜色；
- API 仍由现有 Admin 权限保护；
- 这是“建议/闸门”，不是自动操作。真正暂停仍通过现有 Admin 发布策略接口并留下审计记录。

## 6. 验收标准

- 空窗口返回完整结构，状态为 `observe`，不把空数据标成 `healthy`；
- 19 个正常启动返回 `observe`；
- 20 个正常启动返回 `healthy`；
- 20 个启动中 1 个 `emergency` 返回 `pause_rollout`；
- 20 个终态中 2 个 `failed` 返回 `pause_rollout`；
- 按 `user_id` 过滤时不能混入其他用户事件；
- 既有 `client_events_stats` 返回结构除新增字段外保持兼容；
- 运行后端单测、漂移检查、Dossier 检查和生产健康检查。

## 7. 后续演进

满足真实样本和人工处置记录后，再评估：连续窗口自动暂停、原生升级引导、跨端发布健康门和经审批的自动回滚。任何自动动作必须先有独立审计、冷却时间和人工解锁机制。
