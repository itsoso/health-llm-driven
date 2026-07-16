# 受控应用更新平面 PRD

> 状态：P0 待发布验证
> 日期：2026-07-16

## 1. 目标

把“Mobile OTA 快速迭代、原生发版控制能力边界、Remote Config 控制、回滚保证稳定性”落成一个可审计的生产更新闭环，避免错误 bundle、错误 runtime 或不可兼容的原生能力进入用户设备后只能人工排查。

## 2. 产品对象与核心循环映射

| 对象 | 映射 |
|---|---|
| `ExecutionEvent` | 更新检查、下载、应用、失败、启动来源、回滚事件 |
| `HealthAgendaItem` | 本切片只影响更新后的健康行动可达性，不改变医疗建议 |
| 工程基础设施 | 远程发布策略、发布 manifest、回滚指针、Admin 观测 |

核心循环位置：保证 `Agenda top action -> Mobile 执行` 的客户端版本可用性。

## 3. 一期范围

### 3.1 包含

1. Remote Config 发布策略：OTA 开关、channel、最低原生 build、推荐 build、强制更新、kill switch、配置版本和过期时间。
2. 客户端安全读取：缓存 last-known-good 配置；远程配置不可用时不强制更新、不改变安全核心行为。
3. OTA 更新生命周期事件：检查、发现、下载、应用、失败、启动来源。
4. OTA 发布 manifest：commit、runtime、channel、update group、update id、已验证版本。
5. Mobile 手工回滚脚本：把指定已验证 update 重新指向生产发布入口，并留下回滚记录。
6. Admin 读取/更新策略和查看更新事件聚合。

`forced_update` 只在 OTA 已下载完成后生效：端上保留“立即更新”，隐藏“稍后”；不会静默重载，也不会在下载阶段阻断聊天、健康记录或草稿。

### 3.2 不包含

- 本期不做自动推进的实验编排；提供管理员手工配置的百分比门控和稳定 cohort，便于小范围验证后再扩大。
- 本期不自动根据崩溃循环回滚；先记录启动异常和 `isEmergencyLaunch`，下一期再做自动回退。
- 不通过 Remote Config 修改药物剂量、疾病阈值、禁忌规则或 Safety Guardian 核心逻辑。
- 不把原生能力、Watch 扩展或权限变化伪装成 OTA。

## 4. 安全与隐私不变量

- Remote Config 失效或网络不可用：继续使用内置安全默认值和本地 last-known-good，不默认开启新能力。
- 版本不兼容：客户端拒绝应用 OTA，并提示原生发版。
- 更新前不丢失未发送文本、图片草稿、上传队列和健康记录写回状态。
- 更新 telemetry 只记录平台、channel、runtime、版本、update id、耗时、结果和错误码，不记录健康正文、图片、药物、基因和检查报告内容。
- Admin 写配置需要管理员权限、版本并发校验和审计日志。

## 5. 验收标准

1. 非管理员不能读取或修改全局发布策略的 Admin 写接口。
2. 客户端可以拿到策略并在配置失败时稳定降级。
3. 每次 OTA 生命周期至少有终态事件，事件不阻塞主流程。
4. OTA manifest 能证明发布物的 commit/runtime/channel/update id。
5. 指定已验证 update 的回滚命令具备 dry-run、明确确认和结果校验。
6. 现有 OTA、聊天草稿、语音输入和健康数据写入测试不回归。
