# Dossier: TokenPlan HappyHorse 短视频链路

| 字段 | 值 |
|---|---|
| slug | `tokenplan-happyhorse-video` |
| 创建日期 | 2026-07-22 |
| 当前阶段 | S8 上线验证 |
| 状态 | complete |
| 负责 | Codex |
| 反馈环 | backend deploy；客户端复用既有 AIGC 卡片，无 OTA |

## S0 · 用户需求（逐字）
> tokenplan 支持了 happyhorse 模型 api 集成进来 aigc 短视频走这个链路的调用

- 谁用 / 解决什么：小巴 Agent 用户在明确确认 AIGC 短视频后，通过已有 TokenPlan 套餐调用 HappyHorse，替代授权异常的旧 Wan 视频提交链路。
- 当前绕过：旧链路使用独立 DashScope AIGC 凭证；授权异常时任务直接失败。

## S1 · Discovery
- 已有可复用：`aigc_media_service.py` 已实现异步提交、轮询、取消和安全错误；`aigc_media_job_service.py` 已实现确认、幂等、配额、结果落盘和恢复；模型注册表已登记 HappyHorse 1.1。
- 缺口：provider 明确拒绝 TokenPlan 域名与凭证，视频模型仍绑定 Wan；轮询没有按任务模型选择凭证域。
- 官方协议：TokenPlan 团队版支持 `happyhorse-1.1-t2v/i2v/r2v`；HappyHorse 使用 `video-synthesis` 异步任务协议，结果 URL 仅 24 小时有效。
- 安全边界：继续要求用户点击确认；不自动生成、不自动切到按量计费；不记录 prompt/API key；历史 Wan 任务必须继续可轮询。

## G1 · 准入裁决
- first_class_objects：Agent Run、AIGC confirmation、AIGC media job。
- core_loop_step：用户请求 → Agent 草稿 → 用户确认 → provider 执行 → 回执/结果卡。
- target_surface / safety_level / autonomy_tier：Agent 对话；中等成本与隐私风险；`manual_confirm`。
- spec_required：否，保持既有产品行为，仅替换 provider 路由与模型能力。
- smallest_end_to_end_slice：T2V/I2V 提交、轮询、取消、持久化结果。
- stale_surface_to_remove：旧的“TokenPlan 仅文本、禁止媒体”代码注释与拒绝测试。
- **裁决：PASS**。用户已明确要求实施。

## S2/S3 · Tech Spec 与规划
1. 图片生成保留 Wan/标准 DashScope；短视频改用 TokenPlan 专用 AIGC base URL 与 `sk-sp-` key。
2. 新任务使用 `happyhorse-1.1-t2v` / `happyhorse-1.1-i2v`；按模型选择提交、轮询、取消域。
3. HappyHorse T2V 使用 3–15 秒、支持 ratio；I2V 由首帧决定比例，不发送 ratio/prompt_extend。
4. 加契约测试、配置样例、日志 provider/model 维度；真实上线验证只验证配置/鉴权，不自动创建计费任务。

## G2 · 可行性 + 安全压测
- 协议可行：TokenPlan 与标准 Model Studio 视频均使用 `/api/v1/services/aigc/video-generation/video-synthesis` 和 `/api/v1/tasks/{task_id}`。
- 关键防错：禁止把 `/compatible-mode/v1` 当媒体端点；TokenPlan 视频凭证必须为 `sk-sp-`；失败不静默回退按量计费。
- **裁决：PASS**。用户已确认 provider 切换方向。

## S4 · 研发任务
- [x] T1 官方协议与当前链路核对。
- [x] T2 provider 双凭证/双域路由与 HappyHorse payload。
- [x] T3 job model 绑定、历史任务恢复与配置契约。
- [x] T4 聚焦测试、部署、线上非计费验证。

## S5 · 实现
- 图片继续使用标准 Model Studio；T2V/I2V 默认使用 TokenPlan `sk-sp-` 凭证和专用 AIGC 域。
- 新任务冻结 `happyhorse-1.1-t2v` / `happyhorse-1.1-i2v` 模型；轮询与取消按持久化模型选域，历史 Wan 任务继续可恢复。
- TokenPlan 模式严格限定 HappyHorse 模型，未知模型 fail closed，不会静默转按量链路。
- 运维聚合增加 `by_model`，管理员页可直接核对 HappyHorse/Wan 任务分布。

## G3 · 测试闸
- `118 passed`：AIGC provider/job/confirmation/API/tasks、模型注册、Agent 工具门控与运维聚合。
- `36 passed`：新增 provider fail-closed 与监控模型维度专项测试。
- TypeScript `tsc --noEmit`、目标 ESLint、Python compileall、`git diff --check` 均通过。
- **裁决：PASS**。

## G4 · 安全闸
- 不改变健康建议或用户数据写路径；保持人工确认、幂等、配额、结果私有落盘。
- 日志仅记录 job/kind/error type/status/error code，不记录 prompt、图片 URL 或 API key。
- TokenPlan key 只用于视频专用域；图片凭证缺失时明确失败，不复用 TokenPlan key；未知模型不回退按量。
- **裁决：PASS**。

## S6–S8
- 本地配置非敏感检查通过：TokenPlan key 已配置且前缀为 `sk-sp-`，provider/model 使用安全默认值。
- 实现提交：`31f733d5f203`，已推送 `origin/main`。
- G5 部署健康：标准 `deploy.sh -a -y` 完成；数据库备份、231 表恢复演练、站外加密归档通过；前端在线；后端健康评分 `60/60 PASS`；线上代码版本与实现提交一致。**裁决：PASS**。
- G6 上线验证：生产环境解析为 `provider=tokenplan`、专用 `/api/v1` 域、`happyhorse-1.1-t2v/i2v`；视频 key 已配置且 `sk-sp-` 前缀正确；公开健康端点显示 API/DB/Redis/Celery 全部 healthy。验证未创建计费任务，实际生成仍由用户点击确认卡触发。**裁决：PASS**。
