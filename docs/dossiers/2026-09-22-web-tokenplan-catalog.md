# Web TokenPlan 模型目录刷新

| 字段 | 值 |
| --- | --- |
| 状态 | in_progress |
| 当前阶段 | 本地验证与发布前安全复核 |
| Overlay | safety-gate |

## G1 — 准入

裁决: PASS

用户要求获取阿里云最新模型并更新 Web，明确要求使用已有 TokenPlan API Key，不依赖网页登录。
只更新目录、兼容 ID 和测试，不修改用户已选模型、默认模型、认证、健康写入权限或计费通道。

## 根因与修改

- Web 独立白名单仍只有 Qwen3.8 preview，过滤了后端已注册的正式 Max、Flash 及 DeepSeek V4 Pro 0813。
- 恢复上述模型可见性；新增通过真实 API 确认的 DeepSeek V4.1 Flash 和 GLM-5.3。
- 两个新型号 `reliable_tool_calling=False`，不提升思考预算、强制工具或缓存能力。工具轮继续使用现有可靠模型门控，纯文本回答可以使用用户选中的新型号。
- `auto` 虽出现在官方目录中，但底层路由、归因和工具兼容性尚未验证，本次不加入固定模型选择器。图片、音频和视频模型不进入聊天菜单；不恢复旧代模型。
- Mac 默认目录、Mobile allowlist 仅同步兼容性源码；本次用户指定的发布范围为 Web 及依赖的后端，不包含 native App 构建安装或 Mobile OTA。
- 新增 Web/Mobile/Mac 目录与后端 chat catalog 的一致性闸，防止仅更新后端导致客户端漏显示。

## 来源与可用性边界

- 2026-09-22 北京时间，已有 TokenPlan 配置调用官方 `/compatible-mode/v1/models` 返回 HTTP 200；未输出、保存或提交密钥。
- 能力来源为当日打开的阿里云 Token Plan 个人版、团队版官方文档。搜索摘要比正文旧，以实时正文及认证 API 为准。
- 变更相关快照：`docs/model-snapshots/tokenplan-2026-09-22-web-refresh.json`。它是增量快照，不是完整套餐清单。
- 真实合成文本探针：DeepSeek V4.1 Flash、GLM-5.3、Qwen3.8 Flash、DeepSeek V4 Pro 0813 均 HTTP 200，响应型号与请求一致，正文非空，finish_reason=stop。未发送用户健康信息；文本探针不代表完整工具调用、视觉能力或医疗质量评估通过。
- Pro 0813 未出现在本次 `/models` 响应，但官方文档仍列出，直接合成聊天请求成功，因此保留其已有注册并恢复 Web 显示。
- 未查询套餐价格、剩余额度或变更订阅；不把 API 目录响应等同于所有模型质量和所有协议兼容性。

## 验证与发布状态

- RED：Web 旧白名单 3 项回归失败，后端新增目录与一致性检查 5 项失败；未绕过旧过滤器。
- Web 全量测试 401 项通过，Next.js 生产构建通过；模型菜单定向测试 8 项通过。
- 后端注册表、factory、任务路由、工具门控与模型覆盖定向测试通过；Mobile 目录测试及 TypeScript 通过，Mac 目录测试通过。
- 后端 CI-mode `k-m-rest` 与 `agent-executor-i-z` 两个相关分片合计 1,634 项通过、5 项跳过；System Map、文档一致性与秘密扫描通过。
- 安全复核、精确 SHA CI、生产发布与线上菜单验收尚待完成，不能据此宣称线上已更新。

## 巡检衔接

已只读核对现有 `aliyun-tokenplan` 三天巡检任务，当前提示只列后端和 Mobile，未列 Web 白名单。本次未修改定时任务或其他仓库。新增代码一致性测试使后续漏同步 Web 时直接失败。
