# Dossier: 拍照记餐确认态误报修复

| 字段 | 值 |
|---|---|
| slug | `meal-photo-confirmation-terminal` |
| 创建日期 | 2026-08-28 |
| 当前阶段 | G4 安全复审 |
| 状态 | implementation_verified |
| 负责 | Codex |
| 反馈环 | 生产 run/operation 取证 + Backend pytest + LLM regression gate + backend deploy |

## S0 · 用户反馈

> 直接拍照记餐 会报错 无法识别

## S1 · 生产取证与根因

- 2026-08-28 07:37（生产时区 UTC+8）的真实回合已成功完成图片上传和结构化食物识别，共识别出 2 项食物。
- 服务端已经创建 owner-scoped 私有照片资产和待确认 `DietPhotoDraft`，没有丢图，也没有发生不确定写入。
- 识别置信度未满足自动写入阈值时，策略正确选择 `confirm`；但主循环仍继续调用模型和 `health_record`。
- 写入适配器按设计拒绝重复写入，通用收口层却把这个安全拒绝当成失败，最终返回“本轮记录没有完成”，并因 `completion_status=error` 丢弃已构建的确认卡。
- 同一回合额外消耗了一次约 14 秒的模型工具决策，既不能提升识别结果，也不能安全绕过人工确认。

## G1 · 准入

- first_class_objects: `WriteIntent`、`ExecutionEvent`、`DietPhotoDraft`。
- core_loop_step: 餐食照片 -> 结构化识别 -> 自动写入或人工确认 -> 可验证饮食事实。
- safety_level: privacy-sensitive health write。
- **裁决: PASS。** 这是现有核心闭环的生产可靠性修复，不新增产品对象或自动化权限。

## G2 · 方案与安全边界

- 识别成功但需要人工核对时，直接以已持久化草稿和确定性确认卡结束本轮。
- 不再让 LLM 对同一草稿二次调用写工具；不降低自动写入置信度阈值；不伪造成功回执。
- `turn_outcome` 明确标记 `confirmation_required`，确认动作继续复用 owner-scoped `diet_record.create`。
- **裁决: PASS。** 改动只消除冗余模型/写入尝试，保留原有隐私、所有权、幂等和人工确认边界。

## S4 · 实现

- `backend/app/services/agent_executor.py`: 对已持久化的 `confirmation_pending` 餐食草稿执行确定性终止，返回全中文确认提示并保留确认卡。
- `backend/tests/test_agent_executor_food_vision.py`: 新增低置信度 Mobile 拍照记餐端到端回归，验证零 LLM 调用、零饮食写入、草稿保留、确认卡可见和正确终态。

## G3 · 测试

- TDD: 新回归先在旧逻辑下失败（`llm_calls == 1`），修复后通过。
- 餐食照片、策略、服务、写入/回合收口：175 项通过。
- Agent completion status：88 项通过。
- Ruff 与 `py_compile` 通过。
- LLM gate：无成本 62 项、轨迹契约 12 项、轨迹 golden 9 项通过；生产凭据下 live orchestrator 5/5 通过，平均分 0.94。
- **裁决: PASS。**

## G4 · 安全复审

- 待独立只读复审。

## G5 · 部署健康 / G6 · 上线验证

- 待本地提交、安全复审、主干 CI、后端部署与生产只读验证。
