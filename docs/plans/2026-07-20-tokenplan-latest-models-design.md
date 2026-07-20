# TokenPlan 最新模型白名单设计

## 目标

以 2026-07-20 用户提供的百炼 TokenPlan 清单作为唯一 TokenPlan 白名单，新增
`qwen3.8-max-preview` 与 HappyHorse 视频模型，纠正 GLM 推理能力标记，并删除任何不在清单中的旧 TokenPlan 模型。

## 来源与验证

- 用户提供的完整品牌、模型 ID 与能力清单记录在
  `docs/research/2026-07-20-tokenplan-models.json`。
- 项目已配置的 TokenPlan `/models` 接口返回了精确 ID
  `qwen3.8-max-preview`。
- 真实探针验证该模型可完成文本生成和自动工具调用；模型强制思考，传入
  `enable_thinking=false` 会返回 `400 invalid_parameter_error`。
- 阿里云公开价格页尚未包含该模型，因此本次不猜测价格、缓存折扣或上下文长度。

## 注册策略

1. TokenPlan 注册表必须与来源 JSON 的模型 ID 集合一致。
2. LangBridge 商用模型属于独立 provider，不纳入本次 TokenPlan 白名单差异比较，也不删除。
3. 文本模型保留现有选择策略：当前最高级模型进入聊天选择，低阶兼容型号继续留在能力目录供内部路由使用。
4. 图片和视频生成模型必须设置 `chat_selectable=False` 和
   `reliable_tool_calling=False`，不能成为聊天或工具调用模型。
5. `qwen3.8-max-preview` 标记文本生成、推理、视觉理解和可靠自动工具调用；由于它拒绝关闭思考，`supports_thinking_budget`、
   `supports_forced_tool_choice` 与 `supports_explicit_cache` 均保持关闭，等待独立真网探针后再开放。
6. 预览模型只新增为可选项，不自动修改用户偏好、管理员活跃模型或环境默认模型。

## 计费与风险

- `qwen3.8-max-preview` 尚无可核验公开价格，不加入硬编码价格表。管理后台应继续将其显示为未定价调用，避免虚假成本数据。
- “限时加量 10 倍”只作为模型说明展示，不折算成价格或永久容量承诺。
- Preview 可能变更参数或下线；保留 Qwen3.7 系列作为明确的回退路径。

## 验收标准

- TokenPlan 模型集合与来源快照完全一致。
- Qwen3.8 在模型目录和聊天选择中可见，能力与保守参数标记正确。
- HappyHorse 三个模型只出现在非聊天能力目录。
- GLM 5.2、5.1、5 都具有 `reasoning` 能力。
- 现有显式用户偏好、管理员切换、默认模型与可靠工具模型路由测试全部通过。
